"""Вікно «Про програму»: вкладки Про програму / Розробники / Ліцензія / Конфіденційність."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QTabWidget, QTextBrowser, QVBoxLayout, QWidget

from .. import __version__
from ..config import (APP_NAME, CO_DEVELOPER_FULL, CO_DEVELOPER_SITE, DEVELOPERS_LINE, LOG_FILE, ORG_NAME,
                      PUBLISHER_FULL, PUBLISHER_SITE, resource_dir)
from .logo import logo_pixmap

CONTACT = "admin@uait.org.ua"

PRIVACY = f"""<h3>Політика конфіденційності</h3>
<p>«{APP_NAME}» не збирає, не зберігає на серверах і не передає третім особам жодних персональних даних,
відсканованих документів чи розпізнаного тексту.</p>
<ul>
<li>Скани й розпізнавання обробляються лише на комп'ютері користувача (офлайн) і зберігаються тільки в теці, яку він обрав.</li>
<li>Мережа використовується для зв'язку зі сканерами в локальній мережі та для оновлення переліку курсів УАІТ (один запит до uait.org.ua при запуску, без будь-яких даних користувача).</li>
<li>Налаштування й журнал роботи зберігаються локально: <code>{LOG_FILE.parent}</code>.</li>
<li>Програма не містить реклами, аналітики та телеметрії.</li>
</ul>
<p>Питання: <a href="mailto:{CONTACT}">{CONTACT}</a></p>"""


def _text(html: str) -> QTextBrowser:
    t = QTextBrowser()
    t.setOpenExternalLinks(True)
    t.setHtml(html)
    return t


def _license_html(path) -> str:
    """Абзаци ліцензії як HTML: рядки всередині абзацу зливаються, тож текст переноситься рівно."""
    import html
    if not path.exists():
        return ""
    paras = [" ".join(p.split()) for p in path.read_text(encoding="utf-8").split("\n\n") if p.strip()]
    head, body = paras[0], paras[1:]
    return f"<h3>{html.escape(head)}</h3>" + "".join(f"<p>{html.escape(p)}</p>" for p in body)


class AboutDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Про програму")
        tabs = QTabWidget()
        tabs.addTab(self._about(), "Про програму")
        tabs.addTab(_text(
            "<h3>Розробники</h3>"
            f"<p><b>{PUBLISHER_FULL}</b><br>"
            f"<a href='{PUBLISHER_SITE}'>{PUBLISHER_SITE}</a> · <a href='mailto:{CONTACT}'>{CONTACT}</a></p>"
            f"<p><b>{CO_DEVELOPER_FULL}</b><br>"
            f"<a href='{CO_DEVELOPER_SITE}'>{CO_DEVELOPER_SITE}</a></p>"
            f"<p>Розроблено для: <b>{ORG_NAME}</b></p>"
            "<h4>Використані компоненти з відкритим кодом</h4>"
            "<ul><li>Tesseract OCR 5 (Apache 2.0), tesserocr (MIT), мовні моделі tessdata (Apache 2.0)</li>"
            "<li>RapidLaTeXOCR (MIT) — розпізнавання формул; ONNX Runtime (MIT); HuggingFace tokenizers (Apache 2.0)</li>"
            "<li>Qt for Python (PySide6) — LGPLv3</li><li>Pillow — HPND · NumPy — BSD · OpenCV — Apache 2.0</li>"
            "<li>python-docx — MIT · openpyxl — MIT · reportlab — BSD · шрифт DejaVu — вільна ліцензія</li>"
            "<li>Іконки Font Awesome Free — CC BY 4.0, шрифт — SIL OFL 1.1 (fontawesome.com)</li>"
            "<li>pypdfium2 / PDFium — Apache 2.0 / BSD · requests — Apache 2.0 · python-zeroconf — LGPL · pywin32 — PSF</li></ul>"), "Розробники")
        lic = resource_dir() / "LICENSE.txt"
        tabs.addTab(_text(_license_html(lic)), "Ліцензія")
        tabs.addTab(_text(PRIVACY), "Конфіденційність")
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        bb.accepted.connect(self.accept)
        lay = QVBoxLayout(self)
        lay.addWidget(tabs)
        lay.addWidget(bb)
        self.resize(660, 500)

    @staticmethod
    def _about() -> QWidget:
        w = QWidget()
        logo = QLabel()
        logo.setPixmap(logo_pixmap(96))
        text = QLabel(
            f"<h3>{APP_NAME} {__version__}</h3><p><b>{ORG_NAME}</b></p>"
            "<p>Сканування з USB- і мережних сканерів (WIA, eSCL/AirScan), пакети документів, завантаження PDF і "
            "зображень, автоформат і корекція. <b>Розпізнавання тексту</b> українською та англійською офлайн, "
            "<b>розпізнавання формул</b> (LaTeX), визначення заголовків, списків і таблиць. "
            "Збереження в PDF (зокрема з текстовим шаром), DOCX, XLSX, TXT, PNG, JPEG, TIFF. "
            "Вбудовані <b>редактор документів</b> і <b>табличний редактор</b>.</p>"
            f"<p>Розробники: {DEVELOPERS_LINE}</p>")
        text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row = QHBoxLayout(w)
        row.addWidget(logo, 0, Qt.AlignmentFlag.AlignTop)
        row.addWidget(text, 1)
        return w
