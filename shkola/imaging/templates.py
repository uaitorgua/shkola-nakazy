"""Автовизначення формату документа (A4, A5, диплом, ID-картка, фото 13×18, 10×15…) за фізичним розміром аркуша."""

from __future__ import annotations

from dataclasses import dataclass

from ..config import TEMPLATE_TOLERANCE, TEMPLATES


@dataclass
class TemplateMatch:
    name: str
    size_mm: tuple[float, float]       # уже з урахуванням орієнтації (ширина, висота)
    landscape: bool
    error: float                       # відносна похибка


def match(width_mm: float, height_mm: float, allowed: list[str] | None = None) -> TemplateMatch | None:
    """Найближчий шаблон для аркуша заданого розміру або None, якщо нічого не підходить."""
    landscape = width_mm > height_mm
    short, long_ = sorted((width_mm, height_mm))
    best: TemplateMatch | None = None
    for name, (tw, th) in TEMPLATES.items():
        if allowed and name not in allowed:
            continue
        err = max(abs(short - tw) / tw, abs(long_ - th) / th)
        if err <= TEMPLATE_TOLERANCE and (best is None or err < best.error):
            size = (th, tw) if landscape else (tw, th)
            best = TemplateMatch(name, size, landscape, err)
    return best


def box_for(match_: TemplateMatch, content: tuple[int, int, int, int], dpi: int,
            limit: tuple[int, int]) -> tuple[int, int, int, int]:
    """Рамка точно під розмір шаблону, по центру знайденого аркуша."""
    x0, y0, x1, y1 = content
    w = round(match_.size_mm[0] / 25.4 * dpi)
    h = round(match_.size_mm[1] / 25.4 * dpi)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    nx0 = int(max(0, min(cx - w / 2, limit[0] - w)))
    ny0 = int(max(0, min(cy - h / 2, limit[1] - h)))
    return nx0, ny0, min(limit[0], nx0 + w), min(limit[1], ny0 + h)
