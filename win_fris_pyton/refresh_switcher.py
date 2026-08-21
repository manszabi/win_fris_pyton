"""Kompatibilitasi inditoszkript: ``python refresh_switcher.py`` -> allapotkiiras.

Uj kod hasznalja inkabb: ``python -m refreshswitcher status``.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from refreshswitcher.cli import main

if __name__ == "__main__":
    sys.exit(main(["status", *sys.argv[1:]]))
