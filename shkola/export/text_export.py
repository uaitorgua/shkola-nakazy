"""TXT і HTML: з розпізнаних структур."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Callable

from ..ocr.formula import latex_to_unicode
from ..ocr.models import Document, Formula, Paragraph, Table


def save_txt(docs: list[Document], path: Path, progress: Callable[[int, int], None] | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    parts = []
    for i, d in enumerate(docs):
        parts.append(d.plain_text())
        if progress:
            progress(i + 1, len(docs))
    path.write_text("\n\n\f\n".join(parts), encoding="utf-8")
    return path


def doc_to_html(doc: Document) -> str:
    """HTML для редактора (QTextDocument розуміє h1–h3, p align, ul/ol, table)."""
    out = []
    list_open = None
    for b in doc.blocks:
        tag = "ul" if isinstance(b, Paragraph) and b.kind == "li" else "ol" if isinstance(b, Paragraph) and b.kind == "oli" else None
        if list_open and tag != list_open:
            out.append(f"</{list_open}>")
            list_open = None
        if tag and not list_open:
            out.append(f"<{tag}>")
            list_open = tag
        if isinstance(b, Paragraph):
            t = html.escape(b.text)
            if tag:
                out.append(f"<li>{t}</li>")
            elif b.kind in ("h1", "h2", "h3"):
                out.append(f'<{b.kind} align="{b.align}">{t}</{b.kind}>')
            else:
                out.append(f'<p align="{b.align}">{t}</p>')
        elif isinstance(b, Table):
            rows = "".join("<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in r) + "</tr>" for r in b.rows)
            out.append(f'<table border="1" cellpadding="4" cellspacing="0" width="100%">{rows}</table><p></p>')
        elif isinstance(b, Formula):
            out.append(f'<p align="center"><i title="{html.escape(b.latex)}">{html.escape(latex_to_unicode(b.latex))}</i></p>')
    if list_open:
        out.append(f"</{list_open}>")
    return "".join(out)


def docs_to_html(docs: list[Document]) -> str:
    return "<hr/>".join(doc_to_html(d) for d in docs)
