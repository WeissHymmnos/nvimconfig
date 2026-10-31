import json
from urllib.parse import urlencode

from PyQt6.QtCore import QByteArray, QObject, QTimer, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest


class ApiClient(QObject):
    state_ready = pyqtSignal(object)
    schema_ready = pyqtSignal(object)
    health_ready = pyqtSignal(object)
    patch_ready = pyqtSignal(object, object)
    request_error = pyqtSignal(str)
    change_received = pyqtSignal()
    events_status = pyqtSignal(str)

    def __init__(self, base_url, token="", parent=None):
        super().__init__(parent)
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.manager = QNetworkAccessManager(self)
        self._event_reply = None
        self._event_buffer = b""
        self._events_stopped = False
        self._reconnect_pending = False

    def _request(self, path):
        request = QNetworkRequest(QUrl(self.base_url + path))
        request.setRawHeader(b"Accept", b"application/json")
        if self.token:
            request.setRawHeader(
                b"Authorization", QByteArray(("Bearer " + self.token).encode("utf-8"))
            )
        return request

    @staticmethod
    def _error_text(reply):
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        detail = bytes(reply.readAll()).decode("utf-8", errors="replace").strip()
        message = reply.errorString()
        if status:
            message = f"HTTP {status}: {message}"
        if detail:
            try:
                payload = json.loads(detail)
                detail = payload.get("error") or payload.get("message") or detail
            except (ValueError, AttributeError):
                pass
            message += f"（{detail}）"
        return message

    def _get(self, path, signal, label):
        reply = self.manager.get(self._request(path))

        def finished():
            try:
                if reply.error() != QNetworkReply.NetworkError.NoError:
                    self.request_error.emit(f"{label}失败：{self._error_text(reply)}")
                    return
                try:
                    payload = json.loads(bytes(reply.readAll()).decode("utf-8"))
                except (ValueError, UnicodeDecodeError) as exc:
                    self.request_error.emit(f"{label}返回了无效 JSON：{exc}")
                    return
                signal.emit(payload)
            finally:
                reply.deleteLater()

        reply.finished.connect(finished)
        return reply

    def get_state(self):
        return self._get("/api/state", self.state_ready, "读取配置")

    def get_schema(self):
        return self._get("/api/schema", self.schema_ready, "读取选项 schema")

    def get_health(self):
        return self._get("/api/health", self.health_ready, "健康检查")

    def patch(self, field, value, context=None):
        body = {
            "id": field.get("id"),
            "file": field.get("file"),
            "revision": field.get("revision"),
            "value": value,
        }
        request = self._request("/api/entities")
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        data = QByteArray(json.dumps(body, ensure_ascii=False).encode("utf-8"))
        reply = self.manager.sendCustomRequest(request, b"PATCH", data)

        def finished():
            try:
                if reply.error() != QNetworkReply.NetworkError.NoError:
                    self.request_error.emit(f"保存失败：{self._error_text(reply)}")
                    self.patch_ready.emit(None, context)
                    return
                try:
                    payload = json.loads(bytes(reply.readAll()).decode("utf-8"))
                except (ValueError, UnicodeDecodeError) as exc:
                    self.request_error.emit(f"保存响应无效：{exc}")
                    self.patch_ready.emit(None, context)
                    return
                self.patch_ready.emit(payload, context)
            finally:
                reply.deleteLater()

        reply.finished.connect(finished)
        return reply

    def patch_batch(self, items, context=None):
        """
        Atomically patch multiple fields in the same file without intermediate revision conflicts.
        `items` is a list of (field_dict, value_dict) tuples or pre-built patch dicts.
        """
        patches = []
        default_file = ""
        default_rev = ""
        for item in items or []:
            if isinstance(item, (tuple, list)) and len(item) == 2:
                field, val = item
                f_path = field.get("file", "")
                f_rev = field.get("revision", "")
                if not default_file and f_path:
                    default_file = f_path
                if not default_rev and f_rev:
                    default_rev = f_rev
                patches.append({
                    "id": field.get("id", ""),
                    "file": f_path,
                    "revision": f_rev,
                    "value": val,
                })
            elif isinstance(item, dict):
                f_path = item.get("file", "")
                f_rev = item.get("revision", "")
                if not default_file and f_path:
                    default_file = f_path
                if not default_rev and f_rev:
                    default_rev = f_rev
                patches.append(item)

        body = {
            "file": default_file,
            "revision": default_rev,
            "patches": patches,
        }
        request = self._request("/api/entities/batch")
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        data = QByteArray(json.dumps(body, ensure_ascii=False).encode("utf-8"))
        reply = self.manager.sendCustomRequest(request, b"PATCH", data)

        def finished():
            try:
                if reply.error() != QNetworkReply.NetworkError.NoError:
                    self.request_error.emit(f"批量保存失败：{self._error_text(reply)}")
                    self.patch_ready.emit(None, context)
                    return
                try:
                    payload = json.loads(bytes(reply.readAll()).decode("utf-8"))
                except (ValueError, UnicodeDecodeError) as exc:
                    self.request_error.emit(f"批量保存响应无效：{exc}")
                    self.patch_ready.emit(None, context)
                    return
                self.patch_ready.emit(payload, context)
            finally:
                reply.deleteLater()

        reply.finished.connect(finished)
        return reply

    def create_option(self, name, value, context=None):
        body = {"name": name, "value": value}
        request = self._request("/api/options")
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        data = QByteArray(json.dumps(body, ensure_ascii=False).encode("utf-8"))
        reply = self.manager.post(request, data)

        def finished():
            try:
                if reply.error() != QNetworkReply.NetworkError.NoError:
                    self.request_error.emit(f"添加设置失败：{self._error_text(reply)}")
                    self.patch_ready.emit(None, context)
                    return
                try:
                    payload = json.loads(bytes(reply.readAll()).decode("utf-8"))
                except (ValueError, UnicodeDecodeError) as exc:
                    self.request_error.emit(f"添加设置响应无效：{exc}")
                    self.patch_ready.emit(None, context)
                    return
                self.patch_ready.emit(payload, context)
            finally:
                reply.deleteLater()

        reply.finished.connect(finished)
        return reply

    def create_keymap(self, mode, lhs, rhs, opts=None, context=None):
        body = {
            "mode": mode,
            "lhs": lhs,
            "rhs": rhs,
            "opts": opts if opts is not None else {"kind": "table", "entries": []},
        }
        request = self._request("/api/keymaps")
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        data = QByteArray(json.dumps(body, ensure_ascii=False).encode("utf-8"))
        reply = self.manager.post(request, data)

        def finished():
            try:
                if reply.error() != QNetworkReply.NetworkError.NoError:
                    self.request_error.emit(f"添加快捷键失败：{self._error_text(reply)}")
                    self.patch_ready.emit(None, context)
                    return
                try:
                    payload = json.loads(bytes(reply.readAll()).decode("utf-8"))
                except (ValueError, UnicodeDecodeError) as exc:
                    self.request_error.emit(f"添加快捷键响应无效：{exc}")
                    self.patch_ready.emit(None, context)
                    return
                self.patch_ready.emit(payload, context)
            finally:
                reply.deleteLater()

        reply.finished.connect(finished)
        return reply

    def create_plugin(self, payload, context=None):
        request = self._request("/api/plugins")
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        data = QByteArray(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        reply = self.manager.post(request, data)

        def finished():
            try:
                if reply.error() != QNetworkReply.NetworkError.NoError:
                    self.request_error.emit(f"添加插件失败：{self._error_text(reply)}")
                    self.patch_ready.emit(None, context)
                    return
                try:
                    resp = json.loads(bytes(reply.readAll()).decode("utf-8"))
                except (ValueError, UnicodeDecodeError) as exc:
                    self.request_error.emit(f"添加插件响应无效：{exc}")
                    self.patch_ready.emit(None, context)
                    return
                self.patch_ready.emit(resp, context)
            finally:
                reply.deleteLater()

        reply.finished.connect(finished)
        return reply

    def delete_entity(self, field, context=None):
        if isinstance(field, dict):
            entity_id = field.get("id", "")
            body = {
                "id": entity_id,
                "file": field.get("file"),
                "revision": field.get("revision"),
            }
        else:
            entity_id = str(field or "")
            body = {"id": entity_id}
        request = self._request(f"/api/entities/{entity_id}")
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        data = QByteArray(json.dumps(body, ensure_ascii=False).encode("utf-8"))
        reply = self.manager.sendCustomRequest(request, b"DELETE", data)

        def finished():
            try:
                if reply.error() != QNetworkReply.NetworkError.NoError:
                    self.request_error.emit(f"删除失败：{self._error_text(reply)}")
                    self.patch_ready.emit(None, context)
                    return
                try:
                    resp = json.loads(bytes(reply.readAll()).decode("utf-8"))
                except (ValueError, UnicodeDecodeError) as exc:
                    self.request_error.emit(f"删除响应无效：{exc}")
                    self.patch_ready.emit(None, context)
                    return
                self.patch_ready.emit(resp, context)
            finally:
                reply.deleteLater()

        reply.finished.connect(finished)
        return reply

    def rollback(self, file_path=None, target_revision=None, context=None):
        body = {}
        if file_path is not None:
            body["file"] = file_path
        if target_revision is not None:
            body["target_revision"] = target_revision
        request = self._request("/api/rollback")
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        data = QByteArray(json.dumps(body, ensure_ascii=False).encode("utf-8"))
        reply = self.manager.post(request, data)

        def finished():
            try:
                if reply.error() != QNetworkReply.NetworkError.NoError:
                    self.request_error.emit(f"回滚失败：{self._error_text(reply)}")
                    self.patch_ready.emit(None, context)
                    return
                try:
                    resp = json.loads(bytes(reply.readAll()).decode("utf-8"))
                except (ValueError, UnicodeDecodeError) as exc:
                    self.request_error.emit(f"回滚响应无效：{exc}")
                    self.patch_ready.emit(None, context)
                    return
                self.patch_ready.emit(resp, context)
            finally:
                reply.deleteLater()

        reply.finished.connect(finished)
        return reply

    def start_events(self):
        self._events_stopped = False
        if self._event_reply is not None or self._reconnect_pending:
            return
        query = "?" + urlencode({"token": self.token}) if self.token else ""
        request = self._request("/api/events" + query)
        request.setRawHeader(b"Accept", b"text/event-stream")
        reply = self.manager.get(request)
        self._event_reply = reply
        self._event_buffer = b""
        self._pending_event = ""

        def on_meta():
            if self._event_reply is reply:
                status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
                if status == 200:
                    self.events_status.emit("实时更新已连接")

        reply.metaDataChanged.connect(on_meta)
        reply.readyRead.connect(self._read_events)
        reply.finished.connect(self._events_finished)
        self.events_status.emit("正在连接实时更新")

    def _read_events(self):
        reply = self._event_reply
        if reply is None:
            return
        self._event_buffer += bytes(reply.readAll())
        self.events_status.emit("实时更新已连接")
        while b"\n" in self._event_buffer:
            raw_line, self._event_buffer = self._event_buffer.split(b"\n", 1)
            line = raw_line.rstrip(b"\r").decode("utf-8", errors="replace")
            if not line:
                if self._pending_event == "change":
                    self.change_received.emit()
                self._pending_event = ""
            elif line.startswith("event:"):
                self._pending_event = line[6:].strip()
            elif line == "data:" or line.startswith("data: "):
                if not self._pending_event:
                    self._pending_event = "message"

    def _events_finished(self):
        reply = self._event_reply
        if reply is not None:
            reply.deleteLater()
        self._event_reply = None
        self._event_buffer = b""
        self._pending_event = ""
        if not self._events_stopped:
            self.events_status.emit("实时更新已断开，正在重连")
            self._schedule_reconnect()

    def _schedule_reconnect(self):
        if self._reconnect_pending or self._events_stopped:
            return
        self._reconnect_pending = True

        def reconnect():
            self._reconnect_pending = False
            if not self._events_stopped:
                self.start_events()

        QTimer.singleShot(2500, reconnect)

    def stop_events(self):
        self._events_stopped = True
        if self._event_reply is not None:
            self._event_reply.abort()
