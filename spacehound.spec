# -*- mode: python ; coding: utf-8 -*-
# Build with:  pyinstaller spacehound.spec --noconfirm --clean
from PyInstaller.utils.hooks import collect_data_files

datas = [("ui", "ui")]
datas += collect_data_files("webview")

a = Analysis(
    ["run_spacehound.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "clr",
        "webview.platforms.edgechromium",
        "webview.platforms.winforms",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "PIL", "numpy", "pytest", "unittest.mock"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="SpaceHound",
    debug=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    icon="assets/icon.ico",
    version="version_info.txt",
)
