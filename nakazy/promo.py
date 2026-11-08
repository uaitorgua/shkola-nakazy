"""Блок «Курси УАІТ»: вшитий перелік + оновлення з сайту + локальний кеш свіжого.

Порядок:
1. Показуємо найсвіжіше з наявного офлайн: кеш %APPDATA%\\nakazy-shkola\\promo_cache.json (якщо
   новіший за вшитий) або вшитий promo/courses.json.
2. У фоні (без блокування, тайм-аут 6 с) беремо courses.json із сайту.
3. Якщо отримане коректне й новіше (поле «updated» або інший вміст) – атомарно зберігаємо в кеш
   і показуємо. Далі воно доступне й без мережі.
Посилання з мережі приймаються лише https і лише на сайти УАІТ (захист від підміни).
"""
from __future__ import annotations

import json
import logging
import os
from urllib.parse import urlparse

from shkola.config import resource_dir

from .db import default_db_path

log = logging.getLogger(__name__)
BUNDLED = resource_dir() / "promo" / "courses.json"
ONLINE = "https://uait.org.ua/skaner/courses.json"
ALL_COURSES_URL = "https://uait.org.ua/skaner/"
ALLOWED_HOSTS = ("uait.org.ua", "vector.uied.gov.ua")  # сайт УАІТ і платформа «Вектор»


def cache_path() -> str:
    return os.path.join(os.path.dirname(default_db_path()), "promo_cache.json")


def valid(data) -> bool:
    if not isinstance(data, dict) or not isinstance(data.get("courses"), list) or not data["courses"]:
        return False
    for c in data["courses"]:
        if not isinstance(c, dict) or not str(c.get("name", "")).strip():
            return False
        url = c.get("url")
        if url:
            u = urlparse(str(url))
            host = u.hostname or ""
            if u.scheme != "https" or not any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS):
                return False
    return True


def _read(path) -> dict | None:
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        return d if valid(d) else None
    except (OSError, ValueError):
        return None


def load_offline() -> dict:
    """Найсвіжіше без мережі: кеш, якщо він не старший за вшитий, інакше вшитий."""
    bundled = _read(BUNDLED) or {"courses": []}
    cached = _read(cache_path())
    if cached and str(cached.get("updated", "")) >= str(bundled.get("updated", "")):
        return cached
    return bundled


def is_newer(new: dict, cur: dict) -> bool:
    nu, cu = str(new.get("updated", "")), str(cur.get("updated", ""))
    if nu != cu:
        return nu > cu
    return json.dumps(new, sort_keys=True, ensure_ascii=False) != json.dumps(cur, sort_keys=True, ensure_ascii=False)


def save_cache(data: dict) -> bool:
    if not valid(data):
        return False
    path = cache_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)  # атомарно: обрив живлення не залишить зіпсований кеш
    return True


def fetch(url: str = ONLINE, timeout: float = 6) -> dict | None:
    import urllib.request
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "NakazyShkola"})
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 – лише https uait.org.ua
            if r.status != 200 or int(r.headers.get("Content-Length") or 0) > 1_000_000:
                return None
            d = json.loads(r.read(1_000_001).decode("utf-8"))
        return d if valid(d) else None
    except Exception:
        log.info("Курси УАІТ: сайт недоступний, показуємо збережене")
        return None


def refresh(current: dict, fetcher=fetch) -> dict | None:
    """Повертає нові дані (і зберігає їх у кеш), якщо на сайті оновилось; інакше None."""
    new = fetcher()
    if new and is_newer(new, current):
        save_cache(new)
        return new
    return None
