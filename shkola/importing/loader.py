"""Додавання зовнішньої графіки замість сканування: PDF (багатосторінкові), PNG, JPG, TIFF, BMP, WEBP, HEIC."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from PIL import Image

from ..core.models import Page

log = logging.getLogger(__name__)

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp", ".heic", ".heif"}
PDF_EXT = {".pdf"}
SUPPORTED = IMAGE_EXT | PDF_EXT
FILE_FILTER = ("Документи й зображення (*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.bmp *.gif *.webp *.heic);;"
               "PDF (*.pdf);;Зображення (*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.gif *.webp *.heic)")
PDF_DPI = 200

try:   # фото з iPhone
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass


def _normal(im: Image.Image) -> Image.Image:
    if im.mode in ("RGB", "L"):
        return im.copy()
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))     # прозорість → білий аркуш
        bg.paste(im, mask=im.split()[-1])
        return bg
    return im.convert("RGB")


def load_image(path: Path) -> list[Page]:
    from PIL import ImageOps
    pages = []
    with Image.open(path) as im:
        for i in range(getattr(im, "n_frames", 1)):          # багатосторінкові TIFF/GIF
            im.seek(i)
            dpi = int(round((im.info.get("dpi") or (300, 300))[0] or 300))
            frame = ImageOps.exif_transpose(im) if i == 0 else im   # орієнтація з EXIF (фото телефоном)
            pages.append(Page(original=_normal(frame), dpi=max(72, dpi), note=path.name))
    return pages


def load_pdf(path: Path, dpi: int = PDF_DPI) -> list[Page]:
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(str(path))
    try:
        pages = []
        for i in range(len(pdf)):
            bmp = pdf[i].render(scale=dpi / 72)
            pages.append(Page(original=_normal(bmp.to_pil()), dpi=dpi, note=f"{path.name} с.{i + 1}"))
        return pages
    finally:
        pdf.close()


def load_files(paths: list[str | Path], progress: Callable[[int, int], None] | None = None) -> tuple[list[Page], list[str]]:
    """Повертає (сторінки у порядку файлів, помилки)."""
    from ..imaging.parallel import pmap

    def one(p):
        p = Path(p)
        try:
            ext = p.suffix.lower()
            if ext in PDF_EXT:
                return load_pdf(p), None
            if ext in IMAGE_EXT:
                return load_image(p), None
            return [], f"{p.name}: непідтримуваний формат"
        except Exception as e:
            log.exception("Імпорт %s", p)
            return [], f"{p.name}: {e}"

    results = pmap(one, list(paths), progress)
    pages = [pg for r, _ in results for pg in r]
    errors = [e for _, e in results if e]
    return pages, errors
