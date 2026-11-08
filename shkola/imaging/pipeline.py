"""Застосування неруйнівних правок сторінки в правильному порядку + автоматичні дії."""

from __future__ import annotations

from PIL import Image

from ..core.models import Adjust, Page
from . import geometry, tone
from .filters import apply_filter


def geometry_stage(img: Image.Image, adj: Adjust) -> Image.Image:
    """Поворот + вирівнювання (без кадрування) — у цих координатах задається рамка кадру."""
    return geometry.rotate(img, adj.rotation, adj.fine_angle)


def render(page: Page, max_side: int | None = None, with_crop: bool = True) -> Image.Image:
    img = page.original
    if max_side and max(img.size) > max_side:
        k = max_side / max(img.size)
        img = img.resize((max(1, int(img.width * k)), max(1, int(img.height * k))), Image.Resampling.LANCZOS)
    else:
        k = 1.0
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    adj = page.adjust
    img = geometry_stage(img, adj)
    if with_crop and adj.crop:
        img = geometry.crop(img, tuple(int(v * k) for v in adj.crop))
    if adj.auto_levels:
        img = tone.auto_levels(img)
    img = tone.brightness_contrast_gamma(img, adj.brightness, adj.contrast, adj.gamma)
    img = apply_filter(img, adj.filter, adj.bw_threshold)
    return img.copy() if img is page.original else img   # оригінал ніколи не віддаємо назовні


def auto_deskew(page: Page) -> float:
    base = geometry.rotate(page.original, page.adjust.rotation)
    page.adjust.fine_angle = geometry.detect_skew(base)
    page.adjust.crop = None
    return page.adjust.fine_angle


def auto_crop(page: Page) -> bool:
    staged = geometry_stage(page.original, page.adjust)
    box = geometry.content_bbox(staged)
    page.adjust.crop = box
    return box is not None


def auto_orient(page: Page) -> int:
    """Повернути аркуш, покладений боком, щоб рядки стали горизонтальними."""
    turn = geometry.detect_orientation(geometry.rotate(page.original, page.adjust.rotation))
    if turn:
        page.adjust.rotation = (page.adjust.rotation + turn) % 360
        page.adjust.crop = None
    return turn


def detect_template(page: Page) -> str:
    """За запитом: визначити формат (A4, A5, диплом, фото 13×18…) і обрізати точно під нього.
    Повертає назву шаблону або порожній рядок, якщо формат нестандартний (кадр — за вмістом)."""
    from . import templates
    staged = geometry_stage(page.original, page.adjust)
    box = geometry.content_bbox(staged, margin_px=0)
    if not box:
        return ""
    mm = lambda px: px / page.dpi * 25.4
    m = templates.match(mm(box[2] - box[0]), mm(box[3] - box[1]))
    page.adjust.crop = templates.box_for(m, box, page.dpi, staged.size) if m else box
    page.note = m.name if m else ""
    return page.note


def auto_format(page: Page) -> None:
    """Автоформатування: орієнтація → вирівнювання перекосу → обрізання зайвого."""
    auto_orient(page)
    auto_deskew(page)
    auto_crop(page)


def auto_enhance(page: Page) -> None:
    """Одна кнопка «зробити добре»: автоформат + рівні."""
    auto_orient(page)
    auto_deskew(page)
    auto_crop(page)
    page.adjust.auto_levels = True
