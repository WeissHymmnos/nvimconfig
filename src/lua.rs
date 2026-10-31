use crate::model::{
    AddPluginRequest, ApiError, DeleteEntityRequest, Diagnostic, Field, Keymap, LuaValue,
    PatchRequest, Plugin, PluginManagerKind, Setting, SettingNamespace, Snapshot, TableEntry,
};
use full_moon::ast::punctuated::Pair;
use full_moon::ast::{
    Assignment, Expression, Field as AstField, FunctionArgs, FunctionCall, Index, LastStmt, Prefix,
    Suffix, TableConstructor, UnOp, Var,
};
use full_moon::node::Node;
use full_moon::tokenizer::{StringLiteralQuoteType, TokenKind, TokenReference, TokenType};
use full_moon::visitors::Visitor;
use rand::RngCore;
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, HashMap};
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::ops::Range;
use std::path::{Path, PathBuf};
use std::str::FromStr;
use std::time::{SystemTime, UNIX_EPOCH};
use walkdir::WalkDir;

#[derive(Clone, Debug)]
pub enum RuntimeEntity {
    Setting {
        namespace: SettingNamespace,
        name: String,
        id: String,
    },
    Keymap {
        prefix: String,
    },
    Plugin {
        name: String,
        manager: PluginManagerKind,
    },
}

#[derive(Clone, Debug)]
enum EditTarget {
    Replace(Range<usize>),
    ReplaceInverted(Range<usize>),
    ExpandBareStringToTable {
        range: Range<usize>,
        plugin_source: String,
        name: &'static str,
        invert_bool: bool,
    },
    Insert {
        offset: usize,
        needs_comma: bool,
        name: &'static str,
    },
    InsertArg {
        offset: usize,
    },
    InsertInverted {
        offset: usize,
        needs_comma: bool,
        name: &'static str,
    },
    VimscriptReplace(Range<usize>),
    #[allow(dead_code)]
    VimscriptInsert {
        offset: usize,
        needs_comma: bool,
        name: &'static str,
    },
}

#[derive(Clone, Debug)]
enum DeleteAction {
    RemoveLineOrSpan(Range<usize>),
    RemoveTableElement {
        element_range: Range<usize>,
        table_range: Range<usize>,
    },
    ClearLazySingleSpecFile(Range<usize>),
}

#[derive(Clone, Debug)]
struct DeleteTarget {
    file: PathBuf,
    revision: String,
    action: DeleteAction,
    entity: RuntimeEntity,
}

#[derive(Clone, Debug)]
struct Target {
    file: PathBuf,
    revision: String,
    edit: EditTarget,
    read_only: bool,
    entity: RuntimeEntity,
}

pub struct ScanResult {
    pub snapshot: Snapshot,
    targets: HashMap<String, Target>,
    delete_targets: HashMap<String, DeleteTarget>,
}

pub struct PatchSuccess {
    pub scan: ScanResult,
    pub entity: RuntimeEntity,
}

fn register_plugin_delete(
    plugin: &Plugin,
    delete_targets: &mut HashMap<String, DeleteTarget>,
    file: &Path,
    revision: &str,
    action: DeleteAction,
) {
    let dt = DeleteTarget {
        file: file.to_path_buf(),
        revision: revision.to_owned(),
        action,
        entity: RuntimeEntity::Plugin {
            name: plugin.name.clone(),
            manager: plugin.manager,
        },
    };
    for (_, field) in plugin.all_fields() {
        delete_targets.insert(field.id.clone(), dt.clone());
    }
    delete_targets.insert(plugin.name.clone(), dt);
}

pub fn scan(root: &Path) -> ScanResult {
    let root_display = root.to_string_lossy().into_owned();
    let mut snapshot = Snapshot::empty(root_display);
    let mut targets = HashMap::new();
    let mut delete_targets = HashMap::new();

    if !root.exists() {
        snapshot.diagnostics.push(Diagnostic {
            file: root.to_string_lossy().into_owned(),
            line: None,
            column: None,
            severity: Some("error".to_owned()),
            message: "config root does not exist".to_owned(),
        });
        return ScanResult {
            snapshot,
            targets,
            delete_targets,
        };
    }

    let mut files = Vec::new();
    for entry in WalkDir::new(root)
        .follow_links(false)
        .into_iter()
        .filter_entry(|e| {
            let name = e.file_name().to_string_lossy();
            name != ".backup" && name != ".git" && name != ".ucdp"
        })
    {
        match entry {
            Ok(entry) => {
                if entry.file_type().is_file() {
                    if let Some(ext) = entry.path().extension() {
                        if ext == "lua" || ext == "vim" {
                            files.push(entry.into_path());
                        }
                    }
                }
            }
            Err(error) => snapshot.diagnostics.push(Diagnostic {
                file: error.path().unwrap_or(root).to_string_lossy().into_owned(),
                line: None,
                column: None,
                severity: Some("error".to_owned()),
                message: error.to_string(),
            }),
        }
    }
    files.sort();

    for file in files {
        scan_into(root, &file, &mut snapshot, &mut targets, &mut delete_targets);
    }

    ScanResult {
        snapshot,
        targets,
        delete_targets,
    }
}

fn scan_into(
    root: &Path,
    file: &Path,
    snapshot: &mut Snapshot,
    targets: &mut HashMap<String, Target>,
    delete_targets: &mut HashMap<String, DeleteTarget>,
) {
    let is_vim = file.extension().is_some_and(|value| value == "vim");
    match fs::read(file) {
        Ok(bytes) => match String::from_utf8(bytes) {
            Ok(source) => {
                if is_vim {
                    scan_vimscript_file(
                        root,
                        file,
                        &source,
                        snapshot,
                        targets,
                        delete_targets,
                    );
                } else {
                    scan_file(
                        root,
                        file,
                        &source,
                        snapshot,
                        targets,
                        delete_targets,
                    );
                }
            }
            Err(error) => snapshot.diagnostics.push(Diagnostic {
                file: file.to_string_lossy().into_owned(),
                line: None,
                column: None,
                severity: Some("error".to_owned()),
                message: format!("file is not UTF-8: {error}"),
            }),
        },
        Err(error) => snapshot.diagnostics.push(Diagnostic {
            file: file.to_string_lossy().into_owned(),
            line: None,
            column: None,
            severity: Some("error".to_owned()),
            message: format!("cannot read file: {error}"),
        }),
    }
}

pub fn scan_single_file(root: &Path, file: &Path) -> ScanResult {
    let mut snapshot = Snapshot::empty(root.to_string_lossy().into_owned());
    let mut targets = HashMap::new();
    let mut delete_targets = HashMap::new();
    scan_into(root, file, &mut snapshot, &mut targets, &mut delete_targets);
    ScanResult {
        snapshot,
        targets,
        delete_targets,
    }
}

pub fn rescan_file_in_snapshot(root: &Path, file: &Path, previous: Option<&Snapshot>) -> ScanResult {
    let Some(prev) = previous else {
        return scan(root);
    };
    let single = scan_single_file(root, file);
    let file_str = file.to_string_lossy().into_owned();
    let mut snapshot = Snapshot::empty(prev.config_root.clone());

    let replace_slice = |old_files: Vec<String>| -> Option<usize> {
        old_files.iter().position(|f| f == &file_str)
    };

    // Incrementally update settings
    let old_setting_files: Vec<String> = prev.settings.iter().map(|s| s.field.file.clone()).collect();
    if let Some(first_idx) = replace_slice(old_setting_files) {
        let mut inserted = false;
        for (idx, s) in prev.settings.iter().enumerate() {
            if idx == first_idx && !inserted {
                snapshot.settings.extend(single.snapshot.settings.clone());
                inserted = true;
            }
            if s.field.file != file_str {
                snapshot.settings.push(s.clone());
            }
        }
    } else {
        snapshot.settings = prev.settings.clone();
        snapshot.settings.extend(single.snapshot.settings);
    }

    // Incrementally update keymaps
    let old_km_files: Vec<String> = prev.keymaps.iter().map(|k| k.mode.file.clone()).collect();
    if let Some(first_idx) = replace_slice(old_km_files) {
        let mut inserted = false;
        for (idx, k) in prev.keymaps.iter().enumerate() {
            if idx == first_idx && !inserted {
                snapshot.keymaps.extend(single.snapshot.keymaps.clone());
                inserted = true;
            }
            if k.mode.file != file_str {
                snapshot.keymaps.push(k.clone());
            }
        }
    } else {
        snapshot.keymaps = prev.keymaps.clone();
        snapshot.keymaps.extend(single.snapshot.keymaps);
    }

    // Incrementally update plugins
    let old_plg_files: Vec<String> = prev.plugins.iter().map(|p| p.enabled.file.clone()).collect();
    if let Some(first_idx) = replace_slice(old_plg_files) {
        let mut inserted = false;
        for (idx, p) in prev.plugins.iter().enumerate() {
            if idx == first_idx && !inserted {
                snapshot.plugins.extend(single.snapshot.plugins.clone());
                inserted = true;
            }
            if p.enabled.file != file_str {
                snapshot.plugins.push(p.clone());
            }
        }
    } else {
        snapshot.plugins = prev.plugins.clone();
        snapshot.plugins.extend(single.snapshot.plugins);
    }

    // Incrementally update diagnostics
    snapshot.diagnostics = prev
        .diagnostics
        .iter()
        .filter(|d| d.file != file_str)
        .cloned()
        .collect();
    snapshot.diagnostics.extend(single.snapshot.diagnostics);

    ScanResult {
        snapshot,
        targets: single.targets,
        delete_targets: single.delete_targets,
    }
}

fn scan_file(
    root: &Path,
    file: &Path,
    source: &str,
    snapshot: &mut Snapshot,
    targets: &mut HashMap<String, Target>,
    delete_targets: &mut HashMap<String, DeleteTarget>,
) {
    let ast = match full_moon::parse(source) {
        Ok(ast) => ast,
        Err(errors) => {
            for error in errors {
                snapshot.diagnostics.push(Diagnostic {
                    file: file.to_string_lossy().into_owned(),
                    line: Some(error.range().0.line() as u64),
                    column: Some(error.range().0.character() as u64),
                    severity: Some("error".to_owned()),
                    message: error.to_string(),
                });
            }
            return;
        }
    };

    let revision = revision(source.as_bytes());
    let relative = relative_path(root, file);
    let mut visitor = FileVisitor {
        file,
        relative: &relative,
        revision: &revision,
        source,
        settings: Vec::new(),
        keymaps: Vec::new(),
        plugins: Vec::new(),
        targets: HashMap::new(),
        delete_targets: HashMap::new(),
        occurrences: HashMap::new(),
        setting_occurrences: HashMap::new(),
        keymap_count: 0,
    };
    visitor.visit_ast(&ast);
    snapshot.settings.extend(visitor.settings);
    snapshot.keymaps.extend(visitor.keymaps);
    snapshot.plugins.extend(visitor.plugins);
    targets.extend(visitor.targets);
    delete_targets.extend(visitor.delete_targets);

    scan_lazy_returns(
        ast.nodes(),
        root,
        file,
        &relative,
        &revision,
        source,
        snapshot,
        targets,
        delete_targets,
        &mut visitor.occurrences,
    );
}

struct FileVisitor<'a> {
    file: &'a Path,
    relative: &'a str,
    revision: &'a str,
    source: &'a str,
    settings: Vec<Setting>,
    keymaps: Vec<Keymap>,
    plugins: Vec<Plugin>,
    targets: HashMap<String, Target>,
    delete_targets: HashMap<String, DeleteTarget>,
    occurrences: HashMap<String, usize>,
    setting_occurrences: HashMap<String, usize>,
    keymap_count: usize,
}

impl FileVisitor<'_> {
    fn add_setting(&mut self, var: &Var, expression: &Expression, assign_range: Option<Range<usize>>) {
        let Some((namespace, name)) = setting_path(var) else {
            return;
        };
        self.add_setting_expr(namespace, name, expression, assign_range);
    }

    fn add_setting_expr(
        &mut self,
        namespace: SettingNamespace,
        name: String,
        expression: &Expression,
        assign_range: Option<Range<usize>>,
    ) {
        let occurrence_key = format!("{namespace:?}:{name}");
        let occurrence = self
            .setting_occurrences
            .entry(occurrence_key)
            .and_modify(|value| *value += 1)
            .or_insert(0);
        let id = stable_id(&format!(
            "setting:{}:{}:{}:{occurrence}",
            self.relative,
            namespace_name(&namespace),
            name
        ));
        let field = self.field(id.clone(), expression);
        let entity = RuntimeEntity::Setting {
            namespace: namespace.clone(),
            name: name.clone(),
            id: id.clone(),
        };
        if let Some(stmt_range) = assign_range {
            self.delete_targets.insert(
                id.clone(),
                DeleteTarget {
                    file: self.file.to_path_buf(),
                    revision: self.revision.to_owned(),
                    action: DeleteAction::RemoveLineOrSpan(stmt_range),
                    entity: entity.clone(),
                },
            );
        }
        self.targets.insert(
            id.clone(),
            Target {
                file: self.file.to_path_buf(),
                revision: self.revision.to_owned(),
                edit: EditTarget::Replace(node_range(expression).range),
                read_only: false,
                entity,
            },
        );
        self.settings.push(Setting {
            namespace,
            name,
            field,
        });
    }

    fn keymap_semantic_token(expression: &Expression, source: &str) -> String {
        match parse_value(expression, source) {
            LuaValue::String { value } => value,
            LuaValue::Array { values } => values
                .into_iter()
                .map(|v| match v {
                    LuaValue::String { value } => value,
                    other => format!("{other:?}"),
                })
                .collect::<Vec<_>>()
                .join(","),
            LuaValue::Unsupported { source } => source.trim().to_owned(),
            other => format!("{other:?}"),
        }
    }

    fn add_keymap(&mut self, call: &FunctionCall) {
        if !is_keymap_set(call) {
            return;
        }
        let Some(arguments) = call.suffixes().find_map(|suffix| match suffix {
            Suffix::Call(full_moon::ast::Call::AnonymousCall(FunctionArgs::Parentheses {
                arguments,
                ..
            })) => Some(arguments),
            _ => None,
        }) else {
            return;
        };
        if arguments.len() != 3 && arguments.len() != 4 {
            return;
        }
        let mut args_iter = arguments.iter();
        let mode = args_iter.next().unwrap();
        let lhs = args_iter.next().unwrap();
        let rhs = args_iter.next().unwrap();
        let opts_opt = args_iter.next();
        let occurrence = self.keymap_count;
        self.keymap_count += 1;

        let mode_token = Self::keymap_semantic_token(mode, self.source);
        let lhs_token = Self::keymap_semantic_token(lhs, self.source);
        let sem_occ_key = format!("km:{}:{mode_token}:{lhs_token}", self.relative);
        let sem_occ = *self
            .occurrences
            .entry(sem_occ_key)
            .and_modify(|v| *v += 1)
            .or_insert(0);
        let prefix = if sem_occ == 0 {
            format!("keymap:{}:{mode_token}:{lhs_token}", self.relative)
        } else {
            format!("keymap:{}:{mode_token}:{lhs_token}:{sem_occ}", self.relative)
        };
        let legacy_prefix = format!("keymap:{}:{occurrence}", self.relative);

        let fields = [("mode", mode), ("lhs", lhs), ("rhs", rhs)];
        let mut keymap_fields = Vec::new();
        for (name, expression) in fields {
            let id = stable_id(&format!("{prefix}:{name}"));
            let legacy_id = stable_id(&format!("{legacy_prefix}:{name}"));
            let field = self.field(id.clone(), expression);
            let target_obj = Target {
                file: self.file.to_path_buf(),
                revision: self.revision.to_owned(),
                edit: EditTarget::Replace(node_range(expression).range),
                read_only: false,
                entity: RuntimeEntity::Keymap {
                    prefix: prefix.clone(),
                },
            };
            self.targets.insert(id, target_obj.clone());
            self.targets.insert(legacy_id, target_obj);
            keymap_fields.push(field);
        }
        let opts_id = stable_id(&format!("{prefix}:opts"));
        let legacy_opts_id = stable_id(&format!("{legacy_prefix}:opts"));
        let opts_field = if let Some(opts) = opts_opt {
            let field = self.field(opts_id.clone(), opts);
            let target_obj = Target {
                file: self.file.to_path_buf(),
                revision: self.revision.to_owned(),
                edit: EditTarget::Replace(node_range(opts).range),
                read_only: false,
                entity: RuntimeEntity::Keymap {
                    prefix: prefix.clone(),
                },
            };
            self.targets.insert(opts_id, target_obj.clone());
            self.targets.insert(legacy_opts_id, target_obj);
            field
        } else {
            let rhs_range = node_range(rhs);
            let field = Field {
                id: opts_id.clone(),
                file: self.file.to_string_lossy().into_owned(),
                revision: self.revision.to_owned(),
                line: Some(rhs_range.start_line),
                value: Some(LuaValue::Table {
                    entries: Vec::new(),
                }),
            };
            let target_obj = Target {
                file: self.file.to_path_buf(),
                revision: self.revision.to_owned(),
                edit: EditTarget::InsertArg {
                    offset: rhs_range.range.end,
                },
                read_only: false,
                entity: RuntimeEntity::Keymap {
                    prefix: prefix.clone(),
                },
            };
            self.targets.insert(opts_id, target_obj.clone());
            self.targets.insert(legacy_opts_id, target_obj);
            field
        };
        let mut fields = keymap_fields.into_iter();
        let km = Keymap {
            mode: fields.next().unwrap(),
            lhs: fields.next().unwrap(),
            rhs: fields.next().unwrap(),
            opts: opts_field,
        };
        let call_range = node_range(call).range;
        let dt = DeleteTarget {
            file: self.file.to_path_buf(),
            revision: self.revision.to_owned(),
            action: DeleteAction::RemoveLineOrSpan(call_range),
            entity: RuntimeEntity::Keymap {
                prefix: prefix.clone(),
            },
        };
        for field_id in [&km.mode.id, &km.lhs.id, &km.rhs.id, &km.opts.id] {
            self.delete_targets.insert(field_id.clone(), dt.clone());
        }
        for name in ["mode", "lhs", "rhs", "opts"] {
            self.delete_targets
                .insert(stable_id(&format!("{legacy_prefix}:{name}")), dt.clone());
        }
        self.keymaps.push(km);
    }

    fn field(&self, id: String, expression: &Expression) -> Field {
        Field {
            id,
            file: self.file.to_string_lossy().into_owned(),
            revision: self.revision.to_owned(),
            line: Some(node_range(expression).start_line),
            value: Some(parse_value(expression, self.source)),
        }
    }

    fn check_packer_use(&mut self, call: &FunctionCall) {
        let is_use = match call.prefix() {
            Prefix::Name(n) => n.token().to_string() == "use",
            _ => false,
        };
        if !is_use {
            return;
        }
        let call_range = node_range(call).range;

        for suffix in call.suffixes() {
            let Suffix::Call(full_moon::ast::Call::AnonymousCall(args)) = suffix else {
                continue;
            };
            match args {
                FunctionArgs::String(tok) => {
                    if let Some(plugin) = extract_bare_string_plugin(
                        tok,
                        self.file,
                        self.relative,
                        self.revision,
                        PluginManagerKind::Packer,
                        &mut self.targets,
                        &mut self.occurrences,
                    ) {
                        register_plugin_delete(
                            &plugin,
                            &mut self.delete_targets,
                            self.file,
                            self.revision,
                            DeleteAction::RemoveLineOrSpan(call_range.clone()),
                        );
                        self.plugins.push(plugin);
                    }
                }
                FunctionArgs::TableConstructor(tc) => {
                    let prev_len = self.plugins.len();
                    extract_packer_table(
                        tc,
                        self.file,
                        self.relative,
                        self.revision,
                        self.source,
                        &mut self.plugins,
                        &mut self.targets,
                        &mut self.occurrences,
                    );
                    if let Some(first_plugin) = self.plugins.get(prev_len) {
                        register_plugin_delete(
                            first_plugin,
                            &mut self.delete_targets,
                            self.file,
                            self.revision,
                            DeleteAction::RemoveLineOrSpan(call_range.clone()),
                        );
                    }
                }
                FunctionArgs::Parentheses { arguments, .. } => {
                    for arg in arguments {
                        match arg {
                            Expression::String(tok) => {
                                if let Some(plugin) = extract_bare_string_plugin(
                                    tok,
                                    self.file,
                                    self.relative,
                                    self.revision,
                                    PluginManagerKind::Packer,
                                    &mut self.targets,
                                    &mut self.occurrences,
                                ) {
                                    register_plugin_delete(
                                        &plugin,
                                        &mut self.delete_targets,
                                        self.file,
                                        self.revision,
                                        DeleteAction::RemoveLineOrSpan(call_range.clone()),
                                    );
                                    self.plugins.push(plugin);
                                }
                            }
                            Expression::TableConstructor(tc) => {
                                let prev_len = self.plugins.len();
                                extract_packer_table(
                                    tc,
                                    self.file,
                                    self.relative,
                                    self.revision,
                                    self.source,
                                    &mut self.plugins,
                                    &mut self.targets,
                                    &mut self.occurrences,
                                );
                                if let Some(first_plugin) = self.plugins.get(prev_len) {
                                    register_plugin_delete(
                                        first_plugin,
                                        &mut self.delete_targets,
                                        self.file,
                                        self.revision,
                                        DeleteAction::RemoveLineOrSpan(call_range.clone()),
                                    );
                                }
                            }
                            _ => {}
                        }
                    }
                }
                _ => {}
            }
        }
    }

    fn check_lazy_setup(&mut self, call: &FunctionCall) {
        let Some(table) = is_lazy_setup_call(call) else {
            return;
        };
        let mut spec_table = table;
        for field in table.fields().iter() {
            if let Some((k, expr)) = named_field(field, self.source) {
                if k == "spec" {
                    if let Expression::TableConstructor(tc) = expr {
                        spec_table = tc;
                        break;
                    }
                }
            }
        }
        let table_range = node_range(spec_table).range;
        match classify_lazy_table(spec_table, self.source, true) {
            LazyTableKind::SingleSpec(tc) => {
                if let Some(p) = extract_lazy_plugin_from_table(
                    tc,
                    self.file,
                    self.relative,
                    self.revision,
                    self.source,
                    &mut self.targets,
                    &mut self.occurrences,
                ) {
                    register_plugin_delete(
                        &p,
                        &mut self.delete_targets,
                        self.file,
                        self.revision,
                        DeleteAction::ClearLazySingleSpecFile(node_range(tc).range),
                    );
                    self.plugins.push(p);
                }
            }
            LazyTableKind::SpecList(items) => {
                for item in items {
                    match item {
                        LazySpecItem::Table(tc) => {
                            if let Some(p) = extract_lazy_plugin_from_table(
                                tc,
                                self.file,
                                self.relative,
                                self.revision,
                                self.source,
                                &mut self.targets,
                                &mut self.occurrences,
                            ) {
                                register_plugin_delete(
                                    &p,
                                    &mut self.delete_targets,
                                    self.file,
                                    self.revision,
                                    DeleteAction::RemoveTableElement {
                                        element_range: node_range(tc).range,
                                        table_range: table_range.clone(),
                                    },
                                );
                                self.plugins.push(p);
                            }
                        }
                        LazySpecItem::String(tok) => {
                            if let Some(p) = extract_bare_string_plugin(
                                tok,
                                self.file,
                                self.relative,
                                self.revision,
                                PluginManagerKind::Lazy,
                                &mut self.targets,
                                &mut self.occurrences,
                            ) {
                                register_plugin_delete(
                                    &p,
                                    &mut self.delete_targets,
                                    self.file,
                                    self.revision,
                                    DeleteAction::RemoveTableElement {
                                        element_range: node_range(tok).range,
                                        table_range: table_range.clone(),
                                    },
                                );
                                self.plugins.push(p);
                            }
                        }
                    }
                }
            }
            _ => {}
        }
    }

    fn check_embedded_vim_cmd(&mut self, call: &FunctionCall) {
        if !is_vim_cmd(call) {
            return;
        }
        if let Some((content, content_offset, line_offset)) = extract_cmd_string(call) {
            scan_vimscript_text(
                &content,
                content_offset,
                line_offset,
                self.file,
                self.relative,
                self.revision,
                &mut self.plugins,
                &mut self.targets,
                &mut self.delete_targets,
                &mut self.occurrences,
            );
        }
    }

    fn check_plug_fn_call(&mut self, call: &FunctionCall) {
        extract_plug_lua_call(
            call,
            self.file,
            self.relative,
            self.revision,
            self.source,
            &mut self.plugins,
            &mut self.targets,
            &mut self.delete_targets,
            &mut self.occurrences,
        );
    }

    fn check_opt_method_call(&mut self, call: &FunctionCall) {
        let Prefix::Name(prefix) = call.prefix() else {
            return;
        };
        let prefix_str = prefix.token().to_string();
        let mut parts = Vec::new();
        let mut method_expr: Option<&Expression> = None;

        for suffix in call.suffixes() {
            match suffix {
                Suffix::Index(Index::Dot { name, .. }) => {
                    parts.push(name.token().to_string());
                }
                Suffix::Index(Index::Brackets { expression, .. }) => {
                    if let Expression::String(tok) = expression {
                        if let Some(s) = parse_string(tok) {
                            parts.push(s);
                        } else {
                            return;
                        }
                    } else {
                        return;
                    }
                }
                Suffix::Call(full_moon::ast::Call::MethodCall(method_call)) => {
                    let method_name = method_call.name().token().to_string();
                    if !matches!(method_name.as_str(), "append" | "prepend" | "remove") {
                        return;
                    }
                    match method_call.args() {
                        FunctionArgs::Parentheses { arguments, .. } if arguments.len() == 1 => {
                            method_expr = arguments.iter().next();
                        }
                        _ => return,
                    }
                }
                _ => return,
            }
        }

        let Some(expr) = method_expr else {
            return;
        };
        let opt_name = if matches!(prefix_str.as_str(), "opt" | "o" | "wo" | "bo") && parts.len() == 1 {
            parts.remove(0)
        } else if prefix_str == "vim"
            && parts.len() == 2
            && matches!(parts[0].as_str(), "opt" | "o" | "wo" | "bo")
        {
            parts.remove(1)
        } else {
            return;
        };

        self.add_setting_expr(
            SettingNamespace::Opt,
            opt_name,
            expr,
            Some(node_range(call).range),
        );
    }
}

impl Visitor for FileVisitor<'_> {
    fn visit_assignment(&mut self, assignment: &Assignment) {
        let assign_range = if assignment.variables().len() == 1 {
            Some(node_range(assignment).range)
        } else {
            None
        };
        for (variable, expression) in assignment
            .variables()
            .iter()
            .zip(assignment.expressions().iter())
        {
            self.add_setting(variable, expression, assign_range.clone());
        }
    }

    fn visit_function_call(&mut self, call: &FunctionCall) {
        self.add_keymap(call);
        self.check_packer_use(call);
        self.check_lazy_setup(call);
        self.check_embedded_vim_cmd(call);
        self.check_plug_fn_call(call);
        self.check_opt_method_call(call);
    }
}

pub fn extract_plugin_name(source: &str) -> String {
    if source.is_empty() {
        return "unnamed".to_string();
    }
    let mut clean = source.trim().trim_end_matches('/');
    if clean.ends_with(".git") {
        clean = &clean[..clean.len() - 4];
    }
    if let Some(pos) = clean.rfind('/') {
        clean = &clean[pos + 1..];
    } else if let Some(pos) = clean.rfind(':') {
        clean = &clean[pos + 1..];
    }
    if clean.is_empty() {
        "unnamed".to_string()
    } else {
        clean.to_string()
    }
}

fn is_lazy_property(name: &str) -> bool {
    matches!(
        name,
        "enabled"
            | "opts"
            | "config"
            | "dependencies"
            | "lazy"
            | "cmd"
            | "ft"
            | "event"
            | "keys"
            | "branch"
            | "tag"
            | "commit"
            | "version"
            | "pin"
            | "build"
            | "name"
            | "dir"
            | "url"
            | "dev"
            | "priority"
            | "cond"
    )
}

enum LazyTableKind<'a> {
    SingleSpec(&'a TableConstructor),
    SpecList(Vec<LazySpecItem<'a>>),
    Import(#[allow(dead_code)] String),
    NotPlugin,
}

enum LazySpecItem<'a> {
    Table(&'a TableConstructor),
    String(&'a TokenReference),
}

fn classify_lazy_table<'a>(
    table: &'a TableConstructor,
    source: &str,
    is_in_plugins_dir: bool,
) -> LazyTableKind<'a> {
    for field in table.fields().iter() {
        if let Some((key, expr)) = named_field(field, source) {
            if key == "import" {
                if let LuaValue::String { value } = parse_value(expr, source) {
                    return LazyTableKind::Import(value);
                }
            }
        }
    }

    let mut positional_tables = Vec::new();
    let mut positional_strings = Vec::new();
    let mut has_named_property = false;
    let mut first_positional_is_repo = false;

    for (idx, field) in table.fields().iter().enumerate() {
        match field {
            AstField::NoKey(expr) => match expr {
                Expression::TableConstructor(tc) => positional_tables.push(tc),
                Expression::String(tok) => {
                    if idx == 0 {
                        if let Some(s) = parse_string(tok) {
                            if s.contains('/') || is_in_plugins_dir {
                                first_positional_is_repo = true;
                            }
                        }
                    }
                    positional_strings.push(tok);
                }
                _ => {}
            },
            AstField::NameKey { key, .. } => {
                let name = key.token().to_string();
                if is_lazy_property(&name) {
                    has_named_property = true;
                }
            }
            AstField::ExpressionKey { key, .. } => {
                if let LuaValue::String { value } = parse_value(key, source) {
                    if is_lazy_property(&value) {
                        has_named_property = true;
                    }
                }
            }
            _ => {}
        }
    }

    if !positional_tables.is_empty() {
        let mut items = Vec::new();
        for tc in positional_tables {
            items.push(LazySpecItem::Table(tc));
        }
        for tok in positional_strings {
            items.push(LazySpecItem::String(tok));
        }
        return LazyTableKind::SpecList(items);
    }

    if positional_strings.len() > 1 && (is_in_plugins_dir || first_positional_is_repo) {
        let mut items = Vec::new();
        for tok in positional_strings {
            items.push(LazySpecItem::String(tok));
        }
        return LazyTableKind::SpecList(items);
    }

    if has_named_property && (first_positional_is_repo || is_in_plugins_dir) {
        return LazyTableKind::SingleSpec(table);
    }

    if positional_strings.len() == 1 && (first_positional_is_repo || is_in_plugins_dir) {
        return LazyTableKind::SingleSpec(table);
    }

    LazyTableKind::NotPlugin
}

fn lazy_slot_static_name(slot: &str) -> Option<&'static str> {
    match slot {
        "enabled" => Some("enabled"),
        "event" => Some("event"),
        "keys" => Some("keys"),
        "opts" => Some("opts"),
        "lazy" => Some("lazy"),
        "cmd" => Some("cmd"),
        "ft" => Some("ft"),
        "dependencies" => Some("dependencies"),
        "branch" => Some("branch"),
        "tag" => Some("tag"),
        "commit" => Some("commit"),
        "version" => Some("version"),
        "pin" => Some("pin"),
        "build" => Some("build"),
        _ => None,
    }
}

fn packer_slot_static_name(slot: &str) -> Option<&'static str> {
    match slot {
        "lazy" => Some("opt"),
        "build" => Some("run"),
        "dependencies" => Some("requires"),
        "pin" => Some("lock"),
        "event" => Some("event"),
        "keys" => Some("keys"),
        "cmd" => Some("cmd"),
        "ft" => Some("ft"),
        "branch" => Some("branch"),
        "tag" => Some("tag"),
        "commit" => Some("commit"),
        "opts" => Some("config"),
        _ => None,
    }
}

fn extract_setup_table_from_call<'a>(call: &'a FunctionCall) -> Option<&'a TableConstructor> {
    let suffixes: Vec<_> = call.suffixes().collect();
    for window in suffixes.windows(2) {
        if let Suffix::Index(Index::Dot { name, .. }) = window[0] {
            let method = name.token().to_string();
            if method == "setup" || method == "set_config" {
                if let Some(tc) = extract_table_arg(window[1]) {
                    return Some(tc);
                }
            }
        }
    }
    for suffix in &suffixes {
        if let Suffix::Call(full_moon::ast::Call::MethodCall(mc)) = suffix {
            let method = mc.name().token().to_string();
            if method == "setup" || method == "set_config" {
                match mc.args() {
                    FunctionArgs::TableConstructor(tc) => return Some(tc),
                    FunctionArgs::Parentheses { arguments, .. } => {
                        if let Some(Expression::TableConstructor(tc)) = arguments.iter().next() {
                            return Some(tc);
                        }
                    }
                    _ => {}
                }
            }
        }
    }
    None
}

fn find_setup_table_in_block<'a>(
    block: &'a full_moon::ast::Block,
) -> Option<&'a TableConstructor> {
    for stmt in block.stmts() {
        match stmt {
            full_moon::ast::Stmt::FunctionCall(call) => {
                if let Some(tc) = extract_setup_table_from_call(call) {
                    return Some(tc);
                }
            }
            full_moon::ast::Stmt::Do(do_stmt) => {
                if let Some(tc) = find_setup_table_in_block(do_stmt.block()) {
                    return Some(tc);
                }
            }
            full_moon::ast::Stmt::If(if_stmt) => {
                if let Some(tc) = find_setup_table_in_block(if_stmt.block()) {
                    return Some(tc);
                }
                if let Some(else_ifs) = if_stmt.else_if() {
                    for else_if in else_ifs {
                        if let Some(tc) = find_setup_table_in_block(else_if.block()) {
                            return Some(tc);
                        }
                    }
                }
                if let Some(else_block) = if_stmt.else_block() {
                    if let Some(tc) = find_setup_table_in_block(else_block) {
                        return Some(tc);
                    }
                }
            }
            full_moon::ast::Stmt::LocalAssignment(assign) => {
                for expr in assign.expressions() {
                    if let Expression::FunctionCall(call) = expr {
                        if let Some(tc) = extract_setup_table_from_call(call) {
                            return Some(tc);
                        }
                    }
                }
            }
            full_moon::ast::Stmt::Assignment(assign) => {
                for expr in assign.expressions() {
                    if let Expression::FunctionCall(call) = expr {
                        if let Some(tc) = extract_setup_table_from_call(call) {
                            return Some(tc);
                        }
                    }
                }
            }
            _ => {}
        }
    }
    None
}

fn find_setup_table_in_expr<'a>(expr: &'a Expression) -> Option<&'a TableConstructor> {
    match expr {
        Expression::Function(anon_fn) => find_setup_table_in_block(anon_fn.body().block()),
        _ => None,
    }
}

fn extract_lazy_plugin_from_table(
    spec: &TableConstructor,
    file: &Path,
    relative: &str,
    revision: &str,
    source: &str,
    targets: &mut HashMap<String, Target>,
    occurrences: &mut HashMap<String, usize>,
) -> Option<Plugin> {
    let mut plugin_source = None;
    let mut custom_name = None;

    for field in spec.fields().iter() {
        match field {
            AstField::NoKey(expr) if plugin_source.is_none() => {
                if let Expression::String(tok) = expr {
                    plugin_source = parse_string(tok);
                } else if let LuaValue::String { value } = parse_value(expr, source) {
                    plugin_source = Some(value);
                }
            }
            AstField::NameKey { key, value, .. } => {
                let k = key.token().to_string();
                if k == "name" {
                    if let LuaValue::String { value: n } = parse_value(value, source) {
                        custom_name = Some(n);
                    }
                } else if plugin_source.is_none() && (k == "url" || k == "dir") {
                    if let LuaValue::String { value: s } = parse_value(value, source) {
                        plugin_source = Some(s);
                    }
                }
            }
            _ => {}
        }
    }

    let plugin_source = plugin_source?;
    let name = custom_name.unwrap_or_else(|| extract_plugin_name(&plugin_source));

    let occurrence = occurrences
        .entry(plugin_source.clone())
        .and_modify(|v| *v += 1)
        .or_insert(0);
    let prefix = format!("plugin:{relative}:{plugin_source}:{occurrence}");
    let entity = RuntimeEntity::Plugin {
        name: name.clone(),
        manager: PluginManagerKind::Lazy,
    };

    let mut found_fields: HashMap<String, (Range<usize>, Field)> = HashMap::new();
    let mut config_expr: Option<&Expression> = None;

    for field in spec.fields().iter() {
        let Some((key, expr)) = named_field(field, source) else {
            continue;
        };
        let slot_name = match key.as_str() {
            "cond" => "enabled",
            "enabled" | "event" | "keys" | "opts" | "lazy" | "cmd" | "ft" | "dependencies"
            | "branch" | "tag" | "commit" | "version" | "pin" | "build" | "config" => {
                key.as_str()
            }
            _ => continue,
        };

        if found_fields.contains_key(slot_name) {
            continue;
        }
        if slot_name == "config" {
            config_expr = Some(expr);
        }

        let id = stable_id(&format!("{prefix}:{slot_name}"));
        let range = node_range(expr);
        let val = parse_value(expr, source);
        let field_obj = Field {
            id: id.clone(),
            file: file.to_string_lossy().into_owned(),
            revision: revision.to_owned(),
            line: Some(range.start_line),
            value: Some(val),
        };
        let target_obj = Target {
            file: file.to_path_buf(),
            revision: revision.to_owned(),
            edit: EditTarget::Replace(range.range.clone()),
            read_only: slot_name == "config"
                && matches!(field_obj.value.as_ref(), Some(LuaValue::Unsupported { .. })),
            entity: entity.clone(),
        };
        targets.insert(id, target_obj.clone());
        targets.insert(format!("plugin_slot:{}:{slot_name}", name), target_obj);
        found_fields.insert(slot_name.to_string(), (range.range, field_obj));
    }

    // Lift `.setup({ ... })` or `.set_config({ ... })` inside `config = function() ... end` into `opts`
    // when top-level `opts` is not explicitly specified on the plugin table.
    if !found_fields.contains_key("opts") {
        if let Some(cfg_expr) = config_expr {
            if let Some(setup_tc) = find_setup_table_in_expr(cfg_expr) {
                let id = stable_id(&format!("{prefix}:opts"));
                let range = node_range(setup_tc);
                let val =
                    parse_table(setup_tc, source).unwrap_or_else(|| unsupported(setup_tc, source));
                let field_obj = Field {
                    id: id.clone(),
                    file: file.to_string_lossy().into_owned(),
                    revision: revision.to_owned(),
                    line: Some(range.start_line),
                    value: Some(val),
                };
                let target_obj = Target {
                    file: file.to_path_buf(),
                    revision: revision.to_owned(),
                    edit: EditTarget::Replace(range.range.clone()),
                    read_only: false,
                    entity: entity.clone(),
                };
                targets.insert(id, target_obj.clone());
                targets.insert(format!("plugin_slot:{}:opts", name), target_obj);
                found_fields.insert("opts".to_string(), (range.range, field_obj));
            }
        }
    }

    let (offset, needs_comma) = match spec.fields().last() {
        Some(pair) => match pair.punctuation() {
            Some(punctuation) => (punctuation.token().end_position().bytes(), false),
            None => (node_range(pair.value()).range.end, true),
        },
        None => (
            spec.braces().tokens().0.token().end_position().bytes(),
            false,
        ),
    };

    for slot in [
        "enabled",
        "event",
        "keys",
        "opts",
        "lazy",
        "cmd",
        "ft",
        "dependencies",
        "branch",
        "tag",
        "commit",
        "version",
        "pin",
        "build",
    ] {
        if !found_fields.contains_key(slot) {
            if let Some(slot_static) = lazy_slot_static_name(slot) {
                let id = stable_id(&format!("{prefix}:{slot}"));
                let target_obj = Target {
                    file: file.to_path_buf(),
                    revision: revision.to_owned(),
                    edit: EditTarget::Insert {
                        offset,
                        needs_comma,
                        name: slot_static,
                    },
                    read_only: false,
                    entity: entity.clone(),
                };
                targets.insert(id, target_obj.clone());
                targets.insert(format!("plugin_slot:{}:{slot}", name), target_obj);
            }
        }
    }

    let mut core_fields = HashMap::new();
    for slot in ["enabled", "event", "keys", "opts"] {
        if let Some((_, field_obj)) = found_fields.remove(slot) {
            core_fields.insert(slot, field_obj);
        } else {
            let id = stable_id(&format!("{prefix}:{slot}"));
            let field_obj = Field {
                id,
                file: file.to_string_lossy().into_owned(),
                revision: revision.to_owned(),
                line: None,
                value: if slot == "enabled" {
                    Some(LuaValue::Boolean { value: true })
                } else {
                    None
                },
            };
            core_fields.insert(slot, field_obj);
        }
    }

    let mut plugin = Plugin::new_lazy(
        name,
        plugin_source,
        core_fields.remove("enabled").unwrap(),
        core_fields.remove("event").unwrap(),
        core_fields.remove("keys").unwrap(),
        core_fields.remove("opts").unwrap(),
    );

    if let Some((_, f)) = found_fields.remove("lazy") {
        plugin = plugin.with_lazy(f);
    }
    if let Some((_, f)) = found_fields.remove("cmd") {
        plugin = plugin.with_cmd(f);
    }
    if let Some((_, f)) = found_fields.remove("ft") {
        plugin = plugin.with_ft(f);
    }
    if let Some((_, f)) = found_fields.remove("dependencies") {
        plugin = plugin.with_dependencies(f);
    }
    if let Some((_, f)) = found_fields.remove("branch") {
        plugin = plugin.with_branch(f);
    }
    if let Some((_, f)) = found_fields.remove("tag") {
        plugin = plugin.with_tag(f);
    }
    if let Some((_, f)) = found_fields.remove("commit") {
        plugin = plugin.with_commit(f);
    }
    if let Some((_, f)) = found_fields.remove("version") {
        plugin = plugin.with_version(f);
    }
    if let Some((_, f)) = found_fields.remove("pin") {
        plugin = plugin.with_pin(f);
    }
    if let Some((_, f)) = found_fields.remove("build") {
        plugin = plugin.with_build(f);
    }
    if let Some((_, f)) = found_fields.remove("config") {
        plugin = plugin.with_config(f);
    }

    Some(plugin)
}

fn extract_bare_string_plugin(
    tok: &TokenReference,
    file: &Path,
    relative: &str,
    revision: &str,
    manager: PluginManagerKind,
    targets: &mut HashMap<String, Target>,
    occurrences: &mut HashMap<String, usize>,
) -> Option<Plugin> {
    let plugin_source = parse_string(tok)?;
    let name = extract_plugin_name(&plugin_source);
    let occurrence = occurrences
        .entry(plugin_source.clone())
        .and_modify(|v| *v += 1)
        .or_insert(0);
    let prefix = format!("plugin:{relative}:{plugin_source}:{occurrence}");
    let entity = RuntimeEntity::Plugin {
        name: name.clone(),
        manager,
    };

    let line = Some(tok.token().start_position().line() as u64);
    let enabled_id = stable_id(&format!("{prefix}:enabled"));
    let enabled = Field {
        id: enabled_id.clone(),
        file: file.to_string_lossy().into_owned(),
        revision: revision.to_owned(),
        line,
        value: Some(LuaValue::Boolean { value: true }),
    };

    let range = node_range(tok).range;
    let (enabled_attr_name, invert_enabled) = match manager {
        PluginManagerKind::Packer => ("disable", true),
        _ => ("enabled", false),
    };
    let enabled_target = Target {
        file: file.to_path_buf(),
        revision: revision.to_owned(),
        edit: EditTarget::ExpandBareStringToTable {
            range: range.clone(),
            plugin_source: plugin_source.clone(),
            name: enabled_attr_name,
            invert_bool: invert_enabled,
        },
        read_only: false,
        entity: entity.clone(),
    };
    targets.insert(enabled_id, enabled_target.clone());
    targets.insert(format!("plugin_slot:{}:enabled", name), enabled_target);

    for slot in [
        "event",
        "keys",
        "opts",
        "lazy",
        "cmd",
        "ft",
        "dependencies",
        "branch",
        "tag",
        "commit",
        "version",
        "pin",
        "build",
    ] {
        let attr_name = match manager {
            PluginManagerKind::Packer => packer_slot_static_name(slot),
            _ => lazy_slot_static_name(slot),
        };
        if let Some(attr_name) = attr_name {
            let slot_id = stable_id(&format!("{prefix}:{slot}"));
            let slot_target = Target {
                file: file.to_path_buf(),
                revision: revision.to_owned(),
                edit: EditTarget::ExpandBareStringToTable {
                    range: range.clone(),
                    plugin_source: plugin_source.clone(),
                    name: attr_name,
                    invert_bool: false,
                },
                read_only: false,
                entity: entity.clone(),
            };
            targets.insert(slot_id, slot_target.clone());
            targets.insert(format!("plugin_slot:{}:{slot}", name), slot_target);
        }
    }

    let event = Field {
        id: stable_id(&format!("{prefix}:event")),
        file: file.to_string_lossy().into_owned(),
        revision: revision.to_owned(),
        line: None,
        value: None,
    };
    let keys = Field {
        id: stable_id(&format!("{prefix}:keys")),
        file: file.to_string_lossy().into_owned(),
        revision: revision.to_owned(),
        line: None,
        value: None,
    };
    let opts = Field {
        id: stable_id(&format!("{prefix}:opts")),
        file: file.to_string_lossy().into_owned(),
        revision: revision.to_owned(),
        line: None,
        value: None,
    };

    Some(Plugin::new(
        name,
        plugin_source,
        manager,
        enabled,
        event,
        keys,
        opts,
    ))
}

fn scan_lazy_returns(
    block: &full_moon::ast::Block,
    root: &Path,
    file: &Path,
    relative: &str,
    revision: &str,
    source: &str,
    snapshot: &mut Snapshot,
    targets: &mut HashMap<String, Target>,
    delete_targets: &mut HashMap<String, DeleteTarget>,
    occurrences: &mut HashMap<String, usize>,
) {
    let Some(LastStmt::Return(return_stmt)) = block.last_stmt() else {
        return;
    };
    if return_stmt.returns().len() != 1 {
        return;
    }
    let expr = return_stmt.returns().iter().next().unwrap();

    let is_in_plugins_dir = file.starts_with(root.join("lua").join("plugins"))
        || file
            .parent()
            .and_then(|p| p.file_name())
            .is_some_and(|n| n == "plugins" || n == "lazy");

    match expr {
        Expression::TableConstructor(table) => {
            let table_range = node_range(table).range;
            match classify_lazy_table(table, source, is_in_plugins_dir) {
                LazyTableKind::SingleSpec(spec_table) => {
                    if let Some(plugin) = extract_lazy_plugin_from_table(
                        spec_table,
                        file,
                        relative,
                        revision,
                        source,
                        targets,
                        occurrences,
                    ) {
                        register_plugin_delete(
                            &plugin,
                            delete_targets,
                            file,
                            revision,
                            DeleteAction::ClearLazySingleSpecFile(node_range(spec_table).range),
                        );
                        snapshot.plugins.push(plugin);
                    }
                }
                LazyTableKind::SpecList(items) => {
                    for item in items {
                        match item {
                            LazySpecItem::Table(spec_table) => {
                                if let Some(plugin) = extract_lazy_plugin_from_table(
                                    spec_table,
                                    file,
                                    relative,
                                    revision,
                                    source,
                                    targets,
                                    occurrences,
                                ) {
                                    register_plugin_delete(
                                        &plugin,
                                        delete_targets,
                                        file,
                                        revision,
                                        DeleteAction::RemoveTableElement {
                                            element_range: node_range(spec_table).range,
                                            table_range: table_range.clone(),
                                        },
                                    );
                                    snapshot.plugins.push(plugin);
                                }
                            }
                            LazySpecItem::String(tok) => {
                                if let Some(plugin) = extract_bare_string_plugin(
                                    tok,
                                    file,
                                    relative,
                                    revision,
                                    PluginManagerKind::Lazy,
                                    targets,
                                    occurrences,
                                ) {
                                    register_plugin_delete(
                                        &plugin,
                                        delete_targets,
                                        file,
                                        revision,
                                        DeleteAction::RemoveTableElement {
                                            element_range: node_range(tok).range,
                                            table_range: table_range.clone(),
                                        },
                                    );
                                    snapshot.plugins.push(plugin);
                                }
                            }
                        }
                    }
                }
                LazyTableKind::Import(_) | LazyTableKind::NotPlugin => {}
            }
        }
        Expression::String(tok) => {
            if is_in_plugins_dir {
                if let Some(plugin) = extract_bare_string_plugin(
                    tok,
                    file,
                    relative,
                    revision,
                    PluginManagerKind::Lazy,
                    targets,
                    occurrences,
                ) {
                    register_plugin_delete(
                        &plugin,
                        delete_targets,
                        file,
                        revision,
                        DeleteAction::ClearLazySingleSpecFile(node_range(tok).range),
                    );
                    snapshot.plugins.push(plugin);
                }
            }
        }
        _ => {}
    }
}

fn is_lazy_setup_call<'a>(call: &'a FunctionCall) -> Option<&'a TableConstructor> {
    let suffixes: Vec<_> = call.suffixes().collect();
    if let Prefix::Name(prefix) = call.prefix() {
        let p_str = prefix.token().to_string();
        if p_str == "require" && suffixes.len() >= 3 {
            if let Suffix::Call(full_moon::ast::Call::AnonymousCall(args)) = suffixes[0] {
                let is_lazy_req = match args {
                    FunctionArgs::String(tok) => parse_string(tok).as_deref() == Some("lazy"),
                    FunctionArgs::Parentheses { arguments, .. } => {
                        if let Some(Expression::String(tok)) = arguments.iter().next() {
                            parse_string(tok).as_deref() == Some("lazy")
                        } else {
                            false
                        }
                    }
                    _ => false,
                };
                if is_lazy_req {
                    if let Suffix::Index(Index::Dot { name, .. }) = suffixes[1] {
                        if name.token().to_string() == "setup" {
                            return extract_table_arg(suffixes[2]);
                        }
                    }
                }
            }
        } else if p_str == "lazy" && suffixes.len() >= 2 {
            if let Suffix::Index(Index::Dot { name, .. }) = suffixes[0] {
                if name.token().to_string() == "setup" {
                    return extract_table_arg(suffixes[1]);
                }
            }
        }
    }
    None
}

fn extract_table_arg<'a>(suffix: &'a Suffix) -> Option<&'a TableConstructor> {
    if let Suffix::Call(full_moon::ast::Call::AnonymousCall(args)) = suffix {
        match args {
            FunctionArgs::TableConstructor(tc) => return Some(tc),
            FunctionArgs::Parentheses { arguments, .. } => {
                if let Some(Expression::TableConstructor(tc)) = arguments.iter().next() {
                    return Some(tc);
                }
            }
            _ => {}
        }
    }
    None
}

fn extract_packer_table(
    tc: &TableConstructor,
    file: &Path,
    relative: &str,
    revision: &str,
    source: &str,
    plugins: &mut Vec<Plugin>,
    targets: &mut HashMap<String, Target>,
    occurrences: &mut HashMap<String, usize>,
) {
    let mut plugin_source = None;
    let mut custom_name = None;
    let mut inner_specs = Vec::new();

    let mut is_first = true;
    for field in tc.fields().iter() {
        match field {
            AstField::NoKey(expr) => {
                if is_first {
                    is_first = false;
                    if let Expression::String(tok) = expr {
                        plugin_source = parse_string(tok);
                    } else if let LuaValue::String { value } = parse_value(expr, source) {
                        plugin_source = Some(value);
                    }
                } else if let Expression::TableConstructor(inner_tc) = expr {
                    inner_specs.push(inner_tc);
                }
            }
            AstField::NameKey { key, value, .. } => {
                let k = key.token().to_string();
                if k == "as" {
                    if let LuaValue::String { value: n } = parse_value(value, source) {
                        custom_name = Some(n);
                    }
                }
            }
            _ => {}
        }
    }

    if let Some(plugin_source) = plugin_source {
        let name = custom_name.unwrap_or_else(|| extract_plugin_name(&plugin_source));
        let occurrence = occurrences
            .entry(plugin_source.clone())
            .and_modify(|v| *v += 1)
            .or_insert(0);
        let prefix = format!("plugin:{relative}:{plugin_source}:{occurrence}");
        let entity = RuntimeEntity::Plugin {
            name: name.clone(),
            manager: PluginManagerKind::Packer,
        };

        let mut found_fields: HashMap<String, (Range<usize>, Field)> = HashMap::new();
        let mut disable_field = None;
        let mut config_expr: Option<&Expression> = None;

        for field in tc.fields().iter() {
            let Some((key, expr)) = named_field(field, source) else {
                continue;
            };
            if key == "disable" {
                let range = node_range(expr);
                let val = parse_value(expr, source);
                let disable_bool = match &val {
                    LuaValue::Boolean { value } => *value,
                    _ => false,
                };
                let enabled_val = !disable_bool;
                let id = stable_id(&format!("{prefix}:enabled"));
                let field_obj = Field {
                    id: id.clone(),
                    file: file.to_string_lossy().into_owned(),
                    revision: revision.to_owned(),
                    line: Some(range.start_line),
                    value: Some(LuaValue::Boolean { value: enabled_val }),
                };
                let target_obj = Target {
                    file: file.to_path_buf(),
                    revision: revision.to_owned(),
                    edit: EditTarget::ReplaceInverted(range.range.clone()),
                    read_only: false,
                    entity: entity.clone(),
                };
                targets.insert(id, target_obj.clone());
                targets.insert(format!("plugin_slot:{}:enabled", name), target_obj);
                disable_field = Some(field_obj);
                continue;
            }

            let slot_name = match key.as_str() {
                "opt" => "lazy",
                "run" => "build",
                "requires" => "dependencies",
                "lock" => "pin",
                "cmd" | "ft" | "event" | "keys" | "branch" | "tag" | "commit" | "config" => {
                    key.as_str()
                }
                _ => continue,
            };
            if slot_name == "config" {
                config_expr = Some(expr);
            }

            let id = stable_id(&format!("{prefix}:{slot_name}"));
            let range = node_range(expr);
            let val = parse_value(expr, source);
            let field_obj = Field {
                id: id.clone(),
                file: file.to_string_lossy().into_owned(),
                revision: revision.to_owned(),
                line: Some(range.start_line),
                value: Some(val),
            };
            let target_obj = Target {
                file: file.to_path_buf(),
                revision: revision.to_owned(),
                edit: EditTarget::Replace(range.range.clone()),
                read_only: slot_name == "config"
                    && matches!(field_obj.value.as_ref(), Some(LuaValue::Unsupported { .. })),
                entity: entity.clone(),
            };
            targets.insert(id, target_obj.clone());
            targets.insert(format!("plugin_slot:{}:{slot_name}", name), target_obj);
            found_fields.insert(slot_name.to_string(), (range.range, field_obj));
        }

        if !found_fields.contains_key("opts") {
            if let Some(cfg_expr) = config_expr {
                if let Some(setup_tc) = find_setup_table_in_expr(cfg_expr) {
                    let id = stable_id(&format!("{prefix}:opts"));
                    let range = node_range(setup_tc);
                    let val = parse_table(setup_tc, source)
                        .unwrap_or_else(|| unsupported(setup_tc, source));
                    let field_obj = Field {
                        id: id.clone(),
                        file: file.to_string_lossy().into_owned(),
                        revision: revision.to_owned(),
                        line: Some(range.start_line),
                        value: Some(val),
                    };
                    let target_obj = Target {
                        file: file.to_path_buf(),
                        revision: revision.to_owned(),
                        edit: EditTarget::Replace(range.range.clone()),
                        read_only: false,
                        entity: entity.clone(),
                    };
                    targets.insert(id, target_obj.clone());
                    targets.insert(format!("plugin_slot:{}:opts", name), target_obj);
                    found_fields.insert("opts".to_string(), (range.range, field_obj));
                }
            }
        }

        let (offset, needs_comma) = match tc.fields().last() {
            Some(pair) => match pair.punctuation() {
                Some(punctuation) => (punctuation.token().end_position().bytes(), false),
                None => (node_range(pair.value()).range.end, true),
            },
            None => (
                tc.braces().tokens().0.token().end_position().bytes(),
                false,
            ),
        };

        for slot in [
            "event",
            "keys",
            "opts",
            "lazy",
            "cmd",
            "ft",
            "dependencies",
            "branch",
            "tag",
            "commit",
            "pin",
            "build",
        ] {
            if !found_fields.contains_key(slot) {
                if let Some(slot_static) = packer_slot_static_name(slot) {
                    let id = stable_id(&format!("{prefix}:{slot}"));
                    let target_obj = Target {
                        file: file.to_path_buf(),
                        revision: revision.to_owned(),
                        edit: EditTarget::Insert {
                            offset,
                            needs_comma,
                            name: slot_static,
                        },
                        read_only: false,
                        entity: entity.clone(),
                    };
                    targets.insert(id, target_obj.clone());
                    targets.insert(format!("plugin_slot:{}:{slot}", name), target_obj);
                }
            }
        }

        let enabled_field = if let Some(f) = disable_field {
            f
        } else {
            let id = stable_id(&format!("{prefix}:enabled"));
            let field_obj = Field {
                id: id.clone(),
                file: file.to_string_lossy().into_owned(),
                revision: revision.to_owned(),
                line: None,
                value: Some(LuaValue::Boolean { value: true }),
            };
            let target_obj = Target {
                file: file.to_path_buf(),
                revision: revision.to_owned(),
                edit: EditTarget::InsertInverted {
                    offset,
                    needs_comma,
                    name: "disable",
                },
                read_only: false,
                entity: entity.clone(),
            };
            targets.insert(id, target_obj.clone());
            targets.insert(format!("plugin_slot:{}:enabled", name), target_obj);
            field_obj
        };

        let event_field = if let Some((_, f)) = found_fields.remove("event") {
            f
        } else {
            Field::placeholder(
                stable_id(&format!("{prefix}:event")),
                file.to_string_lossy(),
                revision,
            )
        };

        let keys_field = if let Some((_, f)) = found_fields.remove("keys") {
            f
        } else {
            Field::placeholder(
                stable_id(&format!("{prefix}:keys")),
                file.to_string_lossy(),
                revision,
            )
        };

        let opts_field = if let Some((_, f)) = found_fields.remove("opts") {
            f
        } else {
            Field::placeholder(
                stable_id(&format!("{prefix}:opts")),
                file.to_string_lossy(),
                revision,
            )
        };

        let mut plugin = Plugin::new_packer(
            name,
            plugin_source,
            enabled_field,
            event_field,
            keys_field,
            opts_field,
        );

        if let Some((_, f)) = found_fields.remove("lazy") {
            plugin = plugin.with_lazy(f);
        }
        if let Some((_, f)) = found_fields.remove("cmd") {
            plugin = plugin.with_cmd(f);
        }
        if let Some((_, f)) = found_fields.remove("ft") {
            plugin = plugin.with_ft(f);
        }
        if let Some((_, f)) = found_fields.remove("dependencies") {
            plugin = plugin.with_dependencies(f);
        }
        if let Some((_, f)) = found_fields.remove("branch") {
            plugin = plugin.with_branch(f);
        }
        if let Some((_, f)) = found_fields.remove("tag") {
            plugin = plugin.with_tag(f);
        }
        if let Some((_, f)) = found_fields.remove("commit") {
            plugin = plugin.with_commit(f);
        }
        if let Some((_, f)) = found_fields.remove("pin") {
            plugin = plugin.with_pin(f);
        }
        if let Some((_, f)) = found_fields.remove("build") {
            plugin = plugin.with_build(f);
        }
        if let Some((_, f)) = found_fields.remove("config") {
            plugin = plugin.with_config(f);
        }

        plugins.push(plugin);
    }

    for inner_tc in inner_specs {
        extract_packer_table(
            inner_tc,
            file,
            relative,
            revision,
            source,
            plugins,
            targets,
            occurrences,
        );
    }
}

fn is_vim_cmd(call: &FunctionCall) -> bool {
    let Prefix::Name(prefix) = call.prefix() else {
        return false;
    };
    if prefix.token().to_string() != "vim" {
        return false;
    }
    let mut suffixes = call.suffixes();
    match suffixes.next() {
        Some(Suffix::Index(Index::Dot { name, .. })) => name.token().to_string() == "cmd",
        _ => false,
    }
}

fn extract_cmd_string(call: &FunctionCall) -> Option<(String, usize, u64)> {
    for suffix in call.suffixes() {
        let Suffix::Call(full_moon::ast::Call::AnonymousCall(args)) = suffix else {
            continue;
        };
        match args {
            FunctionArgs::String(tok) => {
                return extract_cmd_from_tok(tok);
            }
            FunctionArgs::Parentheses { arguments, .. } => {
                if let Some(Expression::String(tok)) = arguments.iter().next() {
                    return extract_cmd_from_tok(tok);
                }
            }
            _ => {}
        }
    }
    None
}

fn extract_cmd_from_tok(tok: &TokenReference) -> Option<(String, usize, u64)> {
    let TokenType::StringLiteral {
        literal,
        quote_type,
        ..
    } = tok.token().token_type()
    else {
        return None;
    };
    let start_pos = tok.token().start_position();
    let mut base_offset = start_pos.bytes();
    let mut base_line = start_pos.line() as u64;

    if *quote_type == StringLiteralQuoteType::Brackets {
        let open_bracket_len = literal.find('[').map_or(2, |first| {
            let rest = &literal[first + 1..];
            let second = rest.find('[').unwrap_or(0);
            first + 1 + second + 1
        });
        base_offset += open_bracket_len;
        let mut value = &literal[open_bracket_len..];
        if let Some(rest) = value.strip_prefix("\r\n") {
            base_offset += 2;
            base_line += 1;
            value = rest;
        } else if let Some(rest) = value.strip_prefix('\n') {
            base_offset += 1;
            base_line += 1;
            value = rest;
        }
        let close_pos = value.rfind(']').and_then(|idx| value[..idx].rfind(']'));
        let final_val = if let Some(pos) = close_pos {
            &value[..pos]
        } else {
            value
        };
        return Some((final_val.to_owned(), base_offset, base_line));
    }

    let decoded = decode_quoted_string(literal)?;
    base_offset += 1;
    Some((decoded, base_offset, base_line))
}

fn extract_plug_lua_call(
    call: &FunctionCall,
    file: &Path,
    relative: &str,
    revision: &str,
    source: &str,
    plugins: &mut Vec<Plugin>,
    targets: &mut HashMap<String, Target>,
    delete_targets: &mut HashMap<String, DeleteTarget>,
    occurrences: &mut HashMap<String, usize>,
) {
    let is_plug = match call.prefix() {
        Prefix::Name(n) if n.token().to_string() == "Plug" => true,
        Prefix::Name(n) if n.token().to_string() == "vim" => {
            let suffixes: Vec<_> = call.suffixes().collect();
            if suffixes.len() >= 2 {
                let is_fn = match suffixes[0] {
                    Suffix::Index(Index::Dot { name, .. }) => name.token().to_string() == "fn",
                    _ => false,
                };
                let is_plug_sharp = match suffixes[1] {
                    Suffix::Index(Index::Brackets { expression, .. }) => {
                        if let Expression::String(tok) = expression {
                            parse_string(tok).as_deref() == Some("plug#")
                        } else {
                            false
                        }
                    }
                    _ => false,
                };
                is_fn && is_plug_sharp
            } else {
                false
            }
        }
        _ => false,
    };

    if !is_plug {
        return;
    }

    let Some(call_suffix) = call.suffixes().find_map(|s| match s {
        Suffix::Call(full_moon::ast::Call::AnonymousCall(args)) => Some(args),
        _ => None,
    }) else {
        return;
    };

    let mut plugin_source = None;
    let mut options_table = None;

    match call_suffix {
        FunctionArgs::String(tok) => {
            plugin_source = parse_string(tok);
        }
        FunctionArgs::Parentheses { arguments, .. } => {
            let mut iter = arguments.iter();
            if let Some(arg0) = iter.next() {
                if let Expression::String(tok) = arg0 {
                    plugin_source = parse_string(tok);
                } else if let LuaValue::String { value } = parse_value(arg0, source) {
                    plugin_source = Some(value);
                }
            }
            if let Some(arg1) = iter.next() {
                if let Expression::TableConstructor(tc) = arg1 {
                    options_table = Some(tc);
                }
            }
        }
        _ => {}
    }

    let Some(plugin_source) = plugin_source else {
        return;
    };

    let mut custom_name = None;
    if let Some(tc) = options_table {
        for field in tc.fields().iter() {
            if let Some((k, expr)) = named_field(field, source) {
                if k == "as" {
                    if let LuaValue::String { value: n } = parse_value(expr, source) {
                        custom_name = Some(n);
                    }
                }
            }
        }
    }

    let name = custom_name.unwrap_or_else(|| extract_plugin_name(&plugin_source));
    let occurrence = occurrences
        .entry(plugin_source.clone())
        .and_modify(|v| *v += 1)
        .or_insert(0);
    let prefix = format!("plugin:{relative}:{plugin_source}:{occurrence}");
    let entity = RuntimeEntity::Plugin {
        name: name.clone(),
        manager: PluginManagerKind::Plug,
    };

    let enabled = Field {
        id: stable_id(&format!("{prefix}:enabled")),
        file: file.to_string_lossy().into_owned(),
        revision: revision.to_owned(),
        line: Some(node_range(call).start_line),
        value: Some(LuaValue::Boolean { value: true }),
    };

    let event = Field::placeholder(
        stable_id(&format!("{prefix}:event")),
        file.to_string_lossy(),
        revision,
    );
    let keys = Field::placeholder(
        stable_id(&format!("{prefix}:keys")),
        file.to_string_lossy(),
        revision,
    );
    let opts = Field::placeholder(
        stable_id(&format!("{prefix}:opts")),
        file.to_string_lossy(),
        revision,
    );

    let mut plugin = Plugin::new_plug(name, plugin_source, enabled, event, keys, opts);

    if let Some(tc) = options_table {
        for field in tc.fields().iter() {
            let Some((k, expr)) = named_field(field, source) else {
                continue;
            };
            let range = node_range(expr);
            let val = parse_value(expr, source);
            let field_id = stable_id(&format!("{prefix}:{k}"));
            let field_obj = Field {
                id: field_id.clone(),
                file: file.to_string_lossy().into_owned(),
                revision: revision.to_owned(),
                line: Some(range.start_line),
                value: Some(val.clone()),
            };
            targets.insert(
                field_id,
                Target {
                    file: file.to_path_buf(),
                    revision: revision.to_owned(),
                    edit: EditTarget::Replace(range.range),
                    read_only: matches!(val, LuaValue::Unsupported { .. }),
                    entity: entity.clone(),
                },
            );

            match k.as_str() {
                "branch" => plugin = plugin.with_branch(field_obj),
                "tag" => plugin = plugin.with_tag(field_obj),
                "commit" => plugin = plugin.with_commit(field_obj),
                "do" => plugin = plugin.with_build(field_obj),
                "for" => {
                    plugin = plugin.with_ft(field_obj);
                    let lazy_id = stable_id(&format!("{prefix}:lazy"));
                    plugin = plugin.with_lazy(Field {
                        id: lazy_id,
                        file: file.to_string_lossy().into_owned(),
                        revision: revision.to_owned(),
                        line: Some(range.start_line),
                        value: Some(LuaValue::Boolean { value: true }),
                    });
                }
                "on" => {
                    let is_plug_key = match &val {
                        LuaValue::String { value: s } => s.starts_with("<Plug>"),
                        LuaValue::Array { values } => values.iter().any(|v| match v {
                            LuaValue::String { value: s } => s.starts_with("<Plug>"),
                            _ => false,
                        }),
                        _ => false,
                    };
                    if is_plug_key {
                        plugin.keys = field_obj;
                    } else {
                        plugin = plugin.with_cmd(field_obj);
                    }
                    let lazy_id = stable_id(&format!("{prefix}:lazy"));
                    plugin = plugin.with_lazy(Field {
                        id: lazy_id,
                        file: file.to_string_lossy().into_owned(),
                        revision: revision.to_owned(),
                        line: Some(range.start_line),
                        value: Some(LuaValue::Boolean { value: true }),
                    });
                }
                "frozen" => {
                    let is_frozen = match &val {
                        LuaValue::Number { value } => value.as_i64() == Some(1),
                        LuaValue::Boolean { value } => *value,
                        LuaValue::String { value } => value == "1",
                        _ => false,
                    };
                    let pin_id = stable_id(&format!("{prefix}:pin"));
                    plugin = plugin.with_pin(Field {
                        id: pin_id,
                        file: file.to_string_lossy().into_owned(),
                        revision: revision.to_owned(),
                        line: Some(range.start_line),
                        value: Some(LuaValue::Boolean { value: is_frozen }),
                    });
                }
                _ => {}
            }
        }
    }

    register_plugin_delete(
        &plugin,
        delete_targets,
        file,
        revision,
        DeleteAction::RemoveLineOrSpan(node_range(call).range),
    );
    plugins.push(plugin);
}

fn scan_vimscript_file(
    _root: &Path,
    file: &Path,
    source: &str,
    snapshot: &mut Snapshot,
    targets: &mut HashMap<String, Target>,
    delete_targets: &mut HashMap<String, DeleteTarget>,
) {
    let revision = revision(source.as_bytes());
    let relative = file.to_string_lossy().replace('\\', "/");
    let mut occurrences = HashMap::new();
    let mut plugins = Vec::new();

    scan_vimscript_text(
        source,
        0,
        1,
        file,
        &relative,
        &revision,
        &mut plugins,
        targets,
        delete_targets,
        &mut occurrences,
    );

    snapshot.plugins.extend(plugins);
}

fn scan_vimscript_text(
    content: &str,
    base_offset: usize,
    base_line: u64,
    file: &Path,
    relative: &str,
    revision: &str,
    plugins: &mut Vec<Plugin>,
    targets: &mut HashMap<String, Target>,
    delete_targets: &mut HashMap<String, DeleteTarget>,
    occurrences: &mut HashMap<String, usize>,
) {
    let mut current_offset = base_offset;
    for (line_idx, line) in content.split_inclusive('\n').enumerate() {
        let line_num = base_line + line_idx as u64;
        let line_start_offset = current_offset;
        current_offset += line.len();

        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('"') {
            continue;
        }

        let commands = split_vim_commands(line);
        for (cmd_offset, cmd) in commands {
            let cmd_trimmed = cmd.trim();
            let mut plug_cmd = cmd_trimmed;
            if let Some(rest) = plug_cmd.strip_prefix("call ") {
                plug_cmd = rest.trim_start();
            }
            if !plug_cmd.starts_with("Plug ")
                && !plug_cmd.starts_with("Plug'")
                && !plug_cmd.starts_with("Plug\"")
            {
                continue;
            }

            let after_plug = plug_cmd.strip_prefix("Plug").unwrap().trim_start();
            let Some((repo, after_repo, _repo_range)) = extract_vim_string(after_plug) else {
                continue;
            };

            let plugin_source = repo;
            let mut custom_name = None;
            let occurrence = occurrences
                .entry(plugin_source.clone())
                .and_modify(|v| *v += 1)
                .or_insert(0);
            let prefix = format!("plugin:{relative}:{plugin_source}:{occurrence}");

            let mut parsed_options = Vec::new();
            let trimmed_after_repo = after_repo.trim_start();
            if let Some(after_comma) = trimmed_after_repo.strip_prefix(',') {
                let trimmed_dict = after_comma.trim_start();
                if trimmed_dict.starts_with('{') {
                    let dict_rel_in_cmd = cmd_offset
                        + (cmd.len() - cmd.trim_start().len())
                        + (cmd_trimmed.len() - trimmed_dict.len());
                    let dict_abs_offset = line_start_offset + dict_rel_in_cmd;
                    parsed_options = parse_vim_dict(trimmed_dict, dict_abs_offset);
                }
            }

            for opt in &parsed_options {
                if opt.key == "as" {
                    if let LuaValue::String { value: ref n } = opt.value {
                        custom_name = Some(n.clone());
                    }
                }
            }

            let name = custom_name.unwrap_or_else(|| extract_plugin_name(&plugin_source));
            let entity = RuntimeEntity::Plugin {
                name: name.clone(),
                manager: PluginManagerKind::Plug,
            };

            let enabled = Field {
                id: stable_id(&format!("{prefix}:enabled")),
                file: file.to_string_lossy().into_owned(),
                revision: revision.to_owned(),
                line: Some(line_num),
                value: Some(LuaValue::Boolean { value: true }),
            };

            let event = Field::placeholder(
                stable_id(&format!("{prefix}:event")),
                file.to_string_lossy(),
                revision,
            );
            let keys = Field::placeholder(
                stable_id(&format!("{prefix}:keys")),
                file.to_string_lossy(),
                revision,
            );
            let opts = Field::placeholder(
                stable_id(&format!("{prefix}:opts")),
                file.to_string_lossy(),
                revision,
            );

            let mut plugin = Plugin::new_plug(name, plugin_source, enabled, event, keys, opts);

            for opt in parsed_options {
                let field_id = stable_id(&format!("{prefix}:{}", opt.key));
                let field_obj = Field {
                    id: field_id.clone(),
                    file: file.to_string_lossy().into_owned(),
                    revision: revision.to_owned(),
                    line: Some(line_num),
                    value: Some(opt.value.clone()),
                };
                targets.insert(
                    field_id,
                    Target {
                        file: file.to_path_buf(),
                        revision: revision.to_owned(),
                        edit: EditTarget::VimscriptReplace(opt.val_range.clone()),
                        read_only: matches!(opt.value, LuaValue::Unsupported { .. }),
                        entity: entity.clone(),
                    },
                );

                match opt.key.as_str() {
                    "branch" => plugin = plugin.with_branch(field_obj),
                    "tag" => plugin = plugin.with_tag(field_obj),
                    "commit" => plugin = plugin.with_commit(field_obj),
                    "do" => plugin = plugin.with_build(field_obj),
                    "for" => {
                        plugin = plugin.with_ft(field_obj);
                        let lazy_id = stable_id(&format!("{prefix}:lazy"));
                        plugin = plugin.with_lazy(Field {
                            id: lazy_id,
                            file: file.to_string_lossy().into_owned(),
                            revision: revision.to_owned(),
                            line: Some(line_num),
                            value: Some(LuaValue::Boolean { value: true }),
                        });
                    }
                    "on" => {
                        let is_plug_key = match &opt.value {
                            LuaValue::String { value: s } => s.starts_with("<Plug>"),
                            LuaValue::Array { values } => values.iter().any(|v| match v {
                                LuaValue::String { value: s } => s.starts_with("<Plug>"),
                                _ => false,
                            }),
                            _ => false,
                        };
                        if is_plug_key {
                            plugin.keys = field_obj;
                        } else {
                            plugin = plugin.with_cmd(field_obj);
                        }
                        let lazy_id = stable_id(&format!("{prefix}:lazy"));
                        plugin = plugin.with_lazy(Field {
                            id: lazy_id,
                            file: file.to_string_lossy().into_owned(),
                            revision: revision.to_owned(),
                            line: Some(line_num),
                            value: Some(LuaValue::Boolean { value: true }),
                        });
                    }
                    "frozen" => {
                        let is_frozen = match &opt.value {
                            LuaValue::Number { value } => value.as_i64() == Some(1),
                            LuaValue::Boolean { value } => *value,
                            LuaValue::String { value } => value == "1",
                            _ => false,
                        };
                        let pin_id = stable_id(&format!("{prefix}:pin"));
                        plugin = plugin.with_pin(Field {
                            id: pin_id,
                            file: file.to_string_lossy().into_owned(),
                            revision: revision.to_owned(),
                            line: Some(line_num),
                            value: Some(LuaValue::Boolean { value: is_frozen }),
                        });
                    }
                    _ => {}
                }
            }

            register_plugin_delete(
                &plugin,
                delete_targets,
                file,
                revision,
                DeleteAction::RemoveLineOrSpan(line_start_offset..current_offset),
            );
            plugins.push(plugin);
        }
    }
}

fn split_vim_commands(line: &str) -> Vec<(usize, &str)> {
    let mut result = Vec::new();
    let mut in_quote = None;
    let mut start = 0;
    let bytes = line.as_bytes();

    for (i, &b) in bytes.iter().enumerate() {
        if let Some(q) = in_quote {
            if b == q {
                in_quote = None;
            }
        } else if b == b'\'' || b == b'"' {
            in_quote = Some(b);
        } else if b == b'|' {
            result.push((start, &line[start..i]));
            start = i + 1;
        }
    }
    result.push((start, &line[start..]));
    result
}

fn extract_vim_string(s: &str) -> Option<(String, &str, Range<usize>)> {
    let trimmed = s.trim_start();
    let lead_ws = s.len() - trimmed.len();
    let quote = trimmed.chars().next()?;
    if quote != '\'' && quote != '"' {
        return None;
    }
    let after_quote = &trimmed[1..];
    let end_idx = after_quote.find(quote)?;
    let content = &after_quote[..end_idx];
    let rest = &after_quote[end_idx + 1..];
    let range = lead_ws..(lead_ws + 1 + end_idx + 1);
    Some((content.to_string(), rest, range))
}

struct VimDictEntry {
    key: String,
    value: LuaValue,
    val_range: Range<usize>,
}

fn parse_vim_dict(text: &str, base_offset: usize) -> Vec<VimDictEntry> {
    let mut entries = Vec::new();
    let trimmed = text.trim();
    if !trimmed.starts_with('{') {
        return entries;
    }
    let inner = match trimmed.strip_suffix('}') {
        Some(s) => &s[1..],
        None => {
            if let Some(pos) = trimmed.rfind('}') {
                &trimmed[1..pos]
            } else {
                &trimmed[1..]
            }
        }
    };
    let inner_offset = base_offset + (inner.as_ptr() as usize - text.as_ptr() as usize);

    let item_spans = split_vim_dict_items(inner);
    for (item_rel_offset, item_str) in item_spans {
        let item_abs_offset = inner_offset + item_rel_offset;
        let Some(colon_pos) = find_top_level_colon(item_str) else {
            continue;
        };
        let key_str = item_str[..colon_pos].trim();
        let key_name = if (key_str.starts_with('\'') && key_str.ends_with('\''))
            || (key_str.starts_with('"') && key_str.ends_with('"'))
        {
            if key_str.len() >= 2 {
                key_str[1..key_str.len() - 1].to_string()
            } else {
                key_str.to_string()
            }
        } else {
            key_str.to_string()
        };

        let val_part = &item_str[colon_pos + 1..];
        let val_trimmed = val_part.trim();
        let val_lead = val_part.len() - val_part.trim_start().len();
        let val_rel_start = colon_pos + 1 + val_lead;
        let val_len = val_trimmed.len();
        let val_abs_start = item_abs_offset + val_rel_start;
        let val_range = val_abs_start..(val_abs_start + val_len);

        let lua_val = parse_vim_value(val_trimmed);
        entries.push(VimDictEntry {
            key: key_name,
            value: lua_val,
            val_range,
        });
    }
    entries
}

fn parse_vim_value(s: &str) -> LuaValue {
    let s = s.trim();
    if (s.starts_with('\'') && s.ends_with('\'')) || (s.starts_with('"') && s.ends_with('"')) {
        if s.len() >= 2 {
            LuaValue::String {
                value: s[1..s.len() - 1].to_string(),
            }
        } else {
            LuaValue::String {
                value: String::new(),
            }
        }
    } else if s == "v:true" || s == "true" {
        LuaValue::Boolean { value: true }
    } else if s == "v:false" || s == "false" {
        LuaValue::Boolean { value: false }
    } else if let Ok(n) = s.parse::<i64>() {
        LuaValue::Number {
            value: serde_json::Number::from(n),
        }
    } else if s.starts_with('[') && s.ends_with(']') {
        let inner = &s[1..s.len() - 1];
        let items = split_vim_dict_items(inner);
        let values: Vec<LuaValue> = items
            .into_iter()
            .map(|(_, item)| parse_vim_value(item))
            .collect();
        LuaValue::Array { values }
    } else {
        LuaValue::Unsupported {
            source: s.to_string(),
        }
    }
}

fn split_vim_dict_items(text: &str) -> Vec<(usize, &str)> {
    let mut items = Vec::new();
    let mut in_quote = None;
    let mut depth_brace = 0;
    let mut depth_bracket = 0;
    let mut start = 0;
    let bytes = text.as_bytes();

    for (i, &b) in bytes.iter().enumerate() {
        if let Some(q) = in_quote {
            if b == q {
                in_quote = None;
            }
        } else if b == b'\'' || b == b'"' {
            in_quote = Some(b);
        } else if b == b'{' {
            depth_brace += 1;
        } else if b == b'}' {
            depth_brace = (depth_brace - 1).max(0);
        } else if b == b'[' {
            depth_bracket += 1;
        } else if b == b']' {
            depth_bracket = (depth_bracket - 1).max(0);
        } else if b == b',' && depth_brace == 0 && depth_bracket == 0 {
            let item = &text[start..i];
            if !item.trim().is_empty() {
                items.push((start, item));
            }
            start = i + 1;
        }
    }
    if start < text.len() {
        let item = &text[start..];
        if !item.trim().is_empty() {
            items.push((start, item));
        }
    }
    items
}

fn find_top_level_colon(text: &str) -> Option<usize> {
    let mut in_quote = None;
    let mut depth_brace = 0;
    let mut depth_bracket = 0;
    for (i, &b) in text.as_bytes().iter().enumerate() {
        if let Some(q) = in_quote {
            if b == q {
                in_quote = None;
            }
        } else if b == b'\'' || b == b'"' {
            in_quote = Some(b);
        } else if b == b'{' {
            depth_brace += 1;
        } else if b == b'}' {
            depth_brace = (depth_brace - 1).max(0);
        } else if b == b'[' {
            depth_bracket += 1;
        } else if b == b']' {
            depth_bracket = (depth_bracket - 1).max(0);
        } else if b == b':' && depth_brace == 0 && depth_bracket == 0 {
            return Some(i);
        }
    }
    None
}

fn named_field<'a>(field: &'a AstField, source: &str) -> Option<(String, &'a Expression)> {
    match field {
        AstField::NameKey { key, value, .. } => Some((key.token().to_string(), value)),
        AstField::ExpressionKey { key, value, .. } => match parse_value(key, source) {
            LuaValue::String { value: key } => Some((key, value)),
            _ => None,
        },
        _ => None,
    }
}

fn setting_path(var: &Var) -> Option<(SettingNamespace, String)> {
    let Var::Expression(expression) = var else {
        return None;
    };
    let Prefix::Name(prefix) = expression.prefix() else {
        return None;
    };
    let prefix_str = prefix.token().to_string();
    let mut parts = Vec::new();
    for suffix in expression.suffixes() {
        match suffix {
            Suffix::Index(Index::Dot { name, .. }) => {
                parts.push(name.token().to_string());
            }
            Suffix::Index(Index::Brackets { expression, .. }) => {
                if let Expression::String(tok) = expression {
                    if let Some(s) = parse_string(tok) {
                        parts.push(s);
                    } else {
                        return None;
                    }
                } else {
                    return None;
                }
            }
            _ => return None,
        }
    }
    if matches!(prefix_str.as_str(), "opt" | "o" | "wo" | "bo") && parts.len() == 1 {
        return Some((SettingNamespace::Opt, parts.remove(0)));
    }
    if prefix_str != "vim" || parts.len() != 2 {
        return None;
    }
    let namespace = match parts[0].as_str() {
        "opt" | "o" | "wo" | "bo" => SettingNamespace::Opt,
        "g" => SettingNamespace::G,
        "env" => SettingNamespace::Env,
        _ => return None,
    };
    Some((namespace, parts.remove(1)))
}

fn is_keymap_set(call: &FunctionCall) -> bool {
    let Prefix::Name(prefix) = call.prefix() else {
        return false;
    };
    let prefix_str = prefix.token().to_string();
    let mut names = Vec::new();
    for suffix in call.suffixes() {
        match suffix {
            Suffix::Index(Index::Dot { name, .. }) => names.push(name.token().to_string()),
            Suffix::Call(_) => break,
            _ => return false,
        }
    }
    (prefix_str == "vim" && (names == ["keymap", "set"] || names == ["api", "nvim_set_keymap"]))
        || (prefix_str == "keymap" && names == ["set"])
}

struct SourceRange {
    range: Range<usize>,
    start_line: u64,
}

fn node_range(node: &impl Node) -> SourceRange {
    if let Some((start, end)) = node.range() {
        return SourceRange {
            range: start.bytes()..end.bytes(),
            start_line: start.line() as u64,
        };
    }
    let mut tokens = node.tokens();
    let first = tokens.next().expect("AST node must have a token");
    let last = tokens.last().unwrap_or(first);
    SourceRange {
        range: first.token().start_position().bytes()..last.token().end_position().bytes(),
        start_line: first.token().start_position().line() as u64,
    }
}

fn parse_value(expression: &Expression, source: &str) -> LuaValue {
    match expression {
        Expression::Symbol(token) if token.token().to_string() == "true" => {
            LuaValue::Boolean { value: true }
        }
        Expression::Symbol(token) if token.token().to_string() == "false" => {
            LuaValue::Boolean { value: false }
        }
        Expression::Number(token) => parse_number(&token.token().to_string())
            .map(|value| LuaValue::Number { value })
            .unwrap_or_else(|| unsupported(expression, source)),
        whole @ Expression::UnaryOperator {
            unop: UnOp::Minus(_),
            expression,
        } => {
            if let Expression::Number(token) = expression.as_ref() {
                parse_number(&format!("-{}", token.token()))
                    .map(|value| LuaValue::Number { value })
                    .unwrap_or_else(|| unsupported(whole, source))
            } else {
                unsupported(whole, source)
            }
        }
        Expression::String(token) => parse_string(token)
            .map(|value| LuaValue::String { value })
            .unwrap_or_else(|| unsupported(expression, source)),
        Expression::TableConstructor(table) => {
            parse_table(table, source).unwrap_or_else(|| unsupported(expression, source))
        }
        _ => unsupported(expression, source),
    }
}

fn unsupported(expression: &impl Node, source: &str) -> LuaValue {
    let range = node_range(expression).range;
    LuaValue::Unsupported {
        source: source[range].to_owned(),
    }
}

fn parse_number(text: &str) -> Option<serde_json::Number> {
    let (negative, text) = text
        .strip_prefix('-')
        .map_or((false, text), |text| (true, text));
    let parsed = if let Some(hex) = text.strip_prefix("0x").or_else(|| text.strip_prefix("0X")) {
        if hex.contains(['.', 'p', 'P']) {
            return None;
        }
        let value = i128::from_str_radix(hex, 16).ok()?;
        let value = if negative { -value } else { value };
        if value < i64::MIN as i128 || value > u64::MAX as i128 {
            return None;
        }
        if value < 0 {
            serde_json::Number::from(value as i64)
        } else {
            serde_json::Number::from(value as u64)
        }
    } else {
        serde_json::Number::from_str(text).ok()?
    };
    Some(parsed)
}

fn parse_string(token: &TokenReference) -> Option<String> {
    let TokenType::StringLiteral {
        literal,
        quote_type,
        ..
    } = token.token().token_type()
    else {
        return None;
    };
    if *quote_type == StringLiteralQuoteType::Brackets {
        let mut value = literal.as_str();
        if let Some(rest) = value.strip_prefix("\r\n") {
            value = rest;
        } else if let Some(rest) = value.strip_prefix('\n') {
            value = rest;
        }
        return Some(value.to_owned());
    }
    decode_quoted_string(literal)
}

fn decode_quoted_string(literal: &str) -> Option<String> {
    let mut chars = literal.chars();
    let mut output = String::new();
    while let Some(character) = chars.next() {
        if character != '\\' {
            output.push(character);
            continue;
        }
        let escape = chars.next()?;
        match escape {
            'a' => output.push('\u{7}'),
            'b' => output.push('\u{8}'),
            'f' => output.push('\u{c}'),
            'n' => output.push('\n'),
            'r' => output.push('\r'),
            't' => output.push('\t'),
            'v' => output.push('\u{b}'),
            '\\' => output.push('\\'),
            '"' => output.push('"'),
            '\'' => output.push('\''),
            '\n' => output.push('\n'),
            '\r' => {
                if chars.clone().next() == Some('\n') {
                    chars.next();
                }
                output.push('\n');
            }
            'z' => {
                while chars.clone().next().is_some_and(char::is_whitespace) {
                    chars.next();
                }
            }
            'x' => {
                let first = chars.next()?;
                let second = chars.next()?;
                let value = u8::from_str_radix(&format!("{first}{second}"), 16).ok()?;
                output.push(value as char);
            }
            'u' => {
                if chars.next()? != '{' {
                    return None;
                }
                let mut digits = String::new();
                loop {
                    let character = chars.next()?;
                    if character == '}' {
                        break;
                    }
                    digits.push(character);
                }
                let value = u32::from_str_radix(&digits, 16).ok()?;
                output.push(char::from_u32(value)?);
            }
            digit if digit.is_ascii_digit() => {
                let mut digits = digit.to_string();
                for _ in 0..2 {
                    if chars
                        .clone()
                        .next()
                        .is_some_and(|value| value.is_ascii_digit())
                    {
                        digits.push(chars.next().unwrap());
                    } else {
                        break;
                    }
                }
                let value = digits.parse::<u8>().ok()?;
                output.push(value as char);
            }
            _ => return None,
        }
    }
    Some(output)
}

fn parse_table(table: &TableConstructor, source: &str) -> Option<LuaValue> {
    if table.fields().is_empty() {
        return Some(LuaValue::Table {
            entries: Vec::new(),
        });
    }
    let array = table
        .fields()
        .iter()
        .all(|field| matches!(field, AstField::NoKey(_)));
    if array {
        return Some(LuaValue::Array {
            values: table
                .fields()
                .iter()
                .map(|field| match field {
                    AstField::NoKey(expression) => parse_value(expression, source),
                    _ => unreachable!(),
                })
                .collect(),
        });
    }

    let mut entries = Vec::new();
    let mut array_index = 1usize;
    for field in table.fields().iter() {
        let (key, value) = match field {
            AstField::NoKey(expression) => {
                let key = array_index.to_string();
                array_index += 1;
                (key, parse_value(expression, source))
            }
            AstField::NameKey { key, value, .. } => {
                (key.token().to_string(), parse_value(value, source))
            }
            AstField::ExpressionKey { key, value, .. } => {
                let key = match parse_value(key, source) {
                    LuaValue::String { value } => value,
                    LuaValue::Number { value } => value.to_string(),
                    LuaValue::Boolean { value } => value.to_string(),
                    _ => return None,
                };
                (key, parse_value(value, source))
            }
            _ => return None,
        };
        entries.push(TableEntry { key, value });
    }
    Some(LuaValue::Table { entries })
}

pub fn append_option(root: &Path, name: &str, value: &LuaValue) -> Result<ScanResult, ApiError> {
    if !is_identifier(name) {
        return Err(ApiError::BadRequest(
            "option name is not a valid Lua identifier".to_owned(),
        ));
    }
    if !matches!(
        value,
        LuaValue::Boolean { .. } | LuaValue::Number { .. } | LuaValue::String { .. }
    ) {
        return Err(ApiError::BadRequest(
            "native options require a boolean, number, or string value".to_owned(),
        ));
    }
    fs::create_dir_all(root).map_err(|error| {
        ApiError::Internal(format!(
            "cannot create config root {}: {error}",
            root.display()
        ))
    })?;
    let canonical_root = root.canonicalize().map_err(|error| {
        ApiError::Internal(format!(
            "cannot resolve config root {}: {error}",
            root.display()
        ))
    })?;
    let options_file = canonical_root
        .join("lua")
        .join("config")
        .join("options.lua");
    let init_file = canonical_root.join("init.lua");
    let requested_file = if options_file.exists() {
        options_file
    } else {
        init_file
    };
    if requested_file.exists() && !requested_file.is_file() {
        return Err(ApiError::BadRequest(format!(
            "option target is not a file: {}",
            requested_file.display()
        )));
    }
    let target = if requested_file.exists() {
        let canonical = requested_file.canonicalize().map_err(|error| {
            ApiError::Internal(format!(
                "cannot resolve option target {}: {error}",
                requested_file.display()
            ))
        })?;
        if !canonical.starts_with(&canonical_root) {
            return Err(ApiError::BadRequest(
                "refusing to append an option outside the config root".to_owned(),
            ));
        }
        canonical
    } else {
        requested_file
    };
    let mut source = match fs::read(&target) {
        Ok(source) => source,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Vec::new(),
        Err(error) => {
            return Err(ApiError::Internal(format!(
                "cannot read option target {}: {error}",
                target.display()
            )));
        }
    };
    let newline = if source.windows(2).any(|bytes| bytes == b"\r\n") {
        b"\r\n".as_slice()
    } else {
        b"\n".as_slice()
    };
    if !source.is_empty() && !source.ends_with(b"\n") {
        source.extend_from_slice(newline);
    }
    source.extend_from_slice(format!("vim.opt.{name} = {}", serialize_value(value)?).as_bytes());
    source.extend_from_slice(newline);
    let updated_text = std::str::from_utf8(&source).map_err(|_| {
        ApiError::BadRequest(format!("option target is not UTF-8: {}", target.display()))
    })?;
    full_moon::parse(updated_text).map_err(|errors| {
        ApiError::Internal(format!(
            "refusing to save invalid appended Lua: {}",
            errors
                .iter()
                .map(ToString::to_string)
                .collect::<Vec<_>>()
                .join("; ")
        ))
    })?;
    atomic_write(&target, source.as_ref())?;
    let scan_result = scan(&canonical_root);
    let _ = sync_state_file(&canonical_root, &scan_result.snapshot);
    Ok(scan_result)
}

pub fn append_keymap(
    root: &Path,
    mode: &LuaValue,
    lhs: &LuaValue,
    rhs: &LuaValue,
    opts: &LuaValue,
) -> Result<(ScanResult, String), ApiError> {
    match mode {
        LuaValue::String { value } if !value.trim().is_empty() => {}
        LuaValue::Array { values } if !values.is_empty() => {}
        _ => {
            return Err(ApiError::BadRequest(
                "keymap mode must be a non-empty string or array of strings".to_owned(),
            ));
        }
    }
    match lhs {
        LuaValue::String { value } if !value.trim().is_empty() => {}
        _ => {
            return Err(ApiError::BadRequest(
                "keymap lhs must be a non-empty string".to_owned(),
            ));
        }
    }
    match rhs {
        LuaValue::String { value } if !value.trim().is_empty() => {}
        _ => {
            return Err(ApiError::BadRequest(
                "keymap rhs must be a non-empty string".to_owned(),
            ));
        }
    }
    if !matches!(opts, LuaValue::Table { .. }) {
        return Err(ApiError::BadRequest(
            "keymap opts must be a table".to_owned(),
        ));
    }

    fs::create_dir_all(root).map_err(|error| {
        ApiError::Internal(format!(
            "cannot create config root {}: {error}",
            root.display()
        ))
    })?;
    let canonical_root = root.canonicalize().map_err(|error| {
        ApiError::Internal(format!(
            "cannot resolve config root {}: {error}",
            root.display()
        ))
    })?;
    let config_keymaps_file = canonical_root
        .join("lua")
        .join("config")
        .join("keymaps.lua");
    let lua_keymaps_file = canonical_root.join("lua").join("keymaps.lua");
    let init_file = canonical_root.join("init.lua");
    let requested_file = if config_keymaps_file.exists() {
        config_keymaps_file
    } else if lua_keymaps_file.exists() {
        lua_keymaps_file
    } else {
        init_file
    };
    if requested_file.exists() && !requested_file.is_file() {
        return Err(ApiError::BadRequest(format!(
            "keymap target is not a file: {}",
            requested_file.display()
        )));
    }
    let target = if requested_file.exists() {
        let canonical = requested_file.canonicalize().map_err(|error| {
            ApiError::Internal(format!(
                "cannot resolve keymap target {}: {error}",
                requested_file.display()
            ))
        })?;
        if !canonical.starts_with(&canonical_root) {
            return Err(ApiError::BadRequest(
                "refusing to append a keymap outside the config root".to_owned(),
            ));
        }
        canonical
    } else {
        requested_file
    };
    let mut source = match fs::read(&target) {
        Ok(source) => source,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Vec::new(),
        Err(error) => {
            return Err(ApiError::Internal(format!(
                "cannot read keymap target {}: {error}",
                target.display()
            )));
        }
    };
    let newline = if source.windows(2).any(|bytes| bytes == b"\r\n") {
        b"\r\n".as_slice()
    } else {
        b"\n".as_slice()
    };
    if !source.is_empty() && !source.ends_with(b"\n") {
        source.extend_from_slice(newline);
    }
    let statement = format!(
        "vim.keymap.set({}, {}, {}, {})",
        serialize_value(mode)?,
        serialize_value(lhs)?,
        serialize_value(rhs)?,
        serialize_value(opts)?,
    );
    source.extend_from_slice(statement.as_bytes());
    source.extend_from_slice(newline);
    let updated_text = std::str::from_utf8(&source).map_err(|_| {
        ApiError::BadRequest(format!("keymap target is not UTF-8: {}", target.display()))
    })?;
    full_moon::parse(updated_text).map_err(|errors| {
        ApiError::Internal(format!(
            "refusing to save invalid appended Lua keymap: {}",
            errors
                .iter()
                .map(ToString::to_string)
                .collect::<Vec<_>>()
                .join("; ")
        ))
    })?;
    atomic_write(&target, source.as_ref())?;
    let scan_result = scan(&canonical_root);
    let _ = sync_state_file(&canonical_root, &scan_result.snapshot);
    let relative = relative_path(&canonical_root, &target);
    let mode_str = match mode {
        LuaValue::String { value } => value.clone(),
        LuaValue::Array { values } => values
            .iter()
            .map(|v| match v {
                LuaValue::String { value } => value.clone(),
                other => format!("{other:?}"),
            })
            .collect::<Vec<_>>()
            .join(","),
        other => format!("{other:?}"),
    };
    let lhs_str = match lhs {
        LuaValue::String { value } => value.clone(),
        other => format!("{other:?}"),
    };
    let target_str = target.to_string_lossy();
    let same_count = scan_result
        .snapshot
        .keymaps
        .iter()
        .filter(|km| {
            km.lhs.file == target_str
                && km.mode.value.as_ref() == Some(mode)
                && km.lhs.value.as_ref() == Some(lhs)
        })
        .count();
    let sem_occ = same_count.saturating_sub(1);
    let prefix = if sem_occ == 0 {
        format!("keymap:{relative}:{mode_str}:{lhs_str}")
    } else {
        format!("keymap:{relative}:{mode_str}:{lhs_str}:{sem_occ}")
    };
    Ok((scan_result, prefix))
}

fn find_packer_insert_offset(source: &str) -> Option<usize> {
    let mut last_match = None;
    let mut offset = 0usize;
    for line in source.split_inclusive('\n') {
        let code_part = match line.find("--") {
            Some(idx) => &line[..idx],
            None => line,
        };
        if let Some(rel_pos) = code_part.rfind("end)") {
            last_match = Some(offset + rel_pos);
        }
        offset += line.len();
    }
    last_match
}

fn strip_inline_vim_comment(line: &str) -> &str {
    let mut in_single = false;
    for (i, b) in line.bytes().enumerate() {
        if b == b'\'' {
            in_single = !in_single;
        } else if b == b'"' && !in_single {
            return &line[..i];
        }
    }
    line
}

fn find_plug_end_offset(source: &str) -> Option<usize> {
    let mut last_match = None;
    let mut offset = 0usize;
    for line in source.split_inclusive('\n') {
        let trimmed = line.trim_start();
        if !trimmed.starts_with('"') {
            let code_part = strip_inline_vim_comment(line);
            if let Some(rel_pos) = code_part.find("call plug#end") {
                last_match = Some(offset + rel_pos);
            }
        }
        offset += line.len();
    }
    last_match
}

pub fn append_plugin(
    root: &Path,
    request: &AddPluginRequest,
) -> Result<(ScanResult, String, PluginManagerKind), ApiError> {
    let raw_source = request.source.trim();
    if raw_source.is_empty() {
        return Err(ApiError::BadRequest(
            "plugin source (e.g. owner/repo) must not be empty".to_owned(),
        ));
    }
    let name = extract_plugin_name(raw_source);
    fs::create_dir_all(root).map_err(|error| {
        ApiError::Internal(format!(
            "cannot create config root {}: {error}",
            root.display()
        ))
    })?;
    let canonical_root = root.canonicalize().map_err(|error| {
        ApiError::Internal(format!(
            "cannot resolve config root {}: {error}",
            root.display()
        ))
    })?;
    let existing_scan = scan(&canonical_root);
    if existing_scan
        .snapshot
        .plugins
        .iter()
        .any(|p| p.source == raw_source || p.name == name)
    {
        return Err(ApiError::Conflict(format!(
            "plugin {} is already present in the config",
            raw_source
        )));
    }

    let manager = request.manager.unwrap_or_else(|| {
        existing_scan
            .snapshot
            .plugins
            .first()
            .map(|p| p.manager)
            .unwrap_or(PluginManagerKind::Lazy)
    });

    match manager {
        PluginManagerKind::Lazy => {
            let plugins_dir = canonical_root.join("lua").join("plugins");
            fs::create_dir_all(&plugins_dir).map_err(|error| {
                ApiError::Internal(format!(
                    "cannot create lua/plugins directory {}: {error}",
                    plugins_dir.display()
                ))
            })?;
            let stem: String = name
                .trim_end_matches(".nvim")
                .trim_end_matches(".lua")
                .trim_start_matches("nvim-")
                .chars()
                .map(|c| {
                    if c.is_ascii_alphanumeric() || c == '_' || c == '-' {
                        c
                    } else {
                        '_'
                    }
                })
                .collect();
            let stem = if stem.is_empty() {
                "custom_plugin".to_owned()
            } else {
                stem
            };
            let mut candidate = plugins_dir.join(format!("{stem}.lua"));
            let mut counter = 1usize;
            while candidate.exists() {
                candidate = plugins_dir.join(format!("{stem}_{counter}.lua"));
                counter += 1;
            }

            let mut fields = vec![format!("  {}", quote_string(raw_source))];
            if let Some(enabled) = request.enabled {
                if !enabled {
                    fields.push("  enabled = false".to_owned());
                }
            }
            if let Some(lazy_val) = request.lazy {
                fields.push(format!("  lazy = {lazy_val}"));
            }
            if let Some(event) = &request.event {
                fields.push(format!("  event = {}", serialize_value(event)?));
            }
            if let Some(cmd) = &request.cmd {
                fields.push(format!("  cmd = {}", serialize_value(cmd)?));
            }
            if let Some(ft) = &request.ft {
                fields.push(format!("  ft = {}", serialize_value(ft)?));
            }
            if let Some(branch) = &request.branch {
                if !branch.trim().is_empty() {
                    fields.push(format!("  branch = {}", quote_string(branch.trim())));
                }
            }
            if let Some(tag) = &request.tag {
                if !tag.trim().is_empty() {
                    fields.push(format!("  tag = {}", quote_string(tag.trim())));
                }
            }
            if let Some(build) = &request.build {
                if !build.trim().is_empty() {
                    fields.push(format!("  build = {}", quote_string(build.trim())));
                }
            }
            if let Some(opts) = &request.opts {
                fields.push(format!("  opts = {}", serialize_value(opts)?));
            }

            let content = format!("return {{\n{},\n}}\n", fields.join(",\n"));
            full_moon::parse(&content).map_err(|errors| {
                ApiError::Internal(format!(
                    "refusing to save invalid lazy plugin Lua: {}",
                    errors
                        .iter()
                        .map(ToString::to_string)
                        .collect::<Vec<_>>()
                        .join("; ")
                ))
            })?;
            atomic_write(&candidate, content.as_bytes())?;
        }
        PluginManagerKind::Packer => {
            let target = existing_scan
                .snapshot
                .plugins
                .iter()
                .find(|p| p.manager == PluginManagerKind::Packer)
                .map(|p| PathBuf::from(&p.enabled.file))
                .unwrap_or_else(|| {
                    let packer_file = canonical_root.join("lua").join("plugins.lua");
                    if packer_file.exists() {
                        packer_file
                    } else {
                        canonical_root.join("init.lua")
                    }
                });

            let mut fields = vec![quote_string(raw_source)];
            if let Some(enabled) = request.enabled {
                if !enabled {
                    fields.push("disable = true".to_owned());
                }
            }
            if let Some(lazy_val) = request.lazy {
                if lazy_val {
                    fields.push("opt = true".to_owned());
                }
            }
            if let Some(event) = &request.event {
                fields.push(format!("event = {}", serialize_value(event)?));
            }
            if let Some(cmd) = &request.cmd {
                fields.push(format!("cmd = {}", serialize_value(cmd)?));
            }
            if let Some(ft) = &request.ft {
                fields.push(format!("ft = {}", serialize_value(ft)?));
            }
            if let Some(branch) = &request.branch {
                if !branch.trim().is_empty() {
                    fields.push(format!("branch = {}", quote_string(branch.trim())));
                }
            }
            if let Some(tag) = &request.tag {
                if !tag.trim().is_empty() {
                    fields.push(format!("tag = {}", quote_string(tag.trim())));
                }
            }
            if let Some(build) = &request.build {
                if !build.trim().is_empty() {
                    fields.push(format!("run = {}", quote_string(build.trim())));
                }
            }
            let use_stmt = format!("  use({{ {} }})\n", fields.join(", "));
            let existing = fs::read_to_string(&target).unwrap_or_default();
            let updated = if existing.trim().is_empty() {
                format!(
                    "return require('packer').startup(function(use)\n{use_stmt}end)\n"
                )
            } else if let Some(pos) = find_packer_insert_offset(&existing) {
                let mut s = existing.clone();
                s.insert_str(pos, &use_stmt);
                s
            } else {
                format!("{existing}\n{use_stmt}")
            };
            full_moon::parse(&updated).map_err(|errors| {
                ApiError::Internal(format!(
                    "refusing to save invalid packer Lua: {}",
                    errors
                        .iter()
                        .map(ToString::to_string)
                        .collect::<Vec<_>>()
                        .join("; ")
                ))
            })?;
            atomic_write(&target, updated.as_bytes())?;
        }
        PluginManagerKind::Plug => {
            let target = existing_scan
                .snapshot
                .plugins
                .iter()
                .find(|p| p.manager == PluginManagerKind::Plug)
                .map(|p| PathBuf::from(&p.enabled.file))
                .unwrap_or_else(|| canonical_root.join("init.vim"));

            let mut opts_parts = Vec::new();
            if let Some(branch) = &request.branch {
                if !branch.trim().is_empty() {
                    opts_parts.push(format!("'branch': '{}'", branch.trim().replace('\'', "''")));
                }
            }
            if let Some(tag) = &request.tag {
                if !tag.trim().is_empty() {
                    opts_parts.push(format!("'tag': '{}'", tag.trim().replace('\'', "''")));
                }
            }
            if let Some(build) = &request.build {
                if !build.trim().is_empty() {
                    opts_parts.push(format!("'do': '{}'", build.trim().replace('\'', "''")));
                }
            }
            if let Some( LuaValue::String { value: cmd } ) = &request.cmd {
                if !cmd.trim().is_empty() {
                    opts_parts.push(format!("'on': '{}'", cmd.trim().replace('\'', "''")));
                }
            }
            if let Some( LuaValue::String { value: ft } ) = &request.ft {
                if !ft.trim().is_empty() {
                    opts_parts.push(format!("'for': '{}'", ft.trim().replace('\'', "''")));
                }
            }
            let prefix_comment = if request.enabled == Some(false) {
                "\" "
            } else {
                ""
            };
            let plug_line = if opts_parts.is_empty() {
                format!(
                    "{prefix_comment}Plug '{}'\n",
                    raw_source.replace('\'', "''")
                )
            } else {
                format!(
                    "{prefix_comment}Plug '{}', {{ {} }}\n",
                    raw_source.replace('\'', "''"),
                    opts_parts.join(", ")
                )
            };
            let existing = fs::read_to_string(&target).unwrap_or_default();
            let updated = if existing.trim().is_empty() {
                format!("call plug#begin()\n{plug_line}call plug#end()\n")
            } else if let Some(pos) = find_plug_end_offset(&existing) {
                let mut s = existing.clone();
                s.insert_str(pos, &plug_line);
                s
            } else {
                format!("{existing}\n{plug_line}")
            };
            atomic_write(&target, updated.as_bytes())?;
        }
    }

    let scan_result = scan(&canonical_root);
    let _ = sync_state_file(&canonical_root, &scan_result.snapshot);
    Ok((scan_result, name, manager))
}

fn apply_target_edit(
    updated: &mut Vec<u8>,
    edit: &EditTarget,
    value: &LuaValue,
) -> Result<(), ApiError> {
    match edit {
        EditTarget::Replace(range) => {
            let source_text = std::str::from_utf8(updated)
                .map_err(|_| ApiError::Internal("target source is not UTF-8".to_owned()))?;
            let edits = plan_expression_edits(source_text, range, value)?;
            apply_text_edits(updated, edits)?;
        }
        EditTarget::ReplaceInverted(range) => {
            let inverted_value = match value {
                LuaValue::Boolean { value } => LuaValue::Boolean { value: !value },
                other => other.clone(),
            };
            let source_text = std::str::from_utf8(updated)
                .map_err(|_| ApiError::Internal("target source is not UTF-8".to_owned()))?;
            let edits = plan_expression_edits(source_text, range, &inverted_value)?;
            apply_text_edits(updated, edits)?;
        }
        EditTarget::ExpandBareStringToTable {
            range,
            plugin_source,
            name,
            invert_bool,
        } => {
            if range.end > updated.len() {
                return Err(ApiError::Internal(
                    "AST returned an invalid bare string range".to_owned(),
                ));
            }
            let effective_value = if *invert_bool {
                match value {
                    LuaValue::Boolean { value } => LuaValue::Boolean { value: !value },
                    other => other.clone(),
                }
            } else {
                value.clone()
            };
            let serialized_source = quote_string(plugin_source);
            let serialized_val = serialize_value(&effective_value)?;
            let replacement = format!("{{ {serialized_source}, {name} = {serialized_val} }}");
            updated.splice(range.clone(), replacement.bytes());
        }
        EditTarget::Insert {
            offset,
            needs_comma,
            name,
        } => {
            if *offset > updated.len() {
                return Err(ApiError::Internal(
                    "AST returned an invalid insertion offset".to_owned(),
                ));
            }
            let replacement = serialize_value(value)?;
            let separator = if *needs_comma { "," } else { "" };
            let insertion = format!("{separator}\n{name} = {replacement}");
            updated.splice(*offset..*offset, insertion.bytes());
        }
        EditTarget::InsertArg { offset } => {
            if *offset > updated.len() {
                return Err(ApiError::Internal(
                    "AST returned an invalid argument insertion offset".to_owned(),
                ));
            }
            let replacement = serialize_value(value)?;
            let insertion = format!(", {replacement}");
            updated.splice(*offset..*offset, insertion.bytes());
        }
        EditTarget::InsertInverted {
            offset,
            needs_comma,
            name,
        } => {
            if *offset > updated.len() {
                return Err(ApiError::Internal(
                    "AST returned an invalid insertion offset".to_owned(),
                ));
            }
            if matches!(value, LuaValue::Boolean { value: false }) {
                let separator = if *needs_comma { "," } else { "" };
                let insertion = format!("{separator}\n{name} = true");
                updated.splice(*offset..*offset, insertion.bytes());
            }
        }
        EditTarget::VimscriptReplace(range) => {
            if range.end > updated.len() {
                return Err(ApiError::Internal("invalid Vimscript replace range".to_owned()));
            }
            let replacement = serialize_vimscript_value(value)?;
            updated.splice(range.clone(), replacement.bytes());
        }
        EditTarget::VimscriptInsert {
            offset,
            needs_comma,
            name,
        } => {
            if *offset > updated.len() {
                return Err(ApiError::Internal("invalid Vimscript insert offset".to_owned()));
            }
            let replacement = serialize_vimscript_value(value)?;
            let separator = if *needs_comma { ", " } else { "" };
            let insertion = format!("{separator}'{name}': {replacement}");
            updated.splice(*offset..*offset, insertion.bytes());
        }
    }
    Ok(())
}

pub fn apply_patch(root: &Path, request: &PatchRequest) -> Result<PatchSuccess, ApiError> {
    apply_patch_with_snapshot(root, request, None)
}

pub fn apply_patch_with_snapshot(
    root: &Path,
    request: &PatchRequest,
    previous_snapshot: Option<&Snapshot>,
) -> Result<PatchSuccess, ApiError> {
    if matches!(request.value, LuaValue::Unsupported { .. }) {
        return Err(ApiError::BadRequest(
            "unsupported Lua source is read-only".to_owned(),
        ));
    }
    let requested_file = PathBuf::from(&request.file);
    if !requested_file.is_absolute() {
        return Err(ApiError::BadRequest(
            "entity file must be an absolute path".to_owned(),
        ));
    }
    let canonical_root = root
        .canonicalize()
        .map_err(|error| ApiError::Internal(format!("cannot resolve config root: {error}")))?;
    let canonical_file = requested_file
        .canonicalize()
        .map_err(|error| ApiError::Conflict(format!("cannot resolve {}: {error}", request.file)))?;
    if !canonical_file.starts_with(&canonical_root) {
        return Err(ApiError::BadRequest(
            "refusing to write outside the config root".to_owned(),
        ));
    }
    let source = fs::read(&canonical_file)
        .map_err(|error| ApiError::Internal(format!("cannot read {}: {error}", request.file)))?;
    if revision(&source) != request.revision {
        return Err(ApiError::Conflict(format!(
            "revision mismatch for {}; reload the snapshot",
            request.file
        )));
    }

    // PERF-P1-01: Scan only the target file before patching rather than the entire directory tree
    let current = scan_single_file(&canonical_root, &canonical_file);
    let target = current
        .targets
        .get(&request.id)
        .ok_or_else(|| ApiError::NotFound(format!("entity {} was not found", request.id)))?;
    let expected_file = target.file.to_string_lossy();
    let target_file = target
        .file
        .canonicalize()
        .map_err(|error| ApiError::Conflict(format!("cannot resolve {expected_file}: {error}")))?;
    if canonical_file != target_file {
        return Err(ApiError::BadRequest(format!(
            "entity file mismatch: expected {expected_file}"
        )));
    }
    if request.revision != target.revision {
        return Err(ApiError::Conflict(format!(
            "revision mismatch for {expected_file}; reload the snapshot"
        )));
    }
    if target.read_only {
        return Err(ApiError::BadRequest(
            "dynamic or unsupported Lua values are read-only".to_owned(),
        ));
    }
    let is_vimscript = canonical_file.extension().is_some_and(|ext| ext == "vim");
    let mut updated = source;
    apply_target_edit(&mut updated, &target.edit, &request.value)?;

    let updated_text = String::from_utf8(updated)
        .map_err(|_| ApiError::Internal("patched source is not UTF-8".to_owned()))?;
    if is_vimscript {
        validate_vimscript(&updated_text)?;
    } else {
        full_moon::parse(&updated_text).map_err(|errors| {
            ApiError::Internal(format!(
                "refusing to save invalid patched Lua: {}",
                errors
                    .iter()
                    .map(ToString::to_string)
                    .collect::<Vec<_>>()
                    .join("; ")
            ))
        })?;
    }
    atomic_write(&canonical_file, updated_text.as_bytes())?;
    let entity = target.entity.clone();
    drop(current);
    let scan_res = rescan_file_in_snapshot(&canonical_root, &canonical_file, previous_snapshot);
    let _ = sync_state_file(&canonical_root, &scan_res.snapshot);
    Ok(PatchSuccess {
        scan: scan_res,
        entity,
    })
}

pub fn apply_batch_patch(
    root: &Path,
    requests: &[PatchRequest],
    previous_snapshot: Option<&Snapshot>,
) -> Result<PatchSuccess, ApiError> {
    if requests.is_empty() {
        return Err(ApiError::BadRequest(
            "batch patch requires at least one patch item".to_owned(),
        ));
    }
    if requests.len() == 1 {
        return apply_patch_with_snapshot(root, &requests[0], previous_snapshot);
    }

    let first = &requests[0];
    let requested_file = PathBuf::from(&first.file);
    if !requested_file.is_absolute() {
        return Err(ApiError::BadRequest(
            "entity file must be an absolute path".to_owned(),
        ));
    }
    let canonical_root = root
        .canonicalize()
        .map_err(|error| ApiError::Internal(format!("cannot resolve config root: {error}")))?;
    let canonical_file = requested_file
        .canonicalize()
        .map_err(|error| ApiError::Conflict(format!("cannot resolve {}: {error}", first.file)))?;
    if !canonical_file.starts_with(&canonical_root) {
        return Err(ApiError::BadRequest(
            "refusing to write outside the config root".to_owned(),
        ));
    }
    let source = fs::read(&canonical_file)
        .map_err(|error| ApiError::Internal(format!("cannot read {}: {error}", first.file)))?;
    let initial_rev = revision(&source);
    if initial_rev != first.revision {
        return Err(ApiError::Conflict(format!(
            "revision mismatch for {}; reload the snapshot",
            first.file
        )));
    }

    let is_vimscript = canonical_file.extension().is_some_and(|ext| ext == "vim");
    let mut updated = source;
    let mut last_entity: Option<RuntimeEntity> = None;

    // Resolve all targets against the initial file AST so we can sort by descending byte offset
    // (or re-parse in memory if offsets collide or bare strings expand).
    let initial_scan = scan_single_file(&canonical_root, &canonical_file);
    let mut resolved = Vec::with_capacity(requests.len());
    for req in requests {
        if matches!(req.value, LuaValue::Unsupported { .. }) {
            return Err(ApiError::BadRequest(
                "unsupported Lua source is read-only".to_owned(),
            ));
        }
        if !req.revision.is_empty() && req.revision != initial_rev {
            return Err(ApiError::Conflict(format!(
                "revision mismatch for {}; reload the snapshot",
                req.file
            )));
        }
        let target = initial_scan
            .targets
            .get(&req.id)
            .ok_or_else(|| ApiError::NotFound(format!("entity {} was not found", req.id)))?;
        if target.read_only {
            return Err(ApiError::BadRequest(
                "dynamic or unsupported Lua values are read-only".to_owned(),
            ));
        }
        let edit_offset = match &target.edit {
            EditTarget::Replace(r)
            | EditTarget::ReplaceInverted(r)
            | EditTarget::ExpandBareStringToTable { range: r, .. }
            | EditTarget::VimscriptReplace(r) => r.start,
            EditTarget::Insert { offset, .. }
            | EditTarget::InsertArg { offset }
            | EditTarget::InsertInverted { offset, .. }
            | EditTarget::VimscriptInsert { offset, .. } => *offset,
        };
        last_entity = Some(target.entity.clone());
        resolved.push((edit_offset, target.edit.clone(), req.value.clone()));
    }

    // Sort by descending byte offset so edits near the end of the file never shift earlier offsets.
    // If multiple Insert edits target the exact same offset, only the one applied last (first in file order)
    // uses the original `needs_comma`, while subsequent ones at that offset prepend a comma.
    resolved.sort_by(|a, b| b.0.cmp(&a.0));
    for i in 0..resolved.len() {
        let same_offset_follows = i + 1 < resolved.len() && resolved[i + 1].0 == resolved[i].0;
        let mut edit = resolved[i].1.clone();
        if same_offset_follows {
            if let EditTarget::Insert { needs_comma, .. } = &mut edit {
                *needs_comma = true;
            }
        }
        apply_target_edit(&mut updated, &edit, &resolved[i].2)?;
    }

    let updated_text = String::from_utf8(updated)
        .map_err(|_| ApiError::Internal("patched source is not UTF-8".to_owned()))?;
    if is_vimscript {
        validate_vimscript(&updated_text)?;
    } else {
        full_moon::parse(&updated_text).map_err(|errors| {
            ApiError::Internal(format!(
                "refusing to save invalid batch-patched Lua: {}",
                errors
                    .iter()
                    .map(ToString::to_string)
                    .collect::<Vec<_>>()
                    .join("; ")
            ))
        })?;
    }
    atomic_write(&canonical_file, updated_text.as_bytes())?;
    let scan_res = rescan_file_in_snapshot(&canonical_root, &canonical_file, previous_snapshot);
    let _ = sync_state_file(&canonical_root, &scan_res.snapshot);
    Ok(PatchSuccess {
        scan: scan_res,
        entity: last_entity.unwrap(),
    })
}

pub fn delete_entity(
    root: &Path,
    request: &DeleteEntityRequest,
) -> Result<PatchSuccess, ApiError> {
    if request.id.trim().is_empty() {
        return Err(ApiError::BadRequest("entity id is required".to_owned()));
    }
    let canonical_root = root
        .canonicalize()
        .map_err(|error| ApiError::Internal(format!("cannot resolve config root: {error}")))?;
    let current = scan(root);
    let target = current
        .delete_targets
        .get(&request.id)
        .ok_or_else(|| ApiError::NotFound(format!("entity {} was not found", request.id)))?;

    let expected_file = target.file.to_string_lossy();
    let canonical_file = target
        .file
        .canonicalize()
        .map_err(|error| ApiError::Conflict(format!("cannot resolve {expected_file}: {error}")))?;
    if !canonical_file.starts_with(&canonical_root) {
        return Err(ApiError::BadRequest(
            "refusing to write outside the config root".to_owned(),
        ));
    }
    if let Some(ref req_file) = request.file {
        if !req_file.trim().is_empty() {
            let requested_path = PathBuf::from(req_file);
            if requested_path.is_absolute() {
                if let Ok(canon_req) = requested_path.canonicalize() {
                    if canon_req != canonical_file {
                        return Err(ApiError::BadRequest(format!(
                            "entity file mismatch: expected {expected_file}"
                        )));
                    }
                }
            }
        }
    }
    let mut source = fs::read(&canonical_file)
        .map_err(|error| ApiError::Internal(format!("cannot read {expected_file}: {error}")))?;
    let actual_rev = revision(&source);
    if actual_rev != target.revision {
        return Err(ApiError::Conflict(format!(
            "revision mismatch for {expected_file}; reload the snapshot"
        )));
    }
    if let Some(ref req_rev) = request.revision {
        if !req_rev.trim().is_empty() && *req_rev != actual_rev {
            return Err(ApiError::Conflict(format!(
                "revision mismatch for {expected_file}; reload the snapshot"
            )));
        }
    }

    apply_delete_action(&mut source, &target.action)?;

    let updated_text = String::from_utf8(source)
        .map_err(|_| ApiError::Internal("patched source is not UTF-8".to_owned()))?;
    let is_vimscript = canonical_file.extension().is_some_and(|ext| ext == "vim");
    if is_vimscript {
        validate_vimscript(&updated_text)?;
    } else {
        full_moon::parse(&updated_text).map_err(|errors| {
            ApiError::Internal(format!(
                "refusing to save invalid patched Lua after delete: {}",
                errors
                    .iter()
                    .map(ToString::to_string)
                    .collect::<Vec<_>>()
                    .join("; ")
            ))
        })?;
    }

    atomic_write(&canonical_file, updated_text.as_bytes())?;
    let entity = target.entity.clone();
    drop(current);
    let scan_res = scan(root);
    let _ = sync_state_file(&canonical_root, &scan_res.snapshot);
    Ok(PatchSuccess {
        scan: scan_res,
        entity,
    })
}

fn apply_delete_action(source: &mut Vec<u8>, action: &DeleteAction) -> Result<(), ApiError> {
    match action {
        DeleteAction::ClearLazySingleSpecFile(range) => {
            if range.end > source.len() {
                return Err(ApiError::Internal("invalid delete range".to_owned()));
            }
            source.splice(range.clone(), b"{}".iter().copied());
            Ok(())
        }
        DeleteAction::RemoveLineOrSpan(range) => {
            if range.end > source.len() {
                return Err(ApiError::Internal("invalid delete range".to_owned()));
            }
            let mut line_start = range.start;
            while line_start > 0
                && (source[line_start - 1] == b' ' || source[line_start - 1] == b'\t')
            {
                line_start -= 1;
            }
            let at_bol = line_start == 0 || source[line_start - 1] == b'\n';
            let mut after = range.end;
            while after < source.len() && (source[after] == b' ' || source[after] == b'\t') {
                after += 1;
            }
            if after < source.len() && source[after] == b';' {
                after += 1;
                while after < source.len() && (source[after] == b' ' || source[after] == b'\t') {
                    after += 1;
                }
            }
            if at_bol
                && (after == source.len()
                    || source[after] == b'\n'
                    || (source[after] == b'\r'
                        && after + 1 < source.len()
                        && source[after + 1] == b'\n'))
            {
                if after < source.len() && source[after] == b'\r' {
                    after += 1;
                }
                if after < source.len() && source[after] == b'\n' {
                    after += 1;
                }
                source.splice(line_start..after, std::iter::empty());
            } else {
                source.splice(range.start..after, std::iter::empty());
            }
            Ok(())
        }
        DeleteAction::RemoveTableElement {
            element_range,
            table_range,
        } => {
            if element_range.end > source.len() || table_range.end > source.len() {
                return Err(ApiError::Internal("invalid table element range".to_owned()));
            }
            let mut start = element_range.start;
            let mut end = element_range.end;
            let mut temp = end;
            while temp < table_range.end && (source[temp] == b' ' || source[temp] == b'\t') {
                temp += 1;
            }
            let mut consumed_sep = false;
            if temp < table_range.end && (source[temp] == b',' || source[temp] == b';') {
                end = temp + 1;
                consumed_sep = true;
            }
            if !consumed_sep {
                let mut prev = start;
                while prev > table_range.start
                    && (source[prev - 1] == b' '
                        || source[prev - 1] == b'\t'
                        || source[prev - 1] == b'\r'
                        || source[prev - 1] == b'\n')
                {
                    prev -= 1;
                }
                if prev > table_range.start
                    && (source[prev - 1] == b',' || source[prev - 1] == b';')
                {
                    start = prev - 1;
                }
            } else {
                let mut line_start = start;
                while line_start > table_range.start
                    && (source[line_start - 1] == b' ' || source[line_start - 1] == b'\t')
                {
                    line_start -= 1;
                }
                let at_bol = line_start == 0 || source[line_start - 1] == b'\n';
                let mut after = end;
                while after < table_range.end && (source[after] == b' ' || source[after] == b'\t') {
                    after += 1;
                }
                if at_bol
                    && after < table_range.end
                    && (source[after] == b'\n' || source[after] == b'\r')
                {
                    start = line_start;
                    if source[after] == b'\r' {
                        after += 1;
                    }
                    if after < table_range.end && source[after] == b'\n' {
                        after += 1;
                    }
                    end = after;
                }
            }
            source.splice(start..end, std::iter::empty());
            Ok(())
        }
    }
}

#[derive(Debug)]
struct TextEdit {
    range: Range<usize>,
    replacement: String,
}

struct ExpressionPatchPlanner<'a> {
    target: Range<usize>,
    requested: &'a LuaValue,
    source: &'a str,
    result: Option<Result<Vec<TextEdit>, ApiError>>,
}

impl Visitor for ExpressionPatchPlanner<'_> {
    fn visit_expression(&mut self, expression: &Expression) {
        if self.result.is_none() && node_range(expression).range == self.target {
            self.result = Some(plan_value_edits(expression, self.requested, self.source));
        }
    }

    fn visit_function_args(&mut self, args: &FunctionArgs) {
        if self.result.is_none() {
            match args {
                FunctionArgs::String(tok) => {
                    if node_range(tok).range == self.target {
                        self.result = Some(serialize_value(self.requested).map(|replacement| {
                            vec![TextEdit {
                                range: self.target.clone(),
                                replacement,
                            }]
                        }));
                    }
                }
                FunctionArgs::TableConstructor(table) => {
                    if node_range(table).range == self.target {
                        let current = parse_table(table, self.source)
                            .unwrap_or_else(|| unsupported(table, self.source));
                        if current == *self.requested {
                            self.result = Some(Ok(Vec::new()));
                        } else {
                            self.result = Some(match (&current, self.requested) {
                                (
                                    LuaValue::Array { values: old_values },
                                    LuaValue::Array { values: new_values },
                                ) => plan_array_edits(table, old_values, new_values, self.source),
                                (LuaValue::Table { .. }, LuaValue::Table { entries }) => {
                                    plan_table_edits(table, entries, self.source)
                                }
                                _ => serialize_value(self.requested).map(|replacement| {
                                    vec![TextEdit {
                                        range: self.target.clone(),
                                        replacement,
                                    }]
                                }),
                            });
                        }
                    }
                }
                _ => {}
            }
        }
    }
}

fn plan_expression_edits(
    source: &str,
    target: &Range<usize>,
    requested: &LuaValue,
) -> Result<Vec<TextEdit>, ApiError> {
    let ast = full_moon::parse(source).map_err(|errors| {
        ApiError::Internal(format!(
            "cannot reparse target before patching: {}",
            errors
                .iter()
                .map(ToString::to_string)
                .collect::<Vec<_>>()
                .join("; ")
        ))
    })?;
    let mut planner = ExpressionPatchPlanner {
        target: target.clone(),
        requested,
        source,
        result: None,
    };
    planner.visit_ast(&ast);
    planner.result.unwrap_or_else(|| {
        Err(ApiError::Internal(
            "target expression disappeared during AST patch planning".to_owned(),
        ))
    })
}

fn plan_value_edits(
    expression: &Expression,
    requested: &LuaValue,
    source: &str,
) -> Result<Vec<TextEdit>, ApiError> {
    let current = parse_value(expression, source);
    if current == *requested {
        return Ok(Vec::new());
    }
    if matches!(requested, LuaValue::Unsupported { .. }) {
        return Err(ApiError::BadRequest(
            "unsupported Lua source is read-only".to_owned(),
        ));
    }

    match (expression, &current, requested) {
        (
            Expression::TableConstructor(table),
            LuaValue::Array { values: old_values },
            LuaValue::Array { values: new_values },
        ) => plan_array_edits(table, old_values, new_values, source),
        (
            Expression::TableConstructor(table),
            LuaValue::Table { .. },
            LuaValue::Table { entries },
        ) => plan_table_edits(table, entries, source),
        _ => {
            if matches!(current, LuaValue::Array { .. } | LuaValue::Table { .. })
                && (node_has_comments(expression) || contains_unsupported(Some(&current)))
            {
                return Err(ApiError::BadRequest(
                    "structural replacement would remove comments or unsupported Lua; change static leaves instead".to_owned(),
                ));
            }
            Ok(vec![TextEdit {
                range: node_range(expression).range,
                replacement: serialize_value(requested)?,
            }])
        }
    }
}

fn plan_array_edits(
    table: &TableConstructor,
    old_values: &[LuaValue],
    new_values: &[LuaValue],
    source: &str,
) -> Result<Vec<TextEdit>, ApiError> {
    let pairs = table.fields().pairs().collect::<Vec<_>>();
    let expressions = pairs
        .iter()
        .map(|pair| match pair.value() {
            AstField::NoKey(expression) => Ok(expression),
            _ => Err(ApiError::Internal(
                "array AST contains a named field".to_owned(),
            )),
        })
        .collect::<Result<Vec<_>, _>>()?;

    if let Some(matched_new) = subsequence(old_values, new_values) {
        let mut old_for_new = vec![None; new_values.len()];
        for (old_index, new_index) in matched_new.into_iter().enumerate() {
            old_for_new[new_index] = Some(old_index);
        }
        let mut insertions = BTreeMap::<usize, Vec<String>>::new();
        let mut appended = Vec::new();
        for (new_index, value) in new_values.iter().enumerate() {
            if old_for_new[new_index].is_some() {
                continue;
            }
            let next_old = old_for_new[new_index + 1..]
                .iter()
                .flatten()
                .copied()
                .next();
            if let Some(old_index) = next_old {
                insertions
                    .entry(node_range(expressions[old_index]).range.start)
                    .or_default()
                    .push(format!("{}, ", serialize_value(value)?));
            } else {
                appended.push(serialize_value(value)?);
            }
        }
        let mut edits = insertions
            .into_iter()
            .map(|(offset, values)| TextEdit {
                range: offset..offset,
                replacement: values.concat(),
            })
            .collect::<Vec<_>>();
        if let Some(edit) = append_to_table(table, appended)? {
            edits.push(edit);
        }
        return Ok(edits);
    }

    if let Some(matched_old) = subsequence(new_values, old_values) {
        let mut retained = vec![false; old_values.len()];
        for old_index in matched_old {
            retained[old_index] = true;
        }
        return pairs
            .into_iter()
            .enumerate()
            .filter(|(index, _)| !retained[*index])
            .map(|(_, pair)| delete_field(pair, source))
            .collect();
    }

    let common = old_values.len().min(new_values.len());
    let mut edits = Vec::new();
    for index in 0..common {
        edits.extend(plan_value_edits(
            expressions[index],
            &new_values[index],
            source,
        )?);
    }
    if old_values.len() > common {
        for pair in &pairs[common..] {
            edits.push(delete_field(pair, source)?);
        }
    } else {
        let additions = new_values[common..]
            .iter()
            .map(serialize_value)
            .collect::<Result<Vec<_>, _>>()?;
        if let Some(edit) = append_to_table(table, additions)? {
            edits.push(edit);
        }
    }
    Ok(edits)
}

fn plan_table_edits(
    table: &TableConstructor,
    requested: &[TableEntry],
    source: &str,
) -> Result<Vec<TextEdit>, ApiError> {
    let items = table_items(table, source)?;
    let pairs = table.fields().pairs().collect::<Vec<_>>();
    let mut used = vec![false; requested.len()];
    let mut edits = Vec::new();

    for (index, item) in items.iter().enumerate() {
        let occurrence = items[..index]
            .iter()
            .filter(|candidate| candidate.key == item.key)
            .count();
        let requested_index = requested
            .iter()
            .enumerate()
            .filter(|(_, entry)| entry.key == item.key)
            .nth(occurrence)
            .map(|(index, _)| index);
        if let Some(requested_index) = requested_index {
            used[requested_index] = true;
            edits.extend(plan_value_edits(
                item.expression,
                &requested[requested_index].value,
                source,
            )?);
        } else {
            edits.push(delete_field(pairs[index], source)?);
        }
    }

    let additions = requested
        .iter()
        .zip(used)
        .filter(|(_, used)| !used)
        .map(|(entry, _)| serialize_table_entry(entry))
        .collect::<Result<Vec<_>, _>>()?;
    if let Some(edit) = append_to_table(table, additions)? {
        edits.push(edit);
    }
    Ok(edits)
}

struct TableItem<'a> {
    key: String,
    expression: &'a Expression,
}

fn table_items<'a>(
    table: &'a TableConstructor,
    source: &str,
) -> Result<Vec<TableItem<'a>>, ApiError> {
    let mut items = Vec::new();
    let mut array_index = 1usize;
    for field in table.fields().iter() {
        let (key, expression) = match field {
            AstField::NoKey(expression) => {
                let key = array_index.to_string();
                array_index += 1;
                (key, expression)
            }
            AstField::NameKey { key, value, .. } => (key.token().to_string(), value),
            AstField::ExpressionKey { key, value, .. } => {
                let key = match parse_value(key, source) {
                    LuaValue::String { value } => value,
                    LuaValue::Number { value } => value.to_string(),
                    LuaValue::Boolean { value } => value.to_string(),
                    _ => {
                        return Err(ApiError::BadRequest(
                            "table has a dynamic key and cannot be structurally patched".to_owned(),
                        ));
                    }
                };
                (key, value)
            }
            _ => {
                return Err(ApiError::BadRequest(
                    "table field type cannot be structurally patched".to_owned(),
                ));
            }
        };
        items.push(TableItem { key, expression });
    }
    Ok(items)
}

fn append_to_table(
    table: &TableConstructor,
    values: Vec<String>,
) -> Result<Option<TextEdit>, ApiError> {
    if values.is_empty() {
        return Ok(None);
    }
    let (offset, separator) = match table.fields().last() {
        Some(pair) => match pair.punctuation() {
            Some(punctuation) => (punctuation.token().end_position().bytes(), " "),
            None => (node_range(pair.value()).range.end, ", "),
        },
        None => (
            table.braces().tokens().0.token().end_position().bytes(),
            "\n",
        ),
    };
    Ok(Some(TextEdit {
        range: offset..offset,
        replacement: format!("{separator}{}", values.join(", ")),
    }))
}

fn delete_field(pair: &Pair<AstField>, source: &str) -> Result<TextEdit, ApiError> {
    let expression = match pair.value() {
        AstField::NoKey(expression)
        | AstField::NameKey {
            value: expression, ..
        }
        | AstField::ExpressionKey {
            value: expression, ..
        } => expression,
        _ => {
            return Err(ApiError::BadRequest(
                "table field cannot be safely deleted".to_owned(),
            ));
        }
    };
    if node_has_comments(pair.value())
        || contains_unsupported(Some(&parse_value(expression, source)))
    {
        return Err(ApiError::BadRequest(
            "deletion would remove comments or unsupported Lua; refusing to rewrite the container"
                .to_owned(),
        ));
    }
    let mut range = node_range(pair.value()).range;
    if let Some(punctuation) = pair.punctuation() {
        range.end = punctuation.token().end_position().bytes();
    }
    Ok(TextEdit {
        range,
        replacement: String::new(),
    })
}

fn serialize_table_entry(entry: &TableEntry) -> Result<String, ApiError> {
    let key = if is_identifier(&entry.key) {
        entry.key.clone()
    } else {
        format!("[{}]", quote_string(&entry.key))
    };
    Ok(format!("{key} = {}", serialize_value(&entry.value)?))
}

fn subsequence(needle: &[LuaValue], haystack: &[LuaValue]) -> Option<Vec<usize>> {
    let mut matched = Vec::with_capacity(needle.len());
    let mut start = 0usize;
    for value in needle {
        let index = haystack[start..]
            .iter()
            .position(|candidate| candidate == value)?
            + start;
        matched.push(index);
        start = index + 1;
    }
    Some(matched)
}

fn node_has_comments(node: &impl Node) -> bool {
    node.tokens().any(|token| {
        token
            .leading_trivia()
            .chain(token.trailing_trivia())
            .any(|trivia| {
                matches!(
                    trivia.token_kind(),
                    TokenKind::SingleLineComment | TokenKind::MultiLineComment
                )
            })
    })
}

fn apply_text_edits(source: &mut Vec<u8>, mut edits: Vec<TextEdit>) -> Result<(), ApiError> {
    for edit in &edits {
        if edit.range.start > edit.range.end || edit.range.end > source.len() {
            return Err(ApiError::Internal(
                "structured patch produced an invalid byte range".to_owned(),
            ));
        }
    }
    for (index, edit) in edits.iter().enumerate() {
        if edits[index + 1..]
            .iter()
            .any(|other| edit.range.start < other.range.end && other.range.start < edit.range.end)
        {
            return Err(ApiError::Internal(
                "structured patch produced overlapping edits".to_owned(),
            ));
        }
    }
    edits.sort_by(|left, right| {
        right
            .range
            .start
            .cmp(&left.range.start)
            .then_with(|| right.range.end.cmp(&left.range.end))
    });
    for edit in edits {
        source.splice(edit.range, edit.replacement.bytes());
    }
    Ok(())
}

fn infer_config_root_for_backup(file: &Path) -> PathBuf {
    let Some(parent) = file.parent() else {
        return PathBuf::from(".");
    };
    let mut current = parent;
    for _ in 0..4 {
        if let Some(dir_name) = current.file_name().and_then(|n| n.to_str()) {
            if matches!(dir_name, "plugins" | "lazy" | "lua" | "plugin" | "after") {
                if let Some(up) = current.parent() {
                    current = up;
                    continue;
                }
            }
        }
        break;
    }
    current.to_path_buf()
}

fn create_file_backup(file: &Path) {
    let Ok(existing) = fs::read(file) else {
        return;
    };
    let root = infer_config_root_for_backup(file);
    let backup_dir = root.join(".backup");
    if fs::create_dir_all(&backup_dir).is_err() {
        return;
    }
    let rel = relative_path(&root, file);
    let sanitized = rel.replace(['/', '\\'], "__");
    let rev = revision(&existing);
    let short_rev = &rev[..8.min(rev.len())];
    let ts = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis();
    let bak_name = format!("{sanitized}.{ts}.{short_rev}.bak");
    let bak_path = backup_dir.join(&bak_name);
    if fs::write(&bak_path, &existing).is_ok() {
        let latest_meta = serde_json::json!({
            "file": rel,
            "abs_file": file.to_string_lossy(),
            "backup_file": bak_name,
            "revision": rev,
            "timestamp": ts,
        });
        let _ = fs::write(
            backup_dir.join("latest.json"),
            serde_json::to_vec_pretty(&latest_meta).unwrap_or_default(),
        );
        // Rolling retention: keep at most 20 backups per file
        if let Ok(entries) = fs::read_dir(&backup_dir) {
            let prefix = format!("{sanitized}.");
            let mut matching: Vec<PathBuf> = entries
                .filter_map(|e| e.ok().map(|e| e.path()))
                .filter(|p| {
                    p.file_name()
                        .and_then(|n| n.to_str())
                        .is_some_and(|n| n.starts_with(&prefix) && n.ends_with(".bak"))
                })
                .collect();
            matching.sort();
            if matching.len() > 20 {
                let remove_count = matching.len() - 20;
                for old in matching.into_iter().take(remove_count) {
                    let _ = fs::remove_file(old);
                }
            }
        }
    }
}

pub fn rollback_backup(
    root: &Path,
    target_file: Option<&str>,
    target_revision: Option<&str>,
) -> Result<ScanResult, ApiError> {
    let backup_dir = root.join(".backup");
    if !backup_dir.exists() {
        return Err(ApiError::NotFound("no backup history found".to_owned()));
    }
    let sanitized_filter = target_file.map(|f| {
        let p = Path::new(f);
        let rel = if p.is_absolute() {
            relative_path(root, p)
        } else {
            f.replace('\\', "/")
        };
        (rel, p.to_path_buf())
    });

    let entries = fs::read_dir(&backup_dir)
        .map_err(|e| ApiError::Internal(format!("cannot read .backup directory: {e}")))?;
    let mut candidates: Vec<(String, PathBuf)> = entries
        .filter_map(|e| e.ok())
        .filter_map(|e| {
            let path = e.path();
            let name = path.file_name()?.to_str()?.to_owned();
            if name.ends_with(".bak") {
                Some((name, path))
            } else {
                None
            }
        })
        .collect();
    candidates.sort_by(|a, b| b.0.cmp(&a.0));

    for (name, bak_path) in candidates {
        if let Some((ref rel, _)) = sanitized_filter {
            let expected_prefix = format!("{}.", rel.replace(['/', '\\'], "__"));
            if !name.starts_with(&expected_prefix) {
                continue;
            }
        }
        if let Some(rev_filter) = target_revision {
            let short = &rev_filter[..8.min(rev_filter.len())];
            if !name.contains(&format!(".{short}.bak")) {
                continue;
            }
        }
        let parts: Vec<&str> = name.rsplitn(4, '.').collect();
        if parts.len() < 4 {
            continue;
        }
        let sanitized_rel = parts[3];
        let rel_path = sanitized_rel.replace("__", "/");
        let dest = root.join(&rel_path);
        let contents = fs::read(&bak_path)
            .map_err(|e| ApiError::Internal(format!("cannot read backup file: {e}")))?;
        atomic_write(&dest, &contents)?;
        let scan_res = scan(root);
        let _ = sync_state_file(root, &scan_res.snapshot);
        return Ok(scan_res);
    }

    Err(ApiError::NotFound(
        "no matching backup snapshot found for rollback".to_owned(),
    ))
}

#[derive(Clone, Debug, serde::Serialize, serde::Deserialize)]
pub struct UcdpStateFile {
    pub version: u32,
    pub config_root: String,
    pub settings: Vec<Setting>,
    pub keymaps: Vec<Keymap>,
    pub plugins: Vec<Plugin>,
}

pub fn sync_state_file(root: &Path, snapshot: &Snapshot) -> Result<PathBuf, ApiError> {
    if !root.exists() {
        return Err(ApiError::NotFound(format!(
            "config root {} does not exist",
            root.display()
        )));
    }
    let state_dir = root.join(".ucdp");
    fs::create_dir_all(&state_dir).map_err(|e| {
        ApiError::Internal(format!(
            "cannot create .ucdp state directory {}: {e}",
            state_dir.display()
        ))
    })?;
    let state_path = state_dir.join("state.json");
    let state_obj = UcdpStateFile {
        version: 1,
        config_root: snapshot.config_root.clone(),
        settings: snapshot.settings.clone(),
        keymaps: snapshot.keymaps.clone(),
        plugins: snapshot.plugins.clone(),
    };
    let payload = serde_json::to_vec_pretty(&state_obj).map_err(|e| {
        ApiError::Internal(format!("cannot serialize .ucdp/state.json payload: {e}"))
    })?;
    fs::write(&state_path, payload).map_err(|e| {
        ApiError::Internal(format!(
            "cannot write .ucdp/state.json at {}: {e}",
            state_path.display()
        ))
    })?;
    Ok(state_path)
}

pub fn load_state_file(root: &Path) -> Option<UcdpStateFile> {
    let state_path = root.join(".ucdp").join("state.json");
    let bytes = fs::read(state_path).ok()?;
    serde_json::from_slice(&bytes).ok()
}

pub fn compile_plugin_spec_lua(plugin: &Plugin) -> Result<String, ApiError> {
    let mut fields = vec![format!("  {}", quote_string(&plugin.source))];
    if let Some(LuaValue::Boolean { value: false }) = &plugin.enabled.value {
        fields.push("  enabled = false".to_owned());
    }
    if let Some(ref f) = plugin.lazy {
        if let Some(ref val) = f.value {
            if !matches!(val, LuaValue::Unsupported { .. }) {
                fields.push(format!("  lazy = {}", serialize_value(val)?));
            }
        }
    }
    if let Some(ref f) = plugin.pin {
        if let Some(ref val) = f.value {
            if !matches!(val, LuaValue::Unsupported { .. }) {
                fields.push(format!("  pin = {}", serialize_value(val)?));
            }
        }
    }
    if let Some(ref val) = plugin.event.value {
        if !matches!(val, LuaValue::Unsupported { .. }) {
            fields.push(format!("  event = {}", serialize_value(val)?));
        }
    }
    if let Some(ref f) = plugin.cmd {
        if let Some(ref val) = f.value {
            if !matches!(val, LuaValue::Unsupported { .. }) {
                fields.push(format!("  cmd = {}", serialize_value(val)?));
            }
        }
    }
    if let Some(ref f) = plugin.ft {
        if let Some(ref val) = f.value {
            if !matches!(val, LuaValue::Unsupported { .. }) {
                fields.push(format!("  ft = {}", serialize_value(val)?));
            }
        }
    }
    if let Some(ref val) = plugin.keys.value {
        if !matches!(val, LuaValue::Unsupported { .. }) {
            fields.push(format!("  keys = {}", serialize_value(val)?));
        }
    }
    for (slot_name, slot_opt) in [
        ("branch", &plugin.branch),
        ("tag", &plugin.tag),
        ("commit", &plugin.commit),
        ("version", &plugin.version),
        ("build", &plugin.build),
        ("dependencies", &plugin.dependencies),
    ] {
        if let Some(ref f) = slot_opt {
            if let Some(ref val) = f.value {
                if !matches!(val, LuaValue::Unsupported { .. }) {
                    fields.push(format!("  {slot_name} = {}", serialize_value(val)?));
                }
            }
        }
    }
    if let Some(ref val) = plugin.opts.value {
        if !matches!(val, LuaValue::Unsupported { .. }) {
            fields.push(format!("  opts = {}", serialize_value(val)?));
        }
    }
    if let Some(ref f) = plugin.config {
        if let Some(LuaValue::Unsupported { ref source }) = f.value {
            fields.push(format!("  config = {source}"));
        } else if let Some(ref val) = f.value {
            fields.push(format!("  config = {}", serialize_value(val)?));
        }
    }
    Ok(format!("return {{\n{},\n}}\n", fields.join(",\n")))
}

fn atomic_write(file: &Path, contents: &[u8]) -> Result<(), ApiError> {
    if file.exists() {
        create_file_backup(file);
    }
    let parent = file
        .parent()
        .ok_or_else(|| ApiError::Internal("target has no parent directory".to_owned()))?;
    let permissions = match fs::metadata(file) {
        Ok(metadata) => Some(metadata.permissions()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => None,
        Err(error) => {
            return Err(ApiError::Internal(format!(
                "cannot read file permissions: {error}"
            )));
        }
    };
    let name = file
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or("config.lua");
    let mut random = [0u8; 8];
    rand::thread_rng().fill_bytes(&mut random);
    let temporary = parent.join(format!(".{name}.ucdp-{}.tmp", hex::encode(random)));

    let result = (|| -> Result<(), ApiError> {
        let mut output = OpenOptions::new()
            .create_new(true)
            .write(true)
            .open(&temporary)
            .map_err(|error| {
                ApiError::Internal(format!("cannot create temporary file: {error}"))
            })?;
        output
            .write_all(contents)
            .map_err(|error| ApiError::Internal(format!("cannot write temporary file: {error}")))?;
        output
            .sync_all()
            .map_err(|error| ApiError::Internal(format!("cannot sync temporary file: {error}")))?;
        if let Some(permissions) = permissions {
            fs::set_permissions(&temporary, permissions).map_err(|error| {
                ApiError::Internal(format!("cannot preserve file permissions: {error}"))
            })?;
        }
        fs::rename(&temporary, file)
            .map_err(|error| ApiError::Internal(format!("cannot replace config file: {error}")))?;
        Ok(())
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temporary);
    }
    result
}

pub fn serialize_value(value: &LuaValue) -> Result<String, ApiError> {
    match value {
        LuaValue::Boolean { value } => Ok(value.to_string()),
        LuaValue::Number { value } => Ok(value.to_string()),
        LuaValue::String { value } => Ok(quote_string(value)),
        LuaValue::Array { values } => Ok(format!(
            "{{{}}}",
            values
                .iter()
                .map(serialize_value)
                .collect::<Result<Vec<_>, _>>()?
                .join(", ")
        )),
        LuaValue::Table { entries } => Ok(format!(
            "{{{}}}",
            entries
                .iter()
                .map(|entry| {
                    let key = if is_identifier(&entry.key) {
                        entry.key.clone()
                    } else {
                        format!("[{}]", quote_string(&entry.key))
                    };
                    Ok(format!("{key} = {}", serialize_value(&entry.value)?))
                })
                .collect::<Result<Vec<_>, ApiError>>()?
                .join(", ")
        )),
        LuaValue::Unsupported { .. } => Err(ApiError::BadRequest(
            "unsupported Lua source cannot be written".to_owned(),
        )),
    }
}

fn quote_string(value: &str) -> String {
    let mut output = String::from("\"");
    for character in value.chars() {
        match character {
            '\\' => output.push_str("\\\\"),
            '"' => output.push_str("\\\""),
            '\n' => output.push_str("\\n"),
            '\r' => output.push_str("\\r"),
            '\t' => output.push_str("\\t"),
            '\u{7}' => output.push_str("\\a"),
            '\u{8}' => output.push_str("\\b"),
            '\u{b}' => output.push_str("\\v"),
            '\u{c}' => output.push_str("\\f"),
            character if character.is_control() => {
                output.push_str(&format!("\\{:03}", character as u32));
            }
            character => output.push(character),
        }
    }
    output.push('"');
    output
}

pub fn serialize_vimscript_value(value: &LuaValue) -> Result<String, ApiError> {
    match value {
        LuaValue::Boolean { value: true } => Ok("v:true".to_owned()),
        LuaValue::Boolean { value: false } => Ok("v:false".to_owned()),
        LuaValue::Number { value } => Ok(value.to_string()),
        LuaValue::String { value } => {
            let escaped = value.replace('\'', "''");
            Ok(format!("'{escaped}'"))
        }
        LuaValue::Array { values } => {
            let items: Result<Vec<String>, ApiError> =
                values.iter().map(serialize_vimscript_value).collect();
            Ok(format!("[{}]", items?.join(", ")))
        }
        LuaValue::Table { entries } => {
            let items: Result<Vec<String>, ApiError> = entries
                .iter()
                .map(|e| {
                    let val = serialize_vimscript_value(&e.value)?;
                    let escaped_key = e.key.replace('\'', "''");
                    Ok(format!("'{escaped_key}': {val}"))
                })
                .collect();
            Ok(format!("{{{}}}", items?.join(", ")))
        }
        LuaValue::Unsupported { .. } => Err(ApiError::BadRequest(
            "unsupported value cannot be written to Vimscript".to_owned(),
        )),
    }
}

pub fn validate_vimscript(source: &str) -> Result<(), ApiError> {
    let mut braces = 0i32;
    let mut brackets = 0i32;
    let mut parens = 0i32;

    for line in source.lines() {
        let trimmed = line.trim_start();
        if trimmed.is_empty() || trimmed.starts_with('"') {
            continue;
        }

        let mut in_single_quote = false;
        let mut in_double_quote = false;
        let mut last_non_ws: Option<char> = None;
        let mut chars = line.char_indices().peekable();

        while let Some((byte_idx, ch)) = chars.next() {
            if in_single_quote {
                if ch == '\'' {
                    if chars.peek().map(|(_, next_ch)| *next_ch) == Some('\'') {
                        chars.next();
                    } else {
                        in_single_quote = false;
                        last_non_ws = Some('\'');
                    }
                }
            } else if in_double_quote {
                if ch == '\\' {
                    chars.next();
                } else if ch == '"' {
                    in_double_quote = false;
                    last_non_ws = Some('"');
                }
            } else {
                match ch {
                    '\'' => {
                        in_single_quote = true;
                    }
                    '"' => {
                        let prefix_trimmed = line[..byte_idx].trim();
                        let is_string_start = matches!(prefix_trimmed, "Plug" | "Plugin")
                            || matches!(
                                last_non_ws,
                                Some('=' | ':' | ',' | '(' | '[' | '{' | '.' | '?')
                            );
                        if is_string_start {
                            in_double_quote = true;
                        } else {
                            // Trailing inline Vimscript comment to end of line
                            break;
                        }
                    }
                    '{' => {
                        braces += 1;
                        last_non_ws = Some(ch);
                    }
                    '}' => {
                        braces -= 1;
                        last_non_ws = Some(ch);
                    }
                    '[' => {
                        brackets += 1;
                        last_non_ws = Some(ch);
                    }
                    ']' => {
                        brackets -= 1;
                        last_non_ws = Some(ch);
                    }
                    '(' => {
                        parens += 1;
                        last_non_ws = Some(ch);
                    }
                    ')' => {
                        parens -= 1;
                        last_non_ws = Some(ch);
                    }
                    _ => {
                        if !ch.is_whitespace() {
                            last_non_ws = Some(ch);
                        }
                    }
                }
                if braces < 0 || brackets < 0 || parens < 0 {
                    return Err(ApiError::Internal(
                        "refusing to save invalid patched Vimscript: unbalanced delimiters"
                            .to_owned(),
                    ));
                }
            }
        }

        if in_single_quote || in_double_quote {
            return Err(ApiError::Internal(
                "refusing to save invalid patched Vimscript: unclosed quotes or delimiters"
                    .to_owned(),
            ));
        }
    }

    if braces != 0 || brackets != 0 || parens != 0 {
        return Err(ApiError::Internal(
            "refusing to save invalid patched Vimscript: unclosed quotes or delimiters".to_owned(),
        ));
    }
    Ok(())
}

fn is_identifier(value: &str) -> bool {
    let mut chars = value.chars();
    chars
        .next()
        .is_some_and(|first| first == '_' || first.is_ascii_alphabetic())
        && chars.all(|character| character == '_' || character.is_ascii_alphanumeric())
        && !matches!(
            value,
            "and"
                | "break"
                | "do"
                | "else"
                | "elseif"
                | "end"
                | "false"
                | "for"
                | "function"
                | "goto"
                | "if"
                | "in"
                | "local"
                | "nil"
                | "not"
                | "or"
                | "repeat"
                | "return"
                | "then"
                | "true"
                | "until"
                | "while"
        )
}

fn contains_unsupported(value: Option<&LuaValue>) -> bool {
    match value {
        None
        | Some(LuaValue::Boolean { .. } | LuaValue::Number { .. } | LuaValue::String { .. }) => {
            false
        }
        Some(LuaValue::Unsupported { .. }) => true,
        Some(LuaValue::Array { values }) => {
            values.iter().any(|value| contains_unsupported(Some(value)))
        }
        Some(LuaValue::Table { entries }) => entries
            .iter()
            .any(|entry| contains_unsupported(Some(&entry.value))),
    }
}

pub fn keymap_field_id(prefix: &str, name: &str) -> String {
    stable_id(&format!("{prefix}:{name}"))
}

fn stable_id(value: &str) -> String {
    hex::encode(Sha256::digest(value.as_bytes()))
}

fn revision(bytes: &[u8]) -> String {
    hex::encode(Sha256::digest(bytes))
}

fn relative_path(root: &Path, file: &Path) -> String {
    file.strip_prefix(root)
        .unwrap_or(file)
        .to_string_lossy()
        .replace('\\', "/")
}

fn namespace_name(namespace: &SettingNamespace) -> &'static str {
    match namespace {
        SettingNamespace::Opt => "opt",
        SettingNamespace::G => "g",
        SettingNamespace::Env => "env",
    }
}
