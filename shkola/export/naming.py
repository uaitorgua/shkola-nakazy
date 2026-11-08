"""Імена файлів без перезапису наявних."""

from datetime import datetime
from pathlib import Path


def stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for n in range(2, 10_000):
        cand = path.with_name(f"{path.stem}_{n}{path.suffix}")
        if not cand.exists():
            return cand
    raise FileExistsError(path)


def safe_name(text: str) -> str:
    bad = '<>:"/\\|?*'
    return "".join("_" if c in bad else c for c in text).strip() or "скан"
