"""Генерує build/version_info.txt (властивості EXE: видавець, версія, опис)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from nakazy import __version__  # noqa: E402

PUB = "Громадська спілка «Українська асоціація інноваційних технологій»"
v = tuple(int(x) for x in __version__.split(".")) + (0,)
txt = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={v}, prodvers={v}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('042204B0', [
    StringStruct('CompanyName', '{PUB}'),
    StringStruct('FileDescription', 'Накази ШКОЛА – реєстр і редактор наказів закладу освіти'),
    StringStruct('FileVersion', '{__version__}'),
    StringStruct('InternalName', 'NakazyShkola'),
    StringStruct('LegalCopyright', '© {PUB}'),
    StringStruct('OriginalFilename', 'NakazyShkola.exe'),
    StringStruct('ProductName', 'Накази ШКОЛА'),
    StringStruct('ProductVersion', '{__version__}')])]),
  VarFileInfo([VarStruct('Translation', [0x0422, 1200])])])
"""
(ROOT / "build").mkdir(exist_ok=True)
(ROOT / "build" / "version_info.txt").write_text(txt, encoding="utf-8")
print("build/version_info.txt готово")
