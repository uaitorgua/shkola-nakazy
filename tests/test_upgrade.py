"""Оновлення програми не губить дані: база попередньої версії (0.1.3, схема v4) відкривається новою версією,
усі рядки на місці, перед зміною схеми є резервна копія, нові функції працюють на старій базі.
Зразок tests/fixtures/nakazy_v4_0.1.3.db створено кодом 0.1.3 (коміт 877dc44) 17.11.2026."""
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["NAKAZY_OFFLINE"] = "1"

from nakazy.db import SCHEMA_VERSION, Database  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "nakazy_v4_0.1.3.db")
TABLES = ["counters", "orders", "audit", "people", "classes", "order_persons", "originals", "order_versions",
          "attachments", "blanks"]


def rows(path, cols_of=None):
    con = sqlite3.connect(path); out = {}
    for t in TABLES:
        cols = cols_of[t] if cols_of else [r[1] for r in con.execute(f"PRAGMA table_info({t})")]
        out[t] = sorted(map(repr, con.execute(f"SELECT {', '.join(cols)} FROM {t}").fetchall()))
    cols = {t: [r[1] for r in con.execute(f"PRAGMA table_info({t})")] for t in TABLES}
    settings = dict(con.execute("SELECT key, value FROM meta WHERE key != 'schema_version'").fetchall())
    con.close()
    return out, cols, settings


class UpgradeTest(unittest.TestCase):
    def test_old_db_kept(self):
        d = tempfile.mkdtemp(); path = os.path.join(d, "nakazy.db")
        shutil.copy(FIXTURE, path)
        before, cols, settings = rows(path)
        db = Database(path)
        self.assertEqual(db.con.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0],
                         str(SCHEMA_VERSION))
        after, _c, settings2 = rows(path, cols)
        for t in TABLES:
            self.assertEqual(before[t], after[t], f"змінено/втрачено рядки в таблиці {t}")
        self.assertEqual(settings, settings2)
        backups = os.listdir(os.path.join(d, "backups"))
        bk = [b for b in backups if "before-migration-v4" in b]
        self.assertEqual(len(bk), 1, backups)
        con = sqlite3.connect(os.path.join(d, "backups", bk[0]))
        self.assertEqual(con.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0], "4")
        self.assertEqual(con.execute("SELECT COUNT(*) FROM orders").fetchone()[0], len(before["orders"]))
        con.close()
        # нові можливості на старій базі: зв'язок наказів, залишок відпустки, графік
        from nakazy.leave_plan import LeavePlan
        from nakazy.ui.order_editor import create_from_template
        leave = db.con.execute("SELECT id FROM orders WHERE template_id='v_annual'").fetchone()[0]
        pid = db.con.execute("SELECT id FROM people WHERE kind='staff'").fetchone()[0]
        oid = create_from_template(db, "v_transfer", {}, persons={"employee": pid}, refs={"leave_order": leave})
        self.assertEqual([r["id"] for r in db.links_from(oid)], [leave])
        LeavePlan(db).add(2027, pid, days=28)
        # чернетка, створена у старій версії, редагується в окремій програмі (з 0.1.5) без втрат
        import docx

        from nakazy import external_edit as ee
        draft = db.con.execute("SELECT id FROM orders WHERE status='draft' AND template_id='o_attest'").fetchone()[0]
        dpath = ee.write_docx(db, draft)
        doc = docx.Document(dpath); doc.add_paragraph("Додано після оновлення."); doc.save(dpath)
        self.assertTrue(ee.sync(db, draft, dpath))
        self.assertIn("Додано після оновлення.", db.get(draft)["body_html"])
        self.assertEqual(len(db.attachments(draft)), 3)  # додатки старої чернетки (2 шаблонні + файл) на місці
        db.close()
        # повторний запуск: схема та сама – копія «start», не нова міграція
        Database(path).close()
        self.assertEqual(len([b for b in os.listdir(os.path.join(d, "backups")) if "before-migration" in b]), 1)


if __name__ == "__main__":
    unittest.main()
