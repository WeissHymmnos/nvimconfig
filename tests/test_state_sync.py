import copy
import json
import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QT_GUI_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "qt_gui"))
if QT_GUI_DIR not in sys.path:
    sys.path.insert(0, QT_GUI_DIR)

from PyQt6.QtWidgets import QApplication
from client import ApiClient
from main import MainWindow, friendly_error
from widgets import FieldEditor


def get_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["test_state_sync"])
    return app


class TestStateSynchronization(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = get_app()

    def setUp(self):
        self.window = MainWindow("http://127.0.0.1:37777", token="test_token_123")
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()

    # 1. ApiClient Request and Header Configuration
    def test_client_request_headers_and_url(self):
        client = ApiClient("http://127.0.0.1:37777/", token="my_secret_token")
        req = client._request("/api/state")
        self.assertEqual(req.url().toString(), "http://127.0.0.1:37777/api/state")
        auth_header = bytes(req.rawHeader(b"Authorization")).decode("utf-8")
        self.assertEqual(auth_header, "Bearer my_secret_token")
        accept_header = bytes(req.rawHeader(b"Accept")).decode("utf-8")
        self.assertEqual(accept_header, "application/json")

    # 2. Friendly Error Message Transformation
    def test_friendly_error_formatting(self):
        # 409 Conflict / Revision mismatch
        err_409 = friendly_error("HTTP 409: conflict revision mismatch", saving=True)
        self.assertIn("配置刚被其他程序修改", err_409)

        # 401 / 403 Authorization
        err_auth = friendly_error("HTTP 401: unauthorized token missing", saving=False)
        self.assertIn("连接验证失败", err_auth)

        # JSON parsing error
        err_json = friendly_error("invalid JSON syntax at line 1", saving=True)
        self.assertIn("配置服务返回了无法识别的内容", err_json)

        # Connection failure fallback
        err_conn = friendly_error("Connection refused to 127.0.0.1:37777", saving=True)
        self.assertIn("无法连接配置服务", err_conn)

    # 3. FieldEditor State Transitions: Optimistic Update, Save Succeeded, Save Failed
    def test_field_editor_save_lifecycle(self):
        field_data = {
            "id": "opt:shiftwidth:0",
            "file": "init.lua",
            "revision": "rev_abc",
            "line": 4,
            "value": {"kind": "number", "value": 4},
        }
        editor = FieldEditor("缩进宽度", field_data, value={"kind": "number", "value": 4})
        self.app.processEvents()

        # Initial state
        self.assertFalse(editor.dirty)
        self.assertFalse(editor.saving)

        # Simulate user edit
        editor.editor.set_value(8)
        self.assertTrue(editor.dirty)
        self.assertEqual(editor.state_label.text(), "尚未保存")

        # Save initiated
        editor._save()
        self.assertTrue(editor.saving)
        self.assertEqual(editor.state_label.text(), "正在保存…")

        # Save succeeded
        editor.save_succeeded("已保存并生效")
        self.assertFalse(editor.saving)
        self.assertEqual(editor.state_label.text(), "已保存并生效")

        # Simulate subsequent save failure
        editor.editor.set_value(12)
        editor._save()
        editor.save_failed("保存失败：网络超时")
        self.assertFalse(editor.saving)
        self.assertTrue(editor.dirty)
        self.assertEqual(editor.state_label.text(), "保存失败：网络超时")

    # 4. In-Place Field Updates without Overwriting In-Flight User Edits
    def test_editor_protects_in_flight_edits(self):
        field_data = {
            "id": "opt:tabstop:0",
            "file": "init.lua",
            "revision": "rev_1",
            "value": {"kind": "number", "value": 2},
        }
        editor = FieldEditor("Tab 宽度", field_data, value={"kind": "number", "value": 2})
        self.app.processEvents()

        # User starts typing a new value
        editor.editor.set_value(8)
        self.assertTrue(editor.is_editing())

        # Background state refresh arrives with old revision
        updated_field = copy.deepcopy(field_data)
        updated_field["revision"] = "rev_2"
        updated_field["value"] = {"kind": "number", "value": 4}
        editor.update_field(updated_field)

        # The dirty user value (8) should NOT be wiped out
        self.assertEqual(editor.editor.value(), 8)
        self.assertEqual(editor.field.get("revision"), "rev_2")

    # 5. Patch Response Handling in MainWindow
    def test_main_window_patch_response_handling(self):
        field_data = {
            "id": "opt:number:0",
            "file": "init.lua",
            "revision": "rev_1",
            "value": {"kind": "boolean", "value": True},
        }
        editor = self.window._editor("显示行号", field_data, value={"kind": "boolean", "value": True})
        self.app.processEvents()

        # Response 1: disk_saved and applied
        result_applied = {"disk_saved": True, "runtime": {"applied": True, "message": "OK"}}
        self.window._patch_received(result_applied, editor)
        self.assertEqual(editor.state_label.text(), "已保存并生效")

        # Response 2: disk_saved only (runtime reload failed or pending restart)
        result_disk_only = {"disk_saved": True, "runtime": {"applied": False, "message": "Nvim offline"}}
        self.window._patch_received(result_disk_only, editor)
        self.assertEqual(editor.state_label.text(), "已保存，重启后生效")

        # Response 3: disk_saved is False
        result_failed = {"disk_saved": False, "runtime": {"applied": False, "message": "Disk full"}}
        self.window._patch_received(result_failed, editor)
        self.assertEqual(editor.state_label.text(), "保存失败：配置未写入")

        # Response 4: None result (network or HTTP error)
        self.window._patch_received(None, editor)
        self.assertEqual(editor.state_label.text(), "保存失败，请检查连接后重试")

    # 6. SSE Event Stream Buffer Parsing
    def test_sse_event_stream_parsing(self):
        client = ApiClient("http://127.0.0.1:37777")

        class DummyReply:
            def readAll(self):
                return b""

        client._event_reply = DummyReply()
        client._pending_event = ""
        changes_received = []
        client.change_received.connect(lambda: changes_received.append(True))

        # Feed partial SSE lines into client buffer
        client._event_buffer = b"event: change\ndata: {\"reason\": \"file_changed\"}\n\n"
        client._read_events()
        self.assertEqual(len(changes_received), 1)

        # Multiple concatenated events
        client._event_buffer = (
            b"event: change\ndata: 1\n\n"
            b": keepalive comment\n\n"
            b"event: change\ndata: 2\n\n"
        )
        client._read_events()
        self.assertEqual(len(changes_received), 3)

    # 7. Scenario 5: Concurrency Conflict Recovery Simulation
    def test_concurrency_conflict_recovery_simulation(self):
        # 1. State loaded with revision rev_100
        initial_state = {
            "snapshot": {
                "settings": [
                    {
                        "namespace": "opt",
                        "name": "shiftwidth",
                        "field": {
                            "id": "opt:shiftwidth:0",
                            "file": "init.lua",
                            "revision": "rev_100",
                            "value": {"kind": "number", "value": 4},
                        },
                    }
                ],
                "keymaps": [],
                "plugins": [],
                "diagnostics": [],
            },
            "nvim": {"connected": True},
        }
        self.window._state_received(initial_state)
        self.app.processEvents()

        # 2. Find editor and apply user edit
        editors = self.window.common_page.findChildren(FieldEditor)
        target_editor = next((e for e in editors if e.title == "自动缩进宽度"), None)
        self.assertIsNotNone(target_editor)
        target_editor.editor.set_value(8)
        self.assertTrue(target_editor.dirty)

        # 3. Simulate conflict error reported by backend (HTTP 409 conflict)
        self.window._request_error("HTTP 409: Conflict (revision rev_100 outdated, current is rev_101)")
        self.assertIn("配置刚被其他程序修改", self.window.statusBar().currentMessage())

        # 4. Background re-sync arrives with updated revision rev_101 and external change value 6
        refreshed_state = {
            "snapshot": {
                "settings": [
                    {
                        "namespace": "opt",
                        "name": "shiftwidth",
                        "field": {
                            "id": "opt:shiftwidth:0",
                            "file": "init.lua",
                            "revision": "rev_101",
                            "value": {"kind": "number", "value": 6},
                        },
                    }
                ],
                "keymaps": [],
                "plugins": [],
                "diagnostics": [],
            },
            "nvim": {"connected": True},
        }
        self.window._state_received(refreshed_state)
        self.app.processEvents()

        # 5. Verify field revision was updated to rev_101 for subsequent retry
        self.assertEqual(target_editor.field.get("revision"), "rev_101")


if __name__ == "__main__":
    unittest.main()
