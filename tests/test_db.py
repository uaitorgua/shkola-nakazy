import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nakazy.db import Database, OrderLocked, RegistrationError  # noqa: E402

BODY = "<p>Відповідно до …</p><p>НАКАЗУЮ:</p><p>1. …</p>"


class DbTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(os.path.join(self.tmp.name, "t.db"))

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def draft(self, kind="osn", title="Про затвердження плану", **kw):
        return self.db.create_draft(kind, title=title, body_html=BODY, signer="О. Петренко", **kw)

    def test_separate_numbering_and_suffix(self):
        self.assertEqual(self.db.register(self.draft(), "2026-01-10"), "1")
        self.assertEqual(self.db.register(self.draft(), "2026-01-11"), "2")
        self.assertEqual(self.db.register(self.draft("u", "Про зарахування"), "2026-01-11"), "1-у")
        self.assertEqual(self.db.register(self.draft("k", "Про прийняття"), "2026-01-12"), "1-к")
        self.assertEqual(self.db.register(self.draft("v", "Про відпустку"), "2026-01-12"), "1-в")
        self.assertEqual(self.db.register(self.draft("g", "Про інвентаризацію"), "2026-01-12"), "1-г")

    def test_calendar_year_reset(self):
        self.db.register(self.draft(), "2025-12-30")
        self.assertEqual(self.db.register(self.draft(), "2026-01-02"), "1")

    def test_order_of_dates(self):
        self.db.register(self.draft(), "2026-03-10")
        with self.assertRaises(RegistrationError):
            self.db.register(self.draft(), "2026-03-01")

    def test_locked_after_registration(self):
        oid = self.draft()
        self.db.register(oid, "2026-02-01")
        with self.assertRaises(OrderLocked):
            self.db.update_draft(oid, title="Про інше")
        with self.assertRaises(OrderLocked):
            self.db.delete_draft(oid)

    def test_amendment(self):
        oid = self.draft()
        self.db.register(oid, "2026-02-01")
        aid = self.db.create_amendment(oid)
        row = self.db.get(aid)
        self.assertEqual(row["amends_order_id"], oid)
        self.assertIn("від 01.02.2026 № 1", row["title"])

    def test_cancel_keeps_number(self):
        oid = self.draft()
        self.db.register(oid, "2026-02-01")
        self.db.cancel(oid, "помилка")
        self.assertEqual(self.db.register(self.draft(), "2026-02-02"), "2")
        self.assertEqual([r["number"] for r in self.db.journal("osn", 2026)], [1, 2])

    def test_requires_signer(self):
        oid = self.db.create_draft("osn", title="Про щось", body_html=BODY)
        with self.assertRaises(RegistrationError):
            self.db.register(oid)

    def test_search(self):
        self.draft(title="Про організацію харчування")
        oid = self.draft(title="Про екскурсію до Львова")
        self.db.update_draft(oid, basis="лист управління освіти")
        self.assertEqual(len(self.db.list_orders(query="харчув")), 1)
        self.assertEqual(self.db.list_orders(query="управління")[0]["id"], oid)
        self.db.delete_draft(oid)
        self.assertEqual(self.db.list_orders(query="Львова"), [])

    def test_attachments(self):
        oid = self.draft()
        self.db.add_attachment(oid, "Склад комісії")
        self.db.add_attachment(oid, "Графік", mode="file", filename="g.pdf", data=b"%PDF")
        self.assertEqual([a["n"] for a in self.db.attachments(oid)], [1, 2])
        self.db.register(oid, "2026-02-01")
        with self.assertRaises(OrderLocked):
            self.db.add_attachment(oid, "Ще")

    def test_versions_and_backup(self):
        from nakazy.backup import list_backups, make_backup, restore_backup
        oid = self.draft(title="Про перше")
        self.db.update_draft(oid, title="Про друге")
        self.db.revert_to_version(self.db.versions(oid)[0]["id"])
        self.assertEqual(self.db.get(oid)["title"], "Про перше")
        b = make_backup(self.db.path, "test")
        self.db.delete_draft(oid)
        self.db.close()
        restore_backup(self.db.path, b)
        self.db = Database(self.db.path)
        self.assertEqual(self.db.get(oid)["title"], "Про перше")
        self.assertTrue(any("before-restore" in f for f in list_backups(self.db.path)))

    def test_blank(self):
        self.db.save_blank("Основний", "image", b"PNG", {"height_mm": 60})
        b = self.db.default_blank()
        self.assertEqual((b["mode"], b["data"], b["fields"]["height_mm"]), ("image", b"PNG", 60))


if __name__ == "__main__":
    unittest.main()
