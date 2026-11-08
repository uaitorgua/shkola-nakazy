"""Евристичне визначення структур після OCR: абзаци, заголовки, списки, вирівнювання, таблиці.

Таблиці: (1) за лініями сітки на зображенні (морфологія NumPy), (2) за вирівняними стовпцями слів
у сусідніх рядках без ліній. Решта слів групується в абзаци за розміткою Tesseract.
"""

from __future__ import annotations

import re
from statistics import median

import numpy as np
from PIL import Image

from .models import Document, OcrPage, Paragraph, Table, Word

BULLET_RE = re.compile(r"^([•·\-–—*▪■○●♦➢➤►\"“”°]|[а-яa-z]\)|[а-яa-z]\.)\s*$", re.I)
NUMBER_RE = re.compile(r"^(\d{1,3}[.)]|\d{1,3}(\.\d{1,3})+\.?|[IVX]{1,5}[.)])$")
MIN_TABLE_ROWS, MIN_TABLE_COLS = 2, 2


# ---------- лінії сітки ----------
def _binary(img: Image.Image) -> np.ndarray:
    g = np.asarray(img.convert("L"))
    thr = max(60, min(200, int(g.mean()) - 40))
    return g < thr


def grid_lines(img: Image.Image) -> tuple[list[tuple[int, int, int, int]], list[tuple[int, int, int, int]]]:
    """Горизонтальні та вертикальні лінії (x0, y0, x1, y1) довжиною ≥ 1/12 сторони."""
    b = _binary(img)
    h, w = b.shape
    out_h, out_v = [], []
    min_len_h, min_len_v = max(40, w // 12), max(40, h // 12)
    # горизонтальні: ряд з довгим неперервним темним відрізком
    rows = b.sum(axis=1)
    for y in np.flatnonzero(rows >= min_len_h):
        xs = np.flatnonzero(b[y])
        gaps = np.flatnonzero(np.diff(xs) > 3)
        starts = np.r_[0, gaps + 1]
        ends = np.r_[gaps, len(xs) - 1]
        for s, e in zip(starts, ends):
            if xs[e] - xs[s] >= min_len_h:
                out_h.append((int(xs[s]), int(y), int(xs[e]), int(y)))
    cols = b.sum(axis=0)
    for x in np.flatnonzero(cols >= min_len_v):
        ys = np.flatnonzero(b[:, x])
        gaps = np.flatnonzero(np.diff(ys) > 3)
        starts = np.r_[0, gaps + 1]
        ends = np.r_[gaps, len(ys) - 1]
        for s, e in zip(starts, ends):
            if ys[e] - ys[s] >= min_len_v:
                out_v.append((int(x), int(ys[s]), int(x), int(ys[e])))
    return _merge(out_h, axis=1), _merge(out_v, axis=0)


def _merge(lines: list, axis: int, tol: int = 4) -> list:
    """Злиття сусідніх паралельних ліній (товсті лінії дають кілька рядків пікселів)."""
    if not lines:
        return []
    key = (lambda l: l[1]) if axis == 1 else (lambda l: l[0])
    lines = sorted(lines, key=key)
    merged = [list(lines[0])]
    for l in lines[1:]:
        m = merged[-1]
        if abs(key(l) - key(tuple(m))) <= tol and _overlap(l, m, axis):
            if axis == 1:
                m[0], m[2] = min(m[0], l[0]), max(m[2], l[2])
            else:
                m[1], m[3] = min(m[1], l[1]), max(m[3], l[3])
        else:
            merged.append(list(l))
    return [tuple(m) for m in merged]


def _overlap(a, b, axis) -> bool:
    if axis == 1:
        return min(a[2], b[2]) - max(a[0], b[0]) > -20
    return min(a[3], b[3]) - max(a[1], b[1]) > -20


def ruled_tables(img: Image.Image) -> list[tuple[tuple[int, int, int, int], list[int], list[int]]]:
    """Таблиці за сіткою: (bbox, межі рядків y, межі стовпців x)."""
    hs, vs = grid_lines(img)
    if len(hs) < 2 or len(vs) < 2:
        return []
    tables = []
    used = set()
    for i, h in enumerate(hs):
        if i in used:
            continue
        # усі горизонтальні, що перекриваються по x із цією
        grp = [j for j, o in enumerate(hs) if j not in used and min(h[2], o[2]) - max(h[0], o[0]) > 0.5 * min(h[2] - h[0], o[2] - o[0])]
        ys = sorted({hs[j][1] for j in grp})
        x0, x1 = min(hs[j][0] for j in grp), max(hs[j][2] for j in grp)
        y0, y1 = ys[0], ys[-1]
        xs = sorted({v[0] for v in vs if v[0] >= x0 - 10 and v[0] <= x1 + 10 and v[1] <= y0 + 10 and v[3] >= y1 - 10})
        if len(ys) >= MIN_TABLE_ROWS + 1 - 1 and len(xs) >= MIN_TABLE_COLS + 1 - 1 and len(ys) >= 2 and len(xs) >= 2:
            used.update(grp)
            tables.append(((x0, y0, x1, y1), ys, xs))
    return tables


def _cells_from_grid(words: list[Word], ys: list[int], xs: list[int]) -> list[list[str]]:
    rows = [["" for _ in range(len(xs) - 1)] for _ in range(len(ys) - 1)]
    for w in sorted(words, key=lambda w: (w.cy, w.x0)):
        r = next((i for i in range(len(ys) - 1) if ys[i] <= w.cy < ys[i + 1]), None)
        c = next((i for i in range(len(xs) - 1) if xs[i] <= w.cx < xs[i + 1]), None)
        if r is not None and c is not None:
            rows[r][c] = (rows[r][c] + " " + w.text).strip()
    return rows


# ---------- рядки й абзаци ----------
def _lines(words: list[Word]) -> list[list[Word]]:
    groups: dict[tuple[int, int, int], list[Word]] = {}
    for w in words:
        groups.setdefault((w.block, w.para, w.line), []).append(w)
    return [sorted(g, key=lambda w: w.x0) for _, g in sorted(groups.items())]


def _line_text(ln: list[Word]) -> str:
    return " ".join(w.text for w in ln)


def _bbox(ws: list[Word]) -> tuple[int, int, int, int]:
    return min(w.x0 for w in ws), min(w.y0 for w in ws), max(w.x1 for w in ws), max(w.y1 for w in ws)


def _list_kind(ln: list[Word]) -> str | None:
    first = ln[0].text
    if BULLET_RE.match(first):
        return "li"
    if NUMBER_RE.match(first) and len(ln) > 1:
        return "oli"
    return None


def columns_table(lines: list[list[Word]]) -> list[list[str]] | None:
    """Таблиця без ліній: ≥3 рядки поспіль з ≥2 великими проміжками в однакових позиціях."""
    if len(lines) < 3:
        return None
    med_h = median(w.h for ln in lines for w in ln) or 10
    gap_min = med_h * 1.8
    col_sets = []
    for ln in lines:
        cuts = []
        for a, b in zip(ln, ln[1:]):
            if b.x0 - a.x1 > gap_min:
                cuts.append((a.x1 + b.x0) / 2)
        col_sets.append(cuts)
    if any(len(c) < 1 for c in col_sets):
        return None
    n = min(len(c) for c in col_sets)
    ref = col_sets[0][:n]
    for c in col_sets[1:]:
        if any(abs(c[i] - ref[i]) > med_h * 2.5 for i in range(n)):
            return None
    rows = []
    for ln in lines:
        cells = [""] * (n + 1)
        for w in ln:
            idx = sum(1 for cut in ref if w.cx > cut)
            cells[idx] = (cells[idx] + " " + w.text).strip()
        rows.append(cells)
    return rows


def analyze(page: OcrPage, img: Image.Image | None = None) -> Document:
    doc = Document()
    words = list(page.words)
    if not words:
        page.doc = doc
        return doc
    med_h = median(w.h for w in words) or 10
    page_w = page.width

    # 1. Таблиці за сіткою
    table_blocks: list[tuple[int, Table]] = []
    if img is not None:
        for bbox, ys, xs in ruled_tables(img):
            inside = [w for w in words if bbox[0] - 5 <= w.cx <= bbox[2] + 5 and bbox[1] - 5 <= w.cy <= bbox[3] + 5]
            rows = _cells_from_grid(inside, ys, xs)
            if sum(1 for r in rows for c in r if c) >= 2:
                table_blocks.append((bbox[1], Table(rows, bbox)))
                ids = {id(w) for w in inside}
                words = [w for w in words if id(w) not in ids]

    # 2. Рядки → абзаци / списки / таблиці за стовпцями
    lines = _lines(words)
    items: list[tuple[int, object]] = [(b.bbox[1], b) for _, b in table_blocks]
    i = 0
    while i < len(lines):
        # спроба таблиці без ліній: беремо послідовні рядки одного блоку з ≥1 розривом
        j = i
        while j < len(lines) and len(lines[j]) >= 2 and lines[j][0].block == lines[i][0].block \
                and any(b.x0 - a.x1 > med_h * 1.8 for a, b in zip(lines[j], lines[j][1:])):
            j += 1
        if j - i >= 3:
            rows = columns_table(lines[i:j])
            if rows:
                ws = [w for ln in lines[i:j] for w in ln]
                items.append((ws[0].y0, Table(rows, _bbox(ws))))
                i = j
                continue
        ln = lines[i]
        text = _line_text(ln)
        bb = _bbox(ln)
        h = median(w.h for w in ln)
        kind = "p"
        lk = _list_kind(ln)
        caps = sum(c.isupper() for c in text) / max(1, sum(c.isalpha() for c in text))
        if lk:
            kind = lk
            text = " ".join(w.text for w in ln[1:])
        elif h >= med_h * 1.6 and len(text) < 80:
            kind = "h1"
        elif (h >= med_h * 1.25 and len(text) < 80) or (caps > 0.8 and len(text) < 80 and len(text) > 3):
            kind = "h2"
        # вирівнювання
        cx = (bb[0] + bb[2]) / 2
        width = bb[2] - bb[0]
        align = "left"
        if width < page_w * 0.7 and abs(cx - page_w / 2) < page_w * 0.06:
            align = "center"
        elif width < page_w * 0.6 and bb[2] > page_w * 0.85:
            align = "right"
        # злиття з попереднім абзацом (той самий para у Tesseract, звичайний текст)
        prev = items[-1][1] if items else None
        same_para = isinstance(prev, Paragraph) and prev.kind in ("p", "li", "oli") and kind == "p" \
            and i > 0 and (lines[i - 1][0].block, lines[i - 1][0].para) == (ln[0].block, ln[0].para) \
            and prev.align == align
        if same_para:
            prev.text += " " + text
            prev.bbox = (min(prev.bbox[0], bb[0]), prev.bbox[1], max(prev.bbox[2], bb[2]), bb[3])
        else:
            items.append((bb[1], Paragraph(text, kind, align, bb)))
        i += 1

    items.sort(key=lambda t: t[0])
    doc.blocks = [b for _, b in items]
    page.doc = doc
    return doc


def page_as_table(page: OcrPage) -> list[list[str]]:
    """Уся сторінка як одна таблиця: знайдені таблиці — як є; решта рядків ділиться на стовпці за великими
    проміжками між словами (м'якший поріг), інакше — один стовпець на рядок. Для кнопки «Таблиця → InterTab»."""
    if page.doc.tables and len(page.doc.tables) == 1 and len(page.doc.blocks) <= 2:
        return page.doc.tables[0].rows
    words = list(page.words)
    if not words:
        return []
    med_h = median(w.h for w in words) or 10
    gap_min = med_h * 1.2
    lines = _lines(words)
    # опорні стовпці: кластеризуємо початки «комірок» по всій сторінці
    starts = []
    for ln in lines:
        starts.append(ln[0].x0)
        for a, b in zip(ln, ln[1:]):
            if b.x0 - a.x1 > gap_min:
                starts.append(b.x0)
    starts.sort()
    cols: list[float] = []
    for x in starts:
        if not cols or x - cols[-1] > med_h * 2.5:
            cols.append(x)
    rows = []
    for ln in lines:
        cells = [""] * len(cols)
        for w in ln:
            idx = max(0, max((i for i, cx in enumerate(cols) if w.x0 >= cx - med_h), default=0))
            cells[idx] = (cells[idx] + " " + w.text).strip()
        rows.append(cells)
    # прибрати повністю порожні стовпці
    keep = [j for j in range(len(cols)) if any(r[j] for r in rows)]
    return [[r[j] for j in keep] for r in rows]
