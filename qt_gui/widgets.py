import copy
import os
from dataclasses import dataclass

from PyQt6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSignalBlocker,
    QSize,
    QTimer,
    QUrl,
    Qt,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import QBrush, QColor, QDesktopServices, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QTabWidget,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


from theme import ThemeManager, get_current_palette


def set_status_label(label: QLabel, text: str, status: str = "muted"):
    """Update status label text and semantic status property via QSS property selector."""
    label.setText(text)
    if label.property("status") != status:
        label.setProperty("status", status)
        style = label.style()
        if style is not None:
            style.unpolish(label)
            style.polish(label)


@dataclass
class UnsupportedValue:
    source: str


def is_lua_value(value):
    return isinstance(value, dict) and value.get("kind") in {
        "boolean",
        "number",
        "string",
        "array",
        "table",
        "unsupported",
    }


def lua_to_python(value):
    if value is None:
        return None
    if not is_lua_value(value):
        return copy.deepcopy(value)
    kind = value.get("kind")
    if kind in {"boolean", "number", "string"}:
        return value.get("value")
    if kind == "array":
        return [lua_to_python(item) for item in value.get("values") or []]
    if kind == "table":
        return {
            str(entry.get("key", "")): lua_to_python(entry.get("value"))
            for entry in value.get("entries") or []
        }
    return UnsupportedValue(str(value.get("source", "")))


def python_to_lua(value):
    if isinstance(value, UnsupportedValue):
        return {"kind": "unsupported", "source": value.source}
    if isinstance(value, bool):
        return {"kind": "boolean", "value": value}
    if isinstance(value, (int, float)):
        return {"kind": "number", "value": value}
    if isinstance(value, str):
        return {"kind": "string", "value": value}
    if isinstance(value, (list, tuple)):
        return {"kind": "array", "values": [python_to_lua(item) for item in value]}
    if isinstance(value, dict):
        return {
            "kind": "table",
            "entries": [
                {"key": str(key), "value": python_to_lua(item)}
                for key, item in value.items()
            ],
        }
    return {"kind": "string", "value": "" if value is None else str(value)}


def value_kind(value):
    if isinstance(value, UnsupportedValue):
        return "unsupported"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "table"
    return "string"


def default_for_kind(kind):
    return {
        "boolean": False,
        "number": 0,
        "string": "",
        "array": [],
        "table": {},
    }.get(kind, "")


def field_value(field, default=None):
    if isinstance(field, dict) and "value" in field:
        val = field.get("value")
        return default if val is None and default is not None else val
    return default


def format_display_path(path_str: str) -> str:
    """Shorten absolute Neovim config paths (e.g. /home/user/.config/nvim/lua/...) for clean UI display."""
    if not path_str:
        return ""
    s = str(path_str)
    for marker in ("/.config/nvim/", "\\.config\\nvim\\"):
        idx = s.find(marker)
        if idx >= 0:
            return s[idx + len(marker):]
    home = os.path.expanduser("~")
    if home and s.startswith(home):
        return "~" + s[len(home):]
    return s


def parse_plugin_repo_url(source: str):
    """
    Parses plugin source identifier into an external browser URL and tooltip description.
    Supports:
    - 'owner/repo' -> 'https://github.com/owner/repo'
    - 'https://github.com/...git' -> stripped '.git'
    - 'git@github.com:owner/repo.git' -> 'https://github.com/owner/repo'
    - Local directory ('~/...', '/...', './...') -> 'file://...'
    """
    if not source:
        return None, "未指定插件源"
    s = source.strip()
    if s.startswith(("http://", "https://")):
        clean = s[:-4] if s.endswith(".git") else s
        return clean, f"在浏览器中打开：{clean}"
    if s.startswith("git://github.com/"):
        path = s[len("git://github.com/"):].removesuffix(".git")
        url = f"https://github.com/{path}"
        return url, f"在浏览器中打开：{url}"
    if s.startswith("file://"):
        expanded = os.path.abspath(os.path.expanduser(s[7:]))
        return f"file://{expanded}", f"打开本地目录：{expanded}"
    if s.startswith("git@"):
        host_path = s[4:]
        if ":" in host_path:
            host, path = host_path.split(":", 1)
            path = path.removesuffix(".git")
            url = f"https://{host}/{path}"
            return url, f"在浏览器中打开：{url}"
    if s.startswith(("~", "/", "./", "../")) or os.path.isabs(s):
        expanded = os.path.expanduser(s)
        return f"file://{os.path.abspath(expanded)}", f"打开本地目录：{expanded}"
    if "/" in s:
        clean = s.removesuffix(".git")
        url = f"https://github.com/{clean}"
        return url, f"在浏览器中打开：{url}"
    return None, f"插件源：{s}"


def get_field_display_val(field):
    """Extracts a user-friendly string from a Field dict for chip rendering."""
    if not isinstance(field, dict):
        return None
    val = field.get("value")
    py_val = lua_to_python(val)
    if py_val is None:
        return None
    if isinstance(py_val, bool):
        return py_val
    if isinstance(py_val, list):
        items = [str(x) for x in py_val if x]
        return ", ".join(items) if items else None
    if isinstance(py_val, dict):
        return f"{len(py_val)} 项"
    return str(py_val)


_MD3_PIXMAP_CACHE = {}
_MD3_ICON_CACHE = {}


def get_md3_pixmap(kind: str, color_hex: str, size: int = 16) -> QPixmap:
    """Renders and caches crisp Material Design 3 geometric vector icons without using any emojis."""
    key = (kind, color_hex, size)
    cached = _MD3_PIXMAP_CACHE.get(key)
    if cached is not None:
        return cached
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    stroke = max(1.5, size * 0.1)
    pen = QPen(QColor(color_hex), stroke, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    s = float(size)
    if kind == "delete":
        # Trash can lid, handle, and body
        p.drawLine(QPointF(s * 0.20, s * 0.26), QPointF(s * 0.80, s * 0.26))
        p.drawLine(QPointF(s * 0.38, s * 0.16), QPointF(s * 0.62, s * 0.16))
        p.drawRoundedRect(QRectF(s * 0.27, s * 0.26, s * 0.46, s * 0.56), s * 0.08, s * 0.08)
        p.drawLine(QPointF(s * 0.42, s * 0.40), QPointF(s * 0.42, s * 0.68))
        p.drawLine(QPointF(s * 0.58, s * 0.40), QPointF(s * 0.58, s * 0.68))
    elif kind == "external":
        # Open-in-new external arrow
        p.drawLine(QPointF(s * 0.42, s * 0.24), QPointF(s * 0.24, s * 0.24))
        p.drawLine(QPointF(s * 0.24, s * 0.24), QPointF(s * 0.24, s * 0.76))
        p.drawLine(QPointF(s * 0.24, s * 0.76), QPointF(s * 0.76, s * 0.76))
        p.drawLine(QPointF(s * 0.76, s * 0.76), QPointF(s * 0.76, s * 0.58))
        p.drawLine(QPointF(s * 0.48, s * 0.52), QPointF(s * 0.78, s * 0.22))
        p.drawLine(QPointF(s * 0.56, s * 0.22), QPointF(s * 0.78, s * 0.22))
        p.drawLine(QPointF(s * 0.78, s * 0.22), QPointF(s * 0.78, s * 0.44))
    elif kind == "close":
        p.drawLine(QPointF(s * 0.28, s * 0.28), QPointF(s * 0.72, s * 0.72))
        p.drawLine(QPointF(s * 0.72, s * 0.28), QPointF(s * 0.28, s * 0.72))
    elif kind == "search":
        p.drawEllipse(QPointF(s * 0.44, s * 0.44), s * 0.24, s * 0.24)
        p.drawLine(QPointF(s * 0.62, s * 0.62), QPointF(s * 0.80, s * 0.80))
    elif kind == "offline":
        p.drawEllipse(QPointF(s * 0.50, s * 0.50), s * 0.36, s * 0.36)
        p.drawLine(QPointF(s * 0.50, s * 0.30), QPointF(s * 0.50, s * 0.54))
        p.drawEllipse(QPointF(s * 0.50, s * 0.68), stroke * 0.4, stroke * 0.4)
    elif kind == "plugin":
        r = s * 0.24
        p.drawRoundedRect(QRectF(s * 0.20, s * 0.20, r, r), 2.0, 2.0)
        p.drawRoundedRect(QRectF(s * 0.56, s * 0.20, r, r), 2.0, 2.0)
        p.drawRoundedRect(QRectF(s * 0.20, s * 0.56, r, r), 2.0, 2.0)
        p.drawRoundedRect(QRectF(s * 0.56, s * 0.56, r, r), 2.0, 2.0)
    elif kind == "success":
        p.drawEllipse(QPointF(s * 0.50, s * 0.50), s * 0.36, s * 0.36)
        p.drawLine(QPointF(s * 0.34, s * 0.52), QPointF(s * 0.46, s * 0.64))
        p.drawLine(QPointF(s * 0.46, s * 0.64), QPointF(s * 0.68, s * 0.38))
    elif kind in ("warning", "error", "info"):
        p.drawEllipse(QPointF(s * 0.50, s * 0.50), s * 0.36, s * 0.36)
        p.drawLine(QPointF(s * 0.50, s * 0.32), QPointF(s * 0.50, s * 0.54))
        p.drawEllipse(QPointF(s * 0.50, s * 0.67), stroke * 0.35, stroke * 0.35)
    p.end()
    _MD3_PIXMAP_CACHE[key] = px
    return px


def get_md3_icon(kind: str, color_hex: str, size: int = 16) -> QIcon:
    key = (kind, color_hex, size)
    cached = _MD3_ICON_CACHE.get(key)
    if cached is not None:
        return cached
    ic = QIcon(get_md3_pixmap(kind, color_hex, size))
    _MD3_ICON_CACHE[key] = ic
    return ic


_SWITCH_PALETTE_CACHE = {}


def _get_switch_colors() -> tuple[QColor, QColor, QColor, QColor, QColor, QColor]:
    theme_key = ThemeManager.instance().current_theme
    cached = _SWITCH_PALETTE_CACHE.get(theme_key)
    if cached is not None:
        return cached
    p = get_current_palette()
    colors = (
        QColor(p["blue"]),
        QColor(p["bg_highlight"]),
        QColor(p.get("border_highlight", p["fg_muted"])),
        QColor(p.get("fg_on_accent", "#ffffff")),
        QColor(p["bg_card"]),
        QColor(p["fg_gutter"]),
    )
    _SWITCH_PALETTE_CACHE[theme_key] = colors
    return colors


class SwitchWidget(QCheckBox):
    """Material Design 3 (M3) toggle switch widget for PyQt6.

    Follows the official M3 Switch specification:
    - Unchecked: SurfaceContainerHighest track with 2px Outline border and 12px Outline thumb.
    - Checked: Solid Primary track with 16px OnPrimary thumb and drawn Checkmark icon.
    - Hover: Subtle circular M3 state-layer halo around the thumb.
    """

    def __init__(
        self,
        checked=False,
        parent=None,
        active_color=None,
        inactive_color=None,
        handle_color="#ffffff",
    ):
        super().__init__(parent)
        self.setObjectName("switchWidget")
        self.setFixedSize(44, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._custom_active = QColor(active_color) if active_color else None
        self._custom_inactive = QColor(inactive_color) if inactive_color else None
        self._handle_color = QColor(handle_color)
        self._thumb_position = 1.0 if checked else 0.0
        self._hovered = False
        self._animation = None

        self.setChecked(checked)
        self.toggled.connect(self._on_toggled)

    def sizeHint(self):
        return QSize(44, 24)

    def minimumSizeHint(self):
        return QSize(44, 24)

    @property
    def _active_color(self):
        return self._custom_active or _get_switch_colors()[0]

    @property
    def _inactive_color(self):
        return self._custom_inactive or _get_switch_colors()[1]

    @pyqtProperty(float)
    def thumb_position(self):
        return self._thumb_position

    @thumb_position.setter
    def thumb_position(self, pos):
        self._thumb_position = max(0.0, min(1.0, float(pos)))
        self.update()

    def _on_toggled(self, checked):
        if not self.isVisible():
            if self._animation is not None:
                self._animation.stop()
            self._thumb_position = 1.0 if checked else 0.0
            self.update()
            return
        if self._animation is None:
            self._animation = QPropertyAnimation(self, b"thumb_position", self)
            self._animation.setDuration(150)
            self._animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._animation.stop()
        self._animation.setStartValue(self._thumb_position)
        self._animation.setEndValue(1.0 if checked else 0.0)
        self._animation.start()

    def setChecked(self, checked):
        super().setChecked(checked)
        if self.signalsBlocked() or not self.isVisible():
            if self._animation is not None:
                self._animation.stop()
            self._thumb_position = 1.0 if checked else 0.0
            self.update()

    def text(self):
        return "开启" if self.isChecked() else "关闭"

    def value(self):
        return self.isChecked()

    def enterEvent(self, event):
        super().enterEvent(event)
        self._hovered = True
        self.update()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._hovered = False
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pos = self._thumb_position

        active_col, inactive_col, outline_col, on_primary_col, dis_track_col, dis_handle_col = _get_switch_colors()
        if self._custom_active is not None:
            active_col = self._custom_active
        if self._custom_inactive is not None:
            inactive_col = self._custom_inactive

        if not self.isEnabled():
            track_color = dis_track_col
            border_color = dis_handle_col
            handle_color = dis_handle_col
        elif pos <= 0.01:
            track_color = inactive_col
            border_color = outline_col
            handle_color = outline_col
        elif pos >= 0.99:
            track_color = active_col
            border_color = active_col
            handle_color = on_primary_col
        else:
            r = int(inactive_col.red() + (active_col.red() - inactive_col.red()) * pos)
            g = int(inactive_col.green() + (active_col.green() - inactive_col.green()) * pos)
            b = int(inactive_col.blue() + (active_col.blue() - inactive_col.blue()) * pos)
            track_color = QColor(r, g, b)

            br = int(outline_col.red() + (active_col.red() - outline_col.red()) * pos)
            bg = int(outline_col.green() + (active_col.green() - outline_col.green()) * pos)
            bb = int(outline_col.blue() + (active_col.blue() - outline_col.blue()) * pos)
            border_color = QColor(br, bg, bb)

            hr = int(outline_col.red() + (on_primary_col.red() - outline_col.red()) * pos)
            hg = int(outline_col.green() + (on_primary_col.green() - outline_col.green()) * pos)
            hb = int(outline_col.blue() + (on_primary_col.blue() - outline_col.blue()) * pos)
            handle_color = QColor(hr, hg, hb)

        # 1. Draw M3 pill track (with 1.8px outline in unchecked state)
        painter.setPen(QPen(border_color, 1.8))
        painter.setBrush(QBrush(track_color))
        painter.drawRoundedRect(QRectF(1.0, 1.0, 42.0, 22.0), 11.0, 11.0)

        # 2. Compute M3 thumb center and expanding diameter (12px unchecked -> 16px checked/hovered)
        center_x = 12.0 + 20.0 * pos
        center_y = 12.0
        base_diam = 12.0 + 4.0 * pos
        if self._hovered and self.isEnabled():
            base_diam = max(base_diam, 15.0)
            halo_color = QColor(active_col if pos > 0.5 else outline_col)
            halo_color.setAlpha(42)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(halo_color))
            painter.drawEllipse(QPointF(center_x, center_y), 11.5, 11.5)

        if self.hasFocus():
            focus_pen = QPen(active_col, 1.5)
            painter.setPen(focus_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(0.75, 0.75, 42.5, 22.5), 11.25, 11.25)

        # 3. Draw circular thumb
        radius = base_diam / 2.0
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(handle_color))
        painter.drawEllipse(QPointF(center_x, center_y), radius, radius)

        # 4. Draw M3 Checkmark icon inside active thumb
        if pos > 0.55 and self.isEnabled():
            check_pen = QPen(
                active_col,
                1.8,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
            painter.setPen(check_pen)
            p1 = QPointF(center_x - 3.2, center_y + 0.2)
            p2 = QPointF(center_x - 0.8, center_y + 2.6)
            p3 = QPointF(center_x + 3.5, center_y - 2.2)
            painter.drawLine(p1, p2)
            painter.drawLine(p2, p3)
        painter.end()


CONTEXT_RANGES = {
    # Indentation options
    "shiftwidth": (1, 16),
    "tabstop": (1, 16),
    "softtabstop": (1, 16),
    # Viewport scroll offsets
    "scrolloff": (0, 20),
    "sidescrolloff": (0, 20),
    # Common UI dimensions and limits
    "cmdheight": (1, 10),
    "updatetime": (10, 2000),
    "timeoutlen": (50, 2000),
    "foldlevel": (0, 20),
    "textwidth": (0, 120),
}


class _NoWheelFilter(QObject):
    """Prevents unfocused spinboxes, sliders, and comboboxes from stealing mouse wheel scroll events."""

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel and not obj.hasFocus():
            event.ignore()
            return True
        return super().eventFilter(obj, event)


class _NestedScrollFilter(QObject):
    """Allows nested QTreeWidget / QPlainTextEdit to scroll internally when possible, and forwards wheel events to ancestor QScrollArea at boundaries."""

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel:
            scroll_area = obj.parent() if hasattr(obj, "parent") else None
            if not hasattr(scroll_area, "verticalScrollBar"):
                scroll_area = obj
            vbar = scroll_area.verticalScrollBar() if hasattr(scroll_area, "verticalScrollBar") else None
            if vbar is not None:
                delta_y = event.angleDelta().y() or event.pixelDelta().y()
                at_boundary = (
                    vbar.maximum() <= vbar.minimum()
                    or (delta_y > 0 and vbar.value() <= vbar.minimum())
                    or (delta_y < 0 and vbar.value() >= vbar.maximum())
                )
                if at_boundary:
                    p = scroll_area.parentWidget() if hasattr(scroll_area, "parentWidget") else None
                    while p is not None and not isinstance(p, QScrollArea):
                        p = p.parentWidget()
                    if p is not None:
                        QApplication.sendEvent(p.verticalScrollBar(), event)
                        return True
                    event.ignore()
                    return True
        return super().eventFilter(obj, event)


_NO_WHEEL_FILTER_INSTANCE = None
_NESTED_SCROLL_FILTER_INSTANCE = None


def _get_no_wheel_filter() -> _NoWheelFilter:
    global _NO_WHEEL_FILTER_INSTANCE
    if _NO_WHEEL_FILTER_INSTANCE is None:
        _NO_WHEEL_FILTER_INSTANCE = _NoWheelFilter()
    return _NO_WHEEL_FILTER_INSTANCE


def _get_nested_scroll_filter() -> _NestedScrollFilter:
    global _NESTED_SCROLL_FILTER_INSTANCE
    if _NESTED_SCROLL_FILTER_INSTANCE is None:
        _NESTED_SCROLL_FILTER_INSTANCE = _NestedScrollFilter()
    return _NESTED_SCROLL_FILTER_INSTANCE


class IntegerEdit(QWidget):
    edited = pyqtSignal()

    def __init__(
        self,
        value=0,
        default=0,
        option_name="",
        min_val=None,
        max_val=None,
        parent=None,
    ):
        super().__init__(parent)
        self.spin = QSpinBox()
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.option_name = option_name

        if min_val is not None and max_val is not None:
            lower, upper = min_val, max_val
        else:
            base = option_name.lower().split(".")[-1].strip() if option_name else ""
            if base in CONTEXT_RANGES:
                c_min, c_max = CONTEXT_RANGES[base]
                vals = [item for item in (value, default) if isinstance(item, (int, float))]
                lower = min([c_min] + [int(v) for v in vals if v is not None])
                upper = max([c_max] + [int(v) for v in vals if v is not None])
            else:
                values = [item for item in (value, default) if isinstance(item, (int, float))]
                largest = max([abs(int(item)) for item in values] + [10])
                upper = min(1_000_000, max(100, largest * 10))
                lower = 0 if all(item >= 0 for item in values) else -upper

        self.spin.setRange(-2_147_483_647, 2_147_483_647)
        self.slider.setRange(lower, upper)
        self.spin.setKeyboardTracking(False)
        self.spin.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.slider.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.spin.installEventFilter(_get_no_wheel_filter())
        self.slider.installEventFilter(_get_no_wheel_filter())
        self.spin.setToolTip("可直接输入数字，也可以拖动滑块")
        self.spin.setFixedWidth(88)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.spin)

        self.slider.valueChanged.connect(self._on_slider_changed)
        self.spin.valueChanged.connect(self._on_spin_changed)
        self.spin.valueChanged.connect(self.edited)

        self.set_value(value)

    def _on_slider_changed(self, val):
        self.spin.setValue(val)

    def _on_spin_changed(self, val):
        if val < self.slider.minimum():
            self.slider.setMinimum(val)
        elif val > self.slider.maximum():
            self.slider.setMaximum(val)
        self.slider.setValue(val)

    def set_value(self, value):
        try:
            number = int(value or 0)
        except (TypeError, ValueError, OverflowError):
            number = 0
        number = max(-2_147_483_647, min(2_147_483_647, number))
        if number < self.slider.minimum():
            self.slider.setMinimum(number)
        if number > self.slider.maximum():
            self.slider.setMaximum(max(self.slider.maximum(), number))
        self.spin.setValue(number)

    def value(self):
        return self.spin.value()


class CollapsibleSection(QFrame):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.toggle = QToolButton()
        self.toggle.setText(title)
        self.toggle.setCheckable(True)
        self.toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setObjectName("sectionToggle")
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(4, 8, 4, 2)
        self.content.setVisible(False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.toggle)
        layout.addWidget(self.content)
        self.toggle.toggled.connect(self._toggle_content)

    def _toggle_content(self, expanded):
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self.content.setVisible(expanded)

    def add_widget(self, widget):
        self.content_layout.addWidget(widget)


class LuaValueEditor(QWidget):
    edited = pyqtSignal()

    def __init__(self, value=None, default=None, advanced=False, read_only=False, parent=None):
        super().__init__(parent)
        self.advanced = advanced
        self.read_only = read_only
        initial = value if value is not None else default
        self._value = lua_to_python(initial)
        if self._value is None:
            self._value = ""
        self.dirty = False
        self.confirm_remove = None
        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(["名称", "类型", "值"])
        self.tree.setColumnWidth(0, 225)
        self.tree.setColumnWidth(1, 88)
        self.tree.header().setStretchLastSection(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tree.setMinimumHeight(74)
        self.tree.viewport().installEventFilter(_get_nested_scroll_filter())
        self.source = QPlainTextEdit()
        self.source.setObjectName("luaRawPreview")
        self.source.setReadOnly(True)
        self.source.setPlaceholderText("此处显示暂时无法可视化编辑的原始内容")
        self.source.setMaximumHeight(110)
        self.source.setVisible(False)
        self.source.viewport().installEventFilter(_get_nested_scroll_filter())
        self.summary_badge = QLabel("")
        self.summary_badge.setObjectName("technicalName")
        self.add_button = QPushButton("+ 添加")
        self.add_button.setObjectName("treeActionChip")
        self.add_button.setToolTip("在当前表或列表中新增一项")
        self.add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.type_button = QPushButton("更改类型")
        self.type_button.setObjectName("treeActionChip")
        self.type_button.setToolTip("更改所选节点的数据类型")
        self.type_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.remove_button = QPushButton("删除")
        self.remove_button.setObjectName("treeActionChip")
        self.remove_button.setToolTip("删除当前选中的节点")
        self.remove_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.buttons_widget = QWidget()
        buttons = QHBoxLayout(self.buttons_widget)
        buttons.setContentsMargins(2, 0, 2, 0)
        buttons.setSpacing(6)
        buttons.addWidget(self.summary_badge)
        buttons.addStretch(1)
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.type_button)
        buttons.addWidget(self.remove_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.buttons_widget)
        layout.addWidget(self.tree)
        layout.addWidget(self.source)
        self.add_button.clicked.connect(self._add_child)
        self.type_button.clicked.connect(self._change_type)
        self.remove_button.clicked.connect(self._remove)
        self.tree.currentItemChanged.connect(self._show_source)
        self.rebuild()

    def value(self):
        return python_to_lua(self._value)

    def mark_saved(self):
        self.dirty = False

    def _mark_edited(self):
        self.dirty = True
        self.edited.emit()

    def _new_item(self, label, path, value, parent=None):
        item = QTreeWidgetItem(parent) if parent is not None else QTreeWidgetItem()
        item.setText(0, str(label))
        item.setToolTip(0, str(label))
        item.setText(1, value_kind(value))
        item.setData(0, Qt.ItemDataRole.UserRole, path)
        item.setSizeHint(0, QSize(0, 34))
        item.setSizeHint(2, QSize(0, 34))
        if isinstance(value, UnsupportedValue):
            raw = value.source.strip()
            first_line = raw.splitlines()[0].strip() if raw else "Lua 表达式"
            summary = f"{first_line[:44]} …" if len(raw) > 44 or "\n" in raw else first_line
            item.setText(2, summary if self.advanced else "暂不支持可视化编辑")
            item.setToolTip(2, value.source if self.advanced else "为避免破坏原配置，此内容只能查看")
        elif self.read_only and not isinstance(value, (dict, list)):
            item.setText(2, "" if value is None else str(value))
        return item

    def _measure_tree_stats(self, item, fm, indent_px: int, depth: int = 0) -> tuple[int, int, int]:
        total = 1
        col0_w = (depth + 1) * indent_px + fm.horizontalAdvance(item.text(0))
        col1_w = fm.horizontalAdvance(item.text(1))
        for i in range(item.childCount()):
            c_rows, c_col0, c_col1 = self._measure_tree_stats(item.child(i), fm, indent_px, depth + 1)
            total += c_rows
            if c_col0 > col0_w:
                col0_w = c_col0
            if c_col1 > col1_w:
                col1_w = c_col1
        return total, col0_w, col1_w

    def rebuild(self):
        self.tree.setUpdatesEnabled(False)
        try:
            self.tree.clear()
            root = self._new_item("全部内容", (), self._value)
            self.tree.addTopLevelItem(root)
            self._populate_item(root, (), self._value)
            root.setExpanded(True)
            self.tree.setCurrentItem(root)
        finally:
            self.tree.setUpdatesEnabled(True)

        kind_str = value_kind(self._value)
        count_num = len(self._value) if isinstance(self._value, (dict, list)) else 0
        self.summary_badge.setText(f"{kind_str} · {count_num} 项" if isinstance(self._value, (dict, list)) else kind_str)

        is_root_unsup = isinstance(self._value, UnsupportedValue)
        if self.read_only and is_root_unsup:
            self.buttons_widget.setVisible(False)
            self.tree.setVisible(False)
            raw_src = self._value.source or ""
            self.source.setPlainText(raw_src)
            line_count = max(1, len(raw_src.splitlines()))
            desired_h = min(260, max(130, 24 + line_count * 20))
            self.source.setMinimumHeight(desired_h)
            self.source.setMaximumHeight(max(220, desired_h))
            self.source.setEnabled(True)
            self.source.setVisible(True)
            self.source.updateGeometry()
        else:
            self.buttons_widget.setVisible(not self.read_only)
            self.tree.setVisible(True)
            fm = self.tree.fontMetrics()
            indent_px = max(18, self.tree.indentation())
            total_rows, max_col0, max_col1 = self._measure_tree_stats(root, fm, indent_px, 0)
            if total_rows <= 1:
                self.tree.setMinimumHeight(68)
                self.tree.setMaximumHeight(82)
            elif total_rows <= 6:
                target_h = 36 + total_rows * 35
                self.tree.setMinimumHeight(min(230, target_h))
                self.tree.setMaximumHeight(min(250, target_h + 12))
            else:
                self.tree.setMinimumHeight(240)
                self.tree.setMaximumHeight(350)
            self.tree.setColumnWidth(0, max(210, min(340, max_col0 + 30)))
            self.tree.setColumnWidth(1, max(88, min(130, max_col1 + 26)))
            self.tree.updateGeometry()
            self._show_source(self.tree.currentItem())
        self.updateGeometry()
        self._update_buttons()

    def _populate_item(self, item, path, value):
        if isinstance(value, dict):
            children = value.items()
        elif isinstance(value, list):
            children = enumerate(value)
        else:
            editor = self._scalar_editor(path, value)
            if editor is not None:
                self.tree.setItemWidget(item, 2, editor)
            return
        for key, child in children:
            label = f"[{key}]" if isinstance(value, list) else key
            child_path = path + (key,)
            child_item = self._new_item(label, child_path, child, item)
            self._populate_item(child_item, child_path, child)
            if isinstance(child, (dict, list)):
                child_item.setExpanded(True)

    def _scalar_editor(self, path, value):
        if self.read_only or isinstance(value, UnsupportedValue):
            return None
        if isinstance(value, bool):
            editor = QCheckBox("已开启" if value else "已关闭")
            editor.setChecked(value)
            editor.setCursor(Qt.CursorShape.PointingHandCursor)
            editor.toggled.connect(
                lambda checked, ed=editor, p=path: (
                    ed.setText("已开启" if checked else "已关闭"),
                    self._update_scalar(p, checked),
                )
            )
            return editor
        if isinstance(value, int):
            editor = QSpinBox()
            editor.setRange(-2_147_483_647, 2_147_483_647)
            editor.setValue(max(-2_147_483_647, min(2_147_483_647, value)))
            editor.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            editor.installEventFilter(_get_no_wheel_filter())
            editor.valueChanged.connect(lambda number: self._update_scalar(path, number))
            return editor
        if isinstance(value, float):
            editor = QDoubleSpinBox()
            editor.setRange(-1e15, 1e15)
            editor.setDecimals(6)
            editor.setValue(value)
            editor.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            editor.installEventFilter(_get_no_wheel_filter())
            editor.valueChanged.connect(lambda number: self._update_scalar(path, number))
            return editor
        str_val = "" if value is None else str(value)
        editor = QLineEdit(str_val)
        editor.setToolTip(str_val)
        editor.textChanged.connect(lambda text, ed=editor: (ed.setToolTip(text), self._update_scalar(path, text)))
        return editor

    def _get(self, path):
        target = self._value
        for component in path:
            target = target[component]
        return target

    def _set(self, path, value):
        if not path:
            self._value = value
            return
        self._get(path[:-1])[path[-1]] = value

    def _update_scalar(self, path, value):
        if not isinstance(self._get(path), UnsupportedValue):
            self._set(path, value)
            self._mark_edited()

    def _selected_path(self):
        item = self.tree.currentItem()
        return None if item is None else item.data(0, Qt.ItemDataRole.UserRole)

    def _update_buttons(self):
        path = self._selected_path()
        if path is None:
            return
        value = self._get(path)
        unsupported = isinstance(value, UnsupportedValue)
        self.add_button.setEnabled(isinstance(value, (dict, list)))
        self.type_button.setEnabled(True)
        self.remove_button.setEnabled(bool(path) and not unsupported)

    def _show_source(self, current, previous=None):
        del previous
        self._update_buttons()
        if self.read_only and isinstance(self._value, UnsupportedValue):
            self.source.setPlainText(self._value.source)
            self.source.setVisible(True)
            return
        if current is None or not self.advanced:
            self.source.setVisible(False)
            return
        value = self._get(current.data(0, Qt.ItemDataRole.UserRole))
        is_unsup = isinstance(value, UnsupportedValue)
        self.source.setPlainText(value.source if is_unsup else "")
        self.source.setVisible(is_unsup)

    def _choose_kind(self):
        kinds = ["string", "number", "boolean", "array", "table"]
        labels = ["文本", "数字", "开关", "列表", "分组"]
        kind, accepted = QInputDialog.getItem(self, "选择内容类型", "新内容的类型：", labels, 0, False)
        if not accepted:
            return None
        return kinds[labels.index(kind)]

    def _add_child(self):
        path = self._selected_path()
        if path is None:
            return
        container = self._get(path)
        if not isinstance(container, (dict, list)):
            return
        kind = self._choose_kind()
        if kind is None:
            return
        if isinstance(container, dict):
            key, accepted = QInputDialog.getText(self, "新增设置项", "名称：")
            if not accepted or not key:
                return
            if key in container:
                key = f"{key}_new"
            container[key] = default_for_kind(kind)
        else:
            container.append(default_for_kind(kind))
        self._mark_edited()
        self.rebuild()

    def _change_type(self):
        path = self._selected_path()
        if path is None or isinstance(self._get(path), UnsupportedValue):
            return
        kind = self._choose_kind()
        if kind is None:
            return
        self._set(path, default_for_kind(kind))
        self._mark_edited()
        self.rebuild()

    def _remove(self):
        path = self._selected_path()
        if not path or isinstance(self._get(path), UnsupportedValue):
            return
        item = self.tree.currentItem()
        label = item.text(0) if item is not None else str(path[-1])
        if callable(getattr(self, "confirm_remove", None)):
            if not self.confirm_remove(path, label):
                return
        elif os.environ.get("QT_QPA_PLATFORM") != "offscreen":
            reply = QMessageBox.question(
                self,
                "确认删除配置项",
                f"确定要删除所选配置项 “{label}” 吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        parent = self._get(path[:-1])
        if isinstance(parent, list):
            parent.pop(path[-1])
        else:
            parent.pop(path[-1], None)
        self._mark_edited()
        self.rebuild()


class FieldEditor(QFrame):
    save_requested = pyqtSignal(object, object, object)
    edited = pyqtSignal()

    def __init__(
        self,
        title,
        field,
        value=None,
        default=None,
        schema=None,
        allow_create=False,
        structured=False,
        auto_save=False,
        advanced=False,
        description="",
        technical_name="",
        choices=None,
        compact=False,
        read_only=False,
        show_location=True,
        show_save_button=True,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("settingCard")
        self.read_only = read_only
        self.show_location = show_location
        self.show_save_button = show_save_button
        self.title = title
        self.field = copy.deepcopy(field) if field is not None else None
        self.creation = bool(self.field and self.field.get("create_option"))
        self.schema = schema or {}
        self.allow_create = allow_create
        self.advanced = advanced
        self.technical_name = technical_name
        self.dirty = False
        self.saving = False
        self._revision_pending = False
        self._queued_after_refresh = False
        self._submitted_value = None
        self._submitted_revision = None
        self._initializing = True
        self.unmanaged = field is None and not allow_create

        initial = value
        if initial is None and field is not None:
            initial = field.get("value")
        if initial is None:
            initial = default
        if initial is None:
            initial = self._schema_default()
        python_value = lua_to_python(initial)
        if python_value is None:
            python_value = self._empty_value()
        self.python_value = copy.deepcopy(python_value)
        kind = value_kind(self.python_value)
        self.structured = structured or kind in {"array", "table", "unsupported"}
        self._auto_save_type = auto_save and kind in {"boolean", "number"}
        self._global_auto_save_enabled = True
        self.auto_save = self._auto_save_type and not self.creation and self._global_auto_save_enabled
        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.setInterval(420)
        self.debounce.timeout.connect(self._save)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("settingTitle")
        self.state_label = QLabel("")
        self.state_label.setObjectName("saveState")
        self.save_button = QPushButton("添加设置" if self.creation else "应用修改")
        self.save_button.setObjectName("accentButton")
        self.save_button.clicked.connect(self._save)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        text_layout.addWidget(self.title_label)
        if technical_name and advanced:
            technical = QLabel(technical_name)
            technical.setObjectName("technicalName")
            text_layout.addWidget(technical)
        header = QHBoxLayout()
        header.addLayout(text_layout, 1)
        header.addWidget(self.state_label)
        header.addWidget(self.save_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10 if compact else 12, 14, 10 if compact else 12)
        layout.setSpacing(7)
        if compact and not self.structured:
            self.editor = self._make_editor(self.python_value, choices)
            header.insertWidget(1, self.editor)
            layout.addLayout(header)
        else:
            layout.addLayout(header)
            self.editor = self._make_editor(self.python_value, choices)
            layout.addWidget(self.editor)
        if description:
            description_label = QLabel(description)
            description_label.setObjectName("settingDescription")
            description_label.setWordWrap(True)
            layout.addWidget(description_label)
        if advanced and self.show_location:
            self.location_label = QLabel(self._location_text())
            self.location_label.setObjectName("technicalName")
            self.location_label.setWordWrap(True)
            self.location_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(self.location_label)
        if isinstance(self.python_value, UnsupportedValue) and not self.read_only:
            explanation = QLabel("这项配置包含暂时无法可视化编辑的内容。为避免破坏原配置，此处只能查看。")
            explanation.setObjectName("settingDescription")
            explanation.setWordWrap(True)
            layout.addWidget(explanation)
        if self.read_only:
            self.save_button.setVisible(False)
            if hasattr(self, "editor") and self.editor is not None and not isinstance(self.editor, LuaValueEditor):
                self.editor.setEnabled(False)
        self._initializing = False
        self._refresh_state()

    def _schema_default(self):
        default = self.schema.get("default")
        return lua_to_python(default) if is_lua_value(default) else copy.deepcopy(default)

    def _empty_value(self):
        schema_type = str(self.schema.get("type", "")).lower()
        if schema_type in {"boolean", "bool"}:
            return False
        if schema_type in {"number", "integer", "float"}:
            return 0
        return ""

    def _make_editor(self, value, choices):
        if self.structured:
            editor = LuaValueEditor(value, advanced=self.advanced, read_only=self.read_only)
            editor.edited.connect(self._on_edited)
            return editor
        schema_type = str(self.schema.get("type", "")).lower()
        if choices:
            editor = QComboBox()
            editor.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            editor.installEventFilter(_get_no_wheel_filter())
            for label, raw in choices:
                editor.addItem(label, raw)
            index = editor.findData(value)
            editor.setCurrentIndex(max(0, index))
            editor.currentIndexChanged.connect(self._on_edited)
            editor.value = editor.currentData
            return editor
        if isinstance(value, bool) or schema_type in {"boolean", "bool"}:
            editor = SwitchWidget(checked=bool(value))
            editor.toggled.connect(self._on_edited)
            editor.value = editor.isChecked
            return editor
        if isinstance(value, int) and not isinstance(value, bool):
            opt_name = (
                self.technical_name
                or (self.schema.get("name") if isinstance(self.schema, dict) else "")
                or (self.field.get("create_option") if isinstance(self.field, dict) else "")
                or ""
            )
            editor = IntegerEdit(value, self._schema_default(), option_name=opt_name)
            editor.setMinimumWidth(210)
            editor.edited.connect(self._on_edited)
            return editor
        if isinstance(value, float):
            editor = QDoubleSpinBox()
            editor.setRange(-1e15, 1e15)
            editor.setDecimals(6)
            editor.setValue(value)
            editor.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            editor.installEventFilter(_get_no_wheel_filter())
            editor.valueChanged.connect(self._on_edited)
            editor.value = editor.value
            return editor
        editor = QLineEdit("" if value is None else str(value))
        editor.setMinimumWidth(190)
        editor.textChanged.connect(self._on_edited)
        editor.returnPressed.connect(self._save)
        editor.value = editor.text
        return editor

    def _location_text(self):
        if self.creation:
            return "尚未写入配置；点击“添加设置”后会显示配置位置"
        if self.field is None:
            return "此默认值仅供查看，当前配置中没有可写入的位置"
        file = format_display_path(self.field.get("file")) or "未知文件"
        line = self.field.get("line")
        location = f"{file}:{line}" if line is not None else file
        rev = str(self.field.get("revision") or "")
        short_rev = rev[:8] if len(rev) > 8 else rev
        return f"{location} · #{short_rev}" if short_rev else location

    def _refresh_state(self):
        current_val = self.value() if hasattr(self, "editor") and self.editor is not None else None
        is_unsup = (
            isinstance(current_val, dict) and current_val.get("kind") == "unsupported"
        ) or (current_val is None and isinstance(self.python_value, UnsupportedValue))
        read_only = self.read_only or is_unsup
        editable = self.field is not None and not read_only
        if isinstance(self.editor, LuaValueEditor):
            self.editor.setEnabled(True)
        else:
            self.editor.setEnabled(self.field is not None and not self.read_only)
        self.save_button.setText("+ 添加" if self.creation else "保存")
        self.save_button.setVisible(self.show_save_button and editable and not self.auto_save)
        is_active_btn = editable and (self.dirty or self.creation) and not self.saving and not self._revision_pending
        self.save_button.setEnabled(is_active_btn)
        dirty_prop = "true" if (self.dirty or self.creation or not self._global_auto_save_enabled) else "false"
        if self.save_button.property("dirty") != dirty_prop:
            self.save_button.setProperty("dirty", dirty_prop)
            st = self.save_button.style()
            if st is not None:
                st.unpolish(self.save_button)
                st.polish(self.save_button)
        if self.unmanaged:
            self.state_label.setText("使用编辑器默认设置")
        elif self.field is None:
            self.state_label.setText("当前无法修改")
        elif self.saving:
            self.state_label.setText("正在添加…" if self.creation else "正在保存…")
        elif self._revision_pending and self.dirty:
            self.state_label.setText("正在同步最新修改…")
        elif self.dirty:
            self.state_label.setText("尚未添加" if self.creation else ("尚未保存" if not self.auto_save else "等待自动保存…"))
        elif isinstance(getattr(self, "editor", None), QLineEdit) and self.editor.text() == " " and not self._revision_pending:
            self.state_label.setText('当前值: 空格 (" ")')
        elif not self._revision_pending:
            self.state_label.setText("")

    def _on_edited(self, *args):
        del args
        if self._initializing:
            return
        self.dirty = True
        if self.saving or self._revision_pending:
            self._queued_after_refresh = True
            self.debounce.stop()
        elif self.auto_save:
            self.debounce.start()
        self._refresh_state()
        self.edited.emit()

    def value(self):
        if isinstance(self.editor, LuaValueEditor):
            return self.editor.value()
        return python_to_lua(self.editor.value())

    def save(self):
        self._save()

    def _save(self):
        current_val = self.value()
        is_unsup = isinstance(current_val, dict) and current_val.get("kind") == "unsupported"
        if self.field is None or self.unmanaged or self.read_only or is_unsup:
            return
        if self.saving or self._revision_pending:
            if not self.creation:
                self._queued_after_refresh = True
            self._refresh_state()
            return
        self.debounce.stop()
        self._submitted_value = copy.deepcopy(self.value())
        self._submitted_revision = self.field.get("revision")
        self.saving = True
        self._refresh_state()
        self.save_requested.emit(self.field, copy.deepcopy(self._submitted_value), self)

    def save_succeeded(self, feedback):
        self.saving = False
        self._revision_pending = True
        self.dirty = self.value() != self._submitted_value
        if not self.dirty:
            if isinstance(self.editor, LuaValueEditor):
                self.editor.mark_saved()
            self._queued_after_refresh = False
        self.state_label.setText(feedback)
        self._refresh_state()
        self.state_label.setText(feedback)

    def save_failed(self, feedback):
        self.saving = False
        self._revision_pending = False
        self._queued_after_refresh = False
        self.debounce.stop()
        self.dirty = True
        self._refresh_state()
        self.state_label.setText(feedback)

    def update_field(self, field):
        if not isinstance(field, dict):
            return
        became_managed = self.creation and not field.get("create_option")
        self.field = copy.deepcopy(field)
        if became_managed:
            self.creation = False
            self.auto_save = self._auto_save_type and self._global_auto_save_enabled
            self.unmanaged = False
        if self.advanced and hasattr(self, "location_label"):
            self.location_label.setText(self._location_text())
        if not self._revision_pending:
            self._refresh_state()
            return
        if field.get("revision") == self._submitted_revision:
            return
        self._revision_pending = False
        should_save = self.auto_save and self.dirty and (self._queued_after_refresh or became_managed)
        self._queued_after_refresh = False
        self._refresh_state()
        if became_managed and not self.dirty:
            focused = QApplication.focusWidget()
            if focused is not None and self.isAncestorOf(focused):
                focused.clearFocus()
        if should_save:
            self.debounce.start(0)

    def set_auto_save_enabled(self, enabled: bool):
        self._global_auto_save_enabled = bool(enabled)
        self.auto_save = self._auto_save_type and not self.creation and self._global_auto_save_enabled
        if not self.auto_save:
            self.debounce.stop()
        elif self.dirty and not self.saving and not self._revision_pending:
            self.debounce.start()
        self._refresh_state()

    def bind_slot(self, field, value, default, allow_create=False, auto_save=False):
        """Fast in-place rebinding of a FieldEditor for another plugin without recreating widgets."""
        self.field = copy.deepcopy(field) if field else None
        self.creation = bool(self.field and (self.field.get("create_option") or self.field.get("create_plugin_slot")))
        self.unmanaged = self.field is None and not allow_create
        self._auto_save_type = bool(auto_save)
        self.auto_save = self._auto_save_type and not self.creation and self._global_auto_save_enabled
        self.saving = False
        self._revision_pending = False
        self._queued_after_refresh = False
        self._submitted_value = None
        self._submitted_revision = None
        self.state_label.setText("")
        initial = value if value is not None else default
        if initial is None:
            initial = self._empty_value()
        self.set_editor_value(initial)

    def set_editor_value(self, lua_or_py_val):
        py_val = lua_to_python(lua_or_py_val)
        self.python_value = copy.deepcopy(py_val)
        self._initializing = True
        try:
            if isinstance(self.editor, LuaValueEditor):
                if self.editor.dirty or self.editor._value != py_val:
                    self.editor._value = copy.deepcopy(py_val)
                    self.editor.dirty = False
                    self.editor.rebuild()
                else:
                    self.editor.dirty = False
            elif isinstance(self.editor, QComboBox):
                idx = self.editor.findData(py_val)
                self.editor.setCurrentIndex(max(0, idx))
            elif isinstance(self.editor, SwitchWidget) or hasattr(self.editor, "setChecked"):
                self.editor.setChecked(bool(py_val))
            elif isinstance(self.editor, IntegerEdit):
                self.editor.set_value(py_val)
            elif hasattr(self.editor, "setValue"):
                self.editor.setValue(float(py_val or 0))
            elif hasattr(self.editor, "setText"):
                self.editor.setText("" if py_val is None else str(py_val))
        finally:
            self._initializing = False
        self.dirty = False
        self.debounce.stop()
        self._refresh_state()

    def discard_changes(self):
        if self.field is not None and "value" in self.field:
            self.set_editor_value(self.field.get("value"))
        else:
            self.set_editor_value(self.python_value)
        self.state_label.setText("")

    def is_editing(self):
        if getattr(self, "read_only", False):
            return False
        focused = QApplication.focusWidget()
        return (
            self.dirty
            or self.saving
            or self._revision_pending
            or (focused is not None and self.isAncestorOf(focused))
        )


MODE_CHOICES = [
    ("n", "普通模式 (n)"),
    ("i", "插入模式 (i)"),
    ("v", "可视模式 (v)"),
    ("x", "仅可视模式 (x)"),
    ("s", "选择模式 (s)"),
    ("o", "操作符挂起 (o)"),
    ("t", "终端模式 (t)"),
    ("c", "命令行模式 (c)"),
]


class KeymapCard(QFrame):
    """
    Unified Keymap Card Component for Milestone 2.
    - Single card container with modern Tokyo Night styling
    - Unified header with mode badge, key chord, arrow, and target preview
    - Grid/Flex inputs with responsive stretch factors preventing text truncation
    - Collapsible advanced options with common switches (silent, expr, etc.)
    - Single card footer with status label and unified save button
    - Coordinated sequential save queue preventing HTTP 409 Conflict revision mismatches
    """
    save_requested = pyqtSignal(object, object, object)  # (field, new_value, card)
    batch_save_requested = pyqtSignal(object, object)  # ([(field, new_value), ...], card)
    delete_requested = pyqtSignal(object, object)  # (field, card)
    edited = pyqtSignal()

    def __init__(self, keymap_data, parent=None):
        super().__init__(parent)
        self.setObjectName("keymapCard")
        self.keymap_data = copy.deepcopy(keymap_data)

        # Field references
        self.field_lhs = self.keymap_data.get("lhs") or {}
        self.field_mode = self.keymap_data.get("mode") or {}
        self.field_rhs = self.keymap_data.get("rhs") or {}
        self.field_opts = self.keymap_data.get("opts") or {}

        # Initial values
        self.initial_lhs = self._scalar_str(self.field_lhs.get("value"), "")
        self.initial_mode = self._scalar_str(self.field_mode.get("value"), "n")
        self.initial_rhs = self._scalar_str(self.field_rhs.get("value"), "")
        opts_raw = lua_to_python(self.field_opts.get("value"))
        self.initial_opts = opts_raw if isinstance(opts_raw, dict) else {}

        # Working values
        self.current_lhs = self.initial_lhs
        self.current_mode = self.initial_mode
        self.current_rhs = self.initial_rhs
        self.current_opts = copy.deepcopy(self.initial_opts)

        # State tracking
        self.dirty = False
        self.saving = False
        self.creation = False
        self._revision_pending = False
        self._save_queue = []
        self.title = f"快捷键 {self.current_lhs}"

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(9)

        # ---------------- 1. Header Row ----------------
        header = QHBoxLayout()
        header.setSpacing(8)

        # Mode Badge
        self.mode_badge = QLabel(f" {self.current_mode} ")
        self.mode_badge.setObjectName("keymapModeBadge")
        header.addWidget(self.mode_badge)

        # Key Chord Title
        self.chord_label = QLabel(self.current_lhs or "<未指定>")
        self.chord_label.setObjectName("keymapChordTitle")
        header.addWidget(self.chord_label)

        # Arrow indicator
        arrow = QLabel("->")
        arrow.setObjectName("keymapArrow")
        header.addWidget(arrow)

        # Target preview
        self.rhs_preview = QLabel(self.current_rhs)
        self.rhs_preview.setObjectName("keymapRhsSummary")
        self.rhs_preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        header.addWidget(self.rhs_preview, 1)

        # Optional description badge
        desc_str = str(self.current_opts.get("desc", "") or "").strip()
        self.desc_badge = QLabel(f" {desc_str} " if desc_str else "")
        self.desc_badge.setObjectName("keymapDescBadge")
        self.desc_badge.setVisible(bool(desc_str))
        header.addWidget(self.desc_badge)

        # Location tag (right-aligned)
        loc = ""
        full_loc = ""
        file_path = self.field_lhs.get("file") or self.field_rhs.get("file")
        line_no = self.field_lhs.get("line") or self.field_rhs.get("line")
        if file_path:
            short_path = format_display_path(file_path)
            loc = f"{short_path}:{line_no}" if line_no else str(short_path)
            full_loc = f"{file_path}:{line_no}" if line_no else str(file_path)
        self.loc_label = QLabel(loc)
        self.loc_label.setToolTip(full_loc)
        self.loc_label.setObjectName("technicalName")
        header.addWidget(self.loc_label)

        layout.addLayout(header)

        # ---------------- 2. Body: Responsive Inputs ----------------
        # Row 1: LHS & Mode
        row1 = QHBoxLayout()
        row1.setSpacing(10)

        lhs_label = QLabel("按键 (LHS):")
        lhs_label.setObjectName("keymapFieldLabel")
        lhs_label.setFixedWidth(72)
        row1.addWidget(lhs_label)

        self.lhs_edit = QLineEdit(self.current_lhs)
        self.lhs_edit.setPlaceholderText("例如: <leader>ff 或 <C-p>")
        self.lhs_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.lhs_edit.setMinimumWidth(140)
        self.lhs_edit.textChanged.connect(self._on_inputs_changed)
        self.lhs_edit.returnPressed.connect(self.save)
        row1.addWidget(self.lhs_edit, 2)

        mode_label = QLabel("模式:")
        mode_label.setObjectName("keymapFieldLabel")
        mode_label.setFixedWidth(38)
        row1.addWidget(mode_label)

        self.mode_combo = QComboBox()
        for code, label in MODE_CHOICES:
            self.mode_combo.addItem(label, code)
        idx = self.mode_combo.findData(self.current_mode)
        if idx >= 0:
            self.mode_combo.setCurrentIndex(idx)
        elif self.current_mode:
            self.mode_combo.addItem(f"模式 ({self.current_mode})", self.current_mode)
            self.mode_combo.setCurrentIndex(self.mode_combo.count() - 1)
        self.mode_combo.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.mode_combo.setMinimumWidth(120)
        self.mode_combo.setMaximumWidth(240)
        self.mode_combo.currentIndexChanged.connect(self._on_inputs_changed)
        row1.addWidget(self.mode_combo, 1)

        layout.addLayout(row1)

        # Row 2: RHS Command
        row2 = QHBoxLayout()
        row2.setSpacing(10)

        rhs_label = QLabel("命令 (RHS):")
        rhs_label.setObjectName("keymapFieldLabel")
        rhs_label.setFixedWidth(72)
        row2.addWidget(rhs_label)

        self.rhs_edit = QLineEdit(self.current_rhs)
        self.rhs_edit.setPlaceholderText("例如: <cmd>Telescope find_files<cr> 或 :w<CR>")
        self.rhs_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.rhs_edit.setMinimumWidth(240)
        self.rhs_edit.textChanged.connect(self._on_inputs_changed)
        self.rhs_edit.returnPressed.connect(self.save)
        row2.addWidget(self.rhs_edit, 1)

        layout.addLayout(row2)

        # Row 3: Collapsible Advanced Opts
        self.opts_container = QWidget()
        opts_layout = QVBoxLayout(self.opts_container)
        opts_layout.setContentsMargins(0, 4, 0, 4)
        opts_layout.setSpacing(6)

        opts_switches = QHBoxLayout()
        opts_switches.setSpacing(16)

        self.opt_silent = QCheckBox("silent (静音)")
        self.opt_silent.setChecked(bool(self.current_opts.get("silent", False)))
        self.opt_silent.stateChanged.connect(self._on_opts_changed)
        opts_switches.addWidget(self.opt_silent)

        self.opt_noremap = QCheckBox("noremap (非递归)")
        self.opt_noremap.setChecked(bool(self.current_opts.get("noremap", True)))
        self.opt_noremap.stateChanged.connect(self._on_opts_changed)
        opts_switches.addWidget(self.opt_noremap)

        self.opt_expr = QCheckBox("expr (表达式)")
        self.opt_expr.setChecked(bool(self.current_opts.get("expr", False)))
        self.opt_expr.stateChanged.connect(self._on_opts_changed)
        opts_switches.addWidget(self.opt_expr)

        self.opt_nowait = QCheckBox("nowait (不等待)")
        self.opt_nowait.setChecked(bool(self.current_opts.get("nowait", False)))
        self.opt_nowait.stateChanged.connect(self._on_opts_changed)
        opts_switches.addWidget(self.opt_nowait)

        opts_switches.addStretch(1)
        opts_layout.addLayout(opts_switches)

        # Opt desc row
        desc_row = QHBoxLayout()
        desc_label = QLabel("按键描述 (desc):")
        desc_label.setObjectName("settingDescription")
        desc_label.setFixedWidth(100)
        desc_row.addWidget(desc_label)

        self.desc_edit = QLineEdit(str(self.current_opts.get("desc", "")))
        self.desc_edit.setPlaceholderText("例如: Find Files (which-key 提示文字)")
        self.desc_edit.textChanged.connect(self._on_opts_changed)
        desc_row.addWidget(self.desc_edit, 1)
        opts_layout.addLayout(desc_row)

        self.opts_container.setVisible(False)
        layout.addWidget(self.opts_container)

        # ---------------- 4. Unified Card Footer ----------------
        footer = QHBoxLayout()
        footer.setContentsMargins(0, 2, 0, 0)
        footer.setSpacing(10)

        self.toggle_opts_btn = QPushButton("展开高级选项 (opts)")
        self.toggle_opts_btn.setObjectName("sectionToggle")
        self.toggle_opts_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_opts_btn.clicked.connect(self._toggle_opts)
        footer.addWidget(self.toggle_opts_btn)

        # Status label
        self.status_label = QLabel("")
        self.status_label.setObjectName("keymapStatusLabel")
        self.status_label.setWordWrap(True)
        self.status_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        footer.addWidget(self.status_label, 1)

        # Delete Button (compact M3 Tonal Error Pill with vector icon)
        p = get_current_palette()
        self.delete_button = QPushButton("")
        self.delete_button.setIcon(get_md3_icon("delete", p.get("red", "#f7768e"), 16))
        self.delete_button.setIconSize(QSize(16, 16))
        self.delete_button.setObjectName("dangerButton")
        self.delete_button.setFixedWidth(40)
        self.delete_button.setFixedHeight(28)
        self.delete_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_button.setToolTip("从配置文件中删除此快捷键")
        self.delete_button.clicked.connect(self._on_delete_clicked)
        footer.addWidget(self.delete_button)

        # Single Save Button (visually hidden when clean via M3 [dirty="false"] rule)
        self.save_button = QPushButton("保存")
        self.save_button.setObjectName("accentButton")
        self.save_button.setProperty("dirty", "false")
        self.save_button.setMinimumWidth(78)
        self.save_button.setFixedHeight(28)
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save)
        footer.addWidget(self.save_button)

        layout.addLayout(footer)

    def _on_delete_clicked(self):
        target_field = self.field_mode or self.field_lhs or self.field_rhs or self.field_opts
        if not target_field or not target_field.get("id"):
            return
        if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
            reply = QMessageBox.question(
                self,
                "确认删除快捷键",
                f"确定要从配置文件中删除快捷键 “{self.current_lhs}” 吗？\n（系统将自动创建配置备份快照）",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self.delete_requested.emit(target_field, self)

    def _toggle_opts(self):
        is_visible = self.opts_container.isVisible()
        self.opts_container.setVisible(not is_visible)
        self.toggle_opts_btn.setText("收起高级选项 (opts)" if not is_visible else "展开高级选项 (opts)")

    def _on_inputs_changed(self):
        self.current_lhs = self.lhs_edit.text()
        self.current_mode = self.mode_combo.currentData() or "n"
        self.current_rhs = self.rhs_edit.text()

        self.mode_badge.setText(f" {self.current_mode} ")
        self.chord_label.setText(self.current_lhs or "<未指定>")
        self.rhs_preview.setText(self.current_rhs)

        self._check_dirty()

    def _on_opts_changed(self):
        self.current_opts["silent"] = self.opt_silent.isChecked()
        self.current_opts["noremap"] = self.opt_noremap.isChecked()
        self.current_opts["expr"] = self.opt_expr.isChecked()
        self.current_opts["nowait"] = self.opt_nowait.isChecked()
        desc_val = self.desc_edit.text().strip()
        if desc_val:
            self.current_opts["desc"] = desc_val
        elif "desc" in self.current_opts:
            del self.current_opts["desc"]
        if hasattr(self, "desc_badge"):
            self.desc_badge.setText(f" {desc_val} " if desc_val else "")
            self.desc_badge.setVisible(bool(desc_val))

        self._check_dirty()

    def _sync_save_btn_dirty(self):
        dirty_prop = "true" if self.dirty else "false"
        if self.save_button.property("dirty") != dirty_prop:
            self.save_button.setProperty("dirty", dirty_prop)
            st = self.save_button.style()
            if st is not None:
                st.unpolish(self.save_button)
                st.polish(self.save_button)

    def _check_dirty(self):
        lhs_dirty = (self.current_lhs != self.initial_lhs)
        mode_dirty = (self.current_mode != self.initial_mode)
        rhs_dirty = (self.current_rhs != self.initial_rhs)
        opts_dirty = (self.current_opts != self.initial_opts)

        self.dirty = lhs_dirty or mode_dirty or rhs_dirty or opts_dirty
        self._sync_save_btn_dirty()

        if self.dirty:
            changed = []
            if lhs_dirty:
                changed.append("按键")
            if mode_dirty:
                changed.append("模式")
            if rhs_dirty:
                changed.append("命令")
            if opts_dirty:
                changed.append("选项")
            set_status_label(self.status_label, f"已修改 ({', '.join(changed)})，尚未保存", "modified")
            self.save_button.setEnabled(not self.saving)
        else:
            set_status_label(self.status_label, "", "muted")
            self.save_button.setEnabled(False)

        self.edited.emit()

    def discard_changes(self):
        self._sync_inputs_from_initial()
        self.dirty = False
        self._sync_save_btn_dirty()
        set_status_label(self.status_label, "", "muted")
        self.save_button.setEnabled(False)

    def is_editing(self):
        focused = QApplication.focusWidget()
        return (
            self.dirty
            or self.saving
            or self._revision_pending
            or (focused is not None and self.isAncestorOf(focused))
        )

    def save(self):
        if not self.dirty or self.saving:
            return

        self.saving = True
        self.save_button.setEnabled(False)
        set_status_label(self.status_label, "正在保存…", "info")

        self._save_queue = []
        if self.current_lhs != self.initial_lhs:
            self._save_queue.append(("lhs", self.field_lhs, python_to_lua(self.current_lhs)))
        if self.current_mode != self.initial_mode:
            self._save_queue.append(("mode", self.field_mode, python_to_lua(self.current_mode)))
        if self.current_rhs != self.initial_rhs:
            self._save_queue.append(("rhs", self.field_rhs, python_to_lua(self.current_rhs)))
        if self.current_opts != self.initial_opts:
            self._save_queue.append(("opts", self.field_opts, python_to_lua(self.current_opts)))

        if len(self._save_queue) > 1 and self.receivers(self.batch_save_requested) > 0:
            batch_items = [(f, v) for _, f, v in self._save_queue]
            self._save_queue = [self._save_queue[-1]]
            self.title = f"快捷键 {self.current_lhs}"
            self.batch_save_requested.emit(batch_items, self)
        else:
            self._send_next_save()

    def _send_next_save(self):
        if not self._save_queue:
            self._on_all_saved()
            return
        field_name, field, val = self._save_queue[0]
        self.title = f"快捷键 {self.current_lhs} ({field_name})"
        self.save_requested.emit(field, val, self)

    def save_succeeded(self, feedback="已保存并生效"):
        if self._save_queue:
            self._save_queue.pop(0)

        if not self._save_queue:
            self._on_all_saved(feedback)
        else:
            set_status_label(self.status_label, "正在同步并保存后续修改…", "info")

    def save_failed(self, feedback="保存失败"):
        self.saving = False
        self._save_queue.clear()
        self.save_button.setEnabled(True)
        set_status_label(self.status_label, feedback, "error")

    def _on_all_saved(self, feedback="已保存并生效"):
        self.saving = False
        self.dirty = False
        self._sync_save_btn_dirty()
        self.initial_lhs = self.current_lhs
        self.initial_mode = self.current_mode
        self.initial_rhs = self.current_rhs
        self.initial_opts = copy.deepcopy(self.current_opts)
        set_status_label(self.status_label, feedback, "saved")
        self.save_button.setEnabled(False)

    @staticmethod
    def _scalar_str(raw_val, default="") -> str:
        py_val = lua_to_python(raw_val)
        if py_val is None:
            return default
        if isinstance(py_val, UnsupportedValue):
            return py_val.source
        if isinstance(py_val, list):
            return ",".join(str(x.source if isinstance(x, UnsupportedValue) else x) for x in py_val)
        return str(py_val)

    def update_snapshot_fields(self, new_keymap):
        if not self.saving and self.keymap_data == new_keymap:
            return
        self.keymap_data = copy.deepcopy(new_keymap)
        self.field_lhs = self.keymap_data.get("lhs") or {}
        self.field_mode = self.keymap_data.get("mode") or {}
        self.field_rhs = self.keymap_data.get("rhs") or {}
        self.field_opts = self.keymap_data.get("opts") or {}

        if not self.dirty and not self.saving:
            self.initial_lhs = self._scalar_str(self.field_lhs.get("value"), "")
            self.initial_mode = self._scalar_str(self.field_mode.get("value"), "n")
            self.initial_rhs = self._scalar_str(self.field_rhs.get("value"), "")
            opts_raw = lua_to_python(self.field_opts.get("value"))
            self.initial_opts = opts_raw if isinstance(opts_raw, dict) else {}
            self._sync_inputs_from_initial()

        if self.saving and self._save_queue:
            next_name, _, val = self._save_queue[0]
            field_map = {
                "lhs": self.field_lhs,
                "mode": self.field_mode,
                "rhs": self.field_rhs,
                "opts": self.field_opts,
            }
            self._save_queue[0] = (next_name, field_map.get(next_name, {}), val)
            self._send_next_save()

    def _sync_inputs_from_initial(self):
        self.current_lhs = self.initial_lhs
        self.current_mode = self.initial_mode
        self.current_rhs = self.initial_rhs
        self.current_opts = copy.deepcopy(self.initial_opts)

        self.lhs_edit.blockSignals(True)
        self.lhs_edit.setText(self.current_lhs)
        self.lhs_edit.blockSignals(False)

        idx = self.mode_combo.findData(self.current_mode)
        if idx >= 0:
            self.mode_combo.blockSignals(True)
            self.mode_combo.setCurrentIndex(idx)
            self.mode_combo.blockSignals(False)
        elif self.current_mode:
            self.mode_combo.blockSignals(True)
            self.mode_combo.addItem(f"模式 ({self.current_mode})", self.current_mode)
            self.mode_combo.setCurrentIndex(self.mode_combo.count() - 1)
            self.mode_combo.blockSignals(False)

        self.rhs_edit.blockSignals(True)
        self.rhs_edit.setText(self.current_rhs)
        self.rhs_edit.blockSignals(False)

        self.opt_silent.blockSignals(True)
        self.opt_silent.setChecked(bool(self.current_opts.get("silent", False)))
        self.opt_silent.blockSignals(False)

        self.opt_noremap.blockSignals(True)
        self.opt_noremap.setChecked(bool(self.current_opts.get("noremap", True)))
        self.opt_noremap.blockSignals(False)

        self.opt_expr.blockSignals(True)
        self.opt_expr.setChecked(bool(self.current_opts.get("expr", False)))
        self.opt_expr.blockSignals(False)

        self.opt_nowait.blockSignals(True)
        self.opt_nowait.setChecked(bool(self.current_opts.get("nowait", False)))
        self.opt_nowait.blockSignals(False)

        self.desc_edit.blockSignals(True)
        self.desc_edit.setText(str(self.current_opts.get("desc", "")))
        self.desc_edit.blockSignals(False)

        self.mode_badge.setText(f" {self.current_mode} ")
        self.chord_label.setText(self.current_lhs or "<未指定>")
        self.rhs_preview.setText(self.current_rhs)
        desc_str = str(self.current_opts.get("desc", "") or "").strip()
        if hasattr(self, "desc_badge"):
            self.desc_badge.setText(f" {desc_str} " if desc_str else "")
            self.desc_badge.setVisible(bool(desc_str))

        loc = ""
        full_loc = ""
        file_path = self.field_lhs.get("file") or self.field_rhs.get("file")
        line_no = self.field_lhs.get("line") or self.field_rhs.get("line")
        if file_path:
            short_path = format_display_path(file_path)
            loc = f"{short_path}:{line_no}" if line_no else str(short_path)
            full_loc = f"{file_path}:{line_no}" if line_no else str(file_path)
        self.loc_label.setText(loc)
        self.loc_label.setToolTip(full_loc)


class NewKeymapCard(QFrame):
    """Inline creation card for adding a new Neovim keymap."""
    create_requested = pyqtSignal(object, object, object, object, object)
    cancelled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("keymapCard")
        self.creation = True
        self.saving = False
        self.dirty = False
        self.title = "新增快捷键"
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(9)

        header = QHBoxLayout()
        header.setSpacing(8)

        badge = QLabel(" 新增快捷键 ")
        badge.setObjectName("newCardBadge")
        badge.setProperty("kind", "keymap")
        header.addWidget(badge)

        self.mode_badge = QLabel(" n ")
        self.mode_badge.setObjectName("keymapModeBadge")
        header.addWidget(self.mode_badge)

        self.chord_label = QLabel("<未指定按键>")
        self.chord_label.setObjectName("keymapChordTitle")
        header.addWidget(self.chord_label)

        arrow = QLabel("->")
        arrow.setObjectName("keymapArrow")
        header.addWidget(arrow)

        self.rhs_preview = QLabel("<未指定命令>")
        self.rhs_preview.setObjectName("keymapRhsSummary")
        self.rhs_preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        header.addWidget(self.rhs_preview, 1)

        target_hint = QLabel("写入 keymaps.lua / init.lua")
        target_hint.setObjectName("technicalName")
        header.addWidget(target_hint)

        layout.addLayout(header)

        row1 = QHBoxLayout()
        row1.setSpacing(10)

        lhs_label = QLabel("按键 (LHS):")
        lhs_label.setObjectName("keymapFieldLabel")
        lhs_label.setFixedWidth(72)
        row1.addWidget(lhs_label)

        self.lhs_edit = QLineEdit()
        self.lhs_edit.setPlaceholderText("例如: <leader>w 或 <C-s>")
        self.lhs_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.lhs_edit.setMinimumWidth(140)
        self.lhs_edit.textChanged.connect(self._on_changed)
        self.lhs_edit.returnPressed.connect(self.save)
        row1.addWidget(self.lhs_edit, 2)

        mode_label = QLabel("模式:")
        mode_label.setObjectName("keymapFieldLabel")
        mode_label.setFixedWidth(38)
        row1.addWidget(mode_label)

        self.mode_combo = QComboBox()
        for code, label in MODE_CHOICES:
            self.mode_combo.addItem(label, code)
        self.mode_combo.setCurrentIndex(0)
        self.mode_combo.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.mode_combo.setMinimumWidth(120)
        self.mode_combo.setMaximumWidth(240)
        self.mode_combo.currentIndexChanged.connect(self._on_changed)
        row1.addWidget(self.mode_combo, 1)

        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(10)

        rhs_label = QLabel("命令 (RHS):")
        rhs_label.setObjectName("keymapFieldLabel")
        rhs_label.setFixedWidth(72)
        row2.addWidget(rhs_label)

        self.rhs_edit = QLineEdit()
        self.rhs_edit.setPlaceholderText("例如: <cmd>w<CR> 或 :Telescope find_files<CR>")
        self.rhs_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.rhs_edit.setMinimumWidth(240)
        self.rhs_edit.textChanged.connect(self._on_changed)
        self.rhs_edit.returnPressed.connect(self.save)
        row2.addWidget(self.rhs_edit, 1)

        layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.setSpacing(10)

        desc_label = QLabel("描述 (desc):")
        desc_label.setObjectName("keymapFieldLabel")
        desc_label.setFixedWidth(72)
        row3.addWidget(desc_label)

        self.desc_edit = QLineEdit()
        self.desc_edit.setPlaceholderText("可选：快捷键说明（如 Save file，用于 which-key 提示）")
        self.desc_edit.textChanged.connect(self._on_changed)
        self.desc_edit.returnPressed.connect(self.save)
        row3.addWidget(self.desc_edit, 1)

        layout.addLayout(row3)

        opts_switches = QHBoxLayout()
        opts_switches.setSpacing(16)

        self.opt_noremap = QCheckBox("noremap (非递归)")
        self.opt_noremap.setChecked(True)
        opts_switches.addWidget(self.opt_noremap)

        self.opt_silent = QCheckBox("silent (静音)")
        self.opt_silent.setChecked(True)
        opts_switches.addWidget(self.opt_silent)

        self.opt_expr = QCheckBox("expr (表达式)")
        self.opt_expr.setChecked(False)
        opts_switches.addWidget(self.opt_expr)

        self.opt_nowait = QCheckBox("nowait (不等待)")
        self.opt_nowait.setChecked(False)
        opts_switches.addWidget(self.opt_nowait)

        opts_switches.addStretch(1)
        layout.addLayout(opts_switches)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 4, 0, 0)
        footer.setSpacing(10)

        self.status_label = QLabel("填写按键 (LHS) 与命令 (RHS) 后点击“添加快捷键”")
        self.status_label.setObjectName("keymapStatusLabel")
        self.status_label.setProperty("status", "muted")
        self.status_label.setWordWrap(True)
        footer.addWidget(self.status_label, 1)

        self.cancel_button = QPushButton("取消")
        self.cancel_button.setMinimumWidth(68)
        self.cancel_button.setFixedHeight(28)
        self.cancel_button.clicked.connect(self._on_cancel)
        footer.addWidget(self.cancel_button)

        self.save_button = QPushButton("添加快捷键")
        self.save_button.setObjectName("accentButton")
        self.save_button.setMinimumWidth(96)
        self.save_button.setFixedHeight(28)
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save)
        footer.addWidget(self.save_button)

        layout.addLayout(footer)

    def focus_first_input(self):
        self.lhs_edit.setFocus()
        self.lhs_edit.selectAll()

    def reset_form(self):
        self.saving = False
        self.dirty = False
        self.lhs_edit.blockSignals(True)
        self.rhs_edit.blockSignals(True)
        self.desc_edit.blockSignals(True)
        self.lhs_edit.clear()
        self.rhs_edit.clear()
        self.desc_edit.clear()
        self.lhs_edit.blockSignals(False)
        self.rhs_edit.blockSignals(False)
        self.desc_edit.blockSignals(False)
        self.mode_combo.setCurrentIndex(0)
        self.opt_noremap.setChecked(True)
        self.opt_silent.setChecked(True)
        self.opt_expr.setChecked(False)
        self.opt_nowait.setChecked(False)
        self._on_changed()

    def _on_cancel(self):
        self.reset_form()
        self.cancelled.emit()

    def _on_changed(self):
        lhs = self.lhs_edit.text().strip()
        rhs = self.rhs_edit.text().strip()
        mode = self.mode_combo.currentData() or "n"
        self.mode_badge.setText(f" {mode} ")
        self.chord_label.setText(lhs or "<未指定按键>")
        self.rhs_preview.setText(rhs or "<未指定命令>")
        valid = bool(lhs and rhs)
        self.dirty = bool(lhs or rhs or self.desc_edit.text().strip())
        self.save_button.setEnabled(valid and not self.saving)
        if not self.saving:
            if valid:
                set_status_label(self.status_label, "准备就绪，点击“添加快捷键”保存并同步", "info")
            else:
                set_status_label(self.status_label, "填写按键 (LHS) 与命令 (RHS) 后点击“添加快捷键”", "muted")

    def save(self):
        lhs = self.lhs_edit.text().strip()
        rhs = self.rhs_edit.text().strip()
        mode = self.mode_combo.currentData() or "n"
        if not lhs or not rhs or self.saving:
            return
        opts = {}
        if self.opt_noremap.isChecked():
            opts["noremap"] = True
        if self.opt_silent.isChecked():
            opts["silent"] = True
        if self.opt_expr.isChecked():
            opts["expr"] = True
        if self.opt_nowait.isChecked():
            opts["nowait"] = True
        desc = self.desc_edit.text().strip()
        if desc:
            opts["desc"] = desc

        self.saving = True
        self.save_button.setEnabled(False)
        self.title = f"快捷键 {lhs}"
        set_status_label(self.status_label, "正在添加快捷键…", "info")
        self.create_requested.emit(
            python_to_lua(mode),
            python_to_lua(lhs),
            python_to_lua(rhs),
            python_to_lua(opts),
            self,
        )

    def save_succeeded(self, feedback="已保存并生效"):
        self.saving = False
        self.dirty = False
        self.reset_form()
        set_status_label(self.status_label, feedback, "saved")
        self.cancelled.emit()

    def save_failed(self, feedback="添加失败"):
        self.saving = False
        self.save_button.setEnabled(bool(self.lhs_edit.text().strip() and self.rhs_edit.text().strip()))
        set_status_label(self.status_label, feedback, "error")

    def discard_changes(self):
        self.reset_form()

    def is_editing(self):
        focused = QApplication.focusWidget()
        return self.dirty or self.saving or (focused is not None and self.isAncestorOf(focused))


class NewPluginCard(QFrame):
    """Inline creation card for adding a new Neovim plugin (lazy.nvim, packer.nvim, or vim-plug)."""
    create_requested = pyqtSignal(object, object)
    cancelled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("groupCard")
        self.creation = True
        self.saving = False
        self.dirty = False
        self.title = "新增插件"
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(9)

        header = QHBoxLayout()
        header.setSpacing(8)

        badge = QLabel(" 新增插件 ")
        badge.setObjectName("newCardBadge")
        badge.setProperty("kind", "plugin")
        header.addWidget(badge)

        self.mgr_badge = QLabel(" lazy.nvim ")
        self.mgr_badge.setObjectName("pluginManagerBadge")
        self.mgr_badge.setProperty("manager", "lazy")
        header.addWidget(self.mgr_badge)

        self.repo_preview = QLabel("<未指定仓库>")
        self.repo_preview.setObjectName("groupTitle")
        self.repo_preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        header.addWidget(self.repo_preview, 1)

        self.target_hint = QLabel("自动写入 lua/plugins/<name>.lua")
        self.target_hint.setObjectName("technicalName")
        header.addWidget(self.target_hint)

        layout.addLayout(header)

        row1 = QHBoxLayout()
        row1.setSpacing(10)

        source_label = QLabel("插件仓库:")
        source_label.setObjectName("keymapFieldLabel")
        source_label.setFixedWidth(72)
        row1.addWidget(source_label)

        self.source_edit = QLineEdit()
        self.source_edit.setPlaceholderText("例如: folke/tokyonight.nvim 或 stevearc/oil.nvim")
        self.source_edit.setMinimumWidth(200)
        self.source_edit.textChanged.connect(self._on_changed)
        self.source_edit.returnPressed.connect(self.save)
        row1.addWidget(self.source_edit, 2)

        mgr_label = QLabel("管理器:")
        mgr_label.setObjectName("keymapFieldLabel")
        mgr_label.setFixedWidth(50)
        row1.addWidget(mgr_label)

        self.mgr_combo = QComboBox()
        for code, label in [
            ("lazy", "lazy.nvim"),
            ("packer", "packer.nvim"),
            ("plug", "vim-plug"),
        ]:
            self.mgr_combo.addItem(label, code)
        self.mgr_combo.setMinimumWidth(115)
        self.mgr_combo.currentIndexChanged.connect(self._on_changed)
        row1.addWidget(self.mgr_combo)

        enabled_label = QLabel("立即启用:")
        enabled_label.setObjectName("keymapFieldLabel")
        row1.addWidget(enabled_label)

        self.enabled_switch = SwitchWidget(checked=True)
        row1.addWidget(self.enabled_switch)

        layout.addLayout(row1)

        # FE-P2-02: 2-column responsive grid layout for secondary plugin attributes
        self.options_grid = QGridLayout()
        self.options_grid.setHorizontalSpacing(10)
        self.options_grid.setVerticalSpacing(8)
        self.options_grid.setColumnStretch(1, 1)
        self.options_grid.setColumnStretch(3, 1)

        event_label = QLabel("加载事件:")
        event_label.setObjectName("keymapFieldLabel")
        event_label.setFixedWidth(72)
        self.options_grid.addWidget(event_label, 0, 0)

        self.event_edit = QLineEdit()
        self.event_edit.setPlaceholderText("可选: VeryLazy / BufReadPre")
        self.event_edit.textChanged.connect(self._on_changed)
        self.event_edit.returnPressed.connect(self.save)
        self.options_grid.addWidget(self.event_edit, 0, 1)

        cmd_label = QLabel("命令触发:")
        cmd_label.setObjectName("keymapFieldLabel")
        cmd_label.setFixedWidth(72)
        self.options_grid.addWidget(cmd_label, 0, 2)

        self.cmd_edit = QLineEdit()
        self.cmd_edit.setPlaceholderText("可选: Telescope / Oil")
        self.cmd_edit.textChanged.connect(self._on_changed)
        self.cmd_edit.returnPressed.connect(self.save)
        self.options_grid.addWidget(self.cmd_edit, 0, 3)

        ft_label = QLabel("文件类型:")
        ft_label.setObjectName("keymapFieldLabel")
        ft_label.setFixedWidth(72)
        self.options_grid.addWidget(ft_label, 1, 0)

        self.ft_edit = QLineEdit()
        self.ft_edit.setPlaceholderText("可选: markdown / rust")
        self.ft_edit.textChanged.connect(self._on_changed)
        self.ft_edit.returnPressed.connect(self.save)
        self.options_grid.addWidget(self.ft_edit, 1, 1)

        build_label = QLabel("构建命令:")
        build_label.setObjectName("keymapFieldLabel")
        build_label.setFixedWidth(72)
        self.options_grid.addWidget(build_label, 1, 2)

        self.build_edit = QLineEdit()
        self.build_edit.setPlaceholderText("可选 (build/run/do): :TSUpdate")
        self.build_edit.textChanged.connect(self._on_changed)
        self.build_edit.returnPressed.connect(self.save)
        self.options_grid.addWidget(self.build_edit, 1, 3)

        branch_label = QLabel("Git 分支:")
        branch_label.setObjectName("keymapFieldLabel")
        branch_label.setFixedWidth(72)
        self.options_grid.addWidget(branch_label, 2, 0)

        self.branch_edit = QLineEdit()
        self.branch_edit.setPlaceholderText("可选分支 (branch): main / master")
        self.branch_edit.textChanged.connect(self._on_changed)
        self.branch_edit.returnPressed.connect(self.save)
        self.options_grid.addWidget(self.branch_edit, 2, 1)

        tag_label = QLabel("Git 标签:")
        tag_label.setObjectName("keymapFieldLabel")
        tag_label.setFixedWidth(72)
        self.options_grid.addWidget(tag_label, 2, 2)

        self.tag_edit = QLineEdit()
        self.tag_edit.setPlaceholderText("可选标签 (tag): v1.0.0 / *")
        self.tag_edit.textChanged.connect(self._on_changed)
        self.tag_edit.returnPressed.connect(self.save)
        self.options_grid.addWidget(self.tag_edit, 2, 3)

        layout.addLayout(self.options_grid)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 4, 0, 0)
        footer.setSpacing(10)

        self.status_label = QLabel("填写 GitHub 插件仓库名（如 owner/repo）后点击“添加插件”")
        self.status_label.setObjectName("keymapStatusLabel")
        self.status_label.setProperty("status", "muted")
        self.status_label.setWordWrap(True)
        footer.addWidget(self.status_label, 1)

        self.cancel_button = QPushButton("取消")
        self.cancel_button.setMinimumWidth(68)
        self.cancel_button.setFixedHeight(28)
        self.cancel_button.clicked.connect(self._on_cancel)
        footer.addWidget(self.cancel_button)

        self.save_button = QPushButton("添加插件")
        self.save_button.setObjectName("accentButton")
        self.save_button.setMinimumWidth(96)
        self.save_button.setFixedHeight(28)
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save)
        footer.addWidget(self.save_button)

        layout.addLayout(footer)

    def focus_first_input(self):
        self.source_edit.setFocus()
        self.source_edit.selectAll()

    def reset_form(self):
        self.saving = False
        self.dirty = False
        for edit in (
            self.source_edit,
            self.event_edit,
            self.cmd_edit,
            self.ft_edit,
            self.branch_edit,
            self.tag_edit,
            self.build_edit,
        ):
            edit.blockSignals(True)
            edit.clear()
            edit.blockSignals(False)
        self.mgr_combo.setCurrentIndex(0)
        self.enabled_switch.setChecked(True)
        self._on_changed()

    def _on_cancel(self):
        self.reset_form()
        self.cancelled.emit()

    def _on_changed(self):
        source = self.source_edit.text().strip()
        mgr = self.mgr_combo.currentData() or "lazy"
        mgr_names = {"lazy": "lazy.nvim", "packer": "packer.nvim", "plug": "vim-plug"}
        target_hints = {
            "lazy": "自动写入 lua/plugins/<name>.lua",
            "packer": "自动写入 packer.startup 配置块",
            "plug": "自动写入 plug#begin..plug#end 块",
        }
        self.mgr_badge.setText(f" {mgr_names.get(mgr, mgr)} ")
        self.mgr_badge.setProperty("manager", mgr)
        self.mgr_badge.style().unpolish(self.mgr_badge)
        self.mgr_badge.style().polish(self.mgr_badge)
        self.target_hint.setText(target_hints.get(mgr, ""))
        self.repo_preview.setText(source or "<未指定仓库>")

        valid = bool(source)
        self.dirty = bool(
            source
            or self.event_edit.text().strip()
            or self.cmd_edit.text().strip()
            or self.ft_edit.text().strip()
            or self.branch_edit.text().strip()
            or self.tag_edit.text().strip()
            or self.build_edit.text().strip()
        )
        self.save_button.setEnabled(valid and not self.saving)
        if not self.saving:
            if valid:
                set_status_label(
                    self.status_label,
                    f"准备就绪，将以 {mgr_names.get(mgr, mgr)} 格式写入配置",
                    "info",
                )
            else:
                set_status_label(
                    self.status_label,
                    "填写 GitHub 插件仓库名（如 owner/repo）后点击“添加插件”",
                    "muted",
                )

    def save(self):
        source = self.source_edit.text().strip()
        if not source or self.saving:
            return
        mgr = self.mgr_combo.currentData() or "lazy"
        payload = {
            "source": source,
            "manager": mgr,
            "enabled": bool(self.enabled_switch.isChecked()),
        }
        event_text = self.event_edit.text().strip()
        if event_text:
            payload["event"] = python_to_lua(event_text)
        cmd_text = self.cmd_edit.text().strip()
        if cmd_text:
            payload["cmd"] = python_to_lua(cmd_text)
        ft_text = self.ft_edit.text().strip()
        if ft_text:
            payload["ft"] = python_to_lua(ft_text)
        branch_text = self.branch_edit.text().strip()
        if branch_text:
            payload["branch"] = branch_text
        tag_text = self.tag_edit.text().strip()
        if tag_text:
            payload["tag"] = tag_text
        build_text = self.build_edit.text().strip()
        if build_text:
            payload["build"] = build_text

        self.saving = True
        self.save_button.setEnabled(False)
        self.title = f"插件 {source}"
        set_status_label(self.status_label, "正在添加插件…", "info")
        self.create_requested.emit(payload, self)

    def save_succeeded(self, feedback="已保存并生效"):
        self.saving = False
        self.dirty = False
        self.reset_form()
        set_status_label(self.status_label, feedback, "saved")
        self.cancelled.emit()

    def save_failed(self, feedback="添加失败"):
        self.saving = False
        self.save_button.setEnabled(bool(self.source_edit.text().strip()))
        set_status_label(self.status_label, feedback, "error")

    def discard_changes(self):
        self.reset_form()

    def is_editing(self):
        focused = QApplication.focusWidget()
        return self.dirty or self.saving or (focused is not None and self.isAncestorOf(focused))


# ===========================================================================
# Milestone 3 Feedback Components & Multi-Manager PluginCard
# ===========================================================================

class NotificationBanner(QFrame):
    """Floating notification toast banner with level styling, auto-dismiss,
    message queue, and action button for conflict recovery / retry."""
    action_clicked = pyqtSignal()
    dismissed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("notificationBanner")
        self.setProperty("level", "info")
        self._action_callback = None
        self._queue = []
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)
        self._remaining_time = 0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(10)

        self.icon_label = QLabel("")
        self.icon_label.setObjectName("notificationIcon")
        self.icon_label.setPixmap(get_md3_pixmap("info", get_current_palette().get("blue", "#7aa2f7"), 18))
        layout.addWidget(self.icon_label)

        self.message_label = QLabel("")
        self.message_label.setObjectName("notificationMessage")
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label, 1)

        self.action_btn = QPushButton("")
        self.action_btn.setObjectName("accentButton")
        self.action_btn.setFixedHeight(26)
        self.action_btn.setVisible(False)
        self.action_btn.clicked.connect(self._on_action_clicked)
        layout.addWidget(self.action_btn)

        self.close_btn = QToolButton()
        self.close_btn.setText("")
        self.close_btn.setIcon(get_md3_icon("close", get_current_palette().get("fg_sub", "#a9b1d6"), 14))
        self.close_btn.setIconSize(QSize(14, 14))
        self.close_btn.setObjectName("actionButton")
        self.close_btn.setFixedSize(22, 22)
        self.close_btn.setToolTip("关闭通知 (Esc)")
        self.close_btn.clicked.connect(self.dismiss)
        layout.addWidget(self.close_btn)

        self.hide()

    def queue_size(self):
        return len(self._queue)

    def enqueue_message(
        self,
        text,
        level="info",
        duration_ms=4000,
        action_text=None,
        on_action=None,
    ):
        self.show_message(
            text,
            level=level,
            duration_ms=duration_ms,
            action_text=action_text,
            on_action=on_action,
            enqueue=True,
        )

    def show_message(
        self,
        text,
        level="info",
        duration_ms=4000,
        action_text=None,
        on_action=None,
        enqueue=False,
    ):
        current_level = self.property("level")
        has_active_high_priority = (
            self.isVisible()
            and self._action_callback is not None
            and current_level in ("warning", "error")
            and level in ("info", "success")
        )
        if self.isVisible() and (enqueue or has_active_high_priority):
            self._queue.append((text, level, duration_ms, action_text, on_action))
            return
        self._display_message(text, level, duration_ms, action_text, on_action)

    def _display_message(
        self,
        text,
        level="info",
        duration_ms=4000,
        action_text=None,
        on_action=None,
    ):
        self.setProperty("level", level)
        self.style().unpolish(self)
        self.style().polish(self)

        self.icon_label.setProperty("level", level)
        self.icon_label.style().unpolish(self.icon_label)
        self.icon_label.style().polish(self.icon_label)

        p = get_current_palette()
        level_colors = {
            "success": p.get("green", "#9ece6a"),
            "info": p.get("blue", "#7aa2f7"),
            "warning": p.get("yellow", "#e0af68"),
            "error": p.get("red", "#f7768e"),
        }
        self.icon_label.setPixmap(get_md3_pixmap(level if level in level_colors else "info", level_colors.get(level, p.get("blue", "#7aa2f7")), 18))
        self.message_label.setText(text)

        self._action_callback = on_action
        if action_text and on_action:
            self.action_btn.setText(action_text)
            self.action_btn.setVisible(True)
        else:
            self.action_btn.setVisible(False)

        self.reposition()
        self.show()
        self.raise_()

        self._timer.stop()
        if duration_ms > 0:
            self._remaining_time = duration_ms
            self._timer.start(duration_ms)
        else:
            self._remaining_time = 0

    def reposition(self):
        if not self.parent():
            return
        parent_w = self.parent().width()
        banner_w = min(parent_w - 40, 620) if parent_w <= 660 else min(620, max(380, self.sizeHint().width()))
        banner_w = max(280, banner_w)
        self.setFixedWidth(banner_w)
        self.adjustSize()
        x = max(10, (parent_w - self.width()) // 2)
        # FE-P1-04: Offset below top bar (y=56) so search bar and controls are never obscured
        self.move(x, 56)
        self.raise_()

    def dismiss(self):
        self._timer.stop()
        self._action_callback = None
        if self._queue:
            next_msg = self._queue.pop(0)
            self._display_message(*next_msg)
            return
        self.hide()
        self.dismissed.emit()

    def _on_action_clicked(self):
        cb = self._action_callback
        self.dismiss()
        self.action_clicked.emit()
        if cb and callable(cb):
            cb()

    def enterEvent(self, event):
        super().enterEvent(event)
        if self._timer.isActive():
            self._remaining_time = self._timer.remainingTime()
            self._timer.stop()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        if self._remaining_time > 0:
            self._timer.start(self._remaining_time)


class OfflineHeroCard(QFrame):
    """Offline Hero Card displayed in central panel when daemon is unreachable
    on launch or network connection drops."""
    retry_requested = pyqtSignal()

    def __init__(self, base_url="http://127.0.0.1:37777", on_retry=None, parent=None):
        super().__init__(parent)
        self.setObjectName("offlineHeroCard")
        self.base_url = base_url
        self._on_retry = on_retry
        self._countdown = 0
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)

        main_layout = QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.setContentsMargins(24, 32, 24, 32)

        card = QFrame()
        card.setObjectName("heroCardInner")
        card.setMaximumWidth(540)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(32, 28, 32, 28)
        card_layout.setSpacing(14)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.icon_label = QLabel("")
        self.icon_label.setObjectName("heroIconLabel")
        self.icon_label.setPixmap(get_md3_pixmap("offline", get_current_palette().get("yellow", "#e0af68"), 42))
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.icon_label)

        self.title_label = QLabel("无法连接 Neovim 配置服务")
        self.title_label.setObjectName("heroTitleLabel")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.title_label)

        self.subtitle_label = QLabel("请确认 Neovim 是否已启动且后台配置服务正在运行。")
        self.subtitle_label.setObjectName("heroSubtitleLabel")
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.subtitle_label)

        self.diag_box = QFrame()
        self.diag_box.setObjectName("heroDiagBox")
        diag_layout = QVBoxLayout(self.diag_box)
        diag_layout.setContentsMargins(10, 8, 10, 8)
        diag_layout.setSpacing(4)

        self.url_label = QLabel(f"服务地址: {self.base_url}")
        self.url_label.setObjectName("heroUrlLabel")
        diag_layout.addWidget(self.url_label)

        self.error_label = QLabel("状态: 正在等待连接…")
        self.error_label.setObjectName("heroErrorLabel")
        self.error_label.setWordWrap(True)
        diag_layout.addWidget(self.error_label)

        self.tip_label = QLabel("提示: 在 Neovim 中执行 :UcdpStart 启动服务，或确认 ucdp-daemon 进程正在运行。")
        self.tip_label.setObjectName("heroTipLabel")
        self.tip_label.setWordWrap(True)
        diag_layout.addWidget(self.tip_label)

        card_layout.addWidget(self.diag_box)

        self.retry_btn = QPushButton("重新连接 (Ctrl+R)")
        self.retry_btn.setObjectName("accentButton")
        self.retry_btn.setMinimumWidth(160)
        self.retry_btn.setFixedHeight(34)
        self.retry_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.retry_btn.clicked.connect(self._trigger_retry)
        card_layout.addWidget(self.retry_btn, 0, Qt.AlignmentFlag.AlignCenter)

        self.countdown_label = QLabel("")
        self.countdown_label.setObjectName("heroCountdownLabel")
        self.countdown_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.countdown_label)

        main_layout.addWidget(card)

    def set_error(self, message):
        self.error_label.setText(f"状态: {message}")

    def start_countdown(self, seconds=5):
        self._countdown = seconds
        self.countdown_label.setText(f"{self._countdown} 秒后自动尝试重新连接…")
        self._timer.start()

    def stop_countdown(self):
        self._timer.stop()
        self.countdown_label.setText("")

    def _tick(self):
        self._countdown -= 1
        if self._countdown <= 0:
            self._timer.stop()
            self.countdown_label.setText("正在重新连接…")
            self._trigger_retry()
        else:
            self.countdown_label.setText(f"{self._countdown} 秒后自动尝试重新连接…")

    def _trigger_retry(self):
        self.stop_countdown()
        self.retry_requested.emit()
        if self._on_retry and callable(self._on_retry):
            self._on_retry()


class EmptySearchPlaceholder(QFrame):
    """Placeholder displayed inside an EntityPage when active search query
    yields 0 matching configuration or plugin cards."""
    clear_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("emptySearchPlaceholder")
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(16, 36, 16, 36)
        layout.setSpacing(10)

        self.icon_label = QLabel("")
        self.icon_label.setObjectName("emptySearchIcon")
        self.icon_label.setPixmap(get_md3_pixmap("search", get_current_palette().get("fg_gutter", "#565f89"), 34))
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.icon_label)

        self.title_label = QLabel("未找到匹配的设置项")
        self.title_label.setObjectName("emptySearchTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_label)

        self.query_label = QLabel("")
        self.query_label.setObjectName("emptySearchQuery")
        self.query_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.query_label)

        self.clear_btn = QPushButton("清除搜索 (Esc)")
        self.clear_btn.setObjectName("accentButton")
        self.clear_btn.setMinimumWidth(130)
        self.clear_btn.setFixedHeight(28)
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_btn.clicked.connect(self.clear_requested.emit)
        layout.addWidget(self.clear_btn, 0, Qt.AlignmentFlag.AlignCenter)

    def set_query(self, query):
        self.query_label.setText(f"没有找到与 “{query}” 相关的选项、快捷键或插件")


class PluginCard(QFrame):
    """
    Master-list Plugin Card Component for Milestone 3 Master-Detail Split View.
    - Compact, scannable master summary card (no visible inline accordion expansion)
    - Clickable selection state (`selected="true"`) synced with right-hand `PluginDetailPanel`
    - Colored manager pill badge (lazy: purple, packer: cyan, vim-plug: teal)
    - Primary metadata chip + external repository navigation button + quick enabled switch
    - Retains hidden `self.advanced` section for backward-compatible programmatic test access
    """
    delete_requested = pyqtSignal(object, object)  # (field, card)
    selected_requested = pyqtSignal(object)  # (card)
    slot_order = [
        ("lazy", "懒加载模式 (lazy)", False, False, "是否在触发条件满足时才按需延迟加载此插件。"),
        ("event", "何时加载 (event)", "", True, "指定 Neovim 自动命令事件触发加载，例如 BufReadPost, VeryLazy。"),
        ("cmd", "命令触发 (cmd)", [], True, "输入指定 Ex 命令时加载插件，例如 Telescope 或 TSUpdate。"),
        ("ft", "文件类型触发 (ft)", [], True, "打开特定类型文件时加载插件，例如 rust, python。"),
        ("keys", "插件按键 (keys)", [], True, "触发插件加载的按键映射规格。"),
        ("dependencies", "依赖插件 (dependencies)", [], True, "此插件运行所依赖的前置插件列表。"),
        ("branch", "Git 分支 (branch)", "", False, "指定锁定的 Git 分支名称。"),
        ("tag", "Git 标签 (tag)", "", False, "指定锁定的 Git Tag 标签版本。"),
        ("commit", "Git 提交 (commit)", "", False, "指定锁定的 Git Commit SHA。"),
        ("version", "版本范围 (version)", "", False, "Semver 语义化版本约束，例如 ^1.0.0。"),
        ("pin", "锁定更新 (pin)", False, False, "是否锁定该插件，在批量更新插件时跳过。"),
        ("build", "构建命令 (build)", "", False, "安装或更新插件后执行的构建脚本或命令，例如 :TSUpdate。"),
        ("opts", "插件参数 (opts)", {}, True, "传递给插件 setup() 的结构化配置字典。"),
        ("config", "配置代码 (config)", "", True, "插件加载后执行的自定义 Lua 配置脚本 (只读)。"),
    ]

    def __init__(self, plugin_data, editor_factory=None, parent=None):
        super().__init__(parent)
        self.setObjectName("groupCard")
        self.setProperty("selected", "false")
        self._selected = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if editor_factory is None:
            self.editor_factory = lambda title, field, **kwargs: FieldEditor(title, field, **kwargs)
        else:
            self.editor_factory = editor_factory
        self.plugin_data = copy.deepcopy(plugin_data)
        self.name = str(self.plugin_data.get("name") or "未命名插件")
        self.source = str(self.plugin_data.get("source") or "")

        # Canonical manager
        raw_mgr = str(self.plugin_data.get("manager") or "lazy").lower().replace("_", "-")
        if "packer" in raw_mgr:
            self.manager = "packer"
        elif "plug" in raw_mgr:
            self.manager = "plug"
        else:
            self.manager = "lazy"

        self.search_text = self._build_search_text()
        self._build_ui()

    def _build_search_text(self):
        mgr_names = {"lazy": "lazy.nvim lazy", "packer": "packer.nvim packer", "plug": "vim-plug plug"}
        tokens = [self.name, self.source, mgr_names.get(self.manager, self.manager)]
        for slot in ("branch", "tag", "commit", "version", "build"):
            val = get_field_display_val(self.plugin_data.get(slot))
            if val:
                tokens.append(str(val))
        for slot in ("cmd", "ft", "event", "dependencies"):
            val = lua_to_python(field_value(self.plugin_data.get(slot)))
            if isinstance(val, list):
                tokens.extend(str(x) for x in val if x)
            elif val:
                tokens.append(str(val))
        return " ".join(tokens)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(9)

        # 1. Header Row
        header = QHBoxLayout()
        header.setSpacing(6)

        # Title
        self.title_label = QLabel(self.name)
        self.title_label.setObjectName("groupTitle")
        header.addWidget(self.title_label)

        # Manager Badge
        mgr_badge_names = {
            "lazy": ("lazy.nvim", "managerBadgeLazy"),
            "packer": ("packer.nvim", "managerBadgePacker"),
            "plug": ("vim-plug", "managerBadgePlug"),
        }
        mgr_label, badge_id = mgr_badge_names.get(self.manager, ("lazy.nvim", "managerBadgeLazy"))
        self.badge_label = QLabel(f" {mgr_label} ")
        self.badge_label.setObjectName(badge_id)
        header.addWidget(self.badge_label)

        # Compact Chips Container (at most 1 summary chip on master card to avoid crowding)
        self.chips_layout = QHBoxLayout()
        self.chips_layout.setSpacing(4)
        self._populate_chips()
        header.addLayout(self.chips_layout)

        header.addStretch(1)

        # Open Repo Icon Pill
        p = get_current_palette()
        self.repo_url, tooltip = parse_plugin_repo_url(self.source)
        self.repo_btn = QPushButton("")
        self.repo_btn.setIcon(get_md3_icon("external", p.get("cyan", "#7dcfff"), 14))
        self.repo_btn.setIconSize(QSize(14, 14))
        self.repo_btn.setObjectName("openRepoButton")
        self.repo_btn.setFixedWidth(34)
        self.repo_btn.setFixedHeight(24)
        self.repo_btn.setToolTip(tooltip)
        self.repo_btn.setEnabled(bool(self.repo_url))
        self.repo_btn.setCursor(Qt.CursorShape.PointingHandCursor if self.repo_url else Qt.CursorShape.ArrowCursor)
        self.repo_btn.clicked.connect(self._open_repo)
        header.addWidget(self.repo_btn)

        # Delete Plugin Icon Pill
        self.delete_button = QPushButton("")
        self.delete_button.setIcon(get_md3_icon("delete", p.get("red", "#f7768e"), 14))
        self.delete_button.setIconSize(QSize(14, 14))
        self.delete_button.setObjectName("dangerButton")
        self.delete_button.setFixedWidth(34)
        self.delete_button.setFixedHeight(24)
        self.delete_button.setToolTip(f"从配置文件中删除插件 {self.name}")
        self.delete_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_button.clicked.connect(self._on_delete_clicked)
        header.addWidget(self.delete_button)

        layout.addLayout(header)

        # 2. Subtitle: Source & Single-Line Location
        sub_row = QHBoxLayout()
        sub_row.setSpacing(8)
        source_text = f"{self.source}" if self.source else "本地插件"
        self.source_label = QLabel(source_text)
        self.source_label.setObjectName("settingDescription")
        self.source_label.setWordWrap(True)
        sub_row.addWidget(self.source_label)
        sub_row.addStretch(1)

        loc = self._extract_location()
        self.loc_label = QLabel(loc)
        self.loc_label.setObjectName("technicalName")
        self.loc_label.setWordWrap(True)
        self.loc_label.setVisible(bool(loc))
        sub_row.addWidget(self.loc_label)

        self.inspect_hint_label = QLabel("")
        self.inspect_hint_label.setObjectName("inspectHintBadge")
        self.inspect_hint_label.setProperty("selected", "false")
        self.inspect_hint_label.setWordWrap(True)
        self.inspect_hint_label.setVisible(False)
        sub_row.addWidget(self.inspect_hint_label)
        layout.addLayout(sub_row)

        # 3. Quick Enabled Switch (flat inline M3 row without nested dark box)
        enabled_field = self.plugin_data.get("enabled")
        self.enabled_editor = self.editor_factory(
            "启用插件",
            enabled_field,
            value=field_value(enabled_field),
            default=True,
            schema={"type": "boolean"},
            allow_create=True,
            auto_save=True,
            description="",
            technical_name="enabled",
            compact=True,
            show_location=False,
            show_save_button=False,
        )
        self.enabled_editor.setObjectName("inlineSwitchEditor")
        if self.enabled_editor.layout() is not None:
            self.enabled_editor.layout().setContentsMargins(0, 2, 0, 0)
        self.enabled_editor.edited.connect(lambda: self.selected_requested.emit(self))
        layout.addWidget(self.enabled_editor)

        # 4. Hidden Collapsible Section (kept hidden so master cards never expand inline in UI,
        # while remaining programmatically accessible for legacy unit tests)
        self._advanced_populated = False
        self.advanced = CollapsibleSection("加载方式、按键与插件参数")
        self.advanced.toggle.setVisible(False)
        self.advanced.toggle.toggled.connect(self._on_advanced_toggled)
        layout.addWidget(self.advanced)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.selected_requested.emit(self)

    def set_selected(self, selected: bool):
        new_sel = bool(selected)
        if getattr(self, "_selected", None) == new_sel:
            return
        self._selected = new_sel
        val = "true" if self._selected else "false"
        self.setProperty("selected", val)
        self.style().unpolish(self)
        self.style().polish(self)
        if hasattr(self, "inspect_hint_label"):
            self.inspect_hint_label.setProperty("selected", val)
            self.inspect_hint_label.setText("编辑中" if self._selected else "")
            self.inspect_hint_label.setVisible(self._selected)
            self.inspect_hint_label.style().unpolish(self.inspect_hint_label)
            self.inspect_hint_label.style().polish(self.inspect_hint_label)

    def is_selected(self) -> bool:
        return self._selected

    def _extract_location(self):
        file_path = self.plugin_data.get("file")
        if file_path:
            short = format_display_path(file_path)
            line = self.plugin_data.get("line")
            return f"{short}:{line}" if line is not None else str(short)
        for slot in ("enabled", "opts", "keys", "event", "branch", "tag"):
            f = self.plugin_data.get(slot)
            if isinstance(f, dict) and f.get("file"):
                short = format_display_path(f["file"])
                line = f.get("line")
                return f"{short}:{line}" if line is not None else str(short)
        return ""

    def _populate_chips(self):
        pin_val = lua_to_python(field_value(self.plugin_data.get("pin")))
        lazy_val = lua_to_python(field_value(self.plugin_data.get("lazy")))
        tag_val = get_field_display_val(self.plugin_data.get("tag"))
        branch_val = get_field_display_val(self.plugin_data.get("branch"))

        spec = None
        if pin_val is True:
            spec = (" 锁定 ", "attributeChipWarn")
        elif lazy_val is True:
            spec = (" 懒加载 ", "attributeChipAccent")
        elif tag_val:
            short_tag = str(tag_val)[:10]
            spec = (f" {short_tag} ", "attributeChip")
        elif branch_val:
            short_branch = str(branch_val)[:10]
            spec = (f" {short_branch} ", "attributeChip")
        elif lazy_val is False and self.manager == "lazy":
            spec = (" 启动 ", "attributeChip")

        if getattr(self, "_last_chip_spec", False) == spec:
            return
        self._last_chip_spec = spec

        while self.chips_layout.count():
            item = self.chips_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

        if spec is not None:
            chip = QLabel(spec[0])
            chip.setObjectName(spec[1])
            self.chips_layout.addWidget(chip)

    def _on_advanced_toggled(self, expanded):
        if expanded and not self._advanced_populated:
            self._populate_advanced_editors()

    def _populate_advanced_editors(self):
        if self._advanced_populated:
            return
        self._advanced_populated = True
        for slot, title, default, is_structured, desc in self.slot_order:
            field = self.plugin_data.get(slot)
            if slot in ("event", "keys", "opts") or field is not None:
                val = field_value(field, default)
                read_only = (slot == "config")
                editor = self.editor_factory(
                    title,
                    field,
                    value=val,
                    default=default,
                    structured=is_structured,
                    technical_name=slot,
                    description=desc,
                    read_only=read_only,
                )
                self.advanced.add_widget(editor)

    def _open_repo(self):
        if self.repo_url:
            QDesktopServices.openUrl(QUrl(self.repo_url))

    def _on_delete_clicked(self):
        target_field = self.plugin_data.get("enabled")
        if not isinstance(target_field, dict) or not target_field.get("id"):
            return
        if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
            reply = QMessageBox.question(
                self,
                "确认删除插件",
                f"确定要从配置文件中删除插件 “{self.name}” ({self.source}) 吗？\n（系统将自动创建配置备份快照）",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self.delete_requested.emit(target_field, self)

    def save(self):
        for editor in self.findChildren(FieldEditor):
            if editor.dirty and not editor.saving:
                editor.save()

    def discard_changes(self):
        for editor in self.findChildren(FieldEditor):
            if editor.dirty:
                editor.discard_changes()

    def is_editing(self):
        focused = QApplication.focusWidget()
        if focused is not None and self.isAncestorOf(focused):
            return True
        return any(w.is_editing() for w in self.findChildren(QWidget) if hasattr(w, "is_editing"))

    def update_data(self, new_plugin_data):
        self.plugin_data = copy.deepcopy(new_plugin_data)
        self.name = str(self.plugin_data.get("name") or "未命名插件")
        self.source = str(self.plugin_data.get("source") or "")
        self.search_text = self._build_search_text()

        raw_mgr = str(self.plugin_data.get("manager") or "lazy").lower().replace("_", "-")
        self.manager = "packer" if "packer" in raw_mgr else ("plug" if "plug" in raw_mgr else "lazy")

        mgr_badge_names = {
            "lazy": ("lazy.nvim", "managerBadgeLazy"),
            "packer": ("packer.nvim", "managerBadgePacker"),
            "plug": ("vim-plug", "managerBadgePlug"),
        }
        mgr_label, badge_id = mgr_badge_names.get(self.manager, ("lazy.nvim", "managerBadgeLazy"))
        self.badge_label.setText(f" {mgr_label} ")
        self.badge_label.setObjectName(badge_id)
        self.badge_label.style().unpolish(self.badge_label)
        self.badge_label.style().polish(self.badge_label)

        self._populate_chips()
        self.repo_url, tooltip = parse_plugin_repo_url(self.source)
        self.repo_btn.setToolTip(tooltip)
        self.repo_btn.setEnabled(bool(self.repo_url))
        self.repo_btn.setCursor(Qt.CursorShape.PointingHandCursor if self.repo_url else Qt.CursorShape.ArrowCursor)

        source_text = f"源: {self.source}" if self.source else "本地插件"
        self.source_label.setText(source_text)
        loc = self._extract_location()
        if hasattr(self, "loc_label"):
            self.loc_label.setText(loc)
            self.loc_label.setVisible(bool(loc))

        # Update primary enabled switch editor if present
        enabled_field = self.plugin_data.get("enabled")
        if hasattr(self, "enabled_editor"):
            self.enabled_editor.update_field(enabled_field)
            if not self.enabled_editor.is_editing():
                val = field_value(enabled_field, True)
                py_val = lua_to_python(val)
                if hasattr(self.enabled_editor, "editor") and self.enabled_editor.editor is not None:
                    ctrl = self.enabled_editor.editor
                    ctrl.blockSignals(True)
                    try:
                        if hasattr(ctrl, "setChecked"):
                            ctrl.setChecked(bool(py_val))
                    finally:
                        ctrl.blockSignals(False)

        # Check for newly added extended slots if advanced section is already populated
        if self._advanced_populated:
            existing_slots = {e.technical_name for e in self.advanced.findChildren(FieldEditor) if hasattr(e, "technical_name") and e.technical_name}
            for slot, title, default, is_structured, desc in self.slot_order:
                field = self.plugin_data.get(slot)
                if slot not in existing_slots and (slot in ("event", "keys", "opts") or field is not None):
                    val = field_value(field, default)
                    read_only = (slot == "config")
                    editor = self.editor_factory(
                        title,
                        field,
                        value=val,
                        default=default,
                        structured=is_structured,
                        technical_name=slot,
                        description=desc,
                        read_only=read_only,
                    )
                    self.advanced.add_widget(editor)


class PluginDetailPanel(QFrame):
    """
    Right-hand Master-Detail Inspector Column for PluginPage ("右侧新增一栏").
    Displays full configuration, categorized property editors, quick actions,
    and a live Lua/Vimscript Spec Code Preview for the currently selected PluginCard.
    """
    delete_requested = pyqtSignal(object, object)  # (field, card)
    batch_save_requested = pyqtSignal(object, object)  # ([(field, new_value), ...], panel)

    SECTIONS = [
        (
            "核心状态与加载策略",
            [
                ("enabled", "启用此插件 (enabled)", True, False, "关闭后，Neovim 启动时将跳过加载该插件。"),
                ("lazy", "懒加载模式 (lazy)", False, False, "是否在满足事件、命令或按键触发条件时才延迟加载。"),
                ("pin", "锁定版本更新 (pin)", False, False, "开启后，在执行插件管理器批量更新时跳过此插件。"),
            ],
        ),
        (
            "依赖项与模块参数 (Setup & Spec)",
            [
                ("opts", "传递给 setup(opts) 的参数表", {}, True, "传递给 require(plugin).setup(opts) 的结构化配置表。"),
                ("dependencies", "依赖插件列表 (dependencies)", [], True, "该插件运行所需的前置依赖插件仓库列表。"),
                ("config", "自定义配置脚本 (config)", "", True, "插件加载后执行的自定义 Lua 函数或脚本（只读展示）。"),
            ],
        ),
        (
            "按需触发条件 (Triggers)",
            [
                ("event", "事件触发 (event)", [], True, "指定触发插件加载的自动命令事件，如 VeryLazy、BufReadPost。"),
                ("cmd", "命令触发 (cmd)", [], True, "输入指定 Ex 命令时按需加载插件，如 Telescope、Oil。"),
                ("ft", "文件类型触发 (ft)", [], True, "打开特定语言文件时加载插件，如 lua、rust、python。"),
                ("keys", "按键映射触发 (keys)", [], True, "按下特定快捷键时按需加载插件。"),
            ],
        ),
        (
            "版本控制与构建 (Git & Build)",
            [
                ("branch", "Git 分支 (branch)", "", False, "指定检出的 Git 分支名称（如 main 或 master）。"),
                ("tag", "Git 标签 (tag)", "", False, "指定锁定的 Git Release 标签版本（如 v1.2.0）。"),
                ("commit", "Git 提交 (commit)", "", False, "指定锁定的 Git Commit SHA 哈希值。"),
                ("version", "语义版本约束 (version)", "", False, "指定 Semver 版本范围（如 ^1.0.0 或 *）。"),
                ("build", "构建命令 (build)", "", False, "安装或更新后执行的构建命令（如 :TSUpdate 或 make）。"),
            ],
        ),
    ]

    def __init__(self, editor_factory=None, parent=None):
        super().__init__(parent)
        self.setObjectName("pluginDetailPanel")
        if editor_factory is None:
            self.editor_factory = lambda title, field, **kwargs: FieldEditor(title, field, **kwargs)
        else:
            self.editor_factory = editor_factory
        self.current_card = None
        self.plugin_data = None
        self.slot_editors = {}
        self._cached_slot_editors = {}
        self._section_layouts = {}
        self._sections_initialized = False
        self.creation = False
        self._build_ui()

    @property
    def title(self) -> str:
        if self.current_card is not None and getattr(self.current_card, "name", None):
            return f"插件 {self.current_card.name}"
        return "插件配置"

    def _build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(12, 10, 12, 10)
        root_layout.setSpacing(10)

        # Empty state placeholder when no plugin is selected
        self.empty_widget = QFrame()
        self.empty_widget.setObjectName("inspectorSectionCard")
        empty_layout = QVBoxLayout(self.empty_widget)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.setContentsMargins(20, 40, 20, 40)
        empty_layout.setSpacing(8)
        empty_icon = QLabel("")
        empty_icon.setObjectName("emptySearchIcon")
        empty_icon.setPixmap(get_md3_pixmap("plugin", get_current_palette().get("fg_gutter", "#565f89"), 36))
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_icon)
        self.empty_title = QLabel("在左侧点击任意插件以查看与编辑详情")
        self.empty_title.setObjectName("emptySearchTitle")
        self.empty_title.setWordWrap(True)
        self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self.empty_title)
        self.empty_desc = QLabel("右侧详情栏提供完整的加载触发器、Git 版本控制、插件参数表与实时配置代码预览。")
        self.empty_desc.setObjectName("settingDescription")
        self.empty_desc.setWordWrap(True)
        self.empty_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self.empty_desc)
        root_layout.addWidget(self.empty_widget, 1)

        # Active detail container
        self.detail_container = QWidget()
        detail_layout = QVBoxLayout(self.detail_container)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(10)

        # 1. Sticky Inspector Header Card
        self.header_card = QFrame()
        self.header_card.setObjectName("pluginDetailHeader")
        header_card_layout = QVBoxLayout(self.header_card)
        header_card_layout.setContentsMargins(14, 12, 14, 12)
        header_card_layout.setSpacing(8)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        self.title_label = QLabel("")
        self.title_label.setObjectName("groupTitle")
        self.title_label.setWordWrap(True)
        top_row.addWidget(self.title_label, 1)

        self.badge_label = QLabel(" lazy.nvim ")
        self.badge_label.setObjectName("managerBadgeLazy")
        top_row.addWidget(self.badge_label)

        p = get_current_palette()
        self.repo_btn = QPushButton("仓库")
        self.repo_btn.setIcon(get_md3_icon("external", p.get("cyan", "#7dcfff"), 14))
        self.repo_btn.setIconSize(QSize(14, 14))
        self.repo_btn.setObjectName("openRepoButton")
        self.repo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.repo_btn.clicked.connect(self._open_repo)
        top_row.addWidget(self.repo_btn)

        self.save_all_btn = QPushButton("保存修改")
        self.save_all_btn.setObjectName("accentButton")
        self.save_all_btn.setProperty("dirty", "false")
        self.save_all_btn.setEnabled(False)
        self.save_all_btn.clicked.connect(self.save_all)
        top_row.addWidget(self.save_all_btn)

        self.delete_btn = QPushButton("")
        self.delete_btn.setIcon(get_md3_icon("delete", p.get("red", "#f7768e"), 16))
        self.delete_btn.setIconSize(QSize(16, 16))
        self.delete_btn.setObjectName("dangerButton")
        self.delete_btn.setFixedWidth(36)
        self.delete_btn.setToolTip("从配置文件中删除此插件")
        self.delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_btn.clicked.connect(self._on_delete_clicked)
        top_row.addWidget(self.delete_btn)
        header_card_layout.addLayout(top_row)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(8)
        self.source_label = QLabel("")
        self.source_label.setObjectName("settingDescription")
        self.source_label.setWordWrap(True)
        self.source_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        meta_row.addWidget(self.source_label)
        meta_row.addStretch(1)

        self.loc_label = QLabel("")
        self.loc_label.setObjectName("technicalName")
        self.loc_label.setWordWrap(True)
        self.loc_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        meta_row.addWidget(self.loc_label)
        header_card_layout.addLayout(meta_row)

        self.chips_layout = QHBoxLayout()
        self.chips_layout.setSpacing(6)
        header_card_layout.addLayout(self.chips_layout)

        detail_layout.addWidget(self.header_card)

        # 2. Structured M3 Secondary Tabs (eliminates vertical wall of 15 stacked cards)
        self.inspector_tabs = QTabWidget()
        self.inspector_tabs.setObjectName("inspectorTabs")
        self._tab_layouts = []
        self._tab_scrolls = []
        for tab_title in ("参数与状态", "按需触发", "版本与构建", "代码预览"):
            sc = QScrollArea()
            sc.setWidgetResizable(True)
            sc.setFrameShape(QFrame.Shape.NoFrame)
            sc.setObjectName("scrollViewport")
            host = QWidget()
            host.setObjectName("cardsContainer")
            lay = QVBoxLayout(host)
            lay.setContentsMargins(0, 8, 4, 8)
            lay.setSpacing(10)
            sc.setWidget(host)
            self.inspector_tabs.addTab(sc, tab_title)
            self._tab_layouts.append(lay)
            self._tab_scrolls.append(sc)

        # Legacy alias for backwards compatibility
        self.scroll_area = self._tab_scrolls[0]
        self.sections_host = self._tab_scrolls[0].widget()
        self.sections_layout = self._tab_layouts[0]
        detail_layout.addWidget(self.inspector_tabs, 1)

        root_layout.addWidget(self.detail_container, 1)
        self.detail_container.setVisible(False)

    def load_plugin(self, card: "PluginCard"):
        if card is None:
            self.clear_selection()
            return
        self.current_card = card
        self.plugin_data = copy.deepcopy(card.plugin_data)
        self.empty_widget.setVisible(False)
        self.detail_container.setVisible(True)

        self._refresh_header()
        self._rebuild_sections()
        self._refresh_spec_preview()
        self._update_save_all_state()
        for sec_lay in self._section_layouts.values():
            sec_lay.invalidate()
            sec_lay.activate()
            if sec_lay.parentWidget() is not None:
                sec_lay.parentWidget().updateGeometry()
        for tab_lay in self._tab_layouts:
            tab_lay.invalidate()
            tab_lay.activate()
            if tab_lay.parentWidget() is not None:
                tab_lay.parentWidget().adjustSize()

    def clear_selection(self):
        self.current_card = None
        self.plugin_data = None
        self.slot_editors.clear()
        self.detail_container.setVisible(False)
        self.empty_widget.setVisible(True)

    def _refresh_header(self):
        if not self.plugin_data or not self.current_card:
            return
        self.title_label.setText(self.current_card.name)
        mgr_badge_names = {
            "lazy": ("lazy.nvim", "managerBadgeLazy"),
            "packer": ("packer.nvim", "managerBadgePacker"),
            "plug": ("vim-plug", "managerBadgePlug"),
        }
        mgr_label, badge_id = mgr_badge_names.get(
            self.current_card.manager, ("lazy.nvim", "managerBadgeLazy")
        )
        self.badge_label.setText(f" {mgr_label} ")
        if self.badge_label.objectName() != badge_id:
            self.badge_label.setObjectName(badge_id)
            self.badge_label.style().unpolish(self.badge_label)
            self.badge_label.style().polish(self.badge_label)

        self.repo_url, tooltip = parse_plugin_repo_url(self.current_card.source)
        self.repo_btn.setToolTip(tooltip)
        self.repo_btn.setEnabled(bool(self.repo_url))

        source_text = f"仓库源: {self.current_card.source}" if self.current_card.source else "本地插件"
        self.source_label.setText(source_text)
        loc = self.current_card._extract_location()
        self.loc_label.setText(loc)
        self.loc_label.setVisible(bool(loc))

        chip_specs = []
        for slot, prefix in (("branch", "branch:"), ("tag", "tag:"), ("commit", "#"), ("version", "v")):
            val = get_field_display_val(self.plugin_data.get(slot))
            if val:
                disp = str(val)[:7] if slot == "commit" else str(val)
                chip_specs.append((f" {prefix} {disp} ", "attributeChip"))

        pin_val = lua_to_python(field_value(self.plugin_data.get("pin")))
        if pin_val is True:
            chip_specs.append((" 已锁定 ", "attributeChipWarn"))

        lazy_val = lua_to_python(field_value(self.plugin_data.get("lazy")))
        if lazy_val is True:
            chip_specs.append((" 按需懒加载 ", "attributeChipAccent"))
        elif lazy_val is False and self.current_card.manager == "lazy":
            chip_specs.append((" 启动立即加载 ", "attributeChip"))

        if getattr(self, "_last_header_chips", None) == chip_specs:
            return
        self._last_header_chips = chip_specs

        while self.chips_layout.count():
            item = self.chips_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

        for text, obj_name in chip_specs:
            chip = QLabel(text)
            chip.setObjectName(obj_name)
            chip.setWordWrap(True)
            self.chips_layout.addWidget(chip)
        self.chips_layout.addStretch(1)

    def _synthesize_slot_field(self, slot: str):
        if not self.plugin_data or not self.current_card:
            return None
        base_field = self.plugin_data.get("enabled") or {}
        if not isinstance(base_field, dict) or not base_field.get("file"):
            return None
        return {
            "id": f"plugin_slot:{self.current_card.name}:{slot}",
            "file": base_field.get("file", ""),
            "revision": base_field.get("revision", ""),
            "line": None,
            "value": None,
        }

    def _ensure_sections_initialized(self):
        if self._sections_initialized:
            return
        self._sections_initialized = True
        section_tab_map = {0: 0, 1: 0, 2: 1, 3: 2}
        for sec_idx, (section_title, _slots) in enumerate(self.SECTIONS):
            sec_card = QFrame()
            sec_card.setObjectName("inspectorSectionCard")
            sec_layout = QVBoxLayout(sec_card)
            sec_layout.setContentsMargins(12, 10, 12, 10)
            sec_layout.setSpacing(8)

            sec_header = QLabel(section_title)
            sec_header.setObjectName("inspectorSectionTitle")
            sec_header.setWordWrap(True)
            sec_layout.addWidget(sec_header)

            target_tab_idx = section_tab_map.get(sec_idx, 0)
            self._tab_layouts[target_tab_idx].addWidget(sec_card)
            self._section_layouts[sec_idx] = sec_layout

        # Tab 3: Live Spec Code Preview Section
        self.spec_preview_card = QFrame()
        self.spec_preview_card.setObjectName("inspectorSectionCard")
        spec_card_layout = QVBoxLayout(self.spec_preview_card)
        spec_card_layout.setContentsMargins(12, 10, 12, 10)
        spec_card_layout.setSpacing(8)

        spec_top = QHBoxLayout()
        spec_title = QLabel("实时配置代码预览 (Spec Preview)")
        spec_title.setObjectName("inspectorSectionTitle")
        spec_title.setWordWrap(True)
        spec_top.addWidget(spec_title, 1)

        self.copy_spec_btn = QPushButton("复制代码")
        self.copy_spec_btn.setObjectName("openRepoButton")
        self.copy_spec_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_spec_btn.clicked.connect(self._copy_spec_code)
        spec_top.addWidget(self.copy_spec_btn)
        spec_card_layout.addLayout(spec_top)

        self.spec_preview_box = QFrame()
        self.spec_preview_box.setObjectName("specPreviewBox")
        box_layout = QVBoxLayout(self.spec_preview_box)
        box_layout.setContentsMargins(10, 8, 10, 8)
        self.spec_preview_label = QLabel("")
        self.spec_preview_label.setObjectName("specPreviewCode")
        self.spec_preview_label.setWordWrap(True)
        self.spec_preview_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        box_layout.addWidget(self.spec_preview_label)
        spec_card_layout.addWidget(self.spec_preview_box)

        self._tab_layouts[3].addWidget(self.spec_preview_card)
        for lay in self._tab_layouts:
            lay.addStretch(1)

    def _rebuild_sections(self):
        self.slot_editors.clear()
        if not self.plugin_data:
            return
        self._ensure_sections_initialized()

        for sec_idx, (_section_title, slots) in enumerate(self.SECTIONS):
            sec_layout = self._section_layouts[sec_idx]
            for slot, title, default, is_structured, desc in slots:
                field = self.plugin_data.get(slot)
                if field is None and slot != "config":
                    field = self._synthesize_slot_field(slot)
                if slot == "config" and field is None:
                    cached_ed = self._cached_slot_editors.get(slot)
                    if cached_ed is not None:
                        cached_ed.setVisible(False)
                    continue

                raw_py = lua_to_python(field.get("value")) if isinstance(field, dict) else None
                if slot in ("event", "cmd", "ft") and isinstance(raw_py, str):
                    slot_structured = False
                    slot_default = ""
                else:
                    slot_structured = is_structured
                    slot_default = copy.deepcopy(default)
                val = field_value(field, slot_default)
                read_only = (slot == "config")
                schema = {"type": "boolean"} if isinstance(slot_default, bool) else {}
                auto_save = isinstance(slot_default, bool)

                cached_ed = self._cached_slot_editors.get(slot)
                if cached_ed is not None and cached_ed.structured == slot_structured and cached_ed.read_only == read_only:
                    cached_ed.bind_slot(
                        field,
                        val,
                        slot_default,
                        allow_create=(slot == "enabled"),
                        auto_save=auto_save,
                    )
                    if cached_ed.isHidden():
                        cached_ed.setVisible(True)
                    self.slot_editors[slot] = cached_ed
                else:
                    if cached_ed is not None:
                        sec_layout.removeWidget(cached_ed)
                        cached_ed.setParent(None)
                        cached_ed.deleteLater()
                    editor = self.editor_factory(
                        title,
                        field,
                        value=val,
                        default=slot_default,
                        schema=schema,
                        allow_create=(slot == "enabled"),
                        auto_save=auto_save,
                        advanced=True,
                        structured=slot_structured,
                        technical_name=slot,
                        description=desc,
                        read_only=read_only,
                        compact=(not slot_structured),
                        show_location=False,
                        show_save_button=False,
                    )
                    editor.edited.connect(self._on_editor_changed)
                    sec_layout.addWidget(editor)
                    self._cached_slot_editors[slot] = editor
                    self.slot_editors[slot] = editor

    def _format_spec_preview(self) -> str:
        if not self.plugin_data or not self.current_card:
            return ""
        src = self.current_card.source or self.current_card.name
        mgr = self.current_card.manager

        def _slot_py(slot_name, fallback=None):
            if slot_name in self.slot_editors:
                return lua_to_python(self.slot_editors[slot_name].value())
            f = self.plugin_data.get(slot_name)
            return lua_to_python(field_value(f, fallback))

        enabled = _slot_py("enabled", True)
        lazy = _slot_py("lazy", None)
        pin = _slot_py("pin", None)
        event = _slot_py("event", None)
        cmd = _slot_py("cmd", None)
        ft = _slot_py("ft", None)
        keys = _slot_py("keys", None)
        branch = _slot_py("branch", None)
        tag = _slot_py("tag", None)
        commit = _slot_py("commit", None)
        version = _slot_py("version", None)
        build = _slot_py("build", None)
        dependencies = _slot_py("dependencies", None)
        opts = _slot_py("opts", None)

        if mgr == "plug":
            opts_parts = []
            if branch:
                opts_parts.append(f"'branch': '{branch}'")
            if tag:
                opts_parts.append(f"'tag': '{tag}'")
            if commit:
                opts_parts.append(f"'commit': '{commit}'")
            if build:
                opts_parts.append(f"'do': '{build}'")
            if ft:
                ft_str = repr(ft)
                opts_parts.append(f"'for': {ft_str}")
            if cmd:
                cmd_str = repr(cmd)
                opts_parts.append(f"'on': {cmd_str}")
            prefix = '" ' if enabled is False else ""
            if opts_parts:
                return f"{prefix}Plug '{src}', {{ {', '.join(opts_parts)} }}"
            return f"{prefix}Plug '{src}'"

        lines = [f'  "{src}",']
        if mgr == "packer":
            if enabled is False:
                lines.append("  disable = true,")
            if lazy is True:
                lines.append("  opt = true,")
            if pin is True:
                lines.append("  lock = true,")
        else:
            if enabled is False:
                lines.append("  enabled = false,")
            if isinstance(lazy, bool):
                lines.append(f"  lazy = {'true' if lazy else 'false'},")
            if pin is True:
                lines.append("  pin = true,")

        for k, v in (
            ("event", event),
            ("cmd", cmd),
            ("ft", ft),
            ("keys", keys),
            ("branch", branch),
            ("tag", tag),
            ("commit", commit),
            ("version", version),
        ):
            if v:
                if isinstance(v, list):
                    items = ", ".join(
                        (x.source if isinstance(x, UnsupportedValue) else f'"{x}"')
                        for x in v
                        if x
                    )
                    if items:
                        lines.append(f"  {k} = {{ {items} }},")
                elif isinstance(v, str) and v.strip():
                    lines.append(f'  {k} = "{v.strip()}",')
        if build and isinstance(build, str) and build.strip():
            key_name = "run" if mgr == "packer" else "build"
            lines.append(f'  {key_name} = "{build.strip()}",')
        if dependencies and isinstance(dependencies, list):
            dep_items = ", ".join(
                (x.source if isinstance(x, UnsupportedValue) else f'"{x}"')
                for x in dependencies
                if x
            )
            if dep_items:
                dep_key = "requires" if mgr == "packer" else "dependencies"
                lines.append(f"  {dep_key} = {{ {dep_items} }},")
        if opts and isinstance(opts, dict) and len(opts) > 0:
            def _fmt_lua(val, indent=2):
                pad = "  " * indent
                if isinstance(val, UnsupportedValue):
                    return val.source.strip()
                if isinstance(val, bool):
                    return "true" if val else "false"
                if isinstance(val, (int, float)):
                    return str(val)
                if isinstance(val, str):
                    escaped = val.replace("\\", "\\\\").replace('"', '\\"')
                    return f'"{escaped}"'
                if isinstance(val, list):
                    if not val:
                        return "{}"
                    if len(val) <= 5 and all(isinstance(x, (str, int, float, bool)) for x in val):
                        return "{ " + ", ".join(_fmt_lua(x, indent) for x in val) + " }"
                    inner = [f"{pad}  {_fmt_lua(x, indent + 1)}," for x in val[:8]]
                    if len(val) > 8:
                        inner.append(f"{pad}  -- ... 共 {len(val)} 项")
                    return "{\n" + "\n".join(inner) + f"\n{pad}}}"
                if isinstance(val, dict):
                    if not val:
                        return "{}"
                    inner = []
                    items_list = list(val.items())
                    for k_sub, v_sub in items_list[:10]:
                        k_str = k_sub if str(k_sub).isidentifier() else f'["{k_sub}"]'
                        inner.append(f"{pad}  {k_str} = {_fmt_lua(v_sub, indent + 1)},")
                    if len(items_list) > 10:
                        inner.append(f"{pad}  -- ... 共 {len(items_list)} 项")
                    return "{\n" + "\n".join(inner) + f"\n{pad}}}"
                return '""'

            lines.append(f"  opts = {_fmt_lua(opts, 1)},")

        wrapper_open = "use({" if mgr == "packer" else "return {"
        wrapper_close = "})" if mgr == "packer" else "}"
        return "\n".join([wrapper_open] + lines + [wrapper_close])

    def _refresh_spec_preview(self):
        if hasattr(self, "spec_preview_label"):
            self.spec_preview_label.setText(self._format_spec_preview())

    def _copy_spec_code(self):
        code = self._format_spec_preview()
        clipboard = QApplication.clipboard()
        if clipboard is not None and code:
            clipboard.setText(code)
            self.copy_spec_btn.setText("已复制")
            QTimer.singleShot(1500, lambda: self.copy_spec_btn.setText("复制代码"))

    def _on_editor_changed(self):
        # Sync enabled switch back to master card if changed in detail panel
        if "enabled" in self.slot_editors and self.current_card is not None:
            en_val = self.slot_editors["enabled"].value()
            master_ed = getattr(self.current_card, "enabled_editor", None)
            if master_ed is not None and master_ed.value() != en_val:
                master_ed.set_editor_value(en_val)
        self._refresh_spec_preview()
        self._update_save_all_state()

    def _update_save_all_state(self):
        any_dirty = any(ed.dirty and not ed.saving for ed in self.slot_editors.values())
        self.save_all_btn.setEnabled(any_dirty)
        dirty_prop = "true" if any_dirty else "false"
        if self.save_all_btn.property("dirty") != dirty_prop:
            self.save_all_btn.setProperty("dirty", dirty_prop)
            st = self.save_all_btn.style()
            if st is not None:
                st.unpolish(self.save_all_btn)
                st.polish(self.save_all_btn)

    def save_all(self):
        dirty_editors = [
            ed
            for ed in self.slot_editors.values()
            if ed.dirty and not ed.saving and ed.field is not None and not ed.read_only
        ]
        if len(dirty_editors) == 1:
            dirty_editors[0].save()
        elif len(dirty_editors) > 1:
            items = []
            for ed in dirty_editors:
                ed.debounce.stop()
                ed._submitted_value = copy.deepcopy(ed.value())
                ed._submitted_revision = ed.field.get("revision")
                ed.saving = True
                ed._refresh_state()
                items.append((ed.field, copy.deepcopy(ed._submitted_value)))
            self.batch_save_requested.emit(items, self)
        self._update_save_all_state()

    def save_succeeded(self, feedback="已保存并生效"):
        for ed in self.slot_editors.values():
            if ed.saving:
                ed.save_succeeded(feedback)
        self._update_save_all_state()

    def save_failed(self, feedback="保存失败"):
        for ed in self.slot_editors.values():
            if ed.saving:
                ed.save_failed(feedback)
        self._update_save_all_state()

    def discard_changes(self):
        for ed in self.slot_editors.values():
            if ed.dirty:
                ed.discard_changes()
        self._refresh_spec_preview()
        self._update_save_all_state()

    def is_editing(self) -> bool:
        focused = QApplication.focusWidget()
        if focused is not None and self.isAncestorOf(focused):
            return True
        return any(ed.is_editing() for ed in self.slot_editors.values())

    def sync_from_card(self, card: "PluginCard"):
        if card is None or self.current_card is not card:
            return
        self.plugin_data = copy.deepcopy(card.plugin_data)
        self._refresh_header()
        slot_defaults = {
            s[0]: s[2] for _, sec_slots in self.SECTIONS for s in sec_slots
        }
        for slot, ed in list(self.slot_editors.items()):
            new_field = self.plugin_data.get(slot)
            if new_field is None and slot != "config":
                new_field = self._synthesize_slot_field(slot)
            if isinstance(new_field, dict):
                ed.update_field(new_field)
                if not ed.is_editing():
                    default_val = "" if (slot in ("event", "cmd", "ft") and not ed.structured) else copy.deepcopy(slot_defaults.get(slot))
                    ed.set_editor_value(field_value(new_field, default_val))
        self._refresh_spec_preview()
        self._update_save_all_state()

    def _open_repo(self):
        if getattr(self, "repo_url", None):
            QDesktopServices.openUrl(QUrl(self.repo_url))

    def _on_delete_clicked(self):
        if self.current_card is not None:
            self.current_card._on_delete_clicked()


