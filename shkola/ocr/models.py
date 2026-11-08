"""Моделі результату розпізнавання: слова з координатами, структурований документ."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Word:
    text: str
    x0: int
    y0: int
    x1: int
    y1: int
    conf: float = 0.0
    block: int = 0
    para: int = 0
    line: int = 0

    @property
    def h(self) -> int:
        return self.y1 - self.y0

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


@dataclass
class Paragraph:
    """kind: p | h1 | h2 | h3 | li (маркований) | oli (нумерований); align: left | center | right | justify."""
    text: str
    kind: str = "p"
    align: str = "left"
    bbox: tuple[int, int, int, int] | None = None


@dataclass
class Table:
    rows: list[list[str]]
    bbox: tuple[int, int, int, int] | None = None

    @property
    def n_cols(self) -> int:
        return max((len(r) for r in self.rows), default=0)


@dataclass
class Formula:
    latex: str
    bbox: tuple[int, int, int, int] | None = None


Block = Paragraph | Table | Formula


@dataclass
class Document:
    blocks: list[Block] = field(default_factory=list)

    @property
    def tables(self) -> list[Table]:
        return [b for b in self.blocks if isinstance(b, Table)]

    def plain_text(self) -> str:
        out = []
        for b in self.blocks:
            if isinstance(b, Paragraph):
                out.append(("• " if b.kind == "li" else "") + b.text)
            elif isinstance(b, Table):
                out.extend("\t".join(r) for r in b.rows)
            else:
                out.append(f"$ {b.latex} $")
        return "\n\n".join(out)


@dataclass
class OcrPage:
    width: int
    height: int
    dpi: int
    words: list[Word] = field(default_factory=list)
    doc: Document = field(default_factory=Document)
    langs: str = ""

    @property
    def text(self) -> str:
        return self.doc.plain_text()

    @property
    def mean_conf(self) -> float:
        ws = [w.conf for w in self.words if w.text.strip()]
        return sum(ws) / len(ws) if ws else 0.0
