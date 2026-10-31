use std::fs;
use std::panic::{self, AssertUnwindSafe};
use std::path::PathBuf;
use ucdp_daemon::lua::{apply_patch, scan};
use ucdp_daemon::model::{ApiError, LuaValue, PatchRequest};

fn create_temp_workspace(prefix: &str) -> (PathBuf, PathBuf) {
    let mut rng_bytes = [0u8; 8];
    rand::RngCore::fill_bytes(&mut rand::thread_rng(), &mut rng_bytes);
    let temp_dir = std::env::temp_dir().join(format!("{}_{}", prefix, hex::encode(rng_bytes)));
    fs::create_dir_all(&temp_dir).unwrap();
    let canonical = temp_dir.canonicalize().unwrap();
    (temp_dir, canonical)
}

// =========================================================================
// Category 1: Vimscript Parsing Edge Cases & Stress Tests
// =========================================================================

#[test]
fn test_adversarial_vimscript_trailing_whitespace_subtraction_overflow() {
    // Stress test: Vimscript line with trailing spaces or CRLF after options dict.
    // Line 1686-1690 calculates:
    // dict_rel_in_cmd = cmd_offset + (cmd.len() - cmd.trim_start().len()) + (cmd_trimmed.len() - trimmed_dict.len())
    // If line has trailing whitespace, cmd_trimmed strips it, but trimmed_dict (from after_comma.trim_start()) does not.
    // If trailing whitespace > length before dict, cmd_trimmed.len() < trimmed_dict.len(), causing an underflow panic!
    let (temp_dir, temp_root) = create_temp_workspace("adv_vim_overflow");

    let vim_file = temp_root.join("overflow.vim");
    // 50 trailing spaces after options dict
    let content = "call plug#begin()\nPlug 'user/repo', {'tag': 'v1.0'}                                                  \ncall plug#end()\n";
    fs::write(&vim_file, content).unwrap();

    let result = panic::catch_unwind(AssertUnwindSafe(|| {
        scan(&temp_root)
    }));

    if let Err(panic_payload) = result {
        let panic_msg = if let Some(s) = panic_payload.downcast_ref::<&str>() {
            s.to_string()
        } else if let Some(s) = panic_payload.downcast_ref::<String>() {
            s.clone()
        } else {
            "Unknown panic payload".to_string()
        };
        eprintln!("CONFIRMED BUG: Daemon panics on Vimscript trailing whitespace: {}", panic_msg);
        let _ = fs::remove_dir_all(&temp_dir);
        panic!("VIM_OVERFLOW_PANIC_REPRODUCED: attempt to subtract with overflow in scan_vimscript_text: {}", panic_msg);
    } else {
        println!("Trailing whitespace test passed without panic");
    }

    let _ = fs::remove_dir_all(&temp_dir);
}

#[test]
fn test_adversarial_vimscript_crlf_offset_corruption() {
    // Test Windows CRLF line endings on Vimscript Plug line
    let (temp_dir, temp_root) = create_temp_workspace("adv_vim_crlf");
    let vim_file = temp_root.join("crlf.vim");
    let content = "call plug#begin()\r\nPlug 'user/repo', {'branch': 'main'}\r\ncall plug#end()\r\n";
    fs::write(&vim_file, content).unwrap();

    let res = scan(&temp_root);
    assert_eq!(res.snapshot.plugins.len(), 1, "Should parse 1 plugin under CRLF");
    let p = &res.snapshot.plugins[0];
    let branch_field = p.branch.as_ref().expect("Branch field should exist");
    assert_eq!(
        branch_field.value,
        Some(LuaValue::String { value: "main".to_string() })
    );

    // Now test patching under CRLF
    let patch = PatchRequest {
        id: branch_field.id.clone(),
        file: branch_field.file.clone(),
        revision: branch_field.revision.clone(),
        value: LuaValue::String { value: "develop".to_string() },
    };
    let patch_res = apply_patch(&temp_root, &patch);
    assert!(
        patch_res.is_ok(),
        "apply_patch on CRLF vimscript failed: {:?}",
        patch_res.err()
    );

    let patched_content = fs::read_to_string(&vim_file).unwrap();
    assert!(
        patched_content.contains("'branch': 'develop'"),
        "Patched content should contain updated branch, got: {:?}",
        patched_content
    );

    let _ = fs::remove_dir_all(&temp_dir);
}

#[test]
fn test_adversarial_vimscript_comments_and_validation() {
    // In Vimscript, quotes `"` denote comments.
    // validate_vimscript treats `"` as double-quote string delimiter.
    // If a Vimscript file has a standard comment with an odd number of `"` characters,
    // does validate_vimscript fail and reject patches?
    let (temp_dir, temp_root) = create_temp_workspace("adv_vim_comment");
    let vim_file = temp_root.join("with_comments.vim");
    let content = "\" This is a single comment line\ncall plug#begin()\nPlug 'tpope/vim-fugitive', {'tag': 'v1'}\ncall plug#end()\n";
    fs::write(&vim_file, content).unwrap();

    let res = scan(&temp_root);
    assert_eq!(res.snapshot.plugins.len(), 1);
    let p = &res.snapshot.plugins[0];
    let tag = p.tag.as_ref().unwrap();

    let patch = PatchRequest {
        id: tag.id.clone(),
        file: tag.file.clone(),
        revision: tag.revision.clone(),
        value: LuaValue::String { value: "v2".to_string() },
    };

    let patch_res = apply_patch(&temp_root, &patch);
    // Observe whether validate_vimscript fails due to the comment!
    match &patch_res {
        Ok(_) => println!("Vimscript patch with comment succeeded"),
        Err(e) => {
            eprintln!("CONFIRMED BUG: Vimscript patch rejected due to valid comment: {:?}", e);
        }
    }
    let _ = fs::remove_dir_all(&temp_dir);
}

#[test]
fn test_adversarial_vimscript_inline_comment_with_brace() {
    // Test inline comment containing a brace or single quote
    let (temp_dir, temp_root) = create_temp_workspace("adv_vim_inline_comment");
    let vim_file = temp_root.join("inline.vim");
    let content = "call plug#begin()\nPlug 'tpope/vim-surround', {'tag': 'v1'} \" note: don't use } here\ncall plug#end()\n";
    fs::write(&vim_file, content).unwrap();

    let res = scan(&temp_root);
    assert_eq!(res.snapshot.plugins.len(), 1, "Should find 1 plugin");
    let p = &res.snapshot.plugins[0];
    assert_eq!(p.name, "vim-surround");
    println!("Parsed tag value with inline comment: {:?}", p.tag.as_ref().and_then(|t| t.value.clone()));

    let _ = fs::remove_dir_all(&temp_dir);
}

#[test]
fn test_adversarial_vimscript_escaped_quotes_in_options() {
    // In Vimscript strings, single quotes are escaped with ''
    let (temp_dir, temp_root) = create_temp_workspace("adv_vim_escaped");
    let vim_file = temp_root.join("escaped.vim");
    let content = "call plug#begin()\nPlug 'tpope/vim-fugitive', {'branch': 'user''s-branch'}\ncall plug#end()\n";
    fs::write(&vim_file, content).unwrap();

    let res = scan(&temp_root);
    let p = &res.snapshot.plugins[0];
    println!("Branch parsed from escaped single quote: {:?}", p.branch.as_ref().and_then(|b| b.value.clone()));

    let _ = fs::remove_dir_all(&temp_dir);
}

#[test]
fn test_adversarial_vimscript_git_urls() {
    let (temp_dir, temp_root) = create_temp_workspace("adv_vim_urls");
    let vim_file = temp_root.join("urls.vim");
    let content = r#"
call plug#begin()
Plug 'git@github.com:folke/which-key.nvim.git'
Plug 'https://gitlab.com/group/subgroup/custom-plugin.git'
Plug 'tpope/vim-repeat'
Plug '~/code/local-plugin'
Plug 'bare-plugin'
call plug#end()
"#;
    fs::write(&vim_file, content).unwrap();

    let res = scan(&temp_root);
    assert_eq!(res.snapshot.plugins.len(), 5);
    let names: Vec<String> = res.snapshot.plugins.iter().map(|p| p.name.clone()).collect();
    assert!(names.contains(&"which-key.nvim".to_string()));
    assert!(names.contains(&"custom-plugin".to_string()));
    assert!(names.contains(&"vim-repeat".to_string()));
    assert!(names.contains(&"local-plugin".to_string()));
    assert!(names.contains(&"bare-plugin".to_string()));

    let _ = fs::remove_dir_all(&temp_dir);
}

// =========================================================================
// Category 2: Lazy.nvim Syntax Edge Cases & Patching
// =========================================================================

#[test]
fn test_adversarial_lazy_deeply_nested_tables() {
    let (temp_dir, temp_root) = create_temp_workspace("adv_lazy_nested");
    let plugins_dir = temp_root.join("lua").join("plugins");
    fs::create_dir_all(&plugins_dir).unwrap();
    let spec_file = plugins_dir.join("nested.lua");

    let content = r#"
return {
    "nvim-treesitter/nvim-treesitter",
    opts = {
        highlight = {
            enable = true,
            disable = { "c", "rust" },
        },
        indent = {
            enable = true,
            nested = {
                deep = {
                    level = 42,
                    flag = true,
                },
            },
        },
    },
}
"#;
    fs::write(&spec_file, content).unwrap();

    let res = scan(&temp_root);
    assert_eq!(res.snapshot.plugins.len(), 1);
    let p = &res.snapshot.plugins[0];
    assert_eq!(p.name, "nvim-treesitter");
    assert!(matches!(p.opts.value, Some(LuaValue::Table { .. })));

    let _ = fs::remove_dir_all(&temp_dir);
}

#[test]
fn test_adversarial_lazy_multiline_functions_and_closures() {
    let (temp_dir, temp_root) = create_temp_workspace("adv_lazy_multiline");
    let plugins_dir = temp_root.join("lua").join("plugins");
    fs::create_dir_all(&plugins_dir).unwrap();
    let spec_file = plugins_dir.join("closures.lua");

    let content = r#"
return {
    "folke/tokyonight.nvim",
    lazy = false,
    priority = 1000,
    opts = function(
        client,
        options
    )
        return {
            style = "storm",
            transparent = true,
        }
    end,
    config = function(
        _plugin,
        opts
    )
        require("tokyonight").setup(opts)
        vim.cmd[[colorscheme tokyonight]]
    end,
}
"#;
    fs::write(&spec_file, content).unwrap();

    let res = scan(&temp_root);
    assert_eq!(res.snapshot.plugins.len(), 1);
    let p = &res.snapshot.plugins[0];
    assert_eq!(p.name, "tokyonight.nvim");
    assert!(matches!(p.opts.value, Some(LuaValue::Unsupported { .. })));
    assert!(p.config.is_some());

    let _ = fs::remove_dir_all(&temp_dir);
}

#[test]
fn test_adversarial_lazy_bare_string_patching_replaces_repo_name() {
    let (temp_dir, temp_root) = create_temp_workspace("adv_lazy_bare_patch");
    let plugins_dir = temp_root.join("lua").join("plugins");
    fs::create_dir_all(&plugins_dir).unwrap();
    let spec_file = plugins_dir.join("bare.lua");

    let content = "return {\n    \"tpope/vim-fugitive\",\n}\n";
    fs::write(&spec_file, content).unwrap();

    let res = scan(&temp_root);
    assert_eq!(res.snapshot.plugins.len(), 1);
    let p = &res.snapshot.plugins[0];
    assert_eq!(p.name, "vim-fugitive");
    assert_eq!(p.enabled.value, Some(LuaValue::Boolean { value: true }));

    let patch = PatchRequest {
        id: p.enabled.id.clone(),
        file: p.enabled.file.clone(),
        revision: p.enabled.revision.clone(),
        value: LuaValue::Boolean { value: false },
    };

    let patch_res = apply_patch(&temp_root, &patch).expect("apply_patch should succeed");
    let patched_file = fs::read_to_string(&spec_file).unwrap();
    assert!(
        patched_file.contains("tpope/vim-fugitive"),
        "Patching bare string must preserve plugin repo name, got:\n{patched_file}"
    );
    assert_eq!(patch_res.scan.snapshot.plugins.len(), 1);
    assert_eq!(
        patch_res.scan.snapshot.plugins[0].enabled.value,
        Some(LuaValue::Boolean { value: false })
    );

    let _ = fs::remove_dir_all(&temp_dir);
}

#[test]
fn test_adversarial_lazy_dir_only_spec() {
    // In lazy.nvim, a plugin can be specified with `dir = "~/local-plugin"` without positional string
    let (temp_dir, temp_root) = create_temp_workspace("adv_lazy_dir");
    let plugins_dir = temp_root.join("lua").join("plugins");
    fs::create_dir_all(&plugins_dir).unwrap();
    let spec_file = plugins_dir.join("local_dir.lua");

    let content = r#"
return {
    dir = "~/projects/my-local-plugin",
    name = "my-local-plugin",
    config = true,
}
"#;
    fs::write(&spec_file, content).unwrap();

    let res = scan(&temp_root);
    println!("Plugins found for dir-only spec: {}", res.snapshot.plugins.len());
    for p in &res.snapshot.plugins {
        println!("Plugin found: {} ({})", p.name, p.source);
    }

    let _ = fs::remove_dir_all(&temp_dir);
}

// =========================================================================
// Category 3: Packer.nvim Syntax Edge Cases & Inverted Round-Trip Patching
// =========================================================================

#[test]
fn test_adversarial_packer_inverted_patch_oscillation() {
    // Rigorously test bidirectional round-trip mutations:
    // Start with plugin without disable attribute (implicitly enabled = true).
    // Mutate enabled -> false -> true -> false -> true -> false (5 round-trips).
    // Verify file syntax at every step.
    let (temp_dir, temp_root) = create_temp_workspace("adv_packer_oscillation");
    let packer_file = temp_root.join("packer.lua");
    let content = r#"
return require("packer").startup(function(use)
    use {
        "tpope/vim-surround",
        opt = true,
    }
end)
"#;
    fs::write(&packer_file, content).unwrap();

    let mut expected_enabled = false;
    for step in 1..=6 {
        let snap = scan(&temp_root);
        let p = snap.snapshot.plugins.iter().find(|p| p.name == "vim-surround").unwrap();

        let patch = PatchRequest {
            id: p.enabled.id.clone(),
            file: p.enabled.file.clone(),
            revision: p.enabled.revision.clone(),
            value: LuaValue::Boolean { value: expected_enabled },
        };

        let patch_res = apply_patch(&temp_root, &patch);
        assert!(patch_res.is_ok(), "Step {} apply_patch failed: {:?}", step, patch_res.err());

        // Verify AST can parse the resulting file
        let new_content = fs::read_to_string(&packer_file).unwrap();
        assert!(
            full_moon::parse(&new_content).is_ok(),
            "Step {} created invalid Lua syntax:\n{}",
            step,
            new_content
        );

        let rescanned = scan(&temp_root);
        let rescanned_p = rescanned.snapshot.plugins.iter().find(|p| p.name == "vim-surround").unwrap();
        assert_eq!(
            rescanned_p.enabled.value,
            Some(LuaValue::Boolean { value: expected_enabled }),
            "Step {} did not reflect expected enabled state",
            step
        );

        // Toggle state for next iteration
        expected_enabled = !expected_enabled;
    }

    let _ = fs::remove_dir_all(&temp_dir);
}

#[test]
fn test_adversarial_concurrent_patch_revision_conflict() {
    // Test concurrent/competing patch requests with optimistic concurrency
    let (temp_dir, temp_root) = create_temp_workspace("adv_concurrent_conflict");
    let plugins_dir = temp_root.join("lua").join("plugins");
    fs::create_dir_all(&plugins_dir).unwrap();
    let spec_file = plugins_dir.join("single.lua");
    let content = "return {\n    \"tpope/vim-sensible\",\n    tag = \"v1.0\",\n}\n";
    fs::write(&spec_file, content).unwrap();

    let initial = scan(&temp_root);
    let p = &initial.snapshot.plugins[0];
    let tag = p.tag.as_ref().unwrap();

    let patch_a = PatchRequest {
        id: tag.id.clone(),
        file: tag.file.clone(),
        revision: tag.revision.clone(),
        value: LuaValue::String { value: "v2.0".to_string() },
    };

    let patch_b = PatchRequest {
        id: tag.id.clone(),
        file: tag.file.clone(),
        revision: tag.revision.clone(), // STALE revision!
        value: LuaValue::String { value: "v3.0".to_string() },
    };

    // Apply Patch A: should succeed
    let res_a = apply_patch(&temp_root, &patch_a);
    assert!(res_a.is_ok(), "First patch should succeed");

    // Apply Patch B with now-stale revision: MUST fail with ApiError::Conflict
    let res_b = apply_patch(&temp_root, &patch_b);
    assert!(
        matches!(res_b, Err(ApiError::Conflict(_))),
        "Second patch with stale revision MUST return ApiError::Conflict, got {:?}",
        res_b.err()
    );

    // Verify file has Patch A content, not corrupted by Patch B
    let file_content = fs::read_to_string(&spec_file).unwrap();
    assert!(file_content.contains("v2.0"));
    assert!(!file_content.contains("v3.0"));

    let _ = fs::remove_dir_all(&temp_dir);
}

#[test]
fn test_adversarial_packer_bare_string_patching_overwrites_repo_name() {
    let (temp_dir, temp_root) = create_temp_workspace("adv_packer_bare_patch");
    let packer_file = temp_root.join("packer_bare.lua");
    let content = "return require(\"packer\").startup(function(use)\n    use 'tpope/vim-commentary'\nend)\n";
    fs::write(&packer_file, content).unwrap();

    let res = scan(&temp_root);
    assert_eq!(res.snapshot.plugins.len(), 1);
    let p = &res.snapshot.plugins[0];
    assert_eq!(p.name, "vim-commentary");
    assert_eq!(p.source, "tpope/vim-commentary");
    assert_eq!(p.enabled.value, Some(LuaValue::Boolean { value: true }));

    let patch = PatchRequest {
        id: p.enabled.id.clone(),
        file: p.enabled.file.clone(),
        revision: p.enabled.revision.clone(),
        value: LuaValue::Boolean { value: false },
    };

    let patch_res = apply_patch(&temp_root, &patch).expect("Packer bare string patch must succeed");
    let patched_file = fs::read_to_string(&packer_file).unwrap();
    assert!(
        patched_file.contains("tpope/vim-commentary") && patched_file.contains("disable = true"),
        "Packer bare string patch must expand to table with disable = true, got:\n{patched_file}"
    );
    assert_eq!(patch_res.scan.snapshot.plugins.len(), 1);
    assert_eq!(
        patch_res.scan.snapshot.plugins[0].enabled.value,
        Some(LuaValue::Boolean { value: false })
    );

    let _ = fs::remove_dir_all(&temp_dir);
}

#[test]
fn test_adversarial_lazy_speclist_bare_string_patching_overwrites_repo_name() {
    let (temp_dir, temp_root) = create_temp_workspace("adv_lazy_speclist_bare");
    let plugins_dir = temp_root.join("lua").join("plugins");
    fs::create_dir_all(&plugins_dir).unwrap();
    let spec_file = plugins_dir.join("multi_bare.lua");
    let content = "return {\n    \"tpope/vim-fugitive\",\n    \"tpope/vim-surround\",\n}\n";
    fs::write(&spec_file, content).unwrap();

    let res = scan(&temp_root);
    assert_eq!(res.snapshot.plugins.len(), 2);
    let fugitive = res.snapshot.plugins.iter().find(|p| p.name == "vim-fugitive").unwrap();
    assert_eq!(fugitive.enabled.value, Some(LuaValue::Boolean { value: true }));

    let patch = PatchRequest {
        id: fugitive.enabled.id.clone(),
        file: fugitive.enabled.file.clone(),
        revision: fugitive.enabled.revision.clone(),
        value: LuaValue::Boolean { value: false },
    };

    let patch_res = apply_patch(&temp_root, &patch).expect("apply_patch should succeed");
    let patched_file = fs::read_to_string(&spec_file).unwrap();
    assert!(
        patched_file.contains("tpope/vim-fugitive") && patched_file.contains("enabled = false"),
        "Lazy SpecList bare string patch must expand to table with enabled = false, got:\n{patched_file}"
    );
    let updated_fugitive = patch_res
        .scan
        .snapshot
        .plugins
        .iter()
        .find(|p| p.name == "vim-fugitive")
        .unwrap();
    assert_eq!(
        updated_fugitive.enabled.value,
        Some(LuaValue::Boolean { value: false })
    );

    let _ = fs::remove_dir_all(&temp_dir);
}

#[test]
fn test_adversarial_validate_vimscript_comment_handling() {
    use ucdp_daemon::lua::validate_vimscript;

    // Standard Vimscript comment with odd number of quotes
    let source_with_comment = "\" Configure plugins\ncall plug#begin()\nPlug 'foo/bar'\ncall plug#end()\n";
    let res = validate_vimscript(source_with_comment);
    assert!(
        res.is_ok(),
        "validate_vimscript must accept valid full-line comments: {:?}",
        res.err()
    );

    // Vimscript comment with single quote like: " don't do this
    let source_with_single_quote_comment = "\" don't do this\ncall plug#begin()\ncall plug#end()\n";
    let res_sq = validate_vimscript(source_with_single_quote_comment);
    assert!(
        res_sq.is_ok(),
        "validate_vimscript must accept comments containing single quotes (don't): {:?}",
        res_sq.err()
    );

    // Inline comment with unmatched quotes and parens
    let source_with_inline_comment =
        "call plug#begin()\nPlug 'foo/bar' \" author's favorite (fast)\ncall plug#end()\n";
    let res_inline = validate_vimscript(source_with_inline_comment);
    assert!(
        res_inline.is_ok(),
        "validate_vimscript must accept inline comments after Plug command: {:?}",
        res_inline.err()
    );

    // Actual unclosed double quote in Plug argument must still fail
    let source_unclosed = "call plug#begin()\nPlug \"foo/bar\ncall plug#end()\n";
    assert!(
        validate_vimscript(source_unclosed).is_err(),
        "validate_vimscript must still reject actual unclosed double-quoted strings"
    );
}

#[test]
fn test_m1_entity_deletion_and_backup_rollback() {
    use ucdp_daemon::lua::{delete_entity, rollback_backup};
    use ucdp_daemon::model::DeleteEntityRequest;

    let (temp_dir, temp_root) = create_temp_workspace("m1_delete_and_backup");
    let init_file = temp_root.join("init.lua");
    let initial_content = r#"vim.opt.number = true
vim.keymap.set("n", "<leader>w", ":w<CR>", { desc = "Save" })
require("lazy").setup({
    "tpope/vim-sleuth",
    { "nvim-lua/plenary.nvim" },
})
"#;
    fs::write(&init_file, initial_content).unwrap();

    let scan0 = scan(&temp_root);
    assert_eq!(scan0.snapshot.settings.len(), 1);
    assert_eq!(scan0.snapshot.keymaps.len(), 1);
    assert_eq!(scan0.snapshot.plugins.len(), 2);

    // 1. Delete keymap
    let km = &scan0.snapshot.keymaps[0];
    let del_km = delete_entity(
        &temp_root,
        &DeleteEntityRequest {
            id: km.mode.id.clone(),
            file: Some(km.mode.file.clone()),
            revision: Some(km.mode.revision.clone()),
        },
    )
    .expect("Deleting keymap should succeed");
    assert_eq!(del_km.scan.snapshot.keymaps.len(), 0);
    assert_eq!(del_km.scan.snapshot.settings.len(), 1);
    assert_eq!(del_km.scan.snapshot.plugins.len(), 2);

    // Verify .backup directory was created and ignored by scan
    let backup_dir = temp_root.join(".backup");
    assert!(backup_dir.is_dir(), ".backup directory must be created before write");
    assert!(
        backup_dir.join("latest.json").is_file(),
        "latest.json backup metadata must exist"
    );

    // 2. Delete bare-string plugin ("tpope/vim-sleuth")
    let sleuth = del_km
        .scan
        .snapshot
        .plugins
        .iter()
        .find(|p| p.name == "vim-sleuth")
        .unwrap();
    let del_plugin = delete_entity(
        &temp_root,
        &DeleteEntityRequest {
            id: sleuth.enabled.id.clone(),
            file: Some(sleuth.enabled.file.clone()),
            revision: Some(sleuth.enabled.revision.clone()),
        },
    )
    .expect("Deleting bare-string plugin should succeed");
    assert_eq!(del_plugin.scan.snapshot.plugins.len(), 1);
    assert_eq!(del_plugin.scan.snapshot.plugins[0].name, "plenary.nvim");

    // 3. Rollback to the state before plugin deletion
    let rolled_back = rollback_backup(&temp_root, None, None).expect("rollback should succeed");
    assert_eq!(rolled_back.snapshot.plugins.len(), 2);

    let _ = fs::remove_dir_all(&temp_dir);
}

// =========================================================================
// Category 4: Daemon Panic Resistance on Malformed Files
// =========================================================================

#[test]
fn test_adversarial_malformed_lua_never_panics() {
    let (temp_dir, temp_root) = create_temp_workspace("adv_malformed_lua");
    let plugins_dir = temp_root.join("lua").join("plugins");
    fs::create_dir_all(&plugins_dir).unwrap();

    // 1. Incomplete/unclosed syntax
    fs::write(plugins_dir.join("unclosed.lua"), "return { { { { \"repo\"").unwrap();

    // 2. Random binary garbage
    fs::write(plugins_dir.join("garbage.lua"), b"\x00\xff\xfe\x01\x02\x03random bytes\x00").unwrap();

    // 3. Null bytes in the middle of valid Lua
    fs::write(plugins_dir.join("nulls.lua"), "return { 'foo\0bar' }").unwrap();

    // 4. Empty file
    fs::write(plugins_dir.join("empty.lua"), "").unwrap();

    // 5. Bare return statements
    fs::write(plugins_dir.join("bare_return.lua"), "return").unwrap();
    fs::write(plugins_dir.join("multi_return.lua"), "return 1, 2, 3").unwrap();

    // 6. Moderate nested tables (depth 30) - should NOT stack overflow
    let mut nested = String::new();
    for _ in 0..30 {
        nested.push_str("{ ");
    }
    nested.push_str("\"folke/which-key.nvim\"");
    for _ in 0..30 {
        nested.push_str(" }");
    }
    fs::write(plugins_dir.join("deep.lua"), format!("return {nested}")).unwrap();

    let scan_res = panic::catch_unwind(AssertUnwindSafe(|| {
        scan(&temp_root)
    }));

    assert!(scan_res.is_ok(), "Daemon MUST NOT panic on malformed Lua files");
    let scan_res = scan_res.unwrap();
    assert!(
        !scan_res.snapshot.diagnostics.is_empty(),
        "Expected diagnostics to be recorded for malformed files"
    );

    let _ = fs::remove_dir_all(&temp_dir);
}

#[test]
fn test_adversarial_malformed_vimscript_never_panics() {
    let (temp_dir, temp_root) = create_temp_workspace("adv_malformed_vim");

    // 1. Unclosed quotes and brackets
    fs::write(temp_root.join("unclosed.vim"), "call plug#begin()\nPlug 'repo', { 'tag': \n").unwrap();

    // 2. Binary garbage in vim file
    fs::write(temp_root.join("garbage.vim"), b"\x00\x80\xff\xee").unwrap();

    // 3. Trailing commas and colons without values
    fs::write(temp_root.join("dangling.vim"), "Plug 'repo', { , , : : }\n").unwrap();

    // 4. Extreme whitespace with Plug keyword
    fs::write(temp_root.join("spaces.vim"), "Plug       \n").unwrap();

    let scan_res = panic::catch_unwind(AssertUnwindSafe(|| {
        scan(&temp_root)
    }));

    assert!(scan_res.is_ok(), "Daemon MUST NOT panic on malformed Vimscript files");

    let _ = fs::remove_dir_all(&temp_dir);
}

#[test]
fn test_m3_atomic_batch_patching() {
    use ucdp_daemon::lua::apply_batch_patch;

    let (temp_dir, temp_root) = create_temp_workspace("m3_batch_patch");
    let init_file = temp_root.join("init.lua");
    fs::write(
        &init_file,
        "vim.keymap.set('n', '<leader>ff', '<cmd>Telescope find_files<cr>', { desc = 'Find' })\n",
    )
    .unwrap();

    let initial = scan(&temp_root);
    assert_eq!(initial.snapshot.keymaps.len(), 1);
    let km = &initial.snapshot.keymaps[0];
    let file_str = km.mode.file.clone();
    let rev = km.mode.revision.clone();

    // Batch-update mode, lhs, and rhs in a single atomic transaction
    let batch = vec![
        PatchRequest {
            id: km.mode.id.clone(),
            file: file_str.clone(),
            revision: rev.clone(),
            value: LuaValue::String {
                value: "v".to_owned(),
            },
        },
        PatchRequest {
            id: km.lhs.id.clone(),
            file: file_str.clone(),
            revision: rev.clone(),
            value: LuaValue::String {
                value: "<leader>fg".to_owned(),
            },
        },
        PatchRequest {
            id: km.rhs.id.clone(),
            file: file_str.clone(),
            revision: rev.clone(),
            value: LuaValue::String {
                value: "<cmd>Telescope live_grep<cr>".to_owned(),
            },
        },
    ];

    let res = apply_batch_patch(&temp_root, &batch, Some(&initial.snapshot))
        .expect("atomic batch patch should succeed");
    assert_eq!(res.scan.snapshot.keymaps.len(), 1);
    let updated = &res.scan.snapshot.keymaps[0];
    assert_eq!(
        updated.mode.value,
        Some(LuaValue::String {
            value: "v".to_owned()
        })
    );
    assert_eq!(
        updated.lhs.value,
        Some(LuaValue::String {
            value: "<leader>fg".to_owned()
        })
    );
    assert_eq!(
        updated.rhs.value,
        Some(LuaValue::String {
            value: "<cmd>Telescope live_grep<cr>".to_owned()
        })
    );

    let _ = fs::remove_dir_all(&temp_dir);
}

#[test]
fn test_m3_semantic_keymap_id_stability() {
    let (temp_dir, temp_root) = create_temp_workspace("m3_semantic_keymap_id");
    let init_file = temp_root.join("init.lua");
    fs::write(
        &init_file,
        "vim.keymap.set('n', '<leader>w', '<cmd>w<cr>')\n",
    )
    .unwrap();

    let scan1 = scan(&temp_root);
    assert_eq!(scan1.snapshot.keymaps.len(), 1);
    let original_id = scan1.snapshot.keymaps[0].rhs.id.clone();

    // Insert a brand-new keymap at the TOP of init.lua
    fs::write(
        &init_file,
        "vim.keymap.set('n', '<leader>q', '<cmd>q<cr>')\nvim.keymap.set('n', '<leader>w', '<cmd>w<cr>')\n",
    )
    .unwrap();

    let scan2 = scan(&temp_root);
    assert_eq!(scan2.snapshot.keymaps.len(), 2);
    let moved_km = scan2
        .snapshot
        .keymaps
        .iter()
        .find(|k| {
            k.lhs.value
                == Some(LuaValue::String {
                    value: "<leader>w".to_owned(),
                })
        })
        .expect("should find <leader>w keymap");
    assert_eq!(
        moved_km.rhs.id, original_id,
        "semantic keymap ID must remain stable even when earlier keymaps are inserted"
    );

    let _ = fs::remove_dir_all(&temp_dir);
}

#[test]
fn test_m3_extended_option_syntax_and_comment_aware_plugin_append() {
    use ucdp_daemon::lua::append_plugin;
    use ucdp_daemon::model::{AddPluginRequest, PluginManagerKind};

    let (temp_dir, temp_root) = create_temp_workspace("m3_syntax_ext");
    let init_file = temp_root.join("init.lua");
    fs::write(
        &init_file,
        concat!(
            "vim.wo.relativenumber = true\n",
            "vim.bo.shiftwidth = 4\n",
            "vim.opt[\"number\"] = true\n",
            "vim.opt.clipboard:append(\"unnamedplus\")\n",
            "require('packer').startup(function(use)\n",
            "  use 'wbthomason/packer.nvim'\n",
            "end)\n",
            "-- trailing comment with end) inside\n",
        ),
    )
    .unwrap();

    let scan1 = scan(&temp_root);
    let names: Vec<String> = scan1.snapshot.settings.iter().map(|s| s.name.clone()).collect();
    assert!(names.contains(&"relativenumber".to_owned()));
    assert!(names.contains(&"shiftwidth".to_owned()));
    assert!(names.contains(&"number".to_owned()));
    assert!(names.contains(&"clipboard".to_owned()));

    // Append a Packer plugin; it must insert before the real `end)` and NOT inside the trailing `-- ... end)` comment!
    let (scan2, added_name, _) = append_plugin(
        &temp_root,
        &AddPluginRequest {
            source: "nvim-lua/plenary.nvim".to_owned(),
            manager: Some(PluginManagerKind::Packer),
            enabled: Some(true),
            lazy: None,
            event: None,
            cmd: None,
            ft: None,
            branch: None,
            tag: None,
            build: None,
            opts: None,
        },
    )
    .expect("append_plugin should succeed without corrupting trailing comment");
    assert_eq!(added_name, "plenary.nvim");
    assert!(scan2.snapshot.diagnostics.is_empty());
    assert!(scan2
        .snapshot
        .plugins
        .iter()
        .any(|p| p.name == "plenary.nvim"));

    let _ = fs::remove_dir_all(&temp_dir);
}
