# SPDX-License-Identifier: GPL-3.0-or-later
"""Tema claro/oscuro e íconos vectoriales propios (sin archivos externos)."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

LIGHT = {
    "bg": "#f4f6fa",
    "surface": "#ffffff",
    "surface2": "#eef1f6",
    "border": "#dde2ea",
    "text": "#141a24",
    "muted": "#5b6577",
    "accent": "#6741d9",
    "accent_hover": "#5632c0",
    "accent_text": "#ffffff",
    "accent_soft": "#ece7fb",
    "ok": "#17794a",
    "ok_soft": "#e0f4ea",
    "err": "#b3261e",
    "err_soft": "#fbe6e4",
    "sel": "#e6dffa",
    "warn": "#9a5b00",
}

DARK = {
    "bg": "#10141b",
    "surface": "#181d27",
    "surface2": "#212836",
    "border": "#2b3445",
    "text": "#e8ecf3",
    "muted": "#98a3b6",
    "accent": "#a78bfa",
    "accent_hover": "#bca6fc",
    "accent_text": "#1a1033",
    "accent_soft": "#2a2147",
    "ok": "#58d39a",
    "ok_soft": "#143326",
    "err": "#ff8a80",
    "err_soft": "#3d1a18",
    "sel": "#2f2752",
    "warn": "#f0b45a",
}


def palette(dark: bool) -> dict[str, str]:
    return DARK if dark else LIGHT


_assets: str | None = None


def _asset(name: str, color: str) -> str:
    """Escribe un ícono como PNG temporal (las hojas de estilo de Qt solo aceptan archivos)."""
    global _assets
    if _assets is None:
        import atexit
        import shutil
        import tempfile

        _assets = tempfile.mkdtemp(prefix="music-dlp-")
        atexit.register(shutil.rmtree, _assets, True)
    base = f"{_assets}/{name}-{color.lstrip('#')}"
    for suffix, px in (("", 16), ("@2x", 32)):
        _render(name, color, px, 3).save(f"{base}{suffix}.png")
    return f"{base}.png"


def stylesheet(c: dict[str, str]) -> str:
    check, up, down = _asset("check", c["accent_text"]), _asset("chev_up", c["muted"]), _asset("chev_down", c["muted"])
    return f"""
* {{ font-size: 10.5pt; }}
QWidget#root, QDialog {{ background: {c['bg']}; color: {c['text']}; }}
QLabel {{ color: {c['text']}; background: transparent; }}
QLabel#title {{ font-size: 15pt; font-weight: 700; letter-spacing: -0.3px; }}
QLabel#muted, QLabel#status {{ color: {c['muted']}; }}
QLabel#emptyTitle {{ font-size: 14pt; font-weight: 600; color: {c['text']}; }}
QLabel#emptySub {{ color: {c['muted']}; }}
QLabel#chip {{ border-radius: 12px; padding: 4px 12px; background: {c['surface2']}; color: {c['muted']}; font-weight: 600; }}
QLabel#chip[state="ok"] {{ background: {c['ok_soft']}; color: {c['ok']}; }}
QLabel#msgOk {{ color: {c['ok']}; }}
QLabel#msgErr {{ color: {c['err']}; }}
QLabel#mono {{ font-family: monospace; font-size: 9pt; color: {c['text']}; background: {c['surface2']}; border-radius: 8px; padding: 8px 10px; }}

QFrame#card {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 14px; }}
QFrame#drop {{ background: transparent; border: 2px dashed {c['border']}; border-radius: 14px; }}
QFrame#drop[active="true"] {{ border-color: {c['accent']}; background: {c['accent_soft']}; }}

QPushButton {{
    background: {c['surface']}; color: {c['text']}; border: 1px solid {c['border']};
    border-radius: 10px; padding: 8px 14px; font-weight: 600;
}}
QPushButton:hover {{ background: {c['surface2']}; }}
QPushButton:pressed {{ background: {c['sel']}; }}
QPushButton:disabled {{ color: {c['muted']}; background: {c['surface2']}; border-color: {c['surface2']}; }}
QPushButton:focus {{ border: 2px solid {c['accent']}; padding: 7px 13px; }}
QPushButton#primary {{ background: {c['accent']}; color: {c['accent_text']}; border: 1px solid {c['accent']}; }}
QPushButton#primary:hover {{ background: {c['accent_hover']}; border-color: {c['accent_hover']}; }}
QPushButton#primary:disabled {{ background: {c['surface2']}; color: {c['muted']}; border-color: {c['surface2']}; }}
QPushButton#primary:focus {{ border: 2px solid {c['text']}; }}
QPushButton#flat {{ border: none; background: transparent; padding: 8px 10px; color: {c['muted']}; }}
QPushButton#flat:hover {{ background: {c['surface2']}; color: {c['text']}; }}
QPushButton#flat:focus {{ border: 2px solid {c['accent']}; padding: 6px 8px; }}

QLineEdit {{
    background: {c['surface']}; color: {c['text']}; border: 1px solid {c['border']};
    border-radius: 10px; padding: 8px 10px; selection-background-color: {c['accent']}; selection-color: {c['accent_text']};
}}
QLineEdit:focus {{ border: 2px solid {c['accent']}; padding: 7px 9px; }}

QTreeWidget {{
    background: {c['surface']}; color: {c['text']}; border: none; outline: 0;
    alternate-background-color: {c['surface']};
}}
QTreeWidget::item {{ padding: 9px 6px; border-bottom: 1px solid {c['surface2']}; }}
QTreeWidget::item:hover {{ background: {c['surface2']}; }}
QTreeWidget::item:selected {{ background: {c['sel']}; color: {c['text']}; }}
QHeaderView::section {{
    background: {c['surface']}; color: {c['muted']}; border: none; border-bottom: 1px solid {c['border']};
    padding: 9px 8px; font-weight: 600; font-size: 9.5pt;
}}
QProgressBar {{ background: {c['surface2']}; border: none; border-radius: 3px; max-height: 6px; min-height: 6px; }}
QProgressBar::chunk {{ background: {c['accent']}; border-radius: 3px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {c['muted']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QToolTip {{ background: {c['text']}; color: {c['bg']}; border: none; padding: 5px 8px; border-radius: 6px; }}
QLabel#section {{ font-size: 11.5pt; font-weight: 700; }}
QLabel#hint {{ color: {c['muted']}; font-size: 9.5pt; }}
QLabel a {{ color: {c['accent']}; }}

QTabWidget::pane {{ border: none; top: 0; }}
QTabBar {{ background: transparent; qproperty-drawBase: 0; }}
QTabBar::tab {{
    background: transparent; color: {c['muted']}; border: none; border-bottom: 3px solid transparent;
    padding: 8px 4px; margin: 0 18px 8px 0; font-weight: 700; font-size: 11pt;
}}
QTabBar::tab:hover {{ color: {c['text']}; }}
QTabBar::tab:selected {{ color: {c['text']}; border-bottom-color: {c['accent']}; }}
QTabBar::tab:focus {{ color: {c['accent']}; }}

QPlainTextEdit#console {{
    background: {c['surface']}; color: {c['text']}; border: none; font-family: monospace; font-size: 9.5pt;
    selection-background-color: {c['accent']}; selection-color: {c['accent_text']};
}}
QCheckBox, QRadioButton {{ color: {c['text']}; spacing: 10px; padding: 3px 0; background: transparent; }}
QCheckBox:disabled, QRadioButton:disabled {{ color: {c['muted']}; }}
QCheckBox::indicator, QTreeWidget::indicator {{
    width: 14px; height: 14px; border: 2px solid {c['muted']}; border-radius: 5px; background: {c['surface']};
}}
QCheckBox::indicator:hover, QTreeWidget::indicator:hover, QRadioButton::indicator:hover {{ border-color: {c['accent']}; }}
QCheckBox::indicator:checked, QTreeWidget::indicator:checked {{
    background: {c['accent']}; border-color: {c['accent']}; image: url({check});
}}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{ border-color: {c['border']}; }}
QCheckBox::indicator:checked:disabled {{ background: {c['muted']}; border-color: {c['muted']}; }}
QCheckBox:focus, QRadioButton:focus {{ color: {c['accent']}; }}
QRadioButton::indicator {{
    width: 12px; height: 12px; border: 2px solid {c['muted']}; border-radius: 8px; background: {c['surface']};
}}
QRadioButton::indicator:checked {{ width: 6px; height: 6px; border: 5px solid {c['accent']}; background: {c['accent_text']}; }}
QRadioButton::indicator:checked:disabled {{ border-color: {c['muted']}; }}
QSpinBox, QComboBox {{
    background: {c['surface']}; color: {c['text']}; border: 1px solid {c['border']}; border-radius: 10px;
    padding: 6px 10px; min-height: 22px; font-weight: 600;
}}
QSpinBox {{ padding-right: 26px; min-width: 22px; }}
QSpinBox:focus, QComboBox:focus {{ border: 2px solid {c['accent']}; padding: 5px 9px; }}
QSpinBox:focus {{ padding-right: 25px; }}
QSpinBox:disabled, QComboBox:disabled {{ color: {c['muted']}; background: {c['surface2']}; }}
QSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right; width: 24px; height: 16px; border: none; margin: 3px 3px 0 0; }}
QSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right; width: 24px; height: 16px; border: none; margin: 0 3px 3px 0; }}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{ background: {c['surface2']}; border-radius: 5px; }}
QSpinBox::up-arrow {{ image: url({up}); width: 11px; height: 11px; }}
QSpinBox::down-arrow {{ image: url({down}); width: 11px; height: 11px; }}
QComboBox::drop-down {{ border: none; width: 30px; }}
QComboBox::down-arrow {{ image: url({down}); width: 13px; height: 13px; }}
QComboBox QAbstractItemView {{
    background: {c['surface']}; color: {c['text']}; border: 1px solid {c['border']};
    selection-background-color: {c['sel']}; selection-color: {c['text']}; outline: 0;
}}
QScrollArea, QScrollArea > QWidget > QWidget#page {{ background: transparent; border: none; }}
QSplitter::handle {{ background: transparent; height: 10px; }}
"""


# Íconos propios, trazo de 2 px en una grilla de 24
_ICONS = {
    "add": '<path d="M12 5v14M5 12h14"/>',
    "remove": '<path d="M5 12h14"/>',
    "clear": '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/>',
    "download": '<path d="M12 3v12M7 10l5 5 5-5M5 21h14"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="2"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 3h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "alert": '<path d="M12 4l9 16H3zM12 10v4M12 17.5v.5"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "search": '<circle cx="11" cy="11" r="6"/><path d="M20 20l-4.5-4.5"/>',
    "music": '<path d="M9 18V6l11-2v12"/><circle cx="6" cy="18" r="3"/><circle cx="17" cy="16" r="3"/>',
    "list": '<path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01"/>',
    "copy": '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h9"/>',
    "refresh": '<path d="M20 11a8 8 0 0 0-14.9-3M4 4v4h4M4 13a8 8 0 0 0 14.9 3M20 20v-4h-4"/>',
    "import": '<path d="M3 12h12M10 7l5 5-5 5M20 4v16"/>',
    "cloud": '<path d="M7 18a4 4 0 0 1-.6-7.95A6 6 0 0 1 18 9.5a4.3 4.3 0 0 1-.5 8.5z"/>',
    "shield": '<path d="M12 3l8 3v6c0 4.5-3.2 7.8-8 9-4.8-1.2-8-4.5-8-9V6z"/>',
    "chev_down": '<path d="M6 9l6 6 6-6"/>',
    "chev_up": '<path d="M6 15l6-6 6 6"/>',
    "skip": '<path d="M6 12h12"/><circle cx="12" cy="12" r="9"/>',
}


def _render(name: str, color: str, px: int, width: float = 2) -> QPixmap:
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
        f'stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round">{_ICONS[name]}</svg>'
    )
    pix = QPixmap(QSize(px, px))
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    QSvgRenderer(QByteArray(svg.encode())).render(painter)
    painter.end()
    return pix


def icon(name: str, color: str, size: int = 20, disabled: str | None = None) -> QIcon:
    """Ícono de un color; `disabled` es el color cuando el botón está deshabilitado."""
    result = QIcon()
    for scale in (1, 2):
        pix = _render(name, color, size * scale)
        pix.setDevicePixelRatio(scale)
        result.addPixmap(pix, QIcon.Mode.Normal)
        off = _render(name, disabled or color, size * scale)
        off.setDevicePixelRatio(scale)
        result.addPixmap(off, QIcon.Mode.Disabled)
    return result


_FLAGS = {
    # Bandera del idioma en uso
    "es": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 60 40">'
        '<rect width="60" height="40" fill="#AA151B"/><rect y="10" width="60" height="20" fill="#F1BF00"/></svg>'
    ),
    "en": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 60 40">'
        '<rect width="60" height="40" fill="#012169"/>'
        '<path d="M0 0L60 40M60 0L0 40" stroke="#fff" stroke-width="8"/>'
        '<path d="M0 0L60 40M60 0L0 40" stroke="#C8102E" stroke-width="3"/>'
        '<path d="M30 0v40M0 20h60" stroke="#fff" stroke-width="13"/>'
        '<path d="M30 0v40M0 20h60" stroke="#C8102E" stroke-width="7"/></svg>'
    ),
}


def flag(lang: str, width: int = 27, height: int = 18) -> QIcon:
    """Bandera con esquinas redondeadas para el botón de idioma."""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QPainterPath

    renderer = QSvgRenderer(QByteArray(_FLAGS[lang].encode()))
    result = QIcon()
    for scale in (1, 2):
        w, h = width * scale, height * scale
        pix = QPixmap(QSize(w, h))
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(0, 0, w, h), 3.5 * scale, 3.5 * scale)
        painter.setClipPath(clip)
        renderer.render(painter, QRectF(0, 0, w, h))
        painter.end()
        pix.setDevicePixelRatio(scale)
        result.addPixmap(pix)
    return result


def app_icon() -> QIcon:
    """Ícono de la app: nota musical sobre fondo violeta."""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">'
        '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="#9a7bff"/><stop offset="1" stop-color="#4c2bb3"/></linearGradient></defs>'
        '<rect x="16" y="16" width="224" height="224" rx="56" fill="url(#g)"/>'
        '<path d="M106 172V88l78-17v85" fill="none" stroke="#fff" stroke-width="15" stroke-linecap="round" stroke-linejoin="round"/>'
        '<ellipse cx="86" cy="172" rx="25" ry="21" fill="#fff"/><ellipse cx="164" cy="156" rx="25" ry="21" fill="#fff"/>'
        "</svg>"
    )
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    result = QIcon()
    for size in (32, 64, 128, 256):
        pix = QPixmap(QSize(size, size))
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        renderer.render(painter)
        painter.end()
        result.addPixmap(pix)
    return result


def qpalette(c: dict[str, str]):
    """Paleta de Qt acorde al tema, para que casillas, combos y diálogos no desentonen."""
    from PySide6.QtGui import QColor, QPalette

    pal = QPalette()
    roles = QPalette.ColorRole
    for role, key in (
        (roles.Window, "bg"), (roles.WindowText, "text"), (roles.Base, "surface"), (roles.AlternateBase, "surface2"),
        (roles.Text, "text"), (roles.Button, "surface"), (roles.ButtonText, "text"), (roles.Highlight, "accent"),
        (roles.HighlightedText, "accent_text"), (roles.PlaceholderText, "muted"), (roles.ToolTipBase, "text"),
        (roles.ToolTipText, "bg"), (roles.Link, "accent"), (roles.Mid, "border"), (roles.Dark, "border"), (roles.Light, "surface2"),
    ):
        pal.setColor(role, QColor(c[key]))
    for role in (roles.Text, roles.WindowText, roles.ButtonText):
        pal.setColor(QPalette.ColorGroup.Disabled, role, QColor(c["muted"]))
    return pal
