"""Fajl utvonalak feloldasa - PyInstaller (frozen) es normal futtatas eseten is."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "RefreshSwitcher"

CONFIG_FILENAME = "config.json"
LOG_FILENAME = "refreshswitcher.log"
#: A 2.0 elotti verziok ide logoltak; a migracios uzenethez kell.
LEGACY_LOG_FILENAME = "service.log"


def app_dir() -> Path:
    """Az exe (frozen) vagy a csomag szuloje (fejlesztoi futtatas) melletti mappa.

    PyInstaller ``--onefile`` eseten ``sys.executable`` az ideiglenes kicsomagolo
    mappa helyett a *valodi* exe helyet adja vissza, ezert a config es a log
    az exe mellett keresendo -- ez teszi lehetove a beallitasok szerkeszteset.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def config_path() -> Path:
    """A config.json helye. A ``REFRESHSWITCHER_CONFIG`` env valtozo felulirja."""
    override = os.environ.get("REFRESHSWITCHER_CONFIG")
    if override:
        return Path(override).expanduser().resolve()
    return app_dir() / CONFIG_FILENAME


def user_data_dir() -> Path:
    """Irhato per-user mappa (%LOCALAPPDATA%\\RefreshSwitcher) tartalek logoknak."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        return Path(base) / APP_NAME
    return Path.home() / f".{APP_NAME.lower()}"


def log_path() -> Path:
    """A log fajl helye. A ``REFRESHSWITCHER_LOG`` env valtozo felulirja."""
    override = os.environ.get("REFRESHSWITCHER_LOG")
    if override:
        return Path(override).expanduser().resolve()
    return app_dir() / LOG_FILENAME
