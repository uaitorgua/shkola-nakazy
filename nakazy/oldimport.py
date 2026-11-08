"""Імпорт наявних (архівних) наказів з DOCX, PDF і сканів – без ШІ.

Накази мають сталу структуру (Інструкція МОН № 676, р. III п. 1; дод. 1): «НАКАЗ», дата, «№ …»,
заголовок «Про…», «НАКАЗУЮ:», підпис. Реквізити шукаємо звичайними правилами (регулярні вирази);
скани читає офлайн-OCR Tesseract (з «Сканер ШКОЛА»). Кожне поле має позначку впевненості;
секретар перевіряє й виправляє таблицю перед записом.
"""
from __future__ import annotations

import datetime as dt
import html as h
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from .db import KIND_BY_CODE

SUPPORTED = (".docx", ".doc", ".rtf", ".odt", ".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".txt")
MONTHS = {"січня": 1, "лютого": 2, "березня": 3, "квітня": 4, "травня": 5, "червня": 6, "липня": 7,
          "серпня": 8, "вересня": 9, "жовтня": 10, "листопада": 11, "грудня": 12}
SUFFIX_KIND = {"у": "u", "к": "k", "в": "v", "г": "g", "": "osn"}
# латинські двійники кириличних літер у суфіксі (часто після OCR або ручного набору)
LAT = str.maketrans({"y": "у", "k": "к", "B": "в", "r": "г", "K": "к", "Y": "у"})
KIND_HINTS = [  # якщо суфікса немає: вид за словами заголовка (лише пропозиція)
    ("u", r"зарахуван|відрахуван|вибутт|переведенн[яі] учн|переведення до наступн|випуск учн|сімейн|екстернат"),
    ("v", r"відпустк"),
    ("k", r"прийнятт[яі] на робот|звільненн|переведенн[яі] .*на посад|покладанн[яі] обов|сумісництв|"
          r"класних керівник|педагогічного навантаженн|встановленн[яі] доплат"),
    ("g", r"інвентаризац|списанн[яі] майн|пожежн|ремонт|господарськ"),
]


@dataclass
class Parsed:
    path: str
    text: str = ""
    body_html: str = ""
    number: int | None = None
    suffix: str = ""
    date: str | None = None
    title: str = ""
    kind: str = "osn"
    signer: str = ""
    sure: dict[str, bool] = field(default_factory=dict)   # поле -> знайдено надійно
    source: str = ""          # docx | pdf-text | ocr | txt
    error: str = ""

    @property
    def reg_index(self) -> str:
        return f"{self.number}-{self.suffix}" if self.number and self.suffix else (str(self.number or ""))


# ---------- читання файлів ----------
def _ocr_ready():
    from shkola.ocr import engine
    if not engine.available():  # під час розробки моделі лежать у «Сканер ШКОЛА»
        alt = Path(__file__).resolve().parents[2] / "Сканер-ШКОЛА" / "ocr" / "tessdata"
        if alt.exists():
            engine.TESSDATA_DIR = alt
    return engine


def _ocr_images(images) -> str:
    engine = _ocr_ready()
    if not engine.available():
        raise RuntimeError("Немає моделей OCR (tessdata). Скан не прочитати; збережіть наказ як DOCX або PDF з текстом.")
    from shkola.ocr.structure import analyze
    out = []
    for img, dpi in images:
        page = engine.recognize(img, dpi=dpi)
        page.doc = analyze(page, img)
        out.append(page.text)
    return "\n".join(out)


def read_file(path: str) -> tuple[str, str, str]:
    """(текст, html, джерело)."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".doc", ".rtf", ".odt"):
        t, body, _src = read_file(convert_to_docx(path))
        return t, body, ext[1:]
    if ext == ".docx":
        from docx import Document
        d = Document(path)
        lines = [p.text for p in d.paragraphs]
        for t in d.tables:
            for r in t.rows:
                lines.append("\t".join(c.text for c in r.cells))
        try:
            from shkola.export.html_docx import docx_to_html
            res = docx_to_html(Path(path))
            body = res[0] if isinstance(res, tuple) else res
        except Exception:
            body = "".join(f"<p>{h.escape(x)}</p>" for x in lines)
        return "\n".join(lines), body, "docx"
    if ext == ".txt":
        raw = open(path, "rb").read()
        for enc in ("utf-8-sig", "cp1251"):
            try:
                t = raw.decode(enc); break
            except UnicodeDecodeError:
                continue
        return t, _html(t), "txt"
    if ext == ".pdf":
        from pypdf import PdfReader
        t = "\n".join((p.extract_text() or "") for p in PdfReader(path).pages)
        if len(re.sub(r"\s", "", t)) > 80:
            return t, _html(t), "pdf-text"
        from shkola.importing.loader import load_pdf
        t = _ocr_images([(pg.original, pg.dpi) for pg in load_pdf(Path(path))])
        return t, _html(t), "ocr"
    from PIL import Image
    img = Image.open(path)
    dpi = int((img.info.get("dpi") or (300, 300))[0]) or 300
    t = _ocr_images([(img.convert("RGB"), dpi)])
    return t, _html(t), "ocr"


def convert_to_docx(path: str) -> str:
    """Старі формати (.doc, .rtf, .odt) → тимчасовий DOCX через Word або LibreOffice (офлайн)."""
    import shutil
    import subprocess
    import tempfile
    out_dir = tempfile.mkdtemp()
    out = os.path.join(out_dir, os.path.splitext(os.path.basename(path))[0] + ".docx")
    try:
        import win32com.client  # type: ignore
        word = win32com.client.DispatchEx("Word.Application"); word.Visible = False
        try:
            d = word.Documents.Open(os.path.abspath(path), ReadOnly=True, ConfirmConversions=False)
            d.SaveAs2(out, FileFormat=16); d.Close(False)
            return out
        finally:
            word.Quit()
    except Exception:
        pass
    soffice = shutil.which("soffice") or next((p for p in (
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe") if os.path.exists(p)), None)
    if not soffice:
        raise RuntimeError("Для .doc/.rtf/.odt потрібен Microsoft Word або LibreOffice.")
    subprocess.run([soffice, "--headless", "--convert-to", "docx", "--outdir", out_dir, path],
                   check=True, capture_output=True, timeout=180)
    if not os.path.exists(out):
        raise RuntimeError("Не вдалося перетворити файл у DOCX.")
    return out


def _html(text: str) -> str:
    return "".join(f"<p>{h.escape(x.strip())}</p>" for x in text.splitlines() if x.strip())


# ---------- розбір реквізитів ----------
_NUM = re.compile(r"№\s*([0-9]{1,4})\s*(?:[-–/]\s*([А-Яа-яІіЇїЄєҐґA-Za-z]{1,3}))?(?![0-9])")
_NUM_OCR = re.compile(r"(?:^|\s)(?:N|No|Nº|Ne)\.?\s*([0-9]{1,4})\s*(?:[-–]\s*([А-Яа-яA-Za-z]{1,2}))?(?![0-9])")
_DATE = re.compile(r"(?<!\d)([0-3]?\d)[.,/]([01]?\d)[.,/]((?:19|20)\d\d)(?!\d)")
_DATE_W = re.compile(r"«?\s*([0-3]?\d)\s*»?\s+(" + "|".join(MONTHS) + r")\s+((?:19|20)\d\d)", re.I)


def _date(s: str) -> str | None:
    for m in _DATE.finditer(s):
        try:
            return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
        except ValueError:
            continue
    m = _DATE_W.search(s)
    if m:
        try:
            return dt.date(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1))).isoformat()
        except ValueError:
            return None
    return None


def parse(text: str) -> dict:
    lines = [re.sub(r"\s+", " ", x).strip() for x in text.splitlines()]
    lines = [x for x in lines if x]
    out = {"sure": {}}
    # шапка – до заголовка «Про…» або до 15-го рядка
    title_i = next((i for i, x in enumerate(lines[:40]) if re.match(r"^Про\s+\S", x)), None)
    head = lines[: (title_i if title_i is not None else 15)]
    head_txt = "\n".join(head)
    i_nakaz = next((i for i, x in enumerate(head) if re.fullmatch(r"Н\s*А\s*К\s*А\s*З", x.upper())), None)
    search_from = "\n".join(head[i_nakaz:]) if i_nakaz is not None else head_txt
    m = _NUM.search(search_from) or _NUM.search(head_txt)
    ocr_guess = False
    if not m:
        m = _NUM_OCR.search(search_from); ocr_guess = bool(m)
    if m:
        out["number"] = int(m.group(1))
        suf = (m.group(2) or "").translate(LAT).lower()
        out["suffix"] = suf if suf in SUFFIX_KIND else ""
        out["sure"]["number"] = not ocr_guess and (suf in SUFFIX_KIND)
    d = _date(search_from) or _date(head_txt)
    if d:
        out["date"] = d; out["sure"]["date"] = True
    else:
        d = _date("\n".join(lines[:60]))
        if d:
            out["date"] = d; out["sure"]["date"] = False
    if title_i is not None:
        t = [lines[title_i]]
        for x in lines[title_i + 1: title_i + 5]:  # заголовок у кількох рядках
            if re.match(r"^(Відповідно|На виконання|На підставі|З метою|У зв|Згідно|Керуючись|НАКАЗУЮ)", x) \
                    or len(" ".join(t)) > 250 or x.endswith((".", ":")):
                break
            t.append(x)
        out["title"] = " ".join(t).rstrip(" ,;")
        out["sure"]["title"] = True
    low = (out.get("title") or "").lower()
    hint = next((k for k, rx in KIND_HINTS if re.search(rx, low)), "osn")
    if out.get("suffix") and out.get("number"):
        out["kind"] = SUFFIX_KIND[out["suffix"]]; out["sure"]["kind"] = True
    elif out.get("number") and hint == "osn":  # без літери – основна діяльність (р. III п. 1)
        out["kind"] = "osn"; out["sure"]["kind"] = True
    else:  # без літери, але заголовок схожий на інший вид (старі архіви): пропозиція, перевірити
        out["kind"] = hint; out["sure"]["kind"] = False
    # підпис: «Директор   Ім'я ПРІЗВИЩЕ» у кінці
    for x in reversed(lines[-12:]):
        m = re.match(r"^(?:В\.?\s?о\.?\s+)?(Директор|Директорка|Керівник)\w*\s+(.{3,60})$", x, re.I)
        if m:
            out["signer"] = m.group(2).strip(); break
    out["sure"]["nakazuyu"] = any(x.upper().startswith("НАКАЗУЮ") for x in lines)
    return out


def parse_file(path: str) -> Parsed:
    p = Parsed(path=path)
    try:
        p.text, p.body_html, p.source = read_file(path)
    except Exception as e:
        p.error = str(e)
        return p
    info = parse(p.text)
    for k, v in info.items():
        setattr(p, k, v)
    if p.kind == "osn" and p.suffix:
        p.suffix = ""
    return p


def scan_folder(folder: str) -> list[str]:
    out = []
    for root, _dirs, files in os.walk(folder):
        for f in sorted(files):
            if f.lower().endswith(SUPPORTED) and not f.startswith("~$"):
                out.append(os.path.join(root, f))
    return out


def problems(p: Parsed) -> list[str]:
    msg = []
    if p.error:
        return [p.error]
    if not p.number:
        msg.append("номер не знайдено")
    if not p.date:
        msg.append("дату не знайдено")
    if not p.title:
        msg.append("заголовок «Про…» не знайдено")
    for f, name in (("number", "номер"), ("date", "дата"), ("kind", "вид")):
        if getattr(p, f, None) and not p.sure.get(f, False):
            msg.append(f"{name}: перевірити")
    if p.source == "ocr":
        msg.append("скан: звірити текст")
    return msg


def kind_title(code: str) -> str:
    return KIND_BY_CODE[code].title
