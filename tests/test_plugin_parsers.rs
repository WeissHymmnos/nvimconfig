use std::fs;
use std::path::Path;
use ucdp_daemon::lua::{apply_patch, keymap_field_id, scan, serialize_value};
use ucdp_daemon::model::{LuaValue, PatchRequest, PluginManagerKind, TableEntry};

#[test]
fn test_serialize_values() {
    // Boolean
    let bool_val = LuaValue::Boolean { value: true };
    assert_eq!(serialize_value(&bool_val).unwrap(), "true");

    let bool_false = LuaValue::Boolean { value: false };
    assert_eq!(serialize_value(&bool_false).unwrap(), "false");

    // Number
    let num_val = LuaValue::Number {
        value: serde_json::Number::from(42),
    };
    assert_eq!(serialize_value(&num_val).unwrap(), "42");

    // String
    let str_val = LuaValue::String {
        value: "tokyonight".to_string(),
    };
    assert_eq!(serialize_value(&str_val).unwrap(), "\"tokyonight\"");

    // Array: formatted as {"a", "b"}
    let arr_val = LuaValue::Array {
        values: vec![
            LuaValue::String {
                value: "a".to_string(),
            },
            LuaValue::String {
                value: "b".to_string(),
            },
        ],
    };
    assert_eq!(serialize_value(&arr_val).unwrap(), "{\"a\", \"b\"}");

    // Table with identifier key
    let tbl_val = LuaValue::Table {
        entries: vec![TableEntry {
            key: "style".to_string(),
            value: LuaValue::String {
                value: "storm".to_string(),
            },
        }],
    };
    assert_eq!(serialize_value(&tbl_val).unwrap(), "{style = \"storm\"}");

    // Table with non-identifier key
    let tbl_non_ident = LuaValue::Table {
        entries: vec![TableEntry {
            key: "some-key".to_string(),
            value: LuaValue::Number {
                value: serde_json::Number::from(10),
            },
        }],
    };
    assert_eq!(
        serialize_value(&tbl_non_ident).unwrap(),
        "{[\"some-key\"] = 10}"
    );

    // Unsupported returns BadRequest error (cannot be written)
    let unsup_val = LuaValue::Unsupported {
        source: "function() require('foo').setup() end".to_string(),
    };
    assert!(serialize_value(&unsup_val).is_err());
}

#[test]
fn test_keymap_field_id_deterministic() {
    let id1 = keymap_field_id("keymap:init.lua:0", "lhs");
    let id2 = keymap_field_id("keymap:init.lua:0", "lhs");
    let id3 = keymap_field_id("keymap:init.lua:0", "rhs");
    assert_eq!(id1, id2);
    assert_ne!(id1, id3);
    assert!(!id1.is_empty());
}

#[test]
fn test_scan_hybrid_fixture() {
    let root = Path::new("tests/fixtures/hybrid");
    let result = scan(root);

    // Settings from init.lua
    let setting_names: Vec<&str> = result
        .snapshot
        .settings
        .iter()
        .map(|s| s.name.as_str())
        .collect();
    assert!(
        setting_names.contains(&"number"),
        "Should find 'number' option"
    );
    assert!(
        setting_names.contains(&"shiftwidth"),
        "Should find 'shiftwidth' option"
    );

    // Keymaps from init.lua
    assert!(
        !result.snapshot.keymaps.is_empty(),
        "Should find keymaps in init.lua"
    );

    // Plugins from lua/plugins/ui.lua
    let plugin_names: Vec<&str> = result
        .snapshot
        .plugins
        .iter()
        .map(|p| p.name.as_str())
        .collect();
    assert!(
        plugin_names.contains(&"tokyonight.nvim"),
        "Should parse tokyonight.nvim from table-of-tables spec"
    );
}

#[test]
fn test_scan_resilience_on_nonexistent_or_empty_path() {
    let non_existent = Path::new("tests/fixtures/non_existent_dir_12345");
    let result = scan(non_existent);
    assert!(result.snapshot.plugins.is_empty());
    assert!(result.snapshot.settings.is_empty());
    assert!(result.snapshot.keymaps.is_empty());
}

#[test]
fn test_scan_resilience_on_syntax_error() {
    let temp_dir = std::env::temp_dir().join(format!("nvimconfig_test_{}", std::process::id()));
    let plugins_dir = temp_dir.join("lua").join("plugins");
    fs::create_dir_all(&plugins_dir).unwrap();

    let broken_file = plugins_dir.join("broken.lua");
    fs::write(&broken_file, "return { broken syntax %%% !!!").unwrap();

    let result = scan(&temp_dir);
    // Should gracefully capture diagnostic rather than crashing
    assert!(
        !result.snapshot.diagnostics.is_empty(),
        "Expected syntax error diagnostic to be captured"
    );

    let _ = fs::remove_dir_all(&temp_dir);
}


#[test]
fn test_lazy_plugin_parsing() {
    let result = scan(Path::new("tests/fixtures/lazy"));
    let plugins = &result.snapshot.plugins;

    // Check telescope.nvim from single_spec.lua
    let telescope = plugins
        .iter()
        .find(|p| p.name == "telescope.nvim")
        .expect("telescope.nvim should be found");
    assert_eq!(telescope.manager, PluginManagerKind::Lazy);
    assert_eq!(telescope.source, "nvim-telescope/telescope.nvim");
    assert_eq!(telescope.enabled.value, Some(LuaValue::Boolean { value: true }));
    assert_eq!(
        telescope.tag.as_ref().and_then(|f| f.value.clone()),
        Some(LuaValue::String { value: "0.1.8".to_string() })
    );
    match &telescope.dependencies.as_ref().unwrap().value {
        Some(LuaValue::Array { values }) => {
            assert_eq!(values.len(), 1);
            assert_eq!(values[0], LuaValue::String { value: "nvim-lua/plenary.nvim".to_string() });
        }
        other => panic!("expected array dependencies, got {:?}", other),
    }

    // Check bare strings from bare_strings.lua
    let fugitive = plugins
        .iter()
        .find(|p| p.name == "vim-fugitive")
        .expect("vim-fugitive should be found");
    assert_eq!(fugitive.manager, PluginManagerKind::Lazy);
    assert_eq!(fugitive.source, "tpope/vim-fugitive");
    assert_eq!(fugitive.enabled.value, Some(LuaValue::Boolean { value: true }));

    let surround = plugins
        .iter()
        .find(|p| p.name == "vim-surround")
        .expect("vim-surround should be found");
    assert_eq!(surround.manager, PluginManagerKind::Lazy);
    assert_eq!(surround.source, "tpope/vim-surround");

    // Check complex lazy from complex_lazy.lua
    let which_key = plugins
        .iter()
        .find(|p| p.name == "which-key.nvim")
        .expect("which-key.nvim should be found");
    assert_eq!(which_key.manager, PluginManagerKind::Lazy);
    assert_eq!(
        which_key.event.value,
        Some(LuaValue::String { value: "VeryLazy".to_string() })
    );
    assert!(which_key.keys.value.is_some());
    assert!(which_key.opts.value.is_some());
    assert!(which_key.config.is_some());

    let mini_ai = plugins
        .iter()
        .find(|p| p.name == "mini.ai")
        .expect("mini.ai should be found");
    assert_eq!(mini_ai.manager, PluginManagerKind::Lazy);
    assert_eq!(
        mini_ai.event.value,
        Some(LuaValue::String { value: "VeryLazy".to_string() })
    );
    // Function opts is captured as Unsupported
    match &mini_ai.opts.value {
        Some(LuaValue::Unsupported { .. }) => {}
        other => panic!("expected Unsupported for function opts, got {:?}", other),
    }

    // Check table-of-tables from table_of_tables.lua
    let tokyonight = plugins
        .iter()
        .find(|p| p.name == "tokyonight.nvim")
        .expect("tokyonight.nvim should be found");
    assert_eq!(tokyonight.manager, PluginManagerKind::Lazy);
    assert_eq!(
        tokyonight.lazy.as_ref().and_then(|f| f.value.clone()),
        Some(LuaValue::Boolean { value: false })
    );

    let treesitter = plugins
        .iter()
        .find(|p| p.name == "nvim-treesitter")
        .expect("nvim-treesitter should be found");
    assert_eq!(treesitter.manager, PluginManagerKind::Lazy);
    assert_eq!(
        treesitter.build.as_ref().and_then(|f| f.value.clone()),
        Some(LuaValue::String { value: ":TSUpdate".to_string() })
    );
}

#[test]
fn test_packer_plugin_parsing() {
    let result = scan(Path::new("tests/fixtures/packer"));
    let plugins = &result.snapshot.plugins;

    // From packer_basic.lua
    let packer = plugins
        .iter()
        .find(|p| p.name == "packer.nvim")
        .expect("packer.nvim should be found");
    assert_eq!(packer.manager, PluginManagerKind::Packer);
    assert_eq!(packer.enabled.value, Some(LuaValue::Boolean { value: true }));

    let commentary = plugins
        .iter()
        .find(|p| p.name == "vim-commentary")
        .expect("vim-commentary should be found");
    assert_eq!(commentary.manager, PluginManagerKind::Packer);
    assert_eq!(commentary.source, "tpope/vim-commentary");

    // From packer_disabled.lua: disable = true should invert to enabled = false
    let markdown_preview = plugins
        .iter()
        .find(|p| p.name == "markdown-preview.nvim")
        .expect("markdown-preview.nvim should be found");
    assert_eq!(markdown_preview.manager, PluginManagerKind::Packer);
    assert_eq!(
        markdown_preview.enabled.value,
        Some(LuaValue::Boolean { value: false })
    );
    assert_eq!(
        markdown_preview.cmd.as_ref().and_then(|f| f.value.clone()),
        Some(LuaValue::String { value: "MarkdownPreview".to_string() })
    );
    assert_eq!(
        markdown_preview.build.as_ref().and_then(|f| f.value.clone()),
        Some(LuaValue::String { value: "cd app && yarn install".to_string() })
    );

    // From packer_startup.lua
    let lualine = plugins
        .iter()
        .find(|p| p.name == "lualine.nvim")
        .expect("lualine.nvim should be found");
    assert_eq!(lualine.manager, PluginManagerKind::Packer);
    assert!(lualine.dependencies.is_some());
    assert!(lualine.config.is_some());

    // From packer_table.lua
    let gitsigns = plugins
        .iter()
        .find(|p| p.name == "gitsigns.nvim")
        .expect("gitsigns.nvim should be found");
    assert_eq!(gitsigns.manager, PluginManagerKind::Packer);
    assert_eq!(
        gitsigns.branch.as_ref().and_then(|f| f.value.clone()),
        Some(LuaValue::String { value: "main".to_string() })
    );
    assert_eq!(
        gitsigns.lazy.as_ref().and_then(|f| f.value.clone()),
        Some(LuaValue::Boolean { value: true })
    );
    assert_eq!(
        gitsigns.event.value,
        Some(LuaValue::String { value: "BufRead".to_string() })
    );
}

#[test]
fn test_plug_plugin_parsing() {
    let result = scan(Path::new("tests/fixtures/plug"));
    let plugins = &result.snapshot.plugins;

    // Pure Vimscript init.vim
    let vim_go = plugins
        .iter()
        .find(|p| p.name == "vim-go" && p.tag.is_some())
        .expect("vim-go should be found");
    assert_eq!(vim_go.manager, PluginManagerKind::Plug);
    assert_eq!(
        vim_go.tag.as_ref().and_then(|f| f.value.clone()),
        Some(LuaValue::String { value: "*".to_string() })
    );

    let coc = plugins
        .iter()
        .find(|p| p.name == "coc.nvim")
        .expect("coc.nvim should be found");
    assert_eq!(coc.manager, PluginManagerKind::Plug);
    assert_eq!(
        coc.branch.as_ref().and_then(|f| f.value.clone()),
        Some(LuaValue::String { value: "release".to_string() })
    );

    let nerdtree = plugins
        .iter()
        .find(|p| p.name == "nerdtree")
        .expect("nerdtree should be found");
    assert_eq!(nerdtree.manager, PluginManagerKind::Plug);
    assert_eq!(
        nerdtree.cmd.as_ref().and_then(|f| f.value.clone()),
        Some(LuaValue::String { value: "NERDTreeToggle".to_string() })
    );

    let fireplace = plugins
        .iter()
        .find(|p| p.name == "vim-fireplace")
        .expect("vim-fireplace should be found");
    assert_eq!(fireplace.manager, PluginManagerKind::Plug);
    assert_eq!(
        fireplace.ft.as_ref().and_then(|f| f.value.clone()),
        Some(LuaValue::String { value: "clojure".to_string() })
    );

    let fzf = plugins
        .iter()
        .find(|p| p.name == "fzf")
        .expect("fzf should be found");
    assert_eq!(fzf.manager, PluginManagerKind::Plug);
    assert_eq!(
        fzf.build.as_ref().and_then(|f| f.value.clone()),
        Some(LuaValue::String { value: "./install --all".to_string() })
    );

    // Pure Vimscript complex: plug_complex.vim
    let paredit = plugins
        .iter()
        .find(|p| p.name == "paredit")
        .expect("paredit should be found");
    assert_eq!(paredit.manager, PluginManagerKind::Plug);
    match &paredit.ft.as_ref().unwrap().value {
        Some(LuaValue::Array { values }) => {
            assert_eq!(values.len(), 2);
            assert_eq!(values[0], LuaValue::String { value: "clojure".to_string() });
            assert_eq!(values[1], LuaValue::String { value: "scheme".to_string() });
        }
        other => panic!("expected array ft, got {:?}", other),
    }

    let ycm = plugins
        .iter()
        .find(|p| p.name == "YouCompleteMe")
        .expect("YouCompleteMe should be found");
    assert_eq!(ycm.manager, PluginManagerKind::Plug);
    assert_eq!(
        ycm.build.as_ref().and_then(|f| f.value.clone()),
        Some(LuaValue::String { value: "./install.py".to_string() })
    );

    // Embedded in Lua: plug_embedded.lua
    let fugitive = plugins
        .iter()
        .find(|p| p.name == "vim-fugitive" && p.manager == PluginManagerKind::Plug)
        .expect("vim-fugitive in embedded vim.cmd should be found");
    assert_eq!(fugitive.manager, PluginManagerKind::Plug);

    let gv = plugins
        .iter()
        .find(|p| p.name == "gv.vim")
        .expect("gv.vim in embedded vim.cmd should be found");
    assert_eq!(gv.manager, PluginManagerKind::Plug);

    // Lua fn call: plug_lua.lua
    let seoul = plugins
        .iter()
        .find(|p| p.name == "seoul256.vim")
        .expect("seoul256.vim should be found");
    assert_eq!(seoul.manager, PluginManagerKind::Plug);

    let prototype = plugins
        .iter()
        .find(|p| p.name == "my-prototype-plugin")
        .expect("my-prototype-plugin should be found");
    assert_eq!(prototype.manager, PluginManagerKind::Plug);
}

#[test]
fn test_roundtrip_lazy_patching() {
    let temp_dir = std::env::temp_dir().join(format!("lazy_patch_test_{}", std::process::id()));
    fs::create_dir_all(&temp_dir).unwrap();
    let temp_root = temp_dir.canonicalize().unwrap();

    let fixture_content = fs::read_to_string("tests/fixtures/lazy/single_spec.lua").unwrap();
    let target_file = temp_root.join("single_spec.lua");
    fs::write(&target_file, fixture_content).unwrap();

    let initial = scan(&temp_root);
    let telescope = initial
        .snapshot
        .plugins
        .iter()
        .find(|p| p.name == "telescope.nvim")
        .expect("telescope.nvim should be found");
    assert_eq!(telescope.enabled.value, Some(LuaValue::Boolean { value: true }));

    // Patch enabled to false
    let patch_req = PatchRequest {
        id: telescope.enabled.id.clone(),
        file: telescope.enabled.file.clone(),
        revision: telescope.enabled.revision.clone(),
        value: LuaValue::Boolean { value: false },
    };

    let patch_res = apply_patch(&temp_root, &patch_req);
    assert!(patch_res.is_ok(), "apply_patch should succeed: {:?}", patch_res.err());

    let rescanned = scan(&temp_root);
    let rescanned_telescope = rescanned
        .snapshot
        .plugins
        .iter()
        .find(|p| p.name == "telescope.nvim")
        .expect("telescope.nvim should still be found");
    assert_eq!(
        rescanned_telescope.enabled.value,
        Some(LuaValue::Boolean { value: false })
    );

    let _ = fs::remove_dir_all(&temp_dir);
}


#[test]
fn test_roundtrip_packer_disable_inversion_patching() {
    let temp_dir = std::env::temp_dir().join(format!("packer_patch_test_{}", std::process::id()));
    fs::create_dir_all(&temp_dir).unwrap();
    let temp_root = temp_dir.canonicalize().unwrap();

    let fixture_content = fs::read_to_string("tests/fixtures/packer/packer_disabled.lua").unwrap();
    let target_file = temp_root.join("packer_disabled.lua");
    fs::write(&target_file, fixture_content).unwrap();

    let initial = scan(&temp_root);
    let mp = initial
        .snapshot
        .plugins
        .iter()
        .find(|p| p.name == "markdown-preview.nvim")
        .expect("markdown-preview.nvim should be found");
    // Initially disabled (disable = true) -> enabled is false
    assert_eq!(mp.enabled.value, Some(LuaValue::Boolean { value: false }));

    // Patch enabled = true
    let patch_enable = PatchRequest {
        id: mp.enabled.id.clone(),
        file: mp.enabled.file.clone(),
        revision: mp.enabled.revision.clone(),
        value: LuaValue::Boolean { value: true },
    };
    let res = apply_patch(&temp_root, &patch_enable);
    assert!(res.is_ok(), "apply_patch to enable packer plugin should succeed");

    // Check code in file now has disable = false
    let content = fs::read_to_string(&target_file).unwrap();
    assert!(
        content.contains("disable = false"),
        "Content should have disable = false, got:\n{}",
        content
    );

    // Rescan confirms enabled is true
    let rescanned = scan(&temp_root);
    let mp_enabled = rescanned
        .snapshot
        .plugins
        .iter()
        .find(|p| p.name == "markdown-preview.nvim")
        .unwrap();
    assert_eq!(mp_enabled.enabled.value, Some(LuaValue::Boolean { value: true }));

    // Patch back to enabled = false
    let patch_disable = PatchRequest {
        id: mp_enabled.enabled.id.clone(),
        file: mp_enabled.enabled.file.clone(),
        revision: mp_enabled.enabled.revision.clone(),
        value: LuaValue::Boolean { value: false },
    };
    let res2 = apply_patch(&temp_root, &patch_disable);
    assert!(res2.is_ok(), "apply_patch to disable packer plugin should succeed");

    let content2 = fs::read_to_string(&target_file).unwrap();
    assert!(
        content2.contains("disable = true"),
        "Content should have disable = true, got:\n{}",
        content2
    );

    let rescanned2 = scan(&temp_root);
    let mp_disabled = rescanned2
        .snapshot
        .plugins
        .iter()
        .find(|p| p.name == "markdown-preview.nvim")
        .unwrap();
    assert_eq!(mp_disabled.enabled.value, Some(LuaValue::Boolean { value: false }));

    let _ = fs::remove_dir_all(&temp_dir);
}


#[test]
fn test_roundtrip_vimscript_patching() {
    let temp_dir = std::env::temp_dir().join(format!("plug_patch_test_{}", std::process::id()));
    fs::create_dir_all(&temp_dir).unwrap();
    let temp_root = temp_dir.canonicalize().unwrap();

    let fixture_content = fs::read_to_string("tests/fixtures/plug/init.vim").unwrap();
    let target_file = temp_root.join("init.vim");
    fs::write(&target_file, fixture_content).unwrap();

    let initial = scan(&temp_root);
    let vim_go = initial
        .snapshot
        .plugins
        .iter()
        .find(|p| p.name == "vim-go")
        .expect("vim-go should be found");
    let tag_field = vim_go.tag.as_ref().expect("tag field should exist");
    assert_eq!(tag_field.value, Some(LuaValue::String { value: "*".to_string() }));

    // Patch tag to "v1.28"
    let patch_tag = PatchRequest {
        id: tag_field.id.clone(),
        file: tag_field.file.clone(),
        revision: tag_field.revision.clone(),
        value: LuaValue::String { value: "v1.28".to_string() },
    };
    let res = apply_patch(&temp_root, &patch_tag);
    assert!(res.is_ok(), "apply_patch on vimscript tag should succeed: {:?}", res.err());

    let content = fs::read_to_string(&target_file).unwrap();
    assert!(
        content.contains("'tag': 'v1.28'"),
        "Content should have updated tag, got:\n{}",
        content
    );

    let rescanned = scan(&temp_root);
    let rescanned_vim_go = rescanned
        .snapshot
        .plugins
        .iter()
        .find(|p| p.name == "vim-go")
        .unwrap();
    assert_eq!(
        rescanned_vim_go.tag.as_ref().and_then(|f| f.value.clone()),
        Some(LuaValue::String { value: "v1.28".to_string() })
    );

    let _ = fs::remove_dir_all(&temp_dir);
}

#[test]
fn test_dual_layer_state_and_setup_opts_patching() {
    use ucdp_daemon::lua::load_state_file;

    let temp_dir = std::env::temp_dir().join(format!("dual_layer_test_{}", std::process::id()));
    let _ = fs::remove_dir_all(&temp_dir);
    let plugins_dir = temp_dir.join("lua").join("plugins");
    fs::create_dir_all(&plugins_dir).unwrap();
    let temp_root = temp_dir.canonicalize().unwrap();

    let autopair_file = plugins_dir.join("autopair.lua");
    fs::write(
        &autopair_file,
        r#"return {
    "windwp/nvim-autopairs",
    event = "InsertEnter",
    config = function()
        require("nvim-autopairs").setup({
            check_ts = true,
        })
    end,
}
"#,
    )
    .unwrap();

    let initial = scan(&temp_root);
    let ap = initial
        .snapshot
        .plugins
        .iter()
        .find(|p| p.name == "nvim-autopairs")
        .expect("nvim-autopairs should be found");

    // Verify `.setup({ check_ts = true })` inside `config = function() ... end` is lifted into `opts`
    assert_eq!(
        ap.opts.value,
        Some(LuaValue::Table {
            entries: vec![TableEntry {
                key: "check_ts".to_string(),
                value: LuaValue::Boolean { value: true },
            }],
        })
    );

    // Patch `opts` to update `check_ts = false` and add `map_cr = true`
    let patch_opts = PatchRequest {
        id: ap.opts.id.clone(),
        file: ap.opts.file.clone(),
        revision: ap.opts.revision.clone(),
        value: LuaValue::Table {
            entries: vec![
                TableEntry {
                    key: "check_ts".to_string(),
                    value: LuaValue::Boolean { value: false },
                },
                TableEntry {
                    key: "map_cr".to_string(),
                    value: LuaValue::Boolean { value: true },
                },
            ],
        },
    };
    let res = apply_patch(&temp_root, &patch_opts).expect("patching setup opts should succeed");

    // Verify `.ucdp/state.json` was automatically generated and synced
    let state_file = load_state_file(&temp_root).expect(".ucdp/state.json should exist");
    assert_eq!(state_file.version, 1);
    assert_eq!(state_file.plugins.len(), 1);
    let updated_ap = &res.scan.snapshot.plugins[0];

    // Patch an unset slot (`lazy`) via `plugin_slot:nvim-autopairs:lazy`
    let patch_lazy = PatchRequest {
        id: "plugin_slot:nvim-autopairs:lazy".to_string(),
        file: updated_ap.enabled.file.clone(),
        revision: updated_ap.enabled.revision.clone(),
        value: LuaValue::Boolean { value: true },
    };
    let res2 = apply_patch(&temp_root, &patch_lazy).expect("patching unset lazy slot should succeed");
    assert_eq!(
        res2.scan.snapshot.plugins[0]
            .lazy
            .as_ref()
            .and_then(|f| f.value.clone()),
        Some(LuaValue::Boolean { value: true })
    );

    let lua_text = fs::read_to_string(&autopair_file).unwrap();
    assert!(lua_text.contains("check_ts = false"));
    assert!(lua_text.contains("map_cr = true"));
    assert!(lua_text.contains("lazy = true"));

    let _ = fs::remove_dir_all(&temp_dir);
}



