"""Сканування локальної мережі: пошук eSCL-сканерів перебором адрес підмереж /24.

Потрібно, коли mDNS заблоковано (VLAN, корпоративні комутатори) і сканер не видно автоматично.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

import requests

from .netcheck import tcp_open

log = logging.getLogger(__name__)

PORTS = (80, 443, 8080)
PATHS = ("eSCL", "escl")


def local_subnets() -> list[ipaddress.IPv4Network]:
    """Підмережі /24 усіх активних IPv4-інтерфейсів (без loopback і APIPA)."""
    addrs: set[str] = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addrs.add(info[4][0])
    except OSError:
        pass
    try:   # адреса інтерфейсу з маршрутом за замовчуванням
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            addrs.add(s.getsockname()[0])
    except OSError:
        pass
    nets = set()
    for a in addrs:
        ip = ipaddress.IPv4Address(a)
        if ip.is_loopback or ip.is_link_local:
            continue
        nets.add(ipaddress.IPv4Network(f"{a}/24", strict=False))
    return sorted(nets)


def probe(host: str, timeout: float = 0.4) -> list[tuple[str, int, str]]:
    """Повертає [(host, port, base_path)] для eSCL-сервісів на вузлі."""
    found = []
    for port in PORTS:
        if not tcp_open(host, port, timeout):
            continue
        scheme = "https" if port == 443 else "http"
        for base in PATHS:
            try:
                r = requests.get(f"{scheme}://{host}:{port}/{base}/ScannerCapabilities",
                                 timeout=2, verify=False)
                if r.ok and b"ScannerCapabilities" in r.content:
                    found.append((host, port, base))
                    break
            except requests.RequestException:
                continue
    return found


def scan_networks(nets: list[ipaddress.IPv4Network] | None = None,
                  progress: Callable[[int, int], None] | None = None,
                  workers: int = 96) -> list[tuple[str, int, str]]:
    nets = nets if nets is not None else local_subnets()
    hosts = [str(h) for n in nets for h in n.hosts()]
    result: list[tuple[str, int, str]] = []
    log.info("Сканування мережі: %s (%d адрес)", ", ".join(map(str, nets)), len(hosts))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, res in enumerate(pool.map(probe, hosts), 1):
            result.extend(res)
            if progress and (i % 16 == 0 or i == len(hosts)):
                progress(i, len(hosts))
    return result
