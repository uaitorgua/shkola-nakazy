"""Збереження пакета в один багатосторінковий PDF із правильним фізичним розміром сторінок."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PIL import Image

from .. import __version__
from ..config import APP_NAME, ORG_NAME
from ..core.models import Page
from ..imaging.parallel import pmap
from ..imaging.pipeline import render


def _prepare(p: Page) -> Image.Image:
    img = render(p)
    if img.mode == "1":
        return img.convert("L")      # PDF-кодер Pillow не поєднує ч/б (CCITT) з якістю JPEG
    return img if img.mode in ("RGB", "L") else img.convert("RGB")


def save_pdf(pages: list[Page], path: Path, quality: int = 85, title: str = "",
             progress: Callable[[int, int], None] | None = None) -> Path:
    if not pages:
        raise ValueError("Немає сторінок для збереження")
    images = pmap(_prepare, pages, progress)      # рендер сторінок паралельно
    dpi = pages[0].dpi or 300
    path.parent.mkdir(parents=True, exist_ok=True)
    images[0].save(
        path, "PDF", save_all=True, append_images=images[1:],
        resolution=float(dpi), quality=quality,
        title=title or path.stem, author=ORG_NAME,
        creator=f"{APP_NAME} {__version__}", producer=APP_NAME,
    )
    return path
