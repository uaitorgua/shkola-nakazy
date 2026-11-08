import datetime as dt
import os
import random
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["NAKAZY_OFFLINE"] = "1"

from openpyxl import Workbook  # noqa: E402

from nakazy import importer  # noqa: E402
from nakazy.db import Database  # noqa: E402
from nakazy.names import all_cases  # noqa: E402
from nakazy.people import People, person_values  # noqa: E402
from nakazy.templates import TEMPLATE_BY_ID, render  # noqa: E402

NAMES = [  # (називний, родовий, давальний, знахідний)
    ("Іваненко Петро Олегович", "Іваненка Петра Олеговича", "Іваненку Петрові Олеговичу", "Іваненка Петра Олеговича"),
    ("Коваль Марія Іванівна", "Коваль Марії Іванівни", "Коваль Марії Іванівні", "Коваль Марію Іванівну"),
    ("Шевчук Ольга Петрівна", "Шевчук Ольги Петрівни", "Шевчук Ользі Петрівні", "Шевчук Ольгу Петрівну"),
    ("Петровська Анна Миколаївна", "Петровської Анни Миколаївни", "Петровській Анні Миколаївні",
     "Петровську Анну Миколаївну"),
    ("Коваль Василь Ігорович", "Коваля Василя Ігоровича", "Ковалю Василеві Ігоровичу", "Коваля Василя Ігоровича"),
    ("Білий Микола Іванович", "Білого Миколи Івановича", "Білому Миколі Івановичу", "Білого Миколу Івановича"),
    ("Кравець Ілля Сергійович", "Кравця Іллі Сергійовича", "Кравцю Іллі Сергійовичу", "Кравця Іллю Сергійовича"),
    ("Ткач Наталія Олегівна", "Ткач Наталії Олегівни", "Ткач Наталії Олегівні", "Ткач Наталію Олегівну"),
    ("Мельник Андрій Васильович", "Мельника Андрія Васильовича", "Мельнику Андрію Васильовичу",
     "Мельника Андрія Васильовича"),
]


class Names(unittest.TestCase):
    def test_cases(self):
        for nom, gen, dat, acc in NAMES:
            c = all_cases(*nom.split())
            self.assertEqual((c["gen"], c["dat"], c["acc"]), (gen, dat, acc), nom)


def xlsx(path, rows):
    wb = Workbook(); ws = wb.active
    for r in rows:
        ws.append(r)
    wb.save(path)


class Import(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.db = Database(os.path.join(self.d, "p.db"))

    def run_import(self, path, kind="pupil", left=False):
        rows = importer.read_table(path)
        hi, m = importer.detect_header(rows)
        people, errs = importer.rows_to_people(rows, hi, m, kind)
        plan = importer.make_plan(self.db, people, kind)
        return importer.apply_plan(self.db, plan, left), errs, plan

    def test_xlsx_with_title_rows_and_full_name(self):
        p = os.path.join(self.d, "a.xlsx")
        xlsx(p, [["Звіт АІКОМ2"], ["Ліцей № 1", None, None], [],
                 ["№ з/п", "Прізвище, ім'я, по батькові", "Дата народження", "Клас", "Стать"],
                 [1, "Іваненко Петро Олегович", dt.date(2015, 2, 1), "5-А", "чол"],
                 [2, "Коваль Марія Іванівна", "03.04.2015", "5 А", "жін"],
                 [None, None, None, None, None],
                 ["Разом", 2, None, None, None]])
        res, errs, _ = self.run_import(p)
        self.assertEqual(res["new"], 2, errs)
        ppl = People(self.db).find("pupil")
        self.assertEqual({r["cls"] for r in ppl}, {"5-А"})
        self.assertEqual({r["birth"] for r in ppl}, {"2015-02-01", "2015-04-03"})
        # повторний імпорт: без дублів
        res, _, plan = self.run_import(p)
        self.assertEqual((res["new"], res["changed"], plan.same), (0, 0, 2))

    def test_csv_cp1251_separate_columns_and_update(self):
        p = os.path.join(self.d, "b.csv")
        text = ("Прізвище;Ім'я;По батькові;Дата народження;Паралель;Літера\r\n"
                "Шевчук;Ольга;Петрівна;42000;6;б\r\n"
                "Ткач;Наталія;Олегівна;1.9.14;6;Б\r\n")
        open(p, "wb").write(text.encode("cp1251"))
        res, errs, _ = self.run_import(p)
        self.assertEqual(res["new"], 2, errs)
        r = People(self.db).find("pupil", "Шевчук")[0]
        self.assertEqual((r["cls"], r["birth"]), ("6-Б", "2014-12-27"))
        # переведення до 7 класу й вибуття Ткач
        open(p, "wb").write("Прізвище;Ім'я;По батькові;Дата народження;Клас\r\nШевчук;Ольга;Петрівна;27.12.2014;7-Б\r\n"
                            .encode("utf-8-sig"))
        res, _, _ = self.run_import(p, left=True)
        self.assertEqual((res["changed"], res["left"]), (1, 1))
        self.assertEqual(People(self.db).find("pupil", "Шевчук")[0]["cls"], "7-Б")
        self.assertEqual(People(self.db).find("pupil", "Ткач"), [])

    def test_staff(self):
        p = os.path.join(self.d, "s.xlsx")
        xlsx(p, [["ПІБ", "Посада", "Ставка", "Кваліфікаційна категорія"],
                 ["Мельник Андрій Васильович", "вчитель математики", 1.5, "вища"]])
        res, errs, _ = self.run_import(p, "staff")
        self.assertEqual(res["new"], 1)
        self.assertEqual(People(self.db).find("staff")[0]["position"], "вчитель математики")

    def test_garbage_files_do_not_crash(self):
        rnd = random.Random(7)
        junk = ["", "  ", "=SUM(A1)", "№", "1", "Іван", "32.13.2020", "2015-02-30", "'; DROP TABLE people;--",
                "Коваль\nМарія", "😀", "x" * 300, None, 3.5, dt.date(1850, 1, 1)]
        for n in range(40):
            p = os.path.join(self.d, f"j{n}.xlsx")
            rows = [[rnd.choice(junk) for _ in range(rnd.randint(1, 6))] for _ in range(rnd.randint(0, 25))]
            if rnd.random() < .6:
                rows.insert(rnd.randint(0, len(rows)), rnd.sample(["ПІБ", "Прізвище", "Дата народження", "Клас",
                                                                  "Посада", "Ім'я"], 3))
            xlsx(p, rows)
            self.run_import(p, rnd.choice(["pupil", "staff"]))
        self.assertEqual(self.db.con.execute("PRAGMA integrity_check").fetchone()[0], "ok")


class TemplatesWithPeople(unittest.TestCase):
    def test_female_cases_in_template_and_links(self):
        d = tempfile.mkdtemp(); db = Database(os.path.join(d, "t.db"))
        ppl = People(db)
        pid = ppl.add(kind="pupil", last="Коваль", first="Марія", middle="Іванівна", birth="2015-04-03", cls="5-А")
        ppl.add(kind="pupil", last="Іваненко", first="Петро", middle="Олегович", cls="5-А")
        vals = person_values(ppl, ppl.get(pid), "pupil")
        title, body = render(TEMPLATE_BY_ID["u_expel"], vals)
        self.assertEqual(title, "Про відрахування Коваль Марії Іванівни")
        self.assertIn("Відрахувати Коваль Марію Іванівну, учениці 5-А класу", body)
        from nakazy.ui.order_editor import create_from_template
        oid = create_from_template(db, "u_expel", vals, persons={"pupil": pid})
        self.assertEqual([r["id"] for r in ppl.orders_of(pid)], [oid])
        ex = create_from_template(db, "o_excursion", {"cls": "5-А"})
        self.assertIn("Іваненко Петро", db.attachments(ex)[0]["body_html"])
        # ручне виправлення відмінка має пріоритет
        ppl.set_forms(pid, {"gen": "Коваль Марії Іванівни (вручну)"})
        self.assertTrue(person_values(ppl, ppl.get(pid), "pupil")["pupil.gen"].endswith("(вручну)"))


class Gui(unittest.TestCase):
    def test_windows(self):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        from nakazy.ui.order_editor import TemplatePicker
        from nakazy.ui.people_window import ImportDialog, PeopleWindow
        d = tempfile.mkdtemp(); db = Database(os.path.join(d, "g.db"))
        p = os.path.join(d, "a.xlsx")
        xlsx(p, [["ПІБ", "Дата народження", "Клас"], ["Коваль Марія Іванівна", "03.04.2015", "5-А"]])
        dlg = ImportDialog(None, db, "pupil"); dlg.load(p); dlg._preview()
        self.assertEqual(len(dlg.plan.new), 1); dlg._apply = dlg._apply  # noqa
        from nakazy import importer as im
        im.apply_plan(db, dlg.plan)
        w = PeopleWindow(db); w.show(); app.processEvents()
        self.assertEqual(w.lists["pupil"].topLevelItemCount(), 1)
        w.lists["pupil"].setCurrentItem(w.lists["pupil"].topLevelItem(0)); app.processEvents()
        self.assertIn("Коваль Марії Іванівни", w.card.toPlainText())
        tp = TemplatePicker(None, "u", db)
        tp.template_id = "u_expel"
        top = tp.tree.topLevelItem(1)
        for i in range(top.childCount()):
            for j in range(top.child(i).childCount()):
                if top.child(i).child(j).data(0, 256) == "u_expel":
                    tp.tree.setCurrentItem(top.child(i).child(j))
        pid = People(db).find("pupil")[0]["id"]
        tp._pick_person("pupil", pid)
        v = tp.values()
        self.assertEqual((v["pupil.acc"], v["cls"], tp.persons), ("Коваль Марію Іванівну", "5-А", {"pupil": pid}))
        tp.edits["pupil"].setText("Інша Особа")
        self.assertNotIn("pupil.acc", tp.values())


if __name__ == "__main__":
    unittest.main()
