"""Редагування тексту наказу в окремій програмі (з версії 0.1.5 вбудованого редактора немає).

Порядок вибору редактора (налаштування «Заклад…», ключ editor):
  auto   – «Офіс ШКОЛА» (InterText, псевдонім ofis-shkola.exe), якщо встановлений; інакше програма Windows для DOCX;
  system – програма, яку Windows відкриває для DOCX (Word, LibreOffice…);
  custom – вибрана програма (editor_path).
Наказ записується в DOCX у теці даних (edit/), а після збереження в редакторі зміни забираються в базу:
чернетка – через update_draft (попередня редакція лишається в історії), архівний імпортований – через
fix_imported. Зареєстрований наказ відкривається лише копією для перегляду, зміни не забираються.
Перший абзац файла – заголовок «Про…»; решта – текст наказу.
"""
from __future__ import annotations

import html as _html
import os
import re
import shutil
import subprocess
import time

from .db import Database

OFFICE_ALIAS = "ofis-shkola.exe"
OFFICE_STORE = "ms-windows-store://pdp/?productid=9P6Q3GQW1SQF"
OFFICE_WEB = "https://apps.microsoft.com/detail/9P6Q3GQW1SQF"
MARGINS = (30, 10, 20, 20)  # як у export.py (дод. 1 п. 2)


class NoEditor(Exception):
    """Немає програми для DOCX."""


def edit_dir(db: Database) -> str:
    d = os.path.join(os.path.dirname(os.path.abspath(db.path)), "edit")
    os.makedirs(d, exist_ok=True)
    return d


def _safe(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", name or "").strip()
    return re.sub(r"\s+", " ", name)[:60].rstrip(" .") or "Наказ"


def edit_path(db: Database, order_id: int, copy: bool = False) -> str:
    row = db.get(order_id)
    suffix = " (копія для перегляду)" if copy else ""
    return os.path.join(edit_dir(db), f"Наказ {order_id} {_safe(row['title'])}{suffix}.docx")


def write_docx(db: Database, order_id: int, copy: bool = False) -> str:
    """Записати заголовок і текст наказу в DOCX для редагування (копія з бланком – через export.py)."""
    path = edit_path(db, order_id, copy)
    if copy:
        from .export import export_docx
        export_docx(db, order_id, path)
        return path
    from shkola.export.html_docx import html_to_docx
    row = db.get(order_id)
    body = row["body_html"] or ""
    body = body if "<body" in body.lower() else f"<html><body><p><b>{_html.escape(row['title'] or '')}</b></p>{body}</body></html>"
    html_to_docx(body, None, MARGINS).save(path)
    return path


_EMPTY = re.compile(r"<p[^>]*>(\s|<br\s*/?>|&nbsp;)*</p>", re.I)


def read_docx(path: str, attempts: int = 10) -> tuple[str, str]:
    """(заголовок, HTML тексту). Порожні абзаци прибираються, щоб повторне редагування їх не множило."""
    from pathlib import Path

    from shkola.export.html_docx import docx_to_html
    last = None
    for _ in range(attempts):  # редактор може ще дописувати файл
        try:
            h = docx_to_html(Path(path))
            break
        except Exception as e:  # файл зайнятий або неповний
            last = e; time.sleep(0.3)
    else:
        raise last
    h = _EMPTY.sub("", h).strip()
    m = re.match(r"<p[^>]*>(.*?)</p>", h, re.S)
    if m:
        text = _html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()
        if text.startswith("Про "):
            return re.sub(r"\s+", " ", text), h[m.end():].strip()
    return "", h


def sync(db: Database, order_id: int, path: str) -> bool:
    """Забрати зміни з файла в базу. True – щось змінилось."""
    row = db.get(order_id)
    title, body = read_docx(path)
    fields = {}
    if body and body != (row["body_html"] or ""):
        fields["body_html"] = body
    if title and title != row["title"]:
        fields["title"] = title
    if not fields:
        return False
    if row["source"] == "import":
        db.fix_imported(order_id, **fields)
    else:
        db.update_draft(order_id, **fields)
    return True


def office_exe() -> str | None:
    """«Офіс ШКОЛА» з Microsoft Store: псевдонім запуску ofis-shkola.exe."""
    found = shutil.which(OFFICE_ALIAS)
    if found:
        return found
    p = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WindowsApps", OFFICE_ALIAS)
    return p if os.path.exists(p) else None


def editor_choice(db: Database) -> str:
    return db.get_setting("editor", "auto") or "auto"


def open_file(db: Database, path: str) -> str:
    """Відкрити файл у редакторі за налаштуванням. Повертає назву редактора для повідомлення."""
    mode = editor_choice(db)
    if mode == "custom":
        exe = db.get_setting("editor_path")
        if exe and os.path.exists(exe):
            subprocess.Popen([exe, path])
            return os.path.splitext(os.path.basename(exe))[0]
        mode = "auto"
    if mode == "auto":
        exe = office_exe()
        if exe:
            subprocess.Popen([exe, path])
            return "Офіс ШКОЛА"
    try:
        os.startfile(path)  # програма Windows для DOCX
    except OSError as e:
        raise NoEditor(str(e)) from e
    return "програма Windows для DOCX"
