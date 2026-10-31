import os
import sys
import unittest

QT_GUI_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "qt_gui"))
if QT_GUI_DIR not in sys.path:
    sys.path.insert(0, QT_GUI_DIR)

from widgets import (
    UnsupportedValue,
    default_for_kind,
    is_lua_value,
    lua_to_python,
    python_to_lua,
    value_kind,
)


def extract_plugin_name(source):
    if not source:
        return "unnamed"
    clean = source.rstrip("/")
    if clean.endswith(".git"):
        clean = clean[:-4]
    if "/" in clean:
        return clean.rsplit("/", 1)[1]
    if ":" in clean:
        return clean.rsplit(":", 1)[1]
    return clean


def normalize_plugin_spec(raw_spec, manager_hint=None):
    """Authoritative reference implementation of cross-manager plugin normalization
    specified in miner_survey_plugins/handoff.md § Section 7 and PROJECT.md § Interface Contracts."""
    result = {
        "name": "",
        "source": "",
        "manager": manager_hint or "lazy",
        "enabled": True,
        "lazy": False,
        "event": None,
        "cmd": None,
        "ft": None,
        "keys": None,
        "opts": None,
        "dependencies": None,
        "branch": None,
        "tag": None,
        "commit": None,
        "version": None,
        "pin": False,
        "build": None,
        "dir": None,
    }

    if isinstance(raw_spec, str):
        result["source"] = raw_spec
        result["name"] = extract_plugin_name(raw_spec)
        return result

    if not isinstance(raw_spec, dict):
        return result

    # Manager hint detection
    if "disable" in raw_spec or "requires" in raw_spec or "run" in raw_spec or "opt" in raw_spec:
        result["manager"] = "packer"
    elif "do" in raw_spec or "for" in raw_spec or "frozen" in raw_spec:
        result["manager"] = "plug"
    elif raw_spec.get("manager") in {"lazy", "packer", "plug"}:
        result["manager"] = raw_spec["manager"]

    # Source & Name
    source = raw_spec.get("source") or raw_spec.get(1) or raw_spec.get("url") or raw_spec.get("dir") or ""
    result["source"] = str(source)
    name = raw_spec.get("name") or raw_spec.get("as")
    result["name"] = str(name) if name else extract_plugin_name(result["source"])

    # Enabled
    if result["manager"] == "packer":
        if "disable" in raw_spec:
            result["enabled"] = not bool(raw_spec["disable"])
        else:
            result["enabled"] = True
    else:
        if "enabled" in raw_spec:
            result["enabled"] = bool(raw_spec["enabled"])
        elif "cond" in raw_spec and isinstance(raw_spec["cond"], bool):
            result["enabled"] = raw_spec["cond"]
        else:
            result["enabled"] = True

    # Lazy / Opt
    if result["manager"] == "packer":
        result["lazy"] = bool(raw_spec.get("opt", False))
    elif result["manager"] == "plug":
        result["lazy"] = bool(raw_spec.get("on") or raw_spec.get("for"))
    else:
        result["lazy"] = bool(raw_spec.get("lazy", False))

    # Triggers: cmd, ft, event, keys
    if result["manager"] == "plug":
        on_val = raw_spec.get("on")
        if on_val:
            if isinstance(on_val, str) and on_val.startswith("<Plug>"):
                result["keys"] = on_val
            else:
                result["cmd"] = on_val
        result["ft"] = raw_spec.get("for")
    else:
        result["cmd"] = raw_spec.get("cmd")
        result["ft"] = raw_spec.get("ft")
        result["event"] = raw_spec.get("event")
        result["keys"] = raw_spec.get("keys")

    # Dependencies
    if result["manager"] == "packer":
        result["dependencies"] = raw_spec.get("requires")
    else:
        result["dependencies"] = raw_spec.get("dependencies")

    # Build hooks
    if result["manager"] == "packer":
        result["build"] = raw_spec.get("run")
    elif result["manager"] == "plug":
        result["build"] = raw_spec.get("do")
    else:
        result["build"] = raw_spec.get("build")

    # Pinning
    if result["manager"] == "packer":
        result["pin"] = bool(raw_spec.get("lock", False))
    elif result["manager"] == "plug":
        result["pin"] = bool(raw_spec.get("frozen", 0) in (1, True, "1"))
    else:
        result["pin"] = bool(raw_spec.get("pin", False))

    # Versioning
    result["branch"] = raw_spec.get("branch")
    result["tag"] = raw_spec.get("tag")
    result["commit"] = raw_spec.get("commit")
    result["version"] = raw_spec.get("version")
    result["dir"] = raw_spec.get("dir")
    result["opts"] = raw_spec.get("opts")

    return result


class TestLuaValueConversion(unittest.TestCase):
    """Tier 1: Core LuaValue to Python data conversion."""

    def test_scalar_roundtrip_boolean(self):
        lua_val = {"kind": "boolean", "value": True}
        py_val = lua_to_python(lua_val)
        self.assertIs(py_val, True)
        self.assertEqual(python_to_lua(py_val), lua_val)

        lua_false = {"kind": "boolean", "value": False}
        self.assertIs(lua_to_python(lua_false), False)
        self.assertEqual(python_to_lua(False), lua_false)

    def test_scalar_roundtrip_number(self):
        lua_num = {"kind": "number", "value": 42}
        py_val = lua_to_python(lua_num)
        self.assertEqual(py_val, 42)
        self.assertEqual(python_to_lua(py_val), lua_num)

        lua_float = {"kind": "number", "value": 3.14159}
        self.assertAlmostEqual(lua_to_python(lua_float), 3.14159)
        self.assertEqual(python_to_lua(3.14159), lua_float)

    def test_scalar_roundtrip_string(self):
        lua_str = {"kind": "string", "value": "tokyonight"}
        py_val = lua_to_python(lua_str)
        self.assertEqual(py_val, "tokyonight")
        self.assertEqual(python_to_lua(py_val), lua_str)

    def test_array_roundtrip(self):
        lua_arr = {
            "kind": "array",
            "values": [
                {"kind": "string", "value": "BufRead"},
                {"kind": "string", "value": "BufNewFile"},
            ],
        }
        py_val = lua_to_python(lua_arr)
        self.assertEqual(py_val, ["BufRead", "BufNewFile"])
        self.assertEqual(python_to_lua(py_val), lua_arr)

    def test_table_roundtrip(self):
        lua_tbl = {
            "kind": "table",
            "entries": [
                {"key": "enable", "value": {"kind": "boolean", "value": True}},
                {"key": "style", "value": {"kind": "string", "value": "storm"}},
            ],
        }
        py_val = lua_to_python(lua_tbl)
        self.assertEqual(py_val, {"enable": True, "style": "storm"})
        back = python_to_lua(py_val)
        self.assertEqual(back.get("kind"), "table")
        entry_map = {e["key"]: e["value"] for e in back["entries"]}
        self.assertEqual(entry_map["enable"], {"kind": "boolean", "value": True})
        self.assertEqual(entry_map["style"], {"kind": "string", "value": "storm"})

    def test_unsupported_value_preserved(self):
        src = "function(_, opts) require('foo').setup(opts) end"
        lua_unsup = {"kind": "unsupported", "source": src}
        py_val = lua_to_python(lua_unsup)
        self.assertIsInstance(py_val, UnsupportedValue)
        self.assertEqual(py_val.source, src)
        self.assertEqual(python_to_lua(py_val), lua_unsup)


class TestLazyNvimNormalization(unittest.TestCase):
    """Tier 1: lazy.nvim specification normalization."""

    def test_single_string_spec(self):
        spec = "folke/tokyonight.nvim"
        norm = normalize_plugin_spec(spec, "lazy")
        self.assertEqual(norm["name"], "tokyonight.nvim")
        self.assertEqual(norm["source"], "folke/tokyonight.nvim")
        self.assertEqual(norm["manager"], "lazy")
        self.assertTrue(norm["enabled"])

    def test_table_spec_with_triggers(self):
        spec = {
            1: "nvim-treesitter/nvim-treesitter",
            "build": ":TSUpdate",
            "event": ["BufReadPost", "BufNewFile"],
            "cmd": ["TSUpdateSync"],
            "opts": {"highlight": {"enable": True}},
        }
        norm = normalize_plugin_spec(spec, "lazy")
        self.assertEqual(norm["name"], "nvim-treesitter")
        self.assertEqual(norm["source"], "nvim-treesitter/nvim-treesitter")
        self.assertEqual(norm["build"], ":TSUpdate")
        self.assertEqual(norm["event"], ["BufReadPost", "BufNewFile"])
        self.assertEqual(norm["cmd"], ["TSUpdateSync"])
        self.assertEqual(norm["opts"], {"highlight": {"enable": True}})

    def test_local_dir_spec(self):
        spec = {"dir": "~/projects/my-local-plugin", "lazy": True}
        norm = normalize_plugin_spec(spec, "lazy")
        self.assertEqual(norm["name"], "my-local-plugin")
        self.assertEqual(norm["dir"], "~/projects/my-local-plugin")
        self.assertTrue(norm["lazy"])

    def test_custom_name_override(self):
        spec = {1: "author/repo", "name": "custom-alias"}
        norm = normalize_plugin_spec(spec, "lazy")
        self.assertEqual(norm["name"], "custom-alias")
        self.assertEqual(norm["source"], "author/repo")

    def test_version_and_pin(self):
        spec = {1: "folke/noice.nvim", "version": "^1.0.0", "pin": True}
        norm = normalize_plugin_spec(spec, "lazy")
        self.assertEqual(norm["version"], "^1.0.0")
        self.assertTrue(norm["pin"])


class TestPackerNvimNormalization(unittest.TestCase):
    """Tier 1: packer.nvim specification normalization."""

    def test_packer_use_bare_string(self):
        spec = "rstacruz/vim-closer"
        norm = normalize_plugin_spec(spec, "packer")
        self.assertEqual(norm["name"], "vim-closer")
        self.assertEqual(norm["source"], "rstacruz/vim-closer")
        self.assertEqual(norm["manager"], "packer")

    def test_packer_table_with_requires_and_opt(self):
        spec = {
            1: "lewis6991/gitsigns.nvim",
            "requires": ["nvim-lua/plenary.nvim"],
            "branch": "main",
            "opt": True,
            "event": "BufRead",
        }
        norm = normalize_plugin_spec(spec, "packer")
        self.assertEqual(norm["name"], "gitsigns.nvim")
        self.assertEqual(norm["manager"], "packer")
        self.assertTrue(norm["lazy"], "opt=True should map to lazy=True")
        self.assertEqual(norm["dependencies"], ["nvim-lua/plenary.nvim"])
        self.assertEqual(norm["branch"], "main")
        self.assertEqual(norm["event"], "BufRead")

    def test_packer_disable_flag_inversion(self):
        spec = {
            1: "iamcco/markdown-preview.nvim",
            "run": "cd app && yarn install",
            "cmd": "MarkdownPreview",
            "disable": True,
        }
        norm = normalize_plugin_spec(spec, "packer")
        self.assertFalse(norm["enabled"], "disable=True should invert to enabled=False")
        self.assertEqual(norm["build"], "cd app && yarn install")
        self.assertEqual(norm["cmd"], "MarkdownPreview")

    def test_packer_lock_mapping_to_pin(self):
        spec = {1: "tpope/vim-fugitive", "lock": True}
        norm = normalize_plugin_spec(spec, "packer")
        self.assertTrue(norm["pin"], "lock=True should map to pin=True")

    def test_packer_as_custom_name(self):
        spec = {1: "wbthomason/packer.nvim", "as": "packer_core"}
        norm = normalize_plugin_spec(spec, "packer")
        self.assertEqual(norm["name"], "packer_core")


class TestVimPlugNormalization(unittest.TestCase):
    """Tier 1: vim-plug specification normalization."""

    def test_vim_plug_basic_repo(self):
        spec = "tpope/vim-sensible"
        norm = normalize_plugin_spec(spec, "plug")
        self.assertEqual(norm["name"], "vim-sensible")
        self.assertEqual(norm["source"], "tpope/vim-sensible")
        self.assertEqual(norm["manager"], "plug")
        self.assertTrue(norm["enabled"])

    def test_vim_plug_tag_and_branch(self):
        spec = {1: "fatih/vim-go", "tag": "*"}
        norm = normalize_plugin_spec(spec, "plug")
        self.assertEqual(norm["name"], "vim-go")
        self.assertEqual(norm["tag"], "*")

        spec_branch = {1: "neoclide/coc.nvim", "branch": "release"}
        norm_branch = normalize_plugin_spec(spec_branch, "plug")
        self.assertEqual(norm_branch["branch"], "release")

    def test_vim_plug_lazy_triggers_on_and_for(self):
        spec_cmd = {1: "preservim/nerdtree", "on": "NERDTreeToggle"}
        norm_cmd = normalize_plugin_spec(spec_cmd, "plug")
        self.assertTrue(norm_cmd["lazy"])
        self.assertEqual(norm_cmd["cmd"], "NERDTreeToggle")

        spec_ft = {1: "tpope/vim-fireplace", "for": "clojure"}
        norm_ft = normalize_plugin_spec(spec_ft, "plug")
        self.assertTrue(norm_ft["lazy"])
        self.assertEqual(norm_ft["ft"], "clojure")

    def test_vim_plug_do_hook_and_dir(self):
        spec = {1: "junegunn/fzf", "dir": "~/.fzf", "do": "./install --all"}
        norm = normalize_plugin_spec(spec, "plug")
        self.assertEqual(norm["name"], "fzf")
        self.assertEqual(norm["dir"], "~/.fzf")
        self.assertEqual(norm["build"], "./install --all")

    def test_vim_plug_frozen_mapping(self):
        spec = {1: "ycm-core/YouCompleteMe", "do": "./install.py", "frozen": 1}
        norm = normalize_plugin_spec(spec, "plug")
        self.assertTrue(norm["pin"], "frozen=1 should map to pin=True")


class TestBoundaryAndAdversarial(unittest.TestCase):
    """Tier 2: Boundary values, adversarial inputs, and error resilience."""

    def test_empty_spec_handling(self):
        norm = normalize_plugin_spec({})
        self.assertEqual(norm["name"], "unnamed")
        self.assertEqual(norm["source"], "")
        self.assertTrue(norm["enabled"])

    def test_none_spec_handling(self):
        norm = normalize_plugin_spec(None)
        self.assertEqual(norm["name"], "")
        self.assertEqual(norm["source"], "")

    def test_git_url_formats(self):
        urls = [
            ("https://github.com/folke/tokyonight.nvim.git", "tokyonight.nvim"),
            ("git@github.com:folke/tokyonight.nvim.git", "tokyonight.nvim"),
            ("https://gitlab.com/author/project", "project"),
            ("~/local/path/to/my-plugin", "my-plugin"),
        ]
        for url, expected_name in urls:
            norm = normalize_plugin_spec(url)
            self.assertEqual(norm["name"], expected_name)

    def test_frozen_variations(self):
        for val in (1, "1", True):
            norm = normalize_plugin_spec({1: "test/repo", "frozen": val}, "plug")
            self.assertTrue(norm["pin"])
        for val in (0, "0", False, None):
            norm = normalize_plugin_spec({1: "test/repo", "frozen": val}, "plug")
            self.assertFalse(norm["pin"])

    def test_disable_vs_enabled_priority(self):
        spec = {1: "test/repo", "disable": False}
        norm = normalize_plugin_spec(spec, "packer")
        self.assertTrue(norm["enabled"])

    def test_lazy_boundary_cond_handling(self):
        spec_disabled = {1: "author/repo", "cond": False}
        norm_disabled = normalize_plugin_spec(spec_disabled, "lazy")
        self.assertFalse(norm_disabled["enabled"])

        spec_enabled = {1: "author/repo", "cond": True}
        norm_enabled = normalize_plugin_spec(spec_enabled, "lazy")
        self.assertTrue(norm_enabled["enabled"])

    def test_packer_boundary_empty_options(self):
        spec = {1: "author/repo", "opt": False, "disable": False}
        norm = normalize_plugin_spec(spec, "packer")
        self.assertFalse(norm["lazy"])
        self.assertTrue(norm["enabled"])

    def test_vim_plug_boundary_ex_command_vs_shell_do(self):
        spec_ex = {1: "fatih/vim-go", "do": ":GoUpdateBinaries"}
        norm_ex = normalize_plugin_spec(spec_ex, "plug")
        self.assertEqual(norm_ex["build"], ":GoUpdateBinaries")

        spec_shell = {1: "junegunn/fzf", "do": "./install --all"}
        norm_shell = normalize_plugin_spec(spec_shell, "plug")
        self.assertEqual(norm_shell["build"], "./install --all")

    def test_vim_plug_boundary_plug_keys_vs_cmd(self):
        spec_key = {1: "junegunn/vim-easy-align", "on": "<Plug>(EasyAlign)"}
        norm_key = normalize_plugin_spec(spec_key, "plug")
        self.assertEqual(norm_key["keys"], "<Plug>(EasyAlign)")
        self.assertIsNone(norm_key["cmd"])

        spec_cmd = {1: "mbbill/undotree", "on": "UndotreeToggle"}
        norm_cmd = normalize_plugin_spec(spec_cmd, "plug")
        self.assertEqual(norm_cmd["cmd"], "UndotreeToggle")
        self.assertIsNone(norm_cmd["keys"])

    def test_unusual_characters_and_escaping_in_plugin_names(self):
        sources = [
            ("user/special-plugin_v2.0", "special-plugin_v2.0"),
            ("user.name/repo.name.git", "repo.name"),
            ("https://github.com/org-name/repo_with_underscore", "repo_with_underscore"),
        ]
        for src, expected_name in sources:
            norm = normalize_plugin_spec(src)
            self.assertEqual(norm["name"], expected_name)


class TestPairwiseCombinations(unittest.TestCase):
    """Tier 3: Pairwise cross-feature interactions."""

    def test_lazy_with_closure_and_table_keys(self):
        spec = {
            1: "folke/which-key.nvim",
            "event": "VeryLazy",
            "keys": [{"lhs": "<leader>?", "desc": "Buffer Local Keymaps"}],
            "opts": {"preset": "helix"},
        }
        norm = normalize_plugin_spec(spec, "lazy")
        self.assertEqual(norm["event"], "VeryLazy")
        self.assertEqual(len(norm["keys"]), 1)
        self.assertEqual(norm["opts"]["preset"], "helix")

    def test_packer_opt_with_after_and_run(self):
        spec = {
            1: "hrsh7th/nvim-cmp",
            "requires": ["hrsh7th/cmp-nvim-lsp", "hrsh7th/cmp-buffer"],
            "opt": True,
            "run": ":TSUpdate",
        }
        norm = normalize_plugin_spec(spec, "packer")
        self.assertTrue(norm["lazy"])
        self.assertEqual(len(norm["dependencies"]), 2)
        self.assertEqual(norm["build"], ":TSUpdate")

    def test_vim_plug_multi_for_and_plug_mapping(self):
        spec = {
            1: "kovisoft/paredit",
            "for": ["clojure", "scheme"],
            "on": "<Plug>(Paredit)",
            "frozen": 1,
        }
        norm = normalize_plugin_spec(spec, "plug")
        self.assertTrue(norm["lazy"])
        self.assertEqual(norm["ft"], ["clojure", "scheme"])
        self.assertEqual(norm["keys"], "<Plug>(Paredit)")
        self.assertIsNone(norm["cmd"])
        self.assertTrue(norm["pin"])


class TestFixtureFilesIntegrity(unittest.TestCase):
    """Tier 4: Real-world fixtures integrity verification."""

    def test_all_fixture_files_exist_and_readable(self):
        fixtures_root = os.path.join(os.path.dirname(__file__), "fixtures")
        expected_fixtures = [
            "lazy/single_spec.lua",
            "lazy/table_of_tables.lua",
            "lazy/bare_strings.lua",
            "lazy/complex_lazy.lua",
            "lazy/spec_imports.lua",
            "packer/packer_basic.lua",
            "packer/packer_table.lua",
            "packer/packer_disabled.lua",
            "packer/packer_multi.lua",
            "packer/packer_startup.lua",
            "plug/init.vim",
            "plug/plug_lua.lua",
            "plug/plug_embedded.lua",
            "plug/plug_complex.vim",
            "hybrid/init.lua",
            "hybrid/lua/plugins/ui.lua",
        ]
        for rel_path in expected_fixtures:
            full_path = os.path.join(fixtures_root, rel_path)
            self.assertTrue(os.path.isfile(full_path), f"Fixture not found: {rel_path}")
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertGreater(len(content), 0, f"Fixture is empty: {rel_path}")


if __name__ == "__main__":
    unittest.main()
