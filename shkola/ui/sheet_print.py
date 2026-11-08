"""Друк і PDF для InterTab: аркуш → HTML-таблиця (значення, формат комірок) → QTextDocument → принтер/PDF.
Параметри: орієнтація, усі аркуші чи поточний, сітка, заголовок із назвою аркуша."""

from __future__ import annotations

import html
from pathlib import Path

from PySide6.QtCore import QMarginsF
from PySide6.QtGui import QFont, QPageLayout, QPageSize, QTextDocument
from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout

from .sheet_model import Sheet, col_letters, fmt_value


class PrintDialog(QDialog):
    def __init__(self, parent, n_sheets: int) -> None:
        super().__init__(parent)
        self.setWindowTitle("Друк / PDF таблиці")
        self.orient = QComboBox()
        self.orient.addItems(["Книжкова", "Альбомна"])
        self.which = QComboBox()
        self.which.addItems(["Поточний аркуш", f"Усі аркуші ({n_sheets})"])
        self.grid = QCheckBox("Сітка (межі комірок)")
        self.grid.setChecked(True)
        self.title = QCheckBox("Назва аркуша як заголовок")
        self.title.setChecked(True)
        self.headers = QCheckBox("Підписи стовпців A, B, C…")
        form = QFormLayout(self)
        form.addRow("Орієнтація:", self.orient)
        form.addRow("Що друкувати:", self.which)
        form.addRow(self.grid)
        form.addRow(self.title)
        form.addRow(self.headers)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def landscape(self) -> bool:
        return self.orient.currentIndex() == 1

    def all_sheets(self) -> bool:
        return self.which.currentIndex() == 1


def sheet_html(name: str, sheet: Sheet, grid: bool = True, title: bool = True, headers: bool = False) -> str:
    rows = sheet.data()
    if not rows:
        return f"<h3>{html.escape(name)}</h3><p>Аркуш порожній.</p>" if title else ""
    ncols = max(len(r) for r in rows)
    border = ' border="1" cellspacing="0" cellpadding="4"' if grid else ' border="0" cellspacing="0" cellpadding="4"'
    out = [f"<h3>{html.escape(name)}</h3>" if title else "", f'<table{border} width="100%">']
    if headers:
        out.append("<tr>" + "".join(f'<th bgcolor="#e3f1ec">{col_letters(j)}</th>' for j in range(ncols)) + "</tr>")
    for i, row in enumerate(rows):
        cells = []
        for j in range(ncols):
            f = sheet.fmt.get((i, j), {})
            v = html.escape(fmt_value(sheet.value(i, j), f.get("num")))
            if f.get("bold"):
                v = f"<b>{v}</b>"
            if f.get("italic"):
                v = f"<i>{v}</i>"
            if f.get("color"):
                v = f'<font color="{f["color"]}">{v}</font>'
            attrs = f' align="{f.get("align", "left")}"'
            if f.get("bg"):
                attrs += f' bgcolor="{f["bg"]}"'
            span = sheet.columnSpan(i, j) if i < sheet.rowCount() and j < sheet.columnCount() else 1
            if span > 1:
                attrs += f' colspan="{span}"'
            cells.append(f"<td{attrs}>{v}</td>")
        out.append("<tr>" + "".join(cells) + "</tr>")
    out.append("</table>")
    return "".join(out)


def build_document(sheets: list[tuple[str, Sheet]], grid=True, title=True, headers=False) -> QTextDocument:
    doc = QTextDocument()
    doc.setDefaultFont(QFont("Times New Roman", 11))
    body = '<p style="page-break-before: always"></p>'.join(sheet_html(n, s, grid, title, headers) for n, s in sheets)
    doc.setHtml(f"<html><body>{body}</body></html>")
    return doc


def _printer(landscape: bool, pdf: Path | None = None):
    from PySide6.QtPrintSupport import QPrinter
    pr = QPrinter(QPrinter.PrinterMode.HighResolution)
    pr.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    pr.setPageOrientation(QPageLayout.Orientation.Landscape if landscape else QPageLayout.Orientation.Portrait)
    pr.setPageMargins(QMarginsF(15, 15, 15, 15), QPageLayout.Unit.Millimeter)
    if pdf is not None:
        pr.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        pr.setOutputFileName(str(pdf))
    return pr


def save_pdf(sheets: list[tuple[str, Sheet]], path: Path, landscape: bool = False, **opts) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    build_document(sheets, **opts).print_(_printer(landscape, path))
    return path


def print_sheets(parent, sheets: list[tuple[str, Sheet]], landscape: bool = False, preview: bool = False, **opts) -> None:
    from PySide6.QtPrintSupport import QPrintDialog, QPrintPreviewDialog
    doc = build_document(sheets, **opts)
    pr = _printer(landscape)
    if preview:
        d = QPrintPreviewDialog(pr, parent)
        d.paintRequested.connect(lambda p: doc.print_(p))
        d.exec()
    elif QPrintDialog(pr, parent).exec():
        doc.print_(pr)
