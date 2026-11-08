"""Стилі документа InterText: набір оформлення (шрифт, розмір, інтервал, абзацний відступ, вирівнювання, береги,
заголовки, таблиці) → JSON-файл; збереження з поточного документа, завантаження, застосування до всього тексту.
Збережені стилі лежать у %APPDATA%\\skaner-shkola\\styles\\*.json; вбудовані — «ДСТУ 4163:2020» і «Звичайний»."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QTextBlockFormat, QTextCharFormat, QTextCursor

from ..config import DATA_DIR
from .editor_page import MM, PageSetup, apply_page_setup

STYLES_DIR = DATA_DIR / "styles"


@dataclass
class DocStyle:
    name: str = "Мій стиль"
    font: str = "Times New Roman"
    size: float = 14.0
    line_spacing: float = 1.5
    first_line_mm: float = 10.0
    align: str = "justify"              # left | center | right | justify
    before_pt: float = 0.0
    after_pt: float = 0.0
    margins_mm: tuple = (30.0, 10.0, 20.0, 20.0)
    h1_size: float = 16.0
    h2_size: float = 14.0
    h3_size: float = 14.0
    heading_bold: bool = True
    heading_center: bool = True
    table_size: float = 12.0

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, text: str) -> "DocStyle":
        d = json.loads(text)
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        if "margins_mm" in known:
            known["margins_mm"] = tuple(float(v) for v in known["margins_mm"])
        return cls(**known)

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path) -> "DocStyle":
        return cls.from_json(path.read_text(encoding="utf-8"))


BUILTIN = {
    "ДСТУ 4163:2020": DocStyle("ДСТУ 4163:2020"),
    "Звичайний": DocStyle("Звичайний", size=12.0, line_spacing=1.15, first_line_mm=0.0, align="left",
                          margins_mm=(20.0, 20.0, 20.0, 20.0), h1_size=20.0, h2_size=16.0, h3_size=13.0, heading_center=False),
    "Конспект (компактно)": DocStyle("Конспект (компактно)", font="Arial", size=11.0, line_spacing=1.0, first_line_mm=0.0,
                                     align="left", margins_mm=(15.0, 15.0, 15.0, 15.0), h1_size=16.0, h2_size=13.0, h3_size=12.0,
                                     heading_center=False, table_size=10.0, after_pt=4.0),
}

_ALIGN = {"left": Qt.AlignmentFlag.AlignLeft, "center": Qt.AlignmentFlag.AlignHCenter,
          "right": Qt.AlignmentFlag.AlignRight, "justify": Qt.AlignmentFlag.AlignJustify}


def saved_styles() -> dict[str, Path]:
    STYLES_DIR.mkdir(parents=True, exist_ok=True)
    out = {}
    for p in sorted(STYLES_DIR.glob("*.json")):
        try:
            out[DocStyle.load(p).name or p.stem] = p
        except Exception:
            continue
    return out


def capture(edit, name: str = "Мій стиль") -> DocStyle:
    """Стиль із поточного документа: формат абзацу й символів під курсором (або першого звичайного абзацу),
    береги сторінки, розміри заголовків із документа."""
    doc = edit.document()
    c = edit.textCursor()
    bf, cf = c.blockFormat(), c.charFormat()
    if bf.headingLevel() or c.currentTable() is not None:
        b = doc.begin()
        while b.isValid():
            cc = QTextCursor(b)
            if not b.blockFormat().headingLevel() and cc.currentTable() is None and b.text().strip():
                bf, cf = b.blockFormat(), QTextCursor(doc).charFormat() if not b.length() else cc.charFormat()
                cc.setPosition(b.position() + 1)
                cf = cc.charFormat()
                break
            b = b.next()
    st = DocStyle(name)
    fams = cf.fontFamilies()
    st.font = fams[0] if fams else doc.defaultFont().family()
    st.size = cf.fontPointSize() or doc.defaultFont().pointSizeF() or 12.0
    st.line_spacing = (bf.lineHeight() / 100) if bf.lineHeightType() == 1 and bf.lineHeight() else 1.0
    st.first_line_mm = round(bf.textIndent() / MM, 1)
    a = bf.alignment()
    st.align = "center" if a & Qt.AlignmentFlag.AlignHCenter else "right" if a & Qt.AlignmentFlag.AlignRight \
        else "justify" if a & Qt.AlignmentFlag.AlignJustify else "left"
    st.before_pt, st.after_pt = bf.topMargin(), bf.bottomMargin()
    ps = edit.setup
    st.margins_mm = (ps.left, ps.right, ps.top, ps.bottom)
    sizes = {}
    b = doc.begin()
    while b.isValid():
        lvl = b.blockFormat().headingLevel()
        if lvl and lvl not in sizes and b.length() > 1:
            cc = QTextCursor(b)
            cc.setPosition(b.position() + 1)
            sizes[lvl] = cc.charFormat().fontPointSize() or st.size
            st.heading_bold = cc.charFormat().fontWeight() >= QFont.Weight.Bold
            st.heading_center = bool(b.blockFormat().alignment() & Qt.AlignmentFlag.AlignHCenter)
        b = b.next()
    st.h1_size = sizes.get(1, st.size + 2)
    st.h2_size = sizes.get(2, st.size)
    st.h3_size = sizes.get(3, st.size)
    return st


def apply(edit, st: DocStyle) -> int:
    """Застосовує стиль до всього документа. Повертає кількість абзаців."""
    doc = edit.document()
    n = 0
    c = QTextCursor(doc)
    c.beginEditBlock()
    block = doc.begin()
    while block.isValid():
        c.setPosition(block.position())
        bf = block.blockFormat()
        in_table = c.currentTable() is not None
        lvl = bf.headingLevel()
        cf = QTextCharFormat()
        cf.setFontFamilies([st.font])
        if in_table:
            cf.setFontPointSize(st.table_size)
        elif lvl:
            cf.setFontPointSize({1: st.h1_size, 2: st.h2_size, 3: st.h3_size}.get(lvl, st.size))
            cf.setFontWeight(QFont.Weight.Bold if st.heading_bold else QFont.Weight.Normal)
        else:
            cf.setFontPointSize(st.size)
        c.select(QTextCursor.SelectionType.BlockUnderCursor)
        c.mergeCharFormat(cf)
        nb = QTextBlockFormat()
        nb.setLineHeight(st.line_spacing * 100, 1)
        if lvl:
            nb.setAlignment(Qt.AlignmentFlag.AlignHCenter if st.heading_center else Qt.AlignmentFlag.AlignLeft)
            nb.setTextIndent(0)
            nb.setTopMargin(12)
            nb.setBottomMargin(6)
        elif not in_table and block.textList() is None:
            nb.setTextIndent(st.first_line_mm * MM)
            nb.setAlignment(_ALIGN.get(st.align, Qt.AlignmentFlag.AlignLeft))
            nb.setTopMargin(st.before_pt)
            nb.setBottomMargin(st.after_pt)
        c.mergeBlockFormat(nb)
        n += 1
        block = block.next()
    c.endEditBlock()
    f = QFont(st.font, int(st.size))
    doc.setDefaultFont(f)
    edit.setCurrentFont(f)
    edit.set_page_setup(PageSetup(*st.margins_mm))
    return n
