"""XLSX (openpyxl): кожна розпізнана таблиця — окремий аркуш «Стор N, табл M»; якщо таблиць немає —
аркуш із текстом сторінки по рядках."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, Side
from openpyxl.utils import get_column_letter

from ..ocr.models import Document, Table

_THIN = Side(style="thin", color="999999")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)


def _number(s: str):
    t = s.replace(" ", "").replace(",", ".")
    try:
        if t.lstrip("-").isdigit():
            return int(t)
        return float(t) if t.count(".") == 1 and t.replace(".", "").lstrip("-").isdigit() else s
    except ValueError:
        return s


def fill_sheet(ws, rows: list[list[str]], header: bool = True) -> None:
    for i, row in enumerate(rows, 1):
        for j, val in enumerate(row, 1):
            c = ws.cell(row=i, column=j, value=_number(val))
            c.border = _BORDER
            c.alignment = Alignment(wrap_text=True, vertical="top")
            if header and i == 1:
                c.font = Font(bold=True)
    for j in range(1, max((len(r) for r in rows), default=0) + 1):
        width = max((len(str(r[j - 1])) for r in rows if len(r) >= j), default=8)
        ws.column_dimensions[get_column_letter(j)].width = min(60, max(8, width + 2))


def save_xlsx(docs: list[Document], path: Path, progress: Callable[[int, int], None] | None = None) -> Path:
    wb = Workbook()
    wb.remove(wb.active)
    for pi, doc in enumerate(docs, 1):
        tables = doc.tables
        for ti, t in enumerate(tables, 1):
            ws = wb.create_sheet(f"Стор {pi}, табл {ti}"[:31])
            fill_sheet(ws, t.rows)
        if not tables:
            ws = wb.create_sheet(f"Стор {pi}, текст"[:31])
            fill_sheet(ws, [[line] for line in doc.plain_text().splitlines() if line.strip()], header=False)
        if progress:
            progress(pi, len(docs))
    if not wb.sheetnames:
        wb.create_sheet("Порожньо")
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(path))
    return path


def save_rows_xlsx(sheets: dict[str, list[list[str]]], path: Path) -> Path:
    """Збереження аркушів табличного редактора."""
    wb = Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        fill_sheet(wb.create_sheet(name[:31] or "Аркуш"), rows, header=False)
    if not wb.sheetnames:
        wb.create_sheet("Аркуш1")
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(path))
    return path


def save_sheets_xlsx(sheets: dict[str, tuple], path: Path) -> Path:
    """Аркуші табличного редактора: (raw, values, fmt). Формули Excel-сумісні зберігаються як формули
    (крапка з комою → кома), решта — значення; формат: жирний/курсив/вирівнювання/заливка/колір."""
    from openpyxl.styles import PatternFill
    wb = Workbook()
    wb.remove(wb.active)
    for name, item in sheets.items():
        raw, values, fmt = item[:3]
        charts = item[3] if len(item) > 3 else []
        ws = wb.create_sheet(name[:31] or "Аркуш")
        for i, row in enumerate(raw, 1):
            for j, text in enumerate(row, 1):
                val = text.replace(";", ",") if text.startswith("=") else _number(text)
                c = ws.cell(row=i, column=j, value=val)
                c.border = _BORDER
                f = fmt.get((i - 1, j - 1), {})
                if f:
                    c.font = Font(bold=bool(f.get("bold")), italic=bool(f.get("italic")),
                                  color=(f["color"].lstrip("#").upper() if f.get("color") else None))
                    c.alignment = Alignment(horizontal=f.get("align") or "left", wrap_text=True, vertical="top")
                    if f.get("bg"):
                        c.fill = PatternFill("solid", fgColor=f["bg"].lstrip("#").upper())
        for j in range(1, max((len(r) for r in raw), default=0) + 1):
            width = max((len(str(r[j - 1])) for r in values if len(r) >= j), default=8)
            ws.column_dimensions[get_column_letter(j)].width = min(60, max(8, width + 2))
        if charts:
            from ..ui.charts import add_xlsx_chart
            for spec in charts:
                add_xlsx_chart(ws, spec)
    if not wb.sheetnames:
        wb.create_sheet("Аркуш1")
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(path))
    return path


def load_xlsx(path: Path, with_formats: bool = False):
    """{аркуш: рядки} або, з with_formats, {аркуш: (рядки з формулами, формати)}; формати містять
    службові ключі "__merges__" [(r0,c0,nr,nc)], "__widths__" {c: px}, "__charts__" [XlsxChart] —
    усе, що Excel зберігає поза комірками, замінюється внутрішніми ресурсами InterTab."""
    from openpyxl import load_workbook
    wb = load_workbook(str(path), data_only=not with_formats)
    charts_by_sheet: dict[str, list] = {}
    if with_formats:
        try:
            from .xlsx_charts_read import read_charts
            for ch in read_charts(path):
                charts_by_sheet.setdefault(ch.sheet, []).append(ch)
        except Exception:
            pass
    out = {}
    for ws in wb.worksheets:
        rows, fmts = [], {}
        if with_formats:
            fmts["__merges__"] = [(m.min_row - 1, m.min_col - 1, m.max_row - m.min_row + 1, m.max_col - m.min_col + 1)
                                  for m in ws.merged_cells.ranges]
            fmts["__widths__"] = {}
            for key, dim in ws.column_dimensions.items():
                if dim.width:
                    from openpyxl.utils import column_index_from_string
                    try:
                        fmts["__widths__"][column_index_from_string(key) - 1] = int(dim.width * 7 + 5)
                    except ValueError:
                        pass
            fmts["__charts__"] = charts_by_sheet.get(ws.title, [])
        for i, row in enumerate(ws.iter_rows()):
            vals = []
            for j, c in enumerate(row):
                v = getattr(c, "value", None)
                text = "" if v is None else (str(v).replace(",", ";") if isinstance(v, str) and v.startswith("=") else str(v))
                vals.append(text)
                if with_formats and hasattr(c, "font") and (c.font.bold or c.font.italic or (c.fill and c.fill.fgColor and c.fill.fill_type == "solid")
                                     or (c.alignment and c.alignment.horizontal in ("center", "right"))):
                    f = {}
                    if c.font.bold:
                        f["bold"] = True
                    if c.font.italic:
                        f["italic"] = True
                    if c.alignment and c.alignment.horizontal in ("center", "right"):
                        f["align"] = c.alignment.horizontal
                    if c.fill and c.fill.fill_type == "solid" and c.fill.fgColor and c.fill.fgColor.rgb and isinstance(c.fill.fgColor.rgb, str):
                        f["bg"] = "#" + c.fill.fgColor.rgb[-6:].lower()
                    fmts[(i, j)] = f
            rows.append(vals)
        out[ws.title] = (rows, fmts) if with_formats else rows
    return out
