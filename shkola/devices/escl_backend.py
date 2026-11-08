"""Мережне сканування за протоколом eSCL (AirScan / Mopria) — без драйверів.

Підтримується більшістю сучасних МФП (HP, Canon, Epson, Brother, Kyocera, Xerox, Ricoh).
Пристрої шукаються через mDNS (_uscan._tcp) та за IP-адресами, які ввів користувач.
"""

from __future__ import annotations

import io
import logging
import threading
import time
import xml.etree.ElementTree as ET

import requests
from PIL import Image

from ..config import CONNECT_TIMEOUT_S, PAPER_SIZES
from ..core.models import ColorMode, Link, ScannerInfo, ScanSettings, Source
from .base import PageCallback, ScanCancelled, ScanError, ScannerBackend
from .netcheck import split_host, tcp_open

log = logging.getLogger(__name__)

READY_TIMEOUT_S = 60      # скільки чекати, поки сканер стане «Idle»
PAGE_TIMEOUT_S = 180      # скільки чекати одну сторінку (503 «ще сканує»)

NS = {"scan": "http://schemas.hp.com/imaging/escl/2011/05/03",
      "pwg": "http://www.pwg.org/schemas/2010/12/sm"}

_COLOR = {ColorMode.COLOR: "RGB24", ColorMode.GRAY: "Grayscale8", ColorMode.BW: "BlackAndWhite1"}
_SOURCE = {Source.FLATBED: "Platen", Source.FEEDER: "Feeder", Source.DUPLEX: "Feeder"}

JOB_XML = """<?xml version="1.0" encoding="UTF-8"?>
<scan:ScanSettings xmlns:scan="{scan}" xmlns:pwg="{pwg}">
  <pwg:Version>2.0</pwg:Version>
  <scan:Intent>Document</scan:Intent>
  <pwg:ScanRegions>
    <pwg:ScanRegion>
      <pwg:XOffset>0</pwg:XOffset><pwg:YOffset>0</pwg:YOffset>
      <pwg:Width>{w}</pwg:Width><pwg:Height>{h}</pwg:Height>
      <pwg:ContentRegionUnits>escl:ThreeHundredthsOfInches</pwg:ContentRegionUnits>
    </pwg:ScanRegion>
  </pwg:ScanRegions>
  <pwg:InputSource>{source}</pwg:InputSource>
  <scan:Duplex>{duplex}</scan:Duplex>
  <scan:ColorMode>{color}</scan:ColorMode>
  <scan:XResolution>{dpi}</scan:XResolution>
  <scan:YResolution>{dpi}</scan:YResolution>
  <pwg:DocumentFormat>image/jpeg</pwg:DocumentFormat>
  <scan:DocumentFormatExt>image/jpeg</scan:DocumentFormatExt>
</scan:ScanSettings>"""


def _url(info: ScannerInfo, tail: str) -> str:
    scheme = "https" if info.port == 443 else "http"
    base = info.base_path.strip("/") or "eSCL"
    return f"{scheme}://{info.host}:{info.port}/{base}/{tail}"


class EsclBackend(ScannerBackend):
    name = "escl"

    def __init__(self, manual_hosts: list[str] | None = None) -> None:
        self.manual_hosts = manual_hosts or []
        self.found_hosts: list[tuple[str, int, str]] = []    # з останнього сканування мережі
        self.http = requests.Session()
        self.http.verify = False   # МФП зазвичай мають самопідписані сертифікати
        requests.packages.urllib3.disable_warnings()

    # ---------- пошук ----------
    def discover(self) -> list[ScannerInfo]:
        found = {i.key: i for i in self._mdns()}
        for text in self.manual_hosts:
            host, port = split_host(text, 80)
            info = ScannerInfo(backend=self.name, uid=f"{host}:{port}", name=f"eSCL {host}",
                               host=host, port=port, base_path="eSCL", network=True)
            found.setdefault(info.key, info)
        for host, port, base in self.found_hosts:
            info = ScannerInfo(backend=self.name, uid=f"{host}:{port}", name=f"eSCL {host}",
                               host=host, port=port, base_path=base, network=True)
            found.setdefault(info.key, info)
        return list(found.values())

    def _mdns(self, wait: float = 2.5) -> list[ScannerInfo]:
        try:
            from zeroconf import ServiceBrowser, Zeroconf
        except ImportError:
            log.info("zeroconf не встановлено — автопошук мережних сканерів вимкнено")
            return []
        result: dict[str, ScannerInfo] = {}

        class Listener:
            def add_service(self, zc, type_, name):
                si = zc.get_service_info(type_, name, timeout=1500)
                if not si or not si.parsed_addresses():
                    return
                props = {k.decode(): (v or b"").decode(errors="ignore") for k, v in si.properties.items()}
                host = si.parsed_addresses()[0]
                title = props.get("ty") or name.split(".")[0]
                uid = f"{host}:{si.port}"
                result[uid] = ScannerInfo(backend="escl", uid=uid, name=title, host=host, port=si.port,
                                          base_path=props.get("rs", "eSCL"), network=True)

            update_service = add_service

            def remove_service(self, *a):
                pass

        zc = Zeroconf()
        try:
            ServiceBrowser(zc, ["_uscan._tcp.local.", "_uscans._tcp.local."], Listener())
            time.sleep(wait)
        finally:
            zc.close()
        return list(result.values())

    # ---------- зв'язок ----------
    def check_link(self, info: ScannerInfo) -> tuple[Link, str]:
        if not tcp_open(info.host, info.port):
            return Link.OFFLINE, f"порт {info.host}:{info.port} закритий або вузол недоступний"
        try:
            caps = self.http.get(_url(info, "ScannerCapabilities"), timeout=CONNECT_TIMEOUT_S + 2)
            if caps.ok:
                self._apply_caps(info, caps.content)
            st = self.http.get(_url(info, "ScannerStatus"), timeout=CONNECT_TIMEOUT_S + 2)
            st.raise_for_status()
            state = ET.fromstring(st.content).findtext(".//pwg:State", default="", namespaces=NS)
        except (requests.RequestException, ET.ParseError) as e:
            return Link.OFFLINE, f"вузол відповідає, але eSCL недоступний: {e.__class__.__name__}"
        if state == "Idle":
            return Link.ONLINE, "готовий"
        if state in ("Processing", "Testing"):
            return Link.BUSY, "зайнятий іншим завданням"
        return Link.OFFLINE, f"стан: {state or 'невідомий'}"

    def _apply_caps(self, info: ScannerInfo, xml: bytes) -> None:
        try:
            root = ET.fromstring(xml)
        except ET.ParseError:
            return
        name = root.findtext(".//pwg:MakeAndModel", namespaces=NS)
        if name:
            info.name = name
        srcs = []
        if root.find(".//scan:Platen", NS) is not None:
            srcs.append(Source.FLATBED)
        if root.find(".//scan:Adf", NS) is not None:
            srcs.append(Source.FEEDER)
            if root.find(".//scan:AdfDuplexInputCaps", NS) is not None:
                srcs.append(Source.DUPLEX)
        info.sources = tuple(srcs) or (Source.FLATBED,)
        res = sorted({int(x.text) for x in root.iterfind(".//scan:XResolution", NS) if x.text and x.text.isdigit()})
        if res:
            info.resolutions = tuple(res)

    # ---------- сканування ----------
    def _state(self, info: ScannerInfo) -> str:
        try:
            st = self.http.get(_url(info, "ScannerStatus"), timeout=CONNECT_TIMEOUT_S + 2)
            if st.ok:
                return ET.fromstring(st.content).findtext(".//pwg:State", default="", namespaces=NS)
        except (requests.RequestException, ET.ParseError):
            pass
        return ""

    def wait_ready(self, info: ScannerInfo, cancel: threading.Event, timeout: float = READY_TIMEOUT_S) -> bool:
        """Чекає сигналу готовності (State = Idle). Багато МФП після аркуша ще кілька секунд «Processing»."""
        end = time.monotonic() + timeout
        while True:
            state = self._state(info)
            if state == "Idle":
                return True
            if cancel.is_set():
                raise ScanCancelled()
            if time.monotonic() > end:
                log.warning("eSCL %s: не дочекались Idle (стан %r)", info.host, state)
                return False
            time.sleep(1)

    def scan(self, info: ScannerInfo, settings: ScanSettings,
             on_page: PageCallback, cancel: threading.Event) -> int:
        w_mm, h_mm = PAPER_SIZES.get(settings.paper, (0, 0)) or (0, 0)
        if not w_mm:
            w_mm, h_mm = 215.9, 297.0
        dpi = settings.dpi
        if info.resolutions and dpi not in info.resolutions:
            # непідтримувана роздільність → МФП відповідає 409; беремо найближчу підтримувану
            dpi = min(info.resolutions, key=lambda r: (abs(r - dpi), -r))
            log.info("eSCL %s: %s dpi не підтримується, беру %s", info.host, settings.dpi, dpi)
        body = JOB_XML.format(
            scan=NS["scan"], pwg=NS["pwg"],
            w=int(w_mm / 25.4 * 300), h=int(h_mm / 25.4 * 300),
            source=_SOURCE[settings.source],
            duplex="true" if settings.source == Source.DUPLEX else "false",
            color=_COLOR[settings.color], dpi=dpi,
        )
        if not self.wait_ready(info, cancel):
            raise ScanError("Сканер не повідомив про готовність за хвилину. Перевірте, чи не зайнятий він іншим завданням.")
        end = time.monotonic() + READY_TIMEOUT_S
        while True:
            try:
                r = self.http.post(_url(info, "ScanJobs"), data=body.encode(),
                                   headers={"Content-Type": "text/xml"}, timeout=15)
            except requests.RequestException as e:
                raise ScanError(f"Немає зв'язку зі сканером {info.host}: {e}") from e
            if r.status_code in (200, 201):
                break
            if r.status_code in (409, 503) and time.monotonic() < end:
                # сканер ще закінчує попередній аркуш — чекаємо готовності й пробуємо знову
                log.info("eSCL %s: HTTP %s, чекаю готовності", info.host, r.status_code)
                self.wait_ready(info, cancel, timeout=10)
                time.sleep(1)
                continue
            if r.status_code == 409:
                raise ScanError("Сканер зайнятий або в лотку немає паперу")
            if r.status_code == 503:
                raise ScanError("Сканер довго залишається зайнятим. Спробуйте ще раз за хвилину.")
            raise ScanError(f"Сканер відхилив завдання (HTTP {r.status_code})")
        job = r.headers.get("Location", "")
        if not job:
            raise ScanError("Сканер не повернув адресу завдання")
        if job.startswith("/"):
            job = f"{'https' if info.port == 443 else 'http'}://{info.host}:{info.port}{job}"

        count = 0
        page_end = time.monotonic() + PAGE_TIMEOUT_S
        try:
            while True:
                if cancel.is_set():
                    raise ScanCancelled()
                resp = self._next_document(job)
                if resp.status_code == 404:          # більше сторінок немає
                    break
                if resp.status_code == 503:          # ще сканує
                    if time.monotonic() > page_end:
                        if count:
                            break
                        raise ScanError("Сканер не віддав сторінку за 3 хвилини")
                    time.sleep(1)
                    continue
                page_end = time.monotonic() + PAGE_TIMEOUT_S
                if not resp.ok:
                    if count:
                        break
                    raise ScanError(f"Помилка отримання сторінки (HTTP {resp.status_code})")
                img = Image.open(io.BytesIO(resp.content))
                img.load()
                on_page(img)
                count += 1
                if settings.source == Source.FLATBED:
                    break
        finally:
            # завжди закриваємо завдання: інакше частина МФП лишається «Processing» і повтор зависає
            try:
                self.http.delete(job, timeout=5)
            except requests.RequestException:
                pass
        # дочекатися, поки сканер звільниться, щоб наступний аркуш пакета стартував одразу
        if not cancel.is_set():
            try:
                self.wait_ready(info, cancel, timeout=30)
            except ScanCancelled:
                pass
        return count

    def _next_document(self, job: str, attempts: int = 3) -> requests.Response:
        """Багато МФП рвуть keep-alive-з'єднання між сторінками — повторюємо запит."""
        for i in range(attempts):
            try:
                return self.http.get(job.rstrip("/") + "/NextDocument", timeout=120)
            except (requests.ConnectionError, requests.exceptions.ChunkedEncodingError) as e:
                if i == attempts - 1:
                    raise ScanError(f"Зв'язок зі сканером обірвався: {e}") from e
                log.warning("eSCL: повтор NextDocument після обриву (%s)", e)
                time.sleep(0.5)
