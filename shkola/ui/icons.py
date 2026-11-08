"""Власні SVG-іконки ГС «УАІТ» (assets/icons, генерує tools/make_icons.py); запасний варіант — Font Awesome Free (Solid) для панелей інструментів: assets/fonts/fa-solid-900.ttf (tools/get_assets.py).
Шрифт — SIL OFL 1.1, іконки — CC BY 4.0 (атрибуція у вікні «Про програму»). Без шрифту панелі лишаються текстовими."""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPixmap

from ..config import ASSETS
from . import theme

SVG_DIR = ASSETS / "icons"
SVG_MAIN = "#135548"
FONT_FILE = ASSETS / "fonts" / "fa-solid-900.ttf"
_family: str | None = None

# назва → код гліфа Font Awesome 6 Solid
GLYPHS = {
    "bold": 0xf032, "italic": 0xf033, "underline": 0xf0cd, "strikethrough": 0xf0cc, "superscript": 0xf12b,
    "subscript": 0xf12c, "align-left": 0xf036, "align-center": 0xf037, "align-right": 0xf038, "align-justify": 0xf039,
    "list-ul": 0xf0ca, "list-ol": 0xf0cb, "indent": 0xf03c, "outdent": 0xf03b, "table": 0xf0ce, "image": 0xf03e,
    "search": 0xf002, "undo": 0xf0e2, "redo": 0xf01e, "plus": 0xf067, "minus": 0xf068, "font": 0xf031,
    "palette": 0xf53f, "highlighter": 0xf591, "eraser": 0xf12d, "formula": 0xf698, "calendar": 0xf133,
    "file-word": 0xf1c2, "file-excel": 0xf1c3, "file-pdf": 0xf1c1, "file-lines": 0xf15c, "save": 0xf0c7,
    "folder-open": 0xf07c, "print": 0xf02f, "zoom-in": 0xf00e, "zoom-out": 0xf010, "expand": 0xf065,
    "trash": 0xf1f8, "broom": 0xf51a, "arrow-left": 0xf060, "arrow-right": 0xf061, "info": 0xf05a,
    "text-height": 0xf034, "ruler": 0xf545, "symbol": 0xf1e3, "page-break": 0xf0f6, "line": 0xf068,
    "table-rows": 0xf00b, "table-cols": 0xf009, "merge": 0xf2d2, "split": 0xf24d, "sigma": 0xf68b,
    "sort-up": 0xf160, "sort-down": 0xf161, "fill": 0xf063, "percent": 0xf295, "hashtag": 0xf292, "paint": 0xf5aa,
    "scan": 0xf02f, "ocr": 0xf15c, "edit": 0xf044, "copy": 0xf0c5, "paste": 0xf0ea, "check": 0xf00c, "stamp": 0xf5bf,
    "layers": 0xf5fd, "book": 0xf02d, "file-import": 0xf56f, "eye": 0xf06e, "wand": 0xf0d0, "rotate-left": 0xf2ea,
    "rotate-right": 0xf2f9, "crop": 0xf125, "sheet": 0xf0ce, "text": 0xf031, "gear": 0xf013, "new": 0xf15b,
}


def available() -> bool:
    return SVG_DIR.is_dir() or FONT_FILE.exists()


@lru_cache(maxsize=256)
def _svg_src(name: str) -> str | None:
    f = SVG_DIR / f"{name}.svg"
    return f.read_text(encoding="utf-8") if f.exists() else None


@lru_cache(maxsize=1024)
def _svg(name: str, s: int, col: str) -> QPixmap:
    from PySide6.QtCore import QByteArray
    from PySide6.QtSvg import QSvgRenderer
    src = _svg_src(name).replace(SVG_MAIN, col)
    if col == "#a9b4b0":
        src = src.replace("#f0b14a", col)
    pm = QPixmap(s, s)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(QByteArray(src.encode("utf-8"))).render(p)
    p.end()
    return pm


def family() -> str | None:
    global _family
    if _family is None and FONT_FILE.exists():
        fid = QFontDatabase.addApplicationFont(str(FONT_FILE))
        fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
        _family = fams[0] if fams else ""
    return _family or None


@lru_cache(maxsize=512)
def _glyph(fam: str, code: int, s: int, col: str) -> QPixmap:
    pm = QPixmap(s, s)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    f = QFont(fam)
    f.setPixelSize(int(s * 0.72))
    p.setFont(f)
    p.setPen(QColor(col))
    p.drawText(QRect(0, 0, s, s), Qt.AlignmentFlag.AlignCenter, chr(code))
    p.end()
    return pm


@lru_cache(maxsize=512)
def icon(name: str, color: str = theme.PRIMARY_DARK, size: int = 20) -> QIcon:
    """Звичайний стан — зелений (гама застосунку), увімкнений — графіт на бурштиновому тлі кнопки,
    вимкнений — сірий."""
    ic = QIcon()
    if _svg_src(name):
        for s in (size, size * 2):
            ic.addPixmap(_svg(name, s, color), QIcon.Mode.Normal, QIcon.State.Off)
            ic.addPixmap(_svg(name, s, theme.TEXT), QIcon.Mode.Normal, QIcon.State.On)
            ic.addPixmap(_svg(name, s, theme.TEXT), QIcon.Mode.Active, QIcon.State.On)
            ic.addPixmap(_svg(name, s, "#a9b4b0"), QIcon.Mode.Disabled, QIcon.State.Off)
        return ic
    fam = family()
    code = GLYPHS.get(name)
    if not fam or code is None:
        return ic
    for s in (size, size * 2):
        ic.addPixmap(_glyph(fam, code, s, color), QIcon.Mode.Normal, QIcon.State.Off)
        ic.addPixmap(_glyph(fam, code, s, theme.TEXT), QIcon.Mode.Normal, QIcon.State.On)
        ic.addPixmap(_glyph(fam, code, s, theme.TEXT), QIcon.Mode.Active, QIcon.State.On)
        ic.addPixmap(_glyph(fam, code, s, "#a9b4b0"), QIcon.Mode.Disabled, QIcon.State.Off)
    return ic


def decorate(window, mapping: dict[str, str], keep_text: bool = True) -> None:
    """Ставить іконки діям панелей вікна за їхнім текстом: {текст дії: назва іконки}.
    keep_text=False → лише іконка (текст лишається у підказці)."""
    from PySide6.QtWidgets import QToolBar
    if not available():
        return
    for tb in window.findChildren(QToolBar):
        for a in tb.actions():
            name = mapping.get(a.text())
            if name:
                a.setIcon(icon(name))
                if not keep_text:
                    if not a.toolTip() or a.toolTip() == a.text():
                        a.setToolTip(a.text())
                    a.setIconText("")
                    a.setText("")
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon if keep_text
                              else Qt.ToolButtonStyle.ToolButtonIconOnly)
