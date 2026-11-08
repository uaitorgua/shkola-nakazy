"""Довідник людей: учні й працівники, класи, зв'язок з наказами.

Персональні дані лише локально. РНОКПП не зберігаємо (для наказів не потрібен).
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3

from .db import Database, _now
from .names import all_cases, guess_sex, initials

PERSON_FIELDS = ("kind", "last", "first", "middle", "birth", "sex", "status", "cls", "case_no", "enrolled",
                 "position", "rate", "subjects", "category", "employment", "ext_id", "note")
KIND_TITLES = {"pupil": "Учні", "staff": "Працівники"}


def school_year(today: dt.date | None = None) -> str:
    t = today or dt.date.today()
    y = t.year if t.month >= 9 else t.year - 1
    return f"{y}/{y + 1}"


class People:
    def __init__(self, db: Database):
        self.db, self.con = db, db.con

    def add(self, **f) -> int:
        f = {k: v for k, v in f.items() if k in PERSON_FIELDS}
        if not (f.get("last") or "").strip():
            raise ValueError("Не вказано прізвище")
        f.setdefault("sex", guess_sex(f.get("first", ""), f.get("middle", "")))
        now = _now()
        cols = [*f, "created_at", "updated_at"]
        with self.db.tx():
            cur = self.con.execute(f"INSERT INTO people ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                                   [*f.values(), now, now])
        return cur.lastrowid

    def update(self, pid: int, **f):
        f = {k: v for k, v in f.items() if k in PERSON_FIELDS or k == "forms_json"}
        if f:
            with self.db.tx():
                self.con.execute(f"UPDATE people SET {', '.join(k + ' = ?' for k in f)}, updated_at = ? WHERE id = ?",
                                 [*f.values(), _now(), pid])

    def get(self, pid: int) -> sqlite3.Row | None:
        return self.con.execute("SELECT * FROM people WHERE id = ?", (pid,)).fetchone()

    def find(self, kind: str | None = None, text: str = "", active_only: bool = True, cls: str | None = None):
        sql, a = "SELECT * FROM people WHERE 1=1", []
        if kind:
            sql += " AND kind = ?"; a.append(kind)
        if active_only:
            sql += " AND status = 'active'"
        if cls:
            sql += " AND cls = ?"; a.append(cls)
        for w in text.split():
            sql += " AND (last || ' ' || first || ' ' || middle || ' ' || cls || ' ' || position) LIKE ?"
            a.append(f"%{w}%")
        sql += " ORDER BY kind, cls, last, first"
        return self.con.execute(sql, a).fetchall()

    def classes(self) -> list[str]:
        rows = self.con.execute("SELECT DISTINCT cls FROM people WHERE kind = 'pupil' AND status = 'active' "
                                "AND cls != ''").fetchall()
        return sorted((r[0] for r in rows), key=_cls_key)

    # відмінки
    def forms(self, row) -> dict[str, str]:
        f = all_cases(row["last"], row["first"], row["middle"], row["sex"] or None)
        f.update({k: v for k, v in json.loads(row["forms_json"] or "{}").items() if v})
        f["short"] = initials(row["last"], row["first"], row["middle"])
        return f

    def set_forms(self, pid: int, forms: dict[str, str]):
        self.update(pid, forms_json=json.dumps(forms, ensure_ascii=False))

    # класні керівники
    def set_teacher(self, cls: str, teacher_id: int | None, year: str | None = None):
        with self.db.tx():
            self.con.execute("INSERT OR REPLACE INTO classes VALUES (?, ?, ?)", (year or school_year(), cls, teacher_id))

    def teacher(self, cls: str, year: str | None = None):
        r = self.con.execute("SELECT teacher_id FROM classes WHERE school_year = ? AND name = ?",
                             (year or school_year(), cls)).fetchone()
        return self.get(r[0]) if r and r[0] else None

    # зв'язок з наказами
    def link(self, order_id: int, person_id: int, role: str = ""):
        with self.db.tx():
            self.con.execute("INSERT OR IGNORE INTO order_persons VALUES (?, ?, ?)", (order_id, person_id, role))

    def orders_of(self, person_id: int):
        return self.con.execute("SELECT o.*, op.role FROM orders o JOIN order_persons op ON op.order_id = o.id "
                                "WHERE op.person_id = ? ORDER BY o.date DESC, o.id DESC", (person_id,)).fetchall()

    def persons_of(self, order_id: int):
        return self.con.execute("SELECT p.*, op.role FROM people p JOIN order_persons op ON op.person_id = p.id "
                                "WHERE op.order_id = ?", (order_id,)).fetchall()

    def class_list_html(self, cls: str) -> str:
        """Таблиця «список учнів класу» для додатка."""
        rows = self.find("pupil", cls=cls)
        body = "".join(f"<tr><td>{i}</td><td>{r['last']} {r['first']} {r['middle']}</td>"
                       f"<td>{_d(r['birth'])}</td></tr>" for i, r in enumerate(rows, 1))
        return ("<table><tr><th>№ з/п</th><th>Прізвище, власне ім'я, по батькові</th><th>Дата народження</th></tr>"
                f"{body}</table>")


def _d(iso):
    try:
        return dt.date.fromisoformat(iso).strftime("%d.%m.%Y")
    except (TypeError, ValueError):
        return iso or ""


def _cls_key(c: str):
    import re
    m = re.match(r"(\d+)", c or "")
    return (int(m.group(1)) if m else 99, c)


def person_values(ppl: People, row, key: str) -> dict[str, str]:
    """Значення для шаблону: {key} – називний, {key.gen|dat|acc}, {key.role}, пов'язані поля."""
    f = ppl.forms(row)
    v = {key: f["nom"], f"{key}.gen": f["gen"], f"{key}.dat": f["dat"], f"{key}.acc": f["acc"],
         f"{key}.short": f["short"]}
    fem = (row["sex"] or "") == "f"
    if row["kind"] == "pupil":
        v[f"{key}.role"] = "учениці" if fem else "учня"
        if row["cls"]:
            v["cls"] = row["cls"]
        if row["birth"]:
            v["birth"] = _d(row["birth"])
    else:
        if row["position"]:
            v["position"] = row["position"]
    return v
