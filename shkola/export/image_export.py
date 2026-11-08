"""Збереження сторінок як графіки: окремі файли або багатосторінковий TIFF."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from ..core.models import Page
from ..imaging.parallel import pmap
from ..imaging.pipeline import render
from .naming import unique_path

FORMATS = {
    "PNG": ".png",
    "JPEG": ".jpg",
    "TIFF": ".tif",
    "TIFF багатосторінковий": ".tif",
}


def save_images(pages: list[Page], folder: Path, prefix: str, fmt: str, quality: int = 90,
                progress: Callable[[int, int], None] | None = None) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    ext = FORMATS[fmt]
    if fmt == "TIFF багатосторінковий":
        return [_multi_tiff(pages, unique_path(folder / f"{prefix}{ext}"), progress)]
    width = max(3, len(str(len(pages))))
    # шляхи призначаємо заздалегідь, щоб паралельні потоки не конкурували за імена
    paths, taken = [], set()
    for i in range(1, len(pages) + 1):
        path = unique_path(folder / f"{prefix}_{i:0{width}d}{ext}")
        while path in taken:
            path = path.with_name(path.stem + "_" + path.suffix)
        taken.add(path)
        paths.append(path)

    def one(job):
        p, path = job
        img = render(p)
        kw = {"dpi": (p.dpi, p.dpi)}
        if fmt == "JPEG":
            img = img.convert("RGB") if img.mode not in ("RGB", "L") else img
            kw.update(quality=quality, optimize=True, subsampling=0)
        elif fmt == "TIFF":
            kw["compression"] = "group4" if img.mode == "1" else "tiff_lzw"
        elif fmt == "PNG":
            kw["optimize"] = True
        img.save(path, **kw)
        return path

    return pmap(one, list(zip(pages, paths)), progress)


def _multi_tiff(pages: list[Page], path: Path, progress) -> Path:
    imgs = pmap(render, pages, progress)
    comp = "group4" if all(im.mode == "1" for im in imgs) else "tiff_lzw"
    imgs[0].save(path, save_all=True, append_images=imgs[1:], compression=comp,
                 dpi=(pages[0].dpi, pages[0].dpi))
    return path
