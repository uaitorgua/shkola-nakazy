"""Збереження налаштувань користувача у JSON."""

import json
import logging

from ..config import DEFAULT_OUTPUT_DIR, SETTINGS_FILE

log = logging.getLogger(__name__)

DEFAULTS = {
    "last_scanner": "",
    "manual_hosts": [],          # ["192.168.1.50", "10.0.0.7:8080"]
    "dpi": 300,
    "color": "Кольоровий",
    "source": "Планшет",
    "paper": "A4",
    "output_dir": str(DEFAULT_OUTPUT_DIR),
    "file_prefix": "скан",
    "jpeg_quality": 85,
    "auto_on_scan": {"autoformat": True, "auto_levels": False},
}


class SettingsStore:
    def __init__(self) -> None:
        self.data = dict(DEFAULTS)
        try:
            if SETTINGS_FILE.exists():
                self.data.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
        except Exception:  # пошкоджений файл не повинен ламати запуск
            log.exception("Не вдалося прочитати налаштування")

    def get(self, key, default=None):
        return self.data.get(key, DEFAULTS.get(key, default))

    def set(self, key, value) -> None:
        self.data[key] = value
        self.save()

    def save(self) -> None:
        try:
            SETTINGS_FILE.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            log.exception("Не вдалося зберегти налаштування")
