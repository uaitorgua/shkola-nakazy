"""Крок 4 · Розпізнати: «як текст → InterText» або «як таблицю → InterTab», увесь пакет, формула з ділянки,
прогрес, попередній перегляд тексту. Для вчителя-початківця — підказка «що далі»."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGridLayout, QGroupBox, QLabel, QProgressBar, QPushButton, QTextEdit, QVBoxLayout


class OcrPanel(QGroupBox):
    recognize_as = Signal(str)          # "text" | "table" — розпізнати поточну сторінку й відкрити у субдодатку
    recognize_all = Signal()
    formula_mode = Signal(bool)
    open_editor = Signal()
    open_sheets = Signal()
    text_edited = Signal(str)

    def __init__(self) -> None:
        super().__init__("4 · Розпізнати й відкрити")
        hint = QLabel("Що на сторінці? Оберіть — програма розпізнає текст і одразу відкриє його в редакторі.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        self.btn_text = QPushButton("Текст → InterText")
        self.btn_text.setObjectName("primary")
        self.btn_text.setToolTip("Розпізнати сторінку як документ (абзаци, заголовки, списки, таблиці) і відкрити в InterText (F7)")
        self.btn_table = QPushButton("Таблиця → InterTab")
        self.btn_table.setObjectName("accent")
        self.btn_table.setToolTip("Розпізнати сторінку як таблицю (рядки і стовпці) і відкрити в InterTab (F6)")
        self.btn_all = QPushButton("Увесь пакет")
        self.btn_all.setToolTip("Розпізнати всі сторінки (Shift+F7) — потім «Зберегти як…» DOCX/XLSX/PDF")
        self.btn_formula = QPushButton("∑ Формула з ділянки")
        self.btn_formula.setCheckable(True)
        self.btn_formula.setToolTip("Увімкніть і обведіть формулу мишею на сторінці — отримаєте LaTeX і текст")
        self.btn_text.clicked.connect(lambda: self.recognize_as.emit("text"))
        self.btn_table.clicked.connect(lambda: self.recognize_as.emit("table"))
        self.btn_all.clicked.connect(self.recognize_all)
        self.btn_formula.toggled.connect(self.formula_mode)
        # сумісність зі старими викликами
        self.btn_page = self.btn_text

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        self.info = QLabel("Сторінку ще не розпізнано")
        self.info.setObjectName("hint")
        self.info.setWordWrap(True)

        self.text = QTextEdit()
        self.text.setPlaceholderText("Тут з'явиться розпізнаний текст. Його можна виправити перед збереженням.")
        self.text.setAcceptRichText(False)
        self.text.setMinimumHeight(150)
        self.text.textChanged.connect(lambda: self.text_edited.emit(self.text.toPlainText()))

        self.btn_editor = QPushButton("Усі розпізнані сторінки → InterText")
        self.btn_editor.setToolTip("Відкрити весь пакет як один документ у InterText")
        self.btn_sheets = QPushButton("Знайдені таблиці → InterTab")
        self.btn_sheets.setToolTip("Усі розпізнані таблиці пакета — аркушами в InterTab")
        self.btn_editor.clicked.connect(self.open_editor)
        self.btn_sheets.clicked.connect(self.open_sheets)

        grid = QGridLayout()
        grid.addWidget(self.btn_text, 0, 0)
        grid.addWidget(self.btn_table, 0, 1)
        grid.addWidget(self.btn_all, 1, 0)
        grid.addWidget(self.btn_formula, 1, 1)
        lay = QVBoxLayout(self)
        lay.addWidget(hint)
        lay.addLayout(grid)
        lay.addWidget(self.progress)
        lay.addWidget(self.info)
        lay.addWidget(self.text)
        lay.addWidget(self.btn_editor)
        lay.addWidget(self.btn_sheets)
        self.set_busy(False)
        self.set_count(0)

    def set_busy(self, busy: bool, done: int = 0, total: int = 0) -> None:
        for b in (self.btn_text, self.btn_table, self.btn_all):
            b.setEnabled(not busy and getattr(self, "_count", 0) > 0)
        self.progress.setRange(0, max(1, total))
        self.progress.setValue(done if busy else 0)

    def set_count(self, n: int) -> None:
        self._count = n
        for b in (self.btn_text, self.btn_table, self.btn_all, self.btn_formula):
            b.setEnabled(n > 0)
        if n == 0:
            self.btn_formula.setChecked(False)

    def show_page(self, ocr, has_doc: bool) -> None:
        self.text.blockSignals(True)
        if ocr is None:
            self.text.setPlainText("")
            self.info.setText("Сторінку ще не розпізнано")
        else:
            self.text.setPlainText(ocr.text)
            tables = len(ocr.doc.tables)
            self.info.setText(f"Слів: {len(ocr.words)}, довіра {ocr.mean_conf:.0f} %, таблиць: {tables}")
        self.text.blockSignals(False)
        self.btn_sheets.setEnabled(has_doc)
        self.btn_editor.setEnabled(has_doc)
