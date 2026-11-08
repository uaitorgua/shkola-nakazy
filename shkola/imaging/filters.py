"""Фільтри: сірий, ч/б з порогом, різкість, прибирання дрібного шуму."""

from __future__ import annotations

from PIL import Image, ImageFilter

from .tone import otsu_threshold

FILTERS = {
    "none": "Без фільтра",
    "gray": "Відтінки сірого",
    "bw": "Чорно-білий (текст)",
    "sharpen": "Різкість",
    "despeckle": "Прибрати крапки",
}


def apply_filter(img: Image.Image, name: str, bw_threshold: int = 0) -> Image.Image:
    if name == "gray":
        return img.convert("L")
    if name == "bw":
        gray = img.convert("L")
        t = bw_threshold or otsu_threshold(gray)
        return gray.point(lambda v: 255 if v > t else 0).convert("1")
    if name == "sharpen":
        return img.filter(ImageFilter.UnsharpMask(radius=1.5, percent=120, threshold=3))
    if name == "despeckle":
        return img.filter(ImageFilter.MedianFilter(3))
    return img
