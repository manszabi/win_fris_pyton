# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build-leiras.

A ``config.json`` **szandekosan nincs** az exe-be csomagolva: a program az exe
*melletti* config.json-t olvassa, igy a felhasznalo szerkesztheti a
beallitasokat ujraforditas nelkul. (A regi build mindkettot csinalta, ami
zavaro volt: a beagyazott peldany sosem ervenyesult.)
"""

block_cipher = None

a = Analysis(
    ["tray.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        "pystray._win32",   # a backendet a pystray futasidoben valasztja ki
        "PIL._tkinter_finder",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "unittest", "pydoc", "doctest", "pytest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="RefreshSwitcher",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # a UPX-tomorites gyakran hamis virusjelzest valt ki
    runtime_tmpdir=None,
    console=False,      # nincs konzolablak
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
