"""Логіка пакета та правок: поточна сторінка, прев'ю, кадр, повороти, undo, вставка сторінок."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from ..core.models import Batch, Page
from ..imaging import pipeline
from .adjust_panel import AdjustPanel
from .image_view import ImageView
from .page_strip import PageStrip
from .qtimage import to_pixmap
from .scan_panel import InsertAt
from .undo import UndoHistory

PREVIEW = 1800      # найбільша сторона прев'ю, px


class PageController(QObject):
    changed = Signal()          # пакет змінився (кількість/порядок)
    info = Signal(str)          # повідомлення для рядка стану

    def __init__(self, batch: Batch, view: ImageView, strip: PageStrip, panel: AdjustPanel) -> None:
        super().__init__()
        self.batch, self.view, self.strip, self.panel = batch, view, strip, panel
        self.history = UndoHistory()
        self.current = -1
        self._insert_pos = 0
        self.external_crop = False      # рамка використовується іншим контролером (формула), не кадром

        strip.page_selected.connect(self.select)
        strip.order_changed.connect(self._reorder)
        strip.move_requested.connect(self.move_rows)
        strip.delete_requested.connect(self.delete)
        panel.adjust_changed.connect(lambda _a: self._edited(push=False))
        panel.action.connect(self._action)
        view.crop_changed.connect(self._crop)
        panel.load(None)

    # ---------- доступ ----------
    def page(self) -> Page | None:
        return self.batch.pages[self.current] if 0 <= self.current < len(self.batch) else None

    # ---------- вставка зі сканера ----------
    def begin_insert(self, where: InsertAt, single_mode: bool) -> None:
        sel = self.current
        if single_mode:
            self.batch.clear()
            self._insert_pos = 0
        elif where == InsertAt.END or sel < 0:
            self._insert_pos = len(self.batch)
        elif where == InsertAt.AFTER:
            self._insert_pos = sel + 1
        elif where == InsertAt.BEFORE:
            self._insert_pos = sel
        else:                                   # REPLACE
            self.batch.remove([sel])
            self._insert_pos = sel
        self._rebuild(self._insert_pos)

    def add_page(self, page: Page) -> None:
        idx = self.batch.insert(self._insert_pos, [page])
        self._insert_pos = idx + 1
        self._rebuild(idx)

    def add_pages(self, pages: list[Page]) -> None:
        self.begin_insert(InsertAt.END, single_mode=False)
        for p in pages:
            self.add_page(p)

    # ---------- вибір / прев'ю ----------
    def select(self, index: int) -> None:
        self.current = index
        self.panel.load(self.page().adjust if self.page() else None)
        self._preview()

    def _preview(self, keep_view: bool = False) -> None:
        p = self.page()
        if not p:
            self.view.set_pixmap(None)
            return
        k = min(1.0, PREVIEW / max(p.original.size))
        crop_mode = self.view.crop_mode
        img = pipeline.render(p, max_side=PREVIEW, with_crop=not crop_mode)   # у режимі кадру — увесь аркуш і рамка
        crop = tuple(v * k for v in p.adjust.crop) if crop_mode and p.adjust.crop else None
        self.view.set_pixmap(to_pixmap(img), crop, keep_view=keep_view)

    def _scale(self) -> float:
        p = self.page()
        return min(1.0, PREVIEW / max(p.original.size)) if p else 1.0

    # ---------- правки ----------
    def _edited(self, push: bool = True) -> None:
        p = self.page()
        if not p:
            return
        if push:
            self.history.push(p)
        self._preview(keep_view=True)
        self.strip.refresh_page(self.current, p)

    def _crop(self, box) -> None:
        p = self.page()
        if not p or self.external_crop:
            return
        self.history.push(p)
        k = self._scale()
        p.adjust.crop = tuple(int(v / k) for v in box) if box else None
        self.strip.refresh_page(self.current, p)

    def _action(self, act: str) -> None:
        if act == "autoformat_all":
            self._autoformat_all()
            return
        if act in ("crop_mode", "crop_off"):
            self.view.set_crop_mode(act == "crop_mode")
            self._preview()
            return
        p = self.page()
        if not p:
            return
        self.history.push(p)
        a = p.adjust
        if act in ("rotate_l", "rotate_r"):
            a.rotation = (a.rotation + (270 if act == "rotate_l" else 90)) % 360
            a.crop = None
        elif act == "deskew":
            pipeline.auto_deskew(p)
        elif act == "autocrop":
            pipeline.auto_crop(p)
        elif act == "auto":
            pipeline.auto_enhance(p)
        elif act == "autoformat":
            pipeline.auto_format(p)
        elif act == "template":
            name = pipeline.detect_template(p)
            self.info.emit(f"Формат: {name}" if name else "Стандартний формат не впізнано — кадр за межами аркуша")
        elif act == "crop_clear":
            a.crop = None
        elif act == "reset":
            p.adjust = type(a)()
        elif act == "apply_all":
            self._apply_tone_to_all(p)
        self.panel.load(p.adjust)
        self._edited(push=False)

    def _autoformat_all(self) -> None:
        from PySide6.QtWidgets import QApplication
        from ..imaging.parallel import pmap
        for p in self.batch.pages:
            self.history.push(p)
        self.info.emit("Автоформат пакета…")
        QApplication.processEvents()
        pmap(pipeline.auto_format, self.batch.pages)
        self._rebuild(max(0, self.current))
        self.info.emit(f"Автоформат виконано для {len(self.batch)} сторінок")

    def _apply_tone_to_all(self, src: Page) -> None:
        s = src.adjust
        for i, p in enumerate(self.batch.pages):
            if p is src:
                continue
            self.history.push(p)
            p.adjust.brightness, p.adjust.contrast, p.adjust.gamma = s.brightness, s.contrast, s.gamma
            p.adjust.auto_levels, p.adjust.filter, p.adjust.bw_threshold = s.auto_levels, s.filter, s.bw_threshold
            self.strip.refresh_page(i, p)

    def undo(self) -> None:
        if self.page() and self.history.undo(self.page()):
            self.panel.load(self.page().adjust)
            self._edited(push=False)

    def redo(self) -> None:
        if self.page() and self.history.redo(self.page()):
            self.panel.load(self.page().adjust)
            self._edited(push=False)

    # ---------- пакет ----------
    def delete(self, rows: list[int]) -> None:
        if not rows:
            return
        self.batch.remove(rows)
        self._rebuild(min(rows))

    def move_current(self, delta: int) -> None:
        i = self.current
        if 0 <= i + delta < len(self.batch):
            self.batch.move(i, i + delta)
            self._rebuild(i + delta)

    def move_rows(self, rows: list[int], dst: int) -> None:
        """Перенести вибрані сторінки (одну чи кілька) у позицію dst."""
        moving = [self.batch.pages[r] for r in rows]
        before = sum(1 for r in rows if r < dst)
        rest = [p for i, p in enumerate(self.batch.pages) if i not in set(rows)]
        dst -= before
        self.batch.pages = rest[:dst] + moving + rest[dst:]
        self._rebuild(dst)

    def clear(self) -> None:
        self.batch.clear()
        self._rebuild(0)

    def _reorder(self, ids: list[int]) -> None:
        by_id = {p.id: p for p in self.batch.pages}
        self.batch.pages = [by_id[i] for i in ids if i in by_id]
        self.current = self.strip.currentRow()
        self.changed.emit()

    def _rebuild(self, current: int) -> None:
        self.strip.rebuild(self.batch.pages, current)
        if not self.batch.pages:
            self.select(-1)
        self.changed.emit()
