"""Стрічка мініатюр пакета: вибір, перетягування для зміни порядку, видалення."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QAbstractItemView, QListView, QListWidget, QListWidgetItem

from ..core.models import Page
from ..imaging.pipeline import render
from .qtimage import to_pixmap

THUMB = 150


def _icon(page: Page) -> QIcon:
    pm = to_pixmap(render(page, max_side=THUMB * 2))
    icon = QIcon(pm)
    icon.addPixmap(pm, QIcon.Mode.Selected)     # без синього відтінку на вибраній сторінці
    return icon


class PageStrip(QListWidget):
    page_selected = Signal(int)
    order_changed = Signal(list)       # новий порядок id сторінок
    move_requested = Signal(list, int)  # (рядки, що тягнемо; позиція вставки)
    delete_requested = Signal(list)    # індекси

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("strip")
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setFlow(QListView.Flow.LeftToRight)
        self.setWrapping(False)
        self.setIconSize(QSize(THUMB, THUMB))
        self.setGridSize(QSize(THUMB + 20, THUMB + 34))
        self.setFixedHeight(THUMB + 60)
        self.setMovement(QListView.Movement.Snap)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.currentRowChanged.connect(self.page_selected)
        self.model().rowsMoved.connect(self._emit_order)

    def dropEvent(self, e) -> None:
        """Перетягування мініатюр мишею змінює порядок сторінок у пакеті."""
        if e.source() is not self:
            return super().dropEvent(e)
        rows = self.selected_rows()
        target = self.indexAt(e.position().toPoint())
        if target.isValid():
            rect = self.visualRect(target)
            dst = target.row() + (1 if e.position().x() > rect.center().x() else 0)
        else:
            dst = self.count()
        e.setDropAction(Qt.DropAction.IgnoreAction)
        e.accept()
        if rows:
            self.move_requested.emit(rows, dst)

    def rebuild(self, pages: list[Page], current: int) -> None:
        self.blockSignals(True)
        self.clear()
        for p in pages:
            self.addItem(self._make_item(p))
        self._renumber()
        self.blockSignals(False)
        if pages:
            self.setCurrentRow(max(0, min(current, len(pages) - 1)))
            self.scrollToItem(self.currentItem())
            self.page_selected.emit(self.currentRow())

    def refresh_page(self, index: int, page: Page) -> None:
        item = self.item(index)
        if item:
            item.setIcon(_icon(page))

    def selected_rows(self) -> list[int]:
        return sorted(self.row(i) for i in self.selectedItems())

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key.Key_Delete and self.selectedItems():
            self.delete_requested.emit(self.selected_rows())
            return
        super().keyPressEvent(e)

    def _make_item(self, p: Page) -> QListWidgetItem:
        item = QListWidgetItem(_icon(p), "")
        item.setData(Qt.ItemDataRole.UserRole, p.id)
        item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
        return item

    def _renumber(self) -> None:
        for i in range(self.count()):
            self.item(i).setText(f"Стор. {i + 1}")

    def _emit_order(self, *_):
        self._renumber()
        self.order_changed.emit([self.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.count())])
