# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build-leiras (PyInstaller 6.x).

A ``config.json`` **szandekosan nincs** az exe-be csomagolva: a program az exe
*melletti* config.json-t olvassa, igy a felhasznalo szerkesztheti a
beallitasokat ujraforditas nelkul. (A regi build mindkettot csinalta, ami
zavaro volt: a beagyazott peldany sosem ervenyesult.)
"""

a = Analysis(
    ["tray.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        # A pystray futasidoben valasztja ki a backendet, ezert az import-graf
        # nem talalja meg statikusan.
        "pystray._win32",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Csak olyat zarunk ki, amirol biztosan tudjuk, hogy nem kell. Egy tul
    # agressziv lista futasidoben, konzol nelkul jelentkezo ImportError-t okoz.
    excludes=["tkinter", "unittest", "pydoc", "doctest", "pytest"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="RefreshSwitcher",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # a UPX-tomorites gyakran hamis virusjelzest valt ki
    runtime_tmpdir=None,
    console=False,  # nincs konzolablak
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
