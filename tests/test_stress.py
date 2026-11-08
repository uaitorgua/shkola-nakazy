"""Монте-Карло, краш-тест і перевірка аудитором.

Запуск: python tests/test_stress.py  (MC_STEPS=5000 для довшого прогону)
"""
import datetime as dt
import os
import random
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from nakazy.audit import audit  # noqa: E402
from nakazy.db import KINDS, Database, OrderLocked, RegistrationError  # noqa: E402
from nakazy.templates import TEMPLATES, render  # noqa: E402

BODY = "<p>…</p><p>НАКАЗУЮ:</p><p>1. …</p>"
NASTY = ["", "Про", "Про ' OR 1=1; --", 'Про "лапки" і «ялинки»', "Про <b>тег</b> &amp;", "Про \x00нуль",
         "Про " + "дуже довгий " * 500, "Про AND OR NOT NEAR*", "Про ‘апостроф’ та м'ясо", "Про 😀 емодзі"]


def errors(db, today):
    return [t for lvl, t in audit(db, today) if lvl == "помилка"]


class MonteCarlo(unittest.TestCase):
    def test_random_operations(self):
        steps = int(os.environ.get("MC_STEPS", "1500"))
        for seed in (1, 2, 3):
            rnd = random.Random(seed)
            d = tempfile.mkdtemp()
            db = Database(os.path.join(d, "mc.db"))
            today = dt.date(2027, 12, 31)
            last_date = {}
            for step in range(steps):
                op = rnd.choices(["new", "edit", "reg", "cancel", "amend", "del", "att", "search", "revert"],
                                 [25, 15, 25, 4, 4, 6, 6, 10, 5])[0]
                ids = [r["id"] for r in db.list_orders()]
                pick = rnd.choice(ids) if ids else None
                try:
                    if op == "new":
                        t = rnd.choice(TEMPLATES)
                        title, body = render(t, {k: rnd.choice(NASTY) for k, _ in t.fields})
                        db.create_draft(rnd.choice(KINDS).code, title=rnd.choice([title, rnd.choice(NASTY)]),
                                        body_html=rnd.choice([body, BODY, ""]),
                                        signer=rnd.choice(["О. ПЕТРЕНКО", "", " "]))
                    elif op == "edit" and pick:
                        db.update_draft(pick, title=rnd.choice(NASTY + ["Про зміну"]),
                                        kind=rnd.choice(KINDS).code, signer="О. ПЕТРЕНКО", body_html=BODY)
                    elif op == "reg" and pick:
                        date = dt.date(rnd.choice([2026, 2027]), 1, 1) + dt.timedelta(days=rnd.randint(0, 364))
                        idx = db.register(pick, date.isoformat())
                        k = db.get(pick)["kind"]
                        self.assertGreaterEqual(date, last_date.get((k, date.year), date))
                        last_date[(k, date.year)] = date
                        self.assertTrue(idx)
                    elif op == "cancel" and pick:
                        db.cancel(pick, "тест")
                    elif op == "amend" and pick:
                        db.create_amendment(pick)
                    elif op == "del" and pick:
                        db.delete_draft(pick)
                    elif op == "att" and pick:
                        db.add_attachment(pick, rnd.choice(NASTY), rnd.choice(["text", "file"]), data=b"x")
                    elif op == "search":
                        db.list_orders(query=rnd.choice(NASTY + ["харч", "НАКАЗУЮ", '"', "*", "(", "-"]))
                    elif op == "revert" and pick:
                        v = db.versions(pick)
                        if v:
                            db.revert_to_version(v[0]["id"])
                except (OrderLocked, RegistrationError):
                    pass
                if step % 250 == 0:
                    self.assertEqual(errors(db, today), [], f"seed {seed}, крок {step}")
            self.assertEqual(errors(db, today), [], f"seed {seed}")
            db.close()


CRASH_WORKER = r"""
import sys, random, datetime as dt
sys.path.insert(0, sys.argv[2])
from nakazy.db import Database, RegistrationError
db = Database(sys.argv[1])
d = dt.date(2026, 1, 1)
i = 0
while True:
    i += 1
    oid = db.create_draft(random.choice(["osn", "u", "k"]), title=f"Про {i}", body_html="<p>НАКАЗУЮ:</p>",
                          signer="О. П.")
    try:
        db.register(oid, (d + dt.timedelta(days=min(i // 50, 360))).isoformat())
    except RegistrationError:
        pass
"""


class Crash(unittest.TestCase):
    def test_kill_during_registration(self):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "crash.db")
        script = os.path.join(d, "w.py")
        with open(script, "w", encoding="utf-8") as f:
            f.write(CRASH_WORKER)
        Database(path).close()
        for round_ in range(6):
            p = subprocess.Popen([sys.executable, script, path, ROOT])
            time.sleep(0.6 + round_ * 0.15)
            p.kill(); p.wait()
            db = Database(path)
            errs = errors(db, dt.date(2027, 1, 1))
            n = db.con.execute("SELECT COUNT(*) FROM orders WHERE number IS NOT NULL").fetchone()[0]
            db.close()
            self.assertEqual(errs, [], f"раунд {round_}")
        self.assertGreater(n, 0)


class Auditor(unittest.TestCase):
    """Аудитор знаходить підкладені порушення (база змінена в обхід програми)."""

    def test_detects_tampering(self):
        d = tempfile.mkdtemp()
        db = Database(os.path.join(d, "a.db"))
        for i in range(5):
            db.register(db.create_draft("osn", title=f"Про {i}", body_html=BODY, signer="О. П."),
                        f"2026-02-0{i + 1}")
        today = dt.date(2026, 12, 1)
        self.assertEqual(errors(db, today), [])
        db.con.execute("DELETE FROM orders WHERE number = 3")
        db.con.execute("UPDATE orders SET date = '2026-01-15' WHERE number = 5")
        db.con.execute("UPDATE orders SET signer = '' WHERE number = 4")
        found = " | ".join(errors(db, today))
        self.assertIn("пропуски", found)
        self.assertIn("раніше", found)
        self.assertIn("підписанта", found)
        self.assertIn("індекс неповний", found)


if __name__ == "__main__":
    unittest.main()
