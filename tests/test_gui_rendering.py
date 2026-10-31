import os
import sys
import unittest

# Ensure offscreen Qt platform before importing any PyQt6 modules
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QT_GUI_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "qt_gui"))
if QT_GUI_DIR not in sys.path:
    sys.path.insert(0, QT_GUI_DIR)

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QCheckBox, QSlider, QSpinBox
from main import MainWindow
import widgets
from widgets import FieldEditor, IntegerEdit


def get_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["test_runner"])
    return app


class TestGuiRendering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = get_app()

    def setUp(self):
        self.window = MainWindow("http://127.0.0.1:37777")
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()

    def _sample_snapshot(self):
        return {
            "snapshot": {
                "config_root": "/home/wh/.config/nvim",
                "settings": [
                    {
                        "namespace": "opt",
                        "name": "number",
                        "field": {
                            "id": "opt:number:0",
                            "file": "init.lua",
                            "revision": "rev1",
                            "line": 1,
                            "value": {"kind": "boolean", "value": True},
                        },
                    },
                    {
                        "namespace": "opt",
                        "name": "shiftwidth",
                        "field": {
                            "id": "opt:shiftwidth:0",
                            "file": "init.lua",
                            "revision": "rev1",
                            "line": 2,
                            "value": {"kind": "number", "value": 4},
                        },
                    },
                    {
                        "namespace": "opt",
                        "name": "scrolloff",
                        "field": {
                            "id": "opt:scrolloff:0",
                            "file": "init.lua",
                            "revision": "rev1",
                            "line": 3,
                            "value": {"kind": "number", "value": 8},
                        },
                    },
                    {
                        "namespace": "g",
                        "name": "mapleader",
                        "field": {
                            "id": "g:mapleader:0",
                            "file": "init.lua",
                            "revision": "rev1",
                            "line": 4,
                            "value": {"kind": "string", "value": " "},
                        },
                    },
                ],
                "keymaps": [
                    {
                        "lhs": {
                            "id": "km:lhs:0",
                            "file": "init.lua",
                            "revision": "rev1",
                            "line": 10,
                            "value": {"kind": "string", "value": "<leader>ff"},
                        },
                        "mode": {
                            "id": "km:mode:0",
                            "file": "init.lua",
                            "revision": "rev1",
                            "line": 10,
                            "value": {"kind": "string", "value": "n"},
                        },
                        "rhs": {
                            "id": "km:rhs:0",
                            "file": "init.lua",
                            "revision": "rev1",
                            "line": 10,
                            "value": {"kind": "string", "value": "<cmd>Telescope find_files<cr>"},
                        },
                        "opts": {
                            "id": "km:opts:0",
                            "file": "init.lua",
                            "revision": "rev1",
                            "line": 10,
                            "value": {
                                "kind": "table",
                                "entries": [
                                    {"key": "desc", "value": {"kind": "string", "value": "Find Files"}}
                                ],
                            },
                        },
                    },
                    {
                        "lhs": {
                            "id": "km:lhs:1",
                            "file": "init.lua",
                            "revision": "rev1",
                            "line": 11,
                            "value": {"kind": "string", "value": "jk"},
                        },
                        "mode": {
                            "id": "km:mode:1",
                            "file": "init.lua",
                            "revision": "rev1",
                            "line": 11,
                            "value": {"kind": "string", "value": "i"},
                        },
                        "rhs": {
                            "id": "km:rhs:1",
                            "file": "init.lua",
                            "revision": "rev1",
                            "line": 11,
                            "value": {"kind": "string", "value": "<esc>"},
                        },
                        "opts": {
                            "id": "km:opts:1",
                            "file": "init.lua",
                            "revision": "rev1",
                            "line": 11,
                            "value": {"kind": "table", "entries": []},
                        },
                    },
                ],
                "plugins": [
                    {
                        "name": "tokyonight.nvim",
                        "source": "folke/tokyonight.nvim",
                        "manager": "lazy",
                        "enabled": {
                            "id": "plg:tokyo:enabled",
                            "file": "lua/plugins/ui.lua",
                            "revision": "rev1",
                            "line": 1,
                            "value": {"kind": "boolean", "value": True},
                        },
                        "event": {
                            "id": "plg:tokyo:event",
                            "file": "lua/plugins/ui.lua",
                            "revision": "rev1",
                            "line": 2,
                            "value": None,
                        },
                        "keys": {
                            "id": "plg:tokyo:keys",
                            "file": "lua/plugins/ui.lua",
                            "revision": "rev1",
                            "line": 3,
                            "value": None,
                        },
                        "opts": {
                            "id": "plg:tokyo:opts",
                            "file": "lua/plugins/ui.lua",
                            "revision": "rev1",
                            "line": 4,
                            "value": {
                                "kind": "table",
                                "entries": [
                                    {"key": "style", "value": {"kind": "string", "value": "storm"}}
                                ],
                            },
                        },
                    },
                    {
                        "name": "vim-closer",
                        "source": "rstacruz/vim-closer",
                        "manager": "packer",
                        "enabled": {
                            "id": "plg:closer:enabled",
                            "file": "lua/plugins.lua",
                            "revision": "rev1",
                            "line": 5,
                            "value": {"kind": "boolean", "value": True},
                        },
                        "event": {
                            "id": "plg:closer:event",
                            "file": "lua/plugins.lua",
                            "revision": "rev1",
                            "line": 6,
                            "value": None,
                        },
                        "keys": {
                            "id": "plg:closer:keys",
                            "file": "lua/plugins.lua",
                            "revision": "rev1",
                            "line": 7,
                            "value": None,
                        },
                        "opts": {
                            "id": "plg:closer:opts",
                            "file": "lua/plugins.lua",
                            "revision": "rev1",
                            "line": 8,
                            "value": None,
                        },
                    },
                    {
                        "name": "nerdtree",
                        "source": "preservim/nerdtree",
                        "manager": "plug",
                        "enabled": {
                            "id": "plg:nerdtree:enabled",
                            "file": "init.vim",
                            "revision": "rev1",
                            "line": 15,
                            "value": {"kind": "boolean", "value": True},
                        },
                        "event": {
                            "id": "plg:nerdtree:event",
                            "file": "init.vim",
                            "revision": "rev1",
                            "line": 16,
                            "value": None,
                        },
                        "keys": {
                            "id": "plg:nerdtree:keys",
                            "file": "init.vim",
                            "revision": "rev1",
                            "line": 17,
                            "value": None,
                        },
                        "opts": {
                            "id": "plg:nerdtree:opts",
                            "file": "init.vim",
                            "revision": "rev1",
                            "line": 18,
                            "value": None,
                        },
                    },
                ],
                "diagnostics": [
                    {
                        "file": "lua/plugins/broken.lua",
                        "line": 4,
                        "message": "unexpected symbol near '='",
                        "severity": "错误",
                    }
                ],
            },
            "nvim": {"connected": True, "address": "/tmp/nvim.sock"},
        }

    # 1. MainWindow Initialization Tests
    def test_main_window_initialization(self):
        self.assertEqual(self.window.windowTitle(), "Neovim 设置")
        self.assertGreaterEqual(self.window.width(), 900)
        self.assertGreaterEqual(self.window.height(), 620)
        self.assertEqual(self.window.category_list.count(), 4)
        self.assertEqual(self.window.category_list.currentRow(), 0)
        self.assertIsNotNone(self.window.centralWidget())
        self.assertIsNotNone(self.window.statusBar())

    # 2. Category & Tab Switching Tests
    def test_category_and_tab_switching(self):
        self.window._state_received(self._sample_snapshot())
        self.app.processEvents()

        # Switch to Keymaps (index 1)
        self.window.category_list.setCurrentRow(1)
        self.app.processEvents()
        self.assertEqual(self.window.stack.currentIndex(), 1)
        self.assertEqual(len(self.window.keymap_page.cards), 2)

        # Switch to Plugins (index 2)
        self.window.category_list.setCurrentRow(2)
        self.app.processEvents()
        self.assertEqual(self.window.stack.currentIndex(), 2)
        self.assertEqual(len(self.window.plugin_page.cards), 3)

        # Switch to Advanced (index 3)
        self.window.category_list.setCurrentRow(3)
        self.app.processEvents()
        self.assertEqual(self.window.stack.currentIndex(), 3)
        self.assertEqual(self.window.advanced_tabs.count(), 3)

        # Switch subtabs in Advanced
        self.window.advanced_tabs.setCurrentIndex(1)  # globals
        self.app.processEvents()
        self.window.advanced_tabs.setCurrentIndex(2)  # diagnostics
        self.app.processEvents()
        self.window.advanced_tabs.setCurrentIndex(0)  # all options
        self.app.processEvents()

        # Switch back to Common (index 0)
        self.window.category_list.setCurrentRow(0)
        self.app.processEvents()
        self.assertEqual(self.window.stack.currentIndex(), 0)

    # 3. Search Filtering Across Pages Tests
    def test_search_filtering_plugins(self):
        self.window._state_received(self._sample_snapshot())
        self.window.category_list.setCurrentRow(2)  # Plugins
        self.app.processEvents()

        # Filter by "tokyo"
        self.window.search.setText("tokyo")
        self.app.processEvents()
        visible_cards = [w for w, _ in self.window.plugin_page.cards if not w.isHidden()]
        self.assertEqual(len(visible_cards), 1)

        # Filter by "packer" or "closer"
        self.window.search.setText("closer")
        self.app.processEvents()
        visible_cards = [w for w, _ in self.window.plugin_page.cards if not w.isHidden()]
        self.assertEqual(len(visible_cards), 1)

        # Filter by non-matching string
        self.window.search.setText("non_existent_query_xyz")
        self.app.processEvents()
        visible_cards = [w for w, _ in self.window.plugin_page.cards if not w.isHidden()]
        self.assertEqual(len(visible_cards), 0)

        # Clear search
        self.window.search.setText("")
        self.app.processEvents()
        visible_cards = [w for w, _ in self.window.plugin_page.cards if not w.isHidden()]
        self.assertEqual(len(visible_cards), 3)

    def test_search_filtering_keymaps(self):
        self.window._state_received(self._sample_snapshot())
        self.window.category_list.setCurrentRow(1)  # Keymaps
        self.app.processEvents()

        self.window.search.setText("<leader>ff")
        self.app.processEvents()
        visible_cards = [w for w, _ in self.window.keymap_page.cards if not w.isHidden()]
        self.assertEqual(len(visible_cards), 1)

        self.window.search.setText("jk")
        self.app.processEvents()
        visible_cards = [w for w, _ in self.window.keymap_page.cards if not w.isHidden()]
        self.assertEqual(len(visible_cards), 1)

        self.window.search.setText("")
        self.app.processEvents()
        visible_cards = [w for w, _ in self.window.keymap_page.cards if not w.isHidden()]
        self.assertEqual(len(visible_cards), 2)

    # 4. IntegerEdit Slider & Spinbox Range Tests
    def test_integer_edit_slider_ranges(self):
        # Case A: Standard positive option (e.g. shiftwidth = 4)
        edit_pos = IntegerEdit(value=4, default=4)
        self.assertEqual(edit_pos.value(), 4)
        self.assertEqual(edit_pos.slider.minimum(), 0)
        self.assertGreaterEqual(edit_pos.slider.maximum(), 100)

        # Value change via spinbox syncs slider
        edit_pos.spin.setValue(8)
        self.assertEqual(edit_pos.slider.value(), 8)
        self.assertEqual(edit_pos.value(), 8)

        # Value change via slider syncs spinbox
        edit_pos.slider.setValue(16)
        self.assertEqual(edit_pos.spin.value(), 16)
        self.assertEqual(edit_pos.value(), 16)

        # Case B: Negative numbers allowed
        edit_neg = IntegerEdit(value=-10, default=-10)
        self.assertLess(edit_neg.slider.minimum(), 0)
        self.assertGreater(edit_neg.slider.maximum(), 0)
        self.assertEqual(edit_neg.value(), -10)

        # Case C: Extreme/out of bounds numbers dynamically expand slider range
        edit_large = IntegerEdit(value=0, default=0)
        edit_large.set_value(5000)
        self.assertGreaterEqual(edit_large.slider.maximum(), 5000)
        self.assertEqual(edit_large.value(), 5000)

        # Case D: None or invalid input falls back to 0
        edit_invalid = IntegerEdit(value=0)
        edit_invalid.set_value("invalid_str")
        self.assertEqual(edit_invalid.value(), 0)

    # 5. SwitchWidget and Boolean Toggle Tests
    def test_switch_and_checkbox_toggle_behavior(self):
        # Test custom SwitchWidget if available
        SwitchClass = getattr(widgets, "SwitchWidget", None)
        if SwitchClass is not None:
            switch = SwitchClass()
            self.assertFalse(switch.isChecked())
            switch.setChecked(True)
            self.assertTrue(switch.isChecked())
            switch.toggle()
            self.assertFalse(switch.isChecked())

        # Test FieldEditor boolean toggle
        field_data = {
            "id": "opt:number:0",
            "file": "init.lua",
            "revision": "rev1",
            "value": {"kind": "boolean", "value": True},
        }
        editor = FieldEditor("显示行号", field_data, value={"kind": "boolean", "value": True})
        self.app.processEvents()

        # In compact mode, the boolean editor is a QCheckBox or SwitchWidget
        toggle_widget = editor.editor
        self.assertIsNotNone(toggle_widget)
        if isinstance(toggle_widget, QCheckBox):
            self.assertTrue(toggle_widget.isChecked())
            self.assertEqual(toggle_widget.text(), "开启")
            toggle_widget.setChecked(False)
            self.assertEqual(toggle_widget.text(), "关闭")
            self.assertTrue(editor.dirty)

    # 6. Keymap Cards Structure Tests
    def test_keymap_card_structure(self):
        self.window._state_received(self._sample_snapshot())
        self.window.category_list.setCurrentRow(1)
        self.app.processEvents()

        # Find keymap cards
        self.assertGreaterEqual(len(self.window.keymap_page.cards), 2)
        card, search_text = self.window.keymap_page.cards[0]
        self.assertIn("<leader>ff", search_text)
        self.assertIn("普通模式", search_text)

    # 7. Plugin Cards and Manager Badges Tests
    def test_plugin_cards_multi_manager(self):
        self.window._state_received(self._sample_snapshot())
        self.window.category_list.setCurrentRow(2)
        self.app.processEvents()

        self.assertEqual(len(self.window.plugin_page.cards), 3)

        # Inspect lazy plugin card
        lazy_card, lazy_text = self.window.plugin_page.cards[0]
        self.assertIn("tokyonight.nvim", lazy_text)
        self.assertIn("folke/tokyonight.nvim", lazy_text)

        # Inspect packer plugin card
        packer_card, packer_text = self.window.plugin_page.cards[1]
        self.assertIn("vim-closer", packer_text)

        # Inspect vim-plug plugin card
        plug_card, plug_text = self.window.plugin_page.cards[2]
        self.assertIn("nerdtree", plug_text)

    # 8. Window Resizing and Responsiveness Tests
    def test_window_resizing_stability(self):
        resolutions = [(900, 620), (1040, 720), (1280, 800), (1920, 1080)]
        for width, height in resolutions:
            self.window.resize(width, height)
            self.app.processEvents()
            self.assertGreaterEqual(self.window.width(), 900)
            self.assertGreaterEqual(self.window.height(), 620)

    # 9. Stability: No-Crash & Zero Unhandled Exceptions
    def test_rapid_state_updates_no_crashes(self):
        payload = self._sample_snapshot()
        for _ in range(5):
            self.window._state_received(payload)
            self.app.processEvents()
            self.window.search.setText("test")
            self.app.processEvents()
            self.window.search.setText("")
            self.app.processEvents()

        # Empty snapshot handling
        self.window._state_received({"snapshot": {"settings": [], "keymaps": [], "plugins": [], "diagnostics": []}})
        self.app.processEvents()
        self.assertEqual(len(self.window.plugin_page.cards), 0)

    # 10. Multi-Theme Switching Tests
    def test_multi_theme_switching(self):
        from theme import PALETTES, THEME_CHOICES, ThemeManager, build_theme_qss
        from widgets import SwitchWidget

        self.assertGreaterEqual(len(THEME_CHOICES), 6)
        self.assertTrue(hasattr(self.window, "theme_selector"))
        self.assertEqual(self.window.theme_selector.count(), len(THEME_CHOICES))

        switch = SwitchWidget(checked=True)
        for idx, (theme_key, _label) in enumerate(THEME_CHOICES):
            self.window.theme_selector.setCurrentIndex(idx)
            self.app.processEvents()
            self.assertEqual(ThemeManager.instance().current_theme, theme_key)
            palette = PALETTES[theme_key]
            qss = build_theme_qss(palette)
            self.assertIn(palette["bg_dark"], qss)
            self.assertIn(palette["blue"], qss)
            self.assertEqual(switch._active_color.name().lower(), palette["blue"].lower())

        # Restore default theme
        self.window.set_theme("tokyo_night")
        self.app.processEvents()
        self.assertEqual(ThemeManager.instance().current_theme, "tokyo_night")

    # 11. M1: Ctrl+S on Inline Creation Cards (FE-P0-03) & Entity Deletion / Rollback (FE-P0-01 / BE-P1-01)
    def test_m1_ctrl_s_inline_creation_cards(self):
        self.window._state_received(self._sample_snapshot())

        # Test Ctrl+S on NewKeymapCard
        self.window.category_list.setCurrentRow(1)
        self.window.keymap_page.open_new_card()
        self.app.processEvents()
        new_km = self.window.keymap_page.new_card
        new_km.lhs_edit.setText("<leader>save")
        new_km.rhs_edit.setText(":w<CR>")
        self.app.processEvents()
        self.assertTrue(new_km.dirty)

        created_keymaps = []
        self.window.client.create_keymap = lambda mode, lhs, rhs, opts, ed: created_keymaps.append((mode, lhs, rhs, opts, ed))
        self.window._save_active_card()
        self.app.processEvents()
        self.assertEqual(len(created_keymaps), 1)
        self.assertEqual(created_keymaps[0][1]["value"], "<leader>save")
        new_km.reset_form()

        # Test Ctrl+S on NewPluginCard
        self.window.category_list.setCurrentRow(2)
        self.window.plugin_page.open_new_card()
        self.app.processEvents()
        new_plug = self.window.plugin_page.new_card
        new_plug.source_edit.setText("nvim-treesitter/nvim-treesitter")
        self.app.processEvents()
        self.assertTrue(new_plug.dirty)

        created_plugins = []
        self.window.client.create_plugin = lambda payload, ed: created_plugins.append((payload, ed))
        self.window._save_active_card()
        self.app.processEvents()
        self.assertEqual(len(created_plugins), 1)
        self.assertEqual(created_plugins[0][0]["source"], "nvim-treesitter/nvim-treesitter")
        new_plug.reset_form()

    def test_m1_entity_delete_and_rollback_ui(self):
        self.window._state_received(self._sample_snapshot())
        self.app.processEvents()

        deleted_entities = []
        self.window.client.delete_entity = lambda field, ctx=None: deleted_entities.append((field, ctx))

        # Trigger delete on KeymapCard
        self.window.category_list.setCurrentRow(1)
        self.app.processEvents()
        km_card, _ = self.window.keymap_page.cards[0]
        self.assertTrue(hasattr(km_card, "delete_button"))
        km_card.delete_button.click()
        self.app.processEvents()
        self.assertEqual(len(deleted_entities), 1)
        self.assertEqual(deleted_entities[0][1]["action"], "delete")

        # Trigger delete on PluginCard
        self.window.category_list.setCurrentRow(2)
        self.app.processEvents()
        plug_card, _ = self.window.plugin_page.cards[0]
        self.assertTrue(hasattr(plug_card, "delete_button"))
        plug_card.delete_button.click()
        self.app.processEvents()
        self.assertEqual(len(deleted_entities), 2)
        self.assertEqual(deleted_entities[1][1]["action"], "delete")

    # 12. M2: Theme Palette Contrast, Zero Inline Stylesheets, and Fast Switching (FE-P1-01)
    def test_m2_theme_palette_and_zero_inline_stylesheets(self):
        import time
        from theme import PALETTES, THEME_CHOICES, TOKYO_NIGHT_DAY, ThemeManager, build_theme_qss

        # Verify Tokyo Night Day high-contrast palette & card surfaces
        self.assertEqual(TOKYO_NIGHT_DAY["bg_card"], "#ffffff")
        self.assertEqual(TOKYO_NIGHT_DAY["bg_card_inner"], "#f4f5f9")
        self.assertEqual(TOKYO_NIGHT_DAY["fg"], "#1f2335")

        # Verify centralWidget, scrollViewport, cardsContainer object names
        self.assertEqual(self.window.centralWidget().objectName(), "centralWidget")
        self.assertEqual(self.window.common_page.viewport().objectName(), "scrollViewport")
        self.assertEqual(self.window.common_page.container.objectName(), "cardsContainer")

        # Verify zero inline setStyleSheet in widgets.py
        widgets_path = os.path.join(QT_GUI_DIR, "widgets.py")
        with open(widgets_path, "r", encoding="utf-8") as f:
            widgets_src = f.read()
        self.assertNotIn("setStyleSheet(", widgets_src)

        # Verify QSS cache and fast theme switching across all 6 themes
        self.window._state_received(self._sample_snapshot())
        self.app.processEvents()
        start_t = time.perf_counter()
        for theme_key, _label in THEME_CHOICES:
            self.window.set_theme(theme_key)
            self.app.processEvents()
            self.assertIn(theme_key, ThemeManager._QSS_CACHE)
            qss = build_theme_qss(PALETTES[theme_key])
            self.assertIn(f"QFrame#groupCard {{\n    background-color: {PALETTES[theme_key]['bg_card']};", qss)
        elapsed_ms = (time.perf_counter() - start_t) * 1000.0
        self.assertLess(elapsed_ms / len(THEME_CHOICES), 120.0)
        self.window.set_theme("tokyo_night")
        self.app.processEvents()

    # 13. M2: Global Navigation & Close Unsaved Guard (FE-P0-02)
    def test_m2_navigation_and_close_unsaved_guard(self):
        self.window._state_received(self._sample_snapshot())
        self.window.category_list.setCurrentRow(1)
        self.app.processEvents()

        km_card, _ = self.window.keymap_page.cards[0]
        km_card.rhs_edit.setText(":Telescope live_grep<CR>")
        self.app.processEvents()
        self.assertTrue(km_card.dirty)
        self.assertTrue(self.window.has_unsaved_changes())

        # Policy 1: cancel navigation and close
        self.window.unsaved_guard_policy = "cancel"
        self.window.category_list.setCurrentRow(2)
        self.app.processEvents()
        self.assertEqual(self.window.category_list.currentRow(), 1)
        self.assertEqual(self.window.stack.currentIndex(), 1)

        from PyQt6.QtGui import QCloseEvent
        close_ev = QCloseEvent()
        self.window.closeEvent(close_ev)
        self.assertFalse(close_ev.isAccepted())
        self.assertFalse(self.window._closing)

        # Policy 2: discard changes on navigation
        self.window.unsaved_guard_policy = "discard"
        self.window.category_list.setCurrentRow(2)
        self.app.processEvents()
        self.assertEqual(self.window.category_list.currentRow(), 2)
        self.assertEqual(self.window.stack.currentIndex(), 2)
        self.assertFalse(km_card.dirty)

        # Policy 3: save changes on navigation
        self.window.category_list.setCurrentRow(1)
        self.app.processEvents()
        patched = []
        self.window.client.patch = lambda field, val, ed: patched.append((field, val, ed))
        km_card.rhs_edit.setText(":w!<CR>")
        self.app.processEvents()
        self.assertTrue(km_card.dirty)
        self.window.unsaved_guard_policy = "save"
        self.window.category_list.setCurrentRow(0)
        self.app.processEvents()
        self.assertEqual(self.window.category_list.currentRow(), 0)
        self.assertEqual(len(patched), 1)
        self.window.unsaved_guard_policy = "prompt"

    # 14. M2: Auto-Save Toggle & Lightweight Undo Stack Ctrl+Z (FE-P1-02)
    def test_m2_auto_save_toggle_and_ctrl_z_undo(self):
        self.window._state_received(self._sample_snapshot())
        self.app.processEvents()

        # Disable auto-save globally
        self.window.auto_save_checkbox.setChecked(False)
        self.app.processEvents()
        self.assertFalse(self.window.auto_save_enabled)
        num_card = self.window.common_page.get_card("opt:number")
        self.assertIsNotNone(num_card)
        self.assertFalse(num_card.auto_save)
        self.assertFalse(num_card.save_button.isHidden())

        # Re-enable auto-save and test Ctrl+Z undo stack
        self.window.auto_save_checkbox.setChecked(True)
        self.app.processEvents()
        self.assertTrue(num_card.auto_save)

        patched = []
        self.window.client.patch = lambda field, val, ed: patched.append((field, val, ed))
        num_card.editor.setChecked(False)
        num_card.save()
        self.app.processEvents()
        self.assertEqual(len(patched), 1)
        self.assertEqual(patched[0][1], {"kind": "boolean", "value": False})
        self.assertGreaterEqual(len(self.window._undo_stack), 1)

        # Trigger Ctrl+Z undo
        self.window.shortcut_ctrl_z.activated.emit()
        self.app.processEvents()
        self.assertEqual(len(patched), 2)
        self.assertEqual(patched[1][1], {"kind": "boolean", "value": True})

    # 15. M2: LuaValueEditor Destructive Remove Confirmation (FE-P1-03)
    def test_m2_lua_value_editor_remove_confirmation(self):
        from widgets import LuaValueEditor

        editor = LuaValueEditor({"kind": "array", "values": [{"kind": "string", "value": "alpha"}, {"kind": "string", "value": "beta"}]})
        root = editor.tree.topLevelItem(0)
        self.assertEqual(root.childCount(), 2)
        editor.tree.setCurrentItem(root.child(0))

        # Reject confirmation -> item preserved
        editor.confirm_remove = lambda path, label: False
        editor.remove_button.click()
        self.assertEqual(len(editor._value), 2)

        # Accept confirmation -> item removed
        root = editor.tree.topLevelItem(0)
        editor.tree.setCurrentItem(root.child(0))
        editor.confirm_remove = lambda path, label: True
        editor.remove_button.click()
        self.assertEqual(len(editor._value), 1)
        self.assertEqual(editor._value[0], "beta")

    # 16. M2: NotificationBanner Offset (y=56) & Message Queue (FE-P1-04)
    def test_m2_notification_banner_offset_and_queue(self):
        banner = self.window.notification_banner
        self.window.show_notification(
            "高优先级冲突警告",
            level="warning",
            duration_ms=0,
            action_text="立即刷新",
            on_action=lambda: None,
        )
        self.app.processEvents()
        self.assertTrue(banner.isVisible())
        self.assertEqual(banner.pos().y(), 56)

        # Lower-priority info toast arriving while actionable warning is visible gets queued
        self.window.show_notification("普通后台同步提示", level="info", duration_ms=3000)
        self.app.processEvents()
        self.assertEqual(banner.message_label.text(), "高优先级冲突警告")
        self.assertEqual(banner.queue_size(), 1)

        # Dismissing warning automatically pops and displays the queued info toast
        banner.dismiss()
        self.app.processEvents()
        self.assertTrue(banner.isVisible())
        self.assertEqual(banner.message_label.text(), "普通后台同步提示")
        self.assertEqual(banner.queue_size(), 0)
        banner.dismiss()

    # 17. M2: 3-State Connection Semantics (FE-P1-05) & Card Margins / 2-Column Plugin Grid (FE-P2-01/02/03)
    def test_m2_connection_semantics_and_layout_standardization(self):
        from widgets import KeymapCard, NewKeymapCard, NewPluginCard, PluginCard

        # State 1: Daemon disconnected
        self.window._events_connected = False
        self.window._nvim_connected = False
        self.window._update_connection()
        self.assertEqual(self.window.connection_label.objectName(), "connectionOffline")

        # State 2: Daemon connected, Neovim offline (Standby / Offline edit mode)
        self.window._events_connected = True
        self.window._nvim_connected = False
        self.window._update_connection()
        self.assertEqual(self.window.connection_label.objectName(), "connectionStandby")
        self.assertIn("离线编辑模式", self.window.connection_label.text())

        # State 3: Both connected
        self.window._events_connected = True
        self.window._nvim_connected = True
        self.window._update_connection()
        self.assertEqual(self.window.connection_label.objectName(), "connectionOnline")

        # Verify standardized (14, 12, 14, 12) outer margins across cards
        self.window._state_received(self._sample_snapshot())
        km_card, _ = self.window.keymap_page.cards[0]
        plug_card, _ = self.window.plugin_page.cards[0]
        new_km = NewKeymapCard()
        new_plug = NewPluginCard()
        for card in (km_card, plug_card, new_km, new_plug):
            m = card.layout().contentsMargins()
            self.assertEqual((m.left(), m.top(), m.right(), m.bottom()), (14, 12, 14, 12))

        # Verify NewPluginCard 2-column QGridLayout
        self.assertTrue(hasattr(new_plug, "options_grid"))
        self.assertEqual(new_plug.options_grid.rowCount(), 3)
        self.assertEqual(new_plug.options_grid.columnCount(), 4)

    # 18. M3: Plugin Master-Detail Split View ("不要展开，右侧新增一栏") & Live Spec Preview
    def test_m3_plugin_master_detail_split_view(self):
        from widgets import PluginDetailPanel

        self.window._state_received(self._sample_snapshot())
        self.window.category_list.setCurrentRow(2)
        self.app.processEvents()

        plugin_page = self.window.plugin_page
        self.assertTrue(hasattr(plugin_page, "splitter"))
        self.assertIsInstance(plugin_page.detail_panel, PluginDetailPanel)
        self.assertEqual(plugin_page.splitter.count(), 2)

        # Master cards do not show inline expand accordion toggles
        cards = [c for c, _ in plugin_page.cards]
        self.assertGreaterEqual(len(cards), 3)
        for card in cards:
            self.assertFalse(card.advanced.toggle.isVisible())

        # First visible card is auto-selected and loaded into right-hand detail_panel
        first_card = cards[0]
        self.assertTrue(first_card.is_selected())
        self.assertEqual(first_card.property("selected"), "true")
        self.assertIs(plugin_page.detail_panel.current_card, first_card)
        self.assertEqual(plugin_page.detail_panel.title_label.text(), first_card.name)
        self.assertIn(first_card.source, plugin_page.detail_panel.spec_preview_label.text())

        # Clicking second card (packer.nvim) switches selection and updates right-hand inspector + preview
        second_card = cards[1]
        plugin_page.select_card(second_card)
        self.app.processEvents()
        self.assertFalse(first_card.is_selected())
        self.assertTrue(second_card.is_selected())
        self.assertEqual(plugin_page.detail_panel.title_label.text(), second_card.name)
        self.assertIn("use({", plugin_page.detail_panel.spec_preview_label.text())

        # Clicking third card (vim-plug) shows Vimscript Plug preview
        third_card = cards[2]
        plugin_page.select_card(third_card)
        self.app.processEvents()
        self.assertEqual(plugin_page.detail_panel.title_label.text(), third_card.name)
        self.assertIn("Plug '", plugin_page.detail_panel.spec_preview_label.text())

    # 19. M3: Global UI Zoom Scaling & Resizable Splitters ("让界面可以缩放")
    def test_m3_ui_scaling_and_resizable_splitters(self):
        from theme import ThemeManager

        mgr = ThemeManager.instance()
        try:
            self.window.set_ui_scale(1.25)
            self.app.processEvents()
            self.assertAlmostEqual(mgr.current_scale, 1.25)
            self.assertEqual(self.window.scale_selector.currentData(), 1.25)
            self.assertIn("font-size: 16px", self.app.styleSheet())

            mgr.zoom_in(self.app)
            self.assertAlmostEqual(mgr.current_scale, 1.4)
            mgr.zoom_out(self.app)
            self.assertAlmostEqual(mgr.current_scale, 1.25)
            mgr.reset_zoom(self.app)
            self.assertAlmostEqual(mgr.current_scale, 1.0)

            # Both main sidebar splitter and plugin master-detail splitter are non-collapsible & resizable
            self.assertFalse(self.window.main_splitter.childrenCollapsible())
            self.assertFalse(self.window.plugin_page.splitter.childrenCollapsible())
        finally:
            mgr.reset_zoom(self.app)

    # 20. M3: Lazy Tab Rendering (PERF-P0-01) & Chunked All-Options Pagination (PERF-P2-01)
    def test_m3_lazy_tab_rendering_and_chunked_options(self):
        # Populate 60 synthetic schema options
        self.window.schema_options = [
            {"name": f"synthetic_opt_{i}", "type": "boolean", "default": False}
            for i in range(60)
        ]
        self.window.category_list.setCurrentRow(0)
        self.window._state_received(self._sample_snapshot())

        # While on tab 0, tabs 1, 2, 3 are marked dirty (deferred until visited or queried)
        self.assertIn(1, self.window._dirty_pages)
        self.assertIn(2, self.window._dirty_pages)
        self.assertIn(3, self.window._dirty_pages)

        # Switching to tab 3 materializes advanced options with chunked pagination
        self.window.category_list.setCurrentRow(3)
        self.app.processEvents()
        self.assertNotIn(3, self.window._dirty_pages)
        load_more_btn = self.window.all_options_page.get_card("opt:__load_more__")
        self.assertIsNotNone(load_more_btn)
        self.assertIn("加载更多原生选项", load_more_btn.text())

        # Clicking load more loads the remaining options and removes the button
        load_more_btn.click()
        self.app.processEvents()
        self.assertIsNone(self.window.all_options_page.get_card("opt:__load_more__"))

    # 21. Material Design 3 (MD3) Design System & Structured Interactions
    def test_md3_design_system_and_structured_interactions(self):
        from theme import THEMES, ThemeManager
        from widgets import FieldEditor

        mgr = ThemeManager.instance()
        try:
            self.window._state_received(self._sample_snapshot())
            # Verify MD3 official palettes exist and switch cleanly
            self.assertIn("md3_dark", THEMES)
            self.assertIn("md3_light", THEMES)
            self.assertTrue(self.window.set_theme("md3_dark"))
            self.app.processEvents()
            self.assertEqual(mgr.current_theme, "md3_dark")
            self.assertIn("md_secondary_container", mgr.palette)

            # Verify Navigation Drawer items have M3 geometric icons
            for i in range(self.window.category_list.count()):
                item = self.window.category_list.item(i)
                self.assertFalse(item.icon().isNull())

            # Verify PluginDetailPanel uses 4 structured M3 Secondary Tabs and hides per-slot save buttons
            self.window.category_list.setCurrentRow(2)
            self.app.processEvents()
            detail = self.window.plugin_page.detail_panel
            self.assertEqual(detail.inspector_tabs.count(), 4)
            self.assertEqual(detail.inspector_tabs.tabText(0), "参数与状态")
            self.assertEqual(detail.inspector_tabs.tabText(1), "按需触发")
            self.assertEqual(detail.inspector_tabs.tabText(2), "版本与构建")
            self.assertEqual(detail.inspector_tabs.tabText(3), "代码预览")
            slot_editors = detail.findChildren(FieldEditor)
            self.assertGreater(len(slot_editors), 0)
            for se in slot_editors:
                self.assertFalse(se.show_save_button)
                self.assertTrue(se.save_button.isHidden())

            # Verify in-place FieldEditor reuse when switching between plugin cards
            cards = list(self.window.plugin_page.card_registry.values())
            if len(cards) >= 2:
                self.window.plugin_page.select_card(cards[0])
                first_editors = dict(detail._cached_slot_editors)
                self.window.plugin_page.select_card(cards[1])
                second_editors = dict(detail._cached_slot_editors)
                self.assertEqual(first_editors, second_editors)

            # Verify zero emojis / decorative Unicode symbols in qt_gui/*.py
            import glob
            for py_path in sorted(glob.glob("qt_gui/*.py")):
                with open(py_path, "r", encoding="utf-8") as fh:
                    text = fh.read()
                for ch in text:
                    cp = ord(ch)
                    if cp > 127:
                        is_allowed_cjk_or_punct = (
                            0x4E00 <= cp <= 0x9FFF
                            or 0x3000 <= cp <= 0x303F
                            or 0xFF00 <= cp <= 0xFFEF
                            or ch in "—–…·×“”‘’"
                        )
                        self.assertTrue(
                            is_allowed_cjk_or_punct,
                            f"Unexpected emoji/symbol {ch!r} (U+{cp:04X}) in {py_path}",
                        )

            # Verify dirty="false" at rest on clean cards, transitioning to dirty="true" when edited
            self.window.category_list.setCurrentRow(0)
            self.app.processEvents()
            num_card = self.window.common_page.get_card("opt:shiftwidth")
            self.assertIsNotNone(num_card)
            self.assertEqual(num_card.save_button.property("dirty"), "false")
            num_card.editor.spin.setValue(8)
            self.app.processEvents()
            self.assertEqual(num_card.save_button.property("dirty"), "true")
        finally:
            self.window.set_theme("tokyo_night")
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
