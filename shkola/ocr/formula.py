"""Розпізнавання формул (зображення → LaTeX) і перетворення LaTeX у читабельний Unicode-текст."""

from __future__ import annotations

import logging
import re
import threading
from pathlib import Path

from PIL import Image

from ..config import LATEX_MODEL_DIR

log = logging.getLogger(__name__)
_engine = None
_lock = threading.Lock()
MODEL_FILES = ("image_resizer.onnx", "encoder.onnx", "decoder.onnx", "tokenizer.json")


def available() -> bool:
    return all((Path(LATEX_MODEL_DIR) / f).exists() for f in MODEL_FILES)


def missing_message() -> str:
    return f"Моделі формул не знайдено в {LATEX_MODEL_DIR}. Запустіть tools\\get_ocr.py."


def recognize(img: Image.Image) -> str:
    """Повертає LaTeX. Перший виклик завантажує моделі (~1–2 с)."""
    global _engine
    if not available():
        raise RuntimeError(missing_message())
    with _lock:
        if _engine is None:
            from .latex_vendor.engine import LaTeXOCR
            _engine = LaTeXOCR(LATEX_MODEL_DIR)
        try:
            latex = _engine(img.convert("RGB"))
        except ValueError:              # порожня ділянка (без темних пікселів)
            return ""
    log.info("Формула: %s", latex)
    return latex


# ---------- LaTeX → Unicode ----------
_GREEK = {"alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "varepsilon": "ε", "zeta": "ζ",
          "eta": "η", "theta": "θ", "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ",
          "pi": "π", "rho": "ρ", "sigma": "σ", "tau": "τ", "upsilon": "υ", "phi": "φ", "varphi": "φ", "chi": "χ",
          "psi": "ψ", "omega": "ω", "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ", "Pi": "Π",
          "Sigma": "Σ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω"}
_SYM = {"pm": "±", "mp": "∓", "cdot": "·", "times": "×", "div": "÷", "leq": "≤", "le": "≤", "geq": "≥", "ge": "≥",
        "neq": "≠", "ne": "≠", "approx": "≈", "equiv": "≡", "infty": "∞", "to": "→", "rightarrow": "→",
        "leftarrow": "←", "Rightarrow": "⇒", "Leftrightarrow": "⇔", "sum": "∑", "prod": "∏", "int": "∫",
        "partial": "∂", "nabla": "∇", "in": "∈", "notin": "∉", "subset": "⊂", "cup": "∪", "cap": "∩",
        "forall": "∀", "exists": "∃", "angle": "∠", "perp": "⊥", "parallel": "∥", "degree": "°", "circ": "°",
        "ldots": "…", "cdots": "⋯", "dots": "…", "sin": "sin", "cos": "cos", "tan": "tan", "tg": "tg", "ctg": "ctg",
        "log": "log", "ln": "ln", "lim": "lim", "max": "max", "min": "min", "left": "", "right": "", ",": " ",
        ";": " ", "!": "", "quad": "  ", "qquad": "    ", "{": "{", "}": "}", "%": "%", "_": "_", "&": "&",
        "displaystyle": "", "scriptstyle": "", "textstyle": "", "scriptscriptstyle": "", "mathit": "", "boldsymbol": "", "mathcal": "", "mathbb": "", "mathrm": "", "mathbf": "", "text": "", "operatorname": "", "prime": "′"}
_SUP = str.maketrans("0123456789+-=()ni", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱ")
_SUB = str.maketrans("0123456789+-=()aeoxhklmnpst", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₒₓₕₖₗₘₙₚₛₜ")


def _group(s: str, i: int) -> tuple[str, int]:
    """Повертає вміст {…} від позиції i (s[i] == '{') і позицію після дужки."""
    depth, j = 0, i
    while j < len(s):
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
        j += 1
    return s[i + 1:], len(s)


def _arg(s: str, i: int) -> tuple[str, int]:
    while i < len(s) and s[i] == " ":
        i += 1
    if i < len(s) and s[i] == "{":
        return _group(s, i)
    if i < len(s) and s[i] == "\\":
        m = re.match(r"\\[A-Za-z]+", s[i:])
        return (m.group(0), i + len(m.group(0))) if m else (s[i], i + 1)
    return (s[i], i + 1) if i < len(s) else ("", i)


def _wrap(s: str) -> str:
    return s if len(s) <= 1 or s.isalnum() else f"({s})"


def latex_to_unicode(s: str) -> str:
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c == "\\":
            m = re.match(r"\\([A-Za-z]+|.)", s[i:])
            name = m.group(1)
            i += len(m.group(0))
            if name == "frac":
                a, i = _arg(s, i)
                b, i = _arg(s, i)
                out.append(f"{_wrap(latex_to_unicode(a))}/{_wrap(latex_to_unicode(b))}")
            elif name == "sqrt":
                if i < len(s) and s[i] == "[":
                    j = s.index("]", i)
                    n, i = s[i + 1:j], j + 1
                    a, i = _arg(s, i)
                    out.append(f"{latex_to_unicode(n).translate(_SUP)}√({latex_to_unicode(a)})")
                else:
                    a, i = _arg(s, i)
                    out.append(f"√({latex_to_unicode(a)})")
            elif name in ("hat", "bar", "vec", "overline", "underline", "mathit", "boldsymbol"):
                a, i = _arg(s, i)
                out.append(latex_to_unicode(a) + ("̄" if name in ("bar", "overline") else "⃗" if name == "vec" else ""))
            elif name in ("begin", "end"):
                a, i = _arg(s, i)
                if name == "end":
                    out.append("\n")
            elif name in _GREEK:
                out.append(_GREEK[name])
            elif name in _SYM:
                out.append(_SYM[name])
            else:
                out.append(name)
        elif c in "^_":
            a, i2 = _arg(s, i + 1)
            inner = latex_to_unicode(a)
            tr = inner.translate(_SUP if c == "^" else _SUB)
            if all(ord(ch) > 127 or ch in " " for ch in tr) or len(inner) == 0:
                out.append(tr)
            else:
                out.append(("^" if c == "^" else "_") + _wrap(inner))
            i = i2
        elif c == "{":
            a, i = _group(s, i)
            out.append(latex_to_unicode(a))
        elif c == "}":
            i += 1
        elif c == "&":
            out.append("\t")
            i += 1
        elif c == "~":
            out.append(" ")
            i += 1
        else:
            out.append(c)
            i += 1
    return re.sub(r"[ ]{2,}", " ", "".join(out)).strip()
