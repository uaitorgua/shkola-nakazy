"""Перетворення PIL.Image ↔ QImage/QPixmap."""

from PIL import Image
from PySide6.QtGui import QImage, QPixmap


def to_qimage(img: Image.Image) -> QImage:
    if img.mode == "1":
        img = img.convert("L")
    if img.mode == "L":
        data = img.tobytes()
        return QImage(data, img.width, img.height, img.width, QImage.Format.Format_Grayscale8).copy()
    if img.mode != "RGB":
        img = img.convert("RGB")
    data = img.tobytes()
    return QImage(data, img.width, img.height, img.width * 3, QImage.Format.Format_RGB888).copy()


def to_pixmap(img: Image.Image) -> QPixmap:
    return QPixmap.fromImage(to_qimage(img))
