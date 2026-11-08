"""Перевірка зібраного EXE: стартує на тимчасовій базі, тримається 12 с, у журналі немає помилок."""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

exe = Path(sys.argv[1] if len(sys.argv) > 1 else "dist/NakazyShkola.exe").resolve()
env = dict(os.environ, APPDATA=tempfile.mkdtemp())  # не чіпаємо справжню базу користувача
log = Path(env["APPDATA"]) / "nakazy-shkola" / "nakazy.log"
proc = subprocess.Popen([str(exe)], env=env)
time.sleep(12)
alive = proc.poll() is None
if alive:
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    proc.wait(10); time.sleep(1.5)
text = log.read_text(encoding="utf-8", errors="ignore") if log.exists() else ""
errors = [l for l in text.splitlines() if "ERROR" in l or "Traceback" in l]
if not alive:
    print(f"[EXE] завершився з кодом {proc.returncode}\n{text[-2000:]}"); sys.exit(1)
if errors:
    print("[EXE] помилки в журналі:\n" + "\n".join(errors)); sys.exit(1)
if not (Path(env["APPDATA"]) / "nakazy-shkola" / "nakazy.db").exists():
    print("[EXE] база не створена"); sys.exit(1)
print("[EXE] запуск OK")
