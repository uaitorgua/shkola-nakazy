"""Сторінка інструкції на сайті: https://uait.org.ua/nakazy/ (promo/site/index.html + img/).

Інструкція прив'язана до версії: номер береться з nakazy/__init__.py, а tests/test_site.py не пропускає
збірку, якщо сторінка не перегенерована під поточну версію або в VERSIONS немає запису про неї.
При кожному оновленні програми: дописати VERSIONS, за потреби текст у main_html(), запустити
python tools\\site.py (знімки екрана теж оновлюються), залити promo/site на сервер.

python tools\\site.py          – знімки + сторінка
python tools\\site.py noshots  – лише сторінка (знімки лишаються)
"""
from __future__ import annotations

import html
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, "promo", "site")
URL = "https://uait.org.ua/nakazy/"
STORE = "https://apps.microsoft.com/detail/9PJNZB9R4HGK"
MAIL = "mailto:admin@uait.org.ua?subject=%D0%9D%D0%B0%D0%BA%D0%B0%D0%B7%D0%B8%20%D0%A8%D0%9A%D0%9E%D0%9B%D0%90"

# Що нового: новіша версія першою. Перший запис має збігатися з nakazy.__version__ (перевіряє test_site).
VERSIONS = [
    ("0.1.5", "17.11.2026", [
        "Текст наказу редагується в окремій програмі: «Офіс ШКОЛА» (InterText), якщо встановлений, або програма "
        "Windows для DOCX; зміни після збереження файла самі повертаються в наказ, попередня редакція лишається "
        "в історії. Вбудованого редактора більше немає, програма стала легшою.",
        "«Заклад…» → «Редактор тексту наказів»: автоматично, програма Windows або вибрана програма.",
        "Ширина колонок таблиці групового наказу підбирається за вмістом.",
    ]),
    ("0.1.4", "17.11.2026", [
        "22 нові кадрові шаблони: припинення виконання обов'язків, поновлення, робота у вихідний день, вихід "
        "з відпустки для догляду за дитиною, заохочення, премія, допомога на оздоровлення, надбавка за вислугу "
        "років, оплата заміни уроків, підвищення кваліфікації, призов і повернення зі служби, зміна облікових "
        "даних; графік відпусток, перенесення й компенсація відпустки, дні відпочинку, відрядження, догана.",
        "Зв'язок наказів: наказ-підстава вибирається з реєстру, дата й номер підставляються самі.",
        "Залишок днів щорічної відпустки в картці працівника й у майстрі шаблону.",
        "Групові накази: кілька працівників в одному наказі.",
        "Графік відпусток таблицею: наказ про затвердження й накази про відпустку з таблиці.",
    ]),
    ("0.1.3", "12.11.2026", ["Пошук у шаблонах за частиною слова. Перша версія в Microsoft Store."]),
]


def shots():
    """Знімки вікон на демонстраційній базі (без вікон на екрані)."""
    os.environ["APPDATA"] = tempfile.mkdtemp()
    os.environ["NAKAZY_OFFLINE"] = "1"
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["QT_QPA_FONTDIR"] = r"C:\Windows\Fonts"
    os.environ["QT_SCALE_FACTOR"] = "1"
    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
    from PySide6.QtWidgets import QApplication
    app = QApplication([])
    tr = QTranslator(app)
    tr.load(QLocale(QLocale.Language.Ukrainian), "qtbase", "_", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))
    app.installTranslator(tr)
    from nakazy.db import Database
    from nakazy.leave_plan import LeavePlan
    from nakazy.people import People
    from nakazy.ui.leave_plan_dialog import LeavePlanDialog
    from nakazy.ui.main_window import MainWindow
    from nakazy.ui.order_editor import OrderEditor, TemplatePicker, create_from_template
    from nakazy.ui.people_window import PeopleWindow

    db = Database()
    for k, v in dict(head="Олена ПЕТРЕНКО", school="Ліцей № 1", city="Дрогобич").items():
        db.set_setting(k, v)
    p = People(db)
    for n, c in [("Іваненко Петро Олегович", "5-А"), ("Коваль Марія Іванівна", "5-А"), ("Шевчук Ольга Петрівна", "6-Б")]:
        last, first, mid = n.split(); p.add(kind="pupil", last=last, first=first, middle=mid, cls=c, birth="2015-02-01")
    staff = {}
    for n, pos, right in [("Мельник Андрій Васильович", "вчитель математики", 56),
                          ("Ткач Наталія Олегівна", "вчитель української мови", 56),
                          ("Білий Микола Іванович", "бібліотекар", 28)]:
        last, first, mid = n.split()
        staff[last] = p.add(kind="staff", last=last, first=first, middle=mid, position=pos, leave_right=right)
    period = "з 01.09.2025 по 31.08.2026"
    demo = [("o_year_start", {"school_year": "2026/2027", "from_date": "01.09.2026"}, "2026-09-01"),
            ("k_hire", {"employee": "Мельника Андрія Васильовича", "position": "вчителя математики",
                        "from_date": "01.09.2026"}, "2026-09-01"),
            ("u_enroll", {"pupil": "Іваненка Петра Олеговича", "cls": "5-А", "from_date": "02.09.2026"}, "2026-09-02"),
            ("o_attest", {"school_year": "2026/2027"}, "2026-10-01"),
            ("o_excursion", {"cls": "5-А", "place": "Львова", "date": "22.10.2026"}, "2026-10-20"),
            ("g_inventory", {"date": "01.11.2026"}, "2026-11-02")]
    for t, v, d in demo:
        db.register(create_from_template(db, t, v), d)
    plan = LeavePlan(db)
    rows = [plan.add(2026, staff["Мельник"], days=42, from_date="2026-07-01", to_date="2026-08-11", period=period),
            plan.add(2026, staff["Ткач"], days=28, from_date="2026-07-06", to_date="2026-08-02", period=period),
            plan.add(2026, staff["Білий"], days=28, from_date="2026-08-03", to_date="2026-08-30", period=period)]
    db.register(plan.make_schedule_order(2026, "первинною профспілковою організацією"), "2026-01-12")
    for oid in plan.make_leave_orders(rows[:1]):
        db.register(oid, "2026-06-20")
    os.makedirs(os.path.join(OUT, "img"), exist_ok=True)
    img = lambda n: os.path.join(OUT, "img", n)  # noqa: E731
    W, H = 1366, 768

    w = MainWindow(db); w.resize(W, H); w.show(); app.processEvents()
    w.list.setCurrentItem(w.list.topLevelItem(1)); app.processEvents()
    w.grab().save(img("01_reiestr.png"))

    def picker(kind, tid):
        tp = TemplatePicker(w, kind, db); tp.resize(W, H); tp.show(); app.processEvents()
        tops = [tp.tree.topLevelItem(i) for i in range(tp.tree.topLevelItemCount())]
        for t in tops:
            for i in range(t.childCount()):
                for j in range(t.child(i).childCount()):
                    if t.child(i).child(j).data(0, 256) == tid:
                        t.setExpanded(True); t.child(i).setExpanded(True); tp.tree.setCurrentItem(t.child(i).child(j))
        app.processEvents()
        return tp
    tp = picker("v", "v_transfer")
    from PySide6.QtWidgets import QComboBox

    def choose(value):  # як користувач: вибір у списку (видно у вікні)
        for cb in tp.form_host.widget().findChildren(QComboBox):
            i = cb.findData(value)
            if i > 0:
                cb.setCurrentIndex(i); cb.activated.emit(i); app.processEvents(); return
    choose(staff["Мельник"])
    choose(tp.ref_boxes["leave_order"].itemData(1))
    for k, v in (("action", "перенесення"), ("action_verb", "Перенести"), ("reason", "тимчасовою непрацездатністю"),
                 ("doc", "листка непрацездатності від 05.07.2026 № 1234"),
                 ("new_period", "на 7 календарних днів з 12.08.2026 до 18.08.2026")):
        tp.edits[k].setText(v)
    app.processEvents(); tp.grab().save(img("02_shablon.png")); tp.close()
    tp = picker("k", "k_reward")
    tp.group_box.setChecked(True)
    for last in ("Мельник", "Ткач", "Білий"):
        tp._group_add(staff[last])
    for r, text in enumerate(("Оголосити подяку", "Нагородити грамотою", "Оголосити подяку")):
        tp.gtable.item(r, 2).setText(text)
    tp.edits["merit"].setText("сумлінну працю та високі результати учнів в олімпіадах")
    app.processEvents(); tp.grab().save(img("03_hrupovyi.png")); tp.close()
    draft = create_from_template(db, "o_excursion", {"cls": "6-Б", "place": "Трускавця", "date": "12.12.2026"})
    e = OrderEditor(db, draft, w); e.resize(W, H); e.show(); app.processEvents()
    e.grab().save(img("04_redaktor.png")); e.close()
    lp = LeavePlanDialog(w, db, 2026); lp.resize(W, 560); lp.show(); app.processEvents()
    lp.grab().save(img("05_hrafik.png")); lp.close()
    pw = PeopleWindow(db, w); pw.resize(W, 600); pw.show(); app.processEvents()
    for i in range(pw.tabs.count() if hasattr(pw, "tabs") else 0):
        if "Праців" in pw.tabs.tabText(i):
            pw.tabs.setCurrentIndex(i)
    app.processEvents()
    lst = pw.lists["staff"]
    for i in range(lst.topLevelItemCount()):
        if lst.topLevelItem(i).text(0) == "Мельник":
            lst.setCurrentItem(lst.topLevelItem(i))
    pw.kind = lambda: "staff"; pw.show_card(); app.processEvents()
    pw.grab().save(img("06_kartka.png")); pw.close()
    w.close(); db.close()
    print("знімки:", os.path.join(OUT, "img"))


def main_html(version: str, date: str) -> str:
    def shot(name, alt):
        return f'<img class="shot mb-4" src="img/{name}?v={version}" alt="{html.escape(alt)}" loading="lazy">'

    def sec(id_, title, body):
        return (f'<section id="{id_}" class="card mb-6"><h2 class="text-2xl font-bold mb-4">{title}</h2>'
                f'<div class="ins">{body}</div></section>')

    toc = [("start", "Встановлення й оновлення"), ("zaklad", "Заклад і бланк"), ("liudy", "Люди"),
           ("novyi", "Новий наказ за шаблоном"), ("hrupa", "Групові накази"), ("zviazok", "Зв'язок наказів"),
           ("redaktor", "Редагування, реєстрація, друк"), ("vidpustky", "Відпустки й графік"),
           ("zhurnal", "Журнали, справи, перевірка"), ("import", "Старі накази"), ("kopii", "Дані й резервні копії"),
           ("versii", "Що нового")]
    changes = "".join(
        f'<h3>Версія {v} <span class="muted">· {d}</span></h3><ul>' + "".join(f"<li>{html.escape(x)}</li>" for x in items)
        + "</ul>" for v, d, items in VERSIONS)
    body = [
        f'<div class="text-xs font-mono text-white/40 mb-3"><a href="/" class="hover:text-white">uait.org.ua</a> / '
        f'<a href="/pz/shkola/" class="hover:text-white">ШКОЛА</a> / Накази</div>',
        '<span class="tag tag-pc">Windows 10 / 11</span>',
        '<h1 class="text-4xl md:text-6xl font-extrabold tracking-tighter mt-5 mb-5 text-glow">Накази '
        '<span class="text-[#fbbf24]">ШКОЛА</span></h1>',
        '<p class="text-white/70 text-lg max-w-3xl mb-4 leading-relaxed">Книга наказів закладу освіти: реєстр з '
        'окремою нумерацією за видами, понад 50 шаблонів, бланк закладу, журнали реєстрації, номенклатура справ, '
        'довідник учнів і працівників, відпустки. Дані зберігаються лише на комп\'ютері закладу.</p>',
        f'<p class="mb-8"><span class="ver">Інструкція до версії {version} · оновлено {date}</span></p>',
        f'<div class="flex flex-wrap gap-3 mb-12"><a class="btn-primary" href="{STORE}" target="_blank" '
        f'rel="noopener">Microsoft Store</a><a class="card no-underline !py-3 !px-6 !rounded-xl font-bold" '
        f'href="{MAIL}">Написати нам</a></div>',
        shot("01_reiestr.png", "Головне вікно: реєстр наказів"),
        '<nav class="card mb-6 mt-10"><h2 class="text-xl font-bold mb-3">Зміст</h2><ol class="toc">'
        + "".join(f'<li><a href="#{a}">{t}</a></li>' for a, t in toc) + "</ol></nav>",
        sec("start", "Встановлення й оновлення", f"""
<p>Програму встановлюють з <a href="{STORE}" target="_blank" rel="noopener">Microsoft Store</a> на Windows 10 або 11.
Інтернет потрібен лише для встановлення й оновлень: накази, довідник і бланк зберігаються на цьому комп'ютері.</p>
<p>Оновлення приходять через Microsoft Store. Коли виходить нова версія, програма повідомляє «Потрібне оновлення»
і відкриває сторінку в Store. Без інтернету програма працює як звичайно. Перед кожною зміною будови бази
програма сама робить її копію, тож внесені дані після оновлення зберігаються.</p>
<p>Головне вікно: ліворуч рік і види наказів з лічильниками, посередині список наказів і кнопки, праворуч перегляд
вибраного наказу. Види: з основної діяльності, з руху учнів (-у), з кадрових питань (-к), про відпустки (-в),
адміністративно-господарські (-г). Номери в кожному виді свої й щороку починаються з 1.</p>"""),
        sec("zaklad", "Заклад і бланк", """
<p>Кнопка <b>«Заклад…»</b>. Спершу заповніть: повну назву закладу, населений пункт, керівника у форматі
«Власне ім'я ПРІЗВИЩЕ» (ДСТУ 4163:2020), посаду керівника, кегль тексту, відступ грифа додатка.
Галочка «З наказом ознайомлені» додає до наказу місце для підписів працівників.</p>
<p>Бланк ставиться лише на першу сторінку наказу. Три способи:</p>
<ul><li><b>Текстовий</b>: програма складає шапку з полів (орган управління, назва закладу, адреса, код ЄДРПОУ, e-mail).</li>
<li><b>Зображення</b>: скан або PNG вашого бланка, ширину задаєте в міліметрах.</li>
<li><b>Готовий бланк у Word (DOCX)</b>, наприклад з гербом. Якщо на бланку вже є слово «НАКАЗ», поставте галочку.</li></ul>"""),
        sec("liudy", "Люди: учні й працівники", f"""
<p>Кнопка <b>«Люди…»</b>. Тут довідник учнів і працівників: його можна вести вручну або завантажити з Excel чи CSV,
зокрема з вивантаження АІКОМ (майстер імпорту сам розпізнає колонки і не створює дублів). Програма сама
відмінює ПІБ (кого, кому, кого); якщо помилилась, виправте відмінок у картці.</p>
<p>У картці працівника є поле <b>«Щорічна відпустка, днів на рік»</b>: з нього програма рахує залишок відпустки.
Картка показує всі накази людини.</p>
{shot("06_kartka.png", "Картка працівника із залишком відпустки")}"""),
        sec("novyi", "Новий наказ за шаблоном", f"""
<ol><li>Натисніть <b>«Новий наказ»</b>. Ліворуч дерево: вид → тип → шаблон. Угорі пошук за частиною слова
(«відпустк», «зарахув», «харч»).</li>
<li>Праворуч поля шаблону й нормативна підстава. Людину виберіть з довідника: ПІБ у потрібних відмінках, клас
чи посада підставляться самі. Можна ввести й вручну.</li>
<li>Натисніть <b>«Створити»</b>: відкриється чернетка наказу в редакторі.</li></ol>
<p>Шаблони мають структуру за Інструкцією МОН № 676: заголовок «Про…», підстава, «НАКАЗУЮ:», пункти.
Нормативні підстави подано як орієнтир; позначені «не підтверджено» заклад звіряє з чинною редакцією акта.</p>
{shot("02_shablon.png", "Майстер шаблону: перенесення відпустки з наказом-підставою")}"""),
        sec("hrupa", "Групові накази", f"""
<p>Для щорічних відпусток, днів відпочинку, відряджень, роботи у вихідний, заохочень, надбавок за вислугу,
допомоги на оздоровлення й підвищення кваліфікації можна оформити один наказ на кількох працівників.</p>
<ol><li>У майстрі шаблону поставте галочку <b>«Кілька працівників (груповий наказ)»</b>.</li>
<li>Натисніть <b>«Додати з довідника…»</b> і виділіть потрібних людей (або «+ рядок» для введення вручну).</li>
<li>У таблиці заповніть дані кожного (дні, дати, захід заохочення…), нижче спільні поля.</li></ol>
<p>Кожен працівник стає окремим пунктом наказу, спільні пункти («Бухгалтерії…») йдуть один раз.</p>
{shot("03_hrupovyi.png", "Груповий наказ про заохочення")}"""),
        sec("zviazok", "Зв'язок наказів", """
<p>Деякі накази спираються на попередній: поновлення на звільнення, відкликання й перенесення відпустки на наказ
про відпустку, день відпочинку на роботу у вихідний, зміни до відрядження на відрядження, зняття догани на догану,
повернення зі служби на увільнення у зв'язку з призовом. У майстрі такого шаблону є поле <b>«Наказ-підстава»</b>:
вибраний наказ підставляє в текст «від дата № номер». Першими в списку стоять накази вибраної людини.</p>
<p>Зв'язок видно в перегляді обох наказів: «Підстава» і «Пов'язаний наказ».</p>"""),
        sec("redaktor", "Редагування, реєстрація, друк", f"""
<p>Наказ відкривається карткою: ліворуч текст наказу, праворуч реквізити (дата, заголовок, підписант, контроль,
примітки) і додатки (текстом або файлом). Програма підказує, якщо структура наказу не відповідає вимогам.</p>
<p><b>Текст наказу</b> редагується в окремій програмі. Натисніть <b>«Редагувати текст»</b>: наказ відкриється
в <b>«Офіс ШКОЛА»</b> (InterText), якщо його встановлено, а якщо ні – у програмі, яку Windows відкриває для
документів DOCX (Word, LibreOffice). Виправте текст і збережіть файл: зміни самі з'являться в картці наказу,
а попередня редакція лишиться в історії. Якщо зміни не з'явились, натисніть «Забрати зміни з файла».
Перший рядок файла – заголовок наказу «Про…».</p>
<p>Програму для тексту можна вибрати в «Заклад…» → «Редактор тексту наказів». Якщо на комп'ютері немає жодної
програми для DOCX, «Накази ШКОЛА» запропонують встановити «Офіс ШКОЛА» з Microsoft Store (безкоштовно).
Зареєстрований наказ відкривається лише копією для перегляду.</p>
<ul><li><b>«Зареєструвати»</b> дає наступний номер у виді (наприклад 12-к). Після реєстрації наказ змінити не
можна: лише кнопкою <b>«Наказ про зміни»</b> (окремий наказ «Про внесення змін…») або <b>«Скасувати»</b>
(номер не звільняється).</li>
<li><b>«Зберегти DOCX/PDF…»</b> зберігає наказ з бланком, підписом і додатками для друку.</li>
<li>Чернетку можна видалити; у неї зберігається історія правок.</li></ul>
{shot("04_redaktor.png", "Картка наказу: текст, реквізити, кнопка «Редагувати текст»")}"""),
        sec("vidpustky", "Відпустки й графік відпусток", f"""
<p><b>Залишок днів.</b> Програма рахує щорічну відпустку кожного працівника за робочими роками: право з картки
мінус використані дні (накази про щорічну відпустку), мінус компенсовані, плюс повернуті при відкликанні.
Рахуються лише зареєстровані накази, створені майстром з працівником з довідника. Залишок видно в картці
працівника і в майстрі, щойно вибрано працівника. Якщо після компенсації лишається менше 24 днів, програма
попереджає (ст. 24 Закону України «Про відпустки»).</p>
<p><b>Графік відпусток</b> (кнопка «Графік відпусток…»):</p>
<ol><li>Виберіть рік і додайте працівників з довідника.</li>
<li>Заповніть вид, кількість днів, дати й робочий рік. Програма попередить, якщо дати переплутані або
заплановано більше, ніж право.</li>
<li><b>«Наказ про затвердження графіка»</b> створює чернетку наказу з таблицею в додатку і грифом «ЗАТВЕРДЖЕНО»
(графік погоджують з профспілковим органом: ст. 10 Закону «Про відпустки», ст. 79 КЗпП).</li>
<li>Перед відпусткою виділіть рядки й натисніть <b>«Накази про відпустку (окремі)»</b> або <b>«Груповий наказ
про відпустки»</b>. Рядок пам'ятає свій наказ і вдруге його не створює.</li></ol>
{shot("05_hrafik.png", "Графік відпусток")}"""),
        sec("zhurnal", "Журнали, справи, перевірка", """
<ul><li><b>«Журнал…»</b> – журнал реєстрації наказів вибраного виду за рік у DOCX (шапка на кожній сторінці).</li>
<li><b>«Справи…»</b> – номенклатура справ на рік зі строками зберігання за Переліком 578/5; кнопка формує справу
одним PDF (перелік і накази з додатками за датами).</li>
<li><b>«Перевірка»</b> – перевірка реєстру: пропущені й повторені номери, порядок дат, накази без підписанта,
незаповнені строки зберігання.</li>
<li>Поле <b>«Пошук у наказах…»</b> шукає за текстом і номерами всіх наказів.</li></ul>"""),
        sec("import", "Старі накази", """
<p><b>«Імпорт наказів…»</b> переносить архів у реєстр: файли Word (DOCX, DOC, RTF, ODT), PDF і скани (текст
розпізнається на комп'ютері, без інтернету). Програма знаходить номер, дату, заголовок і підпис; сумнівне
позначає жовтим, ви виправляєте в таблиці перед записом. Оригінал файла зберігається з наказом.</p>"""),
        sec("kopii", "Дані й резервні копії", """
<p>База наказів зберігається лише на цьому комп'ютері, у теці даних користувача Windows, окремо від програми.
Резервні копії програма робить сама: при кожному запуску (зберігаються 30 останніх) і перед кожною зміною
будови бази під час оновлення (ці не видаляються).</p>
<p>Якщо потрібно відновити дані з копії або перенести реєстр на інший комп'ютер, напишіть нам: допоможемо.</p>"""),
        sec("versii", "Що нового", changes),
        f'<div class="card mb-6"><h2 class="text-xl font-bold mb-3">Контакти</h2><p class="text-white/65 '
        f'leading-relaxed m-0">Питання, пропозиції, допомога: <a class="text-[#00d2ff]" href="{MAIL}">'
        f'admin@uait.org.ua</a> · <a class="text-[#00d2ff]" href="tel:+380687686454">+380 68 768 64 54</a>. '
        f'Розробляємо разом із Дрогобицьким науковим ліцеєм імені Богдана Лепкого.</p></div>',
    ]
    style = ("<style>.ins p,.ins li{color:rgba(255,255,255,.72);line-height:1.7;font-size:.95rem}.ins p{margin:0 0 .8rem}"
             ".ins ul,.ins ol{margin:0 0 .9rem 1.2rem}.ins ul{list-style:disc}.ins ol{list-style:decimal}"
             ".ins li{margin:.25rem 0}.ins b{color:#fff}.ins a{color:#00d2ff}.ins h3{font-weight:700;margin:1rem 0 .4rem}"
             ".ins .shot{margin-top:1rem}.muted{color:rgba(255,255,255,.45);font-weight:400}"
             ".toc{list-style:decimal;margin-left:1.2rem;columns:2;color:rgba(255,255,255,.7)}"
             ".toc a{color:#00d2ff;text-decoration:none}@media(max-width:640px){.toc{columns:1}}"
             ".ver{font-family:'JetBrains Mono',monospace;font-size:12px;padding:6px 14px;border-radius:999px;"
             "background:rgba(251,191,36,.12);border:1px solid rgba(251,191,36,.4);color:#fbbf24}"
             "section{scroll-margin-top:80px}</style>")
    return (style + '<main class="max-w-6xl mx-auto px-4 md:px-8 pt-28 pb-20">' + "\n".join(body) + "</main>")


def build():
    from nakazy import __version__
    assert VERSIONS[0][0] == __version__, f"Допишіть VERSIONS для {__version__}"
    shell = open(os.path.join(OUT, "_shell.html"), encoding="utf-8").read()
    desc = "Накази ШКОЛА: інструкція. Реєстр наказів закладу освіти, шаблони, бланк, журнали, відпустки."
    page = (shell.replace("{{TITLE}}", "Накази ШКОЛА: інструкція – ГС «УАІТ»").replace("{{DESC}}", desc)
            .replace("{{URL}}", URL).replace("{{MAIN}}", main_html(__version__, VERSIONS[0][1])))
    page = page.replace("<html lang=\"uk\">", f"<html lang=\"uk\" data-version=\"{__version__}\">", 1)
    open(os.path.join(OUT, "index.html"), "w", encoding="utf-8").write(page)
    print("сторінка:", os.path.join(OUT, "index.html"), __version__)


if __name__ == "__main__":
    if "noshots" not in sys.argv[1:]:
        shots()
    build()
