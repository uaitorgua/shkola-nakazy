"""Формула (зображення) → LaTeX. Адаптовано з rapid_latex_ocr/main.py та utils.py (MIT)."""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
from PIL import Image
from tokenizers import Tokenizer
from tokenizers.models import BPE

from .models import EncoderDecoder
from .utils_load import OrtInferSession

MAX_DIMS, MIN_DIMS = [672, 192], [32, 32]
BOS, EOS, MAX_SEQ, TEMPERATURE = 1, 2, 512, 0.00001


class PreProcess:
    def __init__(self):
        self.mean = np.array([0.7931] * 3, dtype=np.float32)
        self.std = np.array([0.1738] * 3, dtype=np.float32)

    @staticmethod
    def pad(img: Image.Image, divable: int = 32) -> Image.Image:
        data = np.array(img.convert("LA"))
        data = (data[..., 0] if data[..., -1].var() == 0 else 255 - data[..., -1]).astype(np.uint8)
        rng = max(1, int(data.max()) - int(data.min()))
        data = (data - data.min()) / rng * 255
        if data.mean() > 128:
            gray = 255 * (data < 128).astype(np.uint8)
        else:
            gray = 255 * (data > 128).astype(np.uint8)
            data = 255 - data
        ys, xs = np.nonzero(gray)
        if len(xs) == 0:
            raise ValueError("Порожнє зображення формули")
        a, b = int(xs.min()), int(ys.min())
        w, h = int(xs.max()) - a + 1, int(ys.max()) - b + 1
        im = Image.fromarray(data[b:b + h, a:a + w].astype(np.uint8)).convert("L")
        dims = [divable * ((x + divable - 1) // divable) for x in (w, h)]
        padded = Image.new("L", tuple(dims), 255)
        padded.paste(im, (0, 0, im.size[0], im.size[1]))
        return padded

    @staticmethod
    def minmax_size(img: Image.Image) -> Image.Image:
        ratios = [a / b for a, b in zip(img.size, MAX_DIMS)]
        if any(r > 1 for r in ratios):
            size = np.maximum(np.array(img.size) // max(ratios), 1)
            img = img.resize(tuple(size.astype(int)), Image.Resampling.BILINEAR)
        new = tuple(max(d, m) for d, m in zip(img.size, MIN_DIMS))
        if new != img.size:
            p = Image.new("L", new, 255)
            p.paste(img, img.getbbox())
            img = p
        return img

    def tensor(self, img: Image.Image) -> np.ndarray:
        g = np.array(img.convert("L"))
        arr = np.stack([g, g, g], axis=-1)
        arr = (arr.astype(np.float32) - self.mean * 255) * np.reciprocal(self.std * 255, dtype=np.float32)
        return arr.transpose(2, 0, 1)[:1][None, ...]


class LaTeXOCR:
    def __init__(self, model_dir: Path):
        d = Path(model_dir)
        self.pre = PreProcess()
        self.resizer = OrtInferSession(d / "image_resizer.onnx")
        self.enc_dec = EncoderDecoder(d / "encoder.onnx", d / "decoder.onnx", BOS, EOS, MAX_SEQ)
        self.tok = Tokenizer(BPE()).from_file(str(d / "tokenizer.json"))

    def __call__(self, img: Image.Image) -> str:
        x = self._resize_loop(img)
        tokens = self.enc_dec(x, temperature=TEMPERATURE)
        if len(tokens.shape) == 1:
            tokens = tokens[None, :]
        s = self.tok.decode(tokens[0].tolist())
        s = "".join(s.split(" ")).replace("Ġ", " ")
        for t in ("[EOS]", "[BOS]", "[PAD]"):
            s = s.replace(t, "")
        return self.post_process(s.strip())

    def _resize_loop(self, img: Image.Image) -> np.ndarray:
        inp = self.pre.minmax_size(self.pre.pad(img)).convert("RGB")
        r, w, h = 1, inp.size[0], inp.size[1]
        final = None
        for _ in range(10):
            h = int(h * r)
            resized = inp.resize((w, h), Image.Resampling.BILINEAR if r > 1 else Image.Resampling.LANCZOS)
            pad_img = self.pre.pad(self.pre.minmax_size(resized))
            final = self.pre.tensor(pad_img)
            res = self.resizer([final.astype(np.float32)])[0]
            w_new = (int(np.argmax(np.asarray(res).reshape(-1))) + 1) * 32
            if w_new == pad_img.size[0]:
                break
            r = w_new / pad_img.size[0]
            w = w_new
        return final

    @staticmethod
    def post_process(s: str) -> str:
        text_reg = r"(\\(operatorname|mathrm|text|mathbf)\s?\*? {.*?})"
        letter, noletter = "[a-zA-Z]", r"[\W_^\d]"
        names = [x[0].replace(" ", "") for x in re.findall(text_reg, s)]
        s = re.sub(text_reg, lambda m: str(names.pop(0)), s)
        while True:
            news = re.sub(r"(?!\ )(%s)\s+?(%s)" % (noletter, noletter), r"\1\2", s)
            news = re.sub(r"(?!\ )(%s)\s+?(%s)" % (noletter, letter), r"\1\2", news)
            news = re.sub(r"(%s)\s+?(%s)" % (letter, noletter), r"\1\2", news)
            if news == s:
                return s
            s = news
