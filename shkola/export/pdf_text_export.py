"""PDF із текстовим шаром (searchable PDF): зображення сторінки + невидимий текст над кожним словом
(reportlab, режим рендеру 3). Текст можна шукати, виділяти й копіювати."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Callable

from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from .. import __version__
from ..config import APP_NAME, FONT_TTF
from ..core.models import Page
from ..imaging.pipeline import render
from ..ocr.models import OcrPage

FONT = "DejaVuSans"


def _font() -> str:
    if FONT not in pdfmetrics.getRegisteredFontNames():
        if Path(FONT_TTF).exists():
            pdfmetrics.registerFont(TTFont(FONT, str(FONT_TTF)))
        else:
            return "Helvetica"      # без кирилиці; шрифт тягне tools/get_ocr.py
    return FONT


def save_searchable_pdf(pages: list[Page], ocr: list[OcrPage | None], path: Path, quality: int = 85,
                        title: str = "", progress: Callable[[int, int], None] | None = None) -> Path:
    if not pages:
        raise ValueError("Немає сторінок для збереження")
    font = _font()
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path))
    c.setTitle(title or path.stem)
    c.setCreator(f"{APP_NAME} {__version__}")
    for i, (p, o) in enumerate(zip(pages, ocr)):
        img = render(p)
        if img.mode not in ("RGB", "L"):
            img = img.convert("L" if img.mode == "1" else "RGB")
        dpi = p.dpi or 300
        w_pt, h_pt = img.width * 72 / dpi, img.height * 72 / dpi
        c.setPageSize((w_pt, h_pt))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality)
        buf.seek(0)
        c.drawImage(ImageReader(buf), 0, 0, width=w_pt, height=h_pt)
        if o and o.words:
            kx, ky = w_pt / o.width, h_pt / o.height
            t = c.beginText()
            t.setTextRenderMode(3)       # невидимий
            for w in o.words:
                h = max(1.0, (w.y1 - w.y0) * ky)
                size = h * 0.85
                t.setFont(font, size)
                text_w = pdfmetrics.stringWidth(w.text, font, size) or 1.0
                t.setHorizScale(100.0 * ((w.x1 - w.x0) * kx) / text_w)
                t.setTextOrigin(w.x0 * kx, h_pt - w.y1 * ky + h * 0.2)
                t.textOut(w.text)
            c.drawText(t)
        c.showPage()
        if progress:
            progress(i + 1, len(pages))
    c.save()
    return path
