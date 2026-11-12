"""Курси УАІТ: вшите без мережі, свіже з сайту зберігається й показується далі без мережі."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nakazy import promo  # noqa: E402

GOOD = {"updated": "2099-01-01", "courses": [{"name": "Новий курс", "url": "https://uait.org.ua/k/1"}]}


class Promo(unittest.TestCase):
    def setUp(self):
        if os.path.exists(promo.cache_path()):
            os.remove(promo.cache_path())

    def test_offline_uses_bundled(self):
        d = promo.load_offline()
        self.assertTrue(d["courses"])
        self.assertIsNone(promo.refresh(d, fetcher=lambda: None))      # мережі немає
        self.assertFalse(os.path.exists(promo.cache_path()))

    def test_fresh_saved_and_used_offline(self):
        cur = promo.load_offline()
        new = promo.refresh(cur, fetcher=lambda: GOOD)
        self.assertEqual(new["courses"][0]["name"], "Новий курс")
        self.assertEqual(promo.load_offline()["courses"][0]["name"], "Новий курс")   # без мережі – свіже
        self.assertIsNone(promo.refresh(promo.load_offline(), fetcher=lambda: GOOD))  # без змін – не пишемо

    def test_older_cache_ignored_after_app_update(self):
        promo.save_cache({"updated": "2000-01-01", "courses": [{"name": "Старе"}]})
        self.assertNotEqual(promo.load_offline()["courses"][0]["name"], "Старе")   # вшите новіше

    def test_bad_data_rejected(self):
        for bad in [None, {}, {"courses": []}, {"courses": [{"name": ""}]},
                    {"courses": [{"name": "x", "url": "http://uait.org.ua/"}]},
                    {"courses": [{"name": "x", "url": "https://evil.example/"}]}]:
            self.assertFalse(promo.valid(bad))
            self.assertIsNone(promo.refresh(promo.load_offline(), fetcher=lambda b=bad: b if promo.valid(b) else None))
        with open(promo.cache_path(), "w", encoding="utf-8") as fh:
            fh.write("{зіпсований")
        self.assertTrue(promo.load_offline()["courses"])                         # зіпсований кеш – вшите

    def test_panel(self):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        promo.save_cache(GOOD)
        from nakazy.ui.promo_panel import PromoPanel
        p = PromoPanel(online=False); p.show(); app.processEvents()
        self.assertEqual(p.courses()[0]["name"], "Новий курс")


from qt_cleanup import tearDownModule  # noqa: E402,F401

if __name__ == "__main__":
    unittest.main()
