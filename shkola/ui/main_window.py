"""Головне вікно: компонування віджетів і зв'язок контролерів (сканування, файли, правка, OCR, редактори)."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QApplication, QHBoxLayout, QStyle, QMainWindow, QScrollArea, QToolBar, QVBoxLayout, QWidget

from ..config import APP_NAME, INTERTAB, INTERTEXT
from ..core.models import Batch
from ..core.settings_store import SettingsStore
from ..devices.registry import DeviceRegistry
from .about_dialog import AboutDialog
from .adjust_panel import AdjustPanel
from .banner import Banner
from .device_controller import DeviceController
from .device_panel import DevicePanel
from .file_controller import FileController
from .image_view import ImageView
from .load_panel import LoadPanel
from .logo import app_icon
from . import icons
from .ocr_controller import OcrController
from .ocr_panel import OcrPanel
from .page_controller import PageController
from .page_strip import PageStrip
from .promo_panel import PromoPanel
from .save_panel import SavePanel
from .scan_controller import ScanController
from .scan_panel import ScanPanel
from .source_panel import SourcePanel
from .zoom_bar import ZoomBar


LEFT_W, RIGHT_W, CENTER_MIN_W = 460, 392, 360     # ширина бічних панелей і мінімум центру


def _side_width(content: QWidget, base: int) -> int:
    """Ширина бічної колонки: не менша за вміст + вертикальну смугу прокрутки (інакше кнопки обрізаються)."""
    sb = QApplication.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent)
    return max(base, content.minimumSizeHint().width() + sb + 4)
# RIGHT_W враховує ширину вертикального скрола (~18px), щоб вміст правої панелі не обрізався
PROMO_ONLINE = True                                # панель курсів оновлює перелік із uait.org.ua (тести вимикають)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.resize(1480, 920)

        self.store = SettingsStore()
        self.registry = DeviceRegistry(self.store.get("manual_hosts"))
        self.batch = Batch()
        self.editor = None          # вікно редактора документів (одне)
        self.sheets = None          # вікно табличного редактора (одне)

        # Віджети
        self.device_panel = DevicePanel()
        self.scan_panel = ScanPanel(self.store)
        self.load_panel = LoadPanel()
        self.source_panel = SourcePanel(self.scan_panel, self.load_panel)
        self.adjust_panel = AdjustPanel()
        self.ocr_panel = OcrPanel()
        self.save_panel = SavePanel()
        self.view = ImageView()
        self.strip = PageStrip()

        # Контролери
        self.pages = PageController(self.batch, self.view, self.strip, self.adjust_panel)
        self.devices = DeviceController(self.registry, self.device_panel, self.scan_panel, self.store)
        self.scanner = ScanController(self, self.registry, self.device_panel, self.scan_panel, self.pages)
        self.devices.scan_busy = self.scanner.busy
        self.files = FileController(self, self.store, self.pages)
        self.files.insert_at = self.scan_panel.insert_at
        self.files.autoformat = self.load_panel.chk_format.isChecked
        self.ocr = OcrController(self, self.pages, self.ocr_panel)
        self.load_panel.open_requested.connect(self.files.import_dialog)
        self.setAcceptDrops(True)      # перетягування файлів із Провідника
        for c in (self.scanner, self.files, self.ocr):
            c.status.connect(self.statusBar().showMessage)
        self.pages.changed.connect(self._update_title)
        self.save_panel.save_requested.connect(self.files.export)
        self.files.exported.connect(self.ocr.refresh)
        self.pages.info.connect(self.statusBar().showMessage)
        self.ocr_panel.open_editor.connect(lambda: self.open_editor())
        self.ocr_panel.open_sheets.connect(lambda: self.open_sheets())
        self.ocr.open_text.connect(self.open_page_text)
        self.ocr.open_table.connect(self.open_page_table)
        self.adjust_panel.btn_crop.toggled.connect(lambda on: on and self.ocr_panel.btn_formula.setChecked(False))
        self.ocr_panel.btn_formula.toggled.connect(lambda on: on and self.adjust_panel.btn_crop.setChecked(False))

        self._toolbar()
        self._layout()
        icons.decorate(self, {
            "Сканувати": "scan", "Додати файли (PDF, JPG…)": "file-import", "Зберегти як…": "save", "Розпізнати": "ocr",
            "Розпізнати все": "layers", INTERTEXT: "file-lines", INTERTAB: "table", "Відкрити DOCX/XLSX…": "folder-open",
            "◀ Сторінку": "arrow-left", "Сторінку ▶": "arrow-right", "Видалити": "trash", "Очистити пакет": "broom",
            "Скасувати": "undo", "Повторити": "redo", "Вмістити": "expand", "Збільшити": "zoom-in", "Зменшити": "zoom-out",
            "Про програму": "info"})
        self.statusBar().showMessage("Готово")
        QTimer.singleShot(200, self.devices.refresh)      # перевірка сканерів одразу після запуску

    def _layout(self) -> None:
        left = QWidget()
        lv = QVBoxLayout(left)
        self.promo = PromoPanel(online=PROMO_ONLINE)     # курси УАІТ — перше, що бачить користувач
        lv.addWidget(self.promo)
        lv.addWidget(self.device_panel)
        lv.addWidget(self.source_panel)
        lv.addStretch(1)
        left_scroll = QScrollArea()
        left_scroll.setWidget(left)
        left_scroll.setWidgetResizable(True)
        left_scroll.setFixedWidth(_side_width(left, LEFT_W))   # бічні панелі нерухомі, центр масштабується
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        right = QWidget()
        rv_ = QVBoxLayout(right)
        rv_.addWidget(self.adjust_panel)
        rv_.addWidget(self.ocr_panel)
        rv_.addWidget(self.save_panel)
        rv_.addStretch(1)
        right_scroll = QScrollArea()
        right_scroll.setWidget(right)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        right_scroll.setWidgetResizable(True)
        right_scroll.setFixedWidth(_side_width(right, RIGHT_W))

        center = QWidget()
        cv = QVBoxLayout(center)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(0)
        cv.addWidget(self.view, 1)
        cv.addWidget(ZoomBar(self.view))
        cv.addWidget(self.strip)
        center.setMinimumWidth(CENTER_MIN_W)

        split = QWidget()
        sh = QHBoxLayout(split)
        sh.setContentsMargins(0, 0, 0, 0)
        sh.setSpacing(0)
        sh.addWidget(left_scroll)
        sh.addWidget(center, 1)
        sh.addWidget(right_scroll)
        self.setMinimumWidth(left_scroll.width() + CENTER_MIN_W + right_scroll.width())

        root = QWidget()
        rv = QVBoxLayout(root)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)
        rv.addWidget(Banner())
        rv.addWidget(self.toolbar)
        rv.addWidget(split, 1)
        self.setCentralWidget(root)

    def _toolbar(self) -> None:
        tb = QToolBar("Головна")
        tb.setMovable(False)
        self.toolbar = tb

        def act(text, slot, key=None, tip=None):
            a = QAction(text, self)
            a.triggered.connect(slot)
            if key:
                a.setShortcut(QKeySequence(key))
            if tip:
                a.setToolTip(tip)
            tb.addAction(a)
            return a

        act("Сканувати", self.scanner.start, "F5")
        act("Додати файли (PDF, JPG…)", self.files.import_dialog, "Ctrl+O")
        act("Зберегти як…", self.files.export, "Ctrl+S")
        tb.addSeparator()
        act("Текст → InterText", lambda: self.ocr.recognize_and_open("text"), "F7", "Розпізнати сторінку як текст і відкрити в InterText")
        act("Таблиця → InterTab", lambda: self.ocr.recognize_and_open("table"), "F6", "Розпізнати сторінку як таблицю і відкрити в InterTab")
        act("Розпізнати все", self.ocr.recognize_all, "Shift+F7")
        act(INTERTEXT, lambda: self.open_editor(), "F8", f"{INTERTEXT} — редактор документів (DOCX, PDF)")
        act(INTERTAB, lambda: self.open_sheets(), "F9", f"{INTERTAB} — табличний редактор (XLSX, CSV)")
        act("Відкрити DOCX/XLSX…", lambda: self.open_document_file(), "Ctrl+Shift+O",
            f"Відкрити документ DOCX у {INTERTEXT} або таблицю XLSX у {INTERTAB}")
        tb.addSeparator()
        act("◀ Сторінку", lambda: self.pages.move_current(-1), "Ctrl+Left")
        act("Сторінку ▶", lambda: self.pages.move_current(1), "Ctrl+Right")
        act("Видалити", lambda: self.pages.delete(self.strip.selected_rows()))
        act("Очистити пакет", self._clear)
        tb.addSeparator()
        act("Скасувати", self.pages.undo, "Ctrl+Z")
        act("Повторити", self.pages.redo, "Ctrl+Y")
        act("Вмістити", self.view.fit, "Ctrl+0")
        act("Збільшити", lambda: self.view.zoom(1.25), "Ctrl+=")
        act("Зменшити", lambda: self.view.zoom(0.8), "Ctrl+-")
        tb.addSeparator()
        act("Про програму", lambda: AboutDialog(self).exec())

    # ---------- редактори ----------
    def open_editor(self, html: str | None = None):
        from ..export.text_export import docs_to_html
        from .editor_window import EditorWindow
        if html is None:
            docs = [p.ocr.doc for p in self.batch.pages if p.ocr is not None]
            html = docs_to_html(docs) if docs else ""
        if self.editor is None:
            self.editor = EditorWindow(None, html, "Розпізнаний текст" if html else "Документ")
            self.editor.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        elif html:
            self.editor.set_html(html)
        self.editor.show()
        self.editor.raise_()
        self.editor.activateWindow()
        return self.editor

    def open_page_text(self, page) -> None:
        """Одна сторінка → InterText (документ зі структурою)."""
        from ..export.text_export import doc_to_html
        idx = self.batch.pages.index(page) + 1 if page in self.batch.pages else 0
        ed = self.open_editor(doc_to_html(page.ocr.doc) or "<p></p>")
        ed.setWindowTitle(f"Сторінка {idx} — {INTERTEXT} · {APP_NAME}")
        ed.statusBar().showMessage(f"Розпізнано сторінку {idx}: слів {len(page.ocr.words)}, довіра {page.ocr.mean_conf:.0f} %")

    def open_page_table(self, page) -> None:
        """Одна сторінка → InterTab (таблиця рядків і стовпців)."""
        from ..ocr.structure import page_as_table
        idx = self.batch.pages.index(page) + 1 if page in self.batch.pages else 0
        rows = page_as_table(page.ocr)
        sheets = {f"Стор {idx}": rows}
        for ti, t in enumerate(page.ocr.doc.tables, 1):
            if t.rows != rows:
                sheets[f"Стор {idx}, табл {ti}"] = t.rows
        w = self.open_sheets(sheets)
        w.statusBar().showMessage(f"Розпізнано сторінку {idx} як таблицю: рядків {len(rows)}")

    def open_document_file(self, path: str | None = None):
        """DOCX/HTML/TXT → InterText, XLSX/CSV → InterTab."""
        from pathlib import Path
        from PySide6.QtWidgets import QFileDialog
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, "Відкрити документ або таблицю", self.store.get("output_dir"),
                                                  "Документи й таблиці (*.docx *.xlsx *.csv *.html *.htm *.txt);;Усі файли (*)")
        if not path:
            return None
        p = Path(path)
        if p.suffix.lower() in (".xlsx", ".csv"):
            w = self.open_sheets({})
            w.load(p)
        else:
            w = self.open_editor("")
            w.load(p)
        return w

    def open_sheets(self, sheets: dict | None = None):
        from .sheet_window import SheetWindow
        if sheets is None:
            sheets = {}
            for pi, p in enumerate(self.batch.pages, 1):
                if p.ocr is None:
                    continue
                for ti, t in enumerate(p.ocr.doc.tables, 1):
                    sheets[f"Стор {pi}, табл {ti}"] = t.rows
        if self.sheets is None:
            self.sheets = SheetWindow(None, sheets or None)
        elif sheets:
            self.sheets.path = None
            self.sheets.tabs.clear()
            for name, rows in sheets.items():
                self.sheets.add_sheet(name, rows)
        self.sheets.show()
        self.sheets.raise_()
        self.sheets.activateWindow()
        return self.sheets

    def dragEnterEvent(self, e) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:
        from ..importing.loader import SUPPORTED
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        files = [f for f in paths if f.lower().endswith(tuple(SUPPORTED))]
        if files:
            self.files.import_files(files)
        for f in paths:
            if f.lower().endswith((".docx", ".xlsx", ".csv")):
                self.open_document_file(f)

    def _clear(self) -> None:
        from PySide6.QtWidgets import QMessageBox
        if len(self.batch) and QMessageBox.question(self, "Очистити", "Видалити всі сторінки пакета?") \
                == QMessageBox.StandardButton.Yes:
            self.pages.clear()

    def _update_title(self) -> None:
        n = len(self.batch)
        self.save_panel.set_count(n)
        self.setWindowTitle(f"{APP_NAME} — сторінок: {n}" if n else APP_NAME)

    def closeEvent(self, e) -> None:
        from PySide6.QtWidgets import QMessageBox
        if self.scanner.busy():
            self.scanner.cancel()
        if len(self.batch) and QMessageBox.question(
                self, "Вихід", "У пакеті є незбережені сторінки. Вийти?") != QMessageBox.StandardButton.Yes:
            e.ignore()
            return
        for w in (self.editor, self.sheets):
            if w is not None:
                w.close()
        e.accept()
