"""Futo jatekok felismerese processznev alapjan.

**Prioritas: az eloszor elinditott jatek nyer.** Ha jatek kozben elindul egy
masodik ismert jatek, a frekvencia *nem* valtozik. Amint az elso jatek bezarul,
a sorban kovetkezo (masodikkent inditott) jatek beallitasa lep ervenybe.

Ezt a processz letrehozasi ideje (``create_time``) donti el, nem a felismeres
sorrendje -- igy az eredmeny akkor is helyes, ha a program *kozben* indul el,
amikor mar tobb jatek fut.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass

import psutil

logger = logging.getLogger(__name__)

#: Ha a processz inditasi ideje nem kerdezheto le, a sor vegere kerul.
_UNKNOWN_START = float("inf")


@dataclass(frozen=True, slots=True)
class GameMatch:
    """Egy felismert, futo jatek."""

    process_name: str  # normalizalt (kisbetus) nev, pl. 'cs2.exe'
    refresh_rate: int
    pid: int = 0
    started_at: float = _UNKNOWN_START

    @property
    def display_name(self) -> str:
        """Megjelenitesre szant nev, ``.exe`` nelkul."""
        return self.process_name[:-4] if self.process_name.endswith(".exe") else self.process_name

    @property
    def priority_key(self) -> tuple[float, int]:
        """Rendezesi kulcs: korabbi inditas elorebb; azonossag eseten a PID dont."""
        return (self.started_at, self.pid)


def iter_running_games(games: Mapping[str, int]) -> list[GameMatch]:
    """Az osszes futo ismert jatek, inditasi ido szerint novekvo sorrendben."""
    if not games:
        return []

    matches: list[GameMatch] = []
    for proc in psutil.process_iter(["pid", "name", "create_time"]):
        try:
            info = proc.info
            raw_name = info.get("name")
        except (psutil.Error, AttributeError):
            # A processz kozben meghalt, vagy nincs jogosultsagunk hozza.
            continue
        if not raw_name:
            continue
        name = raw_name.lower()
        rate = games.get(name)
        if rate is None:
            continue

        started_at = info.get("create_time")
        matches.append(
            GameMatch(
                process_name=name,
                refresh_rate=rate,
                pid=int(info.get("pid") or 0),
                started_at=float(started_at) if started_at is not None else _UNKNOWN_START,
            )
        )

    matches.sort(key=lambda match: match.priority_key)
    return matches


def find_active_game(games: Mapping[str, int]) -> GameMatch | None:
    """Az *eloszor elinditott* futo jatek, vagy ``None``, ha egyik sem fut."""
    running = iter_running_games(games)
    if not running:
        return None
    if len(running) > 1:
        logger.debug(
            "Tobb jatek fut (%s); az eloszor inditott ervenyes: %s",
            ", ".join(match.process_name for match in running),
            running[0].process_name,
        )
    return running[0]
