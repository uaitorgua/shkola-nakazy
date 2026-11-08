"""Текстове розпізнавання: Tesseract 5 (tesserocr), мови ukr+eng, слова з координатами й рівнем довіри.

Одна сесія на потік (tesserocr не потокобезпечний); перше звернення ініціалізує рушій (~1 с).
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Callable

from PIL import Image

from ..config import OCR_LANGS, TESSDATA_DIR
from .models import OcrPage, Word

log = logging.getLogger(__name__)
_local = threading.local()
_lock = threading.Lock()


def available() -> bool:
    try:
        import tesserocr  # noqa: F401
    except ImportError:
        return False
    return all((Path(TESSDATA_DIR) / f"{l}.traineddata").exists() for l in OCR_LANGS.split("+"))


def missing_message() -> str:
    return (f"Моделі розпізнавання не знайдено в {TESSDATA_DIR}.\n"
            "Запустіть tools\\get_ocr.py (потрібен інтернет один раз) або встановіть збірку EXE.")


def _ansi_path(path) -> bytes:
    """Tesseract на Windows відкриває файли вузькими (ANSI) шляхами: кирилична тека потребує
    кодування mbcs або короткого імені 8.3."""
    p = str(path)
    try:
        return p.encode("mbcs")
    except UnicodeEncodeError:
        import ctypes
        buf = ctypes.create_unicode_buffer(1024)
        if ctypes.windll.kernel32.GetShortPathNameW(p, buf, 1024):
            return buf.value.encode("ascii", "replace")
        return p.encode("utf-8")


def _api(langs: str):
    import tesserocr
    api = getattr(_local, "api", None)
    if api is None or getattr(_local, "langs", "") != langs:
        if api is not None:
            api.End()
        api = tesserocr.PyTessBaseAPI(path=_ansi_path(TESSDATA_DIR), lang=langs, psm=tesserocr.PSM.AUTO)
        _local.api, _local.langs = api, langs
    return api


def _prepare(img: Image.Image) -> Image.Image:
    if img.mode == "1":
        return img.convert("L")
    if img.mode not in ("L", "RGB"):
        return img.convert("RGB")
    return img


def recognize(img: Image.Image, dpi: int = 300, langs: str = OCR_LANGS,
              progress: Callable[[int, int], None] | None = None) -> OcrPage:
    """Повертає OcrPage зі словами (координати в пікселях img). Структуру будує structure.analyze()."""
    if not available():
        raise RuntimeError(missing_message())
    import tesserocr
    img = _prepare(img)
    api = _api(langs)
    api.SetImage(img)
    api.SetSourceResolution(int(dpi) if dpi else 300)
    if progress:
        progress(0, 1)
    api.Recognize()
    page = OcrPage(width=img.width, height=img.height, dpi=dpi, langs=langs)
    it = api.GetIterator()
    RIL = tesserocr.RIL
    if it is None:
        return page
    block = para = line = -1
    while True:
        if it.IsAtBeginningOf(RIL.BLOCK):
            block += 1
        if it.IsAtBeginningOf(RIL.PARA):
            para += 1
        if it.IsAtBeginningOf(RIL.TEXTLINE):
            line += 1
        try:
            text = it.GetUTF8Text(RIL.WORD)
            box = it.BoundingBox(RIL.WORD)
        except RuntimeError:            # tesserocr: «No text returned» на порожній сторінці
            text, box = "", None
        if text and text.strip() and box:
            x0, y0, x1, y1 = box
            page.words.append(Word(text.strip(), x0, y0, x1, y1, it.Confidence(RIL.WORD), block, para, line))
        if not it.Next(RIL.WORD):
            break
    if progress:
        progress(1, 1)
    log.info("OCR: %d слів, довіра %.0f%%", len(page.words), page.mean_conf)
    return page
