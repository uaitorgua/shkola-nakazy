"""Сканування через Windows Image Acquisition (USB і мережні WSD-сканери, додані у Windows)."""

from __future__ import annotations

import logging
import os
import tempfile
import threading
import time

from PIL import Image

from ..config import PAPER_SIZES
from ..core.models import ColorMode, Link, ScannerInfo, ScanSettings, Source
from .base import PageCallback, ScanCancelled, ScanError, ScannerBackend

log = logging.getLogger(__name__)

WIA_SCANNER = 1
FMT_PNG = "{B96B3CAF-0728-11D3-9D7B-0000F81EF32E}"

# Ідентифікатори властивостей WIA
P_DEVICE_NAME = 7
P_PORT_NAME = 6           # "\\.\Usbscan0", "WSD-...", тощо
P_SERVER = 8              # "local" або ім'я хоста (DIP_SERVER_NAME)
P_DOC_HANDLING_CAPS = 3086
P_DOC_HANDLING_STATUS = 3087
P_DOC_HANDLING_SELECT = 3088
P_PAGES = 3096
P_COLOR_INTENT = 6146
P_XRES, P_YRES = 6147, 6148
P_XPOS, P_YPOS = 6149, 6150
P_XEXT, P_YEXT = 6151, 6152

FEEDER, FLATBED, DUPLEX = 0x001, 0x002, 0x004
FEED_READY = 0x001

ERR_PAPER_EMPTY = -2145320957     # 0x80210003
ERR_BUSY = -2145320954            # 0x80210006
ERR_OFFLINE = -2145320955         # 0x80210005
ERR_CANCELLED = -2145320860       # 0x80210064 (користувач скасував)

_INTENT = {ColorMode.COLOR: 1, ColorMode.GRAY: 2, ColorMode.BW: 4}


def _com():
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    return win32com.client


def _prop(props, pid):
    for p in props:
        if p.PropertyID == pid:
            return p
    return None


def _set(props, pid, value) -> bool:
    p = _prop(props, pid)
    if p is None:
        return False
    try:
        p.Value = value
        return True
    except Exception:
        log.debug("WIA: властивість %s=%s не прийнята", pid, value)
        return False


def _hresult(exc: Exception) -> int:
    args = getattr(exc, "args", ())
    if len(args) > 2 and isinstance(args[2], tuple) and len(args[2]) > 5:
        return args[2][5] or args[0]
    return args[0] if args and isinstance(args[0], int) else 0


class WiaBackend(ScannerBackend):
    name = "wia"

    def __init__(self) -> None:
        self._lock = threading.RLock()    # WIA/COM не терпить паралельних викликів із різних потоків

    def discover(self) -> list[ScannerInfo]:
        with self._lock:
            return self._discover()

    def check_link(self, info: ScannerInfo) -> tuple[Link, str]:
        with self._lock:
            return self._check_link(info)

    def scan(self, info: ScannerInfo, settings: ScanSettings,
             on_page: PageCallback, cancel: threading.Event) -> int:
        with self._lock:
            return self._scan(info, settings, on_page, cancel)

    def _discover(self) -> list[ScannerInfo]:
        try:
            client = _com()
            dm = client.Dispatch("WIA.DeviceManager")
        except Exception:
            log.exception("WIA недоступний")
            return []
        found = []
        for i in range(1, dm.DeviceInfos.Count + 1):
            di = dm.DeviceInfos.Item(i)
            if di.Type != WIA_SCANNER:
                continue
            name = str(_prop(di.Properties, P_DEVICE_NAME).Value)
            server = _prop(di.Properties, P_SERVER)
            port = _prop(di.Properties, P_PORT_NAME)
            host = str(server.Value) if server and server.Value else "local"
            port_name = str(port.Value) if port and port.Value else ""
            # мережний — лише якщо WIA явно каже «не local» або порт WSD/IP
            network = host.lower() not in ("local", "") or port_name.upper().startswith(("WSD", "TCP"))
            if host.lower() in ("local", ""):
                host = ""
            found.append(ScannerInfo(
                backend=self.name, uid=di.DeviceID, name=name,
                host=host if network else "", network=network,
                sources=(Source.FLATBED, Source.FEEDER, Source.DUPLEX),
                resolutions=(75, 100, 150, 200, 300, 600, 1200),
            ))
        return found

    def _check_link(self, info: ScannerInfo) -> tuple[Link, str]:
        # ping не використовуємо: USB-пристрої не мають хоста, а мережні МФП часто
        # блокують ICMP, хоч і працюють. Перевіряємо справжнє з'єднання через WIA.
        try:
            client = _com()
            dev = self._connect(client, info)
            caps = _prop(dev.Properties, P_DOC_HANDLING_CAPS)
            if caps is not None:
                srcs = [Source.FLATBED] if caps.Value & FLATBED else []
                if caps.Value & FEEDER:
                    srcs.append(Source.FEEDER)
                if caps.Value & DUPLEX:
                    srcs.append(Source.DUPLEX)
                info.sources = tuple(srcs) or (Source.FLATBED,)
            return Link.ONLINE, "пристрій відповідає"
        except Exception as e:
            code = _hresult(e)
            if code == ERR_BUSY:
                return Link.BUSY, "сканер зайнятий"
            return Link.OFFLINE, f"WIA: не вдалося під'єднатися ({code:#x})" if code else str(e)

    def _connect(self, client, info: ScannerInfo):
        dm = client.Dispatch("WIA.DeviceManager")
        for i in range(1, dm.DeviceInfos.Count + 1):
            di = dm.DeviceInfos.Item(i)
            if di.DeviceID == info.uid:
                return di.Connect()
        raise ScanError("Пристрій зник зі списку WIA")

    def _connect_ready(self, client, info: ScannerInfo, cancel: threading.Event, timeout: float = 60):
        """Під'єднання з очікуванням: після попереднього аркуша драйвер кілька секунд відповідає «зайнятий»."""
        end = time.monotonic() + timeout
        while True:
            try:
                return self._connect(client, info)
            except Exception as e:
                if _hresult(e) not in (ERR_BUSY, ERR_OFFLINE) or time.monotonic() > end:
                    raise
            if cancel.is_set():
                raise ScanCancelled()
            time.sleep(1.5)

    def _scan(self, info: ScannerInfo, settings: ScanSettings,
              on_page: PageCallback, cancel: threading.Event) -> int:
        client = _com()
        try:
            dev = self._connect_ready(client, info, cancel)
        except ScanCancelled:
            raise
        except Exception as e:
            raise ScanError(f"Немає зв'язку зі сканером: {e}") from e

        use_feeder = settings.source in (Source.FEEDER, Source.DUPLEX)
        sel = FEEDER | (DUPLEX if settings.source == Source.DUPLEX else 0) if use_feeder else FLATBED
        _set(dev.Properties, P_DOC_HANDLING_SELECT, sel)
        _set(dev.Properties, P_PAGES, 0 if use_feeder else 1)   # 0 = усі сторінки з лотка

        item = dev.Items.Item(1)
        props = item.Properties
        _set(props, P_COLOR_INTENT, _INTENT[settings.color])
        _set(props, P_XRES, settings.dpi)
        _set(props, P_YRES, settings.dpi)
        w_mm, h_mm = PAPER_SIZES.get(settings.paper, (0, 0))
        if w_mm:
            _set(props, P_XPOS, 0)
            _set(props, P_YPOS, 0)
            _set(props, P_XEXT, int(w_mm / 25.4 * settings.dpi))
            _set(props, P_YEXT, int(h_mm / 25.4 * settings.dpi))

        count = 0
        busy_end = time.monotonic() + 60
        while True:
            if cancel.is_set():
                raise ScanCancelled()
            try:
                img_file = item.Transfer(FMT_PNG)
            except Exception as e:
                code = _hresult(e)
                if code == ERR_BUSY and time.monotonic() < busy_end:
                    time.sleep(1.5)          # сканер ще не готовий — чекаємо
                    continue
                if code == ERR_PAPER_EMPTY:
                    if count == 0:
                        raise ScanError("У автоподавачі немає паперу") from e
                    break
                if code == ERR_CANCELLED:
                    raise ScanCancelled() from e
                raise ScanError(f"Помилка сканування WIA ({code:#x}): {e}") from e
            on_page(self._to_image(img_file))
            count += 1
            busy_end = time.monotonic() + 60
            if not use_feeder:
                break
        del item, props, dev           # звільняємо пристрій, щоб наступний аркуш не впирався в «зайнятий»
        return count

    @staticmethod
    def _to_image(img_file) -> Image.Image:
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        os.remove(path)          # WIA не перезаписує наявний файл
        try:
            img_file.SaveFile(path)
            with Image.open(path) as im:
                im.load()
                return im.copy()
        finally:
            if os.path.exists(path):
                os.remove(path)
