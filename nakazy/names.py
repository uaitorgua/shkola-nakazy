"""Відмінювання українських ПІБ (родовий, давальний, знахідний) за поширеними правилами.

Результат – пропозиція: у картці людини будь-яку форму можна виправити вручну.
Невідмінювані випадки: жіночі прізвища на приголосний і на -о (Коваль, Шевченко у жінок).
"""
from __future__ import annotations

CASES = ("nom", "gen", "dat", "acc")
CASE_TITLES = {"nom": "називний", "gen": "родовий", "dat": "давальний", "acc": "знахідний"}
_HARD_G = "жчшщ"  # після них у род. відм. на -а пишемо -і (Саші), інакше -и (Ольги)
_ALT = {"г": "з", "к": "ц", "х": "с"}  # чергування в дав. відм.: Ольга – Ользі


def guess_sex(first: str, middle: str = "") -> str:
    m = (middle or "").lower()
    if m.endswith(("ович", "евич", "йович", "ич")):
        return "m"
    if m.endswith(("івна", "ївна", "овна", "евна", "на")):
        return "f"
    f = (first or "").lower()
    if f.endswith(("а", "я")) and f not in ("микола", "кузьма", "ілля", "сава", "фома", "лука"):
        return "f"
    return "m"


def _cap(src: str, out: str) -> str:
    return out.upper() if src.isupper() and len(src) > 1 else out


def _word(w: str, case: str, sex: str, part: str) -> str:
    if case == "nom" or not w:
        return w
    if "-" in w:  # подвійні: Петренко-Коваль
        return "-".join(_word(x, case, sex, part) for x in w.split("-"))
    lo = w.lower()

    def r(cut: int, add: str) -> str:
        return _cap(w, (w[:-cut] if cut else w) + add)

    if sex == "f":
        if part == "last":
            if lo.endswith(("ська", "цька", "зька")):
                return r(1, {"gen": "ої", "dat": "ій", "acc": "у"}[case])
            if lo.endswith(("ова", "єва", "іна", "їна", "ина")):
                return r(1, {"gen": "ої", "dat": "ій", "acc": "у"}[case])
            if lo.endswith("а"):
                pass  # далі як іменник на -а
            elif lo.endswith("я"):
                pass
            else:
                return w  # Коваль, Шевченко, Мельник у жінок не відмінюються
        if part == "middle" and lo.endswith("на"):
            return r(1, {"gen": "и", "dat": "і", "acc": "у"}[case])
        if lo.endswith("ія"):
            return r(1, {"gen": "ї", "dat": "ї", "acc": "ю"}[case])
        if lo.endswith("я"):
            return r(1, {"gen": "і", "dat": "і", "acc": "ю"}[case])
        if lo.endswith("а"):
            prev = lo[-2] if len(lo) > 1 else ""
            if case == "gen":
                return r(1, "і" if prev in _HARD_G else "и")
            if case == "dat":
                return (_cap(w, w[:-2] + _ALT[prev] + "і") if prev in _ALT else r(1, "і"))
            return r(1, "у")
        return w
    # чоловічі
    gen_acc = case in ("gen", "acc")
    if part == "last" and lo.endswith(("ський", "цький", "зький", "ий")):
        return r(2, "ого" if gen_acc else "ому")
    if part == "last" and lo.endswith("ій"):
        return r(2, "ього" if gen_acc else "ьому")
    if lo.endswith("ич"):
        return r(0, "а" if gen_acc else "у")
    if lo.endswith(("ко", "о")):
        return r(1, "а" if gen_acc else ("у" if part == "last" else "ові"))
    if lo.endswith("а"):  # Микола, Кузьма
        prev = lo[-2] if len(lo) > 1 else ""
        if case == "gen":
            return r(1, "і" if prev in _HARD_G else "и")
        if case == "dat":
            return (_cap(w, w[:-2] + _ALT[prev] + "і") if prev in _ALT else r(1, "і"))
        return r(1, "у")
    if lo.endswith("я"):  # Ілля
        return r(1, {"gen": "і", "dat": "і", "acc": "ю"}[case])
    if lo.endswith("ець") and len(lo) > 4:  # Кравець – Кравця (випадний е)
        return r(3, "ця" if gen_acc else "цю")
    if lo.endswith("й"):  # Андрій, Олексій
        return r(1, "я" if gen_acc else "ю")
    if lo.endswith("ь"):  # Василь, Коваль
        return r(1, "я" if gen_acc else ("ю" if part == "last" else "еві"))
    if lo[-1] in "бвгґджзклмнпрстфхцчшщ":
        if gen_acc:
            return r(0, "а")
        return r(0, "у" if part == "last" and lo.endswith(("ук", "юк", "ак", "як", "ик", "ок")) else "ові")
    return w


def decline(last: str, first: str, middle: str, case: str, sex: str | None = None) -> str:
    sex = sex or guess_sex(first, middle)
    parts = [_word(last, case, sex, "last"), _word(first, case, sex, "first"), _word(middle, case, sex, "middle")]
    return " ".join(p for p in parts if p)


def all_cases(last: str, first: str, middle: str, sex: str | None = None) -> dict[str, str]:
    return {c: decline(last, first, middle, c, sex) for c in CASES}


def initials(last: str, first: str, middle: str = "") -> str:
    """«О. Іваненко»: ініціали перед прізвищем (як у прикладах № 676)."""
    ini = "".join(f"{x[0]}. " for x in (first, middle) if x)
    return f"{ini}{last}".strip()


def split_full(full: str) -> tuple[str, str, str]:
    p = (full or "").split()
    return (p[0] if p else "", p[1] if len(p) > 1 else "", " ".join(p[2:]))
