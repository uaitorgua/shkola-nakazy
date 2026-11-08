"""База наказів (SQLite): реєстр, нумерація за видами в межах календарного року.

Норми: Інструкція з діловодства у ЗЗСО (наказ МОН № 676), р. III п. 1; р. IV пп. 6-7; дод. 4.
"""
from __future__ import annotations

import datetime as dt
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass

SCHEMA_VERSION = 3


@dataclass(frozen=True)
class Kind:
    code: str       # внутрішній код
    suffix: str     # літерна відмітка через дефіс (р. III п. 1)
    title: str      # назва виду
    journal: str    # група реєстрації (р. IV п. 7)


KINDS: list[Kind] = [
    Kind("osn", "", "З основної діяльності", "Накази з основної діяльності"),
    Kind("u", "у", "З руху учнів", "Накази з руху учнів"),
    Kind("k", "к", "З кадрових питань", "Накази з кадрових питань (тривалого зберігання)"),
    Kind("v", "в", "Про відпустки", "Накази з кадрових питань (тимчасового зберігання)"),
    Kind("g", "г", "Адміністративно-господарські", "Накази з адміністративно-господарських питань"),
]
KIND_BY_CODE = {k.code: k for k in KINDS}

STATUS_TITLES = {"draft": "Чернетка", "registered": "Зареєстровано", "cancelled": "Скасовано"}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS counters (
    kind TEXT NOT NULL, year INTEGER NOT NULL, last_number INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (kind, year));
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    number INTEGER,
    reg_index TEXT,
    date TEXT,
    year INTEGER,
    title TEXT NOT NULL DEFAULT '',
    type_name TEXT NOT NULL DEFAULT '',
    template_id TEXT NOT NULL DEFAULT '',
    body_html TEXT NOT NULL DEFAULT '',
    basis TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft',
    signer TEXT NOT NULL DEFAULT '',
    signer_acting INTEGER NOT NULL DEFAULT 0,
    controller TEXT NOT NULL DEFAULT '',
    responsible TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    amends_order_id INTEGER REFERENCES orders(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (kind, year, number));
CREATE INDEX IF NOT EXISTS orders_kind_year ON orders(kind, year);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY, order_id INTEGER, at TEXT, action TEXT, details TEXT);
CREATE VIRTUAL TABLE IF NOT EXISTS orders_fts USING fts5(
    reg_index, title, body, content='', tokenize='unicode61 remove_diacritics 0');
CREATE TABLE IF NOT EXISTS _fts_cache (id INTEGER PRIMARY KEY, reg_index, title, body);
CREATE TABLE IF NOT EXISTS people (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,                 -- 'pupil' | 'staff'
    last TEXT NOT NULL, first TEXT NOT NULL DEFAULT '', middle TEXT NOT NULL DEFAULT '',
    birth TEXT, sex TEXT NOT NULL DEFAULT '',
    forms_json TEXT NOT NULL DEFAULT '{}',   -- відмінки, виправлені вручну
    status TEXT NOT NULL DEFAULT 'active',   -- active | left
    cls TEXT NOT NULL DEFAULT '', case_no TEXT NOT NULL DEFAULT '', enrolled TEXT,
    position TEXT NOT NULL DEFAULT '', rate TEXT NOT NULL DEFAULT '', subjects TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '', employment TEXT NOT NULL DEFAULT '',
    ext_id TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS people_name ON people(kind, last, first);
CREATE TABLE IF NOT EXISTS classes (
    school_year TEXT NOT NULL, name TEXT NOT NULL, teacher_id INTEGER REFERENCES people(id),
    PRIMARY KEY (school_year, name));
CREATE TABLE IF NOT EXISTS order_persons (
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    person_id INTEGER NOT NULL REFERENCES people(id), role TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (order_id, person_id, role));
CREATE TABLE IF NOT EXISTS order_versions (
    id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL, at TEXT NOT NULL, snapshot_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS attachments (
    id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    n INTEGER NOT NULL, title TEXT NOT NULL DEFAULT '', mode TEXT NOT NULL,  -- 'text' | 'file'
    body_html TEXT NOT NULL DEFAULT '', filename TEXT, data BLOB, approved INTEGER NOT NULL DEFAULT 0,
    UNIQUE (order_id, n));
CREATE TABLE IF NOT EXISTS blanks (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, mode TEXT NOT NULL,  -- 'text' | 'image' | 'docx'
    data BLOB, fields_json TEXT NOT NULL DEFAULT '{}', is_default INTEGER NOT NULL DEFAULT 0);
"""


class OrderLocked(Exception):
    """Зареєстрований наказ не змінюється: зміни лише новим наказом (р. III п. 1)."""


class RegistrationError(Exception):
    pass


def default_db_path() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    folder = os.path.join(base, "nakazy-shkola")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "nakazy.db")


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def format_date(iso: str | None) -> str:
    if not iso:
        return ""
    d = dt.date.fromisoformat(iso)
    return d.strftime("%d.%m.%Y")


def make_index(kind: str, number: int) -> str:
    suffix = KIND_BY_CODE[kind].suffix
    return f"{number}-{suffix}" if suffix else str(number)


def _plain(html: str) -> str:
    import re
    import html as h
    return h.unescape(re.sub(r"<[^>]+>", " ", html or ""))


class Database:
    def __init__(self, path: str | None = None):
        self.path = path or default_db_path()
        self._backup_before_migration()
        self.con = sqlite3.connect(self.path, isolation_level=None)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys = ON")
        self.con.execute("PRAGMA journal_mode = WAL")
        self.con.executescript(_SCHEMA)
        self._migrate()

    def _migrate(self):
        cols = {r[1] for r in self.con.execute("PRAGMA table_info(orders)")}
        for col in ("type_name", "template_id"):  # v1 -> v2
            if col not in cols:
                self.con.execute(f"ALTER TABLE orders ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")
        self.con.execute("INSERT OR REPLACE INTO meta VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))

    def _backup_before_migration(self):
        """Оновлення програми не руйнує базу: перед зміною схеми робиться копія."""
        if not os.path.exists(self.path):
            return
        con = sqlite3.connect(self.path)
        try:
            r = con.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
        except sqlite3.Error:
            r = None
        finally:
            con.close()
        from .backup import make_backup
        if r is None or int(r[0]) != SCHEMA_VERSION:
            make_backup(self.path, f"before-migration-v{r[0] if r else 0}", keep=10**6)
        else:
            make_backup(self.path, "start")

    # історія версій чернетки (повернення змін)
    def versions(self, order_id: int) -> list[sqlite3.Row]:
        return self.con.execute("SELECT * FROM order_versions WHERE order_id = ? ORDER BY id DESC",
                                (order_id,)).fetchall()

    def revert_to_version(self, version_id: int):
        import json
        v = self.con.execute("SELECT * FROM order_versions WHERE id = ?", (version_id,)).fetchone()
        snap = json.loads(v["snapshot_json"])
        self.update_draft(v["order_id"], **{k: snap[k] for k in (_EDITABLE | {"kind"}) if k in snap})

    @contextmanager
    def tx(self):
        """Атомарна зміна: або все (наказ, індекс пошуку, журнал дій), або нічого."""
        if self.con.in_transaction:
            yield; return
        self.con.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.con.execute("ROLLBACK"); raise
        self.con.execute("COMMIT")

    def close(self):
        self.con.close()

    # налаштування закладу
    def get_setting(self, key: str, default: str = "") -> str:
        r = self.con.execute("SELECT value FROM meta WHERE key = ?", (f"s.{key}",)).fetchone()
        return r["value"] if r else default

    def set_setting(self, key: str, value: str):
        self.con.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (f"s.{key}", value))

    # додатки (р. VI п. 4: групуються разом із наказом)
    def add_attachment(self, order_id: int, title: str, mode: str = "text", body_html: str = "",
                       filename: str | None = None, data: bytes | None = None, approved: bool = False) -> int:
        if self._require(order_id)["status"] != "draft":
            raise OrderLocked("До зареєстрованого наказу додатки не додаються.")
        n = self.con.execute("SELECT COALESCE(MAX(n), 0) + 1 FROM attachments WHERE order_id = ?",
                             (order_id,)).fetchone()[0]
        cur = self.con.execute(
            "INSERT INTO attachments (order_id, n, title, mode, body_html, filename, data, approved) "
            "VALUES (?,?,?,?,?,?,?,?)", (order_id, n, title, mode, body_html, filename, data, int(approved)))
        return cur.lastrowid

    def attachments(self, order_id: int) -> list[sqlite3.Row]:
        return self.con.execute("SELECT * FROM attachments WHERE order_id = ? ORDER BY n", (order_id,)).fetchall()

    def remove_attachment(self, att_id: int):
        r = self.con.execute("SELECT order_id FROM attachments WHERE id = ?", (att_id,)).fetchone()
        if r and self._require(r[0])["status"] != "draft":
            raise OrderLocked("Додатки зареєстрованого наказу не змінюються.")
        self.con.execute("DELETE FROM attachments WHERE id = ?", (att_id,))

    # бланк закладу (лише перша сторінка наказу)
    def save_blank(self, name: str, mode: str, data: bytes | None, fields: dict, default: bool = True) -> int:
        import json
        if mode not in ("text", "image", "docx"):
            raise ValueError(mode)
        if default:
            self.con.execute("UPDATE blanks SET is_default = 0")
        cur = self.con.execute("INSERT INTO blanks (name, mode, data, fields_json, is_default) VALUES (?,?,?,?,?)",
                               (name, mode, data, json.dumps(fields, ensure_ascii=False), int(default)))
        return cur.lastrowid

    def default_blank(self) -> dict | None:
        import json
        r = self.con.execute("SELECT * FROM blanks WHERE is_default = 1").fetchone()
        if not r:
            return None
        return {"id": r["id"], "name": r["name"], "mode": r["mode"], "data": r["data"],
                "fields": json.loads(r["fields_json"])}

    # читання
    def get(self, order_id: int) -> sqlite3.Row | None:
        return self.con.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()

    def list_orders(self, kind: str | None = None, year: int | None = None,
                    status: str | None = None, query: str = "", type_name: str | None = None) -> list[sqlite3.Row]:
        sql, args = "SELECT * FROM orders WHERE 1=1", []
        if kind:
            sql += " AND kind = ?"; args.append(kind)
        if year:
            sql += " AND (year = ? OR (status = 'draft' AND year IS NULL))"; args.append(year)
        if status:
            sql += " AND status = ?"; args.append(status)
        if type_name is not None:
            sql += " AND type_name = ?"; args.append(type_name)
        if query.strip():
            sql += " AND id IN (SELECT rowid FROM orders_fts WHERE orders_fts MATCH ?)"
            args.append(_fts_query(query))
        sql += " ORDER BY status = 'draft' DESC, year DESC, kind, number DESC, id DESC"
        return self.con.execute(sql, args).fetchall()

    def counts(self, year: int) -> dict[str, int]:
        rows = self.con.execute(
            "SELECT kind, COUNT(*) c FROM orders WHERE year = ? AND status != 'draft' GROUP BY kind", (year,))
        return {r["kind"]: r["c"] for r in rows}

    def type_counts(self, year: int) -> dict[tuple[str, str], int]:
        rows = self.con.execute("SELECT kind, type_name, COUNT(*) c FROM orders WHERE year = ? "
                                "AND status != 'draft' GROUP BY kind, type_name", (year,))
        return {(r["kind"], r["type_name"]): r["c"] for r in rows}

    def years(self) -> list[int]:
        ys = {r[0] for r in self.con.execute("SELECT DISTINCT year FROM orders WHERE year IS NOT NULL")}
        ys.add(dt.date.today().year)
        return sorted(ys, reverse=True)

    def journal(self, kind: str, year: int) -> list[sqlite3.Row]:
        """Записи реєстраційного журналу (дод. 4) у порядку номерів, разом зі скасованими."""
        return self.con.execute(
            "SELECT * FROM orders WHERE kind = ? AND year = ? AND number IS NOT NULL ORDER BY number",
            (kind, year)).fetchall()

    # запис
    def create_draft(self, kind: str, **fields) -> int:
        if kind not in KIND_BY_CODE:
            raise ValueError(f"Невідомий вид наказу: {kind}")
        now = _now()
        fields = {k: v for k, v in fields.items() if k in _EDITABLE}
        cols = ["kind", "status", "created_at", "updated_at", *fields]
        vals = [kind, "draft", now, now, *fields.values()]
        with self.tx():
            cur = self.con.execute(
                f"INSERT INTO orders ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", vals)
            oid = cur.lastrowid
            self._reindex(oid)
            self._audit(oid, "create", "")
        return oid

    def update_draft(self, order_id: int, **fields):
        row = self._require(order_id)
        if row["status"] != "draft":
            raise OrderLocked("Наказ уже зареєстровано. Зміни вносяться лише новим наказом.")
        fields = {k: v for k, v in fields.items() if k in _EDITABLE or k == "kind"}
        if "kind" in fields and fields["kind"] not in KIND_BY_CODE:
            raise ValueError("Невідомий вид наказу")
        if not fields:
            return
        import json
        with self.tx():
            self._update_locked(order_id, row, fields, json)

    def _update_locked(self, order_id, row, fields, json):
        self.con.execute("INSERT INTO order_versions (order_id, at, snapshot_json) VALUES (?, ?, ?)",
                         (order_id, _now(), json.dumps(dict(row), ensure_ascii=False)))
        sets = ", ".join(f"{k} = ?" for k in fields)
        self.con.execute(f"UPDATE orders SET {sets}, updated_at = ? WHERE id = ?",
                         [*fields.values(), _now(), order_id])
        self._reindex(order_id)

    def delete_draft(self, order_id: int):
        row = self._require(order_id)
        if row["status"] != "draft":
            raise OrderLocked("Зареєстрований наказ не видаляється (номер не можна звільнити).")
        with self.tx():
            self._unindex(order_id)
            self.con.execute("DELETE FROM attachments WHERE order_id = ?", (order_id,))
            self.con.execute("DELETE FROM order_persons WHERE order_id = ?", (order_id,))
            self.con.execute("DELETE FROM order_versions WHERE order_id = ?", (order_id,))
            self.con.execute("DELETE FROM orders WHERE id = ?", (order_id,))

    def register(self, order_id: int, date: str | None = None) -> str:
        """Видає наступний номер у межах виду й календарного року (р. III п. 1)."""
        row = self._require(order_id)
        if row["status"] != "draft":
            raise RegistrationError("Наказ уже зареєстровано.")
        problems = check_structure(row)
        if any(p.startswith("!") for p in problems):
            raise RegistrationError("\n".join(p[1:] for p in problems if p.startswith("!")))
        date = date or row["date"] or dt.date.today().isoformat()
        d = dt.date.fromisoformat(date)
        kind, year = row["kind"], d.year
        self.con.execute("BEGIN IMMEDIATE")
        try:
            last = self.con.execute(
                "SELECT MAX(date) FROM orders WHERE kind = ? AND year = ? AND number IS NOT NULL",
                (kind, year)).fetchone()[0]
            if last and date < last:
                raise RegistrationError(
                    f"Дата {format_date(date)} раніша за дату останнього наказу цього виду "
                    f"({format_date(last)}). Накази нумеруються в порядку видання.")
            self.con.execute("INSERT OR IGNORE INTO counters VALUES (?, ?, 0)", (kind, year))
            self.con.execute("UPDATE counters SET last_number = last_number + 1 WHERE kind = ? AND year = ?",
                             (kind, year))
            number = self.con.execute("SELECT last_number FROM counters WHERE kind = ? AND year = ?",
                                      (kind, year)).fetchone()[0]
            idx = make_index(kind, number)
            self.con.execute(
                "UPDATE orders SET number = ?, reg_index = ?, date = ?, year = ?, status = 'registered', "
                "updated_at = ? WHERE id = ?", (number, idx, date, year, _now(), order_id))
            self._audit(order_id, "register", idx)
            self._reindex(order_id)
            self.con.execute("COMMIT")
        except BaseException:
            self.con.execute("ROLLBACK")
            raise
        return idx

    def cancel(self, order_id: int, reason: str):
        """Позначка «скасовано» (номер лишається в журналі, пропусків немає)."""
        row = self._require(order_id)
        if row["status"] != "registered":
            raise RegistrationError("Скасувати можна лише зареєстрований наказ.")
        note = (row["notes"] + "\n" if row["notes"] else "") + f"Скасовано: {reason}"
        with self.tx():
            self.con.execute("UPDATE orders SET status = 'cancelled', notes = ?, updated_at = ? WHERE id = ?",
                             (note, _now(), order_id))
            self._audit(order_id, "cancel", reason)

    def create_amendment(self, order_id: int) -> int:
        """Чернетка наказу «Про внесення змін…» до зареєстрованого наказу (р. III п. 1)."""
        row = self._require(order_id)
        if row["status"] == "draft":
            raise RegistrationError("Чернетку можна редагувати напряму.")
        ref = f"від {format_date(row['date'])} № {row['reg_index']}"
        title = f"Про внесення змін до наказу {ref}"
        old = row["title"]
        if old.startswith("Про "):
            title += f" «{old}»"
        body = (f"<p>Відповідно до …</p><p>НАКАЗУЮ:</p>"
                f"<p>1. Внести зміни до наказу {ref} «{old}», виклавши … в такій редакції: …</p>"
                f"<p>2. Контроль за виконанням наказу залишаю за собою.</p>")
        return self.create_draft(row["kind"], title=title, body_html=body, amends_order_id=order_id,
                                 signer=row["signer"], controller=row["controller"])

    # службове
    def _require(self, order_id: int) -> sqlite3.Row:
        row = self.get(order_id)
        if row is None:
            raise KeyError(order_id)
        return row

    def _audit(self, oid, action, details):
        self.con.execute("INSERT INTO audit (order_id, at, action, details) VALUES (?, ?, ?, ?)",
                         (oid, _now(), action, details))

    def _unindex(self, oid):
        old = self.con.execute("SELECT reg_index, title, body FROM _fts_cache WHERE id = ?", (oid,)).fetchone()
        if old:
            self.con.execute("INSERT INTO orders_fts (orders_fts, rowid, reg_index, title, body) "
                             "VALUES ('delete', ?, ?, ?, ?)", (oid, *old))
            self.con.execute("DELETE FROM _fts_cache WHERE id = ?", (oid,))

    def _reindex(self, oid):
        self._unindex(oid)
        r = self.get(oid)
        vals = (r["reg_index"] or "", r["title"], _plain(r["body_html"]) + " " + r["basis"])
        self.con.execute("INSERT INTO orders_fts (rowid, reg_index, title, body) VALUES (?, ?, ?, ?)", (oid, *vals))
        self.con.execute("INSERT INTO _fts_cache VALUES (?, ?, ?, ?)", (oid, *vals))


_EDITABLE = {"type_name", "template_id", "date", "title", "body_html", "basis", "signer", "signer_acting", "controller",
             "responsible", "notes", "amends_order_id"}


def _fts_query(q: str) -> str:
    import re
    q = re.sub(r"[^\w\s]", " ", q)  # лише літери й цифри: спецсимволи FTS5 не ламають пошук
    words = [w for w in q.split() if w]
    return " ".join(f'"{w}"*' for w in words) or '""'


def check_structure(row) -> list[str]:
    """Перевірка структури (р. III п. 1). Рядки з «!» блокують реєстрацію."""
    out = []
    title = (row["title"] or "").strip()
    if not title:
        out.append("!Немає заголовка наказу.")
    elif not title.startswith("Про "):
        out.append("Заголовок має починатися з «Про».")
    text = _plain(row["body_html"])
    if "НАКАЗУЮ:" not in text:
        out.append("Розпорядча частина має починатися словом «НАКАЗУЮ:» з нового рядка.")
    if not (row["signer"] or "").strip():
        out.append("!Не вказано, хто підписує наказ.")
    return out
