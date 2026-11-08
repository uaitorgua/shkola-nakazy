"""Резервні копії бази: перед міграцією схеми, при запуску й за запитом; відновлення.

Копія робиться через SQLite backup API (цілісна навіть при відкритій базі).
Дані лежать у %APPDATA%\\nakazy-shkola, поза текою програми, тож оновлення їх не зачіпає.
"""
from __future__ import annotations

import datetime as dt
import os
import shutil
import sqlite3

KEEP = 30


def backup_dir(db_path: str) -> str:
    d = os.path.join(os.path.dirname(db_path), "backups")
    os.makedirs(d, exist_ok=True)
    return d


def make_backup(db_path: str, reason: str = "manual", keep: int = KEEP) -> str | None:
    if not os.path.exists(db_path):
        return None
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    dst = os.path.join(backup_dir(db_path), f"nakazy-{stamp}-{reason}.db")
    src = sqlite3.connect(db_path)
    out = sqlite3.connect(dst)
    try:
        src.backup(out)
    finally:
        out.close(); src.close()
    _rotate(db_path, keep)
    return dst


def list_backups(db_path: str) -> list[str]:
    d = backup_dir(db_path)
    return sorted((os.path.join(d, f) for f in os.listdir(d) if f.endswith(".db")), reverse=True)


def restore_backup(db_path: str, backup_path: str) -> str:
    """Відновлює копію; поточну базу перед цим теж зберігає (відновлення можна відкотити)."""
    make_backup(db_path, "before-restore", keep=10**6)
    for ext in ("-wal", "-shm"):
        if os.path.exists(db_path + ext):
            os.remove(db_path + ext)
    shutil.copy2(backup_path, db_path)
    return db_path


def _rotate(db_path: str, keep: int):
    files = [f for f in list_backups(db_path) if "before-" not in os.path.basename(f)]
    for f in files[keep:]:
        os.remove(f)
