"""Перетворення HTML редактора (QTextDocument.toHtml) → DOCX і DOCX → HTML (для відкриття в редакторі).

Підтримка: абзаци, заголовки h1–h3, жирний/курсив/підкреслений/закреслений, верхній/нижній індекс, шрифт,
розмір, колір тексту й тла, вирівнювання, відступи, списки, таблиці (з об'єднаними комірками по стовпцях),
зображення, розрив сторінки.
"""

from __future__ import annotations

import html as _html
import io
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

from docx import Document as DocxDocument
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.shared import Inches, Pt, RGBColor

_ALIGN = {"left": WD_ALIGN_PARAGRAPH.LEFT, "center": WD_ALIGN_PARAGRAPH.CENTER,
          "right": WD_ALIGN_PARAGRAPH.RIGHT, "justify": WD_ALIGN_PARAGRAPH.JUSTIFY}
_COLOR_NAMES = {"black": "#000000", "red": "#ff0000", "blue": "#0000ff", "green": "#008000", "white": "#ffffff",
                "yellow": "#ffff00", "gray": "#808080", "grey": "#808080"}


@dataclass
class _Style:
    b: bool = False
    i: bool = False
    u: bool = False
    s: bool = False
    sup: bool = False
    sub: bool = False
    size: float | None = None
    font: str | None = None
    color: str | None = None
    bg: str | None = None

    def copy(self) -> "_Style":
        return _Style(**self.__dict__)


@dataclass
class _Run:
    text: str = ""
    style: _Style = field(default_factory=_Style)
    image: str | None = None       # назва ресурсу зображення
    width: int = 0


@dataclass
class _Para:
    kind: str = "p"
    align: str = "left"
    indent: int = 0
    first_line_px: float = 0.0
    margin_left_px: float = 0.0
    margin_right_px: float = 0.0
    line_height: float = 0.0        # відсотки (150 = 1,5)
    page_break: bool = False
    runs: list = field(default_factory=list)


@dataclass
class _Table:
    rows: list = field(default_factory=list)      # list[list[tuple[list[_Para], colspan]]]


def _css(st: str) -> dict[str, str]:
    out = {}
    for part in st.split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip().lower()] = v.strip()
    return out


def _hex(c: str | None) -> str | None:
    if not c:
        return None
    c = c.strip().lower()
    c = _COLOR_NAMES.get(c, c)
    m = re.match(r"rgba?\((\d+),\s*(\d+),\s*(\d+)", c)
    if m:
        return "#%02x%02x%02x" % tuple(int(x) for x in m.groups())
    return c if re.fullmatch(r"#[0-9a-f]{6}", c) else None


class _Parser(HTMLParser):
    """Лінійний список блоків: _Para або _Table."""

    def __init__(self):
        super().__init__()
        self.blocks: list = []
        self.cur: _Para | None = None
        self.style: list[_Style] = [_Style()]
        self.list_stack: list[str] = []
        self.table: _Table | None = None
        self.cell: list[_Para] | None = None
        self.in_body = False
        self.pending_break = False
        self.tstack: list[str] = []          # вкладеність таблиць: "root" (рамка сторінки Qt) або "table"

    def _style_from(self, attrs, base: _Style) -> tuple[_Style, dict]:
        a = dict(attrs)
        css = _css(a.get("style", "") or "")
        s = base.copy()
        fw = css.get("font-weight", "")
        if fw in ("bold", "600", "700", "800", "900"):
            s.b = True
        if css.get("font-style") == "italic":
            s.i = True
        td = css.get("text-decoration", "")
        if "underline" in td:
            s.u = True
        if "line-through" in td:
            s.s = True
        va = css.get("vertical-align", "")
        if va == "super":
            s.sup = True
        elif va == "sub":
            s.sub = True
        m = re.match(r"([\d.]+)pt", css.get("font-size", ""))
        if m:
            s.size = float(m.group(1))
        ff = css.get("font-family", "")
        if ff:
            s.font = ff.split(",")[0].strip("'\" ")
        if _hex(css.get("color")):
            s.color = _hex(css.get("color"))
        if _hex(css.get("background-color")):
            s.bg = _hex(css.get("background-color"))
        return s, css

    def _open_para(self, kind, css, align):
        p = _Para(kind, align or css.get("text-align", "left") or "left")
        m = re.match(r"(\d+)", css.get("-qt-block-indent", "0"))
        p.indent = int(m.group(1)) if m else 0
        m = re.match(r"(-?[\d.]+)px", css.get("text-indent", ""))
        p.first_line_px = float(m.group(1)) if m else 0.0
        for key in ("margin-left", "margin-right"):
            m = re.match(r"([\d.]+)px", css.get(key, ""))
            setattr(p, key.replace("-", "_") + "_px", float(m.group(1)) if m else 0.0)
        m = re.match(r"([\d.]+)%", css.get("line-height", ""))
        p.line_height = float(m.group(1)) if m else 0.0
        if self.pending_break or "page-break-before" in css:
            p.page_break = True
            self.pending_break = False
        self.cur = p
        if self.cell is not None:
            self.cell.append(p)
        else:
            self.blocks.append(p)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        s, css = self._style_from(attrs, self.style[-1])
        if tag == "body":
            self.in_body = True
        elif tag in ("p", "h1", "h2", "h3", "h4", "li"):
            kind = tag
            if tag == "li":
                kind = "oli" if self.list_stack and self.list_stack[-1] == "ol" else "li"
            self._open_para(kind, css, a.get("align"))
            self.style.append(s)
        elif tag in ("ul", "ol"):
            self.list_stack.append(tag)
        elif tag == "table":
            if "-qt-table-type: root" in (a.get("style") or ""):     # коренева рамка сторінки — не таблиця
                self.tstack.append("root")
            else:
                self.tstack.append("table")
                self.table = _Table()
                self.blocks.append(self.table)
        elif tag == "tr" and self.table is not None:
            self.table.rows.append([])
        elif tag in ("td", "th") and self.table is not None:
            self.cell = []
            self.table.rows[-1].append((self.cell, int(a.get("colspan", 1) or 1)))
            self.cur = None
        elif tag in ("span", "b", "strong", "i", "em", "u", "s", "font", "sup", "sub", "a"):
            if tag in ("b", "strong"):
                s.b = True
            if tag in ("i", "em"):
                s.i = True
            if tag == "u":
                s.u = True
            if tag == "s":
                s.s = True
            if tag == "sup":
                s.sup = True
            if tag == "sub":
                s.sub = True
            if tag == "font" and _hex(a.get("color")):
                s.color = _hex(a.get("color"))
            self.style.append(s)
        elif tag == "br":
            self.handle_data("\n")
        elif tag == "img":
            if self.cur is None:
                self._open_para("p", {}, "left")
            w = re.match(r"(\d+)", a.get("width", "") or "")
            self.cur.runs.append(_Run(image=a.get("src", ""), width=int(w.group(1)) if w else 0))
        elif tag == "hr":
            self.pending_break = False
            self._open_para("hr", {}, "left")
            self.cur = None

    def handle_endtag(self, tag):
        if tag in ("p", "h1", "h2", "h3", "h4", "li"):
            self.cur = None
            if len(self.style) > 1:
                self.style.pop()
        elif tag in ("ul", "ol") and self.list_stack:
            self.list_stack.pop()
        elif tag in ("td", "th"):
            self.cell = None
            self.cur = None
        elif tag == "table":
            if self.tstack and self.tstack.pop() == "table":
                self.table = None
        elif tag in ("span", "b", "strong", "i", "em", "u", "s", "font", "sup", "sub", "a") and len(self.style) > 1:
            self.style.pop()

    def handle_data(self, data):
        if not self.in_body:
            return
        if self.cur is None:
            if not data.strip():
                return
            self._open_para("p", {}, "left")
        self.cur.runs.append(_Run(data, self.style[-1]))


def _fill_para(p, para: _Para, images: dict[str, bytes]) -> None:
    for r in para.runs:
        if r.image is not None:
            data = images.get(r.image)
            if data:
                run = p.add_run()
                kw = {"width": Inches(min(6.3, r.width / 96))} if r.width else {}
                run.add_picture(io.BytesIO(data), **kw)
            continue
        run = p.add_run(r.text)
        st = r.style
        run.bold, run.italic, run.underline = st.b or None, st.i or None, st.u or None
        if st.s:
            run.font.strike = True
        if st.sup:
            run.font.superscript = True
        if st.sub:
            run.font.subscript = True
        if st.size:
            run.font.size = Pt(st.size)
        if st.font:
            run.font.name = st.font
        if st.color and st.color != "#000000":
            run.font.color.rgb = RGBColor.from_string(st.color[1:].upper())
        if st.bg and st.bg not in ("#ffffff", "#000000"):
            _shade(run, st.bg[1:])
    p.alignment = _ALIGN.get(para.align, WD_ALIGN_PARAGRAPH.LEFT)
    if para.indent:
        p.paragraph_format.left_indent = Inches(0.4 * para.indent)
    if para.first_line_px:
        p.paragraph_format.first_line_indent = Inches(para.first_line_px / 96)
    if para.margin_left_px and not para.indent:
        p.paragraph_format.left_indent = Inches(para.margin_left_px / 96)
    if para.margin_right_px:
        p.paragraph_format.right_indent = Inches(para.margin_right_px / 96)
    if para.line_height:
        p.paragraph_format.line_spacing = para.line_height / 100


def _shade(run, hex6: str) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex6.upper())
    run._r.get_or_add_rPr().append(shd)


def _add_para(d, para: _Para, images):
    if para.kind == "hr":
        p = d.add_paragraph("_" * 60)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        return
    if para.kind in ("h1", "h2", "h3", "h4"):
        p = d.add_heading("", level=int(para.kind[1]))
    elif para.kind == "li":
        p = d.add_paragraph(style="List Bullet")
    elif para.kind == "oli":
        p = d.add_paragraph(style="List Number")
    else:
        p = d.add_paragraph()
    if para.page_break:
        p.add_run().add_break(WD_BREAK.PAGE)
    _fill_para(p, para, images)


def html_to_docx(html: str, images: dict[str, bytes] | None = None,
                 margins_mm: tuple[float, float, float, float] | None = None) -> DocxDocument:
    """margins_mm = (ліве, праве, верхнє, нижнє)."""
    from docx.shared import Mm
    images = images or {}
    ps = _Parser()
    ps.feed(html)
    d = DocxDocument()
    if margins_mm:
        sec = d.sections[0]
        sec.page_width, sec.page_height = Mm(210), Mm(297)
        sec.left_margin, sec.right_margin, sec.top_margin, sec.bottom_margin = (Mm(v) for v in margins_mm)
    d.styles["Normal"].font.name = "Times New Roman"
    d.styles["Normal"].font.size = Pt(12)
    for b in ps.blocks:
        if isinstance(b, _Para):
            _add_para(d, b, images)
        else:
            rows = [r for r in b.rows if r]
            if not rows:
                continue
            ncols = max(sum(span for _, span in r) for r in rows)
            t = d.add_table(rows=len(rows), cols=ncols)
            t.style = "Table Grid"
            for i, row in enumerate(rows):
                j = 0
                for cell_paras, span in row:
                    c = t.cell(i, j)
                    if span > 1 and j + span - 1 < ncols:
                        c = c.merge(t.cell(i, j + span - 1))
                    c.text = ""
                    for k, para in enumerate(cell_paras):
                        p = c.paragraphs[0] if k == 0 else c.add_paragraph()
                        _fill_para(p, para, images)
                    j += span
            d.add_paragraph()
    return d


def docx_to_html(path: Path, with_images: bool = False):
    """DOCX → HTML для QTextEdit: заголовки, списки, форматування прогонів, кольори, таблиці, зображення.
    with_images=True → (html, {назва: bytes})."""
    from docx.oxml.ns import qn
    from docx.table import Table as DTable
    from docx.text.paragraph import Paragraph as DPara

    d = DocxDocument(str(path))
    out = []
    list_open = None
    images: dict[str, bytes] = {}
    rels = {r.rId: r for r in d.part.rels.values()}

    def run_html(r) -> str:
        t = _html.escape(r.text).replace("\n", "<br/>")
        for blip in r._r.iter(qn("a:blip")):
            rid = blip.get(qn("r:embed"))
            if rid in rels and rid not in images:
                images[f"docx_{rid}.png"] = rels[rid].target_part.blob
            if rid in rels:
                t += f'<img src="docx_{rid}.png"/>'
        styles = []
        if r.bold:
            t = f"<b>{t}</b>"
        if r.italic:
            t = f"<i>{t}</i>"
        if r.underline:
            t = f"<u>{t}</u>"
        if r.font.strike:
            t = f"<s>{t}</s>"
        if r.font.superscript:
            t = f"<sup>{t}</sup>"
        if r.font.subscript:
            t = f"<sub>{t}</sub>"
        if r.font.size:
            styles.append(f"font-size:{r.font.size.pt:g}pt")
        if r.font.name:
            styles.append(f"font-family:'{r.font.name}'")
        if r.font.color is not None and r.font.color.type is not None and r.font.color.rgb is not None:
            styles.append(f"color:#{r.font.color.rgb}")
        return f'<span style="{";".join(styles)}">{t}</span>' if styles else t

    def align_of(p: DPara) -> str:
        a = p.alignment
        return {1: "center", 2: "right", 3: "justify"}.get(int(a) if a is not None else 0, "left")

    for el in d.element.body.iterchildren():
        if el.tag == qn("w:p"):
            p = DPara(el, d)
            name = (p.style.name or "").lower() if p.style is not None else ""
            inner = "".join(run_html(r) for r in p.runs)
            tag = None
            if "list" in name or el.find(".//" + qn("w:numPr")) is not None:
                tag = "ol" if "number" in name else "ul"
            if list_open and tag != list_open:
                out.append(f"</{list_open}>")
                list_open = None
            if tag:
                if not list_open:
                    out.append(f"<{tag}>")
                    list_open = tag
                out.append(f"<li>{inner}</li>")
            elif name.startswith("heading") or name.startswith("title"):
                lvl = name.replace("heading", "").strip() or "1"
                lvl = lvl if lvl in "123" else "1"
                out.append(f'<h{lvl} align="{align_of(p)}">{inner}</h{lvl}>')
            else:
                out.append(f'<p align="{align_of(p)}">{inner or "<br/>"}</p>')
        elif el.tag == qn("w:tbl"):
            if list_open:
                out.append(f"</{list_open}>")
                list_open = None
            t = DTable(el, d)
            rows = []
            for row in t.rows:
                seen = set()
                cells = []
                for c in row.cells:
                    if id(c._tc) in seen:
                        continue
                    seen.add(id(c._tc))
                    span = c._tc.grid_span if hasattr(c._tc, "grid_span") else 1
                    inner = "<br/>".join("".join(run_html(r) for r in p.runs) for p in c.paragraphs)
                    cells.append(f'<td colspan="{span}">{inner}</td>' if span > 1 else f"<td>{inner}</td>")
                rows.append(f"<tr>{''.join(cells)}</tr>")
            out.append(f'<table border="1" cellpadding="4" cellspacing="0" width="100%">{"".join(rows)}</table><p></p>')
    if list_open:
        out.append(f"</{list_open}>")
    html = "".join(out)
    if with_images:
        try:
            sec = d.sections[0]
            images["__margins_mm__"] = (sec.left_margin.mm, sec.right_margin.mm, sec.top_margin.mm, sec.bottom_margin.mm)
        except Exception:
            pass
        return html, images
    return html
