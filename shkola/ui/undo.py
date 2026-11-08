"""Історія правок по сторінках (Ctrl+Z / Ctrl+Y)."""

from __future__ import annotations

from ..core.models import Adjust, Page

LIMIT = 50


class UndoHistory:
    def __init__(self) -> None:
        self._undo: dict[int, list[Adjust]] = {}
        self._redo: dict[int, list[Adjust]] = {}

    def push(self, page: Page) -> None:
        stack = self._undo.setdefault(page.id, [])
        stack.append(page.adjust.copy())
        del stack[:-LIMIT]
        self._redo.pop(page.id, None)

    def undo(self, page: Page) -> bool:
        return self._swap(page, self._undo, self._redo)

    def redo(self, page: Page) -> bool:
        return self._swap(page, self._redo, self._undo)

    @staticmethod
    def _swap(page: Page, src: dict, dst: dict) -> bool:
        stack = src.get(page.id)
        if not stack:
            return False
        dst.setdefault(page.id, []).append(page.adjust.copy())
        page.adjust = stack.pop()
        return True
