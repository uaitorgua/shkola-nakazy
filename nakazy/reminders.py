"""Нагадування: строки виконання наказів, давні чернетки, відпустки з графіка без наказу, атестація цього року,
номенклатура справ на наступний рік. Це підказки програми за даними, які ввів заклад, а не норми."""
from __future__ import annotations

import datetime as dt

from .db import Database, format_date

SOON_DAYS = 7          # строк виконання наближається
DRAFT_DAYS = 7         # чернетка лежить без реєстрації
LEAVE_DAYS = 14        # відпустка з графіка починається, а наказу ще немає


def reminders(db: Database, today: dt.date | None = None) -> list[dict]:
    """[{level: 'увага'|'нагадування', text, order_id}] – спершу прострочене."""
    t = today or dt.date.today()
    iso = t.isoformat()
    out = []
    for o in db.con.execute("SELECT * FROM orders WHERE status = 'registered' AND done = 0 AND due_date != '' "
                            "ORDER BY due_date").fetchall():
        ref = f"наказ від {format_date(o['date'])} № {o['reg_index']} «{o['title']}»"
        who = f" (контроль: {o['controller']})" if o["controller"] else ""
        if o["due_date"] < iso:
            out.append({"level": "увага", "order_id": o["id"],
                        "text": f"Прострочено виконання ({format_date(o['due_date'])}): {ref}{who}"})
        elif o["due_date"] <= (t + dt.timedelta(days=SOON_DAYS)).isoformat():
            out.append({"level": "нагадування", "order_id": o["id"],
                        "text": f"Строк виконання {format_date(o['due_date'])}: {ref}{who}"})
    old = (dt.datetime.combine(t, dt.time()) - dt.timedelta(days=DRAFT_DAYS)).isoformat()
    for o in db.con.execute("SELECT * FROM orders WHERE status = 'draft' AND created_at < ? ORDER BY created_at",
                            (old,)).fetchall():
        out.append({"level": "нагадування", "order_id": o["id"],
                    "text": f"Чернетка без реєстрації понад {DRAFT_DAYS} днів: «{o['title']}»"})
    till = (t + dt.timedelta(days=LEAVE_DAYS)).isoformat()
    for r in db.con.execute(
            "SELECT lp.*, p.last, p.first, o.status AS ostatus FROM leave_plan lp JOIN people p ON p.id = lp.person_id "
            "LEFT JOIN orders o ON o.id = lp.order_id WHERE lp.from_date BETWEEN ? AND ? "
            "AND (lp.order_id IS NULL OR o.status = 'cancelled') ORDER BY lp.from_date", (iso, till)).fetchall():
        out.append({"level": "нагадування", "order_id": None,
                    "text": f"Відпустка за графіком з {format_date(r['from_date'])}, наказу ще немає: "
                            f"{r['last']} {r['first']}"})
    for p in db.con.execute("SELECT * FROM people WHERE kind = 'staff' AND status = 'active' AND attest_year = ? "
                            "ORDER BY last", (t.year,)).fetchall():
        out.append({"level": "нагадування", "order_id": None,
                    "text": f"Атестація у {t.year} році: {p['last']} {p['first']} {p['middle']}".strip()})
    if t.month == 12:
        has = db.con.execute("SELECT name FROM sqlite_master WHERE name = 'nomenclature'").fetchone() and \
            db.con.execute("SELECT 1 FROM nomenclature WHERE year = ?", (t.year + 1,)).fetchone()
        if not has:
            out.append({"level": "нагадування", "order_id": None,
                        "text": f"Номенклатуру справ на {t.year + 1} рік ще не складено («Справи…»)."})
    return sorted(out, key=lambda r: r["level"] != "увага")
