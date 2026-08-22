"""Hamis ``win32*`` modulok, hogy a Windows-fuggo kod barmely platformon tesztelheto legyen."""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass, field

import pytest

# --- hamis Win32 reteg ------------------------------------------------------

ENUM_CURRENT_SETTINGS = -1

ATTACHED = 0x1
PRIMARY = 0x4
MIRRORING = 0x8


class FakeDevMode:
    def __init__(self, width=2560, height=1440, frequency=120, bits=32):
        self.PelsWidth = width
        self.PelsHeight = height
        self.DisplayFrequency = frequency
        self.BitsPerPel = bits
        self.Fields = 0


class FakeDisplayDevice:
    def __init__(self, device_name, device_string, state_flags):
        self.DeviceName = device_name
        self.DeviceString = device_string
        self.StateFlags = state_flags


@dataclass
class FakeDisplay:
    """Egy szimulalt monitor: felbontas, aktualis es tamogatott frekvenciak."""

    device_name: str
    friendly_name: str = "Fake Monitor"
    width: int = 2560
    height: int = 1440
    frequency: int = 120
    supported: tuple[int, ...] = (60, 120, 240, 360)
    primary: bool = True
    mirroring: bool = False
    #: Ezeket a frekvenciakat a "driver" visszautasitja a CDS_TEST fazisban.
    reject: set[int] = field(default_factory=set)

    @property
    def state_flags(self) -> int:
        flags = ATTACHED
        if self.primary:
            flags |= PRIMARY
        if self.mirroring:
            flags |= MIRRORING
        return flags


class FakeWin32Api:
    """A ``win32api`` hasznalt reszenek szimulacioja."""

    def __init__(self, displays: list[FakeDisplay]):
        self.displays = displays
        self.change_calls: list[tuple[str | None, int, int]] = []
        self.enum_settings_calls = 0

    def _find(self, device_name):
        if device_name is None:
            return next((d for d in self.displays if d.primary), self.displays[0])
        for display in self.displays:
            if display.device_name == device_name:
                return display
        raise RuntimeError(f"ismeretlen eszkoz: {device_name}")

    def EnumDisplayDevices(self, device_name, index):
        if device_name is None:
            if index >= len(self.displays):
                raise RuntimeError("nincs tobb adapter")
            display = self.displays[index]
            return FakeDisplayDevice(display.device_name, "Adapter", display.state_flags)
        if index != 0:
            raise RuntimeError("nincs tobb monitor")
        return FakeDisplayDevice(device_name, self._find(device_name).friendly_name, ATTACHED)

    def EnumDisplaySettings(self, device_name, index):
        self.enum_settings_calls += 1
        display = self._find(device_name)
        if index == ENUM_CURRENT_SETTINGS:
            return FakeDevMode(display.width, display.height, display.frequency)
        modes = [(display.width, display.height, hz) for hz in display.supported]
        # Egy masik felbontas is szerepel, hogy a szures tesztelheto legyen.
        modes += [(1920, 1080, hz) for hz in (60, 144)]
        if index >= len(modes):
            raise RuntimeError("nincs tobb mod")
        return FakeDevMode(*modes[index])

    def ChangeDisplaySettingsEx(self, device_name, devmode, flags):
        display = self._find(device_name)
        self.change_calls.append((device_name, devmode.DisplayFrequency, flags))
        if devmode.DisplayFrequency in display.reject:
            return -2  # DISP_CHANGE_BADMODE
        if flags & 0x2:  # CDS_TEST
            return 0
        display.frequency = devmode.DisplayFrequency
        return 0


def _install_fake_win32(displays: list[FakeDisplay]) -> FakeWin32Api:
    api = FakeWin32Api(displays)
    sys.modules["win32api"] = api  # type: ignore[assignment]

    win32con = types.ModuleType("win32con")
    win32con.ENUM_CURRENT_SETTINGS = ENUM_CURRENT_SETTINGS
    win32con.DM_PELSWIDTH = 0x80000
    win32con.DM_PELSHEIGHT = 0x100000
    win32con.DM_BITSPERPEL = 0x40000
    win32con.DM_DISPLAYFREQUENCY = 0x400000
    sys.modules["win32con"] = win32con
    return api


@pytest.fixture
def displays() -> list[FakeDisplay]:
    return [FakeDisplay(device_name=r"\\.\DISPLAY1", friendly_name="Fake 240Hz", primary=True)]


@pytest.fixture
def win32(displays, monkeypatch):
    """Telepiti a hamis win32 modulokat, es ujratolti a ``display`` modult."""
    import importlib

    api = _install_fake_win32(displays)
    import refreshswitcher.display as display_module

    importlib.reload(display_module)
    yield api
    for name in ("win32api", "win32con"):
        sys.modules.pop(name, None)


class FakeProcess:
    """A ``psutil.Process`` hasznalt reszenek szimulacioja.

    A nevet -- ahogy a psutil is -- kulon lekerdezes adja vissza, nem a
    ``process_iter`` altal feltoltott ``info`` szotar; a hivasokat szamoljuk,
    igy tesztelheto, hogy a nev-gyorsitotar tenyleg mukodik.
    """

    def __init__(self, pid, name, started=0.0, name_calls=None):
        self.pid = pid
        self._name = name
        self._name_calls = name_calls if name_calls is not None else []
        self.info = {"pid": pid, "create_time": started}

    def name(self):
        self._name_calls.append(self.pid)
        return self._name


def fake_process_iter(entries, name_calls):
    """``psutil.process_iter`` helyettesitese ``(pid, nev, inditasi ido)`` listabol."""

    def _iter(attrs=None):
        return [FakeProcess(pid, name, started, name_calls) for pid, name, started in entries]

    return _iter


@pytest.fixture
def fake_processes(monkeypatch):
    """Beallithato ``(pid, nev, inditasi ido)`` lista a ``games`` modulhoz."""
    import refreshswitcher.games as games_module

    games_module.reset_name_cache()
    entries: list[tuple[int, str, float]] = []
    monkeypatch.setattr(games_module.psutil, "process_iter", fake_process_iter(entries, []))
    return entries
