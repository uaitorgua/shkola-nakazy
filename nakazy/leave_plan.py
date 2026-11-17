"""Графік відпусток як таблиця (як «Планування відпусток» у HRMIS).

Рядок графіка: працівник, вид відпустки, тривалість, дати, робочий рік. З таблиці створюються:
наказ про затвердження графіка (додаток – таблиця з грифом «ЗАТВЕРДЖЕНО») і накази про надання
щорічної відпустки – окремі або один груповий. Рядок пам'ятає свій наказ, тож двічі не створюється.
Норми: Закон України «Про відпустки», ст. 10; КЗпП України, ст. 79 – черговість визначається графіком,
який затверджується за погодженням з профспілковим органом (звірено на zakon.rada.gov.ua 17.11.2026).
"""
from __future__ import annotations

import datetime as dt
import html

from .db import Database, format_date

FIELDS = ("person_id", "vtype", "days", "from_date", "to_date", "period", "note")


class LeavePlan:
    def __init__(self, db: Database):
        self.db, self.con = db, db.con

    def rows(self, year: int):
        return self.con.execute(
            "SELECT lp.*, p.last, p.first, p.middle, p.position, p.leave_right, o.reg_index, o.status AS order_status "
            "FROM leave_plan lp JOIN people p ON p.id = lp.person_id LEFT JOIN orders o ON o.id = lp.order_id "
            "WHERE lp.year = ? ORDER BY lp.from_date IS NULL, lp.from_date, p.last, p.first", (year,)).fetchall()

    def add(self, year: int, person_id: int, **f) -> int:
        f = {k: v for k, v in f.items() if k in FIELDS}
        f.setdefault("vtype", "основну")
        cols = ["year", "person_id", *f]
        with self.db.tx():
            cur = self.con.execute(f"INSERT INTO leave_plan ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                                   [year, person_id, *f.values()])
        return cur.lastrowid

    def update(self, row_id: int, **f):
        f = {k: v for k, v in f.items() if k in FIELDS}
        if f:
            with self.db.tx():
                self.con.execute(f"UPDATE leave_plan SET {', '.join(k + ' = ?' for k in f)} WHERE id = ?",
                                 [*f.values(), row_id])

    def delete(self, row_id: int):
        with self.db.tx():
            self.con.execute("DELETE FROM leave_plan WHERE id = ?", (row_id,))

    def problems(self, year: int) -> list[str]:
        """Попередження: дати не по порядку, понад право на відпустку (сума запланованих днів)."""
        out, total = [], {}
        for r in self.rows(year):
            name = f"{r['last']} {r['first']}".strip()
            if r["from_date"] and r["to_date"] and r["to_date"] < r["from_date"]:
                out.append(f"{name}: дата закінчення раніше за дату початку.")
            t = total.setdefault(r["person_id"], [name, r["leave_right"], 0])
            t[2] += r["days"] or 0
        for name, right, days in total.values():
            if right is not None and days > right:
                out.append(f"{name}: заплановано {days} дн., право {right} дн.")
        return out

    def schedule_html(self, year: int) -> str:
        """Таблиця графіка для додатка до наказу."""
        head = ("№", "Прізвище, ім'я, по батькові", "Посада", "Вид відпустки", "Кількість календарних днів",
                "Дата початку", "Дата закінчення", "Робочий рік", "Примітка")
        body = "".join(
            "<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in (
                i, f"{r['last']} {r['first']} {r['middle']}".strip(), r["position"], f"щорічна {_nom(r['vtype'])}",
                r["days"] or "", format_date(r["from_date"]), format_date(r["to_date"]), r["period"], r["note"]))
            + "</tr>" for i, r in enumerate(self.rows(year), 1))
        return ("<table border='1' cellspacing='0' cellpadding='3'><tr>"
                + "".join(f"<th>{h}</th>" for h in head) + f"</tr>{body}</table>")

    def make_schedule_order(self, year: int, union: str = "") -> int:
        """Чернетка наказу «Про затвердження графіка відпусток» з таблицею в додатку."""
        from .ui.order_editor import create_from_template
        oid = create_from_template(self.db, "v_schedule", {"year": str(year), "union": union})
        with self.db.tx():
            self.con.execute("UPDATE attachments SET body_html = ? WHERE order_id = ? AND n = 1",
                             (self.schedule_html(year), oid))
        return oid

    def make_leave_orders(self, row_ids: list[int], group: bool = False) -> list[int]:
        """Накази про щорічну відпустку для рядків без наказу: окремі або один груповий."""
        from .people import People, person_values
        from .ui.order_editor import create_from_template
        ppl = People(self.db)
        q = ",".join("?" * len(row_ids))
        rows = [r for r in self.con.execute(f"SELECT * FROM leave_plan WHERE id IN ({q}) ORDER BY from_date",
                                            row_ids).fetchall()
                if r["order_id"] is None or self._order_gone(r["order_id"])]
        if not rows:
            return []
        common = {"application": self._basis(rows[0]["year"])}

        def person_row(r):
            v = person_values(ppl, ppl.get(r["person_id"]), "employee")
            v.update({"vtype": r["vtype"], "days": str(r["days"] or ""), "from_date": format_date(r["from_date"]),
                      "to_date": format_date(r["to_date"]), "period": r["period"], "_pid": r["person_id"]})
            return v
        made = []
        if group and len(rows) > 1:
            oid = create_from_template(self.db, "v_annual", common, group=[person_row(r) for r in rows])
            made.append(oid)
            self._mark([r["id"] for r in rows], oid)
        else:
            for r in rows:
                v = person_row(r); pid = v.pop("_pid")
                oid = create_from_template(self.db, "v_annual", {**common, **v}, persons={"employee": pid})
                made.append(oid); self._mark([r["id"]], oid)
        return made

    def _order_gone(self, oid: int) -> bool:
        row = self.db.get(oid)
        return row is None or row["status"] == "cancelled"

    def _mark(self, ids, oid):
        with self.db.tx():
            self.con.executemany("UPDATE leave_plan SET order_id = ? WHERE id = ?", [(oid, i) for i in ids])

    def _basis(self, year: int) -> str:
        """Підстава в наказі про відпустку: зареєстрований наказ про затвердження графіка, якщо є."""
        r = self.con.execute("SELECT date, reg_index FROM orders WHERE template_id = 'v_schedule' AND status = "
                             "'registered' AND title LIKE ? ORDER BY date DESC LIMIT 1", (f"%{year}%",)).fetchone()
        if r:
            return f"наказу від {format_date(r['date'])} № {r['reg_index']} про затвердження графіка відпусток"
        return "заяви працівника"


def _nom(vtype: str) -> str:
    """«основну» → «основна» для таблиці."""
    return {"основну": "основна", "додаткову": "додаткова"}.get((vtype or "").strip(), vtype or "")


def default_year(today: dt.date | None = None) -> int:
    return (today or dt.date.today()).year
