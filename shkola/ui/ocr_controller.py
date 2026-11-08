"""OCR у фоні: сторінка / пакет, формула з виділеної ділянки, передача в редактори."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMessageBox, QWidget

from ..core.models import Page
from ..imaging import pipeline
from ..ocr import engine, formula, structure
from ..ocr.models import Formula, OcrPage, Paragraph
from .ocr_panel import OcrPanel
from .page_controller import PageController
from .workers import TaskWorker

log = logging.getLogger(__name__)


def ocr_pages(pages: list[Page], progress=None) -> int:
    """Розпізнає сторінки без результату (виклик у фоновому потоці). Повертає кількість."""
    todo = [p for p in pages if p.ocr is None]
    for i, p in enumerate(todo):
        img = pipeline.render(p)
        res = engine.recognize(img, p.dpi)
        structure.analyze(res, img)
        p.ocr = res
        if progress:
            progress(i + 1, len(todo))
    return len(todo)


class OcrController(QObject):
    status = Signal(str)
    changed = Signal()          # результати оновилися
    open_text = Signal(object)  # Page → відкрити в InterText
    open_table = Signal(object)  # Page → відкрити в InterTab

    def __init__(self, parent: QWidget, pages: PageController, panel: OcrPanel) -> None:
        super().__init__(parent)
        self.win, self.pages, self.panel = parent, pages, panel
        self._worker: TaskWorker | None = None
        self.formula_mode = False
        panel.recognize_as.connect(self.recognize_and_open)
        panel.recognize_all.connect(self.recognize_all)
        self._after: tuple[str, Page] | None = None
        panel.formula_mode.connect(self.set_formula_mode)
        panel.text_edited.connect(self._text_edited)
        pages.strip.page_selected.connect(lambda _i: self.refresh())
        pages.changed.connect(self.refresh)
        pages.view.crop_changed.connect(self._region)

    def busy(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def refresh(self) -> None:
        p = self.pages.page()
        self.panel.set_count(len(self.pages.batch))
        self.panel.show_page(p.ocr if p else None, any(q.ocr for q in self.pages.batch.pages))

    # ---------- текст ----------
    def recognize_current(self) -> None:
        p = self.pages.page()
        if p:
            p.ocr = None
            self._run([p])

    def recognize_all(self) -> None:
        self._run(list(self.pages.batch.pages))

    def recognize_and_open(self, mode: str) -> None:
        """«Текст → InterText» / «Таблиця → InterTab»: розпізнати поточну сторінку (якщо ще ні) і відкрити."""
        p = self.pages.page()
        if not p:
            return
        self._after = (mode, p)
        if p.ocr is not None:
            self._open_after()
        else:
            self._run([p])

    def _open_after(self) -> None:
        if not self._after:
            return
        mode, p = self._after
        self._after = None
        if p.ocr is None:
            return
        (self.open_table if mode == "table" else self.open_text).emit(p)

    def _run(self, pages: list[Page]) -> None:
        if self.busy() or not pages:
            return
        if not engine.available():
            QMessageBox.warning(self.win, "Розпізнавання", engine.missing_message())
            return
        self.panel.set_busy(True, 0, len(pages))
        self.status.emit("Розпізнаю…")
        self._worker = TaskWorker(ocr_pages, pages)
        self._worker.progress.connect(lambda a, b: self.panel.set_busy(True, a, b))
        self._worker.done.connect(self._done)
        self._worker.failed.connect(self._failed)
        self._worker.start()

    def _done(self, n: int) -> None:
        self.panel.set_busy(False)
        self.refresh()
        self.status.emit(f"Розпізнано сторінок: {n}")
        self.changed.emit()
        self._open_after()

    def _failed(self, msg: str) -> None:
        self._after = None
        self.panel.set_busy(False)
        self.refresh()
        QMessageBox.critical(self.win, "Розпізнавання", msg)

    def _text_edited(self, text: str) -> None:
        """Правка в панелі замінює текст сторінки одним абзацом на рядок (структура спрощується)."""
        p = self.pages.page()
        if not p or p.ocr is None or text == p.ocr.text:
            return
        p.ocr.doc.blocks = [Paragraph(t) for t in text.split("\n") if t.strip()]

    # ---------- формули ----------
    def set_formula_mode(self, on: bool) -> None:
        self.formula_mode = on
        self.pages.external_crop = on
        self.pages.view.set_crop_mode(on)
        self.pages._preview()
        if on:
            self.status.emit("Обведіть формулу мишею на сторінці")

    def _region(self, box) -> None:
        if not self.formula_mode or not box:
            return
        p = self.pages.page()
        if not p:
            return
        if not formula.available():
            QMessageBox.warning(self.win, "Формули", formula.missing_message())
            return
        k = self.pages._scale()
        x0, y0, x1, y1 = (int(v / k) for v in box)
        full = pipeline.render(p, with_crop=False)
        region = full.crop((max(0, x0), max(0, y0), min(full.width, x1), min(full.height, y1)))
        if region.width < 8 or region.height < 8:
            return
        self.panel.btn_formula.setChecked(False)
        self.status.emit("Розпізнаю формулу…")
        self._worker = TaskWorker(lambda img, progress=None: formula.recognize(img), region)
        self._worker.done.connect(lambda latex: self._formula_done(p, latex, (x0, y0, x1, y1)))
        self._worker.failed.connect(lambda m: QMessageBox.critical(self.win, "Формула", m))
        self._worker.start()

    def _formula_done(self, p: Page, latex: str, bbox) -> None:
        if not latex:
            self.status.emit("У виділеній ділянці формули не знайдено")
            return
        if p.ocr is None:
            p.ocr = OcrPage(width=p.original.width, height=p.original.height, dpi=p.dpi)
        f = Formula(latex, bbox)
        blocks = p.ocr.doc.blocks
        pos = next((i for i, b in enumerate(blocks) if b.bbox and b.bbox[1] > bbox[1]), len(blocks))
        blocks.insert(pos, f)
        self.refresh()
        self.status.emit(f"Формула: {latex}")
        self.changed.emit()
        from ..ocr.formula import latex_to_unicode
        QMessageBox.information(self.win, "Формула розпізнана",
                                f"<b>Текст:</b> {latex_to_unicode(latex)}<br><b>LaTeX:</b> <code>{latex}</code>"
                                "<br><br>Формулу додано до тексту сторінки.")
