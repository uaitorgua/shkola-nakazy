"""Перенесення даних незалежно від будови бази: експорт і імпорт JSON, експорт у Excel (XLSX).

JSON – повна копія всіх таблиць як списків {назва поля: значення}; двійкові дані (оригінали, файли додатків,
бланк) – base64. Імпорт розкладає рядки за назвами полів у нову базу ПОТОЧНОЇ версії: поля, яких у новій
будові немає, пропускаються (і перелічуються у звіті), нові поля отримують типові значення. Тому файл JSON
однієї версії відкривається будь-якою новішою. Пошуковий індекс після імпорту будується заново.
XLSX – лише для перегляду й друку людьми (накази, люди, графік відпусток, додатки); назад не імпортується,
бо в таблиці губиться оформлення тексту наказів.
"""
from __future__ import annotations

import base64
import datetime as dt
import json
import os
import re

from . import __version__
from .db import SCHEMA_VERSION, Database, _plain, format_date

FORMAT = "nakazy-shkola"
FORMAT_VERSION = 1
SKIP = re.compile(r"^(orders_fts.*|_fts_cache|sqlite_.*)$")
# порядок вставки: спершу те, на що посилаються інші таблиці
ORDER = ["meta", "counters", "people", "classes", "orders", "attachments", "originals", "order_persons",
         "order_versions", "order_links", "leave_days", "leave_plan", "order_values", "order_effects", "nomenclature",
         "blanks", "audit"]


def _tables(con) -> list[str]:
    names = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
    names = [n for n in names if not SKIP.match(n)]
    return sorted(names, key=lambda n: (ORDER.index(n) if n in ORDER else len(ORDER), n))


def export_json(db: Database, path: str) -> dict:
    tables = {}
    for t in _tables(db.con):
        cur = db.con.execute(f"SELECT * FROM {t}")
        cols = [c[0] for c in cur.description]
        rows = []
        for r in cur.fetchall():
            row = {}
            for c, v in zip(cols, r):
                row[c] = {"base64": base64.b64encode(v).decode("ascii")} if isinstance(v, (bytes, bytearray)) else v
            rows.append(row)
        tables[t] = rows
    data = {"format": FORMAT, "format_version": FORMAT_VERSION, "app_version": __version__,
            "schema_version": SCHEMA_VERSION, "exported_at": dt.datetime.now().isoformat(timespec="seconds"),
            "tables": tables}
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)
    os.replace(tmp, path)  # файл з'являється лише повністю записаним
    return {t: len(v) for t, v in tables.items()}


class ImportError_(Exception):
    pass


def read_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as e:
        raise ImportError_(f"Файл не прочитано: {e}") from e
    if not isinstance(data, dict) or data.get("format") != FORMAT or not isinstance(data.get("tables"), dict):
        raise ImportError_("Це не файл експорту «Накази ШКОЛА».")
    if int(data.get("format_version") or 0) > FORMAT_VERSION:
        raise ImportError_("Файл експортовано новішою версією програми. Спершу оновіть «Накази ШКОЛА».")
    return data


def import_json(path: str, target: str) -> dict:
    """Створити НОВУ базу target (поточної будови) з файла JSON. Повертає звіт:
    {"rows": {таблиця: кількість}, "skipped": {таблиця: [поля]}, "from_version": …}."""
    data = read_json(path)
    if os.path.exists(target):
        raise ImportError_("Цільовий файл уже існує.")
    db = Database(target)
    from .cases import Cases
    Cases(db)  # таблиця номенклатури справ створюється окремо від основної будови
    report = {"rows": {}, "skipped": {}, "from_version": data.get("app_version", "")}
    try:
        db.con.execute("PRAGMA foreign_keys = OFF")
        current = set(_tables(db.con))
        db.con.execute("BEGIN")
        for t in sorted(data["tables"], key=lambda n: (ORDER.index(n) if n in ORDER else len(ORDER), n)):
            rows = data["tables"][t]
            if t not in current or not isinstance(rows, list):
                report["skipped"][t] = ["вся таблиця"]; continue
            cols = [r[1] for r in db.con.execute(f"PRAGMA table_info({t})")]
            n = 0
            for row in rows:
                if t == "meta" and row.get("key") == "schema_version":
                    continue  # будова – поточна
                use = {c: v for c, v in row.items() if c in cols}
                extra = [c for c in row if c not in cols]
                if extra:
                    report["skipped"].setdefault(t, sorted(set(extra)))
                for c, v in use.items():
                    if isinstance(v, dict) and "base64" in v:
                        use[c] = base64.b64decode(v["base64"])
                db.con.execute(f"INSERT OR REPLACE INTO {t} ({', '.join(use)}) VALUES ({', '.join('?' * len(use))})",
                               list(use.values()))
                n += 1
            report["rows"][t] = n
        for (oid,) in db.con.execute("SELECT id FROM orders").fetchall():  # пошуковий індекс заново
            db._reindex(oid)
        db.con.execute("COMMIT")
        db.con.execute("PRAGMA foreign_keys = ON")
        bad = db.con.execute("PRAGMA foreign_key_check").fetchall()
        if bad:
            report["fk_problems"] = len(bad)
    except Exception:
        try:
            db.con.execute("ROLLBACK")
        except Exception:
            pass
        db.close()
        for ext in ("", "-wal", "-shm"):
            if os.path.exists(target + ext):
                os.remove(target + ext)
        raise
    db.close()
    return report


def export_xlsx(db: Database, path: str) -> str:
    """Excel для перегляду: накази, люди, графік відпусток, додатки."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font
    from .db import KIND_BY_CODE, STATUS_TITLES
    wb = Workbook()

    def sheet(ws, title, head, rows, widths):
        ws.title = title
        ws.append(head)
        for c in ws[1]:
            c.font = Font(bold=True)
        for r in rows:
            ws.append(list(r))
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[ws.cell(1, i).column_letter].width = w
        ws.freeze_panes = "A2"
        for row in ws.iter_rows(min_row=2):
            for c in row:
                c.alignment = Alignment(vertical="top", wrap_text=True)

    orders = db.con.execute("SELECT * FROM orders ORDER BY year, kind, number, id").fetchall()
    sheet(wb.active, "Накази", ["Індекс", "Дата", "Вид", "Тип", "Заголовок", "Статус", "Підписує", "Підстава",
                                "Контроль", "Відповідальні", "Примітки", "Текст"],
          [(o["reg_index"] or "", format_date(o["date"]), KIND_BY_CODE[o["kind"]].title if o["kind"] in KIND_BY_CODE
            else o["kind"], o["type_name"], o["title"], STATUS_TITLES.get(o["status"], o["status"]), o["signer"],
            o["basis"], o["controller"], o["responsible"], o["notes"], _plain(o["body_html"])[:32000])
           for o in orders], [10, 12, 22, 18, 50, 14, 22, 30, 20, 20, 20, 80])
    people = db.con.execute("SELECT * FROM people ORDER BY kind, last, first").fetchall()
    sheet(wb.create_sheet(), "Люди", ["Хто", "Прізвище", "Ім'я", "По батькові", "Народження", "Клас", "Посада",
                                       "Ставка", "Категорія", "Щорічна відпустка, днів", "Статус"],
          [("учень" if p["kind"] == "pupil" else "працівник", p["last"], p["first"], p["middle"], format_date(p["birth"]),
            p["cls"], p["position"], p["rate"], p["category"], p["leave_right"] if "leave_right" in p.keys() else "",
            "вибув" if p["status"] == "left" else "") for p in people], [11, 18, 14, 18, 12, 8, 26, 8, 14, 12, 10])
    plan = db.con.execute("SELECT lp.*, p.last, p.first, p.middle, o.reg_index FROM leave_plan lp JOIN people p "
                          "ON p.id = lp.person_id LEFT JOIN orders o ON o.id = lp.order_id "
                          "ORDER BY lp.year, lp.from_date").fetchall()
    sheet(wb.create_sheet(), "Графік відпусток", ["Рік", "Працівник", "Вид", "Днів", "З", "По", "Робочий рік",
                                                   "Примітка", "Наказ"],
          [(r["year"], f"{r['last']} {r['first']} {r['middle']}".strip(), r["vtype"], r["days"],
            format_date(r["from_date"]), format_date(r["to_date"]), r["period"], r["note"], r["reg_index"] or "")
           for r in plan], [6, 30, 12, 6, 12, 12, 26, 20, 10])
    atts = db.con.execute("SELECT a.*, o.reg_index, o.title AS otitle FROM attachments a JOIN orders o "
                          "ON o.id = a.order_id ORDER BY o.id, a.n").fetchall()
    sheet(wb.create_sheet(), "Додатки", ["Наказ", "Заголовок наказу", "№", "Назва додатка", "Вигляд", "Файл"],
          [(a["reg_index"] or "чернетка", a["otitle"], a["n"], a["title"], "текст" if a["mode"] == "text" else "файл",
            a["filename"] or "") for a in atts], [10, 50, 5, 40, 8, 30])
    wb.save(path)
    return path
