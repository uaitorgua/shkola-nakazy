"""Збирає MSIX для Microsoft Store з dist\\NakazyShkola.exe.

Store підписує пакет сам — свій сертифікат для Store не потрібен.
Для локальної перевірки: --sign підпише MSIX сертифікатом ГС «УАІТ» (Publisher тоді має збігатися з CN сертифіката).
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "packaging"
STAGE = ROOT / "build" / "msix"
OUT = ROOT / "dist" / "NakazyShkola.msix"
SDK = Path(r"C:\Program Files (x86)\Windows Kits\10\bin")


def tool(name: str) -> Path:
    found = sorted(SDK.glob(f"*/x64/{name}"))
    if not found:
        sys.exit(f"Не знайдено {name}. Встановіть Windows SDK.")
    return found[-1]


def main() -> None:
    ident = json.loads((PKG / "store_identity.json").read_text(encoding="utf-8"))
    if "ЗАПОВНИТИ" in json.dumps(ident, ensure_ascii=False) and "--local" not in sys.argv:
        sys.exit("Заповніть packaging/store_identity.json даними з Partner Center (або --local для тестового пакета).")
    if "--local" in sys.argv:
        ident.update(IdentityName="UAIT.NakazyShkola.Local", Publisher="CN=ГС УАІТ, O=ГС УАІТ, C=UA", DisplayName="Накази ШКОЛА")
    exe = ROOT / "dist" / "NakazyShkola.exe"
    if not exe.exists():
        sys.exit("Спершу build.bat")

    shutil.rmtree(STAGE, ignore_errors=True)
    (STAGE / "Assets").mkdir(parents=True)
    shutil.copy2(exe, STAGE)
    assets = ROOT / "build" / "msix_assets"          # tools/make_icon.py: targetsize, unplated, Wide, Splash
    if not (assets / "Square44x44Logo.png").exists():
        subprocess.run([sys.executable, str(ROOT / "tools" / "make_icon.py")], check=True)
    for f in assets.glob("*.png"):
        shutil.copy2(f, STAGE / "Assets" / f.name)
    manifest = (PKG / "AppxManifest.template.xml").read_text(encoding="utf-8")
    for k, v in ((k, v) for k, v in ident.items() if k != "StoreId"):
        manifest = manifest.replace("{" + k + "}", v)
    (STAGE / "AppxManifest.xml").write_text(manifest, encoding="utf-8")

    # resources.pri: без нього Windows ігнорує Square44x44Logo.targetsize-*/altform-unplated
    # (панель задач, «Пуск», Провідник показували б 44-піксельну іконку з плашкою)
    pri_cfg = ROOT / "build" / "priconfig.xml"
    subprocess.run([str(tool("makepri.exe")), "createconfig", "/cf", str(pri_cfg), "/dq", "uk-UA", "/o"],
                   check=True, stdout=subprocess.DEVNULL)
    subprocess.run([str(tool("makepri.exe")), "new", "/pr", str(STAGE), "/cf", str(pri_cfg),
                    "/of", str(STAGE / "resources.pri"), "/mn", str(STAGE / "AppxManifest.xml"), "/o"],
                   check=True, stdout=subprocess.DEVNULL)

    OUT.unlink(missing_ok=True)
    subprocess.run([str(tool("makeappx.exe")), "pack", "/d", str(STAGE), "/p", str(OUT), "/o"], check=True)
    print(f"MSIX: {OUT}")
    if "--sign" in sys.argv:
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                        str(ROOT / "tools" / "sign.ps1"), "-ExePath", str(OUT)], check=True)


if __name__ == "__main__":
    main()
