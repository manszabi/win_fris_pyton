"""Futo jatekok felismerese processznev alapjan.

**Prioritas: az eloszor elinditott jatek nyer.** Ha jatek kozben elindul egy
masodik ismert jatek, a frekvencia *nem* valtozik. Amint az elso jatek bezarul,
a sorban kovetkezo (masodikkent inditott) jatek beallitasa lep ervenybe.

Ezt a processz letrehozasi ideje (``create_time``) donti el, nem a felismeres
sorrendje -- igy az eredmeny akkor is helyes, ha a program *kozben* indul el,
amikor mar tobb jatek fut.

**Processzornevek gyorsitotara.** Ez a modul fut a leggyakrabban (alapbeallitas
szerint 5 masodpercenkent), ezert itt szamit a legtobbet a takarekossag. A
``psutil`` a processznevet Windowson ``OpenProcess`` +
``QueryFullProcessImageName`` parossal szerzi meg: egy atlagos gepen 300+ futo
processz eseten ez koronkent 300+ rendszerhivas, gyakorlatilag mindig ugyanazzal
az eredmennyel. A nevet ezert processzenkent **egyszer** kerdezzuk le, es a
``(pid, inditasi ido)`` kulcs alatt megjegyezzuk -- a kulcs masodik fele vedi ki
a pid-ujrahasznositast. Igy koronkent csak az *ujonnan indult* processzek nevet
kell lekerdezni.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass

import psutil

logger = logging.getLogger(__name__)

#: Ha a processz inditasi ideje nem kerdezheto le, a sor vegere kerul.
_UNKNOWN_START = float("inf")


class _NameCache:
    """``(pid, inditasi ido)`` -> kisbetus processznev.

    Minden bejaras egy *uj* szotarat epit fel, es a vegen azt teszi a regi
    helyere: igy a megszunt processzek bejegyzesei maguktol kiesnek, es a
    gyorsitotar nem nohet a vegtelensegig.
    """

    __slots__ = ("_names",)

    def __init__(self) -> None:
        self._names: dict[tuple[int, float | None], str] = {}

    def __len__(self) -> int:
        return len(self._names)

    def get(self, key: tuple[int, float | None]) -> str | None:
        return self._names.get(key)

    def replace(self, names: dict[tuple[int, float | None], str]) -> None:
        self._names = names

    def clear(self) -> None:
        self._names = {}


_name_cache = _NameCache()


def reset_name_cache() -> None:
    """Uriti a processznev-gyorsitotarat (tesztekhez es diagnosztikahoz)."""
    _name_cache.clear()


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
        # Nincs mit keresni: a gyorsitotarat sem tartjuk fenn feleslegesen.
        _name_cache.clear()
        return []

    current: dict[tuple[int, float | None], str] = {}
    matches: list[GameMatch] = []

    # Csak a pid-et es az inditasi idot kerjuk el: mindketto olcso (a psutil a
    # sajat Process-peldanyaiban gyorsitotarazza), a *nevet* viszont csak akkor
    # kerdezzuk le, ha meg nem ismerjuk.
    for proc in psutil.process_iter(["pid", "create_time"]):
        try:
            info = proc.info
            pid = int(info["pid"])
            started_at = info.get("create_time")
            key = (pid, started_at)
            name = _name_cache.get(key)
            if name is None:
                raw_name = proc.name()
                name = raw_name.lower() if raw_name else ""
        except (psutil.Error, AttributeError, KeyError, TypeError, ValueError):
            # A processz kozben meghalt, vagy nincs jogosultsagunk hozza.
            continue

        current[key] = name
        rate = games.get(name)
        if rate is None:
            continue

        matches.append(
            GameMatch(
                process_name=name,
                refresh_rate=rate,
                pid=pid,
                started_at=float(started_at) if started_at is not None else _UNKNOWN_START,
            )
        )

    _name_cache.replace(current)

    if len(matches) > 1:
        matches.sort(key=lambda match: match.priority_key)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "Tobb jatek fut (%s); az eloszor inditott ervenyes: %s",
                ", ".join(match.process_name for match in matches),
                matches[0].process_name,
            )
    return matches


def find_active_game(games: Mapping[str, int]) -> GameMatch | None:
    """Az *eloszor elinditott* futo jatek, vagy ``None``, ha egyik sem fut."""
    running = iter_running_games(games)
    return running[0] if running else None
