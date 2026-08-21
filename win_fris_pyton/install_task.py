"""Kompatibilitasi inditoszkript: ``python install_task.py [install|remove|start|stop]``.

Uj kod hasznalja inkabb: ``python -m refreshswitcher install``.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from refreshswitcher.cli import main

_ALIASES = {"install", "remove", "start", "stop"}

if __name__ == "__main__":
    argv = sys.argv[1:]
    if not argv or argv[0].lower() not in _ALIASES:
        sys.exit(1)
    sys.exit(main([argv[0].lower(), *argv[1:]]))
