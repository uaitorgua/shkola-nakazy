"""Локальний тест: http-сервер віддає відповідь «каталогу Microsoft» з різними версіями."""
import http.server, json, os, sys, threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
state = {"body": b"{}"}
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(state.get("code", 200)); self.end_headers(); self.wfile.write(state["body"])
    def log_message(self, *a): pass
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
os.environ["NAKAZY_CATALOG_URL"] = f"http://127.0.0.1:{srv.server_port}/"
sys.path.insert(0, str(ROOT))
from nakazy import updater, __version__  # noqa: E402

def cat(*vers, name=updater.PACKAGE_NAME):
    pk = [{"PackageFullName": f"{name}_{v}_x64__abc"} for v in vers]
    state["body"] = json.dumps({"Product": {"DisplaySkuAvailabilities": [{"Sku": {"Properties": {"Packages": pk}}}]}}).encode()

assert updater.is_newer("1.1.10.0", "1.1.9") and not updater.is_newer(__version__ + ".0")
cat("1.0.0.0", "9.9.9.0"); assert updater.check() == {"version": "9.9.9.0"}, updater.check()
cat(__version__ + ".0"); assert updater.check() is None, "та сама версія"
cat("9.9.9.0", name="Other.App"); assert updater.check() is None, "чужий пакет"
state["body"] = b"{}"; assert updater.check() is None, "програми немає в Store"
state["code"] = 404; assert updater.check() is None, "404 від каталогу"; state["code"] = 200
state["body"] = b"not json"; assert updater.check() is None, "зіпсована відповідь"
os.environ["NAKAZY_CATALOG_URL"] = "http://127.0.0.1:1/"
import importlib; importlib.reload(updater); assert updater.check(timeout=2) is None, "без мережі"
print("update OK")
