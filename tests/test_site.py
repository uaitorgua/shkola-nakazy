"""Інструкція на сайті прив'язана до версії: сторінка promo/site/index.html згенерована для поточної версії,
у «Що нового» є запис про неї, кнопки головного вікна з інструкції існують у програмі, знімки на місці.
Якщо тест падає після підняття версії: допишіть VERSIONS у tools/site.py і запустіть python tools\site.py."""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from nakazy import __version__  # noqa: E402

PAGE = os.path.join(ROOT, "promo", "site", "index.html")


class SiteTest(unittest.TestCase):
    def test_page_matches_version(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("nakazy_site", os.path.join(ROOT, "tools", "site.py"))
        gen = importlib.util.module_from_spec(spec); spec.loader.exec_module(gen)
        self.assertEqual(gen.VERSIONS[0][0], __version__, "немає запису «Що нового» для поточної версії")
        page = open(PAGE, encoding="utf-8").read()
        self.assertIn(f'data-version="{__version__}"', page, "сторінку не перегенеровано: python tools\site.py")
        self.assertIn(f"Інструкція до версії {__version__}", page)
        self.assertEqual(page.count("{{"), 0)
        self.assertNotIn("—", page.split("<main")[1].split("</main>")[0], "довге тире в тексті інструкції")
        for img in set(re.findall(r'src="img/([^"?]+)', page)):
            self.assertTrue(os.path.exists(os.path.join(ROOT, "promo", "site", "img", img)), img)

    def test_buttons_exist(self):
        """Кнопки, названі в інструкції «…», є в головному вікні (інструкція не відстає від програми)."""
        src = open(os.path.join(ROOT, "nakazy", "ui", "main_window.py"), encoding="utf-8").read()
        page = open(PAGE, encoding="utf-8").read()
        for label in ("Новий наказ", "Зареєструвати", "Наказ про зміни", "Скасувати", "Зберегти DOCX/PDF…",
                      "Журнал…", "Справи…", "Перевірка", "Нагадування…", "Люди…", "Графік відпусток…", "Імпорт наказів…", "Дані й копії…", "Заклад…"):
            self.assertIn(f'"{label}"', src, label)
            self.assertIn(label, page, label)


if __name__ == "__main__":
    unittest.main()
