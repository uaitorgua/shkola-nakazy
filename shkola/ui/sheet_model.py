"""Аркуш табличного редактора: комірки, формули, формат комірок, об'єднання, сортування, копіювання/вставка.

Формули: =A1+B2*2, діапазони A1:B5, функції SUM, AVERAGE, MIN, MAX, COUNT, COUNTA, ABS, ROUND, INT, SQRT, POWER,
IF, AND, OR, NOT, LEN, CONCAT, UPPER, LOWER, TODAY. Обчислення без eval — через ast із білим списком.
"""

from __future__ import annotations

import ast
import datetime
import math
import operator
import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont, QKeySequence
from PySide6.QtWidgets import QApplication, QTableWidget, QTableWidgetItem

REF_RE = re.compile(r"\$?([A-Z]{1,3})\$?(\d{1,6})")
RANGE_RE = re.compile(r"\$?([A-Z]{1,3})\$?(\d{1,6}):\$?([A-Z]{1,3})\$?(\d{1,6})")
STR_RE = re.compile(r'"[^"]*"')
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos, ast.Mod: operator.mod}
_CMP = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt, ast.LtE: operator.le,
        ast.Gt: operator.gt, ast.GtE: operator.ge}


def _flat(args):
    out = []
    for a in args:
        if isinstance(a, list):
            for v in a:
                if isinstance(v, list):
                    out.extend(x for x in v if isinstance(x, (int, float)) and not isinstance(x, bool))
                elif isinstance(v, (int, float)) and not isinstance(v, bool):
                    out.append(v)
        elif isinstance(a, (int, float)) and not isinstance(a, bool):
            out.append(a)
    return out


def _flat_all(args):
    out = []
    for a in args:
        out.extend(v for v in a if v not in (None, "")) if isinstance(a, list) else out.append(a)
    return out


_FUNCS = {
    "SUM": lambda *a: sum(_flat(a)),
    "AVERAGE": lambda *a: (sum(_flat(a)) / len(_flat(a))) if _flat(a) else 0,
    "MIN": lambda *a: min(_flat(a)) if _flat(a) else 0,
    "MAX": lambda *a: max(_flat(a)) if _flat(a) else 0,
    "COUNT": lambda *a: len(_flat(a)),
    "COUNTA": lambda *a: len(_flat_all(a)),
    "ABS": abs, "ROUND": lambda x, n=0: round(x, int(n)), "INT": lambda x: int(math.floor(x)),
    "SQRT": math.sqrt, "POWER": lambda x, y: x ** y,
    "IF": lambda c, a, b="": a if c else b,
    "AND": lambda *a: all(a), "OR": lambda *a: any(a), "NOT": lambda a: not a,
    "LEN": lambda s: len(str(s)), "CONCAT": lambda *a: "".join(str(x) for x in _flat_all(a)),
    "UPPER": lambda s: str(s).upper(), "LOWER": lambda s: str(s).lower(),
    "TODAY": lambda: datetime.date.today().strftime("%d.%m.%Y"),
    "PRODUCT": lambda *a: math.prod(_flat(a)), "MOD": lambda a, b: a % b, "TRIM": lambda s: " ".join(str(s).split()),
    "LEFT": lambda s, n=1: str(s)[:int(n)], "RIGHT": lambda s, n=1: str(s)[-int(n):] if int(n) else "",
    "MID": lambda s, a, n: str(s)[int(a) - 1:int(a) - 1 + int(n)],
    "SUMIF": lambda rng, crit, sums=None: sum(v for v, m in zip((sums or rng), rng) if _match(m, crit) and isinstance(v, (int, float))),
    "COUNTIF": lambda rng, crit: sum(1 for m in rng if _match(m, crit)),
    "AVERAGEIF": lambda rng, crit, avgs=None: (lambda xs: sum(xs) / len(xs) if xs else 0)(
        [v for v, m in zip((avgs or rng), rng) if _match(m, crit) and isinstance(v, (int, float))]),
    "VLOOKUP": lambda key, tbl, col, _exact=0: next((row[int(col) - 1] for row in tbl if row and row[0] == key), "#Н/Д"),
    "ISBLANK": lambda v: v in (None, ""), "ISNUMBER": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "PI": lambda: math.pi, "RAND": lambda: __import__("random").random(),
}


def _match(v, crit) -> bool:
    """Критерій SUMIF/COUNTIF: число, текст, або ">10", "<=5", "<>x"."""
    if isinstance(crit, str) and crit[:2] in ("<=", ">=", "<>"):
        op, val = crit[:2], crit[2:]
    elif isinstance(crit, str) and crit[:1] in ("<", ">", "="):
        op, val = crit[:1], crit[1:]
    else:
        op, val = "=", crit
    val = to_number(val) if isinstance(val, str) else val
    if v is None:
        return False
    try:
        return {"=": v == val, "<>": v != val, "<": v < val, ">": v > val, "<=": v <= val, ">=": v >= val}[op]
    except TypeError:
        return False


def col_index(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def col_letters(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def to_number(s: str):
    t = (s or "").strip().replace(",", ".").replace(" ", "")
    try:
        return int(t) if re.fullmatch(r"-?\d+", t) else float(t)
    except ValueError:
        return s


def fmt_value(v, num: str | None = None) -> str:
    if v is None:
        return ""
    if num and isinstance(v, (int, float)) and not isinstance(v, bool):
        if num == "%":
            return f"{v * 100:.1f} %".replace(".", ",")
        if num == "0.00":
            return f"{v:.2f}".replace(".", ",")
        if num == "# ##0":
            return f"{v:,.0f}".replace(",", " ")
        if num == "0":
            return f"{round(v):d}"
    if isinstance(v, bool):
        return "ІСТИНА" if v else "ХИБНІСТЬ"
    if isinstance(v, float):
        return f"{v:.10g}".replace(".", ",")
    return str(v)


class Sheet(QTableWidget):
    """raw — введений текст/формула; fmt — формат комірки {bold, italic, align, bg, color}."""

    MIN_ROWS, MIN_COLS = 100, 26        # типово A–Z і 100 рядків; край росте автоматично

    def __init__(self, rows: int = 100, cols: int = 26) -> None:
        super().__init__(rows, cols)
        self.setHorizontalHeaderLabels([col_letters(i) for i in range(cols)])
        self.raw: dict[tuple[int, int], str] = {}
        self.fmt: dict[tuple[int, int], dict] = {}
        self.charts: list = []                 # ChartSpec — графіки аркуша (у XLSX стають діаграмами)
        self.itemChanged.connect(self._changed)
        self._lock = False
        # зміна розміру перетягуванням заголовків; подвійний клік по межі — за вмістом
        from PySide6.QtWidgets import QHeaderView
        hh, vh = self.horizontalHeader(), self.verticalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        vh.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hh.setDefaultSectionSize(90)
        hh.setMinimumSectionSize(24)
        vh.setDefaultSectionSize(26)
        vh.setMinimumSectionSize(16)
        hh.setSectionsClickable(True)
        vh.setSectionsClickable(True)
        hh.sectionDoubleClicked.connect(self.resizeColumnToContents)
        self.currentCellChanged.connect(self._grow_if_edge)

    def _grow_if_edge(self, r: int, c: int, *_):
        """Біля краю додаємо ще рядків/стовпців — аркуш «нескінченний», як в Excel."""
        if r >= self.rowCount() - 3:
            self.setRowCount(self.rowCount() + 50)
        if c >= self.columnCount() - 2:
            self.setColumnCount(self.columnCount() + 10)
            self.setHorizontalHeaderLabels([col_letters(i) for i in range(self.columnCount())])

    # ---------- дані ----------
    def set_data(self, rows: list[list[str]], fmts: dict | None = None) -> None:
        self._lock = True
        self.clearContents()
        self.clearSpans()
        self.setRowCount(max(len(rows) + 20, self.MIN_ROWS))
        ncols = max((len(r) for r in rows), default=0)
        self.setColumnCount(max(ncols + 5, self.MIN_COLS))
        self.setHorizontalHeaderLabels([col_letters(i) for i in range(self.columnCount())])
        self.raw.clear()
        fmts = dict(fmts or {})
        merges = fmts.pop("__merges__", [])
        widths = fmts.pop("__widths__", {})
        xcharts = fmts.pop("__charts__", [])
        self.fmt = fmts
        for i, row in enumerate(rows):
            for j, v in enumerate(row):
                if v != "":
                    self.raw[(i, j)] = v
                self.setItem(i, j, QTableWidgetItem(v))
        self._lock = False
        self.recalc()
        for j in range(self.columnCount()):          # ширина за вмістом, але не вужче за типову
            self.resizeColumnToContents(j)
            self.setColumnWidth(j, max(90, min(320, self.columnWidth(j) + 8)))
        for c, px in widths.items():                  # ширини з Excel
            if 0 <= c < self.columnCount():
                self.setColumnWidth(c, max(24, min(600, px)))
        for r0, c0, nr, nc in merges:                 # об'єднані комірки з Excel
            if r0 < self.rowCount() and c0 < self.columnCount() and (nr > 1 or nc > 1):
                self.setSpan(r0, c0, nr, nc)
        if xcharts:                                   # діаграми Excel → внутрішні графіки
            from .charts import ChartSpec, extract, render
            self.charts = []
            for x in xcharts:
                spec = ChartSpec(kind=x.kind, title=x.title, r0=x.r0, c0=x.c0, r1=x.r1, c1=x.c1,
                                 header_row=x.header_row, label_col=x.label_col, anchor=x.anchor)
                cats, series = extract(self, spec)
                spec.image = render(cats, series, spec.kind, spec.title)
                self.charts.append(spec)

    def data(self) -> list[list[str]]:
        used = [(r, c) for (r, c), v in self.raw.items() if v != ""]
        if not used:
            return []
        last_r, last_c = max(r for r, _ in used), max(c for _, c in used)
        return [[self.raw.get((i, j), "") for j in range(last_c + 1)] for i in range(last_r + 1)]

    def values(self) -> list[list[str]]:
        return [[fmt_value(self.value(i, j)) for j in range(len(row))] for i, row in enumerate(self.data())]

    def set_cell(self, r: int, c: int, text: str) -> None:
        if r >= self.rowCount():
            self.setRowCount(r + 1)
        if c >= self.columnCount():
            self.setColumnCount(c + 1)
            self.setHorizontalHeaderLabels([col_letters(i) for i in range(self.columnCount())])
        self._lock = True
        self.raw[(r, c)] = text
        it = self.item(r, c) or QTableWidgetItem()
        if not self.item(r, c):
            self.setItem(r, c, it)
        it.setText(text)
        self._lock = False
        self.recalc()

    def _changed(self, item: QTableWidgetItem) -> None:
        if self._lock:
            return
        self.raw[(item.row(), item.column())] = item.text()
        self.recalc()

    def edit(self, index, trigger=None, event=None):      # редагування показує формулу/сирий текст
        if trigger is not None and index.isValid():
            raw = self.raw.get((index.row(), index.column()), "")
            it = self.item(index.row(), index.column())
            if it is not None and it.text() != raw:
                self._lock = True
                it.setText(raw)
                self._lock = False
        return super().edit(index, trigger, event) if trigger is not None else super().edit(index)

    # ---------- формули ----------
    def value(self, r: int, c: int, depth: int = 0):
        s = self.raw.get((r, c), "")
        if s.startswith("=") and depth < 50:
            try:
                return self.evaluate(s[1:], depth + 1)
            except Exception:
                return "#ПОМИЛКА"
        v = to_number(s)
        return v if v != "" else None

    def evaluate(self, expr: str, depth: int):
        strings: list[str] = []

        def keep(m):
            strings.append(m.group(0))
            return f"@@{len(strings) - 1}@@"

        expr = STR_RE.sub(keep, expr).replace(";", ",")
        expr = re.sub(r"[^\"]+", lambda m: m.group(0).upper(), expr)

        def rng(m):
            c0, r0, c1, r1 = col_index(m.group(1)), int(m.group(2)) - 1, col_index(m.group(3)), int(m.group(4)) - 1
            rows = [[self.value(r, c, depth) for c in range(min(c0, c1), max(c0, c1) + 1)]
                    for r in range(min(r0, r1), max(r0, r1) + 1)]
            if len(rows) > 1 and len(rows[0]) > 1:        # двовимірний діапазон — матриця (VLOOKUP)
                return "[" + ",".join("[" + ",".join(repr(v) for v in row) + "]" for row in rows) + "]"
            return "[" + ",".join(repr(v) for row in rows for v in row) + "]"

        expr = RANGE_RE.sub(rng, expr)
        expr = REF_RE.sub(lambda m: repr(self.value(int(m.group(2)) - 1, col_index(m.group(1)), depth)), expr)
        expr = expr.replace("^", "**").replace("<>", "!=")
        expr = re.sub(r"(?<![<>!=])=(?!=)", "==", expr)
        for i, s in enumerate(strings):
            expr = expr.replace(f"@@{i}@@", repr(s[1:-1]))
        return self._eval(ast.parse(expr, mode="eval").body)

    def _eval(self, n):
        if isinstance(n, ast.Constant):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            a, b = self._eval(n.left), self._eval(n.right)
            if isinstance(n.op, ast.Add) and (isinstance(a, str) or isinstance(b, str)):
                return f"{a}{b}"
            return _OPS[type(n.op)](a or 0, b or 0)
        if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](self._eval(n.operand) or 0)
        if isinstance(n, ast.Compare) and len(n.ops) == 1 and type(n.ops[0]) in _CMP:
            return _CMP[type(n.ops[0])](self._eval(n.left), self._eval(n.comparators[0]))
        if isinstance(n, ast.List):
            return [self._eval(e) for e in n.elts]
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FUNCS:
            return _FUNCS[n.func.id](*[self._eval(a) for a in n.args])
        if isinstance(n, ast.Name) and n.id in ("TRUE", "FALSE"):
            return n.id == "TRUE"
        raise ValueError("непідтримуваний вираз")

    def recalc(self) -> None:
        self._lock = True
        for (r, c), s in self.raw.items():
            it = self.item(r, c)
            if it is None:
                it = QTableWidgetItem()
                self.setItem(r, c, it)
            num = self.fmt.get((r, c), {}).get("num")
            if s.startswith("="):
                v = self.value(r, c)
                it.setText(fmt_value(v, num))
                it.setToolTip(s)
                it.setForeground(QColor("#b91c1c") if v == "#ПОМИЛКА" else QColor("#135548"))
            elif num:
                it.setText(fmt_value(self.value(r, c), num))
            else:
                it.setText(s)
            self._apply_fmt(r, c, it)
        self._lock = False

    # ---------- формат ----------
    def _apply_fmt(self, r: int, c: int, it: QTableWidgetItem) -> None:
        f = self.fmt.get((r, c), {})
        font = QFont(self.font())
        font.setBold(bool(f.get("bold")))
        font.setItalic(bool(f.get("italic")))
        it.setFont(font)
        it.setTextAlignment({"center": Qt.AlignmentFlag.AlignCenter,
                             "right": Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter}
                            .get(f.get("align"), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter))
        it.setBackground(QBrush(QColor(f["bg"])) if f.get("bg") else QBrush())
        if f.get("color") and not self.raw.get((r, c), "").startswith("="):
            it.setForeground(QColor(f["color"]))
        elif not self.raw.get((r, c), "").startswith("="):
            it.setForeground(QBrush())

    def selected_cells(self) -> list[tuple[int, int]]:
        cells = [(i.row(), i.column()) for i in self.selectedIndexes()]
        if not cells and self.currentRow() >= 0:
            cells = [(self.currentRow(), self.currentColumn())]
        return cells

    def set_format(self, **kw) -> None:
        for r, c in self.selected_cells():
            f = self.fmt.setdefault((r, c), {})
            for k, v in kw.items():
                if v is None:
                    f.pop(k, None)
                else:
                    f[k] = v
            it = self.item(r, c) or QTableWidgetItem()
            if not self.item(r, c):
                self.setItem(r, c, it)
            self._apply_fmt(r, c, it)
        if "num" in kw:
            self.recalc()

    def toggle_format(self, key: str) -> None:
        cells = self.selected_cells()
        on = not all(self.fmt.get(rc, {}).get(key) for rc in cells)
        self.set_format(**{key: on or None})

    # ---------- структура ----------
    def _remap(self, fn) -> None:
        self.raw = {fn(k): v for k, v in self.raw.items() if fn(k) is not None}
        self.fmt = {fn(k): v for k, v in self.fmt.items() if fn(k) is not None}

    def insert_row(self, r: int) -> None:
        self.insertRow(r)
        self._remap(lambda k: (k[0] + 1, k[1]) if k[0] >= r else k)
        self.recalc()

    def delete_row(self, r: int) -> None:
        self.removeRow(r)
        self._remap(lambda k: None if k[0] == r else ((k[0] - 1, k[1]) if k[0] > r else k))
        self.recalc()

    def insert_col(self, c: int) -> None:
        self.insertColumn(c)
        self._remap(lambda k: (k[0], k[1] + 1) if k[1] >= c else k)
        self.setHorizontalHeaderLabels([col_letters(i) for i in range(self.columnCount())])
        self.recalc()

    def delete_col(self, c: int) -> None:
        self.removeColumn(c)
        self._remap(lambda k: None if k[1] == c else ((k[0], k[1] - 1) if k[1] > c else k))
        self.setHorizontalHeaderLabels([col_letters(i) for i in range(self.columnCount())])
        self.recalc()

    def merge_selected(self) -> None:
        rngs = self.selectedRanges()
        if rngs:
            r = rngs[-1]
            if r.rowCount() > 1 or r.columnCount() > 1:
                self.setSpan(r.topRow(), r.leftColumn(), r.rowCount(), r.columnCount())

    def unmerge_current(self) -> None:
        r, c = self.currentRow(), self.currentColumn()
        if r >= 0:
            self.setSpan(r, c, 1, 1)

    def sort_by_column(self, c: int, descending: bool = False, header: bool = True) -> None:
        rows = self.data()
        if not rows:
            return
        head, body = (rows[:1], rows[1:]) if header else ([], rows)
        body = [r + [""] * (len(rows[0]) - len(r)) for r in body]

        def key(row):
            v = to_number(row[c]) if c < len(row) else ""
            return (0, v, "") if isinstance(v, (int, float)) else (1, 0, str(v).lower())
        body.sort(key=key, reverse=descending)
        self.set_data(head + body, {})

    def autosum(self) -> None:
        r, c = self.currentRow(), self.currentColumn()
        if r <= 0 or c < 0:
            return
        top = r - 1
        while top > 0 and isinstance(self.value(top - 1, c), (int, float)):
            top -= 1
        self.set_cell(r, c, f"=SUM({col_letters(c)}{top + 1}:{col_letters(c)}{r})")

    def fill_down(self) -> None:
        """Заповнити виділення значенням/формулою верхньої комірки (посилання на рядки зсуваються)."""
        rngs = self.selectedRanges()
        if not rngs:
            return
        rg = rngs[0]
        for c in range(rg.leftColumn(), rg.rightColumn() + 1):
            src = self.raw.get((rg.topRow(), c), "")
            for r in range(rg.topRow() + 1, rg.bottomRow() + 1):
                d = r - rg.topRow()
                text = REF_RE.sub(lambda m: f"{m.group(1)}{int(m.group(2)) + d}", src) if src.startswith("=") else src
                self.set_cell(r, c, text)

    # ---------- буфер обміну ----------
    def copy_sel(self) -> None:
        rngs = self.selectedRanges()
        if not rngs:
            return
        r = rngs[0]
        lines = ["\t".join(self.raw.get((i, j), "") for j in range(r.leftColumn(), r.rightColumn() + 1))
                 for i in range(r.topRow(), r.bottomRow() + 1)]
        self._clip = "\n".join(lines)      # запас, якщо системний буфер зайнятий іншою програмою
        QApplication.clipboard().setText(self._clip)

    def paste(self) -> None:
        text = QApplication.clipboard().text() or getattr(self, "_clip", "")
        if not text:
            return
        r0, c0 = max(0, self.currentRow()), max(0, self.currentColumn())
        for i, ln in enumerate(text.splitlines()):
            for j, v in enumerate(ln.split("\t")):
                self.set_cell(r0 + i, c0 + j, v)

    def clear_selected(self) -> None:
        for r, c in self.selected_cells():
            self.raw.pop((r, c), None)
            if self.item(r, c):
                self.item(r, c).setText("")
        self.recalc()

    def find_next(self, text: str) -> bool:
        if not text:
            return False
        cells = sorted(self.raw)
        start = (self.currentRow(), self.currentColumn())
        order = [k for k in cells if k > start] + [k for k in cells if k <= start]
        for r, c in order:
            if text.lower() in self.raw[(r, c)].lower() or text.lower() in fmt_value(self.value(r, c)).lower():
                self.setCurrentCell(r, c)
                return True
        return False

    # ---------- маркер автозаповнення (протягування за правий нижній кут) ----------
    HANDLE = 7

    def _sel_rect(self):
        rngs = self.selectedRanges()
        if not rngs:
            r, c = self.currentRow(), self.currentColumn()
            return (r, c, r, c) if r >= 0 and c >= 0 else None
        rg = rngs[-1]
        return rg.topRow(), rg.leftColumn(), rg.bottomRow(), rg.rightColumn()

    def _handle_pos(self):
        sel = self._sel_rect()
        if not sel:
            return None
        rect = self.visualRect(self.model().index(sel[2], sel[3]))
        return rect.bottomRight()

    def paintEvent(self, e) -> None:
        super().paintEvent(e)
        hp = self._handle_pos()
        if hp is None:
            return
        from PySide6.QtGui import QPainter
        p = QPainter(self.viewport())
        p.fillRect(hp.x() - self.HANDLE // 2, hp.y() - self.HANDLE // 2, self.HANDLE, self.HANDLE, QColor("#1d7a66"))
        p.end()

    def mousePressEvent(self, e) -> None:
        hp = self._handle_pos()
        if hp is not None and (e.position().toPoint() - hp).manhattanLength() <= self.HANDLE + 2:
            self._drag_src = self._sel_rect()
            self._drag_to = None
            self.viewport().setCursor(Qt.CursorShape.CrossCursor)
            return
        self._drag_src = None
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e) -> None:
        if getattr(self, "_drag_src", None):
            idx = self.indexAt(e.position().toPoint())
            if idx.isValid():
                self._drag_to = (idx.row(), idx.column())
                r0, c0, r1, c1 = self._drag_src
                from PySide6.QtWidgets import QTableWidgetSelectionRange
                self.clearSelection()
                if self._drag_to[0] > r1:
                    self.setRangeSelected(QTableWidgetSelectionRange(r0, c0, self._drag_to[0], c1), True)
                elif self._drag_to[1] > c1:
                    self.setRangeSelected(QTableWidgetSelectionRange(r0, c0, r1, self._drag_to[1]), True)
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e) -> None:
        if getattr(self, "_drag_src", None):
            src, to = self._drag_src, self._drag_to
            self._drag_src = None
            self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
            if to:
                self.fill_series(src, to)
            return
        super().mouseReleaseEvent(e)

    def fill_series(self, src: tuple[int, int, int, int], to: tuple[int, int]) -> None:
        """Протягування: формули зсуваються, числові серії продовжуються (1,2,3 / 2,4,6), текст із числом
        (Урок 1 → Урок 2), решта копіюється циклічно."""
        r0, c0, r1, c1 = src
        if to[0] > r1:                                   # вниз
            for c in range(c0, c1 + 1):
                seq = [self.raw.get((r, c), "") for r in range(r0, r1 + 1)]
                for k, r in enumerate(range(r1 + 1, to[0] + 1)):
                    self.set_cell(r, c, self._next(seq, k, r - r0, rows=True))
        elif to[1] > c1:                                 # праворуч
            for r in range(r0, r1 + 1):
                seq = [self.raw.get((r, c), "") for c in range(c0, c1 + 1)]
                for k, c in enumerate(range(c1 + 1, to[1] + 1)):
                    self.set_cell(r, c, self._next(seq, k, c - c0, rows=False))

    @staticmethod
    def _next(seq: list[str], k: int, offset: int, rows: bool) -> str:
        n = len(seq)
        base = seq[(n + k) % n] if n else ""
        shift = ((n + k) // n) * n if n else 0
        if base.startswith("="):
            if rows:
                return REF_RE.sub(lambda m: f"{m.group(1)}{int(m.group(2)) + shift}", base)
            return REF_RE.sub(lambda m: f"{col_letters(col_index(m.group(1)) + shift)}{m.group(2)}", base)
        nums = [to_number(x) for x in seq]
        if all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in nums) and nums:
            step = (nums[-1] - nums[0]) / (n - 1) if n > 1 else 1
            v = nums[0] + step * offset
            return str(int(v)) if float(v).is_integer() else f"{v:g}"
        m = re.fullmatch(r"(.*?)(\d+)$", base)
        if m and n == 1:
            return f"{m.group(1)}{int(m.group(2)) + offset}"
        return base

    def contextMenuEvent(self, e) -> None:
        from PySide6.QtWidgets import QMenu
        m = QMenu(self)
        r, c = self.currentRow(), self.currentColumn()
        for text, fn in (("Вставити рядок", lambda: self.insert_row(max(0, r))), ("Видалити рядок", lambda: r >= 0 and self.delete_row(r)),
                         ("Вставити стовпець", lambda: self.insert_col(max(0, c))), ("Видалити стовпець", lambda: c >= 0 and self.delete_col(c)),
                         (None, None), ("Копіювати", self.copy_sel), ("Вставити", self.paste), ("Очистити", self.clear_selected),
                         (None, None), ("Об'єднати комірки", self.merge_selected), ("Роз'єднати", self.unmerge_current)):
            if text is None:
                m.addSeparator()
            else:
                m.addAction(text, fn)
        m.exec(e.globalPos())

    def keyPressEvent(self, e) -> None:
        if e.matches(QKeySequence.StandardKey.Copy):
            self.copy_sel()
        elif e.matches(QKeySequence.StandardKey.Paste):
            self.paste()
        elif e.key() in (Qt.Key.Key_Delete,) and self.state() != self.State.EditingState:
            self.clear_selected()
        else:
            super().keyPressEvent(e)
