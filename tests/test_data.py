"""«Дані й копії»: копія зараз, збереження бази у файл, відновлення з копії й з файла (і з бази 0.1.3),
відмова для чужого файла чи файла новішої версії; перед відновленням поточна база зберігається."""
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["NAKAZY_OFFLINE"] = "1"

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox  # noqa: E402

app = QApplication.instance() or QApplication([])

from nakazy import backup  # noqa: E402
from nakazy.db import SCHEMA_VERSION, Database  # noqa: E402
from nakazy.ui.main_window import MainWindow  # noqa: E402
from nakazy.ui.order_editor import create_from_template  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "nakazy_v4_0.1.3.db")


class DataTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.db = Database(os.path.join(self.d, "nakazy.db")); self.db.set_setting("head", "Олена ПЕТРЕНКО")
        for _ in range(3):
            self.db.register(create_from_template(self.db, "o_free", {"subject": "чергування"}), "2026-11-10")
        self.w = MainWindow(self.db)
        from nakazy.ui.data_dialog import DataDialog
        self.dlg = DataDialog(None, self.w)

    def tearDown(self):
        self.dlg.close(); self.w.close(); self.w.db.close()

    def count(self):
        return len(self.w.db.list_orders())

    def test_backup_export_restore(self):
        with mock.patch.object(QMessageBox, "information"):
            self.dlg.make_now()
        self.assertTrue(any(backup.describe(p)[1] == "вручну" for p in backup.list_backups(self.w.db.path)))
        out = os.path.join(self.d, "out", "Накази.db"); os.makedirs(os.path.dirname(out))
        with mock.patch.object(QFileDialog, "getSaveFileName", return_value=(out, "")), \
                mock.patch.object(QMessageBox, "information"):
            self.dlg.export_file()
        self.assertEqual(backup.check_file(out, SCHEMA_VERSION)[2], 3)
        create_from_template(self.w.db, "o_free", {"subject": "нове"})  # змінюємо поточну базу
        self.assertEqual(self.count(), 4)
        with mock.patch.object(QFileDialog, "getOpenFileName", return_value=(out, "")), \
                mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes), \
                mock.patch.object(QMessageBox, "information"):
            self.dlg.import_file()
        self.assertEqual(self.count(), 3)  # базу замінено файлом
        before = [p for p in backup.list_backups(self.w.db.path) if backup.describe(p)[1] == "перед відновленням"]
        self.assertEqual(len(before), 1)  # поточну базу збережено перед відновленням – її можна повернути
        self.assertEqual(backup.check_file(before[0], SCHEMA_VERSION)[2], 4)
        # відновлення з вибраної копії в списку (повертаємо 4 накази)
        self.dlg.load()
        for i in range(self.dlg.list.topLevelItemCount()):
            if self.dlg.list.topLevelItem(i).data(0, 256) == before[0]:
                self.dlg.list.setCurrentItem(self.dlg.list.topLevelItem(i))
        with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes), \
                mock.patch.object(QMessageBox, "information"):
            self.dlg.restore_selected()
        self.assertEqual(self.count(), 4)

    def test_refuse_bad_files(self):
        bad = os.path.join(self.d, "bad.db"); open(bad, "wb").write(b"not a database")
        newer = backup.export_to(self.w.db.con, os.path.join(self.d, "newer.db"))
        con = sqlite3.connect(newer); con.execute("UPDATE meta SET value = ? WHERE key = 'schema_version'",
                                                  (str(SCHEMA_VERSION + 1),)); con.commit(); con.close()
        for path in (bad, newer):
            with mock.patch.object(QFileDialog, "getOpenFileName", return_value=(path, "")), \
                    mock.patch.object(QMessageBox, "warning") as w, mock.patch.object(QMessageBox, "question") as q:
                self.dlg.import_file()
            w.assert_called_once(); q.assert_not_called()
        self.assertEqual(self.count(), 3)  # поточна база не змінилась

    def test_restore_old_version_file(self):
        """База з версії 0.1.3 відновлюється й оновлюється з копією перед оновленням."""
        with mock.patch.object(QFileDialog, "getOpenFileName", return_value=(FIXTURE, "")), \
                mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes), \
                mock.patch.object(QMessageBox, "information"):
            self.dlg.import_file()
        self.assertEqual(self.count(), 5)
        self.assertEqual(self.w.db.con.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0],
                         str(SCHEMA_VERSION))
        why = [backup.describe(p)[1] for p in backup.list_backups(self.w.db.path)]
        self.assertIn("перед оновленням програми (будова бази)", why)
        self.assertIn("перед відновленням", why)


class PortableTest(unittest.TestCase):
    """JSON – незалежний від будови бази формат: експорт → імпорт без втрат, старіші й новіші поля."""

    def setUp(self):
        from nakazy.people import People
        self.d = tempfile.mkdtemp()
        self.db = Database(os.path.join(self.d, "src.db")); self.db.set_setting("head", "Олена ПЕТРЕНКО")
        pid = People(self.db).add(kind="staff", last="Коваль", first="Марія", middle="Іванівна", leave_right=56)
        self.o1 = create_from_template(self.db, "v_annual", {"employee": "Коваль М. І.", "days": "28",
                                                             "period": "з 01.09.2025 по 31.08.2026"},
                                       persons={"employee": pid})
        self.db.add_attachment(self.o1, "Файл", "file", filename="a.pdf", data=b"%PDF-1.4 \x00\xff bytes")
        self.db.register(self.o1, "2026-07-01")
        from nakazy.leave_plan import LeavePlan
        LeavePlan(self.db).add(2026, pid, days=28)

    def tearDown(self):
        self.db.close()

    def dump(self, db):
        from nakazy.portable import _tables
        return {t: sorted(repr(tuple(r)) for r in db.con.execute(f"SELECT * FROM {t}").fetchall()) for t in _tables(db.con)
                if t != "meta"}

    def test_round_trip(self):
        from nakazy.portable import export_json, import_json
        js = os.path.join(self.d, "e.json"); counts = export_json(self.db, js)
        self.assertEqual(counts["orders"], 1)
        rep = import_json(js, os.path.join(self.d, "new.db"))
        self.assertEqual(rep["skipped"], {})
        new = Database(os.path.join(self.d, "new.db"))
        self.assertEqual(self.dump(new), self.dump(self.db))  # усі таблиці, зокрема двійкові файли, без змін
        self.assertEqual(new.get_setting("head"), "Олена ПЕТРЕНКО")
        self.assertEqual(len(new.list_orders(query="відпустки")), 1)  # пошуковий індекс збудовано
        new.close()

    def test_other_structures(self):
        """JSON зі старішої будови (без нових полів і таблиць) і з новішої (невідомі поля) – імпортується."""
        import json

        from nakazy.portable import ImportError_, export_json, import_json
        js = os.path.join(self.d, "e.json"); export_json(self.db, js)
        data = json.load(open(js, encoding="utf-8"))
        for r in data["tables"]["people"]:
            r.pop("leave_right")                      # як у старій версії
        data["tables"].pop("leave_plan")
        data["tables"]["orders"][0]["future_field"] = "x"   # як у майбутній версії
        data["tables"]["future_table"] = [{"a": 1}]
        data["app_version"] = "9.9.9"
        old = os.path.join(self.d, "mixed.json"); json.dump(data, open(old, "w", encoding="utf-8"), ensure_ascii=False)
        rep = import_json(old, os.path.join(self.d, "m.db"))
        self.assertEqual(rep["skipped"], {"orders": ["future_field"], "future_table": ["вся таблиця"]})
        m = Database(os.path.join(self.d, "m.db"))
        self.assertEqual(len(m.list_orders()), 1)
        self.assertIsNone(m.con.execute("SELECT leave_right FROM people").fetchone()[0])  # нове поле – типове
        m.close()
        bad = os.path.join(self.d, "bad.json"); open(bad, "w").write('{"a": 1}')
        with self.assertRaises(ImportError_):
            import_json(bad, os.path.join(self.d, "b.db"))
        data["format_version"] = 99; json.dump(data, open(bad, "w", encoding="utf-8"))
        with self.assertRaises(ImportError_):
            import_json(bad, os.path.join(self.d, "c.db"))
        self.assertFalse(os.path.exists(os.path.join(self.d, "c.db")))

    def test_dialog_json_and_xlsx(self):
        from openpyxl import load_workbook

        from nakazy.ui.data_dialog import DataDialog
        w = MainWindow(self.db); dlg = DataDialog(None, w)
        js, xl = os.path.join(self.d, "d.json"), os.path.join(self.d, "d.xlsx")
        with mock.patch.object(QFileDialog, "getSaveFileName", side_effect=[(js, ""), (xl, "")]), \
                mock.patch.object(QMessageBox, "information"):
            dlg.export_json(); dlg.export_xlsx()
        wb = load_workbook(xl)
        self.assertEqual(wb.sheetnames, ["Накази", "Люди", "Графік відпусток", "Додатки"])
        self.assertEqual(wb["Накази"].max_row, 2); self.assertEqual(wb["Люди"]["B2"].value, "Коваль")
        create_from_template(w.db, "o_free", {"subject": "зайве"})
        with mock.patch.object(QFileDialog, "getOpenFileName", return_value=(js, "")), \
                mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes), \
                mock.patch.object(QMessageBox, "information"):
            dlg.import_json()
        self.assertEqual(len(w.db.list_orders()), 1)
        self.assertFalse([f for f in os.listdir(self.d) if f.startswith("import-")])  # тимчасовий файл прибрано
        dlg.close(); w.close(); self.db = w.db


from qt_cleanup import tearDownModule  # noqa: E402,F401

if __name__ == "__main__":
    unittest.main()
