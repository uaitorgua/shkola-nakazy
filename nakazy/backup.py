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


REASONS = {"start": "під час запуску", "manual": "вручну", "before-restore": "перед відновленням",
           "before-import": "перед імпортом бази"}


def describe(path: str) -> tuple[str, str]:
    """(дата й час, причина) з назви копії nakazy-YYYYmmdd-HHMMSS-ffffff-<причина>.db."""
    import re
    m = re.match(r"nakazy-(\d{8})-(\d{6})-\d+-(.+)\.db$", os.path.basename(path))
    if not m:
        return "", os.path.basename(path)
    d, t, reason = m.groups()
    when = f"{d[6:8]}.{d[4:6]}.{d[:4]} {t[:2]}:{t[2:4]}"
    if reason.startswith("before-migration-v"):
        return when, "перед оновленням програми (будова бази)"
    return when, REASONS.get(reason, reason)


def check_file(path: str, current_version: int) -> tuple[bool, str, int]:
    """Чи це база «Накази ШКОЛА»: (так/ні, пояснення, кількість наказів)."""
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            ver = con.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
            n = con.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        finally:
            con.close()
    except sqlite3.Error:
        return False, "Це не база «Накази ШКОЛА» або файл пошкоджено.", 0
    v = int(ver[0]) if ver else 0
    if v > current_version:
        return False, "Файл створено новішою версією програми. Спершу оновіть «Накази ШКОЛА».", n
    return True, f"Наказів у файлі: {n}.", n


def export_to(db_con: sqlite3.Connection, dest: str) -> str:
    """Цілісна копія відкритої бази у вибраний файл (SQLite backup API)."""
    out = sqlite3.connect(dest)
    try:
        db_con.backup(out)
    finally:
        out.close()
    return dest
