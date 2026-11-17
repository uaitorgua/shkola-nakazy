import os
import re
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nakazy.db import KIND_BY_CODE, Database, check_structure  # noqa: E402
from nakazy.templates import TEMPLATES, render  # noqa: E402
from nakazy.templates import search as search_ids  # noqa: E402


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

    def test_hr_templates_hrmis(self):
        """Кадрові шаблони за переліком HRMIS (17.11.2026): є, у правильному виді, з підставою."""
        from nakazy.templates import TEMPLATE_BY_ID
        expect = {"k": ["k_duties_stop", "k_reinstate", "k_weekend", "k_childcare_return", "k_reward", "k_bonus",
                        "k_aid", "k_seniority", "k_substitution_pay", "k_training", "k_military",
                        "k_military_return", "k_rename"],
                  "v": ["v_schedule", "v_transfer", "v_compensation", "v_dayoff", "v_donor", "v_trip",
                        "v_trip_change", "v_reprimand", "v_reprimand_remove"]}
        for kind, ids in expect.items():
            for tid in ids:
                t = TEMPLATE_BY_ID[tid]
                self.assertEqual(t.kind, kind, tid)
                self.assertTrue(t.basis, tid)
        t = TEMPLATE_BY_ID["v_reprimand"]
        title, body = render(t, {"employee": "Петренко О. І.", "employee.dat": "Петренко Олені Іванівні",
                                 "position": "вчителю", "violation": "запізнення 03.11.2026",
                                 "explanation_date": "04.11.2026"})
        self.assertEqual(title, "Про оголошення догани Петренко Олені Іванівні")
        self.assertIn("статей 147, 148, 149", body)
        self.assertIn("v_schedule", [x.id for x in search_ids("графік відпусток")])

    def test_search(self):
        from nakazy.templates import search
        self.assertEqual([t.id for t in search("*харч*")], ["o_food", "o_food_free"])
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
        self.assertEqual(db.links_from(1), [])  # v5: таблиця зв'язку наказів створюється
        backups = os.listdir(os.path.join(d, "backups"))
        self.assertTrue(any("before-migration-v1" in f for f in backups))
        db.close()


if __name__ == "__main__":
    unittest.main()
