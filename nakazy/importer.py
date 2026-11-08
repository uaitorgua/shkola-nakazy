"""Гнучкий імпорт людей з XLSX/CSV (АІКОМ2 та будь-які списки).

Формат вивантажень АІКОМ публічно не описаний (див. docs/AIKOM.md), тому:
- рядок заголовків шукаємо серед перших 30 рядків за кількістю збігів зі словником синонімів;
- колонки зіставляються автоматично, користувач підтверджує, зіставлення запам'ятовується;
- ПІБ буває разом або окремо, клас – разом («5-А») або паралель + літера;
- дати: Excel-дата, «01.02.2015», «2015-02-01», «1.2.15»;
- CSV: UTF-8 або Windows-1251, роздільник ; , або табуляція;
- повторний імпорт оновлює наявних (ключ: ідентифікатор або ПІБ + дата народження), не дублює;
- кого немає у файлі, лише позначаємо як «можливо вибув», нічого не видаляємо.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import os
import re
from dataclasses import dataclass, field

from .db import Database
from .names import split_full
from .people import People

# поле -> синоніми заголовків (нижній регістр, без розділових знаків)
SYNONYMS: dict[str, list[str]] = {
    "full": ["піб", "прізвище ім я по батькові", "прізвище імя по батькові", "прізвище ім я та по батькові",
             "прізвище власне ім я по батькові", "учень", "учні", "здобувач освіти", "працівник",
             "педагогічний працівник", "прізвище ініціали", "пiб"],
    "last": ["прізвище"],
    "first": ["ім я", "імя", "власне ім я", "ім я учня"],
    "middle": ["по батькові", "по батькові учня"],
    "birth": ["дата народження", "дата нар", "д н", "народився", "рік народження"],
    "sex": ["стать"],
    "cls": ["клас", "клас група", "назва класу"],
    "parallel": ["паралель", "рік навчання", "клас цифра"],
    "letter": ["літера", "літера класу", "буква"],
    "case_no": ["номер особової справи", "особова справа", "№ особової справи", "номер справи"],
    "enrolled": ["дата зарахування", "зарахований"],
    "position": ["посада", "найменування посади"],
    "rate": ["ставка", "кількість ставок", "обсяг ставки"],
    "employment": ["основне місце роботи", "сумісництво", "вид зайнятості"],
    "subjects": ["предмет", "предмети", "навчальні предмети", "викладає"],
    "category": ["категорія", "кваліфікаційна категорія"],
    "ext_id": ["ід", "id", "ідентифікатор", "код", "код учня", "код працівника", "id учня"],
}
FIELD_TITLES = {"full": "ПІБ разом", "last": "Прізвище", "first": "Ім'я", "middle": "По батькові",
                "birth": "Дата народження", "sex": "Стать", "cls": "Клас", "parallel": "Паралель",
                "letter": "Літера класу", "case_no": "№ особової справи", "enrolled": "Дата зарахування",
                "position": "Посада", "rate": "Ставка", "employment": "Вид зайнятості", "subjects": "Предмети",
                "category": "Категорія", "ext_id": "Ідентифікатор"}


def norm(h) -> str:
    s = str(h or "").lower().replace("’", " ").replace("'", " ").replace("ʼ", " ").replace("ё", "е")
    s = re.sub(r"[^\w№ ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def read_table(path: str) -> list[list[str]]:
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xlsm"):
        from openpyxl import load_workbook
        wb = load_workbook(path, read_only=True, data_only=True)
        ws = max(wb.worksheets, key=lambda w: (w.max_row or 0))  # найбільший аркуш
        rows = [[_cell(v) for v in r] for r in ws.iter_rows(values_only=True)]
        wb.close()
        return rows
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "cp1251"):
        try:
            text = raw.decode(enc); break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", "replace")
    try:
        dialect = csv.Sniffer().sniff(text[:5000], delimiters=";,\t")
    except csv.Error:
        dialect = csv.excel; dialect.delimiter = ";"
    return [list(r) for r in csv.reader(io.StringIO(text), dialect)]


def _cell(v):
    if v is None:
        return ""
    if isinstance(v, dt.datetime):
        return v.date().isoformat()
    if isinstance(v, dt.date):
        return v.isoformat()
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _match(h: str) -> str | None:
    n = norm(h)
    if not n:
        return None
    for f, syns in SYNONYMS.items():
        if n in syns:
            return f
    for f, syns in SYNONYMS.items():  # частковий збіг: «Прізвище учня», «Дата народження (дд.мм.рррр)»
        if any(n.startswith(s + " ") for s in syns if len(s) > 3):
            return f
    return None


def detect_header(rows: list[list[str]]) -> tuple[int, dict[int, str]]:
    best, best_i, best_map = -1, 0, {}
    for i, row in enumerate(rows[:30]):
        m = {j: f for j, h in enumerate(row) if (f := _match(h))}
        score = len(set(m.values()))
        if score > best:
            best, best_i, best_map = score, i, m
    # дублікати поля: лишаємо першу колонку
    seen, clean = set(), {}
    for j in sorted(best_map):
        if best_map[j] not in seen:
            seen.add(best_map[j]); clean[j] = best_map[j]
    return best_i, clean


def parse_date(s: str) -> str | None:
    s = (s or "").strip()
    if not s:
        return None
    if re.fullmatch(r"\d{4,5}(\.0)?", s) and 20000 < float(s) < 60000:  # серійна дата Excel
        return (dt.date(1899, 12, 30) + dt.timedelta(days=int(float(s)))).isoformat()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            d = dt.datetime.strptime(s[:19], fmt).date()
            return d.isoformat() if 1900 < d.year < 2100 else None
        except ValueError:
            continue
    return None


def norm_cls(c: str, parallel: str = "", letter: str = "") -> str:
    c = (c or "").strip()
    if not c and parallel:
        c = f"{parallel}{letter}"
    m = re.fullmatch(r"(\d{1,2})\s*[-–\s]?\s*\(?([А-ЯІЇЄҐа-яіїєґA-Za-z]?)\)?\s*(клас)?", c)
    if m:
        return f"{m.group(1)}-{m.group(2).upper()}" if m.group(2) else m.group(1)
    return c


def _sex(s: str) -> str:
    s = norm(s)
    return "f" if s[:1] in ("ж", "f") else ("m" if s[:1] in ("ч", "m") else "")


@dataclass
class Plan:
    new: list[dict] = field(default_factory=list)
    changed: list[tuple[int, dict, dict]] = field(default_factory=list)   # (id, старі, нові)
    same: int = 0
    missing: list[int] = field(default_factory=list)   # активні в базі, немає у файлі
    errors: list[str] = field(default_factory=list)


def rows_to_people(rows, header_i: int, mapping: dict[int, str], kind: str) -> tuple[list[dict], list[str]]:
    out, errors = [], []
    for n, row in enumerate(rows[header_i + 1:], header_i + 2):
        v = {f: (row[j] if j < len(row) else "") for j, f in mapping.items()}
        if not any(str(x).strip() for x in v.values()):
            continue
        last, first, middle = v.get("last", ""), v.get("first", ""), v.get("middle", "")
        if v.get("full") and not last:
            last, first, middle = split_full(v["full"])
        last, first, middle = (x.strip().strip(",") for x in (last, first, middle))
        if not last or re.fullmatch(r"[\d\s.№]+", last) or norm(last) in ("разом", "всього", "усього"):
            continue
        if not first:
            errors.append(f"рядок {n}: немає імені ({last})")
        p = {"kind": kind, "last": last, "first": first, "middle": middle}
        if "birth" in v:
            b = parse_date(v["birth"])
            if v["birth"].strip() and not b:
                errors.append(f"рядок {n}: незрозуміла дата «{v['birth']}»")
            p["birth"] = b
        if "sex" in v and _sex(v["sex"]):
            p["sex"] = _sex(v["sex"])
        if kind == "pupil" and ("cls" in v or "parallel" in v):
            p["cls"] = norm_cls(v.get("cls", ""), v.get("parallel", ""), v.get("letter", ""))
        for f in ("case_no", "position", "rate", "employment", "subjects", "category", "ext_id"):
            if v.get(f, "").strip():
                p[f] = v[f].strip()
        if v.get("enrolled"):
            p["enrolled"] = parse_date(v["enrolled"])
        out.append(p)
    return out, errors


def _key(p) -> tuple:
    return (norm(p["last"]), norm(p["first"]), norm(p["middle"]), p["birth"] or "")


def make_plan(db: Database, people: list[dict], kind: str) -> Plan:
    plan = Plan()
    existing = db.con.execute("SELECT * FROM people WHERE kind = ?", (kind,)).fetchall()
    by_ext = {r["ext_id"]: r for r in existing if r["ext_id"]}
    by_key = {_key(r): r for r in existing}
    by_name = {}
    for r in existing:
        by_name.setdefault(_key(r)[:3], []).append(r)
    seen = set()
    for p in people:
        p.setdefault("birth", None)
        r = by_ext.get(p.get("ext_id", "")) or by_key.get(_key(p))
        if r is None and not p["birth"]:
            cands = by_name.get(_key(p)[:3], [])
            r = cands[0] if len(cands) == 1 else None
        if r is None:
            plan.new.append(p); continue
        if r["id"] in seen:
            plan.errors.append(f"повтор у файлі: {p['last']} {p['first']}"); continue
        seen.add(r["id"])
        diff = {k: v for k, v in p.items() if k != "kind" and v not in (None, "") and str(r[k] or "") != str(v)}
        if r["status"] != "active":
            diff["status"] = "active"
        if diff:
            plan.changed.append((r["id"], {k: r[k] for k in diff}, diff))
        else:
            plan.same += 1
    plan.missing = [r["id"] for r in existing if r["status"] == "active" and r["id"] not in seen]
    return plan


def apply_plan(db: Database, plan: Plan, mark_missing_left: bool = False) -> dict:
    from .backup import make_backup
    make_backup(db.path, "before-import")
    ppl = People(db)
    with db.tx():
        for p in plan.new:
            ppl.add(**p)
        for pid, _old, new in plan.changed:
            ppl.update(pid, **new)
        if mark_missing_left:
            for pid in plan.missing:
                ppl.update(pid, status="left")
    return {"new": len(plan.new), "changed": len(plan.changed), "left": len(plan.missing) if mark_missing_left else 0}


def save_mapping(db: Database, headers: list[str], mapping: dict[int, str]):
    key = "map." + "|".join(norm(h) for h in headers)[:500]
    db.set_setting(key, json.dumps({norm(headers[j]): f for j, f in mapping.items()}, ensure_ascii=False))


def load_mapping(db: Database, headers: list[str]) -> dict[int, str] | None:
    raw = db.get_setting("map." + "|".join(norm(h) for h in headers)[:500])
    if not raw:
        return None
    m = json.loads(raw)
    return {j: m[norm(h)] for j, h in enumerate(headers) if norm(h) in m}
