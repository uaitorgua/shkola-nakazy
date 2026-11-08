"""Поворот, вирівнювання перекосу, кадрування, автокадрування."""

from __future__ import annotations

import numpy as np
from PIL import Image


def rotate(img: Image.Image, quarter: int, fine: float = 0.0) -> Image.Image:
    quarter %= 360
    if quarter:
        img = img.transpose({90: Image.Transpose.ROTATE_270,
                             180: Image.Transpose.ROTATE_180,
                             270: Image.Transpose.ROTATE_90}[quarter])
    if abs(fine) > 0.01:
        fill = _edge_color(img)
        img = img.rotate(-fine, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=fill)
    return img


def _edge_color(img: Image.Image):
    """Медіанний колір країв — ним заливаються кути після повороту, щоб не з'являлись чужі смуги."""
    a = np.asarray(img)
    edge = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    med = np.median(edge, axis=0)
    return int(med) if np.ndim(med) == 0 else tuple(int(v) for v in med)


def detect_skew(img: Image.Image, max_angle: float = 6.0) -> float:
    """Кут перекосу тексту (градуси, за годинниковою стрілкою додатний) методом проєкційного профілю."""
    small = img.convert("L")
    scale = 1000 / max(small.size)
    if scale < 1:
        small = small.resize((int(small.width * scale), int(small.height * scale)), Image.Resampling.BILINEAR)
    a = np.asarray(small, dtype=np.uint8)
    thr = a.mean() - a.std() * 0.5
    ink = Image.fromarray(((a < thr) * 255).astype(np.uint8))

    def score(angle: float) -> float:
        r = np.asarray(ink.rotate(angle, resample=Image.Resampling.NEAREST, expand=False), dtype=np.float32)
        prof = r.sum(axis=1)
        return float(np.var(prof))

    best, best_s = 0.0, score(0.0)
    for step, span in ((1.0, max_angle), (0.2, 1.0), (0.05, 0.2)):
        center = best
        for ang in np.arange(center - span, center + span + 1e-6, step):
            s = score(float(ang))
            if s > best_s:
                best, best_s = float(ang), s
    return round(-best, 2)


def detect_orientation(img: Image.Image) -> int:
    """0 або 90: чи лежать рядки тексту вертикально (аркуш покладено боком).
    Порівнює «смугастість» горизонтального й вертикального профілів чорнила."""
    box = content_bbox(img)
    if box:                                   # лише сам аркуш, без тла кришки і з відступом від країв
        x0, y0, x1, y1 = box
        dx, dy = (x1 - x0) // 12, (y1 - y0) // 12
        img = img.crop((x0 + dx, y0 + dy, x1 - dx, y1 - dy))
    small = img.convert("L")
    scale = 800 / max(small.size)
    if scale < 1:
        small = small.resize((int(small.width * scale), int(small.height * scale)), Image.Resampling.BILINEAR)
    a = np.asarray(small, dtype=np.float32)
    ink = Image.fromarray(((a < a.mean() - a.std()) * 255).astype(np.uint8))

    def best_rows_score(im: Image.Image) -> float:
        # найкраща «смугастість» рядків серед кутів ±6° (перекіс не повинен заважати)
        best = 0.0
        for ang in np.arange(-6, 6.01, 0.5):
            prof = np.asarray(im.rotate(float(ang), expand=False), dtype=np.float32).sum(axis=1)
            best = max(best, float(np.var(prof) / (prof.mean() ** 2 + 1e-6)))
        return best

    horiz = best_rows_score(ink)
    vert = best_rows_score(ink.transpose(Image.Transpose.ROTATE_90))
    return 90 if vert > horiz * 1.3 else 0


def content_bbox(img: Image.Image, margin_px: int = 10) -> tuple[int, int, int, int] | None:
    """Межі вмісту документа (відкидає темне тло кришки сканера та порожні поля)."""
    a = np.asarray(img.convert("L"), dtype=np.int16)
    # Фон — найчастіший колір по краях
    border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    bg = int(np.median(border))
    diff = np.abs(a - bg) > 40
    rows = np.where(diff.mean(axis=1) > 0.005)[0]
    cols = np.where(diff.mean(axis=0) > 0.005)[0]
    if rows.size == 0 or cols.size == 0:
        return None
    x0 = max(0, cols[0] - margin_px)
    y0 = max(0, rows[0] - margin_px)
    x1 = min(img.width, cols[-1] + margin_px + 1)
    y1 = min(img.height, rows[-1] + margin_px + 1)
    if (x1 - x0) * (y1 - y0) < 0.05 * img.width * img.height:
        return None
    return int(x0), int(y0), int(x1), int(y1)


def crop(img: Image.Image, box: tuple[int, int, int, int] | None) -> Image.Image:
    if not box:
        return img
    x0, y0, x1, y1 = box
    x0, x1 = sorted((max(0, x0), min(img.width, x1)))
    y0, y1 = sorted((max(0, y0), min(img.height, y1)))
    if x1 - x0 < 4 or y1 - y0 < 4:
        return img
    return img.crop((x0, y0, x1, y1))
