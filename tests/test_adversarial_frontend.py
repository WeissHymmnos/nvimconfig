import copy
import json
import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QT_GUI_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "qt_gui"))
if QT_GUI_DIR not in sys.path:
    sys.path.insert(0, QT_GUI_DIR)

from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtWidgets import QApplication, QLabel, QLineEdit, QPushButton, QWidget
from client import ApiClient
from main import COMMON_OPTIONS, MainWindow
from widgets import (
    FieldEditor,
    IntegerEdit,
    KeymapCard,
    NotificationBanner,
    OfflineHeroCard,
    PluginCard,
    SwitchWidget,
)


def get_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["adversarial_test_runner"])
    return app


def create_rich_snapshot(plugin_count=15, keymap_count=15, setting_count=15):
    """Generate a rich, multi-manager snapshot for stress testing."""
    managers = ["lazy", "packer", "plug"]
    plugins = []
    for i in range(plugin_count):
        mgr = managers[i % 3]
        plugins.append({
            "name": f"plugin_{mgr}_{i}",
            "source": f"author_{i}/repo_{i}",
            "manager": mgr,
            "file": f"lua/plugins/{mgr}_{i}.lua",
            "line": i * 10 + 1,
            "enabled": {
                "id": f"plg:{i}:enabled",
                "file": f"lua/plugins/{mgr}_{i}.lua",
                "revision": "rev_init",
                "line": i * 10 + 1,
                "value": {"kind": "boolean", "value": (i % 2 == 0)},
            },
            "branch": {
                "id": f"plg:{i}:branch",
                "file": f"lua/plugins/{mgr}_{i}.lua",
                "revision": "rev_init",
                "line": i * 10 + 2,
                "value": {"kind": "string", "value": f"v{i}.0-dev"} if i % 3 == 0 else None,
            },
            "tag": {
                "id": f"plg:{i}:tag",
                "file": f"lua/plugins/{mgr}_{i}.lua",
                "revision": "rev_init",
                "line": i * 10 + 3,
                "value": {"kind": "string", "value": f"v1.{i}.0"} if i % 4 == 0 else None,
            },
            "pin": {
                "id": f"plg:{i}:pin",
                "file": f"lua/plugins/{mgr}_{i}.lua",
                "revision": "rev_init",
                "line": i * 10 + 4,
                "value": {"kind": "boolean", "value": True} if i % 5 == 0 else None,
            },
            "lazy": {
                "id": f"plg:{i}:lazy",
                "file": f"lua/plugins/{mgr}_{i}.lua",
                "revision": "rev_init",
                "line": i * 10 + 5,
                "value": {"kind": "boolean", "value": True} if i % 2 == 0 else None,
            },
            "event": {
                "id": f"plg:{i}:event",
                "file": f"lua/plugins/{mgr}_{i}.lua",
                "revision": "rev_init",
                "line": i * 10 + 6,
                "value": {"kind": "string", "value": "BufReadPost"} if i % 2 == 0 else None,
            },
            "keys": {
                "id": f"plg:{i}:keys",
                "file": f"lua/plugins/{mgr}_{i}.lua",
                "revision": "rev_init",
                "line": i * 10 + 7,
                "value": None,
            },
            "opts": {
                "id": f"plg:{i}:opts",
                "file": f"lua/plugins/{mgr}_{i}.lua",
                "revision": "rev_init",
                "line": i * 10 + 8,
                "value": {
                    "kind": "table",
                    "entries": [
                        {"key": "timeout", "value": {"kind": "number", "value": 1000 + i}},
                        {"key": "enable_feature", "value": {"kind": "boolean", "value": True}},
                    ],
                },
            },
        })

    modes = ["n", "i", "v", "x", "c", "t"]
    keymaps = []
    for i in range(keymap_count):
        mode = modes[i % len(modes)]
        keymaps.append({
            "lhs": {
                "id": f"km:lhs:{i}",
                "file": "lua/keymaps.lua",
                "revision": "rev_init",
                "line": 10 + i,
                "value": {"kind": "string", "value": f"<leader>k{i}"},
            },
            "mode": {
                "id": f"km:mode:{i}",
                "file": "lua/keymaps.lua",
                "revision": "rev_init",
                "line": 10 + i,
                "value": {"kind": "string", "value": mode},
            },
            "rhs": {
                "id": f"km:rhs:{i}",
                "file": "lua/keymaps.lua",
                "revision": "rev_init",
                "line": 10 + i,
                "value": {"kind": "string", "value": f":echo 'Triggered keymap {i}'<CR>"},
            },
            "opts": {
                "id": f"km:opts:{i}",
                "file": "lua/keymaps.lua",
                "revision": "rev_init",
                "line": 10 + i,
                "value": {
                    "kind": "table",
                    "entries": [
                        {"key": "silent", "value": {"kind": "boolean", "value": True}},
                        {"key": "desc", "value": {"kind": "string", "value": f"Keymap action {i}"}},
                    ],
                },
            },
        })

    settings = []
    for i, (name, title, desc) in enumerate(COMMON_OPTIONS):
        if name in ("shiftwidth", "tabstop", "scrolloff"):
            val = 4
            kind = "number"
        else:
            val = True if i % 2 == 0 else False
            kind = "boolean"
        settings.append({
            "namespace": "opt",
            "name": name,
            "field": {
                "id": f"opt:{name}:0",
                "file": "init.lua",
                "revision": "rev_init",
                "line": i + 1,
                "value": {"kind": kind, "value": val},
            },
        })

    for i in range(setting_count):
        settings.append({
            "namespace": "g",
            "name": f"custom_var_{i}",
            "field": {
                "id": f"g:custom_var_{i}:0",
                "file": "lua/globals.lua",
                "revision": "rev_init",
                "line": i + 50,
                "value": {"kind": "string", "value": f"val_{i}"},
            },
        })

    return {
        "snapshot": {
            "config_root": "/home/wh/.config/nvim",
            "settings": settings,
            "keymaps": keymaps,
            "plugins": plugins,
            "diagnostics": [
                {
                    "file": "lua/test.lua",
                    "line": 42,
                    "severity": "警告",
                    "message": "Unused local variable 'temp'",
                }
            ],
        },
        "nvim": {"connected": True, "address": "/tmp/nvim.sock"},
    }


class TestAdversarialResizingAndLayout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = get_app()

    def setUp(self):
        self.window = MainWindow("http://127.0.0.1:37777")
        self.window.show()
        self.payload = create_rich_snapshot(plugin_count=12, keymap_count=12)
        self.window._state_received(self.payload)
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()

    def test_rapid_window_resizing_range(self):
        """Stress test rapid window resizing from 900x620 up to 3840x2160 and extreme aspects."""
        resolutions = [
            (900, 620),     # Minimum configured
            (1024, 768),    # Standard XGA
            (1280, 720),    # 720p HD
            (1366, 768),    # Laptop HD
            (1440, 900),    # WXGA+
            (1600, 900),    # HD+
            (1920, 1080),   # 1080p FHD
            (2560, 1440),   # 1440p 2K QHD
            (3440, 1440),   # Ultrawide 21:9
            (3840, 2160),   # 4K UHD
            (3840, 620),    # Extreme wide / narrow height
            (900, 2160),    # Extreme vertical / narrow width
            (900, 620),     # Back to minimum
        ]

        # Rapid looping across resolutions
        for width, height in resolutions:
            self.window.resize(width, height)
            self.app.processEvents()

            self.assertGreaterEqual(self.window.width(), 900)
            self.assertGreaterEqual(self.window.height(), 620)
            self.assertTrue(self.window.centralWidget().isVisible())

        # Test sub-minimum requests to verify window enforces minimumSize constraints
        sub_minimums = [(640, 480), (800, 600), (400, 300), (100, 100)]
        for width, height in sub_minimums:
            self.window.resize(width, height)
            self.app.processEvents()
            # Must remain clamped at or above 900x620
            self.assertGreaterEqual(self.window.width(), 900)
            self.assertGreaterEqual(self.window.height(), 620)

    def test_zero_component_overlap(self):
        """Verify zero overlap between sibling components at min (900x620) and max (3840x2160)."""
        test_sizes = [(900, 620), (1920, 1080), (3840, 2160)]

        for w, h in test_sizes:
            self.window.resize(w, h)
            self.app.processEvents()

            # 1. Top bar: connection_label and search bar
            conn_rect = self.window.connection_label.geometry()
            search_rect = self.window.search.geometry()
            self.assertLess(
                conn_rect.right(),
                search_rect.left(),
                f"Top bar components overlap at resolution {w}x{h}: connection_label right={conn_rect.right()}, search left={search_rect.left()}"
            )

            # 2. Keymap Cards (Category 1)
            self.window.category_list.setCurrentRow(1)
            self.app.processEvents()
            keymap_cards = [c for c, _ in self.window.keymap_page.cards if isinstance(c, KeymapCard)]
            self.assertGreater(len(keymap_cards), 0)
            for card in keymap_cards[:3]:
                # Verify Row 1: lhs_edit and mode_combo don't overlap
                lhs_rect = card.lhs_edit.geometry()
                mode_rect = card.mode_combo.geometry()
                self.assertLessEqual(lhs_rect.right(), mode_rect.left())

                # Verify Footer: status_label and save_button don't overlap
                status_rect = card.status_label.geometry()
                save_rect = card.save_button.geometry()
                self.assertLessEqual(status_rect.right(), save_rect.left())

                # Verify vertical ordering: row 1 above row 2, row 2 above footer
                rhs_rect = card.rhs_edit.geometry()
                self.assertLessEqual(lhs_rect.bottom(), rhs_rect.top())
                self.assertLessEqual(rhs_rect.bottom(), save_rect.top())

            # 3. Plugin Cards (Category 2)
            self.window.category_list.setCurrentRow(2)
            self.app.processEvents()
            plugin_cards = [c for c, _ in self.window.plugin_page.cards if isinstance(c, PluginCard)]
            self.assertGreater(len(plugin_cards), 0)
            for card in plugin_cards[:3]:
                # Title, badge, and repo button
                title_rect = card.title_label.geometry()
                badge_rect = card.badge_label.geometry()
                repo_rect = card.repo_btn.geometry()

                self.assertLessEqual(title_rect.right(), badge_rect.left())
                if card.chips_layout.count() > 0:
                    chip_first = card.chips_layout.itemAt(0).widget()
                    if chip_first and chip_first.isVisible():
                        self.assertLessEqual(badge_rect.right(), chip_first.geometry().left())
                self.assertGreater(repo_rect.left(), badge_rect.right())

            # 4. Notification Banner repositioning
            self.window.show_notification("测试通知横幅无重叠", level="info")
            self.app.processEvents()
            banner = self.window.notification_banner
            self.assertTrue(banner.isVisible())
            banner_rect = banner.geometry()
            self.assertGreaterEqual(banner_rect.left(), 0)
            self.assertLessEqual(banner_rect.right(), self.window.width())

    def test_zero_text_truncation_across_sizes(self):
        """Verify no unintended text truncation in labels and buttons."""
        test_sizes = [(900, 620), (1280, 720), (1920, 1080), (3840, 2160)]

        for w, h in test_sizes:
            self.window.resize(w, h)
            self.app.processEvents()

            for cat_idx in range(len(self.window.pages)):
                self.window.category_list.setCurrentRow(cat_idx)
                self.app.processEvents()
                page = self.window.pages[cat_idx]

                # Inspect all labels
                for label in page.findChildren(QLabel):
                    if not label.isVisible():
                        continue
                    text = label.text().strip()
                    if not text or len(text) < 2:
                        continue

                    # If label is not word wrapped, text must fit within geometry
                    if not label.wordWrap():
                        metrics = label.fontMetrics()
                        text_width = metrics.horizontalAdvance(text)
                        label_width = label.width()
                        # Allow 8px margin / layout buffer
                        if label_width > 0 and text_width > label_width + 8:
                            # Verify if parent is inside a layout that elides or if it's clipped
                            self.fail(
                                f"Label text '{text}' (width={text_width}px) truncated in label (width={label_width}px) on category {cat_idx} at {w}x{h}"
                            )


class TestAdversarialInteractions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = get_app()

    def setUp(self):
        self.window = MainWindow("http://127.0.0.1:37777")
        self.window.show()
        self.payload = create_rich_snapshot(plugin_count=15, keymap_count=15)
        self.window._state_received(self.payload)
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()

    def test_rapid_category_switching_and_shortcuts(self):
        """Rapidly toggle categories sequentially and via Ctrl+1..4 shortcuts."""
        import random
        random.seed(42)

        # 1. Rapid direct switching
        for _ in range(60):
            target = random.randint(0, 3)
            self.window.category_list.setCurrentRow(target)
            self.app.processEvents()
            self.assertEqual(self.window.stack.currentIndex(), target)

        # 2. Rapid shortcut switching
        for _ in range(40):
            target = random.randint(0, 3)
            sc = self.window.category_shortcuts[target]
            sc.activated.emit()
            self.app.processEvents()
            self.assertEqual(self.window.stack.currentIndex(), target)
            self.assertEqual(self.window.category_list.currentRow(), target)

        # 3. Rapid subtab switching on Advanced page (index 3)
        self.window.category_list.setCurrentRow(3)
        self.app.processEvents()
        for _ in range(30):
            subtab = random.randint(0, 2)
            self.window.advanced_tabs.setCurrentIndex(subtab)
            self.app.processEvents()
            self.assertEqual(self.window.advanced_tabs.currentIndex(), subtab)

    def test_rapid_search_typing_and_esc_clearing(self):
        """Stress test search typing, unicode queries, special characters, and Esc clearing."""
        queries = [
            "shift",
            "plugin_lazy",
            "packer",
            "plug",
            "<leader>",
            "custom_var",
            "未命名",
            "不存在的搜索词_XYZ_12345",
            ".*",
            "[a-z]+",
            "'; DROP TABLE plugins; --",
            "\\",
            "\"quoted\"",
            "   padded spaces   ",
            "a" * 300,  # Long query
        ]

        for query in queries:
            for cat_idx in [0, 1, 2, 3]:
                self.window.category_list.setCurrentRow(cat_idx)
                self.window.search.setText(query)
                self.app.processEvents()

                # Verify no crashes
                page = self.window.stack.currentWidget()
                self.assertIsNotNone(page)

                # Test Esc clearing
                self.window.shortcut_esc.activated.emit()
                self.app.processEvents()
                self.assertEqual(self.window.search.text(), "")

    def test_plugin_filter_tab_toggling_and_empty_placeholder(self):
        """Stress test plugin manager tabs, counts, and search placeholder clear."""
        self.window.category_list.setCurrentRow(2)  # Plugins
        self.app.processEvents()

        filter_bar = self.window.plugin_page.filter_bar
        scroll_area = self.window.plugin_page.scroll_area

        # Verify initial manager counts: 15 total / 3 = 5 each
        self.assertEqual(filter_bar.current_filter, "all")
        counts = {
            "all": len(scroll_area.cards),
            "lazy": sum(1 for c, _ in scroll_area.cards if getattr(c, "manager", "") == "lazy"),
            "packer": sum(1 for c, _ in scroll_area.cards if getattr(c, "manager", "") == "packer"),
            "plug": sum(1 for c, _ in scroll_area.cards if getattr(c, "manager", "") == "plug"),
        }
        self.assertEqual(counts["lazy"], 5)
        self.assertEqual(counts["packer"], 5)
        self.assertEqual(counts["plug"], 5)

        # Rapidly toggle filter tabs
        for mgr in ["lazy", "packer", "plug", "all", "packer", "lazy", "plug", "all"]:
            filter_bar.set_filter(mgr)
            self.app.processEvents()
            self.assertEqual(filter_bar.current_filter, mgr)
            visible_cards = [c for c, _ in scroll_area.cards if c.isVisible()]
            expected_count = counts["all"] if mgr == "all" else counts[mgr]
            self.assertEqual(len(visible_cards), expected_count)

        # Trigger EmptySearchPlaceholder on non-matching query
        filter_bar.set_filter("lazy")
        self.window.search.setText("packer")
        self.app.processEvents()

        # No lazy plugins match "packer" -> search_empty placeholder visible
        self.assertTrue(scroll_area.search_empty.isVisible())
        self.assertEqual(len([c for c, _ in scroll_area.cards if c.isVisible()]), 0)

        # Click clear button on EmptySearchPlaceholder
        scroll_area.search_empty.clear_btn.click()
        self.app.processEvents()

        # Search should be cleared, lazy plugins restored
        self.assertEqual(self.window.search.text(), "")
        self.assertFalse(scroll_area.search_empty.isVisible())
        self.assertEqual(len([c for c, _ in scroll_area.cards if c.isVisible()]), counts["lazy"])


class TestAdversarialStateSync(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = get_app()

    def setUp(self):
        self.window = MainWindow("http://127.0.0.1:37777")
        self.window.show()
        self.payload = create_rich_snapshot(plugin_count=20, keymap_count=20)
        self.window._state_received(self.payload)
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()

    def test_scrollbar_stability_during_rapid_sse_arrivals(self):
        """Verify scrollbar position does not jump to 0 during rapid background SSE updates."""
        # Scroll down in Plugins page
        self.window.category_list.setCurrentRow(2)
        self.app.processEvents()

        scroll_bar = self.window.plugin_page.verticalScrollBar()
        scroll_bar.setMaximum(2000)
        scroll_bar.setValue(450)
        self.app.processEvents()
        self.assertEqual(scroll_bar.value(), 450)

        # Simulate 25 rapid background state arrivals
        for i in range(25):
            modified_payload = copy.deepcopy(self.payload)
            # Subtle backend modification (e.g. revision change on a setting)
            modified_payload["snapshot"]["settings"][0]["field"]["revision"] = f"rev_{i}"
            self.window._state_received(modified_payload)
            self.app.processEvents()

            # Scroll position must be retained
            self.assertEqual(
                self.window.plugin_page.verticalScrollBar().value(),
                450,
                f"Scrollbar position lost on SSE iteration {i}"
            )

    def test_accordion_expansion_retention_during_sse_arrivals(self):
        """Verify expanded collapsible sections and keymap opts remain open across background updates."""
        # 1. Expand plugin collapsible section
        self.window.category_list.setCurrentRow(2)
        self.app.processEvents()
        first_plugin_card = self.window.plugin_page.cards[0][0]
        self.assertIsInstance(first_plugin_card, PluginCard)
        first_plugin_card.advanced.toggle.setChecked(True)
        self.app.processEvents()
        self.assertTrue(first_plugin_card.advanced.toggle.isChecked())
        self.assertTrue(first_plugin_card.advanced.content.isVisible())

        # 2. Expand keymap advanced options
        self.window.category_list.setCurrentRow(1)
        self.app.processEvents()
        first_keymap_card = self.window.keymap_page.cards[0][0]
        self.assertIsInstance(first_keymap_card, KeymapCard)
        first_keymap_card.toggle_opts_btn.click()
        self.app.processEvents()
        self.assertFalse(first_keymap_card.opts_container.isHidden())

        # 3. Simulate 20 rapid background SSE arrivals
        for i in range(20):
            modified_payload = copy.deepcopy(self.payload)
            self.window._state_received(modified_payload)
            self.app.processEvents()

            # Verify accordions retain their open state
            self.assertTrue(
                first_plugin_card.advanced.toggle.isChecked(),
                f"Plugin accordion collapsed on iteration {i}"
            )
            self.assertFalse(
                first_plugin_card.advanced.content.isHidden(),
                f"Plugin accordion content hidden on iteration {i}"
            )
            self.assertFalse(
                first_keymap_card.opts_container.isHidden(),
                f"Keymap options collapsed on iteration {i}"
            )

        # Switch to plugins page and verify it is visibly rendered
        self.window.category_list.setCurrentRow(2)
        self.app.processEvents()
        self.assertTrue(first_plugin_card.advanced.content.isVisible())

    def test_active_user_editing_and_focus_preservation_during_sse(self):
        """Verify dirty edits and focused widgets are not overwritten by background SSE arrivals."""
        # Focus Common page and edit a field
        self.window.category_list.setCurrentRow(0)
        self.app.processEvents()

        # Find shiftwidth or number editor
        editor = None
        for card, _ in self.window.common_page.cards:
            if isinstance(card, FieldEditor) and card.technical_name == "shiftwidth":
                editor = card
                break
        self.assertIsNotNone(editor)

        # Simulate user edit
        self.assertIsInstance(editor.editor, IntegerEdit)
        editor.editor.set_value(16)
        self.app.processEvents()
        self.assertTrue(editor.dirty)
        self.assertEqual(editor.editor.value(), 16)

        # Background SSE arrival with original server value (4)
        for i in range(15):
            modified_payload = copy.deepcopy(self.payload)
            # Server says shiftwidth is 4
            for s in modified_payload["snapshot"]["settings"]:
                if s["name"] == "shiftwidth":
                    s["field"]["value"]["value"] = 4
                    s["field"]["revision"] = f"rev_{i}"
            self.window._state_received(modified_payload)
            self.app.processEvents()

            # User's edit must NOT be overwritten!
            self.assertTrue(editor.dirty)
            self.assertEqual(editor.editor.value(), 16)

        # Test KeymapCard active editing preservation
        self.window.category_list.setCurrentRow(1)
        self.app.processEvents()
        km_card = self.window.keymap_page.cards[0][0]
        self.assertIsInstance(km_card, KeymapCard)

        km_card.lhs_edit.setText("<leader>custom_edit")
        self.app.processEvents()
        self.assertTrue(km_card.dirty)

        for i in range(10):
            self.window._state_received(self.payload)
            self.app.processEvents()

            self.assertTrue(km_card.dirty)
            self.assertEqual(km_card.lhs_edit.text(), "<leader>custom_edit")


class TestAdversarialOfflineRecovery(unittest.TestCase):
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

    def test_initial_offline_detection_and_hero_card_countdown(self):
        """Verify OfflineHeroCard is shown when daemon is unreachable on launch, and retry works."""
        # Initial launch failure
        self.assertFalse(self.window._has_received_state)
        self.window._request_error("Connection refused to 127.0.0.1:37777")
        self.app.processEvents()

        # Offline Hero Card must be current stack widget
        self.assertIs(self.window.stack.currentWidget(), self.window.offline_hero)
        self.assertTrue(self.window.offline_hero.isVisible())
        self.assertIn("无法连接配置服务", self.window.offline_hero.error_label.text())

        # Verify countdown active
        self.assertEqual(self.window.offline_hero._countdown, 5)
        self.assertIn("5 秒后自动尝试重新连接", self.window.offline_hero.countdown_label.text())

        # Simulate countdown tick
        self.window.offline_hero._tick()
        self.assertEqual(self.window.offline_hero._countdown, 4)
        self.assertIn("4 秒后自动尝试重新连接", self.window.offline_hero.countdown_label.text())

        # Test manual retry button click
        retry_called = []
        self.window.offline_hero.retry_requested.connect(lambda: retry_called.append(True))
        self.window.offline_hero.retry_btn.click()
        self.app.processEvents()
        self.assertTrue(len(retry_called) > 0)

        # Simulate server coming online
        payload = create_rich_snapshot(plugin_count=5, keymap_count=5)
        self.window._state_received(payload)
        self.app.processEvents()

        # Must switch back from offline hero to category 0
        self.assertTrue(self.window._has_received_state)
        self.assertIsNot(self.window.stack.currentWidget(), self.window.offline_hero)
        self.assertEqual(self.window.stack.currentIndex(), self.window.category_list.currentRow())
        self.assertEqual(self.window.offline_hero.countdown_label.text(), "")
        self.assertFalse(self.window.offline_hero._timer.isActive())

    def test_runtime_disconnection_shows_toast_banner(self):
        """Verify runtime disconnection shows non-disruptive toast rather than full screen hijacking."""
        # Connect first
        payload = create_rich_snapshot(plugin_count=5, keymap_count=5)
        self.window._state_received(payload)
        self.app.processEvents()
        self.assertTrue(self.window._has_received_state)

        # Runtime connection loss
        self.window._request_error("HTTP 502 Bad Gateway / Connection lost")
        self.app.processEvents()

        # Stack must NOT be hijacked to OfflineHeroCard
        self.assertIsNot(self.window.stack.currentWidget(), self.window.offline_hero)
        self.assertTrue(self.window.notification_banner.isVisible())
        self.assertIn("无法连接配置服务", self.window.notification_banner.message_label.text())

        # Offline connection status label
        self.window._events_status("连接已断开")
        self.app.processEvents()
        self.assertEqual(self.window.connection_label.objectName(), "connectionOffline")

        # Reconnection
        self.window._events_status("已连接至后台事件流")
        payload["nvim"]["connected"] = True
        self.window._state_received(payload)
        self.app.processEvents()
        self.assertEqual(self.window.connection_label.objectName(), "connectionOnline")

    def test_409_conflict_notification_banner_action(self):
        """Verify 409 conflict shows persistent toast with actionable refresh button."""
        payload = create_rich_snapshot(plugin_count=5, keymap_count=5)
        self.window._state_received(payload)
        self.app.processEvents()

        # Simulate 409 conflict
        refresh_called = []
        original_refresh = self.window.refresh
        self.window.refresh = lambda: refresh_called.append(True)
        try:
            self.window._request_error("HTTP 409 Conflict: revision mismatch on patch")
            self.app.processEvents()

            banner = self.window.notification_banner
            self.assertTrue(banner.isVisible())
            self.assertEqual(banner.property("level"), "warning")
            self.assertTrue(banner.action_btn.isVisible())
            self.assertIn("立即刷新", banner.action_btn.text())

            # Click action button
            banner.action_btn.click()
            self.app.processEvents()
            self.assertTrue(len(refresh_called) > 0)
            self.assertFalse(banner.isVisible())
        finally:
            self.window.refresh = original_refresh

    def test_keyboard_shortcuts_execution(self):
        """Verify F5/Ctrl+R refresh, Ctrl+F focus, Ctrl+S save shortcuts."""
        # F5
        f5_called = []
        original_refresh = self.window.refresh
        self.window.refresh = lambda: f5_called.append(True)
        try:
            self.window.shortcut_f5.activated.emit()
            self.app.processEvents()
            self.assertTrue(len(f5_called) > 0)

            # Ctrl+R
            ctrl_r_called = []
            self.window.refresh = lambda: ctrl_r_called.append(True)
            self.window.shortcut_ctrl_r.activated.emit()
            self.app.processEvents()
            self.assertTrue(len(ctrl_r_called) > 0)
        finally:
            self.window.refresh = original_refresh

        # Ctrl+F
        self.window.search.clearFocus()
        self.assertFalse(self.window.search.hasFocus())
        self.window.shortcut_ctrl_f.activated.emit()
        self.app.processEvents()
        self.assertTrue(self.window.search.hasFocus())

    def test_dynamic_card_deletion_and_empty_state_recovery(self):
        """Verify in-place removal of cards when deleted on disk and empty label restoration."""
        payload = create_rich_snapshot(plugin_count=4, keymap_count=4)
        self.window._state_received(payload)
        self.window.category_list.setCurrentRow(2)  # Plugins
        self.app.processEvents()

        self.assertEqual(len(self.window.plugin_page.cards), 4)
        self.assertFalse(self.window.plugin_page.scroll_area.empty_label.isVisible())

        # Simulate deletion of 2 plugins from snapshot
        reduced_payload = copy.deepcopy(payload)
        reduced_payload["snapshot"]["plugins"] = reduced_payload["snapshot"]["plugins"][:2]
        self.window._state_received(reduced_payload)
        self.app.processEvents()

        self.assertEqual(len(self.window.plugin_page.cards), 2)
        self.assertFalse(self.window.plugin_page.scroll_area.empty_label.isVisible())

        # Simulate deletion of ALL plugins
        empty_payload = copy.deepcopy(payload)
        empty_payload["snapshot"]["plugins"] = []
        self.window._state_received(empty_payload)
        self.app.processEvents()

        self.assertEqual(len(self.window.plugin_page.cards), 0)
        self.assertTrue(self.window.plugin_page.scroll_area.empty_label.isVisible())

        # Restore plugins
        self.window._state_received(payload)
        self.app.processEvents()
        self.assertEqual(len(self.window.plugin_page.cards), 4)
        self.assertFalse(self.window.plugin_page.scroll_area.empty_label.isVisible())


if __name__ == "__main__":
    unittest.main()

