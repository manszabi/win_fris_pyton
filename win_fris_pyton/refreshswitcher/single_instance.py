"""Egypeldany-vedelem nevesitett Windows mutex-szel.

A Task Scheduler bejelentkezeskori inditasa es a kezi inditas konnyen ket
peldanyt eredmenyez. Ket peldany egymas ellen dolgozik: az egyik felmegy
240 Hz-re, a masik vissza 120 Hz-re -- villogo kepernyo es folyamatos
modvaltas. Ez a modul ezt zarja ki.
"""

from __future__ import annotations

import contextlib
import logging
from types import TracebackType

logger = logging.getLogger(__name__)

#: ``Local\`` = bejelentkezesi munkamenetenkent egy peldany. Ez a helyes hatokor:
#: gyorsfelhasznalo-valtas eseten minden munkamenetnek sajat tray ikonja lehet.
MUTEX_NAME = r"Local\RefreshSwitcher-9f2c1d54-singleton"

ERROR_ALREADY_EXISTS = 183


class SingleInstance:
    """Context manager: ``acquired`` jelzi, hogy mienk-e az egyetlen peldany."""

    def __init__(self, name: str = MUTEX_NAME) -> None:
        self._name = name
        self._handle = None
        self.acquired = False

    def __enter__(self) -> SingleInstance:
        try:
            import win32api
            import win32event
            import winerror
        except ImportError:
            # Nem Windows (pl. tesztkornyezet): nincs mit vedeni.
            self.acquired = True
            return self

        try:
            handle = win32event.CreateMutex(None, True, self._name)
            last_error = win32api.GetLastError()
        except Exception:  # noqa: BLE001 - a mutex hianya nem vegzetes
            logger.warning("Nem sikerult letrehozni az egypeldany-mutexet.", exc_info=True)
            self.acquired = True
            return self

        already = getattr(winerror, "ERROR_ALREADY_EXISTS", ERROR_ALREADY_EXISTS)
        if last_error == already:
            self.acquired = False
            with contextlib.suppress(Exception):
                win32api.CloseHandle(handle)
        else:
            self._handle = handle
            self.acquired = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._handle is None:
            return
        try:
            # Kilepeskor egy sikertelen felszabaditas mar nem szamit: a Windows
            # a folyamat megszunesekor amugy is elengedi a mutexet.
            with contextlib.suppress(Exception):
                import win32api
                import win32event

                win32event.ReleaseMutex(self._handle)
                win32api.CloseHandle(self._handle)
        finally:
            self._handle = None
