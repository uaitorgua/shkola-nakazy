"""Локальний тест перевірки оновлень: http-сервер на 127.0.0.1 віддає version.json і «інсталятор»."""
import hashlib, http.server, json, os, sys, tempfile, threading
from functools import partial
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
d = Path(tempfile.mkdtemp())
setup = "NakazyShkola-Setup-9.9.9.exe"
(d / setup).write_bytes(b"MZ" + os.urandom(3_000_000))
md5 = hashlib.md5((d / setup).read_bytes()).hexdigest()
(d / "version.json").write_text(json.dumps({"version": "9.9.9", "setup": setup, "md5": {setup: md5}}), encoding="utf-8")
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), partial(http.server.SimpleHTTPRequestHandler, directory=str(d)))
threading.Thread(target=srv.serve_forever, daemon=True).start()
os.environ["NAKAZY_UPDATE_BASE"] = f"http://127.0.0.1:{srv.server_port}/"
sys.path.insert(0, str(ROOT))
from nakazy import updater, __version__  # noqa: E402

assert updater.is_newer("1.1.10", "1.1.9") and not updater.is_newer(__version__)
info = updater.check(); assert info and info["version"] == "9.9.9", info
seen = []
p = updater.download(info, lambda a, b: seen.append(a)); assert Path(p).read_bytes() == (d / setup).read_bytes() and seen
os.remove(p)
# підмінений файл — відмова
info["md5"][setup] = "0" * 32
try:
    updater.download(info); raise SystemExit("md5 не перевірено")
except IOError:
    pass
# та сама версія — оновлення немає
(d / "version.json").write_text(json.dumps({"version": __version__, "setup": f"NakazyShkola-Setup-{__version__}.exe"}), encoding="utf-8")
assert updater.check() is None
# шкідливе ім'я файлу — ігнор
(d / "version.json").write_text(json.dumps({"version": "9.9.9", "setup": "..\\evil.exe"}), encoding="utf-8")
assert updater.check() is None
# сайт недоступний — без помилки
os.environ["NAKAZY_UPDATE_BASE"] = "http://127.0.0.1:1/"
import importlib; importlib.reload(updater); assert updater.check(timeout=2) is None
print("update OK")
