"""Перевірка оновлень лише через Microsoft Store.

Остання опублікована версія береться з каталогу Microsoft (displaycatalog.mp.microsoft.com).
Якщо вона новіша — програма вимагає оновитись і відкриває свою сторінку в Microsoft Store
(і для Store-копії, і для встановленої іншим способом). Наш сервер не використовується.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import urllib.request

from . import __version__

log = logging.getLogger(__name__)
PRODUCT_ID = "9PJNZB9R4HGK"
CATALOG_URL = os.environ.get(
    "NAKAZY_CATALOG_URL",          # лише для локальних тестів
    f"https://displaycatalog.mp.microsoft.com/v7.0/products/{PRODUCT_ID}?market=UA&languages=uk-ua,neutral")
STORE_URL = f"ms-windows-store://pdp/?productid={PRODUCT_ID}"
WEB_URL = f"https://apps.microsoft.com/detail/{PRODUCT_ID}"
PACKAGE_NAME = "UAIT.118389E8B5916"            # Package/Identity/Name у MSIX


def parse(v: str) -> tuple[int, ...]:
    t = tuple(int(x) for x in re.findall(r"\d+", str(v))[:4]) or (0,)
    return t + (0,) * (4 - len(t))


def is_newer(remote: str, local: str = __version__) -> bool:
    return parse(remote) > parse(local)


def is_store_install() -> bool:
    return r"\windowsapps" + "\\" in sys.executable.lower()


def latest_version(timeout: float = 8) -> str | None:
    """Найвища версія пакета цієї програми, опублікована в Microsoft Store."""
    req = urllib.request.Request(CATALOG_URL, headers={"User-Agent": "NakazyShkola/" + __version__})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 – лише каталог Microsoft
        data = json.loads(r.read(5_000_000).decode("utf-8"))
    names = re.findall(r'"PackageFullName"\s*:\s*"([^"]+)"', json.dumps(data))
    vers = [m.group(1) for n in names if n.startswith(PACKAGE_NAME + "_")
            for m in [re.match(re.escape(PACKAGE_NAME) + r"_(\d+\.\d+\.\d+\.\d+)_", n)] if m]
    return max(vers, key=parse) if vers else None


def check(timeout: float = 8) -> dict | None:
    """{"version": …}, якщо в Microsoft Store є новіша версія; інакше (або без мережі) None."""
    try:
        v = latest_version(timeout)
        return {"version": v} if v and is_newer(v) else None
    except Exception as e:  # noqa: BLE001
        log.info("Оновлення: каталог Microsoft Store недоступний (%s)", e)
        return None
