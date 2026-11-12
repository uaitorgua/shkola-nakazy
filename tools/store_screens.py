"""Знімки для Microsoft Store (packaging/store/*.png) на демонстраційній базі у тимчасовій теці."""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ["NAKAZY_OFFLINE"] = "1"
os.environ["QT_SCALE_FACTOR"] = "1"

from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])
tr = QTranslator(app)
tr.load(QLocale(QLocale.Language.Ukrainian), "qtbase", "_", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))
app.installTranslator(tr)

from nakazy.db import Database  # noqa: E402
from nakazy.people import People  # noqa: E402
from nakazy.ui.main_window import MainWindow  # noqa: E402
from nakazy.ui.order_editor import OrderEditor, TemplatePicker, create_from_template  # noqa: E402

db = Database()
for k, v in dict(head="Олена ПЕТРЕНКО", school="Ліцей № 1", city="Дрогобич").items():
    db.set_setting(k, v)
p = People(db)
for n, c in [("Іваненко Петро Олегович", "5-А"), ("Коваль Марія Іванівна", "5-А"), ("Шевчук Ольга Петрівна", "6-Б")]:
    l, f, m = n.split(); p.add(kind="pupil", last=l, first=f, middle=m, cls=c, birth="2015-02-01")
p.add(kind="staff", last="Мельник", first="Андрій", middle="Васильович", position="вчитель математики")
demo = [("o_year_start", {"school_year": "2026/2027", "from_date": "01.09.2026"}, "2026-09-01"),
        ("k_hire", {"employee": "Мельника Андрія Васильовича", "position": "вчителя математики", "from_date": "01.09.2026"}, "2026-09-01"),
        ("u_enroll", {"pupil": "Іваненка Петра Олеговича", "cls": "5-А", "from_date": "02.09.2026"}, "2026-09-02"),
        ("o_food", {"school_year": "2026/2027", "from_date": "02.09.2026"}, "2026-09-02"),
        ("o_attest", {"school_year": "2026/2027"}, "2026-10-01"),
        ("v_annual", {"employee": "Коваль Марії Іванівни", "position": "вчителю", "days": "14"}, "2026-10-15"),
        ("o_excursion", {"cls": "5-А", "place": "Львова", "date": "22.10.2026"}, "2026-10-20"),
        ("g_inventory", {"date": "01.11.2026"}, "2026-11-02")]
for t, v, d in demo:
    db.register(create_from_template(db, t, v), d)
create_from_template(db, "u_expel", {"pupil": "Шевчук Ольги Петрівни"})
out = os.path.join(ROOT, "packaging", "store")
W, H = 1366, 768

w = MainWindow(db); w.resize(W, H); w.show(); app.processEvents()
w.list.setCurrentItem(w.list.topLevelItem(2)); app.processEvents()
w.grab().save(os.path.join(out, "01_reiestr.png"))
tp = TemplatePicker(w, "u", db); tp.resize(W, H); tp.show(); app.processEvents()
top = tp.tree.topLevelItem(1)
for i in range(top.childCount()):
    if top.child(i).text(0) == "Вибуття":
        top.child(i).setExpanded(True); tp.tree.setCurrentItem(top.child(i).child(0))
app.processEvents()
tp._pick_person("pupil", p.find("pupil", "Коваль")[0]["id"]); app.processEvents()
tp.grab().save(os.path.join(out, "02_shablon.png"))
e = OrderEditor(db, db.list_orders(query="екскурсію")[0]["id"], w); e.resize(W, H); e.show(); app.processEvents()
e.grab().save(os.path.join(out, "03_redaktor.png"))
print("знімки:", out)
