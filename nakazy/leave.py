"""Залишок днів щорічної відпустки працівника (як «Право на відпустку» в HRMIS).

Облік ведеться за наказами, створеними майстром шаблону: щорічна відпустка (використано),
компенсація частини відпустки (компенсовано), відкликання з відпустки (повернуто невикористані дні).
Рахуються лише зареєстровані накази; скасовані й чернетки – ні.
Право (кількість днів на робочий рік) вказується в картці працівника.
Норма: Закон України «Про відпустки», ст. 24 – після компенсації наданих щорічних відпусток
має лишатися не менше 24 календарних днів (звірено на zakon.rada.gov.ua 17.11.2026).
"""
from __future__ import annotations

import html
import re

from .db import Database

MIN_AFTER_COMP = 24
_DATE = re.compile(r"\d{1,2}\.\d{1,2}\.\d{4}")
OPS = {"v_annual": "used", "v_compensation": "comp", "v_recall": "back"}


def work_year_key(text: str) -> str:
    """«з 01.09.2025 по 31.08.2026» → «01.09.2025–31.08.2026»; без дат – як введено."""
    dates = _DATE.findall(text or "")
    if dates:
        return "–".join(_pad(d) for d in dates[:2])
    return (text or "").strip()


def _pad(d: str) -> str:
    dd, mm, yy = d.split(".")
    return f"{int(dd):02d}.{int(mm):02d}.{yy}"


def _days(text: str) -> int | None:
    m = re.search(r"\d+", text or "")
    return int(m.group()) if m else None


def record(db: Database, order_id: int, template_id: str, values: dict[str, str], person_id: int | None,
           refs: dict[str, int] | None = None):
    """Записати дні з наказу, створеного за шаблоном (якщо працівника вибрано з довідника)."""
    op = OPS.get(template_id)
    days = _days(values.get("days", ""))
    if not op or person_id is None or days is None:
        return
    year = work_year_key(values.get("period", ""))
    if op == "back" and refs and refs.get("leave_order"):  # рік – з наказу про відпустку, з якої відкликали
        r = db.con.execute("SELECT work_year FROM leave_days WHERE order_id = ?", (refs["leave_order"],)).fetchone()
        year = r[0] if r else year
    with db.tx():
        db.con.execute("INSERT OR REPLACE INTO leave_days VALUES (?, ?, ?, ?, ?)",
                       (order_id, person_id, year, op, days))


def summary(db: Database, person_id: int) -> list[dict]:
    """Підсумок за робочими роками: право, використано, компенсовано, повернуто, залишок."""
    row = db.con.execute("SELECT leave_right FROM people WHERE id = ?", (person_id,)).fetchone()
    right = row[0] if row else None
    out: dict[str, dict] = {}
    for r in db.con.execute("SELECT l.work_year, l.op, SUM(l.days) FROM leave_days l JOIN orders o ON o.id = l.order_id "
                            "WHERE l.person_id = ? AND o.status = 'registered' GROUP BY l.work_year, l.op "
                            "ORDER BY l.work_year", (person_id,)):
        y = out.setdefault(r[0], {"year": r[0], "right": right, "used": 0, "comp": 0, "back": 0})
        y[r[1]] = r[2]
    for y in out.values():
        y["left"] = None if right is None else right - y["used"] - y["comp"] + y["back"]
        y["warn"] = bool(y["comp"]) and right is not None and right - y["comp"] < MIN_AFTER_COMP
    return list(out.values())


def summary_html(db: Database, person_id: int) -> str:
    rows = summary(db, person_id)
    right = db.con.execute("SELECT leave_right FROM people WHERE id = ?", (person_id,)).fetchone()
    if right is None:
        return ""
    if not rows:
        r = right[0]
        return f"<p>Щорічна відпустка: {'право ' + str(r) + ' дн.' if r is not None else 'право не вказано в картці'}, " \
               "наказів ще немає.</p>"
    lines = []
    for y in rows:
        left = f"залишок <b>{y['left']}</b>" if y["left"] is not None else "право не вказано в картці"
        lines.append(f"<li>{html.escape(y['year'] or 'робочий рік не вказано')}: використано {y['used']}, "
                     f"компенсовано {y['comp']}, повернуто {y['back']}; {left}"
                     + (" <span style='color:#a35b00'>⚠ після компенсації менше 24 днів "
                        "(ст. 24 Закону «Про відпустки»)</span>" if y["warn"] else "") + "</li>")
    head = f"право {rows[0]['right']} дн. на робочий рік" if rows[0]["right"] is not None else "право не вказано"
    return f"<p>Щорічна відпустка ({head}), за зареєстрованими наказами:</p><ul>{''.join(lines)}</ul>"
