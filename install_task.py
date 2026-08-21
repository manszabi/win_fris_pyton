"""Kompatibilitasi inditoszkript: ``python install_task.py [install|remove|start|stop]``.

Uj kod hasznalja inkabb: ``python -m refreshswitcher install``.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from refreshswitcher.cli import main

_ALIASES = ("install", "remove", "start", "stop")

USAGE = f"Hasznalat: python install_task.py [{'|'.join(_ALIASES)}]"


def run(argv: list[str]) -> int:
    """A shim belepesi pontja; tesztelhetoseg miatt kulon fuggveny."""
    if not argv or argv[0].lower() not in _ALIASES:
        print(USAGE, file=sys.stderr)
        return 1
    return main([argv[0].lower(), *argv[1:]])


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
