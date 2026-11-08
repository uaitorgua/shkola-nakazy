"""Читання діаграм з XLSX (openpyxl їх не завантажує): розбір xl/charts/chart*.xml → параметри для
внутрішніх графіків InterTab (тип, назва, діапазон даних, аркуш, комірка прив'язки)."""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

NS = {"c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
      "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
      "xdr": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
      "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
      "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
KIND = {"barChart": "Стовпчикова", "bar3DChart": "Стовпчикова", "lineChart": "Лінійна", "line3DChart": "Лінійна",
        "pieChart": "Кругова", "pie3DChart": "Кругова", "doughnutChart": "Кругова", "areaChart": "Лінійна",
        "scatterChart": "Лінійна"}
REF_RE = re.compile(r"^(?:'?(?P<sheet>[^'!]+)'?!)?\$?([A-Z]+)\$?(\d+)(?::\$?([A-Z]+)\$?(\d+))?$")


@dataclass
class XlsxChart:
    sheet: str
    kind: str
    title: str
    r0: int
    c0: int
    r1: int
    c1: int
    header_row: bool
    label_col: bool
    anchor: str


def _col(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n - 1


def _letters(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def _parse_ref(f: str):
    m = REF_RE.match(f.strip())
    if not m:
        return None
    sheet, c0, r0, c1, r1 = m.group("sheet"), m.group(2), m.group(3), m.group(4), m.group(5)
    return sheet, int(r0) - 1, _col(c0), int(r1 or r0) - 1, _col(c1 or c0)


def _rels(z: zipfile.ZipFile, path: str) -> dict[str, str]:
    base, name = path.rsplit("/", 1)
    rp = f"{base}/_rels/{name}.rels"
    if rp not in z.namelist():
        return {}
    out = {}
    for r in ET.fromstring(z.read(rp)).findall("rel:Relationship", NS):
        t = r.get("Target")
        out[r.get("Id")] = t if t.startswith("/") else f"{base}/{t}"
    return {k: _norm(v) for k, v in out.items()}


def _norm(p: str) -> str:
    parts = []
    for seg in p.lstrip("/").split("/"):
        if seg == "..":
            parts.pop()
        elif seg != ".":
            parts.append(seg)
    return "/".join(parts)


def read_charts(path: Path) -> list[XlsxChart]:
    out: list[XlsxChart] = []
    with zipfile.ZipFile(str(path)) as z:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        wb_rels = _rels(z, "xl/workbook.xml")
        for sh in wb.find("m:sheets", NS):
            name = sh.get("name")
            sheet_path = wb_rels.get(sh.get(f"{{{NS['r']}}}id"))
            if not sheet_path or sheet_path not in z.namelist():
                continue
            srels = _rels(z, sheet_path)
            sx = ET.fromstring(z.read(sheet_path))
            dr = sx.find("m:drawing", NS)
            if dr is None:
                continue
            dpath = srels.get(dr.get(f"{{{NS['r']}}}id"))
            if not dpath or dpath not in z.namelist():
                continue
            drels = _rels(z, dpath)
            dx = ET.fromstring(z.read(dpath))
            for anchor in list(dx):
                frm = anchor.find("xdr:from", NS)
                a_cell = "H2"
                if frm is not None:
                    a_cell = f"{_letters(int(frm.find('xdr:col', NS).text))}{int(frm.find('xdr:row', NS).text) + 1}"
                for ch in anchor.iter(f"{{{NS['c']}}}chart"):
                    cpath = drels.get(ch.get(f"{{{NS['r']}}}id"))
                    if cpath and cpath in z.namelist():
                        spec = _parse_chart(z.read(cpath), name, a_cell)
                        if spec:
                            out.append(spec)
    return out


def _parse_chart(data: bytes, sheet: str, anchor: str) -> XlsxChart | None:
    root = ET.fromstring(data)
    plot = root.find(".//c:plotArea", NS)
    if plot is None:
        return None
    kind, node = None, None
    for child in plot:
        tag = child.tag.split("}")[1]
        if tag in KIND:
            kind, node = KIND[tag], child
            if tag.startswith("bar"):
                bd = child.find("c:barDir", NS)
                if bd is not None and bd.get("val") == "bar":
                    kind = "Горизонтальна"
            break
    if node is None:
        return None
    title = ""
    t = root.find(".//c:title//a:t", NS)
    if t is not None and t.text:
        title = t.text
    rows, cols, cat_cols, has_names = [], [], [], False
    for ser in node.findall("c:ser", NS):
        v = ser.find("c:val//c:f", NS)
        if v is None:
            v = ser.find("c:yVal//c:f", NS)
        if v is not None and v.text:
            ref = _parse_ref(v.text)
            if ref:
                sheet = ref[0] or sheet
                rows += [ref[1], ref[3]]
                cols += [ref[2], ref[4]]
        tx = ser.find("c:tx//c:f", NS)
        if tx is not None and tx.text:
            ref = _parse_ref(tx.text)
            if ref:
                has_names = True
                rows += [ref[1]]
        cat = ser.find("c:cat//c:f", NS)
        if cat is None:
            cat = ser.find("c:xVal//c:f", NS)
        if cat is not None and cat.text:
            ref = _parse_ref(cat.text)
            if ref:
                cat_cols += [ref[2], ref[4]]
                rows += [ref[1], ref[3]]
    if not rows or not cols:
        return None
    label_col = bool(cat_cols) and min(cat_cols) < min(cols)
    c0 = min(cat_cols + cols) if label_col else min(cols)
    return XlsxChart(sheet, kind, title, min(rows), c0, max(rows), max(cols), has_names, label_col, anchor)
