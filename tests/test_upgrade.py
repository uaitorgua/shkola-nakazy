"""Оновлення програми не губить дані: база кожної попередньої опублікованої версії відкривається новою версією,
усі рядки на місці, перед зміною будови є резервна копія, нові функції працюють на старій базі.
Зразки в tests/fixtures створено кодом відповідних версій: 0.1.3 (схема v4, коміт 877dc44) і 0.1.5 (схема v8,
коміт 0ad295f; з номенклатурою справ, графіком відпусток, зв'язками й груповим наказом).
Для кожної нової опублікованої версії сюди додається її зразок."""
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

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
FIXTURES = [("nakazy_v4_0.1.3.db", "4"), ("nakazy_v8_0.1.5.db", "8")]


def tables(con):
    return [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE "
                                      "'orders_fts%' AND name NOT LIKE 'sqlite_%' AND name NOT IN ('_fts_cache', 'meta')")]


def rows(path, cols_of=None):
    con = sqlite3.connect(path); out = {}
    names = list(cols_of) if cols_of else tables(con)
    for t in names:
        cols = cols_of[t] if cols_of else [r[1] for r in con.execute(f"PRAGMA table_info({t})")]
        out[t] = sorted(map(repr, con.execute(f"SELECT {', '.join(cols)} FROM {t}").fetchall()))
    cols = {t: [r[1] for r in con.execute(f"PRAGMA table_info({t})")] for t in names}
    settings = dict(con.execute("SELECT key, value FROM meta WHERE key != 'schema_version'").fetchall())
    con.close()
    return out, cols, settings


class UpgradeTest(unittest.TestCase):
    def open_old(self, name):
        d = tempfile.mkdtemp(); path = os.path.join(d, "nakazy.db")
        shutil.copy(os.path.join(FIX, name), path)
        return d, path

    def test_old_db_kept(self):
        for name, old_ver in FIXTURES:
            with self.subTest(name):
                d, path = self.open_old(name)
                before, cols, settings = rows(path)
                self.assertGreater(len(before["orders"]), 0)
                db = Database(path)
                self.assertEqual(db.con.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0],
                                 str(SCHEMA_VERSION))
                after, _c, settings2 = rows(path, cols)
                for t in before:
                    self.assertEqual(before[t], after[t], f"{name}: змінено/втрачено рядки в таблиці {t}")
                self.assertEqual(settings, settings2)
                backups = os.listdir(os.path.join(d, "backups"))
                bk = [b for b in backups if f"before-migration-v{old_ver}" in b]
                self.assertEqual(len(bk), 1, backups)
                con = sqlite3.connect(os.path.join(d, "backups", bk[0]))
                self.assertEqual(con.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0], old_ver)
                self.assertEqual(con.execute("SELECT COUNT(*) FROM orders").fetchone()[0], len(before["orders"]))
                con.close()
                db.close()
                Database(path).close()  # повторний запуск: будова та сама – нової копії «перед оновленням» немає
                self.assertEqual(len([b for b in os.listdir(os.path.join(d, "backups")) if "before-migration" in b]), 1)

    def test_new_features_on_old_db(self):
        """Стара база 0.1.3: зв'язок наказів, графік, редагування чернетки в іншій програмі."""
        import docx

        from nakazy import external_edit as ee
        from nakazy.leave_plan import LeavePlan
        from nakazy.ui.order_editor import create_from_template
        d, path = self.open_old("nakazy_v4_0.1.3.db")
        db = Database(path)
        leave = db.con.execute("SELECT id FROM orders WHERE template_id='v_annual'").fetchone()[0]
        pid = db.con.execute("SELECT id FROM people WHERE kind='staff'").fetchone()[0]
        oid = create_from_template(db, "v_transfer", {}, persons={"employee": pid}, refs={"leave_order": leave})
        self.assertEqual([r["id"] for r in db.links_from(oid)], [leave])
        LeavePlan(db).add(2027, pid, days=28)
        draft = db.con.execute("SELECT id FROM orders WHERE status='draft' AND template_id='o_attest'").fetchone()[0]
        dpath = ee.write_docx(db, draft)
        doc = docx.Document(dpath); doc.add_paragraph("Додано після оновлення."); doc.save(dpath)
        self.assertTrue(ee.sync(db, draft, dpath))
        self.assertIn("Додано після оновлення.", db.get(draft)["body_html"])
        self.assertEqual(len(db.attachments(draft)), 3)
        db.close()

    def test_v016_on_015_db(self):
        """База 0.1.5: нові поля мають типові значення, старі накази не змінюють довідник заднім числом,
        нові дії, нагадування й JSON з номенклатурою працюють."""
        from nakazy.effects import apply
        from nakazy.portable import export_json, import_json
        from nakazy.reminders import reminders
        from nakazy.ui.order_editor import create_from_template
        d, path = self.open_old("nakazy_v8_0.1.5.db")
        db = Database(path)
        o = db.con.execute("SELECT due_date, done, visas FROM orders LIMIT 1").fetchone()
        self.assertEqual(tuple(o), ("", 0, ""))
        self.assertEqual(db.con.execute("SELECT COUNT(*) FROM order_effects").fetchone()[0], 0)
        old_enroll = db.con.execute("SELECT id FROM orders WHERE template_id='u_enroll'").fetchone()[0]
        self.assertEqual(db.order_values(old_enroll), ({}, []))  # у старих наказів значень шаблону немає
        pid = db.con.execute("SELECT id FROM people WHERE kind='pupil'").fetchone()[0]
        new = create_from_template(db, "u_transfer_class", {"cls": "5-А", "cls_new": "5-Б"}, persons={"pupil": pid})
        db.register(new, "2026-11-20")
        self.assertTrue(apply(db, new))
        self.assertEqual(db.con.execute("SELECT cls, case_no FROM people WHERE id = ?", (pid,)).fetchone()[:],
                         ("5-Б", "І-3"))
        self.assertIsInstance(reminders(db), list)
        js = os.path.join(d, "e.json"); export_json(db, js)
        rep = import_json(js, os.path.join(d, "n.db"))
        self.assertEqual(rep["skipped"], {})
        n = Database(os.path.join(d, "n.db"))
        self.assertEqual(n.con.execute("SELECT case_index, article FROM nomenclature WHERE year = 2026 AND kind = 'k' "
                                       "AND part = 'orders'").fetchone()[:], ("01-05", "16-б"))
        n.close(); db.close()


if __name__ == "__main__":
    unittest.main()
