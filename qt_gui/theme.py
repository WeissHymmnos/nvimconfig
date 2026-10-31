"""
Multi-Theme Engine Module for Neovim Config Manager (PyQt6).

Provides:
- PALETTES / THEMES: 6 curated Neovim color palettes (Tokyo Night, Catppuccin Mocha,
  Gruvbox Dark, Kanagawa Wave, Nord, Tokyo Night Day).
- THEME_CHOICES: Ordered (theme_key, display_name) pairs for UI selectors.
- TOKYO_NIGHT / TOKYO_NIGHT_QSS / apply_tokyo_night_theme(app): Backwards-compatible exports.
- build_theme_qss(palette): Dynamic QSS stylesheet compiler from semantic tokens.
- ThemeManager: Singleton QObject managing active theme, QSettings persistence, and live reload.
"""

import re
from PyQt6.QtCore import QObject, QSettings, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPalette
from PyQt6.QtWidgets import QApplication

# ---------------------------------------------------------------------------
# 1. Tokyo Night Color Palette Tokens (Default Dark Theme)
# ---------------------------------------------------------------------------
TOKYO_NIGHT = {
    "name": "Tokyo Night",
    "is_light": False,
    # Backgrounds & Surfaces
    "bg_dark": "#16161e",          # Deepest background (main window, status bar, base inputs)
    "bg": "#1a1b26",               # Main surface / canvas (sidebar panel, tab bar, header)
    "bg_card": "#1f2335",          # Card containers, popups, combo view background
    "bg_highlight": "#24283b",     # Hover states, active category, groove track
    "bg_button_hover": "#2f3549",  # Button hover surface
    "bg_selected": "#283457",      # Selection background in text / lists / trees
    "bg_card_inner": "#16161e",    # Nested setting cards within group cards

    # Borders & Dividers
    "border_dark": "#24283b",      # Subtle dividers, splitter handle, status bar border
    "border": "#292e42",           # Standard card border, input border, tab pane border
    "border_highlight": "#3b4261", # Hover border, active card border
    "border_focus": "#7aa2f7",     # Focus border for inputs and selections

    # Text & Typography
    "fg": "#c0caf5",               # Primary text (soft, low-fatigue lavender/slate)
    "fg_bright": "#ffffff",        # High-contrast text on bright backgrounds
    "fg_heading": "#7aa2f7",       # Primary section headings and active category
    "fg_sub": "#9aa5ce",           # Subtitles and category unselected text
    "fg_muted": "#7982a9",         # Secondary descriptions, hints, status messages
    "fg_gutter": "#565f89",        # Technical identifiers, disabled items, placeholders
    "fg_on_accent": "#15161e",     # Text color on accent buttons

    # Accent & Functional Colors
    "blue": "#7aa2f7",             # Neovim blue accent (primary buttons, active sliders, tabs)
    "blue_hover": "#89b4fa",       # Accent hover
    "blue_pressed": "#3d59a1",     # Accent pressed
    "cyan": "#7dcfff",             # Packer badge, info highlights, links
    "green": "#9ece6a",            # Success, connection online, vim-plug badge, saved status
    "yellow": "#e0af68",           # Warning, offline status, group titles
    "orange": "#ff9e64",           # Numeric parameters, special badges
    "red": "#f7768e",              # Error, conflict warning, danger button
    "red_hover": "#ff92aa",        # Danger button hover
    "red_pressed": "#c53b53",      # Danger button pressed
    "purple": "#bb9af7",           # Lazy.nvim badge, keywords, collapsible toggles
    "teal": "#73daca",             # Plug alternate badge

    # Badges (Background, Border, Foreground)
    "badge_lazy_bg": "#2d2244",
    "badge_lazy_border": "#4d3770",
    "badge_lazy_fg": "#bb9af7",

    "badge_packer_bg": "#1e2c38",
    "badge_packer_border": "#2b5066",
    "badge_packer_fg": "#7dcfff",

    "badge_plug_bg": "#1a302a",
    "badge_plug_border": "#2a5749",
    "badge_plug_fg": "#73daca",

    # Chips & Notification Banners
    "chip_accent_bg": "#202b40",
    "chip_accent_border": "#3b5275",
    "chip_warn_bg": "#382c20",
    "chip_warn_border": "#6b4e28",
    "toast_success_bg": "#1a2b27",
    "toast_warn_bg": "#2e2619",
    "toast_error_bg": "#341c24",
}

# ---------------------------------------------------------------------------
# 2. Catppuccin Mocha Palette
# ---------------------------------------------------------------------------
CATPPUCCIN_MOCHA = {
    "name": "Catppuccin Mocha",
    "is_light": False,
    "bg_dark": "#11111b",
    "bg": "#181825",
    "bg_card": "#1e1e2e",
    "bg_highlight": "#313244",
    "bg_button_hover": "#3b3d54",
    "bg_selected": "#45475a",
    "bg_card_inner": "#11111b",

    "border_dark": "#313244",
    "border": "#45475a",
    "border_highlight": "#585b70",
    "border_focus": "#89b4fa",

    "fg": "#cdd6f4",
    "fg_bright": "#ffffff",
    "fg_heading": "#89b4fa",
    "fg_sub": "#bac2de",
    "fg_muted": "#a6adc8",
    "fg_gutter": "#6c7086",
    "fg_on_accent": "#11111b",

    "blue": "#89b4fa",
    "blue_hover": "#b4befe",
    "blue_pressed": "#74c7ec",
    "cyan": "#89dceb",
    "green": "#a6e3a1",
    "yellow": "#f9e2af",
    "orange": "#fab387",
    "red": "#f38ba8",
    "red_hover": "#f5c2e7",
    "red_pressed": "#eba0ac",
    "purple": "#cba6f7",
    "teal": "#94e2d5",

    "badge_lazy_bg": "#2a1e38",
    "badge_lazy_border": "#513670",
    "badge_lazy_fg": "#cba6f7",

    "badge_packer_bg": "#182a3a",
    "badge_packer_border": "#254866",
    "badge_packer_fg": "#89dceb",

    "badge_plug_bg": "#1c2e24",
    "badge_plug_border": "#2c543f",
    "badge_plug_fg": "#a6e3a1",

    "chip_accent_bg": "#1e293b",
    "chip_accent_border": "#3b5275",
    "chip_warn_bg": "#362c22",
    "chip_warn_border": "#6b5330",
    "toast_success_bg": "#192b24",
    "toast_warn_bg": "#30281c",
    "toast_error_bg": "#321c26",
}

# ---------------------------------------------------------------------------
# 3. Gruvbox Dark Palette
# ---------------------------------------------------------------------------
GRUVBOX_DARK = {
    "name": "Gruvbox Dark",
    "is_light": False,
    "bg_dark": "#1d2021",
    "bg": "#282828",
    "bg_card": "#32302f",
    "bg_highlight": "#3c3836",
    "bg_button_hover": "#504945",
    "bg_selected": "#504945",
    "bg_card_inner": "#1d2021",

    "border_dark": "#3c3836",
    "border": "#504945",
    "border_highlight": "#665c54",
    "border_focus": "#83a598",

    "fg": "#ebdbb2",
    "fg_bright": "#fbf1c7",
    "fg_heading": "#fabd2f",
    "fg_sub": "#d5c4a1",
    "fg_muted": "#a89984",
    "fg_gutter": "#7c6f64",
    "fg_on_accent": "#1d2021",

    "blue": "#83a598",
    "blue_hover": "#8ec07c",
    "blue_pressed": "#458588",
    "cyan": "#8ec07c",
    "green": "#b8bb26",
    "yellow": "#fabd2f",
    "orange": "#fe8019",
    "red": "#fb4934",
    "red_hover": "#ff6c5c",
    "red_pressed": "#cc241d",
    "purple": "#d3869b",
    "teal": "#8ec07c",

    "badge_lazy_bg": "#332630",
    "badge_lazy_border": "#5a3a52",
    "badge_lazy_fg": "#d3869b",

    "badge_packer_bg": "#253232",
    "badge_packer_border": "#3b5555",
    "badge_packer_fg": "#83a598",

    "badge_plug_bg": "#2b3323",
    "badge_plug_border": "#4a5935",
    "badge_plug_fg": "#b8bb26",

    "chip_accent_bg": "#263334",
    "chip_accent_border": "#458588",
    "chip_warn_bg": "#3c301e",
    "chip_warn_border": "#7c5c26",
    "toast_success_bg": "#28301d",
    "toast_warn_bg": "#382c1a",
    "toast_error_bg": "#3c1f1e",
}

# ---------------------------------------------------------------------------
# 4. Kanagawa Wave Palette
# ---------------------------------------------------------------------------
KANAGAWA_WAVE = {
    "name": "Kanagawa Wave",
    "is_light": False,
    "bg_dark": "#16161d",
    "bg": "#1f1f28",
    "bg_card": "#2a2a37",
    "bg_highlight": "#363646",
    "bg_button_hover": "#434358",
    "bg_selected": "#2d4f67",
    "bg_card_inner": "#16161d",

    "border_dark": "#2a2a37",
    "border": "#363646",
    "border_highlight": "#54546d",
    "border_focus": "#7e9cd8",

    "fg": "#dcd7ba",
    "fg_bright": "#ffffff",
    "fg_heading": "#7e9cd8",
    "fg_sub": "#c8c093",
    "fg_muted": "#938aa9",
    "fg_gutter": "#727169",
    "fg_on_accent": "#16161d",

    "blue": "#7e9cd8",
    "blue_hover": "#7fb4ca",
    "blue_pressed": "#223249",
    "cyan": "#7fb4ca",
    "green": "#98bb6c",
    "yellow": "#e6c384",
    "orange": "#ffa066",
    "red": "#e46876",
    "red_hover": "#ff8593",
    "red_pressed": "#c34043",
    "purple": "#957fb8",
    "teal": "#7aa89f",

    "badge_lazy_bg": "#282438",
    "badge_lazy_border": "#473d66",
    "badge_lazy_fg": "#957fb8",

    "badge_packer_bg": "#202d33",
    "badge_packer_border": "#35505b",
    "badge_packer_fg": "#7fb4ca",

    "badge_plug_bg": "#222e23",
    "badge_plug_border": "#39523c",
    "badge_plug_fg": "#98bb6c",

    "chip_accent_bg": "#223249",
    "chip_accent_border": "#3e5b82",
    "chip_warn_bg": "#362e23",
    "chip_warn_border": "#6b5735",
    "toast_success_bg": "#1f2d21",
    "toast_warn_bg": "#332a1d",
    "toast_error_bg": "#361e24",
}

# ---------------------------------------------------------------------------
# 5. Nord Palette
# ---------------------------------------------------------------------------
NORD = {
    "name": "Nord",
    "is_light": False,
    "bg_dark": "#242933",
    "bg": "#2e3440",
    "bg_card": "#3b4252",
    "bg_highlight": "#434c5e",
    "bg_button_hover": "#4c566a",
    "bg_selected": "#4c566a",
    "bg_card_inner": "#242933",

    "border_dark": "#3b4252",
    "border": "#434c5e",
    "border_highlight": "#4c566a",
    "border_focus": "#88c0d0",

    "fg": "#d8dee9",
    "fg_bright": "#eceff4",
    "fg_heading": "#88c0d0",
    "fg_sub": "#e5e9f0",
    "fg_muted": "#9aa5ce",
    "fg_gutter": "#616e88",
    "fg_on_accent": "#2e3440",

    "blue": "#88c0d0",
    "blue_hover": "#8fbcbb",
    "blue_pressed": "#5e81ac",
    "cyan": "#8fbcbb",
    "green": "#a3be8c",
    "yellow": "#ebcb8b",
    "orange": "#d08770",
    "red": "#bf616a",
    "red_hover": "#d07880",
    "red_pressed": "#9a454d",
    "purple": "#b48ead",
    "teal": "#8fbcbb",

    "badge_lazy_bg": "#362f3f",
    "badge_lazy_border": "#584869",
    "badge_lazy_fg": "#b48ead",

    "badge_packer_bg": "#2b3b42",
    "badge_packer_border": "#3f5c69",
    "badge_packer_fg": "#88c0d0",

    "badge_plug_bg": "#2d3a33",
    "badge_plug_border": "#435d4e",
    "badge_plug_fg": "#a3be8c",

    "chip_accent_bg": "#2e3f4f",
    "chip_accent_border": "#5e81ac",
    "chip_warn_bg": "#3d372e",
    "chip_warn_border": "#7a684b",
    "toast_success_bg": "#29362e",
    "toast_warn_bg": "#3b3426",
    "toast_error_bg": "#3b272c",
}

# ---------------------------------------------------------------------------
# 6. Tokyo Night Day Palette (High-Contrast Light Mode)
# ---------------------------------------------------------------------------
TOKYO_NIGHT_DAY = {
    "name": "Tokyo Night Day (浅色)",
    "is_light": True,
    "bg_dark": "#e6e7ed",
    "bg": "#eef0f6",
    "bg_card": "#ffffff",
    "bg_highlight": "#dfe2ec",
    "bg_button_hover": "#d2d6e4",
    "bg_selected": "#c8d3f5",
    "bg_card_inner": "#f4f5f9",

    "border_dark": "#d0d3df",
    "border": "#c1c5d4",
    "border_highlight": "#949cbe",
    "border_focus": "#2e64d2",

    "fg": "#1f2335",
    "fg_bright": "#0f111a",
    "fg_heading": "#2e59a8",
    "fg_sub": "#3b4261",
    "fg_muted": "#565f89",
    "fg_gutter": "#787fa0",
    "fg_on_accent": "#ffffff",

    "blue": "#2e64d2",
    "blue_hover": "#1d52bf",
    "blue_pressed": "#143d94",
    "cyan": "#006a8e",
    "green": "#386b18",
    "yellow": "#8f5e15",
    "orange": "#b15c00",
    "red": "#d22d56",
    "red_hover": "#e43d67",
    "red_pressed": "#a81c40",
    "purple": "#7847bd",
    "teal": "#117a65",

    "badge_lazy_bg": "#f2ecfc",
    "badge_lazy_border": "#cdb4f6",
    "badge_lazy_fg": "#673ab7",

    "badge_packer_bg": "#e3f2fa",
    "badge_packer_border": "#9fd1eb",
    "badge_packer_fg": "#006a8e",

    "badge_plug_bg": "#e6f4e3",
    "badge_plug_border": "#add6a4",
    "badge_plug_fg": "#2e661e",

    "chip_accent_bg": "#e3ecfa",
    "chip_accent_border": "#9cb9eb",
    "chip_warn_bg": "#f7eedc",
    "chip_warn_border": "#d9bc8c",
    "toast_success_bg": "#e7f5e4",
    "toast_warn_bg": "#f8efd9",
    "toast_error_bg": "#fbe4e9",
}

# ---------------------------------------------------------------------------
# 7. Material Design 3 Baseline Dark (Material You Dark)
# ---------------------------------------------------------------------------
MD3_DARK = {
    "name": "Material You (M3 深色)",
    "is_light": False,
    "bg_dark": "#141218",          # M3 Surface Dim / Surface
    "bg": "#1d1b20",               # M3 Surface Container Low
    "bg_card": "#211f26",          # M3 Surface Container
    "bg_highlight": "#2b2930",     # M3 Surface Container High
    "bg_button_hover": "#36343b",  # M3 Surface Container Highest
    "bg_selected": "#4a4458",      # M3 Secondary Container
    "bg_card_inner": "#141218",    # M3 Surface Container Lowest

    "border_dark": "#2b2930",
    "border": "#49454f",           # M3 Outline Variant
    "border_highlight": "#938f99", # M3 Outline
    "border_focus": "#d0bcff",     # M3 Primary

    "fg": "#e6e0e9",               # M3 On Surface
    "fg_bright": "#ffffff",
    "fg_heading": "#d0bcff",       # M3 Primary
    "fg_sub": "#cac4d0",           # M3 On Surface Variant
    "fg_muted": "#938f99",         # M3 Outline
    "fg_gutter": "#605d66",
    "fg_on_accent": "#381e72",     # M3 On Primary

    "blue": "#d0bcff",             # M3 Primary
    "blue_hover": "#eaddff",
    "blue_pressed": "#4f378b",
    "cyan": "#a8c7fa",
    "green": "#81c995",
    "yellow": "#fdd663",
    "orange": "#fcad70",
    "red": "#f2b8b5",              # M3 Error
    "red_hover": "#f9dedc",
    "red_pressed": "#8c1d18",
    "purple": "#efb8c8",           # M3 Tertiary
    "teal": "#80cbc4",

    "md_secondary_container": "#4a4458",
    "md_on_secondary_container": "#e8def8",
    "md_tertiary_container": "#633b48",
    "md_on_tertiary_container": "#ffd8e4",
    "md_error_container": "#8c1d18",
    "md_on_error_container": "#f9dedc",

    "badge_lazy_bg": "#4f378b",
    "badge_lazy_border": "#6750a4",
    "badge_lazy_fg": "#eaddff",

    "badge_packer_bg": "#004a77",
    "badge_packer_border": "#00639b",
    "badge_packer_fg": "#c2e7ff",

    "badge_plug_bg": "#0f5223",
    "badge_plug_border": "#146c2e",
    "badge_plug_fg": "#c4eed0",

    "chip_accent_bg": "#4a4458",
    "chip_accent_border": "#625b71",
    "chip_warn_bg": "#52401a",
    "chip_warn_border": "#7a5f27",
    "toast_success_bg": "#153822",
    "toast_warn_bg": "#3d2e12",
    "toast_error_bg": "#601410",
}

# ---------------------------------------------------------------------------
# 8. Material Design 3 Baseline Light (Material You Light)
# ---------------------------------------------------------------------------
MD3_LIGHT = {
    "name": "Material You (M3 浅色)",
    "is_light": True,
    "bg_dark": "#f7f2fa",          # M3 Surface Container Low
    "bg": "#f3edf7",               # M3 Surface Container
    "bg_card": "#fef7ff",          # M3 Surface Bright / Card
    "bg_highlight": "#ece6f0",     # M3 Surface Container High
    "bg_button_hover": "#e6e0e9",  # M3 Surface Container Highest
    "bg_selected": "#e8def8",      # M3 Secondary Container
    "bg_card_inner": "#f3edf7",    # M3 Surface Container

    "border_dark": "#e6e0e9",
    "border": "#cac4d0",           # M3 Outline Variant
    "border_highlight": "#79747e", # M3 Outline
    "border_focus": "#6750a4",     # M3 Primary

    "fg": "#1d1b20",               # M3 On Surface
    "fg_bright": "#000000",
    "fg_heading": "#6750a4",       # M3 Primary
    "fg_sub": "#49454f",           # M3 On Surface Variant
    "fg_muted": "#79747e",         # M3 Outline
    "fg_gutter": "#938f99",
    "fg_on_accent": "#ffffff",     # M3 On Primary

    "blue": "#6750a4",             # M3 Primary
    "blue_hover": "#4f378b",
    "blue_pressed": "#381e72",
    "cyan": "#0b57d0",
    "green": "#146c2e",
    "yellow": "#b06000",
    "orange": "#c25100",
    "red": "#b3261e",              # M3 Error
    "red_hover": "#8c1d18",
    "red_pressed": "#601410",
    "purple": "#7d5260",           # M3 Tertiary
    "teal": "#006a6a",

    "md_secondary_container": "#e8def8",
    "md_on_secondary_container": "#1d192b",
    "md_tertiary_container": "#ffd8e4",
    "md_on_tertiary_container": "#31111d",
    "md_error_container": "#f9dedc",
    "md_on_error_container": "#410e0b",

    "badge_lazy_bg": "#eaddff",
    "badge_lazy_border": "#d0bcff",
    "badge_lazy_fg": "#21005d",

    "badge_packer_bg": "#c2e7ff",
    "badge_packer_border": "#7fcfff",
    "badge_packer_fg": "#001d35",

    "badge_plug_bg": "#c4eed0",
    "badge_plug_border": "#6dd58c",
    "badge_plug_fg": "#072711",

    "chip_accent_bg": "#e8def8",
    "chip_accent_border": "#ccc2dc",
    "chip_warn_bg": "#fef0d5",
    "chip_warn_border": "#f0c87a",
    "toast_success_bg": "#e6f4ea",
    "toast_warn_bg": "#fef7e0",
    "toast_error_bg": "#fce8e6",
}

# ---------------------------------------------------------------------------
# Theme Registry & Ordered Choices
# ---------------------------------------------------------------------------
PALETTES = {
    "tokyo_night": TOKYO_NIGHT,
    "md3_dark": MD3_DARK,
    "md3_light": MD3_LIGHT,
    "catppuccin_mocha": CATPPUCCIN_MOCHA,
    "gruvbox_dark": GRUVBOX_DARK,
    "kanagawa": KANAGAWA_WAVE,
    "nord": NORD,
    "tokyo_night_day": TOKYO_NIGHT_DAY,
}
THEMES = PALETTES

THEME_CHOICES = [
    ("tokyo_night", "Tokyo Night (M3 深色)"),
    ("md3_dark", "Material You (M3 深色)"),
    ("md3_light", "Material You (M3 浅色)"),
    ("catppuccin_mocha", "Catppuccin Mocha"),
    ("gruvbox_dark", "Gruvbox Dark"),
    ("kanagawa", "Kanagawa Wave"),
    ("nord", "Nord"),
    ("tokyo_night_day", "Tokyo Night Day (浅色)"),
]

SCALE_CHOICES = [
    (0.85, "85%"),
    (0.9, "90%"),
    (1.0, "100%"),
    (1.1, "110%"),
    (1.25, "125%"),
    (1.4, "140%"),
    (1.5, "150%"),
]


def _resolve_md3_tokens(p: dict) -> dict:
    """Derives full Material Design 3 tonal surface and container roles for any palette."""
    if "md_surface_lowest" in p and "md_secondary_container" in p and "md_outline_variant" in p:
        return p
    t = dict(p)
    t.setdefault("md_surface_lowest", p.get("bg_card_inner", p["bg_dark"]))
    t.setdefault("md_surface_low", p["bg"])
    t.setdefault("md_surface", p["bg_card"])
    t.setdefault("md_surface_high", p["bg_highlight"])
    t.setdefault("md_surface_highest", p.get("bg_button_hover", p["bg_highlight"]))
    t.setdefault("md_outline", p["border_highlight"])
    t.setdefault("md_outline_variant", p["border"])
    t.setdefault("md_primary_container", p["bg_selected"])
    t.setdefault("md_on_primary_container", p["fg_bright"] if not p.get("is_light") else p["fg"])
    t.setdefault("md_secondary_container", p.get("chip_accent_bg", p["bg_selected"]))
    t.setdefault("md_on_secondary_container", p["blue"] if not p.get("is_light") else p["fg_heading"])
    t.setdefault("md_tertiary_container", p["badge_lazy_bg"])
    t.setdefault("md_on_tertiary_container", p["badge_lazy_fg"])
    t.setdefault("md_error_container", p.get("toast_error_bg", p["bg_highlight"]))
    t.setdefault("md_on_error_container", p["red"])
    return t


for _k, _pal in list(PALETTES.items()):
    PALETTES[_k] = _resolve_md3_tokens(_pal)
TOKYO_NIGHT = PALETTES["tokyo_night"]
MD3_DARK = PALETTES["md3_dark"]
MD3_LIGHT = PALETTES["md3_light"]


def build_theme_qss(p: dict, scale: float = 1.0) -> str:
    """
    Compiles the complete Material Design 3 (M3) QSS stylesheet from a semantic theme palette
    dictionary and optional UI zoom scale factor.
    """
    p = _resolve_md3_tokens(p)
    qss = f"""
/* ==========================================================================
   Material Design 3 (M3) Theme for Neovim Config Manager - {p.get("name", "Custom")}
   ========================================================================== */

/* Global Window & M3 Surface Base */
QMainWindow, QWidget#centralWidget, QDialog, QStackedWidget {{
    background-color: {p["bg_dark"]};
    color: {p["fg"]};
    font-family: "Roboto", "Noto Sans CJK SC", "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    font-size: 13px;
}}

QLabel {{
    background: transparent;
    color: {p["fg"]};
}}

/* M3 Top App Bar */
QFrame#topAppBar {{
    background-color: {p["md_surface_low"]};
    border: 1px solid {p["md_outline_variant"]};
    border-radius: 16px;
}}

/* M3 Navigation Drawer Container */
QWidget#sidebarPanel {{
    background-color: {p["md_surface_low"]};
    border: 1px solid {p["md_outline_variant"]};
    border-radius: 16px;
}}

/* --------------------------------------------------------------------------
   Splitter (QSplitter)
   -------------------------------------------------------------------------- */
QSplitter {{
    background: {p["bg_dark"]};
}}

QSplitter::handle {{
    background: transparent;
}}

QSplitter::handle:horizontal {{
    width: 6px;
    margin: 4px 1px;
    border-radius: 3px;
}}

QSplitter::handle:vertical {{
    height: 6px;
    margin: 1px 4px;
    border-radius: 3px;
}}

QSplitter::handle:hover {{
    background: {p["md_outline_variant"]};
}}

QSplitter::handle:pressed {{
    background: {p["blue"]};
}}

/* --------------------------------------------------------------------------
   Scroll Areas & ScrollBars (QScrollArea, QScrollBar)
   -------------------------------------------------------------------------- */
QScrollArea, QWidget#scrollViewport, QWidget#cardsContainer {{
    background-color: {p["bg_dark"]};
    border: none;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 2px 0px;
    border-radius: 4px;
}}

QScrollBar::handle:vertical {{
    background: {p["md_outline_variant"]};
    min-height: 32px;
    border-radius: 4px;
    margin: 1px;
}}

QScrollBar::handle:vertical:hover {{
    background: {p["md_outline"]};
}}

QScrollBar::handle:vertical:pressed {{
    background: {p["blue"]};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
    width: 0px;
    background: none;
    border: none;
}}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    margin: 0px 2px;
    border-radius: 4px;
}}

QScrollBar::handle:horizontal {{
    background: {p["md_outline_variant"]};
    min-width: 32px;
    border-radius: 4px;
    margin: 1px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {p["md_outline"]};
}}

QScrollBar::handle:horizontal:pressed {{
    background: {p["blue"]};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    height: 0px;
    width: 0px;
    background: none;
    border: none;
}}

QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: none;
}}

/* --------------------------------------------------------------------------
   M3 Outlined Text Fields & Inputs (QLineEdit, QSpinBox, QPlainTextEdit)
   -------------------------------------------------------------------------- */
QLineEdit, QSpinBox, QDoubleSpinBox, QPlainTextEdit {{
    background-color: {p["md_surface_lowest"]};
    color: {p["fg"]};
    border: 1px solid {p["md_outline_variant"]};
    border-radius: 8px;
    padding: 6px 12px;
    selection-background-color: {p["bg_selected"]};
    selection-color: {p["fg_bright"]};
}}

QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QPlainTextEdit:hover {{
    border: 1px solid {p["md_outline"]};
    background-color: {p["md_surface_low"]};
}}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QPlainTextEdit:focus {{
    border: 2px solid {p["border_focus"]};
    background-color: {p["bg_card"]};
    padding: 5px 11px;
}}

QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QPlainTextEdit:disabled {{
    background-color: {p["bg_dark"]};
    color: {p["fg_gutter"]};
    border-color: {p["border_dark"]};
}}

/* M3 Stadium Search Bar */
QLineEdit#search {{
    background-color: {p["md_surface_high"]};
    border: 1px solid {p["md_outline_variant"]};
    border-radius: 17px;
    padding: 6px 16px;
    min-height: 22px;
    font-size: 13px;
}}

QLineEdit#search:hover {{
    background-color: {p["md_surface_highest"]};
    border-color: {p["md_outline"]};
}}

QLineEdit#search:focus {{
    border: 2px solid {p["border_focus"]};
    background-color: {p["bg_card"]};
    padding: 5px 15px;
}}

QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    width: 18px;
    background: transparent;
    border: none;
}}

QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{
    background: {p["bg_highlight"]};
}}

/* --------------------------------------------------------------------------
   M3 Slider (QSlider)
   -------------------------------------------------------------------------- */
QSlider {{
    min-height: 26px;
}}

QSlider::groove:horizontal {{
    height: 8px;
    background: {p["md_surface_highest"]};
    border-radius: 4px;
}}

QSlider::sub-page:horizontal {{
    height: 8px;
    background: {p["blue"]};
    border-radius: 4px;
}}

QSlider::sub-page:horizontal:disabled {{
    background: {p["border_highlight"]};
}}

QSlider::add-page:horizontal {{
    height: 8px;
    background: {p["md_surface_highest"]};
    border-radius: 4px;
}}

QSlider::handle:horizontal {{
    background: {p["blue"]};
    border: 2px solid {p["bg_card"]};
    width: 18px;
    height: 18px;
    margin: -5px 0;
    border-radius: 9px;
}}

QSlider::handle:horizontal:hover {{
    background: {p["blue_hover"]};
    border: 2px solid {p["fg_bright"]};
}}

QSlider::handle:horizontal:pressed {{
    background: {p["blue_pressed"]};
}}

QSlider::handle:horizontal:disabled {{
    background: {p["fg_gutter"]};
    border: 2px solid {p["bg_dark"]};
}}

/* --------------------------------------------------------------------------
   M3 Outlined & Tonal Dropdowns (QComboBox)
   -------------------------------------------------------------------------- */
QComboBox {{
    background-color: {p["md_surface_lowest"]};
    color: {p["fg"]};
    border: 1px solid {p["md_outline_variant"]};
    border-radius: 8px;
    padding: 6px 28px 6px 12px;
    font-size: 13px;
    min-height: 20px;
}}

QComboBox#themeSelector, QComboBox#scaleSelector {{
    background-color: {p["md_surface_high"]};
    border: 1px solid {p["md_outline_variant"]};
    border-radius: 16px;
    padding: 5px 12px;
    font-size: 12px;
    font-weight: 600;
}}

QComboBox:hover, QComboBox#themeSelector:hover, QComboBox#scaleSelector:hover {{
    border: 1px solid {p["md_outline"]};
    background-color: {p["md_surface_highest"]};
}}

QComboBox:focus, QComboBox#themeSelector:focus, QComboBox#scaleSelector:focus {{
    border: 1px solid {p["border_focus"]};
}}

QComboBox:on {{
    border-bottom-left-radius: 4px;
    border-bottom-right-radius: 4px;
}}

QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 26px;
    border-left: none;
    border-top-right-radius: 8px;
    border-bottom-right-radius: 8px;
}}

QComboBox::down-arrow {{
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {p["fg_sub"]};
    margin-right: 8px;
}}

QComboBox::down-arrow:hover {{
    border-top-color: {p["fg"]};
}}

QComboBox QAbstractItemView {{
    background-color: {p["md_surface_high"]};
    color: {p["fg"]};
    border: 1px solid {p["md_outline_variant"]};
    border-radius: 12px;
    selection-background-color: {p["md_secondary_container"]};
    selection-color: {p["md_on_secondary_container"]};
    padding: 6px;
    outline: 0;
}}

QComboBox QAbstractItemView::item {{
    min-height: 28px;
    padding: 5px 10px;
    border-radius: 8px;
}}

QComboBox QAbstractItemView::item:hover {{
    background-color: {p["md_surface_highest"]};
    color: {p["fg"]};
}}

QComboBox QAbstractItemView::item:selected {{
    background-color: {p["md_secondary_container"]};
    color: {p["md_on_secondary_container"]};
}}

/* --------------------------------------------------------------------------
   M3 Buttons (Filled, Filled Tonal, Outlined, Text, Icon Pill)
   -------------------------------------------------------------------------- */
QPushButton, QToolButton {{
    background-color: {p["md_secondary_container"]};
    color: {p["md_on_secondary_container"]};
    border: 1px solid transparent;
    border-radius: 16px;
    padding: 6px 16px;
    font-weight: 600;
}}

QPushButton:hover, QToolButton:hover {{
    background-color: {p["md_surface_highest"]};
    border-color: {p["md_outline"]};
    color: {p["fg_bright"]};
}}

QPushButton:pressed, QToolButton:pressed {{
    background-color: {p["bg_selected"]};
    border-color: {p["border_focus"]};
}}

QPushButton:disabled, QToolButton:disabled {{
    background-color: {p["md_surface_low"]};
    border-color: transparent;
    color: {p["fg_gutter"]};
}}

/* M3 Filled Primary Button */
QPushButton#accentButton {{
    background-color: {p["blue"]};
    color: {p.get("fg_on_accent", "#15161e")};
    border: 1px solid {p["blue"]};
    border-radius: 16px;
    padding: 6px 18px;
    font-weight: 600;
}}

QPushButton#accentButton:hover {{
    background-color: {p["blue_hover"]};
    border-color: {p["blue_hover"]};
    color: {p.get("fg_on_accent", "#15161e")};
}}

QPushButton#accentButton:pressed {{
    background-color: {p["blue_pressed"]};
    border-color: {p["blue_pressed"]};
    color: {p["fg_bright"]};
}}

QPushButton#accentButton:disabled {{
    background-color: {p["md_surface_high"]};
    border-color: transparent;
    color: {p["fg_gutter"]};
}}

/* Structured Interaction: Hide clean/unmodified save buttons visually while preserving layout geometry */
QPushButton#accentButton[dirty="false"] {{
    background-color: transparent;
    border-color: transparent;
    color: transparent;
}}

QPushButton#accentButton[dirty="false"]:hover {{
    background-color: {p["md_surface_high"]};
    border-color: {p["md_outline_variant"]};
    color: {p["fg_sub"]};
}}

/* M3 Error / Danger Tonal Button (Subtle tonal container at rest, solid error on hover) */
QPushButton#dangerButton {{
    background-color: {p["md_error_container"]};
    color: {p["md_on_error_container"]};
    border: 1px solid transparent;
    border-radius: 14px;
    padding: 4px 12px;
    font-size: 12px;
    font-weight: 600;
}}

QPushButton#dangerButton:hover {{
    background-color: {p["red"]};
    border-color: {p["red"]};
    color: {p.get("fg_on_accent", "#15161e")};
}}

QPushButton#dangerButton:pressed {{
    background-color: {p.get("red_pressed", p["red"])};
    border-color: {p.get("red_pressed", p["red"])};
    color: {p["fg_bright"]};
}}

/* M3 Compact Tree Toolbar Chip Button */
QPushButton#treeActionChip {{
    background-color: {p["md_surface_high"]};
    color: {p["fg_sub"]};
    border: 1px solid {p["md_outline_variant"]};
    border-radius: 8px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 600;
}}

QPushButton#treeActionChip:hover {{
    background-color: {p["md_secondary_container"]};
    color: {p["md_on_secondary_container"]};
    border-color: {p["md_outline"]};
}}

QPushButton#treeActionChip:disabled {{
    background-color: transparent;
    border-color: {p["border_dark"]};
    color: {p["fg_gutter"]};
}}

QToolButton#actionButton, QPushButton#actionButton {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 14px;
    color: {p["fg_sub"]};
    padding: 4px 10px;
    font-size: 12px;
}}

QToolButton#actionButton:hover, QPushButton#actionButton:hover {{
    background-color: {p["md_surface_high"]};
    border-color: {p["md_outline_variant"]};
    color: {p["fg"]};
}}

QToolButton#sectionToggle, QPushButton#sectionToggle {{
    background-color: {p["md_surface_high"]};
    border: 1px solid {p["md_outline_variant"]};
    border-radius: 12px;
    color: {p["fg_sub"]};
    font-weight: 600;
    font-size: 12px;
    padding: 4px 12px;
}}

QToolButton#sectionToggle:hover, QPushButton#sectionToggle:hover {{
    color: {p["md_on_secondary_container"]};
    background-color: {p["md_secondary_container"]};
    border-color: {p["md_outline"]};
}}

/* --------------------------------------------------------------------------
   Checkboxes & M3 Switches (QCheckBox)
   -------------------------------------------------------------------------- */
QCheckBox {{
    color: {p["fg"]};
    spacing: 8px;
    font-size: 13px;
    font-weight: 500;
}}

QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border: 2px solid {p["md_outline"]};
    border-radius: 4px;
    background-color: transparent;
}}

QCheckBox::indicator:hover {{
    border-color: {p["blue"]};
    background-color: {p["md_surface_high"]};
}}

QCheckBox::indicator:checked {{
    background-color: {p["blue"]};
    border-color: {p["blue"]};
}}

QCheckBox::indicator:disabled {{
    background-color: {p["bg_dark"]};
    border-color: {p["border_dark"]};
}}

QCheckBox#switchWidget::indicator {{
    width: 0px;
    height: 0px;
}}

/* --------------------------------------------------------------------------
   M3 Cards & Tonal Surfaces (settingCard, groupCard, keymapCard)
   -------------------------------------------------------------------------- */
QFrame#settingCard {{
    background-color: {p["bg_card"]};
    border: 1px solid {p["md_outline_variant"]};
    border-radius: 12px;
}}

QFrame#settingCard:hover {{
    border-color: {p["md_outline"]};
    background-color: {p["md_surface_high"]};
}}

QFrame#groupCard {{
    background-color: {p["bg_card"]};
    border: 1px solid {p["md_outline_variant"]};
    border-radius: 16px;
}}

QFrame#groupCard:hover {{
    border-color: {p["md_outline"]};
    background-color: {p["md_surface_high"]};
}}

QFrame#groupCard[selected="true"] {{
    background-color: {p["md_secondary_container"]};
    border: 2px solid {p["blue"]};
    border-radius: 16px;
}}

QFrame#pluginDetailPanel {{
    background-color: {p["md_surface_low"]};
    border-left: 1px solid {p["md_outline_variant"]};
}}

QFrame#pluginDetailHeader {{
    background-color: {p["bg_card"]};
    border: 1px solid {p["md_outline_variant"]};
    border-radius: 16px;
}}

QFrame#m3TonalSwitchBar {{
    background-color: {p["md_surface_lowest"]};
    border: 1px solid {p["md_outline_variant"]};
    border-radius: 12px;
}}

QFrame#inspectorSectionCard {{
    background-color: {p["bg_card"]};
    border: 1px solid {p["md_outline_variant"]};
    border-radius: 16px;
}}

QLabel#inspectorSectionTitle {{
    font-size: 13px;
    font-weight: 700;
    color: {p["fg_heading"]};
}}

QFrame#specPreviewBox {{
    background-color: {p["md_surface_lowest"]};
    border: 1px solid {p["md_outline_variant"]};
    border-radius: 12px;
}}

QLabel#specPreviewCode {{
    color: {p["cyan"]};
    font-size: 12px;
    font-family: "JetBrains Mono", "Fira Code", Consolas, "Courier New", monospace;
}}

QLabel#inspectHintBadge {{
    color: {p["fg_muted"]};
    font-size: 11px;
    font-weight: 600;
}}

QLabel#inspectHintBadge[selected="true"] {{
    color: {p["md_on_secondary_container"]};
    font-weight: 700;
}}

/* M3 KeymapCard styling */
QFrame#keymapCard {{
    background-color: {p["bg_card"]};
    border: 1px solid {p["md_outline_variant"]};
    border-radius: 14px;
}}

QFrame#keymapCard:hover {{
    border-color: {p["md_outline"]};
}}

QLabel#keymapModeBadge {{
    background-color: {p["md_secondary_container"]};
    color: {p["md_on_secondary_container"]};
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 3px 10px;
    font-weight: 700;
    font-size: 11px;
}}

QLabel#newCardBadge[kind="keymap"] {{
    background-color: {p["md_secondary_container"]};
    color: {p["md_on_secondary_container"]};
    border: 1px solid transparent;
    border-radius: 8px;
    font-weight: 700;
    font-size: 12px;
    padding: 3px 8px;
}}

QLabel#newCardBadge[kind="plugin"] {{
    background-color: {p["md_tertiary_container"]};
    color: {p["md_on_tertiary_container"]};
    border: 1px solid transparent;
    border-radius: 8px;
    font-weight: 700;
    font-size: 12px;
    padding: 3px 8px;
}}

QLabel#keymapChordTitle {{
    font-size: 14px;
    font-weight: 700;
    color: {p["cyan"]};
    font-family: "JetBrains Mono", "Fira Code", Consolas, "Courier New", monospace;
}}

QLabel#keymapArrow {{
    color: {p["fg_gutter"]};
    font-size: 13px;
    font-weight: bold;
}}

QLabel#keymapRhsSummary {{
    color: {p["fg"]};
    font-size: 12px;
    font-family: "JetBrains Mono", "Fira Code", Consolas, "Courier New", monospace;
}}

QLabel#keymapDescBadge {{
    background-color: {p["md_surface_high"]};
    color: {p["fg_sub"]};
    border: 1px solid {p["md_outline_variant"]};
    border-radius: 8px;
    padding: 2px 8px;
    font-size: 11px;
}}

QLabel#keymapFieldLabel {{
    color: {p["fg_sub"]};
    font-weight: 600;
    font-size: 12px;
}}

QLabel#keymapStatusLabel {{
    font-size: 12px;
    color: {p["fg_muted"]};
}}

QLabel#keymapStatusLabel[status="muted"] {{
    color: {p["fg_muted"]};
    font-size: 12px;
}}

QLabel#keymapStatusLabel[status="info"] {{
    color: {p["blue"]};
    font-size: 12px;
}}

QLabel#keymapStatusLabel[status="modified"] {{
    color: {p["yellow"]};
    font-size: 12px;
}}

QLabel#keymapStatusLabel[status="saved"] {{
    color: {p["green"]};
    font-size: 12px;
}}

QLabel#keymapStatusLabel[status="error"] {{
    color: {p["red"]};
    font-size: 12px;
}}

/* --------------------------------------------------------------------------
   M3 Type Scale (Headers, Titles & Supporting Text)
   -------------------------------------------------------------------------- */
QLabel#sidebarTitle {{
    font-size: 12px;
    font-weight: 700;
    color: {p["fg_muted"]};
    padding: 8px 14px 4px 14px;
    margin-bottom: 2px;
}}

QLabel#pageHeading {{
    font-size: 16px;
    font-weight: 700;
    color: {p["fg_heading"]};
    padding: 10px 4px 4px 4px;
}}

QLabel#groupTitle {{
    font-size: 15px;
    font-weight: 600;
    color: {p["fg"]};
}}

QLabel#settingTitle {{
    font-size: 13px;
    font-weight: 600;
    color: {p["fg"]};
}}

QLabel#settingDescription {{
    color: {p["fg_sub"]};
    font-size: 12px;
    line-height: 1.4;
}}

QLabel#technicalName {{
    color: {p["fg_gutter"]};
    font-size: 11px;
    font-family: "JetBrains Mono", "Fira Code", Consolas, "Courier New", monospace;
}}

QLabel#saveState {{
    color: {p["green"]};
    font-size: 11px;
    font-weight: 600;
}}

/* M3 Assist Status Pill Chips in Top App Bar */
QLabel#connectionOnline {{
    background-color: {p.get("toast_success_bg", p["md_surface_high"])};
    color: {p["green"]};
    border: 1px solid {p["green"]};
    border-radius: 14px;
    padding: 4px 12px;
    font-weight: 600;
    font-size: 12px;
}}

QLabel#connectionStandby {{
    background-color: {p["md_secondary_container"]};
    color: {p["md_on_secondary_container"]};
    border: 1px solid {p["md_outline_variant"]};
    border-radius: 14px;
    padding: 4px 12px;
    font-weight: 600;
    font-size: 12px;
}}

QLabel#connectionOffline {{
    background-color: {p.get("toast_warn_bg", p["md_surface_high"])};
    color: {p["yellow"]};
    border: 1px solid {p["yellow"]};
    border-radius: 14px;
    padding: 4px 12px;
    font-weight: 600;
    font-size: 12px;
}}

/* --------------------------------------------------------------------------
   M3 Navigation Drawer (QListWidget#categoryList)
   -------------------------------------------------------------------------- */
QListWidget#categoryList {{
    background: transparent;
    border: none;
    outline: none;
}}

QListWidget#categoryList::item {{
    color: {p["fg_sub"]};
    padding: 10px 14px;
    border-radius: 18px;
    margin: 3px 4px;
    font-weight: 500;
    border: 1px solid transparent;
}}

QListWidget#categoryList::item:hover {{
    background-color: {p["md_surface_high"]};
    color: {p["fg"]};
    border: 1px solid transparent;
}}

QListWidget#categoryList::item:selected {{
    background-color: {p["md_secondary_container"]};
    color: {p["md_on_secondary_container"]};
    border: 1px solid {p["md_secondary_container"]};
    font-weight: 700;
}}

/* --------------------------------------------------------------------------
   M3 Primary & Secondary Tabs (QTabWidget, QTabBar)
   -------------------------------------------------------------------------- */
QTabWidget::pane {{
    border: none;
    border-top: 1px solid {p["md_outline_variant"]};
    background-color: {p["bg_dark"]};
    top: -1px;
}}

QTabBar::tab {{
    background-color: transparent;
    color: {p["fg_sub"]};
    padding: 10px 20px;
    border: none;
    border-bottom: 3px solid transparent;
    margin-right: 4px;
    font-weight: 500;
    font-size: 13px;
}}

QTabBar::tab:hover:!selected {{
    background-color: {p["md_surface_high"]};
    color: {p["fg"]};
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}}

QTabBar::tab:selected {{
    background-color: transparent;
    color: {p["blue"]};
    border: none;
    border-bottom: 3px solid {p["blue"]};
    font-weight: 700;
}}

/* --------------------------------------------------------------------------
   M3 Tree / Table Views (QTreeWidget, QHeaderView)
   -------------------------------------------------------------------------- */
QTreeWidget {{
    background-color: {p["md_surface_lowest"]};
    alternate-background-color: {p["md_surface_low"]};
    color: {p["fg"]};
    border: 1px solid {p["md_outline_variant"]};
    border-radius: 12px;
    outline: none;
}}

QTreeWidget::item {{
    padding: 4px 8px;
    min-height: 30px;
}}

QTreeWidget QLineEdit, QTreeWidget QSpinBox, QTreeWidget QDoubleSpinBox {{
    padding: 1px 8px;
    min-height: 24px;
    max-height: 26px;
    border-radius: 6px;
    margin: 1px 2px;
}}

QTreeWidget QCheckBox {{
    background: transparent;
    padding: 2px 6px;
    spacing: 8px;
}}

QPlainTextEdit#luaRawPreview {{
    font-family: "JetBrains Mono", "Fira Code", Consolas, "Courier New", monospace;
    font-size: 12px;
    background-color: {p["md_surface_lowest"]};
    color: {p["cyan"]};
    border: 1px solid {p["md_outline_variant"]};
    border-radius: 12px;
    padding: 8px 10px;
}}

QTreeWidget::item:hover {{
    background-color: {p["md_surface_high"]};
}}

QTreeWidget::item:selected {{
    background-color: {p["md_secondary_container"]};
    color: {p["md_on_secondary_container"]};
}}

QHeaderView::section {{
    background-color: {p["md_surface_low"]};
    color: {p["fg_sub"]};
    font-weight: 600;
    font-size: 12px;
    border: none;
    border-bottom: 1px solid {p["md_outline_variant"]};
    padding: 7px 10px;
}}

/* --------------------------------------------------------------------------
   Status Bar & M3 Rich ToolTip
   -------------------------------------------------------------------------- */
QStatusBar {{
    background-color: {p["bg_dark"]};
    color: {p["fg_muted"]};
    border-top: 1px solid {p["border_dark"]};
    font-size: 12px;
}}

QToolTip {{
    background-color: {p["md_surface_highest"]};
    color: {p["fg"]};
    border: 1px solid {p["md_outline_variant"]};
    border-radius: 8px;
    padding: 6px 10px;
    font-size: 12px;
}}

/* --------------------------------------------------------------------------
   M3 Tonal Badges (Plugin Manager)
   -------------------------------------------------------------------------- */
QLabel#managerBadgeLazy, QLabel#pluginManagerBadge[manager="lazy"] {{
    background-color: {p["badge_lazy_bg"]};
    border: 1px solid {p["badge_lazy_border"]};
    color: {p["badge_lazy_fg"]};
    border-radius: 8px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}}

QLabel#managerBadgePacker, QLabel#pluginManagerBadge[manager="packer"] {{
    background-color: {p["badge_packer_bg"]};
    border: 1px solid {p["badge_packer_border"]};
    color: {p["badge_packer_fg"]};
    border-radius: 8px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}}

QLabel#managerBadgePlug, QLabel#pluginManagerBadge[manager="plug"] {{
    background-color: {p["badge_plug_bg"]};
    border: 1px solid {p["badge_plug_border"]};
    color: {p["badge_plug_fg"]};
    border-radius: 8px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}}

/* --------------------------------------------------------------------------
   M3 Snackbars / Notification Banners
   -------------------------------------------------------------------------- */
QFrame#notificationBanner {{
    border-radius: 14px;
    padding: 10px 16px;
}}

QFrame#notificationBanner[level="info"] {{
    background-color: {p["md_surface_highest"]};
    border: 1px solid {p["blue"]};
}}

QFrame#notificationBanner[level="success"] {{
    background-color: {p.get("toast_success_bg", p["bg_card"])};
    border: 1px solid {p["green"]};
}}

QFrame#notificationBanner[level="warning"] {{
    background-color: {p.get("toast_warn_bg", p["bg_card"])};
    border: 1px solid {p["yellow"]};
}}

QFrame#notificationBanner[level="error"] {{
    background-color: {p.get("toast_error_bg", p["bg_card"])};
    border: 1px solid {p["red"]};
}}

QLabel#notificationIcon {{
    font-size: 15px;
    font-weight: 700;
}}

QLabel#notificationIcon[level="info"] {{
    color: {p["blue"]};
}}

QLabel#notificationIcon[level="success"] {{
    color: {p["green"]};
}}

QLabel#notificationIcon[level="warning"] {{
    color: {p["yellow"]};
}}

QLabel#notificationIcon[level="error"] {{
    color: {p["red"]};
}}

QLabel#notificationMessage {{
    color: {p["fg"]};
    font-size: 13px;
    font-weight: 500;
}}

/* --------------------------------------------------------------------------
   M3 Filter Chip Bar (PluginFilterBar & KeymapPage.top_bar)
   -------------------------------------------------------------------------- */
QFrame#pluginFilterBar {{
    background-color: {p["bg_dark"]};
    border-bottom: 1px solid {p["md_outline_variant"]};
}}

QPushButton#filterTabButton {{
    background-color: transparent;
    color: {p["fg_sub"]};
    border: 1px solid {p["md_outline"]};
    border-radius: 8px;
    padding: 6px 14px;
    font-size: 12px;
    font-weight: 500;
}}

QPushButton#filterTabButton:hover {{
    background-color: {p["md_surface_high"]};
    border-color: {p["fg_sub"]};
    color: {p["fg"]};
}}

QPushButton#filterTabButton[active="true"] {{
    background-color: {p["md_secondary_container"]};
    color: {p["md_on_secondary_container"]};
    border: 1px solid {p["md_secondary_container"]};
    font-weight: 700;
}}

/* --------------------------------------------------------------------------
   M3 Assist Chip Button (Open Repository)
   -------------------------------------------------------------------------- */
QPushButton#openRepoButton {{
    background-color: {p["md_surface_high"]};
    color: {p["cyan"]};
    border: 1px solid {p["md_outline_variant"]};
    border-radius: 14px;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 600;
}}

QPushButton#openRepoButton:hover {{
    background-color: {p["md_secondary_container"]};
    border-color: {p["cyan"]};
    color: {p["fg_bright"]};
}}

QPushButton#openRepoButton:pressed {{
    background-color: {p["bg_card"]};
    color: {p["cyan"]};
}}

QPushButton#openRepoButton:disabled {{
    background-color: transparent;
    border-color: {p["border_dark"]};
    color: {p["fg_gutter"]};
}}

/* --------------------------------------------------------------------------
   M3 Suggestion / Attribute Chips (branch, tag, commit, pin, lazy)
   -------------------------------------------------------------------------- */
QLabel#attributeChip {{
    background-color: {p["md_surface_high"]};
    border: 1px solid {p["md_outline_variant"]};
    color: {p["fg_sub"]};
    border-radius: 8px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 500;
}}

QLabel#attributeChipAccent {{
    background-color: {p["md_secondary_container"]};
    border: 1px solid transparent;
    color: {p["md_on_secondary_container"]};
    border-radius: 8px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}}

QLabel#attributeChipWarn {{
    background-color: {p.get("chip_warn_bg", p["bg_highlight"])};
    border: 1px solid {p.get("chip_warn_border", p["border_highlight"])};
    color: {p["yellow"]};
    border-radius: 8px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}}

/* --------------------------------------------------------------------------
   M3 Hero Card & Empty Search Placeholder
   -------------------------------------------------------------------------- */
QFrame#offlineHeroCard {{
    background-color: {p["bg_dark"]};
}}

QFrame#heroCardInner {{
    background-color: {p["bg_card"]};
    border: 1px solid {p["md_outline_variant"]};
    border-radius: 24px;
}}

QLabel#heroIconLabel {{
    font-size: 44px;
    color: {p["yellow"]};
}}

QLabel#heroTitleLabel {{
    font-size: 18px;
    font-weight: 700;
    color: {p["fg"]};
}}

QLabel#heroSubtitleLabel {{
    font-size: 13px;
    color: {p["fg_sub"]};
    line-height: 1.4;
}}

QFrame#heroDiagBox {{
    background-color: {p["md_surface_lowest"]};
    border: 1px solid {p["md_outline_variant"]};
    border-radius: 12px;
    padding: 10px 14px;
}}

QLabel#heroUrlLabel {{
    font-family: "JetBrains Mono", "Fira Code", Consolas, "Courier New", monospace;
    font-size: 12px;
    color: {p["cyan"]};
}}

QLabel#heroErrorLabel {{
    font-size: 12px;
    color: {p["red"]};
}}

QLabel#heroTipLabel {{
    font-size: 11px;
    color: {p["fg_gutter"]};
}}

QLabel#heroCountdownLabel {{
    font-size: 12px;
    color: {p["fg_muted"]};
}}

QFrame#emptySearchPlaceholder {{
    background-color: transparent;
}}

QLabel#emptySearchIcon {{
    font-size: 32px;
    color: {p["fg_gutter"]};
}}

QLabel#emptySearchTitle {{
    font-size: 14px;
    font-weight: 600;
    color: {p["fg"]};
}}

QLabel#emptySearchQuery {{
    font-size: 12px;
    color: {p["fg_muted"]};
}}
"""
    if abs(scale - 1.0) > 1e-3:
        def _scale_font(match):
            px = int(match.group(1))
            scaled = max(9, int(round(px * scale)))
            return f"font-size: {scaled}px"
        qss = re.sub(r"font-size:\s*(\d+)px", _scale_font, qss)
    return qss


_QSS_CACHE = {}
_PALETTE_OBJ_CACHE = {}

# Backwards-compatible default QSS constant
TOKYO_NIGHT_QSS = build_theme_qss(TOKYO_NIGHT, 1.0)
_QSS_CACHE["tokyo_night"] = TOKYO_NIGHT_QSS
_QSS_CACHE[("tokyo_night", 1.0)] = TOKYO_NIGHT_QSS


def _build_qpalette(p: dict) -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(p["bg_dark"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(p["fg"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(p["bg"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(p["bg_highlight"]))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(p["bg_card"]))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(p["fg"]))
    palette.setColor(QPalette.ColorRole.Text, QColor(p["fg"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(p["bg_highlight"]))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(p["fg"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(p["blue"]))
    palette.setColor(
        QPalette.ColorRole.HighlightedText,
        QColor(p.get("fg_on_accent", p["bg_dark"])),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.WindowText,
        QColor(p["fg_gutter"]),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.Text,
        QColor(p["fg_gutter"]),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.ButtonText,
        QColor(p["fg_gutter"]),
    )
    return palette


class ThemeManager(QObject):
    """Singleton manager for multi-theme switching, UI scaling, QSettings persistence, and live QSS reload."""

    theme_changed = pyqtSignal(str, dict)  # (theme_key, palette_dict)
    scale_changed = pyqtSignal(float)      # (scale_factor)
    _instance = None
    _QSS_CACHE = _QSS_CACHE

    @classmethod
    def instance(cls) -> "ThemeManager":
        if cls._instance is None:
            cls._instance = ThemeManager()
        return cls._instance

    def __init__(self, parent=None):
        super().__init__(parent)
        self._settings = QSettings("NeovimConfig", "Manager")
        saved = str(self._settings.value("theme", "tokyo_night") or "tokyo_night")
        self._current_theme = saved if saved in PALETTES else "tokyo_night"
        try:
            raw_scale = float(self._settings.value("ui_scale", 1.0) or 1.0)
        except (TypeError, ValueError):
            raw_scale = 1.0
        self._ui_scale = max(0.85, min(1.5, round(raw_scale, 2)))

    @property
    def current_theme(self) -> str:
        return self._current_theme

    @property
    def current_scale(self) -> float:
        return self._ui_scale

    @property
    def palette(self) -> dict:
        return PALETTES.get(self._current_theme, TOKYO_NIGHT)

    def available_themes(self) -> list:
        return list(THEME_CHOICES)

    def available_scales(self) -> list:
        return list(SCALE_CHOICES)

    def set_ui_scale(self, scale: float, app: QApplication = None) -> float:
        clamped = max(0.85, min(1.5, round(float(scale), 2)))
        self._ui_scale = clamped
        self._settings.setValue("ui_scale", clamped)
        target_app = app or QApplication.instance()
        if target_app is not None:
            self.apply_theme(target_app, self._current_theme)
        self.scale_changed.emit(self._ui_scale)
        return self._ui_scale

    def zoom_in(self, app: QApplication = None) -> float:
        steps = [s for s, _ in SCALE_CHOICES]
        for s in steps:
            if s > self._ui_scale + 1e-3:
                return self.set_ui_scale(s, app)
        return self.set_ui_scale(steps[-1], app)

    def zoom_out(self, app: QApplication = None) -> float:
        steps = [s for s, _ in reversed(SCALE_CHOICES)]
        for s in steps:
            if s < self._ui_scale - 1e-3:
                return self.set_ui_scale(s, app)
        return self.set_ui_scale(steps[-1], app)

    def reset_zoom(self, app: QApplication = None) -> float:
        return self.set_ui_scale(1.0, app)

    def set_theme(self, theme_key: str, app: QApplication = None) -> bool:
        if theme_key not in PALETTES:
            return False
        self._current_theme = theme_key
        self._settings.setValue("theme", theme_key)

        target_app = app or QApplication.instance()
        if target_app is not None:
            self.apply_theme(target_app, theme_key)

        self.theme_changed.emit(self._current_theme, self.palette)
        return True

    def apply_theme(self, app: QApplication = None, theme_key: str = None):
        if theme_key and theme_key in PALETTES:
            self._current_theme = theme_key
        target_app = app or QApplication.instance()
        if target_app is None:
            return

        p = self.palette
        if not getattr(target_app, "_ucdp_style_initialized", False):
            target_app.setStyle("Fusion")
            target_app._ucdp_style_initialized = True
        base_pt = max(8, int(round(10 * self._ui_scale)))
        if getattr(target_app, "_ucdp_last_font_pt", None) != base_pt:
            target_app.setFont(QFont("Sans Serif", base_pt))
            target_app._ucdp_last_font_pt = base_pt

        palette = _PALETTE_OBJ_CACHE.get(self._current_theme)
        if palette is None:
            palette = _build_qpalette(p)
            _PALETTE_OBJ_CACHE[self._current_theme] = palette

        cache_key = (self._current_theme, round(self._ui_scale, 2))
        qss = _QSS_CACHE.get(cache_key)
        if qss is None:
            qss = build_theme_qss(p, self._ui_scale)
            _QSS_CACHE[cache_key] = qss
        _QSS_CACHE[self._current_theme] = qss

        top_widgets = target_app.topLevelWidgets()
        for w in top_widgets:
            w.setUpdatesEnabled(False)
        try:
            if getattr(target_app, "_ucdp_last_palette_key", None) != self._current_theme:
                target_app.setPalette(palette)
                target_app._ucdp_last_palette_key = self._current_theme
            if getattr(target_app, "_ucdp_last_qss_key", None) != cache_key:
                target_app.setStyleSheet(qss)
                target_app._ucdp_last_qss_key = cache_key
        finally:
            for w in top_widgets:
                w.setUpdatesEnabled(True)
                w.update()


def get_current_palette() -> dict:
    return ThemeManager.instance().palette


def apply_theme(app: QApplication, theme_key: str = None) -> bool:
    mgr = ThemeManager.instance()
    if theme_key:
        return mgr.set_theme(theme_key, app)
    mgr.apply_theme(app)
    return True


def apply_tokyo_night_theme(app: QApplication):
    """
    Backwards-compatible helper: applies the Tokyo Night Dark theme to QApplication.
    """
    ThemeManager.instance().apply_theme(app, "tokyo_night")
