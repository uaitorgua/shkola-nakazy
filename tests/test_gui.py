"""Сценарій секретаря у вікні (без ручних кліків; діалоги підмінено)."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["NAKAZY_OFFLINE"] = "1"

from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog, QMessageBox  # noqa: E402

from nakazy.audit import audit  # noqa: E402
from nakazy.db import Database  # noqa: E402
from nakazy.ui import main_window as mw  # noqa: E402
from nakazy.ui.order_editor import OrderEditor  # noqa: E402

app = QApplication.instance() or QApplication([])


class Secretary(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.db = Database(os.path.join(self.d, "g.db"))
        self.db.set_setting("head", "Олена ПЕТРЕНКО")
        self.msgs = []
        QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
        QMessageBox.information = staticmethod(lambda *a, **k: self.msgs.append(a[2]))
        QMessageBox.warning = staticmethod(lambda *a, **k: self.msgs.append(a[2]))
        self.w = mw.MainWindow(self.db)
        self.opened = []
        self.w.open_editor = lambda oid: self.opened.append(OrderEditor(self.db, oid, self.w))

    def select(self, oid):
        for i in range(self.w.list.topLevelItemCount()):
            it = self.w.list.topLevelItem(i)
            if it.data(0, mw.ROLE) == oid:
                self.w.list.setCurrentItem(it); return
        self.fail(f"наказ {oid} не видно в списку")

    def test_day_of_secretary(self):
        # 1. новий наказ за шаблоном через майстер
        class Picker:
            def __init__(s, *a): s.template_id = "u_enroll"; s.persons = {}
            def exec(s): return True
            def values(s): return {"pupil": "Іваненка Петра Олеговича", "cls": "5-А", "birth": "01.02.2015",
                                   "from_date": "03.11.2026", "application": "заяви матері від 01.11.2026"}
        mw.TemplatePicker = Picker
        self.w.new_order()
        ed = self.opened[-1]; oid = ed.order_id
        # 2. редагування в InterText і збереження
        ed.date.setDate(ed.date.date().fromString("2026-11-03", "yyyy-MM-dd"))
        ed.edit.append("Додатковий абзац.")
        ed.save_order()
        self.assertIn("Додатковий абзац", self.db.get(oid)["body_html"])
        # 3. реєстрація з вікна
        self.w.refresh(); self.select(oid); self.w.register_current()
        self.assertEqual(self.db.get(oid)["reg_index"], "1-у")
        # 4. спроба змінити зареєстрований: редактор лише для перегляду
        self.w.edit_current()
        ro = self.opened[-1]
        self.assertTrue(ro.edit.isReadOnly())
        ro.save_order()
        self.assertNotIn("зламано", self.db.get(oid)["body_html"])
        # 5. наказ про зміни
        self.w.refresh(); self.select(oid); self.w.amend_current()
        amend = self.opened[-1].order_id
        self.assertEqual(self.db.get(amend)["amends_order_id"], oid)
        # 6. пошук і бокове меню
        self.w.search.setText("Іваненка")
        self.assertGreaterEqual(self.w.list.topLevelItemCount(), 1)
        # 7. журнал і перевірка аудитором
        QInputDialog.getItem = staticmethod(lambda *a, **k: ("Накази з руху учнів", True))
        path = os.path.join(self.d, "j.docx")
        QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (path, ""))
        self.w.export_journal()
        self.assertTrue(os.path.getsize(path) > 0)
        self.w.run_audit()
        self.assertNotIn("[помилка]", self.msgs[-1])
        self.assertIn("руху учнів", self.msgs[-1])  # строк для руху учнів визначає заклад: нагадування
        self.assertEqual([x for x in audit(self.db) if x[0] == "помилка"], [])


from qt_cleanup import tearDownModule  # noqa: E402,F401

if __name__ == "__main__":
    unittest.main()
