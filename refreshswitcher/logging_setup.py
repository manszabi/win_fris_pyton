"""Kozponti naplozas-beallitas.

Kulcsfontossagu ``pythonw.exe`` alatt: ott nincs konzol, ``sys.stderr`` lehet
``None``, es minden kezeletlen kivetel *nyomtalanul* megoli a programot. Ezert
itt globalis kivetel-horgokat is telepitunk -- e nelkul a "csak ugy eltunt a
tray ikon" tipusu hibak diagnosztizalhatatlanok.

Ugyanezert kap sajat kezelot a ``pystray`` is: a tray uzenethurokja *elkapja*
es a sajat naplozojara irja a hibait (koztuk azt is, ha egy uzenetkezelo
elszall). A sajat naplozonk ``propagate = False`` beallitasa miatt ezek
kulonben a semmibe hullananak -- pontosan az a "semmi nincs a naploban"
helyzet, amiert ez a modul letezik.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
import threading
from pathlib import Path

from .paths import LOG_FILENAME, log_path, user_data_dir

LOG_FORMAT = "%(asctime)s [%(levelname)-7s] %(name)s: %(message)s"
MAX_LOG_BYTES = 512 * 1024
BACKUP_COUNT = 2

_ROOT_LOGGER_NAME = "refreshswitcher"
#: Kulso csomagok, amiknek a hibauzenetei nelkul nem lehet hibat keresni.
#: WARNING szinten kotjuk be oket, igy nem szemetelik tele a naplot.
_THIRD_PARTY_LOGGERS = ("pystray", "PIL")

_configured = False
_log_file: Path | None = None
_lock = threading.Lock()


def _build_file_handler(path: Path) -> logging.Handler | None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            path,
            maxBytes=MAX_LOG_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
            delay=True,
        )
    except OSError:
        return None
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    return handler


def setup_logging(level: int | str = logging.WARNING, *, console: bool = False) -> Path | None:
    """Beallitja a naplozast; a hasznalt log fajl utjat adja vissza.

    Ha az alkalmazas mappaja nem irhato (pl. ``C:\\Program Files`` alol fut),
    automatikusan a ``%LOCALAPPDATA%\\RefreshSwitcher`` mappaba valt, igy egy
    jogosultsagi hiba nem akadalyozza meg az indulast.
    """
    global _configured, _log_file

    logger = logging.getLogger(_ROOT_LOGGER_NAME)
    logger.setLevel(level)
    # Sajat kezelo -> nem akarjuk, hogy a root logger is kiirja.
    logger.propagate = False

    with _lock:
        if _configured:
            return _log_file

        used_path: Path | None = None
        for candidate in (log_path(), user_data_dir() / LOG_FILENAME):
            handler = _build_file_handler(candidate)
            if handler is not None:
                logger.addHandler(handler)
                used_path = candidate
                break

        # pythonw.exe alatt sys.stderr None -- ilyenkor nincs mibe irni.
        if console and sys.stderr is not None:
            stream = logging.StreamHandler(sys.stderr)
            stream.setFormatter(logging.Formatter(LOG_FORMAT))
            logger.addHandler(stream)

        if not logger.handlers:
            # Vegso mentsvar: ne dobjon "No handlers" figyelmeztetest.
            logger.addHandler(logging.NullHandler())

        for name in _THIRD_PARTY_LOGGERS:
            third_party = logging.getLogger(name)
            third_party.setLevel(logging.WARNING)
            # Sajat kezelot kap, tehat a root loggerre mar nem kell tovabbadni.
            third_party.propagate = False
            for handler in logger.handlers:
                third_party.addHandler(handler)

        _log_file = used_path
        _configured = True

    install_exception_hooks()
    return used_path


def install_exception_hooks() -> None:
    """Kezeletlen kivetelek naplozasa - fo- es munkaszalakon egyarant."""
    logger = logging.getLogger(_ROOT_LOGGER_NAME)

    previous_hook = sys.excepthook

    def _excepthook(exc_type, exc, tb):  # type: ignore[no-untyped-def]
        if issubclass(exc_type, KeyboardInterrupt):
            previous_hook(exc_type, exc, tb)
            return
        logger.critical("Kezeletlen kivetel a foszalon.", exc_info=(exc_type, exc, tb))

    sys.excepthook = _excepthook

    def _threadhook(args: threading.ExceptHookArgs) -> None:
        if issubclass(args.exc_type, SystemExit):
            return
        exc = args.exc_value
        if exc is None:  # elmeletileg lehetseges, gyakorlatilag nem fordul elo
            exc = args.exc_type()
        logger.critical(
            "Kezeletlen kivetel a(z) %r szalban.",
            args.thread.name if args.thread else "?",
            exc_info=exc,
        )

    threading.excepthook = _threadhook


def current_log_file() -> Path | None:
    """A tenylegesen hasznalt log fajl, vagy ``None``, ha egyik sem nyithato meg."""
    return _log_file


def get_logger(name: str = _ROOT_LOGGER_NAME) -> logging.Logger:
    return logging.getLogger(name)
