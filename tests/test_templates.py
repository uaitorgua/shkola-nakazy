import os
import re
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nakazy.db import KIND_BY_CODE, Database, check_structure  # noqa: E402
from nakazy.templates import TEMPLATES, render  # noqa: E402


class TemplatesTest(unittest.TestCase):
    def test_all_render_valid(self):
        ids = set()
        for t in TEMPLATES:
            self.assertNotIn(t.id, ids); ids.add(t.id)
            self.assertIn(t.kind, KIND_BY_CODE)
            vals = {k: f"<{k}>" for k, _ in t.fields}
            title, body = render(t, vals)
            self.assertTrue(title.startswith("Про "), t.id)
            self.assertNotIn("{", title + body, t.id)
            self.assertIn("НАКАЗУЮ:", body)
            row = {"title": title, "body_html": body, "signer": "x"}
            self.assertEqual([p for p in check_structure(row) if p.startswith("!")], [])
            for k, _ in t.fields:
                self.assertTrue(re.search(r"\{" + k + r"(\.\w+)?\}", t.title + t.preamble + "".join(t.items)), f"{t.id}: {k}")

    def test_search(self):
        from nakazy.templates import search
        self.assertEqual([t.id for t in search("*харч*")], ["o_food"])
        self.assertIn("v_annual", [t.id for t in search("ВІДПУСТК щоріч")])
        self.assertIn("u_enroll", [t.id for t in search("зарахув")])
        self.assertEqual(search("ксилофон"), [])
        self.assertEqual(len(search("")), len(TEMPLATES))

    def test_migration_v1(self):
        d = tempfile.mkdtemp(); path = os.path.join(d, "old.db")
        con = sqlite3.connect(path)
        con.executescript("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);"
                          "INSERT INTO meta VALUES ('schema_version','1');"
                          "CREATE TABLE orders (id INTEGER PRIMARY KEY, kind TEXT NOT NULL, number INTEGER, "
                          "reg_index TEXT, date TEXT, year INTEGER, title TEXT NOT NULL DEFAULT '', "
                          "body_html TEXT NOT NULL DEFAULT '', basis TEXT NOT NULL DEFAULT '', "
                          "status TEXT NOT NULL DEFAULT 'draft', signer TEXT NOT NULL DEFAULT '', "
                          "signer_acting INTEGER NOT NULL DEFAULT 0, controller TEXT NOT NULL DEFAULT '', "
                          "responsible TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '', "
                          "amends_order_id INTEGER, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
                          "UNIQUE (kind, year, number));"
                          "INSERT INTO orders (kind, title, created_at, updated_at) VALUES ('osn','Про старе','x','x');")
        con.commit(); con.close()
        db = Database(path)
        self.assertEqual(db.get(1)["type_name"], "")
        backups = os.listdir(os.path.join(d, "backups"))
        self.assertTrue(any("before-migration-v1" in f for f in backups))
        db.close()


if __name__ == "__main__":
    unittest.main()
