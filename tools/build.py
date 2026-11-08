"""Повна збірка «Накази ШКОЛА»: залежності → OCR-моделі → тести → версія → PyInstaller → перевірка EXE →
підпис ГС «УАІТ» → інсталятор (Inno Setup).

python tools\\build.py [notest] [trust] [noinstaller] [check]
  check – лише перевірити, що все потрібне для збірки є (нічого не збирає).
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
args = {a.lower() for a in sys.argv[1:]}
NAME = "NakazyShkola"
EXE = ROOT / "dist" / f"{NAME}.exe"
ISCC = [p for p in (Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
                    Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe")) if p.exists()]
TESS = ROOT / "ocr" / "tessdata"
SCANNER_TESS = ROOT.parent / "Сканер-ШКОЛА" / "ocr" / "tessdata"
TESTS = ["test_db", "test_templates", "test_people", "test_oldimport", "test_export", "test_gui", "test_stress"]


def step(n: int, title: str, cmd: list[str], log: Path | None = None) -> None:
    print(f"[{n}/7] {title}", flush=True)
    if log:
        with log.open("w", encoding="utf-8") as f:
            r = subprocess.run(cmd, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT)
        if r.returncode:
            print("\n".join(log.read_text(encoding="utf-8", errors="ignore").splitlines()[-30:]))
    else:
        r = subprocess.run(cmd, cwd=ROOT)
    if r.returncode:
        sys.exit(f"\n[ПОМИЛКА] Крок «{title}» завершився з кодом {r.returncode}. Збірку зупинено.")


def ocr_models() -> None:
    """Офлайн-моделі Tesseract (ukr, eng, osd): беремо з «Сканер ШКОЛА», без інтернету."""
    need = [f"{l}.traineddata" for l in ("ukr", "eng", "osd")]
    if all((TESS / f).exists() for f in need):
        return
    if all((SCANNER_TESS / f).exists() for f in need):
        TESS.mkdir(parents=True, exist_ok=True)
        for f in need:
            shutil.copy2(SCANNER_TESS / f, TESS / f)
        return
    sys.exit("[ПОМИЛКА] Немає моделей OCR. Скопіюйте ocr/tessdata зі «Сканер ШКОЛА» (python tools/get_ocr.py там).")


if "check" in args:
    missing = []
    for mod in ("PyInstaller", "PySide6", "docx", "openpyxl", "pypdf", "pypdfium2", "tesserocr"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    print("Python-модулі:", "OK" if not missing else f"бракує {missing}")
    print("OCR-моделі:", "OK" if (TESS / "ukr.traineddata").exists() or (SCANNER_TESS / "ukr.traineddata").exists() else "немає")
    print("Inno Setup:", ISCC[0] if ISCC else "не знайдено (winget install JRSoftware.InnoSetup)")
    print("Сертифікат:", "OK" if (ROOT / "certs" / "UAIT_CodeSigning.pfx").exists() or
          (ROOT.parent / "Сканер-ШКОЛА" / "certs" / "UAIT_CodeSigning.pfx").exists() else "немає")
    sys.exit(0)

step(1, "Залежності", [PY, "-m", "pip", "install", "-q", "--disable-pip-version-check", "-r", "requirements.txt"])
print("[1/7] OCR-моделі", flush=True); ocr_models()
if "notest" not in args:
    for t in TESTS:
        step(2, f"Тести: {t}", [PY, f"tests/{t}.py"], ROOT / "build" / f"test_{t}.log")
if EXE.exists():
    try:
        open(EXE, "r+b").close()
    except PermissionError:
        sys.exit(f"[ПОМИЛКА] dist/{NAME}.exe відкритий. Закрийте «Накази ШКОЛА» і повторіть.")
(ROOT / "build").mkdir(exist_ok=True)
step(3, "Властивості файлу", [PY, "tools/version_info.py"])
step(4, "PyInstaller", [
    PY, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
    "--name", NAME, "--icon", "assets/logo.ico", "--version-file", "build/version_info.txt",
    "--add-data", "assets;assets", "--add-data", "LICENSE.txt;.", "--add-data", "ocr;ocr",
    "--hidden-import", "win32timezone", "--collect-all", "pypdfium2", "--collect-all", "pypdfium2_raw",
    "--collect-all", "tesserocr", "--collect-submodules", "docx", "--collect-data", "docx",
    "--collect-submodules", "openpyxl", "--hidden-import", "PySide6.QtPrintSupport",
    *[x for m in ("tkinter", "matplotlib", "pandas", "scipy", "torch", "onnxruntime", "tokenizers", "cv2",
                  "zeroconf", "reportlab", "PySide6.QtWebEngineCore", "PySide6.Qt3DCore", "PySide6.QtQuick",
                  "PySide6.QtQml", "PySide6.QtMultimedia", "IPython")
      for x in ("--exclude-module", m)],
    "main.py"], ROOT / "build" / "pyinstaller.log")
step(5, "Перевірка запуску EXE", [PY, "tools/exe_smoke.py", str(EXE)])
if not (ROOT / "certs" / "UAIT_CodeSigning.pfx").exists():
    src = ROOT.parent / "Сканер-ШКОЛА" / "certs"
    if (src / "UAIT_CodeSigning.pfx").exists():  # той самий сертифікат УАІТ; certs/ у .gitignore
        shutil.copytree(src, ROOT / "certs", dirs_exist_ok=True)
sign = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "tools/sign.ps1",
        "-ExePath", f"dist/{NAME}.exe"] + (["-InstallTrust"] if "trust" in args else [])
step(6, "Підпис сертифікатом ГС «УАІТ»", sign)
if "noinstaller" not in args:
    if ISCC:
        sys.path.insert(0, str(ROOT))
        from nakazy import __version__
        step(7, "Інсталятор (Inno Setup)", [str(ISCC[0]), "/Q", f"/DAppVersion={__version__}",
                                            str(ROOT / "packaging" / "installer.iss")], ROOT / "build" / "installer.log")
        setup = ROOT / "dist" / f"{NAME}-Setup-{__version__}.exe"
        step(7, "Підпис інсталятора", ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                                       "tools/sign.ps1", "-ExePath", str(setup)])
        print(f"Інсталятор: {setup}  ({setup.stat().st_size / 1e6:.1f} МБ)")
    else:
        print("[7/7] Inno Setup не знайдено – інсталятор пропущено (winget install JRSoftware.InnoSetup)")
print(f"\nГОТОВО: {EXE}  ({EXE.stat().st_size / 1e6:.1f} МБ)")
