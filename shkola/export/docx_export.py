"""DOCX (python-docx): абзаци, заголовки, списки, вирівнювання, таблиці, формули (Unicode-текст)."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from docx import Document as DocxDocument
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

from .. import __version__
from ..config import APP_NAME
from ..ocr.formula import latex_to_unicode
from ..ocr.models import Document, Formula, Paragraph, Table

_ALIGN = {"left": WD_ALIGN_PARAGRAPH.LEFT, "center": WD_ALIGN_PARAGRAPH.CENTER,
          "right": WD_ALIGN_PARAGRAPH.RIGHT, "justify": WD_ALIGN_PARAGRAPH.JUSTIFY}
_HEAD = {"h1": 1, "h2": 2, "h3": 3}


def _add_block(d: DocxDocument, b) -> None:
    if isinstance(b, Paragraph):
        if b.kind in _HEAD:
            p = d.add_heading(b.text, level=_HEAD[b.kind])
        elif b.kind == "li":
            p = d.add_paragraph(b.text, style="List Bullet")
        elif b.kind == "oli":
            p = d.add_paragraph(b.text, style="List Number")
        else:
            p = d.add_paragraph(b.text)
        p.alignment = _ALIGN.get(b.align, WD_ALIGN_PARAGRAPH.LEFT)
    elif isinstance(b, Table):
        if not b.rows:
            return
        t = d.add_table(rows=len(b.rows), cols=b.n_cols)
        t.style = "Table Grid"
        for i, row in enumerate(b.rows):
            for j, cell in enumerate(row):
                t.cell(i, j).text = cell
        d.add_paragraph()
    elif isinstance(b, Formula):
        p = d.add_paragraph()
        r = p.add_run(latex_to_unicode(b.latex))
        r.italic = True
        r.font.size = Pt(13)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER


def save_docx(docs: list[Document], path: Path, title: str = "",
              progress: Callable[[int, int], None] | None = None) -> Path:
    """Кожна сторінка — з нової сторінки документа."""
    d = DocxDocument()
    d.core_properties.title = title or path.stem
    d.core_properties.comments = f"{APP_NAME} {__version__}"
    st = d.styles["Normal"]
    st.font.name = "Times New Roman"
    st.font.size = Pt(12)
    for i, doc in enumerate(docs):
        if i:
            d.add_page_break()
        for b in doc.blocks:
            _add_block(d, b)
        if progress:
            progress(i + 1, len(docs))
    path.parent.mkdir(parents=True, exist_ok=True)
    d.save(str(path))
    return path


def save_html_docx(html: str, path: Path) -> Path:
    """DOCX із HTML редактора (QTextDocument.toHtml) — через html_docx."""
    from .html_docx import html_to_docx
    path.parent.mkdir(parents=True, exist_ok=True)
    html_to_docx(html).save(str(path))
    return path
