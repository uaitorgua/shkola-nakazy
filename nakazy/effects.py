"""Наказ оновлює довідник людей: після реєстрації зарахування, вибуття, переведення, прийняття, звільнення
картка людини змінюється сама; скасування наказу повертає попередні значення.

Діє лише для людей, вибраних у майстрі шаблону з довідника (зв'язок order_persons). Кожна зміна записується
в order_effects (поле, було, стало), тож скасування відкочує тільки те, що змінив саме цей наказ і що відтоді
не правили вручну. Номер особової справи учня (алфавітна книга) видається при зарахуванні: літера прізвища
і наступний номер за цією літерою, напр. «К-15»; його можна змінити в картці.
"""
from __future__ import annotations

import re

from .db import Database, format_date

# шаблон → (роль людини, дії). Дія: (поле картки, джерело): "=значення", "@поле шаблону", "#date" (дата наказу),
# "#case" (номер особової справи, якщо порожній). Позначка "?" – лише якщо поле в картці порожнє.
RULES: dict[str, tuple[str, list[tuple[str, str]]]] = {
    "u_enroll": ("pupil", [("status", "=active"), ("cls", "@cls"), ("enrolled", "#date"), ("case_no", "#case")]),
    "u_extern": ("pupil", [("status", "=active"), ("cls", "@cls"), ("enrolled", "#date"), ("case_no", "#case")]),
    "u_expel": ("pupil", [("status", "=left")]),
    "u_abroad": ("pupil", [("status", "=left")]),
    "u_transfer_class": ("pupil", [("cls", "@cls_new")]),
    "k_hire": ("employee", [("status", "=active"), ("position", "?@position")]),
    "k_hire_part": ("employee", [("status", "=active"), ("position", "?@position"), ("employment", "=сумісництво")]),
    "k_probation": ("employee", [("status", "=active"), ("position", "?@position")]),
    "k_dismiss": ("employee", [("status", "=left")]),
    "k_move": ("employee", [("position", "@position_new")]),
}
FIELD_TITLES = {"status": "статус", "cls": "клас", "enrolled": "дата зарахування", "case_no": "особова справа",
                "position": "посада", "employment": "вид зайнятості"}
VALUE_TITLES = {"active": "активний", "left": "вибув"}


def next_case_no(db: Database, last_name: str) -> str:
    """Наступний номер особової справи за літерою прізвища: «К-15»."""
    letter = (last_name or "?").strip()[:1].upper()
    best = 0
    for (c,) in db.con.execute("SELECT case_no FROM people WHERE kind = 'pupil' AND case_no LIKE ?", (letter + "%",)):
        m = re.fullmatch(re.escape(letter) + r"\s*[-/ ]?\s*(\d+)", (c or "").strip())
        if m:
            best = max(best, int(m.group(1)))
    return f"{letter}-{best + 1}"


def _norm_cls(text: str) -> str:
    from .importer import norm_cls
    return norm_cls(text) if text else ""


def apply(db: Database, order_id: int) -> list[str]:
    """Застосувати дії зареєстрованого наказу. Повертає рядки для повідомлення."""
    row = db.get(order_id)
    rule = RULES.get(row["template_id"] or "")
    if not rule or row["status"] != "registered":
        return []
    if db.con.execute("SELECT 1 FROM order_effects WHERE order_id = ?", (order_id,)).fetchone():
        return []  # уже застосовано
    role, actions = rule
    values, group = db.order_values(order_id)
    persons = db.con.execute("SELECT p.* FROM people p JOIN order_persons op ON op.person_id = p.id "
                             "WHERE op.order_id = ? AND op.role = ?", (order_id, role)).fetchall()
    if not persons:
        return ["Людину в цьому наказі не вибрано з довідника, тому довідник не змінено."]
    out = []
    with db.tx():
        for p in persons:
            own = next((g for g in group if g.get("_pid") == p["id"]), {})
            changed = []
            for field, src in actions:
                only_empty = src.startswith("?")
                src = src.lstrip("?")
                if src.startswith("="):
                    new = src[1:]
                elif src.startswith("@"):
                    new = (own.get(src[1:]) or values.get(src[1:]) or "").strip()
                    if field == "cls":
                        new = _norm_cls(new)
                elif src == "#date":
                    new = row["date"]
                else:  # "#case"
                    new = "" if (p["case_no"] or "").strip() else next_case_no(db, p["last"])
                old = p[field]
                if not new or new in ("…",) or str(old or "") == str(new) or (only_empty and (old or "").strip()):
                    continue
                db.con.execute(f"UPDATE people SET {field} = ? WHERE id = ?", (new, p["id"]))
                db.con.execute("INSERT INTO order_effects (order_id, person_id, field, old, new) VALUES (?,?,?,?,?)",
                               (order_id, p["id"], field, old, new))
                shown = format_date(new) if field == "enrolled" else VALUE_TITLES.get(new, new)
                changed.append(f"{FIELD_TITLES[field]}: {shown}")
            if changed:
                out.append(f"{p['last']} {p['first']}: " + ", ".join(changed))
    return out or ["Довідник уже відповідає наказу, змін немає."]


def revert(db: Database, order_id: int) -> list[str]:
    """Скасування наказу: повернути значення, які він змінив і які відтоді не правили."""
    rows = db.con.execute("SELECT e.*, p.last, p.first FROM order_effects e JOIN people p ON p.id = e.person_id "
                          "WHERE e.order_id = ? ORDER BY e.id DESC", (order_id,)).fetchall()
    out = []
    with db.tx():
        for e in rows:
            cur = db.con.execute(f"SELECT {e['field']} FROM people WHERE id = ?", (e["person_id"],)).fetchone()[0]
            name = f"{e['last']} {e['first']}"
            if str(cur or "") == str(e["new"] or ""):
                db.con.execute(f"UPDATE people SET {e['field']} = ? WHERE id = ?", (e["old"], e["person_id"]))
                out.append(f"{name}: {FIELD_TITLES[e['field']]} повернуто")
            else:
                out.append(f"{name}: {FIELD_TITLES[e['field']]} змінено вручну після наказу, лишено як є")
        db.con.execute("DELETE FROM order_effects WHERE order_id = ?", (order_id,))
    return out


def alphabet_rows(db: Database) -> list[dict]:
    """Алфавітна книга учнів: особова справа, ПІБ, клас, зарахування й вибуття з наказами."""
    def order_of(pid, templates):
        q = ",".join("?" * len(templates))
        r = db.con.execute(
            f"SELECT o.date, o.reg_index FROM orders o JOIN order_persons op ON op.order_id = o.id "
            f"WHERE op.person_id = ? AND o.status = 'registered' AND o.template_id IN ({q}) "
            "ORDER BY o.date DESC LIMIT 1", (pid, *templates)).fetchone()
        return (format_date(r["date"]), r["reg_index"]) if r else ("", "")

    def key(p):
        m = re.fullmatch(r"(\D*?)\s*[-/ ]?\s*(\d+)", (p["case_no"] or "").strip())
        return (p["last"][:1].upper(), int(m.group(2)) if m else 10**9, p["last"], p["first"])
    out = []
    for p in sorted(db.con.execute("SELECT * FROM people WHERE kind = 'pupil'").fetchall(), key=key):
        in_d, in_n = order_of(p["id"], ("u_enroll", "u_enroll_first", "u_extern"))
        out_d, out_n = order_of(p["id"], ("u_expel", "u_abroad")) if p["status"] == "left" else ("", "")
        out.append({"letter": p["last"][:1].upper(), "case_no": p["case_no"] or "",
                    "name": f"{p['last']} {p['first']} {p['middle']}".strip(), "birth": format_date(p["birth"]),
                    "cls": p["cls"], "in_date": in_d or format_date(p["enrolled"]), "in_order": in_n,
                    "out_date": out_d, "out_order": out_n, "left": p["status"] == "left"})
    return out


ALPHABET_HEAD = ["Літера", "№ особової справи", "Прізвище, ім'я, по батькові", "Дата народження", "Клас",
                 "Дата зарахування", "Наказ про зарахування", "Дата вибуття", "Наказ про вибуття"]


def export_alphabet_xlsx(db: Database, path: str) -> str:
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook(); ws = wb.active; ws.title = "Алфавітна книга"
    ws.append(ALPHABET_HEAD)
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in alphabet_rows(db):
        ws.append([r["letter"], r["case_no"], r["name"], r["birth"], r["cls"], r["in_date"], r["in_order"],
                   r["out_date"], r["out_order"]])
    for i, w in enumerate((8, 18, 36, 16, 8, 16, 20, 14, 18), 1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = w
    ws.freeze_panes = "A2"
    wb.save(path)
    return path
