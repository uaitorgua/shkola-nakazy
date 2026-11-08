"""Низькорівнева перевірка мережного зв'язку."""

import socket
import subprocess
import sys

from ..config import CONNECT_TIMEOUT_S


def tcp_open(host: str, port: int, timeout: float = CONNECT_TIMEOUT_S) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def ping(host: str, timeout_ms: int = 1000) -> bool:
    if sys.platform == "win32":
        cmd = ["ping", "-n", "1", "-w", str(timeout_ms), host]
        flags = subprocess.CREATE_NO_WINDOW
    else:
        cmd = ["ping", "-c", "1", "-W", str(max(1, timeout_ms // 1000)), host]
        flags = 0
    try:
        return subprocess.run(cmd, capture_output=True, timeout=timeout_ms / 1000 + 2,
                              creationflags=flags).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def split_host(text: str, default_port: int) -> tuple[str, int]:
    text = text.strip()
    if text.count(":") == 1:
        host, port = text.split(":")
        return host.strip(), int(port)
    return text, default_port
