"""Моделі даних: сканер, параметри сканування, сторінка, пакет."""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field, replace
from enum import Enum

from PIL import Image


class ColorMode(str, Enum):
    COLOR = "Кольоровий"
    GRAY = "Відтінки сірого"
    BW = "Чорно-білий"


class Source(str, Enum):
    FLATBED = "Планшет"
    FEEDER = "Автоподавач (ADF)"
    DUPLEX = "Автоподавач, двобічно"


class ScanMode(str, Enum):
    SINGLE = "Один документ"
    BATCH = "Пакет"


class Link(str, Enum):
    UNKNOWN = "невідомо"
    ONLINE = "на зв'язку"
    BUSY = "зайнятий"
    OFFLINE = "немає зв'язку"


@dataclass
class ScannerInfo:
    backend: str            # "wia" | "escl"
    uid: str                # унікальний ідентифікатор у межах бекенда
    name: str
    host: str = ""          # для мережних
    port: int = 0
    base_path: str = ""     # для eSCL, напр. "eSCL"
    network: bool = False
    sources: tuple[Source, ...] = (Source.FLATBED,)
    resolutions: tuple[int, ...] = ()
    link: Link = Link.UNKNOWN
    link_detail: str = ""

    @property
    def key(self) -> str:
        return f"{self.backend}:{self.uid}"

    @property
    def label(self) -> str:
        kind = "мережа" if self.network else "USB/локальний"
        addr = f" — {self.host}" if self.host else ""
        return f"{self.name} ({kind}{addr})"


@dataclass
class ScanSettings:
    dpi: int = 300
    color: ColorMode = ColorMode.COLOR
    source: Source = Source.FLATBED
    paper: str = "A4"
    # Для пакета з планшета: скільки сторінок поспіль (0 = питати після кожної)
    flatbed_pages: int = 0


@dataclass
class Adjust:
    """Неруйнівні правки сторінки. Оригінал не змінюється."""
    rotation: int = 0               # 0/90/180/270
    fine_angle: float = 0.0         # дрібний поворот (вирівнювання), градуси
    crop: tuple[int, int, int, int] | None = None   # (x0, y0, x1, y1) у координатах після повороту
    brightness: int = 0             # -100..100
    contrast: int = 0               # -100..100
    gamma: float = 1.0              # 0.2..3.0
    auto_levels: bool = False
    filter: str = "none"            # none | gray | bw | sharpen | despeckle
    bw_threshold: int = 0           # 0 = автоматичний (Оцу)

    def copy(self) -> "Adjust":
        return replace(self)


_ids = itertools.count(1)


@dataclass
class Page:
    original: Image.Image
    dpi: int = 300
    adjust: Adjust = field(default_factory=Adjust)
    id: int = field(default_factory=lambda: next(_ids))
    note: str = ""
    ocr: object = None          # OcrPage після розпізнавання (shkola.ocr.models), None — ще не розпізнано


class Batch:
    """Впорядкований список сторінок із вставлянням у будь-яку позицію."""

    def __init__(self) -> None:
        self.pages: list[Page] = []

    def __len__(self) -> int:
        return len(self.pages)

    def insert(self, index: int, pages: list[Page]) -> int:
        index = max(0, min(index, len(self.pages)))
        self.pages[index:index] = pages
        return index

    def append(self, pages: list[Page]) -> int:
        return self.insert(len(self.pages), pages)

    def remove(self, indices: list[int]) -> None:
        for i in sorted(set(indices), reverse=True):
            if 0 <= i < len(self.pages):
                del self.pages[i]

    def move(self, src: int, dst: int) -> None:
        if src == dst or not (0 <= src < len(self.pages)):
            return
        page = self.pages.pop(src)
        self.pages.insert(max(0, min(dst, len(self.pages))), page)

    def replace(self, index: int, page: Page) -> None:
        self.pages[index] = page

    def clear(self) -> None:
        self.pages.clear()
