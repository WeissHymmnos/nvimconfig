import argparse
import copy
import json
import os
import sys

from PyQt6.QtCore import QPointF, QRectF, QSignalBlocker, QSize, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QKeySequence, QPainter, QPalette, QPen, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from client import ApiClient
from theme import SCALE_CHOICES, THEME_CHOICES, TOKYO_NIGHT, ThemeManager, apply_theme, apply_tokyo_night_theme
from widgets import (
    CollapsibleSection,
    EmptySearchPlaceholder,
    FieldEditor,
    KeymapCard,
    NewKeymapCard,
    NewPluginCard,
    NotificationBanner,
    OfflineHeroCard,
    PluginCard,
    PluginDetailPanel,
    UnsupportedValue,
    lua_to_python,
    value_kind,
)


CATEGORIES = ["常用设置", "快捷键", "插件", "高级设置"]
COMMON_OPTIONS = [
    ("number", "显示行号", "在每行左侧显示行号，方便定位代码。"),
    ("relativenumber", "显示相对行号", "以当前行为起点显示距离，便于快速移动。"),
    ("shiftwidth", "自动缩进宽度", "设置自动缩进和格式化时使用的空格数。"),
    ("tabstop", "Tab 显示宽度", "设置一个 Tab 在屏幕上占几个字符宽。"),
    ("expandtab", "用空格代替 Tab", "按 Tab 时插入空格，让缩进在不同工具中保持一致。"),
    ("wrap", "自动换行", "超出窗口宽度的长行会在下一行继续显示。"),
    ("cursorline", "高亮当前行", "突出显示光标所在行，更容易找到当前位置。"),
    ("ignorecase", "搜索时忽略大小写", "搜索内容不区分大写和小写字母。"),
    ("smartcase", "智能区分大小写", "搜索词含大写字母时精确匹配，否则忽略大小写。"),
    ("scrolloff", "光标上下保留行数", "移动光标时，在窗口上下保留可见的上下文。"),
]
MODE_CHOICES = [
    ("普通模式", "n"),
    ("插入模式", "i"),
    ("可视模式", "v"),
    ("可视选择模式", "x"),
    ("选择模式", "s"),
    ("命令模式", "c"),
    ("终端模式", "t"),
]
MODE_NAMES = {raw: label for label, raw in MODE_CHOICES}


_NAV_ICON_CACHE = {}


def _make_md3_nav_icon(index: int, color_hex: str) -> QIcon:
    """Draws and caches a crisp 20x20 Material Design 3 geometric icon for Navigation Drawer items."""
    cache_key = (index, color_hex)
    cached = _NAV_ICON_CACHE.get(cache_key)
    if cached is not None:
        return cached
    pix = QPixmap(20, 20)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(color_hex), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)

    if index == 0:
        # M3 Tune / Sliders icon (常用设置)
        painter.drawLine(QPointF(3, 5), QPointF(17, 5))
        painter.drawLine(QPointF(3, 10), QPointF(17, 10))
        painter.drawLine(QPointF(3, 15), QPointF(17, 15))
        painter.setBrush(QColor(color_hex))
        painter.drawEllipse(QPointF(7, 5), 2.0, 2.0)
        painter.drawEllipse(QPointF(13, 10), 2.0, 2.0)
        painter.drawEllipse(QPointF(8, 15), 2.0, 2.0)
    elif index == 1:
        # M3 Keyboard icon (快捷键)
        painter.drawRoundedRect(QRectF(2.5, 4.5, 15.0, 11.0), 2.5, 2.5)
        painter.drawLine(QPointF(6.5, 12.5), QPointF(13.5, 12.5))
        for kx in (5.5, 8.5, 11.5, 14.5):
            painter.drawPoint(QPointF(kx, 7.5))
            painter.drawPoint(QPointF(kx, 9.8))
    elif index == 2:
        # M3 Extension / Grid Modules icon (插件)
        painter.drawRoundedRect(QRectF(3.0, 3.0, 6.0, 6.0), 1.8, 1.8)
        painter.drawRoundedRect(QRectF(11.0, 3.0, 6.0, 6.0), 1.8, 1.8)
        painter.drawRoundedRect(QRectF(3.0, 11.0, 6.0, 6.0), 1.8, 1.8)
        painter.drawRoundedRect(QRectF(11.0, 11.0, 6.0, 6.0), 1.8, 1.8)
    else:
        # M3 Terminal / Code icon (高级设置)
        painter.drawRoundedRect(QRectF(2.5, 3.5, 15.0, 13.0), 2.5, 2.5)
        painter.drawLine(QPointF(6.0, 8.0), QPointF(9.0, 10.5))
        painter.drawLine(QPointF(9.0, 10.5), QPointF(6.0, 13.0))
        painter.drawLine(QPointF(10.5, 13.0), QPointF(14.0, 13.0))

    painter.end()
    icon = QIcon(pix)
    _NAV_ICON_CACHE[cache_key] = icon
    return icon


def plain(value, default=""):
    result = lua_to_python(value)
    if result is None:
        return default
    if isinstance(result, UnsupportedValue):
        return result.source
    if isinstance(result, (dict, list)):
        return json.dumps(result, ensure_ascii=False)
    return str(result)


def field_value(field, default=None):
    if not isinstance(field, dict):
        return default
    value = field.get("value")
    return default if value is None else value


def friendly_error(message, saving=False):
    lowered = message.lower()
    if "revision" in lowered or "conflict" in lowered or "409" in lowered:
        reason = "配置刚被其他程序修改，请刷新后再试"
    elif "401" in lowered or "403" in lowered or "token" in lowered or "authorization" in lowered:
        reason = "连接验证失败，请检查访问令牌"
    elif "json" in lowered or "解析" in message:
        reason = "配置服务返回了无法识别的内容"
    elif "read-only" in lowered or "unsupported" in lowered:
        reason = "该配置项包含无法自动转换的动态脚本"
    elif "not found" in lowered or "404" in lowered:
        reason = "未找到对应的配置写入位置，请刷新后重试"
    elif "400" in lowered or "bad request" in lowered:
        reason = f"配置格式校验未通过 ({message})"
    else:
        reason = "无法连接配置服务，请检查 Neovim 是否正在运行"
    return f"保存失败：{reason}" if saving else reason


def make_group_card(title, subtitle=""):
    card = QFrame()
    card.setObjectName("groupCard")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(14, 12, 14, 12)
    layout.setSpacing(9)
    label = QLabel(title)
    label.setObjectName("groupTitle")
    layout.addWidget(label)
    if subtitle:
        source = QLabel(subtitle)
        source.setObjectName("settingDescription")
        source.setWordWrap(True)
        layout.addWidget(source)
    return card, layout


class EntityPage(QScrollArea):
    clear_search_requested = pyqtSignal()

    def __init__(self, empty_text, parent=None):
        super().__init__(parent)
        self.empty_text = empty_text
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.viewport().setObjectName("scrollViewport")
        self.container = QWidget()
        self.container.setObjectName("cardsContainer")
        self.layout = QVBoxLayout(self.container)
        self.layout.setContentsMargins(14, 12, 14, 12)
        self.layout.setSpacing(8)
        self.setWidget(self.container)

        self.card_registry = {}
        self._cards = []  # [(widget, search_text), ...]
        self.heading_registry = {}
        self._lazy_builder = None

        self.search_empty = EmptySearchPlaceholder(self.container)
        self.search_empty.clear_requested.connect(self.clear_search_requested.emit)
        self.search_empty.setVisible(False)
        self.layout.addWidget(self.search_empty)

        self.empty_label = QLabel(self.empty_text, self.container)
        self.empty_label.setObjectName("settingDescription")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.empty_label)
        self.empty_label.setVisible(True)

        self._stretch_item = self.layout.addStretch(1)

    def _ensure_built(self):
        if self._lazy_builder is not None:
            builder = self._lazy_builder
            self._lazy_builder = None
            builder()

    @property
    def cards(self):
        self._ensure_built()
        return self._cards

    @cards.setter
    def cards(self, value):
        self._cards = value

    def get_card(self, key):
        self._ensure_built()
        return self.card_registry.get(key)

    def _find_insert_index(self):
        count = self.layout.count()
        for i in range(count):
            item = self.layout.itemAt(i)
            if item == self._stretch_item:
                return i
            w = item.widget()
            if w in (self.search_empty, self.empty_label):
                return i
        return count

    def add_heading(self, text, heading_key=None):
        key = heading_key or f"heading:{text}"
        if key in self.heading_registry:
            heading = self.heading_registry[key]
            heading.setText(text)
            heading.setVisible(True)
            return heading
        label = QLabel(text)
        label.setObjectName("pageHeading")
        idx = self._find_insert_index()
        self.layout.insertWidget(idx, label)
        self.heading_registry[key] = label
        return label

    def add_card(self, widget, search_text="", card_key=None):
        key = card_key or f"card_{id(widget)}"
        self.card_registry[key] = widget
        widget._search_lower = search_text.lower()
        self.cards.append((widget, search_text))
        idx = self._find_insert_index()
        self.layout.insertWidget(idx, widget)
        self.empty_label.setVisible(False)
        return widget

    def update_card_search(self, card_key, search_text):
        widget = self.card_registry.get(card_key)
        if widget is not None:
            widget._search_lower = search_text.lower()
            for idx, (w, _) in enumerate(self.cards):
                if w is widget:
                    self.cards[idx] = (widget, search_text)
                    break

    def remove_card(self, card_key):
        widget = self.card_registry.pop(card_key, None)
        if widget is not None:
            self.cards = [(w, s) for w, s in self.cards if w is not widget]
            self.layout.removeWidget(widget)
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()
            if not self.cards:
                self.empty_label.setVisible(True)

    def sync_cards(self, active_keys):
        """Remove cards whose keys are no longer present in the active snapshot."""
        active_set = set(active_keys)
        to_remove = [k for k in list(self.card_registry.keys()) if k not in active_set]
        for k in to_remove:
            self.remove_card(k)

    def finish(self):
        self.empty_label.setVisible(len(self.cards) == 0)

    def is_editing(self):
        return any(w.is_editing() for w in self.findChildren(QWidget) if hasattr(w, "is_editing"))

    def save_view_state(self):
        """Capture scroll position and accordion expansion states."""
        accordions = {}
        for s in self.findChildren(CollapsibleSection):
            parent = s.parent()
            parent_key = getattr(parent, "name", "") or getattr(parent, "title", "") or str(id(s))
            accordions[f"{parent_key}:{s.toggle.text()}"] = s.toggle.isChecked()
            accordions[id(s)] = s.toggle.isChecked()
            if s.toggle.text() not in accordions:
                accordions[s.toggle.text()] = s.toggle.isChecked()

        keymap_opts = {}
        for card in self.findChildren(KeymapCard):
            card_key = getattr(card, "title", "") or f"{getattr(card, 'current_lhs', '')}:{getattr(card, 'current_mode', '')}" or str(id(card))
            is_open = not card.opts_container.isHidden()
            keymap_opts[card_key] = is_open
            keymap_opts[id(card)] = is_open

        state = {
            "v_scroll": self.verticalScrollBar().value(),
            "h_scroll": self.horizontalScrollBar().value(),
            "accordions": accordions,
            "keymap_opts": keymap_opts,
        }
        return state

    def restore_view_state(self, state):
        """Restore scroll position and accordion expansion states."""
        if not state:
            return
        acc_state = state.get("accordions", {})
        for s in self.findChildren(CollapsibleSection):
            parent = s.parent()
            parent_key = getattr(parent, "name", "") or getattr(parent, "title", "") or str(id(s))
            comp_key = f"{parent_key}:{s.toggle.text()}"
            if comp_key in acc_state:
                s.toggle.setChecked(acc_state[comp_key])
            elif id(s) in acc_state:
                s.toggle.setChecked(acc_state[id(s)])
            elif s.toggle.text() in acc_state:
                s.toggle.setChecked(acc_state[s.toggle.text()])

        opts_state = state.get("keymap_opts", {})
        for card in self.findChildren(KeymapCard):
            card_key = getattr(card, "title", "") or f"{getattr(card, 'current_lhs', '')}:{getattr(card, 'current_mode', '')}" or str(id(card))
            was_open = None
            if card_key in opts_state:
                was_open = opts_state[card_key]
            elif id(card) in opts_state:
                was_open = opts_state[id(card)]
            if was_open is not None:
                card.opts_container.setVisible(was_open)
                card.toggle_opts_btn.setText("收起高级选项 (opts)" if was_open else "展开高级选项 (opts)")

        v_val = state.get("v_scroll", 0)
        h_val = state.get("h_scroll", 0)
        self.verticalScrollBar().setValue(v_val)
        self.horizontalScrollBar().setValue(h_val)
        QTimer.singleShot(0, lambda: self._apply_scroll(v_val, h_val))

    def _apply_scroll(self, v_val, h_val):
        self.verticalScrollBar().setValue(v_val)
        self.horizontalScrollBar().setValue(h_val)

    def apply_filter(self, text):
        query = text.strip()
        lowered = query.lower()
        visible_count = 0
        self.container.setUpdatesEnabled(False)
        try:
            for widget, search_text in self.cards:
                s_low = getattr(widget, "_search_lower", None)
                if s_low is None:
                    s_low = search_text.lower()
                    widget._search_lower = s_low
                matched = not lowered or lowered in s_low
                if widget.isHidden() == matched:
                    widget.setVisible(matched)
                if matched:
                    visible_count += 1

            if query and self.cards and visible_count == 0:
                self.search_empty.set_query(query)
                self.search_empty.setVisible(True)
                self.empty_label.setVisible(False)
            else:
                self.search_empty.setVisible(False)
                self.empty_label.setVisible(len(self.cards) == 0)
        finally:
            self.container.setUpdatesEnabled(True)

    def clear(self):
        """Full clear for explicit resets."""
        for key in list(self.card_registry.keys()):
            self.remove_card(key)
        for heading in list(self.heading_registry.values()):
            self.layout.removeWidget(heading)
            heading.hide()
            heading.setParent(None)
            heading.deleteLater()
        self.heading_registry.clear()
        self.cards.clear()
        self.search_empty.setVisible(False)
        self.empty_label.setVisible(True)


class PluginFilterBar(QFrame):
    """Segmented filter bar for quick multi-manager switching with live counters."""
    filter_changed = pyqtSignal(str)
    add_plugin_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("pluginFilterBar")
        self.current_filter = "all"
        self.buttons = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(8)

        for key, label in [("all", "全部"), ("lazy", "lazy.nvim"), ("packer", "packer.nvim"), ("plug", "vim-plug")]:
            btn = QPushButton(f"{label} (0)")
            btn.setObjectName("filterTabButton")
            btn.setProperty("active", "true" if key == "all" else "false")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, k=key: self.set_filter(k))
            layout.addWidget(btn)
            self.buttons[key] = (btn, label)

        layout.addStretch(1)

        self.add_button = QPushButton("+ 新增插件")
        self.add_button.setObjectName("accentButton")
        self.add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_button.setToolTip("新增一个 Neovim 插件 (Ctrl+N)")
        self.add_button.clicked.connect(self.add_plugin_clicked.emit)
        layout.addWidget(self.add_button)

    def set_counts(self, counts: dict[str, int]):
        self._last_counts = dict(counts)
        for key, (btn, label) in self.buttons.items():
            count = counts.get(key, 0)
            btn.setText(f"{label} ({count})")

    def set_filter(self, key: str):
        if self.current_filter == key:
            return
        self.current_filter = key
        counts = getattr(self, "_last_counts", {})
        for k, (btn, label) in self.buttons.items():
            is_act = (k == key)
            btn.setProperty("active", "true" if is_act else "false")
            if counts:
                btn.setText(f"{label} ({counts.get(k, 0)})")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self.filter_changed.emit(key)


class PluginPage(QWidget):
    """
    Dedicated Master-Detail Plugin Page for Milestone 3:
    - Pinned manager filter bar + inline NewPluginCard
    - Horizontal QSplitter (`self.splitter`):
      - Left pane: Scrollable list of compact `PluginCard`s (`self.scroll_area`)
      - Right pane: `PluginDetailPanel` (`self.detail_panel`) inspector column
    """
    clear_search_requested = pyqtSignal()
    create_plugin_requested = pyqtSignal(object, object)

    def __init__(self, empty_text="当前没有插件配置", editor_factory=None, parent=None):
        super().__init__(parent)
        self.empty_text = empty_text
        self.current_search = ""
        self.selected_plugin_name = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Pinned Sticky Filter Bar
        self.filter_bar = PluginFilterBar(self)
        self.filter_bar.filter_changed.connect(self._on_filter_changed)
        self.filter_bar.add_plugin_clicked.connect(self.toggle_new_card)
        layout.addWidget(self.filter_bar)

        # Inline NewPluginCard
        self.new_card_wrapper = QWidget(self)
        wrapper_layout = QVBoxLayout(self.new_card_wrapper)
        wrapper_layout.setContentsMargins(14, 10, 14, 2)
        wrapper_layout.setSpacing(0)
        self.new_card = NewPluginCard(self.new_card_wrapper)
        self.new_card.create_requested.connect(self.create_plugin_requested.emit)
        self.new_card.cancelled.connect(self._hide_new_card)
        wrapper_layout.addWidget(self.new_card)
        self.new_card_wrapper.setVisible(False)
        layout.addWidget(self.new_card_wrapper)

        # Master-Detail Horizontal Splitter ("不要展开，右侧新增一栏，然后让界面可以缩放")
        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.setChildrenCollapsible(False)

        # Left Pane: Scrollable Master Plugin Card List
        self.scroll_area = EntityPage(empty_text, self.splitter)
        self.scroll_area.setMinimumWidth(310)
        self.scroll_area.clear_search_requested.connect(self.clear_search_requested.emit)
        self.splitter.addWidget(self.scroll_area)

        # Right Pane: Plugin Detail Inspector Panel
        self.detail_panel = PluginDetailPanel(editor_factory=editor_factory, parent=self.splitter)
        self.detail_panel.setMinimumWidth(290)
        self.splitter.addWidget(self.detail_panel)

        self.splitter.setStretchFactor(0, 4)
        self.splitter.setStretchFactor(1, 6)
        self.splitter.setSizes([380, 520])

        layout.addWidget(self.splitter, 1)

    def toggle_new_card(self):
        opening = not self.new_card_wrapper.isVisible()
        self.new_card_wrapper.setVisible(opening)
        self.filter_bar.add_button.setText("收起新增面板" if opening else "+ 新增插件")
        if opening:
            self.new_card.focus_first_input()

    def open_new_card(self):
        if not self.new_card_wrapper.isVisible():
            self.new_card_wrapper.setVisible(True)
            self.filter_bar.add_button.setText("收起新增面板")
        self.new_card.focus_first_input()

    def _hide_new_card(self):
        self.new_card_wrapper.setVisible(False)
        self.filter_bar.add_button.setText("+ 新增插件")

    def select_card(self, card):
        if card is None:
            self.selected_plugin_name = None
            for c, _ in self.scroll_area._cards:
                if hasattr(c, "set_selected"):
                    c.set_selected(False)
            self.detail_panel.clear_selection()
            return
        self.selected_plugin_name = getattr(card, "name", None)
        for c, _ in self.scroll_area._cards:
            if hasattr(c, "set_selected"):
                c.set_selected(c is card)
        if self.detail_panel.current_card is not card:
            self.detail_panel.load_plugin(card)
        else:
            self.detail_panel.sync_from_card(card)

    @property
    def cards(self):
        return self.scroll_area.cards

    @cards.setter
    def cards(self, value):
        self.scroll_area.cards = value

    @property
    def card_registry(self):
        self.scroll_area._ensure_built()
        return self.scroll_area.card_registry

    def get_card(self, key):
        return self.scroll_area.get_card(key)

    def add_card(self, widget, search_text="", card_key=None):
        if isinstance(widget, PluginCard):
            widget.selected_requested.connect(self.select_card)
        return self.scroll_area.add_card(widget, search_text, card_key=card_key)

    def update_card_search(self, card_key, search_text):
        self.scroll_area.update_card_search(card_key, search_text)

    def remove_card(self, card_key):
        widget = self.scroll_area.card_registry.get(card_key)
        if widget is not None and self.detail_panel.current_card is widget:
            self.detail_panel.clear_selection()
        self.scroll_area.remove_card(card_key)

    def sync_cards(self, active_keys):
        self.scroll_area.sync_cards(active_keys)

    def clear(self):
        self.detail_panel.clear_selection()
        self.scroll_area.clear()

    def verticalScrollBar(self):
        return self.scroll_area.verticalScrollBar()

    def horizontalScrollBar(self):
        return self.scroll_area.horizontalScrollBar()

    def finish(self):
        counts = {"all": len(self.scroll_area.cards), "lazy": 0, "packer": 0, "plug": 0}
        for card, _ in self.scroll_area.cards:
            mgr = getattr(card, "manager", "lazy")
            counts[mgr] = counts.get(mgr, 0) + 1
        self.filter_bar.set_counts(counts)
        self.scroll_area.finish()
        self._update_visibility()

    def is_editing(self):
        return any(w.is_editing() for w in self.findChildren(QWidget) if hasattr(w, "is_editing"))

    def save_view_state(self):
        state = self.scroll_area.save_view_state()
        state["manager_filter"] = self.filter_bar.current_filter
        state["selected_plugin"] = self.selected_plugin_name
        state["splitter_sizes"] = self.splitter.sizes()
        return state

    def restore_view_state(self, state):
        if not state:
            return
        mgr = state.get("manager_filter", "all")
        self.filter_bar.set_filter(mgr)
        self.scroll_area.restore_view_state(state)
        if state.get("splitter_sizes"):
            self.splitter.setSizes(state["splitter_sizes"])
        sel_name = state.get("selected_plugin")
        if sel_name:
            for card, _ in self.scroll_area._cards:
                if getattr(card, "name", None) == sel_name and not card.isHidden():
                    self.select_card(card)
                    break

    def apply_filter(self, text):
        self.current_search = text
        self._update_visibility()

    def _on_filter_changed(self, key):
        self._update_visibility()

    def _update_visibility(self):
        search_lower = self.current_search.strip().lower()
        visible_cards = []
        self.scroll_area.container.setUpdatesEnabled(False)
        try:
            for card, search_text in self.scroll_area.cards:
                mgr = getattr(card, "manager", "lazy")
                mgr_match = (self.filter_bar.current_filter == "all" or mgr == self.filter_bar.current_filter)
                s_low = getattr(card, "_search_lower", None)
                if s_low is None:
                    s_low = search_text.lower()
                    card._search_lower = s_low
                text_match = (not search_lower or search_lower in s_low)
                is_vis = mgr_match and text_match
                if card.isHidden() == is_vis:
                    card.setVisible(is_vis)
                if is_vis:
                    visible_cards.append(card)

            visible_count = len(visible_cards)
            if not self.scroll_area.cards:
                self.scroll_area.empty_label.setText(self.empty_text)
                self.scroll_area.empty_label.setVisible(True)
                self.scroll_area.search_empty.setVisible(False)
            elif visible_count == 0:
                if self.current_search:
                    self.scroll_area.search_empty.set_query(self.current_search)
                    self.scroll_area.search_empty.setVisible(True)
                    self.scroll_area.empty_label.setVisible(False)
                elif self.filter_bar.current_filter != "all":
                    names = {"lazy": "lazy.nvim", "packer": "packer.nvim", "plug": "vim-plug"}
                    self.scroll_area.empty_label.setText(f"当前没有 {names.get(self.filter_bar.current_filter, self.filter_bar.current_filter)} 插件配置")
                    self.scroll_area.empty_label.setVisible(True)
                    self.scroll_area.search_empty.setVisible(False)
                else:
                    self.scroll_area.empty_label.setText(self.empty_text)
                    self.scroll_area.empty_label.setVisible(True)
                    self.scroll_area.search_empty.setVisible(False)
            else:
                self.scroll_area.empty_label.setVisible(False)
                self.scroll_area.search_empty.setVisible(False)
        finally:
            self.scroll_area.container.setUpdatesEnabled(True)

        # Maintain or auto-select the active plugin in the right-hand detail panel
        if visible_cards:
            if self.detail_panel.current_card in visible_cards:
                if not self.detail_panel.current_card.is_selected():
                    self.select_card(self.detail_panel.current_card)
            else:
                target = None
                if self.selected_plugin_name:
                    for c in visible_cards:
                        if getattr(c, "name", None) == self.selected_plugin_name:
                            target = c
                            break
                self.select_card(target or visible_cards[0])
        else:
            self.detail_panel.clear_selection()


class KeymapPage(QWidget):
    """
    Dedicated Keymap Page with pinned top action/filter bar and inline NewKeymapCard.
    Maintains full interface parity with EntityPage.
    """
    clear_search_requested = pyqtSignal()
    create_keymap_requested = pyqtSignal(object, object, object, object, object)

    def __init__(self, empty_text="当前没有快捷键配置", parent=None):
        super().__init__(parent)
        self.empty_text = empty_text
        self.current_search = ""
        self.current_mode_filter = "all"
        self.mode_buttons = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.top_bar = QFrame(self)
        self.top_bar.setObjectName("pluginFilterBar")
        bar_layout = QHBoxLayout(self.top_bar)
        bar_layout.setContentsMargins(14, 8, 14, 8)
        bar_layout.setSpacing(8)

        for key, label in [
            ("all", "全部"),
            ("n", "普通 (n)"),
            ("i", "插入 (i)"),
            ("v", "可视 (v)"),
            ("t", "终端 (t)"),
        ]:
            btn = QPushButton(f"{label} (0)")
            btn.setObjectName("filterTabButton")
            btn.setProperty("active", "true" if key == "all" else "false")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, k=key: self.set_mode_filter(k))
            bar_layout.addWidget(btn)
            self.mode_buttons[key] = (btn, label)

        bar_layout.addStretch(1)

        self.add_button = QPushButton("+ 新增快捷键")
        self.add_button.setObjectName("accentButton")
        self.add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_button.setToolTip("新增一条快捷键映射 (Ctrl+N)")
        self.add_button.clicked.connect(self.toggle_new_card)
        bar_layout.addWidget(self.add_button)

        layout.addWidget(self.top_bar)

        self.new_card_wrapper = QWidget(self)
        wrapper_layout = QVBoxLayout(self.new_card_wrapper)
        wrapper_layout.setContentsMargins(14, 10, 14, 2)
        wrapper_layout.setSpacing(0)
        self.new_card = NewKeymapCard(self.new_card_wrapper)
        self.new_card.create_requested.connect(self.create_keymap_requested.emit)
        self.new_card.cancelled.connect(self._hide_new_card)
        wrapper_layout.addWidget(self.new_card)
        self.new_card_wrapper.setVisible(False)
        layout.addWidget(self.new_card_wrapper)

        self.scroll_area = EntityPage(empty_text, self)
        self.scroll_area.clear_search_requested.connect(self.clear_search_requested.emit)
        layout.addWidget(self.scroll_area, 1)

    def toggle_new_card(self):
        opening = not self.new_card_wrapper.isVisible()
        self.new_card_wrapper.setVisible(opening)
        self.add_button.setText("收起新增面板" if opening else "+ 新增快捷键")
        if opening:
            self.new_card.focus_first_input()

    def open_new_card(self):
        if not self.new_card_wrapper.isVisible():
            self.new_card_wrapper.setVisible(True)
            self.add_button.setText("收起新增面板")
        self.new_card.focus_first_input()

    def _hide_new_card(self):
        self.new_card_wrapper.setVisible(False)
        self.add_button.setText("+ 新增快捷键")

    def set_mode_filter(self, key: str):
        if self.current_mode_filter == key:
            return
        self.current_mode_filter = key
        counts = getattr(self, "_last_mode_counts", {})
        for k, (btn, label) in self.mode_buttons.items():
            is_act = (k == key)
            btn.setProperty("active", "true" if is_act else "false")
            if counts:
                btn.setText(f"{label} ({counts.get(k, 0)})")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self._update_visibility()

    @property
    def cards(self):
        return self.scroll_area.cards

    @cards.setter
    def cards(self, value):
        self.scroll_area.cards = value

    @property
    def card_registry(self):
        return self.scroll_area.card_registry

    def get_card(self, key):
        return self.scroll_area.get_card(key)

    def add_card(self, widget, search_text="", card_key=None):
        return self.scroll_area.add_card(widget, search_text, card_key=card_key)

    def update_card_search(self, card_key, search_text):
        self.scroll_area.update_card_search(card_key, search_text)

    def remove_card(self, card_key):
        self.scroll_area.remove_card(card_key)

    def sync_cards(self, active_keys):
        self.scroll_area.sync_cards(active_keys)

    def clear(self):
        self.scroll_area.clear()

    def verticalScrollBar(self):
        return self.scroll_area.verticalScrollBar()

    def horizontalScrollBar(self):
        return self.scroll_area.horizontalScrollBar()

    def finish(self):
        counts = {"all": len(self.scroll_area.cards), "n": 0, "i": 0, "v": 0, "t": 0}
        for card, _ in self.scroll_area.cards:
            mode = getattr(card, "current_mode", "n")
            counts[mode] = counts.get(mode, 0) + 1
        self._last_mode_counts = dict(counts)
        for key, (btn, label) in self.mode_buttons.items():
            btn.setText(f"{label} ({counts.get(key, 0)})")
        self.scroll_area.finish()
        self._update_visibility()

    def is_editing(self):
        return any(w.is_editing() for w in self.findChildren(QWidget) if hasattr(w, "is_editing"))

    def save_view_state(self):
        state = self.scroll_area.save_view_state()
        state["mode_filter"] = self.current_mode_filter
        state["new_card_open"] = self.new_card_wrapper.isVisible()
        return state

    def restore_view_state(self, state):
        if not state:
            return
        self.set_mode_filter(state.get("mode_filter", "all"))
        self.scroll_area.restore_view_state(state)

    def apply_filter(self, text):
        self.current_search = text
        self._update_visibility()

    def _update_visibility(self):
        search_lower = self.current_search.strip().lower()
        visible_count = 0
        self.scroll_area.container.setUpdatesEnabled(False)
        try:
            for card, search_text in self.scroll_area.cards:
                mode = getattr(card, "current_mode", "n")
                mode_match = (self.current_mode_filter == "all" or mode == self.current_mode_filter)
                text_match = (not search_lower or search_lower in search_text.lower())
                is_vis = mode_match and text_match
                if card.isHidden() == is_vis:
                    card.setVisible(is_vis)
                if is_vis:
                    visible_count += 1

            if not self.scroll_area.cards:
                self.scroll_area.empty_label.setText(self.empty_text)
                self.scroll_area.empty_label.setVisible(True)
                self.scroll_area.search_empty.setVisible(False)
            elif visible_count == 0:
                if self.current_search:
                    self.scroll_area.search_empty.set_query(self.current_search)
                    self.scroll_area.search_empty.setVisible(True)
                    self.scroll_area.empty_label.setVisible(False)
                else:
                    self.scroll_area.empty_label.setText(f"当前模式下没有快捷键配置")
                    self.scroll_area.empty_label.setVisible(True)
                    self.scroll_area.search_empty.setVisible(False)
            else:
                self.scroll_area.empty_label.setVisible(False)
                self.scroll_area.search_empty.setVisible(False)
        finally:
            self.scroll_area.container.setUpdatesEnabled(True)


class MainWindow(QMainWindow):
    ALL_OPTIONS_CHUNK_SIZE = 35

    def __init__(self, base_url, token=""):
        super().__init__()
        self.setWindowTitle("Neovim 设置")
        self.resize(1040, 720)
        self.setMinimumSize(900, 620)
        self.snapshot = {"settings": [], "keymaps": [], "plugins": [], "diagnostics": []}
        self.schema_options = []
        self._closing = False
        self._events_connected = False
        self._nvim_connected = False
        self._has_received_state = False
        self._active_category_index = 0
        self._dirty_pages = set()
        self._all_options_limit = self.ALL_OPTIONS_CHUNK_SIZE
        self.unsaved_guard_enabled = True
        self.unsaved_guard_policy = "prompt"  # "prompt", "save", "discard", "cancel"
        self.unsaved_guard_handler = None
        self.auto_save_enabled = True
        self._undo_stack = []

        self.client = ApiClient(base_url, token, self)
        self.client.state_ready.connect(self._state_received)
        self.client.schema_ready.connect(self._schema_received)
        self.client.patch_ready.connect(self._patch_received)
        self.client.request_error.connect(self._request_error)
        self.client.change_received.connect(self._change_received)
        self.client.events_status.connect(self._events_status)

        self.connection_label = QLabel("实时同步未连接 · 正在连接")
        self.connection_label.setObjectName("connectionOffline")

        self.auto_save_checkbox = QCheckBox("自动保存")
        self.auto_save_checkbox.setObjectName("autoSaveToggle")
        self.auto_save_checkbox.setChecked(True)
        self.auto_save_checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        self.auto_save_checkbox.setToolTip(
            "开启后，开关与数字选项修改后将自动保存（Ctrl+Z 可撤销最近一次保存）；关闭后需点击“应用修改”或按 Ctrl+S 手动保存"
        )
        self.auto_save_checkbox.toggled.connect(self.set_auto_save_enabled)

        self.scale_selector = QComboBox()
        self.scale_selector.setObjectName("scaleSelector")
        self.scale_selector.setToolTip("界面缩放比例 (Ctrl+= 放大 / Ctrl+- 缩小 / Ctrl+0 重置 / Ctrl+滚轮)")
        self.scale_selector.setCursor(Qt.CursorShape.PointingHandCursor)
        self.scale_selector.setMinimumWidth(114)
        self.scale_selector.setMaximumWidth(145)
        for scale_val, scale_label in SCALE_CHOICES:
            self.scale_selector.addItem(f"缩放 {scale_label}", scale_val)
        current_scale_idx = self.scale_selector.findData(ThemeManager.instance().current_scale)
        if current_scale_idx >= 0:
            self.scale_selector.setCurrentIndex(current_scale_idx)
        self.scale_selector.currentIndexChanged.connect(self._on_scale_selected)
        ThemeManager.instance().scale_changed.connect(self._on_scale_changed_external)

        self.theme_selector = QComboBox()
        self.theme_selector.setObjectName("themeSelector")
        self.theme_selector.setToolTip("切换界面配色主题")
        self.theme_selector.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_selector.setMinimumWidth(196)
        self.theme_selector.setMaximumWidth(245)
        for theme_key, theme_label in THEME_CHOICES:
            self.theme_selector.addItem(theme_label, theme_key)
        current_theme_idx = self.theme_selector.findData(ThemeManager.instance().current_theme)
        if current_theme_idx >= 0:
            self.theme_selector.setCurrentIndex(current_theme_idx)
        self.theme_selector.currentIndexChanged.connect(self._on_theme_selected)
        ThemeManager.instance().theme_changed.connect(self._on_theme_changed_external)

        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索设置、快捷键或插件")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(190)
        self.search.setMaximumWidth(320)

        self.search_debounce = QTimer(self)
        self.search_debounce.setSingleShot(True)
        self.search_debounce.setInterval(150)
        self.search_debounce.timeout.connect(self._filter_current)

        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(self.connection_label)
        top.addStretch(1)
        top.addWidget(self.auto_save_checkbox)
        top.addWidget(self.scale_selector)
        top.addWidget(self.theme_selector)
        top.addWidget(self.search)

        self.category_list = QListWidget()
        self.category_list.addItems(CATEGORIES)
        self.category_list.setIconSize(QSize(18, 18))
        self.category_list.setCurrentRow(0)
        self.category_list.setObjectName("categoryList")
        self._refresh_nav_icons()
        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(10, 14, 10, 10)
        title = QLabel("设置导航")
        title.setObjectName("sidebarTitle")
        left_layout.addWidget(title)
        left_layout.addWidget(self.category_list)
        left = QWidget()
        left.setObjectName("sidebarPanel")
        left.setMinimumWidth(148)
        left.setMaximumWidth(260)
        left.setLayout(left_layout)

        self.stack = QStackedWidget()
        self.common_page = EntityPage("没有找到常用设置")
        self.keymap_page = KeymapPage("当前没有快捷键配置")
        self.keymap_page.create_keymap_requested.connect(self._create_keymap)
        self.plugin_page = PluginPage("当前没有插件配置", editor_factory=self._editor)
        self.plugin_page.create_plugin_requested.connect(self._create_plugin)
        self.plugin_page.detail_panel.batch_save_requested.connect(self._save_entities_batch)
        self.advanced_tabs = QTabWidget()
        self.all_options_page = EntityPage("没有可显示的原生选项")
        self.globals_page = EntityPage("没有全局变量或环境变量")
        self.diagnostics_page = EntityPage("没有需要处理的问题")
        self.advanced_tabs.addTab(self.all_options_page, "全部选项")
        self.advanced_tabs.addTab(self.globals_page, "全局与环境")
        self.advanced_tabs.addTab(self.diagnostics_page, "诊断")
        self.pages = [self.common_page, self.keymap_page, self.plugin_page, self.advanced_tabs]
        for page in self.pages:
            self.stack.addWidget(page)

        # Offline Hero Card at index 4
        self.offline_hero = OfflineHeroCard(base_url, on_retry=self.refresh)
        self.stack.addWidget(self.offline_hero)

        self.category_list.currentRowChanged.connect(self._category_changed)
        self.search.textEdited.connect(self._on_search_edited)
        self.search.textChanged.connect(self._on_search_changed)
        self.advanced_tabs.currentChanged.connect(self._filter_current)

        splitter = QSplitter()
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(left)
        splitter.addWidget(self.stack)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([154, 840])
        self.main_splitter = splitter
        central = QWidget()
        central.setObjectName("centralWidget")
        layout = QVBoxLayout(central)
        layout.setContentsMargins(14, 12, 14, 6)
        layout.addLayout(top)
        layout.addWidget(splitter)
        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("正在读取设置…")

        # Floating Notification Toast Banner
        self.notification_banner = NotificationBanner(self)

        # Connect search clearing from all pages
        for page in self._entity_pages():
            if hasattr(page, "clear_search_requested"):
                page.clear_search_requested.connect(self._clear_search)

        # Keyboard shortcuts
        self._init_shortcuts()

        self.refresh_timer = QTimer(self)
        self.refresh_timer.setSingleShot(True)
        self.refresh_timer.setInterval(350)
        self.refresh_timer.timeout.connect(self.client.get_state)

    def start(self):
        self.refresh()
        self.client.start_events()

    def refresh(self):
        self.statusBar().showMessage("正在读取设置…")
        self.client.get_state()
        self.client.get_schema()

    def _entity_pages(self):
        return [self.common_page, self.keymap_page, self.plugin_page, self.all_options_page, self.globals_page, self.diagnostics_page]

    def _update_connection(self):
        if self._events_connected and self._nvim_connected:
            self.connection_label.setText("实时同步已连接")
            self.connection_label.setObjectName("connectionOnline")
            self.connection_label.setToolTip("后台配置服务与 Neovim 均已连接，设置修改会自动保存并同步到 Neovim")
        elif self._events_connected and not self._nvim_connected:
            self.connection_label.setText("配置服务已就绪 · 离线编辑模式")
            self.connection_label.setObjectName("connectionStandby")
            self.connection_label.setToolTip(
                "后台配置服务运行正常，当前未检测到活动的 Neovim 实例；所有修改将安全写入配置文件，重启 Neovim 后生效"
            )
        else:
            self.connection_label.setText("实时同步未连接 · 请启动 Neovim 并检查连接")
            self.connection_label.setObjectName("connectionOffline")
            self.connection_label.setToolTip("连接恢复后，修改才会同步到正在运行的 Neovim")
        self.connection_label.style().unpolish(self.connection_label)
        self.connection_label.style().polish(self.connection_label)

    def _state_received(self, payload):
        try:
            snapshot = payload.get("snapshot") or {}
            if not isinstance(snapshot, dict):
                raise ValueError("配置内容不是有效对象")
            self.snapshot = snapshot
            self._nvim_connected = bool((payload.get("nvim") or {}).get("connected"))
            self._update_connection()
            self._update_editor_fields()
            self._render_all()

            self._has_received_state = True
            if self.stack.currentWidget() is self.offline_hero:
                self.stack.setCurrentIndex(self.category_list.currentRow())

            self.offline_hero.stop_countdown()
            self.statusBar().showMessage("设置已更新", 3000)
        except Exception as exc:
            self._request_error(f"解析配置失败：{exc}")

    def _schema_received(self, payload):
        try:
            options = payload.get("options", payload) if isinstance(payload, dict) else payload
            normalized = []
            if isinstance(options, dict):
                for name, schema in options.items():
                    if isinstance(schema, dict):
                        item = copy.deepcopy(schema)
                        item.setdefault("name", name)
                        normalized.append(item)
            elif isinstance(options, list):
                normalized = [item for item in options if isinstance(item, dict)]
            self.schema_options = normalized
            self._render_page(0)
            if self.category_list.currentRow() == 3:
                self._render_page(3)
            else:
                self._mark_page_dirty(3)
        except Exception as exc:
            self._request_error(f"解析选项说明失败：{exc}")

    def _change_received(self):
        if not self._closing:
            self.refresh_timer.start()

    def _events_status(self, message):
        self._events_connected = "已连接" in message
        self._update_connection()

    def _request_error(self, message):
        friendly = friendly_error(message, saving="保存" in message or "添加" in message)
        self.statusBar().showMessage(friendly, 10000)
        lowered = message.lower()
        if "409" in lowered or "conflict" in lowered or "revision" in lowered:
            self.show_notification(
                "配置刚被外部程序修改，保存产生冲突。请立即刷新以合并最新版本。",
                level="warning",
                duration_ms=0,
                action_text="立即刷新 (F5)",
                on_action=self.refresh,
            )
        elif not self._has_received_state:
            self.offline_hero.set_error(friendly)
            self.offline_hero.start_countdown(5)
            self.stack.setCurrentWidget(self.offline_hero)
        else:
            self.show_notification(friendly, level="error", duration_ms=5000)

    def _fields_by_id(self):
        fields = {}
        for setting in self.snapshot.get("settings", []):
            if isinstance(setting, dict):
                field = setting.get("field")
                if isinstance(field, dict) and field.get("id") is not None:
                    fields[field["id"]] = field
        for keymap in self.snapshot.get("keymaps", []):
            if isinstance(keymap, dict):
                for val in keymap.values():
                    if isinstance(val, dict) and val.get("id") is not None:
                        fields[val["id"]] = val
        for plugin in self.snapshot.get("plugins", []):
            if isinstance(plugin, dict):
                for val in plugin.values():
                    if isinstance(val, dict) and val.get("id") is not None:
                        fields[val["id"]] = val
        return fields

    def _update_editor_fields(self):
        fields = self._fields_by_id()
        option_fields = {}
        for setting in self.snapshot.get("settings", []):
            if setting.get("namespace") == "opt" and isinstance(setting.get("field"), dict):
                option_fields.setdefault(setting.get("name"), setting.get("field"))
        for page in self._entity_pages():
            for editor in page.findChildren(FieldEditor):
                if editor.creation:
                    name = editor.field.get("create_option")
                    if name in option_fields:
                        editor.update_field(option_fields[name])
                elif editor.field and editor.field.get("id") in fields:
                    editor.update_field(fields[editor.field["id"]])
        for card in self.keymap_page.findChildren(KeymapCard):
            updated_keymap = {}
            for slot, orig_field in (
                ("lhs", card.field_lhs),
                ("mode", card.field_mode),
                ("rhs", card.field_rhs),
                ("opts", card.field_opts),
            ):
                if isinstance(orig_field, dict) and orig_field.get("id") in fields:
                    updated_keymap[slot] = fields[orig_field["id"]]
                else:
                    updated_keymap[slot] = orig_field
            card.update_snapshot_fields(updated_keymap)

    def _mark_page_dirty(self, index: int):
        self._dirty_pages.add(index)
        if index == 1:
            self.keymap_page.scroll_area._lazy_builder = lambda: self._render_page(1)
        elif index == 2:
            self.plugin_page.scroll_area._lazy_builder = lambda: self._render_page(2)
        elif index == 3:
            for sub in (self.all_options_page, self.globals_page, self.diagnostics_page):
                sub._lazy_builder = lambda: self._render_page(3)

    def _ensure_page_rendered(self, index: int):
        if index in self._dirty_pages:
            self._render_page(index)

    def _render_all(self):
        active_idx = self.category_list.currentRow()
        if active_idx < 0 or active_idx >= 4:
            active_idx = 0
        for index in range(4):
            if index == active_idx:
                self._render_page(index)
            else:
                self._mark_page_dirty(index)
        self._filter_current()

    def _render_page(self, index):
        self._dirty_pages.discard(index)
        if index == 3:
            for sub in (self.all_options_page, self.globals_page, self.diagnostics_page):
                sub._lazy_builder = None
            builders = [self._build_all_options, self._build_globals, self._build_diagnostics]
            pages = [self.all_options_page, self.globals_page, self.diagnostics_page]
        else:
            page = self.pages[index]
            if hasattr(page, "scroll_area"):
                page.scroll_area._lazy_builder = None
            else:
                page._lazy_builder = None
            builders = [[self._build_common, self._build_keymaps, self._build_plugins][index]]
            pages = [page]
        try:
            for page, builder in zip(pages, builders):
                page.setUpdatesEnabled(False)
                try:
                    view_state = page.save_view_state()
                    builder(page)
                    page.finish()
                    page.restore_view_state(view_state)
                    page.apply_filter(self.search.text())
                finally:
                    page.setUpdatesEnabled(True)
        except Exception as exc:
            self.statusBar().showMessage(f"页面显示失败：{friendly_error(str(exc))}", 8000)

    def _editor(self, title, field, **kwargs):
        editor = FieldEditor(title, field, **kwargs)
        if not self.auto_save_enabled:
            editor.set_auto_save_enabled(False)
        editor.save_requested.connect(self._save_entity)
        return editor

    def set_auto_save_enabled(self, enabled: bool):
        self.auto_save_enabled = bool(enabled)
        if hasattr(self, "auto_save_checkbox") and self.auto_save_checkbox.isChecked() != self.auto_save_enabled:
            with QSignalBlocker(self.auto_save_checkbox):
                self.auto_save_checkbox.setChecked(self.auto_save_enabled)
        for page in self._entity_pages():
            for editor in page.findChildren(FieldEditor):
                editor.set_auto_save_enabled(self.auto_save_enabled)

    def _update_field_editor(self, editor, field, value=None, default=None, schema=None):
        if schema:
            editor.schema = schema
        editor.update_field(field)
        if not editor.is_editing():
            new_val = value if value is not None else (field.get("value") if isinstance(field, dict) else None)
            if new_val is None and default is not None:
                new_val = default
            if new_val is not None:
                py_val = lua_to_python(new_val)
                self._set_field_editor_control_value(editor, py_val)

    def _set_field_editor_control_value(self, editor, py_val):
        if py_val is None or not hasattr(editor, "editor") or editor.editor is None:
            return
        editor.python_value = copy.deepcopy(py_val)
        ctrl = editor.editor
        ctrl.blockSignals(True)
        try:
            from widgets import SwitchWidget, IntegerEdit
            from PyQt6.QtWidgets import QCheckBox, QDoubleSpinBox, QComboBox, QLineEdit
            if isinstance(ctrl, (SwitchWidget, QCheckBox)):
                ctrl.setChecked(bool(py_val))
                if isinstance(ctrl, QCheckBox) and not isinstance(ctrl, SwitchWidget):
                    ctrl.setText("开启" if py_val else "关闭")
            elif isinstance(ctrl, IntegerEdit):
                ctrl.set_value(py_val)
            elif isinstance(ctrl, QDoubleSpinBox):
                ctrl.setValue(float(py_val))
            elif isinstance(ctrl, QComboBox):
                idx = ctrl.findData(py_val)
                if idx >= 0:
                    ctrl.setCurrentIndex(idx)
            elif isinstance(ctrl, QLineEdit):
                ctrl.setText(str(py_val))
        finally:
            ctrl.blockSignals(False)

    def _build_common(self, page):
        settings = {}
        for item in self.snapshot.get("settings", []):
            if item.get("namespace") == "opt":
                settings.setdefault(item.get("name"), item)
        schemas = {item.get("name"): item for item in self.schema_options}
        active_keys = []
        for name, title, description in COMMON_OPTIONS:
            card_key = f"opt:{name}"
            active_keys.append(card_key)
            setting = settings.get(name)
            field = setting.get("field") if setting else None
            if field is None:
                field = {"create_option": name}
            schema = schemas.get(name, {})
            value = field_value(field, schema.get("default"))
            kind = value_kind(lua_to_python(value))
            search_text = f"{title} {description} {name}"

            existing = page.get_card(card_key)
            if existing is not None and isinstance(existing, FieldEditor):
                self._update_field_editor(existing, field, value=value, default=schema.get("default"), schema=schema)
                page.update_card_search(card_key, search_text)
            else:
                editor = self._editor(
                    title,
                    field,
                    value=value,
                    default=schema.get("default"),
                    schema=schema,
                    auto_save=kind in {"boolean", "number"},
                    description=description,
                    technical_name=name,
                    compact=True,
                )
                page.add_card(editor, search_text, card_key=card_key)
        page.sync_cards(active_keys)

    def _load_more_all_options(self):
        self._all_options_limit += 50
        self._render_page(3)

    def _build_all_options(self, page):
        settings = [item for item in self.snapshot.get("settings", []) if item.get("namespace") == "opt"]
        by_name = {}
        for item in settings:
            by_name.setdefault(item.get("name"), item)
        shown = set()
        common_names = {name for name, _, _ in COMMON_OPTIONS}
        common_descriptions = {name: (title, description) for name, title, description in COMMON_OPTIONS}
        active_keys = []
        search_query = self.search.text().strip().lower()
        rendered_unconfigured = 0
        total_unconfigured = 0

        ordered_schemas = sorted(
            self.schema_options,
            key=lambda s: (0 if str(s.get("name", "")) in by_name else 1, str(s.get("name", ""))),
        )

        for schema in ordered_schemas:
            name = str(schema.get("name", ""))
            if not name:
                continue
            setting = by_name.get(name)
            title, description = common_descriptions.get(name, (name, ""))
            search_text = f"{name} {title}"
            is_configured = setting is not None
            matches_search = bool(search_query and search_query in search_text.lower())

            if not is_configured and not matches_search:
                total_unconfigured += 1
                if rendered_unconfigured >= self._all_options_limit:
                    continue
                rendered_unconfigured += 1

            card_key = f"opt:{name}"
            active_keys.append(card_key)
            field = setting.get("field") if setting else None
            if field is None:
                field = {"create_option": name}
            value = field_value(field, schema.get("default"))
            kind = value_kind(lua_to_python(value))

            existing = page.get_card(card_key)
            if existing is not None and isinstance(existing, FieldEditor):
                self._update_field_editor(existing, field, value=value, default=schema.get("default"), schema=schema)
                page.update_card_search(card_key, search_text)
            else:
                editor = self._editor(
                    title,
                    field,
                    value=value,
                    default=schema.get("default"),
                    schema=schema,
                    auto_save=kind in {"boolean", "number"},
                    advanced=True,
                    description=description,
                    technical_name=name,
                    compact=(kind not in {"array", "table", "unsupported"}),
                )
                page.add_card(editor, search_text, card_key=card_key)
            shown.add(name)
        for setting in settings:
            name = str(setting.get("name", ""))
            if name in shown:
                continue
            card_key = f"opt:{name}"
            active_keys.append(card_key)
            field = setting.get("field")
            val = field_value(field)
            kind = value_kind(lua_to_python(val))
            search_text = name
            existing = page.get_card(card_key)
            if existing is not None and isinstance(existing, FieldEditor):
                self._update_field_editor(existing, field, value=val)
                page.update_card_search(card_key, search_text)
            else:
                editor = self._editor(
                    name,
                    field,
                    value=val,
                    auto_save=kind in {"boolean", "number"},
                    advanced=True,
                    technical_name=name,
                    compact=(kind not in {"array", "table", "unsupported"}),
                )
                page.add_card(editor, search_text, card_key=card_key)

        remaining = max(0, total_unconfigured - rendered_unconfigured)
        if remaining > 0 and not search_query:
            more_key = "opt:__load_more__"
            active_keys.append(more_key)
            more_btn = page.get_card(more_key)
            btn_text = f"加载更多原生选项（剩余 {remaining} 项）"
            if more_btn is not None and isinstance(more_btn, QPushButton):
                more_btn.setText(btn_text)
            else:
                more_btn = QPushButton(btn_text)
                more_btn.setObjectName("accentButton")
                more_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                more_btn.clicked.connect(self._load_more_all_options)
                page.add_card(more_btn, btn_text, card_key=more_key)

        page.sync_cards(active_keys)

    def _build_globals(self, page):
        active_keys = []
        seen_keys = set()
        for namespace, heading in (("g", "全局变量"), ("env", "环境变量")):
            heading_key = f"heading:{namespace}"
            page.add_heading(heading, heading_key=heading_key)
            for setting in self.snapshot.get("settings", []):
                if setting.get("namespace") != namespace:
                    continue
                name = str(setting.get("name", ""))
                field = setting.get("field")
                field_id = field.get("id") if isinstance(field, dict) else None
                base_key = f"{namespace}:{name}"
                card_key = base_key if base_key not in seen_keys else f"{base_key}:{field_id or len(seen_keys)}"
                seen_keys.add(card_key)
                active_keys.append(card_key)
                val = field_value(field)
                kind = value_kind(lua_to_python(val))
                search_text = f"{namespace}.{name}"
                existing = page.get_card(card_key)
                if existing is not None and isinstance(existing, FieldEditor):
                    self._update_field_editor(existing, field, value=val)
                    page.update_card_search(card_key, search_text)
                else:
                    editor = self._editor(
                        name,
                        field,
                        value=val,
                        auto_save=kind in {"boolean", "number"},
                        advanced=True,
                        technical_name=f"{namespace}.{name}",
                        compact=(kind not in {"array", "table", "unsupported"}),
                    )
                    page.add_card(editor, search_text, card_key=card_key)
        page.sync_cards(active_keys)

    def _build_keymaps(self, page):
        active_keys = []
        for idx, keymap in enumerate(self.snapshot.get("keymaps", [])):
            if not isinstance(keymap, dict):
                continue
            lhs_id = (keymap.get("lhs") or {}).get("id")
            mode_val = plain(field_value(keymap.get("mode")), "n")
            lhs_val = plain(field_value(keymap.get("lhs")), "")
            card_key = f"keymap:{lhs_id}" if lhs_id else f"keymap:{mode_val}:{lhs_val}:{idx}"
            active_keys.append(card_key)

            lhs = plain(field_value(keymap.get("lhs")), "未命名快捷键")
            mode = plain(field_value(keymap.get("mode")), "n")
            rhs = plain(field_value(keymap.get("rhs")))
            search_text = f"{lhs} {rhs} {MODE_NAMES.get(mode, mode)} {mode}"

            card = page.get_card(card_key)
            if card is not None and isinstance(card, KeymapCard):
                card.update_snapshot_fields(keymap)
                page.update_card_search(card_key, search_text)
            else:
                card = KeymapCard(keymap)
                card.save_requested.connect(self._save_entity)
                card.batch_save_requested.connect(self._save_entities_batch)
                card.delete_requested.connect(self._delete_entity)
                page.add_card(card, search_text, card_key=card_key)
        page.sync_cards(active_keys)

    def _build_plugins(self, page):
        active_keys = []
        for idx, plugin in enumerate(self.snapshot.get("plugins", [])):
            if not isinstance(plugin, dict):
                continue
            name = str(plugin.get("name") or f"unnamed_{idx}")
            card_key = f"plugin:{name}"
            active_keys.append(card_key)

            existing = page.get_card(card_key)
            if existing is not None and isinstance(existing, PluginCard):
                existing.update_data(plugin)
                if hasattr(page, "detail_panel") and page.detail_panel.current_card is existing:
                    page.detail_panel.sync_from_card(existing)
                page.update_card_search(card_key, existing.search_text)
            else:
                card = PluginCard(plugin, self._editor)
                card.delete_requested.connect(self._delete_entity)
                page.add_card(card, card.search_text, card_key=card_key)
        page.sync_cards(active_keys)

    def _build_diagnostics(self, page):
        diagnostics = self.snapshot.get("diagnostics") or []
        if isinstance(diagnostics, dict):
            diagnostics = [diagnostics]
        card_key = "diagnostics:tree"
        tree = page.get_card(card_key)
        if tree is None:
            tree = QTreeWidget()
            tree.setHeaderLabels(["级别", "位置", "说明"])
            tree.setRootIsDecorated(False)
            tree.setAlternatingRowColors(True)
            tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
            page.add_card(tree, "诊断 问题", card_key=card_key)
        tree.clear()
        for diagnostic in diagnostics:
            if isinstance(diagnostic, dict):
                level = str(diagnostic.get("severity") or diagnostic.get("level") or "信息")
                file = diagnostic.get("file") or ""
                line = diagnostic.get("line")
                location = f"{file}:{line}" if line is not None else str(file)
                message = str(diagnostic.get("message") or diagnostic.get("source") or diagnostic)
            else:
                level, location, message = "信息", "", str(diagnostic)
            item = QTreeWidgetItem([level, location, message])
            item.setToolTip(2, message)
            tree.addTopLevelItem(item)
        tree.setVisible(bool(diagnostics))
        if not diagnostics:
            page.sync_cards([])
        else:
            page.sync_cards([card_key])

    def _init_shortcuts(self):
        # F5 and Ctrl+R for refresh
        self.shortcut_f5 = QShortcut(QKeySequence(Qt.Key.Key_F5), self)
        self.shortcut_f5.activated.connect(lambda: self.refresh())

        self.shortcut_ctrl_r = QShortcut(QKeySequence("Ctrl+R"), self)
        self.shortcut_ctrl_r.activated.connect(lambda: self.refresh())

        # Ctrl+F to focus search
        self.shortcut_ctrl_f = QShortcut(QKeySequence("Ctrl+F"), self)
        self.shortcut_ctrl_f.activated.connect(lambda: self._focus_search())

        # Esc to clear search / dismiss toast
        self.shortcut_esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.shortcut_esc.activated.connect(lambda: self._handle_escape())

        # Ctrl+S to save active/dirty card
        self.shortcut_ctrl_s = QShortcut(QKeySequence("Ctrl+S"), self)
        self.shortcut_ctrl_s.activated.connect(lambda: self._save_active_card())

        # Ctrl+N to open new keymap card
        self.shortcut_ctrl_n = QShortcut(QKeySequence("Ctrl+N"), self)
        self.shortcut_ctrl_n.activated.connect(lambda: self._open_new_keymap())

        # Ctrl+Z to undo last saved modification
        self.shortcut_ctrl_z = QShortcut(QKeySequence("Ctrl+Z"), self)
        self.shortcut_ctrl_z.activated.connect(lambda: self.undo_last_save())

        # Ctrl+1..4 for rapid category navigation
        self.category_shortcuts = []
        for idx in range(min(len(CATEGORIES), 9)):
            sc = QShortcut(QKeySequence(f"Ctrl+{idx + 1}"), self)
            sc.activated.connect(lambda i=idx: self.category_list.setCurrentRow(i))
            self.category_shortcuts.append(sc)

        # Ctrl+= / Ctrl++ / Ctrl+- / Ctrl+0 for global UI zoom scaling
        self.shortcut_zoom_in = QShortcut(QKeySequence("Ctrl+="), self)
        self.shortcut_zoom_in.activated.connect(lambda: ThemeManager.instance().zoom_in())
        self.shortcut_zoom_in_plus = QShortcut(QKeySequence("Ctrl++"), self)
        self.shortcut_zoom_in_plus.activated.connect(lambda: ThemeManager.instance().zoom_in())
        self.shortcut_zoom_out = QShortcut(QKeySequence("Ctrl+-"), self)
        self.shortcut_zoom_out.activated.connect(lambda: ThemeManager.instance().zoom_out())
        self.shortcut_zoom_reset = QShortcut(QKeySequence("Ctrl+0"), self)
        self.shortcut_zoom_reset.activated.connect(lambda: ThemeManager.instance().reset_zoom())

    def _clear_search(self):
        self.search.clear()
        self.search.setFocus()

    def _focus_search(self):
        self.search.setFocus()
        self.search.selectAll()

    def _handle_escape(self):
        if self.search.text():
            self._clear_search()
        elif hasattr(self, "notification_banner") and self.notification_banner.isVisible():
            self.notification_banner.dismiss()
        else:
            focused = QApplication.focusWidget()
            if focused:
                focused.clearFocus()

    def _save_active_card(self):
        savable_types = (NewKeymapCard, NewPluginCard, KeymapCard, FieldEditor, PluginCard)
        focused = QApplication.focusWidget()
        target_card = None
        if focused is not None:
            w = focused
            while w is not None and w is not self:
                if isinstance(w, savable_types):
                    target_card = w
                    break
                w = w.parent()

        if target_card is not None and getattr(target_card, "dirty", False):
            target_card.save()
            return

        current_page = self.stack.currentWidget()
        if current_page:
            for card in current_page.findChildren((NewKeymapCard, NewPluginCard, KeymapCard, FieldEditor)):
                if getattr(card, "dirty", False):
                    card.save()
                    self.show_notification(f"已触发保存：{getattr(card, 'title', '配置项')}", level="info", duration_ms=2000)
                    return

        self.show_notification("当前没有待保存的修改", level="info", duration_ms=2000)

    def show_notification(self, text, level="info", duration_ms=4000, action_text=None, on_action=None):
        if hasattr(self, "notification_banner"):
            self.notification_banner.show_message(text, level, duration_ms, action_text, on_action)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "notification_banner"):
            self.notification_banner.reposition()

    def _open_new_keymap(self):
        idx = self.category_list.currentRow()
        if idx == 2 and hasattr(self.plugin_page, "open_new_card"):
            self.plugin_page.open_new_card()
        else:
            self.category_list.setCurrentRow(1)
            if hasattr(self.keymap_page, "open_new_card"):
                self.keymap_page.open_new_card()

    def _create_keymap(self, mode, lhs, rhs, opts, editor):
        self.statusBar().showMessage(f"正在添加{editor.title}…")
        self.client.create_keymap(mode, lhs, rhs, opts, editor)

    def _create_plugin(self, payload, editor):
        self.statusBar().showMessage(f"正在添加{editor.title}…")
        self.client.create_plugin(payload, editor)

    def _delete_entity(self, field, card):
        title = getattr(card, "title", None) or getattr(card, "name", None) or "配置项"
        self.statusBar().showMessage(f"正在删除 {title}…")
        self.client.delete_entity(field, {"action": "delete", "card": card, "title": title, "field": field})

    def _rollback_last_change(self, file_path=None):
        self.statusBar().showMessage("正在从备份快照恢复配置…")
        self.client.rollback(file_path=file_path, context={"action": "rollback", "title": "配置回滚"})

    def _save_entity(self, field, value, editor):
        if not isinstance(field, dict):
            self.statusBar().showMessage("保存失败：当前配置缺少写入位置", 8000)
            editor.save_failed("保存失败")
            return
        if field.get("create_option"):
            self.statusBar().showMessage(f"正在添加{editor.title}…")
            self.client.create_option(field["create_option"], value, editor)
            return
        if (
            field.get("id") is not None
            and "value" in field
            and not getattr(editor, "_is_undoing", False)
            and field.get("value") != value
        ):
            self._undo_stack.append(
                {
                    "field_id": field.get("id"),
                    "old_value": copy.deepcopy(field.get("value")),
                    "new_value": copy.deepcopy(value),
                    "editor": editor,
                    "title": getattr(editor, "title", "配置项"),
                }
            )
            if len(self._undo_stack) > 30:
                self._undo_stack.pop(0)
        setattr(editor, "_is_undoing", False)
        self.statusBar().showMessage(f"正在保存{editor.title}…")
        self.client.patch(field, value, editor)

    def _save_entities_batch(self, items, editor):
        if not items:
            return
        self.statusBar().showMessage(f"正在批量保存{getattr(editor, 'title', '配置项')}…")
        self.client.patch_batch(items, editor)

    def undo_last_save(self) -> bool:
        if not self._undo_stack:
            self.show_notification("当前没有可撤销的修改记录", level="info", duration_ms=2000)
            return False
        entry = self._undo_stack.pop()
        field_id = entry.get("field_id")
        old_val = entry.get("old_value")
        editor = entry.get("editor")
        title = entry.get("title", "配置项")
        fields = self._fields_by_id()
        target_field = fields.get(field_id) or (getattr(editor, "field", None) if editor is not None else None)
        if not isinstance(target_field, dict) or target_field.get("id") is None:
            self.show_notification(f"无法撤销 {title}：未找到配置项最新版本", level="warning", duration_ms=3000)
            return False
        if isinstance(editor, FieldEditor):
            setattr(editor, "_is_undoing", True)
            editor.set_editor_value(old_val)
            editor.saving = True
            editor._submitted_value = copy.deepcopy(old_val)
            editor._submitted_revision = target_field.get("revision")
            editor._refresh_state()
        self.statusBar().showMessage(f"正在撤销 {title} 的修改…", 4000)
        self.client.patch(target_field, old_val, editor)
        return True

    def _patch_received(self, result, editor):
        if isinstance(editor, dict) and editor.get("action") in ("delete", "rollback"):
            action = editor.get("action")
            title = editor.get("title", "配置项")
            if result is None:
                feedback = "删除失败，请检查后重试" if action == "delete" else "回滚失败，请检查后重试"
                self.statusBar().showMessage(f"{title}：{feedback}", 7000)
                self.show_notification(f"{title}：{feedback}", level="error", duration_ms=5000)
                QTimer.singleShot(80, self.client.get_state)
                return
            feedback = "已删除并备份" if action == "delete" else "已从备份恢复配置"
            self.statusBar().showMessage(f"{title}：{feedback}", 7000)
            if action == "delete":
                file_path = (editor.get("field") or {}).get("file")
                self.show_notification(
                    f"{title}：{feedback}",
                    level="success",
                    duration_ms=5000,
                    action_text="撤销删除",
                    on_action=lambda fp=file_path: self._rollback_last_change(fp),
                )
            else:
                self.show_notification(f"{title}：{feedback}", level="success", duration_ms=3500)
            QTimer.singleShot(80, self.client.get_state)
            return

        if result is None:
            try:
                feedback = "添加失败，请检查后重试" if editor.creation else "保存失败，请检查连接后重试"
                editor.save_failed(feedback)
                self.show_notification(f"{editor.title}：{feedback}", level="error", duration_ms=5000)
            except RuntimeError:
                pass
            QTimer.singleShot(80, self.client.get_state)
            return
        try:
            disk_saved = result.get("disk_saved")
            applied = bool((result.get("runtime") or {}).get("applied"))
            if disk_saved and applied:
                feedback = "已保存并生效"
            elif disk_saved:
                feedback = "已保存，重启后生效"
            else:
                feedback = "保存失败：配置未写入"
                editor.save_failed(feedback)
                self.statusBar().showMessage(feedback, 9000)
                self.show_notification(f"{editor.title}：{feedback}", level="error", duration_ms=5000)
                return
            editor.save_succeeded(feedback)
            self.statusBar().showMessage(f"{editor.title}：{feedback}", 7000)
            if getattr(editor, "auto_save", False) and self._undo_stack:
                self.show_notification(
                    f"{editor.title}：{feedback}",
                    level="success",
                    duration_ms=3500,
                    action_text="撤销 (Ctrl+Z)",
                    on_action=self.undo_last_save,
                )
            else:
                self.show_notification(f"{editor.title}：{feedback}", level="success", duration_ms=3500)
        except RuntimeError:
            return
        QTimer.singleShot(80, self.client.get_state)

    def get_unsaved_cards(self, page=None, all_pages=False):
        if all_pages:
            targets = self.pages
        else:
            current = page if page is not None else self.stack.currentWidget()
            if current is None or current is self.offline_hero:
                return []
            targets = [current]
        unsaved = []
        for target in targets:
            for card in target.findChildren((NewKeymapCard, NewPluginCard, KeymapCard, FieldEditor)):
                if isinstance(card, FieldEditor):
                    if card.dirty and not card.saving and (not card.auto_save or card.creation):
                        unsaved.append(card)
                else:
                    if getattr(card, "dirty", False) and not getattr(card, "saving", False):
                        unsaved.append(card)
        return unsaved

    def has_unsaved_changes(self, page=None, all_pages=False) -> bool:
        return len(self.get_unsaved_cards(page=page, all_pages=all_pages)) > 0

    def _check_unsaved_guard(self, action_name="切换分类", all_pages=False) -> bool:
        if not getattr(self, "unsaved_guard_enabled", True) or self._closing:
            return True
        unsaved = self.get_unsaved_cards(all_pages=all_pages)
        if not unsaved:
            return True

        policy = getattr(self, "unsaved_guard_policy", "prompt")
        if policy in ("save", "discard", "cancel", "allow"):
            decision = policy
        elif callable(getattr(self, "unsaved_guard_handler", None)):
            decision = self.unsaved_guard_handler(unsaved, action_name)
        elif os.environ.get("QT_QPA_PLATFORM") != "offscreen":
            titles = "、".join(getattr(c, "title", "配置项") for c in unsaved[:3])
            if len(unsaved) > 3:
                titles += f" 等 {len(unsaved)} 项"
            msg = QMessageBox(self)
            msg.setWindowTitle("未保存的修改")
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setText(f"当前有未保存的修改（{titles}），是否在{action_name}前保存？")
            save_btn = msg.addButton("保存修改", QMessageBox.ButtonRole.AcceptRole)
            discard_btn = msg.addButton("放弃修改", QMessageBox.ButtonRole.DestructiveRole)
            msg.addButton("取消", QMessageBox.ButtonRole.RejectRole)
            msg.setDefaultButton(save_btn)
            msg.exec()
            clicked = msg.clickedButton()
            if clicked == save_btn:
                decision = "save"
            elif clicked == discard_btn:
                decision = "discard"
            else:
                decision = "cancel"
        else:
            decision = "allow"

        if decision == "cancel":
            return False
        if decision == "save":
            for card in unsaved:
                card.save()
        elif decision == "discard":
            for card in unsaved:
                if hasattr(card, "discard_changes"):
                    card.discard_changes()
        return True

    def _refresh_nav_icons(self):
        palette = ThemeManager.instance().palette
        active_row = self.category_list.currentRow()
        on_secondary = palette.get("md_on_secondary_container", palette.get("accent_blue", "#89b4fa"))
        inactive_col = palette.get("text_secondary", "#9aa0a6")
        for i in range(self.category_list.count()):
            item = self.category_list.item(i)
            if item is not None:
                col = on_secondary if i == active_row else inactive_col
                item.setIcon(_make_md3_nav_icon(i, col))

    def _category_changed(self, index):
        if index < 0 or index >= len(self.pages):
            return
        if index != self._active_category_index:
            if not self._check_unsaved_guard("切换分类"):
                with QSignalBlocker(self.category_list):
                    self.category_list.setCurrentRow(self._active_category_index)
                return
            self._active_category_index = index
        self._refresh_nav_icons()
        self._ensure_page_rendered(index)
        self.stack.setCurrentIndex(index)
        self._filter_current()

    def _on_search_edited(self, _text):
        self.search_debounce.start(150)

    def _on_search_changed(self, _text):
        if not self.search_debounce.isActive():
            self._filter_current()

    def _filter_current(self, *args):
        del args
        index = self.stack.currentIndex()
        if index >= len(self.pages):
            return
        self._ensure_page_rendered(index)
        if index == 3:
            if self.search.text().strip() and len(self.all_options_page._cards) < len(self.schema_options):
                self._build_all_options(self.all_options_page)
                self.all_options_page.finish()
            for page in (self.all_options_page, self.globals_page, self.diagnostics_page):
                page.apply_filter(self.search.text())
        else:
            self.pages[index].apply_filter(self.search.text())

    def _on_scale_selected(self, index):
        scale_val = self.scale_selector.itemData(index)
        if scale_val is None:
            return
        applied = ThemeManager.instance().set_ui_scale(float(scale_val))
        self.statusBar().showMessage(f"界面缩放已调整为 {int(round(applied * 100))}%", 3000)

    def _on_scale_changed_external(self, scale_val: float):
        idx = self.scale_selector.findData(round(float(scale_val), 2))
        if idx >= 0 and self.scale_selector.currentIndex() != idx:
            with QSignalBlocker(self.scale_selector):
                self.scale_selector.setCurrentIndex(idx)

    def set_ui_scale(self, scale: float) -> float:
        return ThemeManager.instance().set_ui_scale(scale)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                ThemeManager.instance().zoom_in()
                event.accept()
                return
            elif delta < 0:
                ThemeManager.instance().zoom_out()
                event.accept()
                return
        super().wheelEvent(event)

    def _on_theme_selected(self, index):
        theme_key = self.theme_selector.itemData(index)
        if not theme_key:
            return
        if ThemeManager.instance().set_theme(theme_key):
            palette = ThemeManager.instance().palette
            theme_name = palette.get("name", theme_key)
            self.statusBar().showMessage(f"已切换主题：{theme_name}", 3500)

    def _on_theme_changed_external(self, theme_key, _palette):
        idx = self.theme_selector.findData(theme_key)
        if idx >= 0 and self.theme_selector.currentIndex() != idx:
            with QSignalBlocker(self.theme_selector):
                self.theme_selector.setCurrentIndex(idx)
        self._refresh_nav_icons()

    def set_theme(self, theme_key: str) -> bool:
        return ThemeManager.instance().set_theme(theme_key)

    def closeEvent(self, event):
        if not self._check_unsaved_guard("关闭窗口", all_pages=True):
            event.ignore()
            return
        self._closing = True
        self.client.stop_events()
        self.deleteLater()
        super().closeEvent(event)


def apply_dark_theme(app):
    ThemeManager.instance().apply_theme(app)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Neovim 原生 Qt 设置界面")
    parser.add_argument("--url", default="http://127.0.0.1:37777", help="后端服务地址")
    parser.add_argument("--token", default="", help="API Bearer token")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    app = QApplication(sys.argv if argv is None else [sys.argv[0]])
    apply_dark_theme(app)
    window = MainWindow(args.url, args.token)
    window.show()
    window.start()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
