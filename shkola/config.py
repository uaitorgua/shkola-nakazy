"""Сталі застосунку: назви, шляхи, типові значення."""

import os
import sys
from pathlib import Path

APP_NAME = "Накази ШКОЛА"
APP_ID = "nakazy-shkola"
INTERTEXT = "InterText"      # субдодаток: редактор документів (DOCX)
INTERTAB = "InterTab"        # субдодаток: табличний редактор (XLSX)
ORG_NAME = "Комунальні заклади освіти України"
ORG_SHORT = "ШКОЛА"
PUBLISHER = "ГС «УАІТ»"
PUBLISHER_FULL = "Громадська спілка «Українська асоціація інноваційних технологій»"
PUBLISHER_SITE = "https://uait.org.ua"
CO_DEVELOPER_FULL = ("Дрогобицький науковий ліцей імені Богдана Лепкого "
                     "Дрогобицької міської ради Львівської області")
CO_DEVELOPER_SITE = "https://dnl.net.ua"
DEVELOPERS_LINE = f"{PUBLISHER_FULL}; {CO_DEVELOPER_FULL}"


def resource_dir() -> Path:
    """Тека з ресурсами (працює і з джерел, і з PyInstaller-збірки)."""
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) if base else Path(__file__).resolve().parent.parent


ASSETS = resource_dir() / "assets"
LOGO_SVG = ASSETS / "logo.svg"
LOGO_PNG = ASSETS / "logo.png"
ICON_ICO = ASSETS / "logo.ico"

# Офлайн-моделі розпізнавання (tools/get_ocr.py; у EXE — всередині пакета)
OCR_DIR = resource_dir() / "ocr"
TESSDATA_DIR = OCR_DIR / "tessdata"
LATEX_MODEL_DIR = OCR_DIR / "latex"
FONT_TTF = OCR_DIR / "fonts" / "DejaVuSans.ttf"       # шрифт для текстового шару PDF
OCR_LANGS = "ukr+eng"

DATA_DIR = Path(os.environ.get("APPDATA", Path.home())) / APP_ID
DATA_DIR.mkdir(parents=True, exist_ok=True)
SETTINGS_FILE = DATA_DIR / "settings.json"
LOG_FILE = DATA_DIR / "skaner.log"

DEFAULT_OUTPUT_DIR = Path.home() / "Documents" / "Скани ШКОЛА"

DPI_CHOICES = (75, 100, 150, 200, 300, 400, 600, 1200)
DEFAULT_DPI = 300

# Розміри паперу в міліметрах
PAPER_SIZES = {
    "A4": (210.0, 297.0),
    "A5": (148.0, 210.0),
    "A3": (297.0, 420.0),
    "Letter": (215.9, 279.4),
    "Legal": (215.9, 355.6),
    "Уся площа": (0.0, 0.0),
}

# Шаблони для автовизначення формату відсканованого документа (мм, книжкова орієнтація)
TEMPLATES = {
    "A3": (297.0, 420.0),
    "A4": (210.0, 297.0),
    "A5": (148.0, 210.0),
    "A6": (105.0, 148.0),
    "Зошит (A5)": (148.0, 210.0),
    "Свідоцтво / атестат (A4)": (210.0, 297.0),
    "Додаток до свідоцтва (A5)": (148.0, 210.0),
    "ID-картка / учнівський квиток": (54.0, 85.6),
    "Фото 13×18": (130.0, 180.0),
    "Фото 10×15": (100.0, 150.0),
    "Фото 9×13": (90.0, 130.0),
    "Letter": (215.9, 279.4),
}
TEMPLATE_TOLERANCE = 0.06     # допустиме відхилення сторін, частка

CONNECT_TIMEOUT_S = 3.0
