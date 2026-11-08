"""Табличний редактор (як Excel у простому варіанті): аркуші, рядок формул, формат комірок (жирний, курсив,
вирівнювання, заливка, колір), рядки/стовпці, об'єднання, сортування, автосума, заповнення вниз, пошук,
копіювання/вставка, відкриття і збереження XLSX/CSV."""

from __future__ import annotations

import csv
import io
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QColorDialog, QComboBox, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMainWindow,
                               QMessageBox, QTabWidget, QToolBar, QVBoxLayout, QWidget)

from ..config import APP_NAME, INTERTAB
from .logo import app_icon
from .banner import Banner
from . import sheet_print
from . import icons
from .ribbon import RIBBON_STYLE, Ribbon
from .sheet_model import Sheet, col_letters


SHEET_ICONS = {
    "Відкрити": "folder-open", "Зберегти": "save", "Зберегти як…": "table", "CSV": "file-lines", "+ Аркуш": "plus",
    "Перейменувати": "edit", "+ Рядок": "table-rows", "+ Стовпець": "table-cols", "− Рядок": "minus", "− Стовпець": "minus",
    "Σ Сума": "sigma", "Заповнити ↓": "fill", "Сортувати ↑": "sort-up", "Сортувати ↓": "sort-down", "Пошук": "search",
    "Ж": "bold", "К": "italic", "⯇": "align-left", "▣": "align-center", "⯈": "align-right", "Заливка": "paint",
    "Колір": "palette", "Очистити формат": "eraser", "Об'єднати": "merge", "Роз'єднати": "split", "Ширина ↔": "expand",
    "0,00": "hashtag", "%": "percent", "PDF": "file-pdf", "Друк": "print",
}


class SheetWindow(QMainWindow):
    def __init__(self, parent=None, sheets: dict[str, list[list[str]]] | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{INTERTAB} · {APP_NAME}")
        self.setWindowIcon(app_icon())
        self.resize(1280, 780)
        self.setStyleSheet(RIBBON_STYLE)
        self.path: Path | None = None
        self.tabs = QTabWidget()
        self.tabs.setObjectName("sheets")
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self._close_tab)
        self.tabs.setMovable(True)
        self.tabs.setTabPosition(QTabWidget.TabPosition.South)   # вкладки аркушів знизу, як в Excel
        from PySide6.QtWidgets import QVBoxLayout, QWidget
        central = QWidget()
        cl = QVBoxLayout(central)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        cl.addWidget(self.tabs, 1)
        self.setCentralWidget(central)
        self._ribbon()
        self._menu()
        self.ribbon.finish(self.menuBar())
        top = QWidget()
        tl = QVBoxLayout(top)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(0)
        tl.addWidget(Banner(INTERTAB, "ТАБЛИЧНИЙ РЕДАКТОР · XLSX · CSV · PDF · ДРУК · ФОРМУЛИ", compact=True))
        tl.addWidget(self.ribbon)
        tl.addWidget(self.formula_row)
        self.setMenuWidget(top)
        self.stats = QLabel("")
        self.statusBar().addPermanentWidget(self.stats)
        self.tabs.currentChanged.connect(lambda _i: self._sync_formula())
        for name, rows in (sheets or {"Аркуш1": []}).items():
            self.add_sheet(name, rows)
        self.statusBar().showMessage("Готово")

    # ---------- інтерфейс ----------
    def _act(self, tb, text, slot, key=None, tip=None):
        a = QAction(text, self)
        a.triggered.connect(slot)
        if key:
            a.setShortcut(QKeySequence(key))
        a.setToolTip(tip or text)
        tb.addAction(a)
        return a

    def _ribbon(self) -> None:
        """Власна стрічка InterTab: Комірки / Додати / Обчислення / Дані / Друк + рядок формул."""
        rb = Ribbon(self)
        self.ribbon = rb
        sh = lambda: self.sheet()
        # ---- Основне ----
        home = rb.tab("Комірки")
        g = home.group("Обмін")
        g.big("Вставити", "paste", lambda: sh().paste(), tip="Вставити (Ctrl+V)")
        g.column(g.action("Копіювати", "copy", lambda: sh().copy_sel(), tip="Копіювати (Ctrl+C)"),
                 g.action("Очистити", "eraser", lambda: sh().clear_selected(), tip="Очистити комірки (Delete)"))
        g = home.group("Текст")
        g.grid([[g.action("Жирний", "bold", lambda: sh().toggle_format("bold"), "Ctrl+B"),
                 g.action("Курсив", "italic", lambda: sh().toggle_format("italic"), "Ctrl+I"),
                 g.action("Колір тексту", "font", self._text_color)],
                [g.action("Заливка", "paint", self._fill_color, tip="Колір тла комірок"),
                 g.action("Очистити формат", "eraser", lambda: sh().set_format(bold=None, italic=None, align=None, bg=None, color=None, num=None)),
                 g.action("Ширина стовпців", "expand", lambda: sh().resizeColumnsToContents(), tip="Підібрати ширину стовпців")]])
        g = home.group("Розташування")
        g.small_row(g.action("Ліворуч", "align-left", lambda: sh().set_format(align=None)),
                    g.action("По центру", "align-center", lambda: sh().set_format(align="center")),
                    g.action("Праворуч", "align-right", lambda: sh().set_format(align="right")))
        g.big("Об'єднати", "merge", lambda: sh().merge_selected(), tip="Об'єднати виділені комірки")
        g.big("Роз'єднати", "split", lambda: sh().unmerge_current())
        g = home.group("Формат чисел")
        g.column(g.action("0,00 — два знаки", "hashtag", lambda: self._numfmt("0.00")),
                 g.action("% — відсотки", "percent", lambda: self._numfmt("%")),
                 g.action("1 000 — тисячі", "layers", lambda: self._numfmt("# ##0")))
        g = home.group("Рядки й стовпці")
        g.grid([[g.action("Вставити рядок", "table-rows", lambda: sh().insert_row(max(0, sh().currentRow()))),
                 g.action("Вставити стовпець", "table-cols", lambda: sh().insert_col(max(0, sh().currentColumn())))],
                [g.action("Видалити рядок", "minus", lambda: sh().currentRow() >= 0 and sh().delete_row(sh().currentRow())),
                 g.action("Видалити стовпець", "minus", lambda: sh().currentColumn() >= 0 and sh().delete_col(sh().currentColumn()))]])
        g = home.group("Швидкі дії")
        g.big("Автосума", "sigma", lambda: sh().autosum(), tip="Сума стовпця над поточною коміркою")
        g.column(g.action("Заповнити ↓", "fill", lambda: sh().fill_down(), "Ctrl+D", tip="Заповнити виділення верхньою коміркою"),
                 g.action("Сортувати", "sort-up", lambda: self._sort(False), tip="За поточним стовпцем ↑ (перший рядок — заголовок)"),
                 g.action("Пошук", "search", self._find, "Ctrl+F"))
        # ---- Вставлення ----
        ins = rb.tab("Додати")
        g = ins.group("Аркуші")
        g.big("Аркуш", "plus", lambda: self.add_sheet(f"Аркуш{self.tabs.count() + 1}", []), tip="Додати аркуш")
        g.big("Перейменувати", "edit", self._rename)
        g = ins.group("Діаграми")
        g.big("Діаграма", "layers", self._insert_chart, tip="Стовпчикова, горизонтальна, лінійна або кругова — з виділеного діапазону")
        g.big("Діаграми аркуша", "eye", self._list_charts, tip="Переглянути, зберегти PNG або видалити графіки аркуша")
        g = ins.group("Вставка")
        g.big("Рядок", "table-rows", lambda: sh().insert_row(max(0, sh().currentRow())), tip="Вставити рядок перед поточним")
        g.big("Стовпець", "table-cols", lambda: sh().insert_col(max(0, sh().currentColumn())), tip="Вставити стовпець перед поточним")
        # ---- Формули ----
        fm = rb.tab("Обчислення")
        g = fm.group("Функції")
        g.big("Автосума", "sigma", lambda: sh().autosum())
        self.cb_func = QComboBox()
        self.cb_func.setToolTip("Вставити функцію у рядок формул")
        self.cb_func.addItem("Функція…")
        for f_ in ("SUM", "AVERAGE", "MIN", "MAX", "COUNT", "COUNTA", "IF", "SUMIF", "COUNTIF", "AVERAGEIF", "ROUND", "INT", "ABS",
                   "SQRT", "POWER", "MOD", "PRODUCT", "AND", "OR", "NOT", "LEN", "CONCAT", "UPPER", "LOWER", "TRIM", "LEFT",
                   "RIGHT", "MID", "VLOOKUP", "ISBLANK", "ISNUMBER", "TODAY", "PI", "RAND"):
            self.cb_func.addItem(f_)
        self.cb_func.activated.connect(self._insert_func)
        self.cb_func.setFixedWidth(130)
        g.widget(self.cb_func)
        hint = QLabel("Формули починаються зі знака «=». Діапазон: A1:B5. Роздільник аргументів: ; або ,")
        hint.setObjectName("hint")
        g.widget(hint)
        # ---- Дані ----
        dt = rb.tab("Дані")
        g = dt.group("Порядок")
        g.big("За зростанням", "sort-up", lambda: self._sort(False), tip="Сортувати за поточним стовпцем ↑")
        g.big("За спаданням", "sort-down", lambda: self._sort(True), tip="Сортувати за поточним стовпцем ↓")
        g = dt.group("Заповнення")
        g.big("Заповнити ↓", "fill", lambda: sh().fill_down(), "Ctrl+D")
        g = dt.group("Експорт")
        g.big("CSV", "file-lines", self.save_csv, tip="Поточний аркуш у CSV")
        # ---- Подання / Друк ----
        pv = rb.tab("Друк")
        g = pv.group("Файл")
        g.big("Відкрити", "folder-open", self.open_file, "Ctrl+O", tip="Відкрити XLSX або CSV")
        g.big("Зберегти", "save", self.save, "Ctrl+S", tip="Зберегти XLSX")
        g.big("Зберегти як", "table", lambda: self.save_as(), "Ctrl+Shift+S")
        g = pv.group("Папір і PDF")
        g.big("Перегляд", "eye", lambda: self.print_(preview=True), tip="Попередній перегляд")
        g.big("Друк", "print", self.print_, "Ctrl+P")
        g.big("PDF", "file-pdf", self.save_pdf, tip="Зберегти таблицю у PDF")
        # ---- рядок формул ----
        self.formula_row = QWidget()
        self.formula_row.setObjectName("formularow")
        fr = QHBoxLayout(self.formula_row)
        fr.setContentsMargins(8, 4, 8, 4)
        fr.setSpacing(6)
        self.namebox = QLineEdit()
        self.namebox.setObjectName("namebox")
        self.namebox.setToolTip("Адреса комірки — введіть, напр. B5, і натисніть Enter, щоб перейти")
        self.namebox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.namebox.returnPressed.connect(self._goto_cell)
        fx = QLabel("fx")
        fx.setObjectName("fx")
        self.formula = QLineEdit()
        self.formula.setObjectName("formulabar")
        self.formula.setPlaceholderText("Вміст комірки / формула: =SUM(A1:A5), =IF(B2>10;\"так\";\"ні\")")
        self.formula.returnPressed.connect(self._apply_formula)
        fr.addWidget(self.namebox)
        fr.addWidget(fx)
        fr.addWidget(self.formula, 1)

    def _insert_chart(self, spec=None):
        from .charts import ChartDialog, ChartSpec
        s = self.sheet()
        if spec is None or isinstance(spec, bool):      # із QAction приходить checked=False
            sel = s._sel_rect()
            if not sel or (sel[2] - sel[0] < 1 and sel[3] - sel[1] < 1):
                data = s.data()
                if not data:
                    QMessageBox.information(self, "Графік", "Виділіть діапазон із даними (напр. A1:C5).")
                    return None
                sel = (0, 0, len(data) - 1, max(len(r) for r in data) - 1)
            r0, c0, r1, c1 = sel
            spec = ChartSpec(r0=r0, c0=c0, r1=r1, c1=c1, anchor=f"{col_letters(c1 + 2)}{r0 + 1}")
        d = ChartDialog(self, s, spec)
        if not d.exec():
            return None
        spec = d.result_spec()
        s.charts.append(spec)
        self._show_chart(spec)
        self.statusBar().showMessage(f"Графік додано ({spec.kind}); у файлі XLSX він збережеться як діаграма")
        return spec

    def _show_chart(self, spec) -> None:
        """Плаваюче вікно з графіком: зберегти PNG, копіювати, вставити в InterText."""
        from PySide6.QtWidgets import QApplication, QDialog, QHBoxLayout, QPushButton, QVBoxLayout
        from PySide6.QtGui import QPixmap
        w = QDialog(self)
        w.setWindowTitle(spec.title or spec.kind)
        lab = QLabel()
        lab.setPixmap(QPixmap.fromImage(spec.image))
        row = QHBoxLayout()
        b1 = QPushButton("Зберегти PNG…")
        b1.clicked.connect(lambda: (lambda p: p and spec.image.save(p))(QFileDialog.getSaveFileName(w, "Зберегти графік", "графік.png", "PNG (*.png)")[0]))
        b2 = QPushButton("Копіювати")
        b2.clicked.connect(lambda: QApplication.clipboard().setImage(spec.image))
        b3 = QPushButton("В InterText")
        b3.clicked.connect(lambda: self._chart_to_editor(spec))
        for b in (b1, b2, b3):
            row.addWidget(b)
        lay = QVBoxLayout(w)
        lay.addWidget(lab)
        lay.addLayout(row)
        w.setModal(False)
        w.show()
        self._chart_windows = getattr(self, "_chart_windows", []) + [w]

    def _chart_to_editor(self, spec) -> None:
        main = self.parent()
        ed = main.open_editor("") if main is not None and hasattr(main, "open_editor") else None
        if ed is None:
            from .editor_window import EditorWindow
            ed = EditorWindow(None, "", "Документ")
            self._editor = ed
            ed.show()
        ed.insert_image(spec.image)
        ed.raise_()

    def _list_charts(self) -> None:
        s = self.sheet()
        if not s.charts:
            QMessageBox.information(self, "Графіки", "На цьому аркуші ще немає графіків.")
            return
        names = [f"{i + 1}. {c.kind} — {c.title or 'без назви'} ({col_letters(c.c0)}{c.r0 + 1}:{col_letters(c.c1)}{c.r1 + 1})" for i, c in enumerate(s.charts)]
        name, ok = QInputDialog.getItem(self, "Графіки аркуша", "Оберіть графік:", names, 0, False)
        if ok:
            i = names.index(name)
            act, ok2 = QInputDialog.getItem(self, "Графік", "Дія:", ["Показати", "Змінити", "Видалити"], 0, False)
            if ok2 and act == "Показати":
                self._show_chart(s.charts[i])
            elif ok2 and act == "Змінити":
                spec = s.charts.pop(i)
                self._insert_chart(spec)
            elif ok2 and act == "Видалити":
                s.charts.pop(i)

    def _insert_func(self, idx: int) -> None:
        if idx > 0:
            name = self.cb_func.itemText(idx)
            cur = self.formula.text()
            self.formula.setText((cur if cur.startswith("=") else "=") + name + "()")
            self.formula.setFocus()
            self.formula.setCursorPosition(len(self.formula.text()) - 1)
        self.cb_func.setCurrentIndex(0)

    def _menu(self) -> None:
        m = self.menuBar().addMenu("Файл")
        for text, slot, key in (("Новий", self._new, "Ctrl+N"), ("Відкрити…", self.open_file, "Ctrl+O"), ("Зберегти", self.save, "Ctrl+S"),
                                ("Зберегти як…", lambda: self.save_as(), None), ("Аркуш у CSV…", self.save_csv, None),
                                ("Зберегти як PDF…", self.save_pdf, None), ("Попередній перегляд…", lambda: self.print_(preview=True), None),
                                ("Друк…", self.print_, "Ctrl+P"), ("Закрити", self.close, "Ctrl+W")):
            self._act(m, text, slot, key)
        e = self.menuBar().addMenu("Правка")
        for text, slot, key in (("Копіювати", lambda: self.sheet().copy_sel(), None), ("Вставити", lambda: self.sheet().paste(), None),
                                ("Очистити комірки", lambda: self.sheet().clear_selected(), "Delete"),
                                ("Пошук…", self._find, None)):
            self._act(e, text, slot, key)

    # ---------- аркуші ----------
    def sheet(self) -> Sheet:
        return self.tabs.currentWidget()

    def add_sheet(self, name: str, rows: list[list[str]], fmts: dict | None = None) -> Sheet:
        s = Sheet()
        s.set_data(rows, fmts)
        s.currentCellChanged.connect(lambda *_: self._sync_formula())
        s.itemSelectionChanged.connect(self._sync_formula)
        self.tabs.addTab(s, name)
        self.tabs.setCurrentWidget(s)
        return s

    def sheets(self, computed: bool = True) -> dict[str, list[list[str]]]:
        out = {}
        for i in range(self.tabs.count()):
            w: Sheet = self.tabs.widget(i)
            out[self.tabs.tabText(i)] = w.values() if computed else w.data()
        return out

    def _close_tab(self, i: int) -> None:
        if self.tabs.count() > 1:
            self.tabs.removeTab(i)

    def _rename(self) -> None:
        name, ok = QInputDialog.getText(self, "Аркуш", "Назва аркуша:", text=self.tabs.tabText(self.tabs.currentIndex()))
        if ok and name.strip():
            self.tabs.setTabText(self.tabs.currentIndex(), name.strip()[:31])

    def _sort(self, desc: bool) -> None:
        s = self.sheet()
        if s.currentColumn() >= 0:
            s.sort_by_column(s.currentColumn(), desc)

    def _find(self) -> None:
        text, ok = QInputDialog.getText(self, "Пошук", "Знайти:")
        if ok and not self.sheet().find_next(text):
            self.statusBar().showMessage("Не знайдено")

    def _numfmt(self, fmt: str) -> None:
        s = self.sheet()
        cur = s.fmt.get((s.currentRow(), s.currentColumn()), {}).get("num")
        s.set_format(num=None if cur == fmt else fmt)

    def _fill_color(self) -> None:
        c = QColorDialog.getColor(parent=self, title="Заливка")
        if c.isValid():
            self.sheet().set_format(bg=c.name())

    def _text_color(self) -> None:
        c = QColorDialog.getColor(parent=self, title="Колір тексту")
        if c.isValid():
            self.sheet().set_format(color=c.name())

    def set_cell(self, r: int, c: int, text: str) -> None:
        self.sheet().set_cell(r, c, text)
        self._sync_formula()

    def _sync_formula(self) -> None:
        s = self.sheet()
        if s is None:
            return
        self.formula.setText(s.raw.get((s.currentRow(), s.currentColumn()), ""))
        if s.currentRow() >= 0:
            ref = f"{col_letters(max(0, s.currentColumn()))}{s.currentRow() + 1}"
            self.namebox.setText(ref)
            self.statusBar().showMessage(ref)
        nums = [v for v in (s.value(r, c) for r, c in s.selected_cells()) if isinstance(v, (int, float)) and not isinstance(v, bool)]
        self.stats.setText(f"Сума: {sum(nums):g}   Середнє: {sum(nums) / len(nums):g}   Кількість: {len(nums)}" if len(nums) > 1 else "")

    def _goto_cell(self) -> None:
        """Перехід до комірки за адресою з поля імені (напр. B5)."""
        import re
        m = re.fullmatch(r"\s*([A-Za-zА-Яа-я]+)(\d+)\s*", self.namebox.text())
        s = self.sheet()
        if not m or s is None:
            self._sync_formula()
            return
        letters = m.group(1).upper()
        col = 0
        for ch in letters:
            col = col * 26 + (ord(ch) - 64)
        col -= 1
        row = int(m.group(2)) - 1
        if 0 <= row < s.rowCount() and 0 <= col < s.columnCount():
            s.setCurrentCell(row, col)
            s.setFocus()

    def _apply_formula(self) -> None:
        s = self.sheet()
        if s.currentRow() >= 0 and s.currentColumn() >= 0:
            self.set_cell(s.currentRow(), s.currentColumn(), self.formula.text())

    # ---------- файли ----------
    def open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Відкрити таблицю", "", "Таблиці (*.xlsx *.csv);;Усі файли (*)")
        if path:
            self.load(Path(path))

    def load(self, path: Path) -> None:
        try:
            if path.suffix.lower() == ".csv":
                text = path.read_text(encoding="utf-8-sig", errors="replace")
                dialect = csv.Sniffer().sniff(text[:2000], delimiters=";,\t") if text.strip() else csv.excel
                sheets = {path.stem[:31]: ([list(r) for r in csv.reader(io.StringIO(text), dialect)], {})}
            else:
                from ..export.xlsx_export import load_xlsx
                sheets = load_xlsx(path, with_formats=True)
        except Exception as e:
            QMessageBox.critical(self, "Відкрити", f"Не вдалося відкрити {path.name}:\n{e}")
            return
        self.tabs.clear()
        for name, (rows, fmts) in sheets.items():
            self.add_sheet(name, rows, fmts)
        self.tabs.setCurrentIndex(0)
        self.path = path
        if path.suffix.lower() == ".xlsx":
            from .editor_window import adaptation_notice
            adaptation_notice(self, "XLSX")
        self.setWindowTitle(f"{path.name} — {INTERTAB} · {APP_NAME}")

    def save(self) -> None:
        if self.path and self.path.suffix.lower() == ".xlsx":
            self.save_to(self.path)
        else:
            self.save_as()

    def save_as(self) -> None:
        start = str(self.path.with_suffix(".xlsx")) if self.path else "таблиця.xlsx"
        path, _ = QFileDialog.getSaveFileName(self, "Зберегти як", start, "Таблиця XLSX (*.xlsx)")
        if path:
            self.save_to(Path(path))

    def save_to(self, path: Path) -> Path | None:
        from ..export.xlsx_export import save_sheets_xlsx
        try:
            sheets = {}
            for i in range(self.tabs.count()):
                w: Sheet = self.tabs.widget(i)
                sheets[self.tabs.tabText(i)] = (w.data(), w.values(), w.fmt, w.charts)
            save_sheets_xlsx(sheets, path)
        except Exception as e:
            QMessageBox.critical(self, "Зберегти", f"Не вдалося зберегти:\n{e}")
            return None
        self.path = path
        self.statusBar().showMessage(f"Збережено: {path}")
        return path

    def _new(self) -> None:
        self.tabs.clear()
        self.add_sheet("Аркуш1", [])
        self.path = None
        self.setWindowTitle(f"{INTERTAB} · {APP_NAME}")

    def _print_sheets(self, all_sheets: bool) -> list:
        if all_sheets:
            return [(self.tabs.tabText(i), self.tabs.widget(i)) for i in range(self.tabs.count())]
        return [(self.tabs.tabText(self.tabs.currentIndex()), self.sheet())]

    def save_pdf(self, path: Path | None = None, landscape: bool = False, all_sheets: bool = False) -> Path | None:
        if not path or isinstance(path, bool):           # із QAction приходить checked=False
            path = None
            d = sheet_print.PrintDialog(self, self.tabs.count())
            if not d.exec():
                return None
            landscape, all_sheets = d.landscape(), d.all_sheets()
            opts = dict(grid=d.grid.isChecked(), title=d.title.isChecked(), headers=d.headers.isChecked())
            start = str(self.path.with_suffix(".pdf")) if self.path else "таблиця.pdf"
            p, _ = QFileDialog.getSaveFileName(self, "Зберегти як PDF", start, "PDF (*.pdf)")
            if not p:
                return None
            path = Path(p)
        else:
            opts = {}
        try:
            sheet_print.save_pdf(self._print_sheets(all_sheets), path, landscape, **opts)
        except Exception as e:
            QMessageBox.critical(self, "PDF", f"Не вдалося зберегти:\n{e}")
            return None
        self.statusBar().showMessage(f"PDF: {path}")
        return path

    def print_(self, preview: bool = False) -> None:
        d = sheet_print.PrintDialog(self, self.tabs.count())
        if d.exec():
            sheet_print.print_sheets(self, self._print_sheets(d.all_sheets()), d.landscape(), preview,
                                     grid=d.grid.isChecked(), title=d.title.isChecked(), headers=d.headers.isChecked())

    def save_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Аркуш у CSV", "аркуш.csv", "CSV (*.csv)")
        if path:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                csv.writer(f, delimiter=";").writerows(self.sheet().values())
            self.statusBar().showMessage(f"Збережено: {path}")
