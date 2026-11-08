"""Імпорт зображень із диска та збереження пакета (PDF / графіка) у фоні."""

from __future__ import annotations

import os

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QFileDialog, QMessageBox, QProgressDialog, QWidget

from ..export.image_export import save_images
from ..export.naming import unique_path
from ..export.pdf_export import save_pdf
from ..importing.loader import FILE_FILTER, load_files
from .export_dialog import ExportDialog
from .scan_panel import InsertAt
from .page_controller import PageController
from .workers import TaskWorker


def export_with_ocr(kind: str, pages, path, quality: int, title: str, progress=None):
    """Фонове завдання: спершу OCR нерозпізнаних сторінок, потім експорт у вибраний формат."""
    from .ocr_controller import ocr_pages
    ocr_pages(pages, progress)
    docs = [p.ocr.doc for p in pages]
    if kind == "pdf_text":
        from ..export.pdf_text_export import save_searchable_pdf
        return save_searchable_pdf(pages, [p.ocr for p in pages], path, quality, title, progress)
    if kind == "docx":
        from ..export.docx_export import save_docx
        return save_docx(docs, path, title, progress)
    if kind == "xlsx":
        from ..export.xlsx_export import save_xlsx
        return save_xlsx(docs, path, progress)
    from ..export.text_export import save_txt
    return save_txt(docs, path, progress)



class FileController(QObject):
    status = Signal(str)
    exported = Signal()        # після збереження (оновити панель OCR — могли розпізнатися сторінки)

    def __init__(self, parent: QWidget, store, pages: PageController) -> None:
        super().__init__(parent)
        self.win, self.store, self.pages = parent, store, pages
        self._worker: TaskWorker | None = None

    def import_dialog(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self.win, "Додати документи й зображення",
                                                self.store.get("output_dir"), FILE_FILTER)
        if files:
            self.import_files(files)

    def import_files(self, files: list[str]) -> None:
        """Імпорт у фоні; вставка — туди ж, куди й скани (кінець / після / перед / замість вибраної)."""
        prog = QProgressDialog("Відкриваю файли…", None, 0, len(files), self.win)
        prog.setWindowTitle("Додавання")
        prog.setMinimumDuration(300)
        self._worker = TaskWorker(load_files, files)
        self._worker.progress.connect(lambda a, b: prog.setValue(a))
        self._worker.done.connect(lambda res: (prog.close(), self._imported(*res)))
        self._worker.failed.connect(lambda m: (prog.close(), QMessageBox.warning(self.win, "Імпорт", m)))
        self._worker.start()

    def _imported(self, pages, errors) -> None:
        if pages and self.autoformat():
            from ..imaging.parallel import pmap
            from ..imaging.pipeline import auto_format
            pmap(auto_format, pages)
        if pages:
            self.pages.begin_insert(self.insert_at(), single_mode=False)
            for p in pages:
                self.pages.add_page(p)
            self.status.emit(f"Додано сторінок: {len(pages)}")
        if errors:
            QMessageBox.warning(self.win, "Не вдалося відкрити", "\n".join(errors))

    insert_at = staticmethod(lambda: InsertAt.END)     # підміняється головним вікном
    autoformat = staticmethod(lambda: False)

    def export(self) -> None:
        batch = self.pages.batch
        if not len(batch):
            QMessageBox.information(self.win, "Зберегти", "Пакет порожній.")
            return
        sel = self.pages.strip.selected_rows()
        dlg = ExportDialog(self.win, self.store, len(sel), len(batch))
        if not dlg.exec():
            return
        dlg.remember()
        chosen = [batch.pages[i] for i in sel] if dlg.only_selected() else list(batch.pages)
        kind = dlg.kind()
        if kind == "pdf":
            path = unique_path(dlg.folder() / f"{dlg.name()}.pdf")
            fn, args = save_pdf, (chosen, path, dlg.quality(), dlg.name())
        elif kind == "image":
            fn, args = save_images, (chosen, dlg.folder(), dlg.name(), dlg.image_format(), dlg.quality())
        else:
            from ..ocr import engine
            if any(p.ocr is None for p in chosen) and not engine.available():
                QMessageBox.warning(self.win, "Зберегти", engine.missing_message())
                return
            path = unique_path(dlg.folder() / f"{dlg.name()}.{'pdf' if kind == 'pdf_text' else kind}")
            fn, args = export_with_ocr, (kind, chosen, path, dlg.quality(), dlg.name())

        prog = QProgressDialog("Зберігаю…", None, 0, len(chosen), self.win)
        prog.setWindowTitle("Збереження")
        prog.setMinimumDuration(300)
        self._worker = TaskWorker(fn, *args)
        self._worker.progress.connect(lambda a, b: prog.setValue(a))
        self._worker.done.connect(lambda res: (prog.close(), self._saved(res, dlg.folder()), self.exported.emit()))
        self._worker.failed.connect(lambda m: (prog.close(), QMessageBox.critical(self.win, "Помилка збереження", m)))
        self._worker.start()

    def _saved(self, result, folder) -> None:
        files = result if isinstance(result, list) else [result]
        self.status.emit(f"Збережено: {files[0]}" + (f" (+{len(files) - 1})" if len(files) > 1 else ""))
        box = QMessageBox(QMessageBox.Icon.Information, "Збережено",
                          f"Файлів: {len(files)}\n{files[0]}", parent=self.win)
        open_btn = box.addButton("Відкрити теку", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Ok)
        box.exec()
        if box.clickedButton() is open_btn:
            os.startfile(str(folder))
