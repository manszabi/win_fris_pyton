"""Inditoszkript a tray alkalmazashoz: ``pythonw tray.py``.

Ez a fajl szandekosan minimalis. A tenyleges logika a ``refreshswitcher``
csomagban van; ez az inditopont azert marad meg, mert a mar telepitett
Task Scheduler feladatok erre az utvonalra mutatnak.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Kozvetlen szkript-inditaskor (pythonw tray.py) a csomag melletti mappa
# kerul a sys.path-ra, igy az import mukodik telepites nelkul is.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from refreshswitcher.cli import main

if __name__ == "__main__":
    sys.exit(main(["tray", *sys.argv[1:]]))
