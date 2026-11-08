"""Яскравість, контраст, гама, автокорекція рівнів."""

from __future__ import annotations

import numpy as np
from PIL import Image


def _lut(fn) -> list[int]:
    x = np.arange(256, dtype=np.float32)
    return np.clip(fn(x), 0, 255).astype(np.uint8).tolist()


def brightness_contrast_gamma(img: Image.Image, brightness: int, contrast: int, gamma: float) -> Image.Image:
    if brightness == 0 and contrast == 0 and abs(gamma - 1.0) < 1e-3:
        return img
    c = (100 + contrast) / 100.0
    c = c * c if contrast > 0 else c          # підсилення м'якше на від'ємних значеннях
    b = brightness * 2.55
    g = max(0.05, gamma)

    def fn(x):
        y = (x - 127.5) * c + 127.5 + b
        y = np.clip(y, 0, 255) / 255.0
        return 255.0 * np.power(y, 1.0 / g)

    return _apply_lut(img, _lut(fn))


def auto_levels(img: Image.Image, clip: float = 0.5) -> Image.Image:
    """Розтягує гістограму: clip% найтемніших → чорний, найсвітліших → білий.
    Для кольорових — спільні межі по яскравості (без зсуву кольору) + нейтралізація фону паперу."""
    gray = np.asarray(img.convert("L"), dtype=np.uint8)
    lo, hi = np.percentile(gray, [clip, 100 - clip])
    if hi - lo < 10:
        return img
    lut = _lut(lambda x: (x - lo) * 255.0 / (hi - lo))
    out = _apply_lut(img, lut)
    if out.mode == "RGB":
        out = _neutral_paper(out)
    return out


def _neutral_paper(img: Image.Image) -> Image.Image:
    """Прибирає жовтизну/синяву паперу: найсвітліші 5% пікселів робимо нейтрально білими."""
    a = np.asarray(img, dtype=np.float32)
    lum = a.mean(axis=2)
    mask = lum >= np.percentile(lum, 95)
    if mask.sum() < 100:
        return img
    ref = a[mask].mean(axis=0)
    scale = ref.mean() / np.maximum(ref, 1)
    if np.abs(scale - 1).max() < 0.01:
        return img
    return Image.fromarray(np.clip(a * scale, 0, 255).astype(np.uint8), "RGB")


def otsu_threshold(img: Image.Image) -> int:
    hist = np.bincount(np.asarray(img.convert("L")).ravel(), minlength=256).astype(np.float64)
    total = hist.sum()
    w = np.cumsum(hist)
    m = np.cumsum(hist * np.arange(256))
    mt = m[-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        between = (mt * w / total - m) ** 2 / (w * (total - w))
    return int(np.nanargmax(between))


def _apply_lut(img: Image.Image, lut: list[int]) -> Image.Image:
    if img.mode == "RGB":
        return img.point(lut * 3)
    if img.mode == "L":
        return img.point(lut)
    return _apply_lut(img.convert("RGB"), lut)
