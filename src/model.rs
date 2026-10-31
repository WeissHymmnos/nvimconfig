use serde::{Deserialize, Serialize};
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum LuaValue {
    Boolean { value: bool },
    Number { value: serde_json::Number },
    String { value: String },
    Array { values: Vec<LuaValue> },
    Table { entries: Vec<TableEntry> },
    Unsupported { source: String },
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct TableEntry {
    pub key: String,
    pub value: LuaValue,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct Field {
    pub id: String,
    pub file: String,
    pub revision: String,
    pub line: Option<u64>,
    pub value: Option<LuaValue>,
}

impl Field {
    pub fn new(
        id: impl Into<String>,
        file: impl Into<String>,
        revision: impl Into<String>,
        line: Option<u64>,
        value: Option<LuaValue>,
    ) -> Self {
        Self {
            id: id.into(),
            file: file.into(),
            revision: revision.into(),
            line,
            value,
        }
    }

    pub fn with_value(
        id: impl Into<String>,
        file: impl Into<String>,
        revision: impl Into<String>,
        value: LuaValue,
    ) -> Self {
        Self::new(id, file, revision, None, Some(value))
    }

    pub fn placeholder(
        id: impl Into<String>,
        file: impl Into<String>,
        revision: impl Into<String>,
    ) -> Self {
        Self::new(id, file, revision, None, None)
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SettingNamespace {
    Opt,
    G,
    Env,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Setting {
    pub namespace: SettingNamespace,
    pub name: String,
    pub field: Field,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Keymap {
    pub mode: Field,
    pub lhs: Field,
    pub rhs: Field,
    pub opts: Field,
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PluginManagerKind {
    #[default]
    Lazy,
    Packer,
    #[serde(alias = "vim-plug", alias = "vim_plug")]
    Plug,
}

impl PluginManagerKind {
    pub const fn as_str(&self) -> &'static str {
        match self {
            Self::Lazy => "lazy",
            Self::Packer => "packer",
            Self::Plug => "plug",
        }
    }

    pub const fn display_name(&self) -> &'static str {
        match self {
            Self::Lazy => "lazy.nvim",
            Self::Packer => "packer.nvim",
            Self::Plug => "vim-plug",
        }
    }

    pub const fn badge_color(&self) -> &'static str {
        match self {
            Self::Lazy => "#bb9af7",
            Self::Packer => "#ff9e3b",
            Self::Plug => "#9ece6a",
        }
    }

    pub const fn is_lazy(&self) -> bool {
        matches!(self, Self::Lazy)
    }

    pub const fn is_packer(&self) -> bool {
        matches!(self, Self::Packer)
    }

    pub const fn is_plug(&self) -> bool {
        matches!(self, Self::Plug)
    }
}

impl std::fmt::Display for PluginManagerKind {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.as_str())
    }
}

impl std::str::FromStr for PluginManagerKind {
    type Err = String;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s.trim().to_ascii_lowercase().as_str() {
            "lazy" | "lazy.nvim" => Ok(Self::Lazy),
            "packer" | "packer.nvim" => Ok(Self::Packer),
            "plug" | "vim-plug" | "vim_plug" => Ok(Self::Plug),
            other => Err(format!(
                "unknown plugin manager '{other}', expected 'lazy', 'packer', or 'plug'"
            )),
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct Plugin {
    pub name: String,
    pub source: String,
    #[serde(default)]
    pub manager: PluginManagerKind,
    pub enabled: Field,
    pub event: Field,
    pub keys: Field,
    pub opts: Field,

    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub lazy: Option<Field>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub cmd: Option<Field>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub ft: Option<Field>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub dependencies: Option<Field>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub branch: Option<Field>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub tag: Option<Field>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub commit: Option<Field>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub version: Option<Field>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub pin: Option<Field>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub build: Option<Field>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub config: Option<Field>,
}

impl Plugin {
    pub const CORE_SLOTS: &'static [&'static str] = &["enabled", "event", "keys", "opts"];

    pub const EXTENDED_SLOTS: &'static [&'static str] = &[
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
        "config",
    ];

    pub const ALL_SLOTS: &'static [&'static str] = &[
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
        "config",
    ];

    pub fn new(
        name: impl Into<String>,
        source: impl Into<String>,
        manager: PluginManagerKind,
        enabled: Field,
        event: Field,
        keys: Field,
        opts: Field,
    ) -> Self {
        Self {
            name: name.into(),
            source: source.into(),
            manager,
            enabled,
            event,
            keys,
            opts,
            lazy: None,
            cmd: None,
            ft: None,
            dependencies: None,
            branch: None,
            tag: None,
            commit: None,
            version: None,
            pin: None,
            build: None,
            config: None,
        }
    }

    pub fn new_lazy(
        name: impl Into<String>,
        source: impl Into<String>,
        enabled: Field,
        event: Field,
        keys: Field,
        opts: Field,
    ) -> Self {
        Self::new(name, source, PluginManagerKind::Lazy, enabled, event, keys, opts)
    }

    pub fn new_packer(
        name: impl Into<String>,
        source: impl Into<String>,
        enabled: Field,
        event: Field,
        keys: Field,
        opts: Field,
    ) -> Self {
        Self::new(name, source, PluginManagerKind::Packer, enabled, event, keys, opts)
    }

    pub fn new_plug(
        name: impl Into<String>,
        source: impl Into<String>,
        enabled: Field,
        event: Field,
        keys: Field,
        opts: Field,
    ) -> Self {
        Self::new(name, source, PluginManagerKind::Plug, enabled, event, keys, opts)
    }

    pub fn with_lazy(mut self, field: Field) -> Self {
        self.lazy = Some(field);
        self
    }

    pub fn with_cmd(mut self, field: Field) -> Self {
        self.cmd = Some(field);
        self
    }

    pub fn with_ft(mut self, field: Field) -> Self {
        self.ft = Some(field);
        self
    }

    pub fn with_dependencies(mut self, field: Field) -> Self {
        self.dependencies = Some(field);
        self
    }

    pub fn with_branch(mut self, field: Field) -> Self {
        self.branch = Some(field);
        self
    }

    pub fn with_tag(mut self, field: Field) -> Self {
        self.tag = Some(field);
        self
    }

    pub fn with_commit(mut self, field: Field) -> Self {
        self.commit = Some(field);
        self
    }

    pub fn with_version(mut self, field: Field) -> Self {
        self.version = Some(field);
        self
    }

    pub fn with_pin(mut self, field: Field) -> Self {
        self.pin = Some(field);
        self
    }

    pub fn with_build(mut self, field: Field) -> Self {
        self.build = Some(field);
        self
    }

    pub fn with_config(mut self, field: Field) -> Self {
        self.config = Some(field);
        self
    }

    pub fn get_field(&self, name: &str) -> Option<&Field> {
        match name {
            "enabled" => Some(&self.enabled),
            "event" => Some(&self.event),
            "keys" => Some(&self.keys),
            "opts" => Some(&self.opts),
            "lazy" => self.lazy.as_ref(),
            "cmd" => self.cmd.as_ref(),
            "ft" => self.ft.as_ref(),
            "dependencies" => self.dependencies.as_ref(),
            "branch" => self.branch.as_ref(),
            "tag" => self.tag.as_ref(),
            "commit" => self.commit.as_ref(),
            "version" => self.version.as_ref(),
            "pin" => self.pin.as_ref(),
            "build" => self.build.as_ref(),
            "config" => self.config.as_ref(),
            _ => None,
        }
    }

    pub fn get_field_mut(&mut self, name: &str) -> Option<&mut Field> {
        match name {
            "enabled" => Some(&mut self.enabled),
            "event" => Some(&mut self.event),
            "keys" => Some(&mut self.keys),
            "opts" => Some(&mut self.opts),
            "lazy" => self.lazy.as_mut(),
            "cmd" => self.cmd.as_mut(),
            "ft" => self.ft.as_mut(),
            "dependencies" => self.dependencies.as_mut(),
            "branch" => self.branch.as_mut(),
            "tag" => self.tag.as_mut(),
            "commit" => self.commit.as_mut(),
            "version" => self.version.as_mut(),
            "pin" => self.pin.as_mut(),
            "build" => self.build.as_mut(),
            "config" => self.config.as_mut(),
            _ => None,
        }
    }

    pub fn all_fields(&self) -> Vec<(&'static str, &Field)> {
        let mut list = vec![
            ("enabled", &self.enabled),
            ("event", &self.event),
            ("keys", &self.keys),
            ("opts", &self.opts),
        ];
        if let Some(f) = &self.lazy {
            list.push(("lazy", f));
        }
        if let Some(f) = &self.cmd {
            list.push(("cmd", f));
        }
        if let Some(f) = &self.ft {
            list.push(("ft", f));
        }
        if let Some(f) = &self.dependencies {
            list.push(("dependencies", f));
        }
        if let Some(f) = &self.branch {
            list.push(("branch", f));
        }
        if let Some(f) = &self.tag {
            list.push(("tag", f));
        }
        if let Some(f) = &self.commit {
            list.push(("commit", f));
        }
        if let Some(f) = &self.version {
            list.push(("version", f));
        }
        if let Some(f) = &self.pin {
            list.push(("pin", f));
        }
        if let Some(f) = &self.build {
            list.push(("build", f));
        }
        if let Some(f) = &self.config {
            list.push(("config", f));
        }
        list
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Diagnostic {
    pub file: String,
    pub line: Option<u64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub column: Option<u64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub severity: Option<String>,
    pub message: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Snapshot {
    pub config_root: String,
    pub settings: Vec<Setting>,
    pub keymaps: Vec<Keymap>,
    pub plugins: Vec<Plugin>,
    pub diagnostics: Vec<Diagnostic>,
}

impl Snapshot {
    pub fn empty(config_root: String) -> Self {
        Self {
            config_root,
            settings: Vec::new(),
            keymaps: Vec::new(),
            plugins: Vec::new(),
            diagnostics: Vec::new(),
        }
    }
}

#[derive(Clone, Debug, Serialize)]
pub struct NvimStatus {
    pub connected: bool,
    pub address: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct StateResponse {
    pub snapshot: Snapshot,
    pub nvim: NvimStatus,
}

#[derive(Clone, Debug, Deserialize)]
pub struct PatchRequest {
    pub id: String,
    pub file: String,
    pub revision: String,
    pub value: LuaValue,
}

#[derive(Clone, Debug, Deserialize)]
pub struct BatchPatchItem {
    pub id: String,
    #[serde(default)]
    pub file: Option<String>,
    #[serde(default)]
    pub revision: Option<String>,
    pub value: LuaValue,
}

#[derive(Clone, Debug, Default, Deserialize)]
pub struct BatchPatchRequest {
    #[serde(default)]
    pub file: Option<String>,
    #[serde(default)]
    pub revision: Option<String>,
    #[serde(default, alias = "items", alias = "updates")]
    pub patches: Vec<BatchPatchItem>,
}

#[derive(Debug, Deserialize)]
pub struct AddOptionRequest {
    pub name: String,
    pub value: LuaValue,
}

fn default_keymap_opts() -> LuaValue {
    LuaValue::Table {
        entries: Vec::new(),
    }
}

#[derive(Debug, Deserialize)]
pub struct AddKeymapRequest {
    pub mode: LuaValue,
    pub lhs: LuaValue,
    pub rhs: LuaValue,
    #[serde(default = "default_keymap_opts")]
    pub opts: LuaValue,
}

#[derive(Debug, Deserialize)]
pub struct AddPluginRequest {
    pub source: String,
    #[serde(default)]
    pub manager: Option<PluginManagerKind>,
    #[serde(default)]
    pub enabled: Option<bool>,
    #[serde(default)]
    pub lazy: Option<bool>,
    #[serde(default)]
    pub event: Option<LuaValue>,
    #[serde(default)]
    pub cmd: Option<LuaValue>,
    #[serde(default)]
    pub ft: Option<LuaValue>,
    #[serde(default)]
    pub branch: Option<String>,
    #[serde(default)]
    pub tag: Option<String>,
    #[serde(default)]
    pub build: Option<String>,
    #[serde(default)]
    pub opts: Option<LuaValue>,
}

#[derive(Debug, Default, Deserialize)]
pub struct DeleteEntityRequest {
    pub id: String,
    #[serde(default)]
    pub file: Option<String>,
    #[serde(default, alias = "expected_revision")]
    pub revision: Option<String>,
}

#[derive(Debug, Default, Deserialize)]
pub struct RollbackRequest {
    #[serde(default, alias = "file_path")]
    pub file: Option<String>,
    #[serde(default)]
    pub target_revision: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct RuntimeStatus {
    pub applied: bool,
    pub message: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct PatchResponse {
    pub disk_saved: bool,
    pub runtime: RuntimeStatus,
}

#[derive(Clone, Debug, Serialize)]
pub struct ChangeEvent {
    pub reason: String,
}

#[derive(Debug, thiserror::Error)]
pub enum ApiError {
    #[error("{0}")]
    BadRequest(String),
    #[error("{0}")]
    Conflict(String),
    #[error("{0}")]
    NotFound(String),
    #[error("{0}")]
    Internal(String),
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::str::FromStr;

    fn sample_field(name: &str) -> Field {
        Field::with_value(
            format!("field_{name}_id"),
            "/path/to/config.lua",
            "rev_123",
            LuaValue::String {
                value: name.to_string(),
            },
        )
    }

    #[test]
    fn test_plugin_manager_kind_serde() {
        assert_eq!(serde_json::to_string(&PluginManagerKind::Lazy).unwrap(), "\"lazy\"");
        assert_eq!(serde_json::to_string(&PluginManagerKind::Packer).unwrap(), "\"packer\"");
        assert_eq!(serde_json::to_string(&PluginManagerKind::Plug).unwrap(), "\"plug\"");

        assert_eq!(serde_json::from_str::<PluginManagerKind>("\"lazy\"").unwrap(), PluginManagerKind::Lazy);
        assert_eq!(serde_json::from_str::<PluginManagerKind>("\"packer\"").unwrap(), PluginManagerKind::Packer);
        assert_eq!(serde_json::from_str::<PluginManagerKind>("\"plug\"").unwrap(), PluginManagerKind::Plug);
        // Alias tests
        assert_eq!(serde_json::from_str::<PluginManagerKind>("\"vim-plug\"").unwrap(), PluginManagerKind::Plug);
        assert_eq!(serde_json::from_str::<PluginManagerKind>("\"vim_plug\"").unwrap(), PluginManagerKind::Plug);
    }

    #[test]
    fn test_plugin_manager_kind_methods() {
        assert_eq!(PluginManagerKind::Lazy.as_str(), "lazy");
        assert_eq!(PluginManagerKind::Lazy.display_name(), "lazy.nvim");
        assert_eq!(PluginManagerKind::Lazy.badge_color(), "#bb9af7");
        assert!(PluginManagerKind::Lazy.is_lazy());
        assert!(!PluginManagerKind::Lazy.is_packer());

        assert_eq!(PluginManagerKind::Packer.as_str(), "packer");
        assert_eq!(PluginManagerKind::Packer.display_name(), "packer.nvim");
        assert_eq!(PluginManagerKind::Packer.badge_color(), "#ff9e3b");
        assert!(PluginManagerKind::Packer.is_packer());

        assert_eq!(PluginManagerKind::Plug.as_str(), "plug");
        assert_eq!(PluginManagerKind::Plug.display_name(), "vim-plug");
        assert_eq!(PluginManagerKind::Plug.badge_color(), "#9ece6a");
        assert!(PluginManagerKind::Plug.is_plug());

        assert_eq!(format!("{}", PluginManagerKind::Lazy), "lazy");
        assert_eq!(PluginManagerKind::from_str("lazy.nvim").unwrap(), PluginManagerKind::Lazy);
        assert_eq!(PluginManagerKind::from_str("vim-plug").unwrap(), PluginManagerKind::Plug);
        assert_eq!(PluginManagerKind::from_str("Packer").unwrap(), PluginManagerKind::Packer);
    }

    #[test]
    fn test_backward_compatibility_deserialization() {
        // Old JSON without "manager" and without extended fields
        let old_json = r#"{
            "name": "telescope.nvim",
            "source": "nvim-telescope/telescope.nvim",
            "enabled": { "id": "1", "file": "f", "revision": "r", "line": 1, "value": { "kind": "boolean", "value": true } },
            "event": { "id": "2", "file": "f", "revision": "r", "line": 2, "value": null },
            "keys": { "id": "3", "file": "f", "revision": "r", "line": 3, "value": null },
            "opts": { "id": "4", "file": "f", "revision": "r", "line": 4, "value": null }
        }"#;

        let plugin: Plugin = serde_json::from_str(old_json).unwrap();
        assert_eq!(plugin.name, "telescope.nvim");
        assert_eq!(plugin.manager, PluginManagerKind::Lazy); // Defaults to Lazy
        assert!(plugin.lazy.is_none());
        assert!(plugin.branch.is_none());
        assert!(plugin.tag.is_none());
        assert!(plugin.dependencies.is_none());
    }

    #[test]
    fn test_full_plugin_serialization_and_deserialization() {
        let mut plugin = Plugin::new(
            "nvim-treesitter",
            "nvim-treesitter/nvim-treesitter",
            PluginManagerKind::Packer,
            sample_field("enabled"),
            sample_field("event"),
            sample_field("keys"),
            sample_field("opts"),
        );
        plugin = plugin
            .with_lazy(sample_field("lazy"))
            .with_cmd(sample_field("cmd"))
            .with_ft(sample_field("ft"))
            .with_dependencies(sample_field("dependencies"))
            .with_branch(sample_field("branch"))
            .with_tag(sample_field("tag"))
            .with_commit(sample_field("commit"))
            .with_version(sample_field("version"))
            .with_pin(sample_field("pin"))
            .with_build(sample_field("build"))
            .with_config(sample_field("config"));

        let json = serde_json::to_string(&plugin).unwrap();
        assert!(json.contains("\"manager\":\"packer\""));
        assert!(json.contains("\"lazy\":"));
        assert!(json.contains("\"build\":"));
        assert!(json.contains("\"config\":"));

        let deserialized: Plugin = serde_json::from_str(&json).unwrap();
        assert_eq!(deserialized, plugin);
        assert_eq!(deserialized.all_fields().len(), 15);
    }

    #[test]
    fn test_skip_serializing_none_fields() {
        let plugin = Plugin::new_plug(
            "vim-fugitive",
            "tpope/vim-fugitive",
            sample_field("enabled"),
            sample_field("event"),
            sample_field("keys"),
            sample_field("opts"),
        );

        let json = serde_json::to_string(&plugin).unwrap();
        assert!(json.contains("\"manager\":\"plug\""));
        assert!(!json.contains("\"lazy\""));
        assert!(!json.contains("\"branch\""));
        assert!(!json.contains("\"tag\""));
        assert!(!json.contains("\"build\""));
    }

    #[test]
    fn test_field_accessors() {
        let mut plugin = Plugin::new_lazy(
            "tokyonight",
            "folke/tokyonight.nvim",
            sample_field("enabled"),
            sample_field("event"),
            sample_field("keys"),
            sample_field("opts"),
        )
        .with_branch(sample_field("branch"));

        assert!(plugin.get_field("enabled").is_some());
        assert!(plugin.get_field("branch").is_some());
        assert!(plugin.get_field("tag").is_none());

        if let Some(branch_field) = plugin.get_field_mut("branch") {
            branch_field.id = "modified_id".to_string();
        }
        assert_eq!(plugin.branch.as_ref().unwrap().id, "modified_id");
    }
}
