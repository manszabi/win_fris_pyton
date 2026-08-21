"""Konfiguracio betoltese, validalasa es biztonsagos ujratoltese.

A regi implementacio minden ciklusban nyersen beolvasta a JSON-t, es barmilyen
hianyzo kulcs ``KeyError``-t dobott a munkaszalban. Itt minden ertek validalt,
es hiba eseten az utolso ervenyes beallitas marad ervenyben.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any

logger = logging.getLogger(__name__)

#: Ennel gyakoribb ellenorzes felesleges CPU-t eget, ritkabb pedig hasznalhatatlan.
MIN_CHECK_INTERVAL = 0.5
MAX_CHECK_INTERVAL = 3600.0
#: Josagos also/felso korlat: valos kijelzo nem megy 20 Hz ala vagy 1000 Hz fole.
MIN_REFRESH_RATE = 20
MAX_REFRESH_RATE = 1000

_KNOWN_KEYS = frozenset(
    {
        "monitor",
        "default_refresh_rate",
        "check_interval",
        "games",
        "restore_on_exit",
        "enforce_default",
        "log_level",
    }
)


class ConfigError(ValueError):
    """Ervenytelen vagy olvashatatlan konfiguracio."""


#: Elso inditaskor ez keletkezik, ha nincs config.json. Igy az exe dupla
#: kattintasra sem "nem csinal semmit", hanem azonnal mukodokepes.
DEFAULT_CONFIG: dict[str, Any] = {
    "monitor": 1,
    "default_refresh_rate": 60,
    "check_interval": 5,
    "enforce_default": True,
    "restore_on_exit": True,
    "log_level": "WARNING",
    "games": {
        "example-game.exe": 144,
    },
}


def write_default_config(path: Path) -> bool:
    """Letrehozza az alapertelmezett config.json-t, ha meg nem letezik.

    ``True``, ha most keszult el. Atomi irast hasznal (ideiglenes fajl +
    atnevezes), igy a menet kozben olvaso figyelo sosem lat felig kesz fajlt.
    """
    if path.exists():
        return False
    temporary = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            json.dumps(DEFAULT_CONFIG, indent=4, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        temporary.replace(path)
    except OSError:
        logger.warning("Nem sikerult letrehozni az alapertelmezett configot: %s", path, exc_info=True)
        with contextlib.suppress(OSError):
            temporary.unlink()
        return False
    logger.warning("Alapertelmezett konfiguracio letrehozva: %s", path)
    return True


def _normalise_process_name(name: str) -> str:
    """``"CS2"`` -> ``"cs2.exe"``; a Windows processz-nevek kis/nagybetu-fuggetlenek."""
    cleaned = name.strip().strip('"').replace("/", "\\")
    # Csak a fajlnev szamit, ha a felhasznalo teljes utvonalat masolt be.
    cleaned = cleaned.rsplit("\\", 1)[-1]
    lowered = cleaned.lower()
    if not lowered:
        raise ConfigError("A 'games' szekcio ures jateknevet tartalmaz.")
    if not lowered.endswith(".exe"):
        lowered += ".exe"
    return lowered


def _as_int(value: Any, key: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"A '{key}' erteknek szamnak kell lennie, kapott: {value!r}")
    if isinstance(value, float) and not value.is_integer():
        raise ConfigError(f"A '{key}' erteknek egesz szamnak kell lennie, kapott: {value!r}")
    return int(value)


def _validate_rate(value: Any, key: str) -> int:
    rate = _as_int(value, key)
    if not MIN_REFRESH_RATE <= rate <= MAX_REFRESH_RATE:
        raise ConfigError(
            f"A '{key}' erteke {rate} Hz, ami a megengedett "
            f"{MIN_REFRESH_RATE}-{MAX_REFRESH_RATE} Hz tartomanyon kivul esik."
        )
    return rate


@dataclass(frozen=True, slots=True)
class Config:
    """Validalt, valtoztathatatlan beallitas-pillanatkep."""

    #: Monitor sorszama (1-tol) vagy eszkoznev (pl. ``\\\\.\\DISPLAY2``).
    monitor: int | str = 1
    #: Ez a frekvencia ervenyes, ha egyetlen ismert jatek sem fut.
    default_refresh_rate: int = 60
    #: Ket ellenorzes kozott eltelt masodperc.
    check_interval: float = 5.0
    #: Normalizalt (kisbetus, ``.exe``-re vegzodo) processznev -> Hz.
    games: Mapping[str, int] = field(default_factory=dict)
    #: Kilepeskor allitsa-e vissza az alapertelmezett frekvenciat.
    restore_on_exit: bool = True
    #: Jatek nelkul is kenyszeritse-e az alapertelmezett frekvenciat.
    #: ``True`` eseten alvas/hibernalas utani Windows-visszaallitast is korrigal.
    enforce_default: bool = True
    #: Log reszletesseg: DEBUG / INFO / WARNING / ERROR.
    log_level: str = "WARNING"

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> Config:
        """Validal egy nyers dict-et. Hiba eseten :class:`ConfigError`."""
        if not isinstance(raw, Mapping):
            raise ConfigError("A config.json gyokerelemenek JSON objektumnak kell lennie.")

        unknown = set(raw) - _KNOWN_KEYS
        if unknown:
            # Nem hiba (elore-kompatibilitas), de szinte mindig elgepeles.
            logger.warning("Ismeretlen beallitas(ok) a config.json-ban: %s", sorted(unknown))

        monitor_raw = raw.get("monitor", 1)
        monitor: int | str
        if isinstance(monitor_raw, str):
            monitor = monitor_raw.strip()
            if not monitor:
                raise ConfigError("A 'monitor' ertek ures szoveg.")
        else:
            monitor = _as_int(monitor_raw, "monitor")
            if monitor < 1:
                raise ConfigError(f"A 'monitor' erteke 1-tol szamozodik, kapott: {monitor}")

        default_rate = _validate_rate(raw.get("default_refresh_rate", 60), "default_refresh_rate")

        interval_raw = raw.get("check_interval", 5.0)
        if isinstance(interval_raw, bool) or not isinstance(interval_raw, (int, float)):
            raise ConfigError(f"A 'check_interval' erteknek szamnak kell lennie, kapott: {interval_raw!r}")
        interval = float(interval_raw)
        if not MIN_CHECK_INTERVAL <= interval <= MAX_CHECK_INTERVAL:
            raise ConfigError(
                f"A 'check_interval' erteke {interval}s, ami a megengedett "
                f"{MIN_CHECK_INTERVAL}-{MAX_CHECK_INTERVAL}s tartomanyon kivul esik."
            )

        games_raw = raw.get("games", {})
        if not isinstance(games_raw, Mapping):
            raise ConfigError("A 'games' erteknek JSON objektumnak kell lennie.")
        games: dict[str, int] = {}
        for name, rate in games_raw.items():
            if not isinstance(name, str):
                raise ConfigError(f"A 'games' kulcsainak szovegnek kell lenniuk, kapott: {name!r}")
            key = _normalise_process_name(name)
            value = _validate_rate(rate, f"games.{name}")
            if key in games and games[key] != value:
                raise ConfigError(
                    f"A '{key}' processz tobbszor szerepel a 'games' alatt, eltero "
                    f"frekvenciaval ({games[key]} Hz es {value} Hz)."
                )
            games[key] = value

        log_level_raw = raw.get("log_level", "WARNING")
        if not isinstance(log_level_raw, str):
            raise ConfigError(f"A 'log_level' erteknek szovegnek kell lennie, kapott: {log_level_raw!r}")
        log_level = log_level_raw.strip().upper()
        if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ConfigError(f"Ismeretlen 'log_level': {log_level_raw!r}")

        return cls(
            monitor=monitor,
            default_refresh_rate=default_rate,
            check_interval=interval,
            games=MappingProxyType(games),
            restore_on_exit=bool(raw.get("restore_on_exit", True)),
            enforce_default=bool(raw.get("enforce_default", True)),
            log_level=log_level,
        )

    @classmethod
    def load(cls, path: Path) -> Config:
        """Beolvassa es validalja a megadott JSON fajlt."""
        try:
            text = path.read_text(encoding="utf-8-sig")
        except FileNotFoundError as exc:
            raise ConfigError(f"A konfiguracios fajl nem talalhato: {path}") from exc
        except OSError as exc:
            raise ConfigError(f"A konfiguracios fajl nem olvashato ({path}): {exc}") from exc

        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ConfigError(
                f"Ervenytelen JSON a(z) {path} fajlban a(z) {exc.lineno}. sor {exc.colno}. "
                f"oszlopanal: {exc.msg}"
            ) from exc

        return cls.from_mapping(raw)


class ConfigWatcher:
    """Igeny szerint ujratolti a configot, es hiba eseten megtartja az utolso jot.

    A fajlt csak akkor olvassa be ujra, ha a merete vagy a modositasi ideje
    valtozott, igy a masodpercenkenti ellenorzes nem general folyamatos I/O-t.
    """

    def __init__(self, path: Path, *, fallback: Config | None = None) -> None:
        self._path = path
        self._stamp: tuple[int, int] | None = None
        self._current: Config | None = fallback
        self._last_error: str | None = None
        #: Minden sikeres betoltessel no -- igy az olvasok olcson eszlelik a valtozast.
        self._generation = 0

    @property
    def path(self) -> Path:
        return self._path

    @property
    def generation(self) -> int:
        """Hanyszor toltodott be ervenyes config. Valtozasdetektalashoz."""
        return self._generation

    @property
    def current(self) -> Config | None:
        """Az utolso ervenyes beallitas, vagy ``None``, ha meg egy sem toltodott be."""
        return self._current

    def _stat_stamp(self) -> tuple[int, int] | None:
        try:
            st = os.stat(self._path)
        except OSError:
            return None
        return (st.st_mtime_ns, st.st_size)

    def reload_if_changed(self) -> Config | None:
        """Ujratolt, ha a fajl valtozott. Mindig az aktualis (vagy utolso jo) configot adja."""
        stamp = self._stat_stamp()
        if stamp is not None and stamp == self._stamp and self._current is not None:
            return self._current

        try:
            config = Config.load(self._path)
        except ConfigError as exc:
            message = str(exc)
            # Ugyanazt a hibat csak egyszer logoljuk, kulonben masodpercenkent spammelne.
            if message != self._last_error:
                self._last_error = message
                if self._current is None:
                    logger.error("Konfiguracios hiba: %s", message)
                else:
                    logger.error("Konfiguracios hiba, a korabbi beallitas marad ervenyben: %s", message)
            # A belyeget nem frissitjuk: felig kiirt fajl eseten a kovetkezo
            # korben ujra probalkozunk.
            return self._current

        self._stamp = stamp
        self._generation += 1
        if self._last_error is not None:
            logger.warning("A konfiguracio ujra ervenyes, ujratoltve: %s", self._path)
            self._last_error = None
        elif self._current is not None:
            logger.info("Konfiguracio ujratoltve: %s", self._path)
        self._current = config
        return config
