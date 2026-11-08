"""Паралельна обробка сторінок. Pillow і numpy відпускають GIL, тож потоки реально прискорюють роботу."""

from __future__ import annotations

import os
from concurrent.futures import Executor, ThreadPoolExecutor
from typing import Callable, Iterable, TypeVar

T = TypeVar("T")
R = TypeVar("R")

WORKERS = max(2, min(8, (os.cpu_count() or 4)))
_pool: ThreadPoolExecutor | None = None


def pool() -> Executor:
    """Спільний пул для фонової обробки (автоформат сканів тощо)."""
    global _pool
    if _pool is None:
        _pool = ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="img")
    return _pool


def pmap(fn: Callable[[T], R], items: Iterable[T],
         progress: Callable[[int, int], None] | None = None) -> list[R]:
    """Як map(), але паралельно; порядок результатів збережено, прогрес — у міру готовності."""
    items = list(items)
    out: list[R] = [None] * len(items)  # type: ignore[list-item]
    with ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="export") as ex:
        futures = {ex.submit(fn, it): i for i, it in enumerate(items)}
        done = 0
        from concurrent.futures import as_completed
        for f in as_completed(futures):
            out[futures[f]] = f.result()
            done += 1
            if progress:
                progress(done, len(items))
    return out
