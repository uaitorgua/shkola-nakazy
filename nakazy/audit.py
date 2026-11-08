"""Перевірка реєстру «очима аудитора»: цілісність нумерації, дат, реквізитів, зв'язків.

Кожна знахідка: (рівень, текст). Рівні: «помилка» (порушення № 676 або цілісності бази),
«увага» (сумнівне, перевірити секретарю).
"""
from __future__ import annotations

import datetime as dt

from .db import KIND_BY_CODE, Database, format_date, make_index


def audit(db: Database, today: dt.date | None = None) -> list[tuple[str, str]]:
    today = today or dt.date.today()
    out: list[tuple[str, str]] = []
    con = db.con

    ok = con.execute("PRAGMA integrity_check").fetchone()[0]
    if ok != "ok":
        out.append(("помилка", f"Пошкодження файлу бази: {ok}"))

    groups = con.execute("SELECT DISTINCT kind, year FROM orders WHERE number IS NOT NULL").fetchall()
    for g in groups:
        kind, year = g["kind"], g["year"]
        name = KIND_BY_CODE[kind].title
        rows = db.journal(kind, year)
        nums = [r["number"] for r in rows]
        expected = list(range(1, len(nums) + 1))
        imported = any(r["source"] == "import" for r in rows)
        if nums != expected:
            missing = sorted(set(range(1, max(nums) + 1)) - set(nums))
            # в архіві пропуски можливі (не всі накази оцифровано): лише увага
            out.append(("увага" if imported and len(set(nums)) == len(nums) else "помилка", f"{name}, {year}: пропуски або повтори номерів (бракує {missing[:10]})"))
        cnt = con.execute("SELECT last_number FROM counters WHERE kind = ? AND year = ?", (kind, year)).fetchone()
        if not cnt or cnt[0] != max(nums):
            out.append(("помилка", f"{name}, {year}: лічильник ({cnt[0] if cnt else '–'}) не збігається "
                                   f"з останнім номером ({max(nums)})"))
        prev = None
        for r in rows:
            if r["reg_index"] != make_index(kind, r["number"]):
                out.append(("помилка", f"Наказ {r['reg_index']}: індекс не відповідає виду й номеру"))
            if not r["date"] or int(r["date"][:4]) != year:
                out.append(("помилка", f"Наказ № {r['reg_index']}: дата {r['date']} не з {year} року"))
            elif prev and r["date"] < prev["date"]:
                out.append(("увага" if "import" in (r["source"], prev["source"]) else "помилка", f"{name}: наказ № {r['reg_index']} від {format_date(r['date'])} "
                                       f"датований раніше за № {prev['reg_index']} від {format_date(prev['date'])}"))
            if r["date"] and dt.date.fromisoformat(r["date"]) > today:
                out.append(("увага", f"Наказ № {r['reg_index']} датований майбутнім ({format_date(r['date'])})"))
            if not r["title"].startswith("Про "):
                out.append(("увага", f"Наказ № {r['reg_index']}: заголовок не починається з «Про»"))
            if not r["signer"].strip():
                out.append(("увага" if r["source"] == "import" else "помилка",
                            f"Наказ № {r['reg_index']}: не вказано підписанта"))
            if r["status"] == "cancelled" and "Скасовано" not in r["notes"]:
                out.append(("увага", f"Наказ № {r['reg_index']}: скасовано без підстави в примітках"))
            prev = r

    for r in con.execute("SELECT * FROM orders WHERE status = 'draft' AND number IS NOT NULL"):
        out.append(("помилка", f"Чернетка «{r['title']}» має номер {r['reg_index']}"))
    for r in con.execute("SELECT * FROM orders WHERE status != 'draft' AND number IS NULL"):
        out.append(("помилка", f"Наказ «{r['title']}» зареєстровано без номера"))
    for r in con.execute("SELECT o.* FROM orders o LEFT JOIN orders a ON a.id = o.amends_order_id "
                         "WHERE o.amends_order_id IS NOT NULL AND (a.id IS NULL OR a.status = 'draft')"):
        out.append(("помилка", f"Наказ «{r['title']}» змінює неіснуючий або незареєстрований наказ"))
    for r in con.execute("SELECT * FROM orders WHERE status = 'draft' AND updated_at < ?",
                         ((today - dt.timedelta(days=30)).isoformat(),)):
        out.append(("увага", f"Чернетка «{r['title']}» не змінювалась понад 30 днів"))
    # зареєстровані тексти не змінювались після реєстрації
    for r in con.execute("SELECT o.id, o.reg_index FROM orders o JOIN order_versions v ON v.order_id = o.id "
                         "JOIN audit a ON a.order_id = o.id AND a.action = 'register' "
                         "WHERE v.at > a.at AND o.source != 'import' GROUP BY o.id"):
        out.append(("помилка", f"Наказ № {r['reg_index']} змінювався після реєстрації"))
    from .cases import Cases
    cs = Cases(db)
    for (y,) in con.execute("SELECT DISTINCT year FROM orders WHERE year IS NOT NULL"):
        for t in cs.problems(y):
            out.append(("увага", f"Номенклатура {y}: {t}"))
    n_fts = con.execute("SELECT COUNT(*) FROM _fts_cache").fetchone()[0]
    n_ord = con.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    if n_fts != n_ord:
        out.append(("помилка", f"Пошуковий індекс неповний ({n_fts} з {n_ord})"))
    return out
