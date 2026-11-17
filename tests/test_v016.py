"""0.1.6: наказ оновлює довідник (і скасування повертає), алфавітна книга, нагадування, візи, титул справи."""
import datetime as dt
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["NAKAZY_OFFLINE"] = "1"

from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox  # noqa: E402

app = QApplication.instance() or QApplication([])

from nakazy import effects  # noqa: E402
from nakazy.db import Database  # noqa: E402
from nakazy.people import People  # noqa: E402
from nakazy.reminders import reminders  # noqa: E402
from nakazy.ui.order_editor import OrderEditor, create_from_template  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.db = Database(os.path.join(self.d, "n.db")); self.db.set_setting("head", "Олена ПЕТРЕНКО")
        self.ppl = People(self.db)

    def tearDown(self):
        self.db.close()

    def person(self, pid):
        return self.ppl.get(pid)


class EffectsTest(Base):
    def test_pupil_flow_and_alphabet(self):
        self.ppl.add(kind="pupil", last="Коваль", first="Іван", cls="6-А", case_no="К-7")
        self.ppl.add(kind="pupil", last="Кравець", first="Ілля", cls="6-А", case_no="К/12")
        p = self.ppl.add(kind="pupil", last="Коваленко", first="Оля", middle="Петрівна", status="left")
        o = create_from_template(self.db, "u_enroll", {"cls": "5а", "from_date": "02.09.2026"}, persons={"pupil": p})
        self.assertEqual(effects.apply(self.db, o), [])  # чернетка довідник не змінює
        self.db.register(o, "2026-09-02")
        msg = effects.apply(self.db, o)
        r = self.person(p)
        self.assertEqual((r["status"], r["cls"], r["enrolled"], r["case_no"]), ("active", "5-А", "2026-09-02", "К-13"))
        self.assertIn("особова справа: К-13", msg[0])
        self.assertEqual(effects.apply(self.db, o), [])  # двічі не застосовується
        t = create_from_template(self.db, "u_transfer_class", {"cls": "5-А", "cls_new": "5-Б"}, persons={"pupil": p})
        self.db.register(t, "2026-10-01"); effects.apply(self.db, t)
        self.assertEqual(self.person(p)["cls"], "5-Б")
        x = create_from_template(self.db, "u_expel", {"cls": "5-Б"}, persons={"pupil": p})
        self.db.register(x, "2026-11-01"); effects.apply(self.db, x)
        self.assertEqual(self.person(p)["status"], "left")
        rows = effects.alphabet_rows(self.db)
        mine = next(r for r in rows if r["name"].startswith("Коваленко"))
        self.assertEqual((mine["case_no"], mine["in_date"], mine["in_order"], mine["out_date"], mine["left"]),
                         ("К-13", "02.09.2026", "1-у", "01.11.2026", True))
        self.assertEqual([r["case_no"] for r in rows], ["К-7", "К/12", "К-13"])  # за номером у межах літери
        # скасування наказу про вибуття повертає статус; про переведення – клас
        self.db.cancel(x, "помилка"); self.assertIn("повернуто", effects.revert(self.db, x)[0])
        self.assertEqual(self.person(p)["status"], "active")
        self.ppl.update(p, cls="5-В")  # клас змінили вручну після наказу про переведення
        self.db.cancel(t, "помилка"); self.assertIn("лишено як є", effects.revert(self.db, t)[0])
        self.assertEqual(self.person(p)["cls"], "5-В")
        from openpyxl import load_workbook
        path = effects.export_alphabet_xlsx(self.db, os.path.join(self.d, "a.xlsx"))
        self.assertEqual(load_workbook(path).active["B4"].value, "К-13")

    def test_staff_and_not_linked(self):
        e = self.ppl.add(kind="staff", last="Ткач", first="Наталія", status="left")
        h = create_from_template(self.db, "k_hire", {"position": "вчителя історії"}, persons={"employee": e})
        self.db.register(h, "2026-09-01"); effects.apply(self.db, h)
        self.assertEqual((self.person(e)["status"], self.person(e)["position"]), ("active", "вчителя історії"))
        m = create_from_template(self.db, "k_move", {"position_new": "заступник директора"}, persons={"employee": e})
        self.db.register(m, "2026-10-01"); effects.apply(self.db, m)
        self.assertEqual(self.person(e)["position"], "заступник директора")
        dsm = create_from_template(self.db, "k_dismiss", {}, persons={"employee": e})
        self.db.register(dsm, "2026-12-01"); effects.apply(self.db, dsm)
        self.assertEqual(self.person(e)["status"], "left")
        free = create_from_template(self.db, "k_dismiss", {"employee": "Невідомий"})
        self.db.register(free, "2026-12-02")
        self.assertIn("не вибрано з довідника", effects.apply(self.db, free)[0])
        other = create_from_template(self.db, "o_free", {"subject": "чергування"}); self.db.register(other, "2026-12-03")
        self.assertEqual(effects.apply(self.db, other), [])

    def test_main_window_register_and_cancel(self):
        from nakazy.ui.main_window import MainWindow
        p = self.ppl.add(kind="pupil", last="Шевчук", first="Ольга", cls="6-Б")
        o = create_from_template(self.db, "u_expel", {"cls": "6-Б"}, persons={"pupil": p})
        w = MainWindow(self.db)
        for i in range(w.list.topLevelItemCount()):
            if w.list.topLevelItem(i).data(0, 256) == o:
                w.list.setCurrentItem(w.list.topLevelItem(i))
        with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes), \
                mock.patch.object(QMessageBox, "information") as info:
            w.register_current()
        self.assertIn("Шевчук Ольга: статус: вибув", info.call_args[0][2])
        self.assertEqual(self.person(p)["status"], "left")
        for i in range(w.list.topLevelItemCount()):
            if w.list.topLevelItem(i).data(0, 256) == o:
                w.list.setCurrentItem(w.list.topLevelItem(i))
        with mock.patch.object(QInputDialog, "getText", return_value=("помилка", True)), \
                mock.patch.object(QMessageBox, "information") as info:
            w.cancel_current()
        self.assertEqual(self.person(p)["status"], "active"); info.assert_called_once()
        w.close()


class RemindersTest(Base):
    def test_reminders(self):
        from nakazy.leave_plan import LeavePlan
        today = dt.date(2026, 12, 10)
        e = self.ppl.add(kind="staff", last="Коваль", first="Марія", middle="Іванівна", attest_year=2026)
        a = create_from_template(self.db, "o_free", {"subject": "прострочене"}); self.db.register(a, "2026-11-01")
        b = create_from_template(self.db, "o_free", {"subject": "скоро"}); self.db.register(b, "2026-11-02")
        c = create_from_template(self.db, "o_free", {"subject": "далеко"}); self.db.register(c, "2026-11-03")
        self.db.set_control(a, "2026-12-01"); self.db.set_control(b, "2026-12-15"); self.db.set_control(c, "2027-03-01")
        old = create_from_template(self.db, "o_free", {"subject": "стара чернетка"})
        self.db.con.execute("UPDATE orders SET created_at = '2026-11-20T10:00:00' WHERE id = ?", (old,))
        create_from_template(self.db, "o_free", {"subject": "свіжа чернетка"})
        self.db.con.execute("UPDATE orders SET created_at = '2026-12-09T10:00:00' WHERE title LIKE '%свіжа%'")
        LeavePlan(self.db).add(2026, e, days=14, from_date="2026-12-20", to_date="2027-01-02")
        LeavePlan(self.db).add(2027, e, days=14, from_date="2027-07-01", to_date="2027-07-14")
        rs = reminders(self.db, today)
        text = "\n".join(r["text"] for r in rs)
        self.assertEqual(rs[0]["level"], "увага"); self.assertIn("Прострочено виконання (01.12.2026)", rs[0]["text"])
        for s in ("Строк виконання 15.12.2026", "стара чернетка", "Відпустка за графіком з 20.12.2026",
                  "Атестація у 2026 році: Коваль Марія", "Номенклатуру справ на 2027 рік"):
            self.assertIn(s, text)
        for s in ("далеко", "свіжа чернетка", "01.07.2027"):
            self.assertNotIn(s, text)
        self.db.set_done(a, True)
        self.assertNotIn("Прострочено", "\n".join(r["text"] for r in reminders(self.db, today)))
        from nakazy.cases import Cases
        Cases(self.db).ensure_year(2027)
        self.assertNotIn("Номенклатуру", "\n".join(r["text"] for r in reminders(self.db, today)))
        self.assertNotIn("Номенклатуру", "\n".join(r["text"] for r in reminders(self.db, dt.date(2026, 6, 1))))

    def test_dialogs_and_button(self):
        from nakazy.ui.extra_dialogs import AlphabetDialog, RemindersDialog
        from nakazy.ui.main_window import MainWindow
        a = create_from_template(self.db, "o_free", {"subject": "строк"}); self.db.register(a, "2020-01-10")
        self.db.set_control(a, "2020-02-01")
        w = MainWindow(self.db)
        self.assertEqual(w.remind_btn.text(), "Нагадування… (1)")
        dlg = RemindersDialog(None, self.db); self.assertEqual(dlg.list.count(), 1)
        dlg.list.setCurrentRow(0); dlg.mark_done()
        self.assertEqual(dlg.list.item(0).text(), "Нагадувань немає.")
        w.refresh(); self.assertEqual(w.remind_btn.text(), "Нагадування…")
        self.ppl.add(kind="pupil", last="Білий", first="Іван", case_no="Б-1")
        al = AlphabetDialog(None, self.db); self.assertEqual(al.table.rowCount(), 1)
        self.assertEqual(al.table.item(0, 0).text(), "Б-1")
        dlg.close(); al.close(); w.close()


class VisasAndControlTest(Base):
    def test_editor_fields_and_export(self):
        import docx

        from nakazy.export import duplex_hint, export_docx, visas_list
        self.assertEqual(visas_list("Заступник директора, Ірина КОВАЛЬ; Юрист"),
                         [("Заступник директора", "Ірина КОВАЛЬ"), ("Юрист", "")])
        self.assertTrue(duplex_hint("v")); self.assertFalse(duplex_hint("k")); self.assertFalse(duplex_hint("osn"))
        oid = create_from_template(self.db, "o_free", {"subject": "чергування"})
        ed = OrderEditor(self.db, oid)
        self.assertFalse(ed.done.isEnabled())  # «Виконано» – лише для зареєстрованого
        ed.visas.setText("Заступник директора, Ірина КОВАЛЬ")
        ed.due.setText("15.12.2026"); ed._save_due()
        ed.save_order()
        row = self.db.get(oid)
        self.assertEqual((row["visas"], row["due_date"]), ("Заступник директора, Ірина КОВАЛЬ", "2026-12-15"))
        self.assertIn("Ірина КОВАЛЬ", ed.text.foot.text())
        ed.due.setText("15/13"); ed._save_due()
        self.assertEqual(self.db.get(oid)["due_date"], "2026-12-15")  # хибна дата не записується
        ed._closed = True; ed.close()
        out = os.path.join(self.d, "o.docx"); export_docx(self.db, oid, out)
        text = "\n".join(p.text for p in docx.Document(out).paragraphs)
        self.assertIn("Заступник директора", text); self.assertIn("Ірина КОВАЛЬ", text)
        self.assertLess(text.index("Олена ПЕТРЕНКО"), text.index("Ірина КОВАЛЬ"))  # візи нижче підпису
        self.db.register(oid, "2026-12-01")
        ro = OrderEditor(self.db, oid)
        self.assertTrue(ro.done.isEnabled()); self.assertFalse(ro.visas.isEnabled())
        ro.done.setChecked(True); self.assertEqual(self.db.get(oid)["done"], 1)
        ro.due.setText(""); ro._save_due(); self.assertEqual(self.db.get(oid)["due_date"], "")
        ro.close()

    def test_draft_from_plan_can_be_deleted(self):
        """Чернетку наказу, створену з графіка відпусток, можна видалити (рядок графіка звільняється)."""
        from nakazy.leave_plan import LeavePlan
        e = self.ppl.add(kind="staff", last="Коваль", first="Марія", middle="Іванівна")
        plan = LeavePlan(self.db); r = plan.add(2027, e, days=14, from_date="2027-07-01", to_date="2027-07-14")
        oid = plan.make_leave_orders([r])[0]
        self.db.delete_draft(oid)
        self.assertIsNone(self.db.con.execute("SELECT order_id FROM leave_plan WHERE id = ?", (r,)).fetchone()[0])
        self.assertEqual(len(plan.make_leave_orders([r])), 1)


from qt_cleanup import tearDownModule  # noqa: E402,F401

if __name__ == "__main__":
    unittest.main()
