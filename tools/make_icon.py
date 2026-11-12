"""Іконки «Накази ШКОЛА» з assets/logo.svg (+ logo_small.svg для 16–24 px).

→ assets/logo.ico (кадри 16, 20, 24, 32, 40, 48, 64, 128, 256 — кожен намальований у своєму розмірі, не стиснутий з 256)
→ build/icon256.png і build/msix_assets/*.png для MSIX (targetsize + altform-unplated, плитки, Wide, Splash)
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QGuiApplication
from PIL import Image
import io

app = QGuiApplication(sys.argv)
from shkola.ui.logo import logo_pixmap  # noqa: E402

BG = (27, 31, 138, 255)          # #1b1f8a — тло плиток і заставки, як у іконці
ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def render(size: int) -> Image.Image:
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    logo_pixmap(size).save(buf, "PNG")
    return Image.open(io.BytesIO(bytes(buf.data()))).convert("RGBA")


def on_canvas(w: int, h: int, icon: int, bg=BG) -> Image.Image:
    c = Image.new("RGBA", (w, h), bg)
    im = render(icon)
    c.alpha_composite(im, ((w - icon) // 2, (h - icon) // 2))
    return c


def main() -> None:
    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    frames = {s: render(s) for s in ICO_SIZES}
    frames[256].save(build / "icon256.png")
    # ICO: кожен кадр — окремий рендер; Pillow бере append_images як готові кадри
    big = frames[256]
    big.save(ROOT / "assets" / "logo.ico", format="ICO", sizes=[(s, s) for s in ICO_SIZES],
             append_images=[frames[s] for s in ICO_SIZES if s != 256])

    out = build / "msix_assets"
    out.mkdir(exist_ok=True)
    for f in out.glob("*.png"):
        f.unlink()
    # Square44x44Logo: базовий + targetsize (панель задач, меню «Пуск», Провідник), plated і unplated
    render(44).save(out / "Square44x44Logo.png")
    for s in (16, 24, 32, 48, 256):
        frames.get(s, render(s)).save(out / f"Square44x44Logo.targetsize-{s}.png")
        frames.get(s, render(s)).save(out / f"Square44x44Logo.targetsize-{s}_altform-unplated.png")
        frames.get(s, render(s)).save(out / f"Square44x44Logo.targetsize-{s}_altform-lightunplated.png")
    render(150).save(out / "Square150x150Logo.png")
    render(50).save(out / "StoreLogo.png")
    on_canvas(310, 150, 120).save(out / "Wide310x150Logo.png")
    on_canvas(620, 300, 240).save(out / "SplashScreen.png")
    print("assets/logo.ico і build/msix_assets готово:", len(list(out.glob('*.png'))), "PNG")


if __name__ == "__main__":
    main()
