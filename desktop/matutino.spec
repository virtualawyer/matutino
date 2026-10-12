# PyInstaller spec for the desktop app, on macOS (Matutino.app) or Windows
# (Matutino\Matutino.exe). Run from the repository root:
#     pyinstaller --noconfirm desktop/matutino.spec
import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = os.path.dirname(SPECPATH)
sys.path.insert(0, ROOT)
from matutino import VERSION  # noqa: E402

MAC = sys.platform == "darwin"
datas = [(os.path.join(ROOT, "matutino", "languages"), "matutino/languages"),
         (os.path.join(ROOT, "matutino", "static"), "matutino/static")]
for pkg in ("trafilatura", "justext", "htmldate", "courlan", "tzdata", "certifi"):
    datas += collect_data_files(pkg)
hidden = collect_submodules("tzdata") + ["pystray._darwin" if MAC else "pystray._win32"]

a = Analysis([os.path.join(SPECPATH, "launch.py")], pathex=[ROOT], datas=datas, hiddenimports=hidden,
             excludes=["tkinter", "unittest", "pydoc", "test"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Matutino", console=False,
          icon=os.path.join(SPECPATH, "icon", "Matutino.icns" if MAC else "Matutino.ico"))
coll = COLLECT(exe, a.binaries, a.datas, name="Matutino")
if MAC:
    app = BUNDLE(coll, name="Matutino.app", icon=os.path.join(SPECPATH, "icon", "Matutino.icns"),
                 bundle_identifier="io.github.virtualawyer.matutino", version=VERSION,
                 info_plist={"LSUIElement": True,            # menu bar only, no Dock icon
                             "CFBundleDisplayName": "Matutino",
                             "CFBundleShortVersionString": VERSION, "CFBundleVersion": VERSION,
                             "LSMinimumSystemVersion": "11.0",
                             "NSHumanReadableCopyright": "Free software, AGPL-3.0"})
