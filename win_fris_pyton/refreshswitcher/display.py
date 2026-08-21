"""Win32 kijelzo API vekony, tesztelheto burkolata.

Fontos kulonbsegek a korabbi implementaciohoz kepest:

* Minden ``EnumDisplay*`` ciklus **felso korlattal** fut. A regi ``while True``
  ciklusok egy hibas/virtualis megjelenito-driver eseten vegtelenul porogtek
  volna, ami a teljes program lefagyasat okozza.
* A tamogatott frekvenciak listaja gyorsitotarazott (felbontasonkent), igy nem
  kell kb. 100-500 mod-lekerdezest vegezni minden egyes valtaskor.
* A modvaltast ``CDS_TEST`` elozi meg, igy nem probalunk olyan modot beallitani,
  amit a driver visszautasitana (fekete kepernyo / reset kockazat).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Final

import win32api
import win32con

logger = logging.getLogger(__name__)

# --- Win32 konstansok (nem mindegyik van meg minden pywin32 verzioban) -------

DISPLAY_DEVICE_ATTACHED_TO_DESKTOP: Final = 0x00000001
DISPLAY_DEVICE_MIRRORING_DRIVER: Final = 0x00000008
DISPLAY_DEVICE_PRIMARY_DEVICE: Final = 0x00000004

CDS_UPDATEREGISTRY: Final = 0x00000001
CDS_TEST: Final = 0x00000002

#: 0 = dinamikus valtas, a registrybe *nem* irodik be. Szandekos: ha a program
#: osszeomlik, az ujrainditas a felhasznalo eredeti beallitasat hozza vissza.
CDS_DYNAMIC: Final = 0

DISP_CHANGE_NAMES: Final[dict[int, str]] = {
    0: "DISP_CHANGE_SUCCESSFUL",
    1: "DISP_CHANGE_RESTART (ujrainditas szukseges)",
    -1: "DISP_CHANGE_FAILED (a driver visszautasitotta)",
    -2: "DISP_CHANGE_BADMODE (a mod nem tamogatott)",
    -3: "DISP_CHANGE_NOTUPDATED (nem sikerult a registrybe irni)",
    -4: "DISP_CHANGE_BADFLAGS (ervenytelen flag)",
    -5: "DISP_CHANGE_BADPARAM (ervenytelen parameter)",
    -6: "DISP_CHANGE_BADDUALVIEW (dualview korlatozas)",
}

#: Windows legfeljebb ennyi megjelenito-adaptert tud; boven eleg felso korlat.
MAX_ADAPTERS: Final = 64
#: Egy adapter modjainak felso korlatja (valosagban 100-1000 kozott van).
MAX_MODES: Final = 8192


class DisplayError(RuntimeError):
    """A kijelzo lekerdezese vagy allitasa nem sikerult."""


@dataclass(frozen=True, slots=True)
class Monitor:
    """Egy asztalhoz csatolt megjelenito."""

    index: int  # 1-tol szamozva, a felhasznaloi config szamozasaval egyezik
    device_name: str  # pl. '\\\\.\\DISPLAY1'
    friendly_name: str  # pl. 'Dell AW2725DF'
    is_primary: bool

    def __str__(self) -> str:  # pragma: no cover - csak megjelenites
        suffix = " [elsodleges]" if self.is_primary else ""
        return f"{self.index}. {self.friendly_name} ({self.device_name}){suffix}"


@dataclass(frozen=True, slots=True)
class DisplayMode:
    """Egy megjelenito aktualis grafikus modja."""

    width: int
    height: int
    frequency: int
    bits_per_pixel: int


def _monitor_friendly_name(device_name: str) -> str:
    """A fizikai monitor neve; ha nem elerheto, az eszkoznev a tartalek."""
    try:
        monitor = win32api.EnumDisplayDevices(device_name, 0)
    except Exception:  # noqa: BLE001 - a pywin32 sajat hibatipust dob
        return device_name
    name = (getattr(monitor, "DeviceString", "") or "").strip()
    return name or device_name


def enumerate_monitors() -> list[Monitor]:
    """Az asztalhoz csatolt monitorok listaja, stabil sorrendben.

    A tukrozo (mirroring) drivereket - pl. tavoli asztal / rogzito szoftverek
    virtualis kijelzoit - kihagyja, mert azok elcsusztatnak a sorszamozast.
    """
    monitors: list[Monitor] = []
    for i in range(MAX_ADAPTERS):
        try:
            device = win32api.EnumDisplayDevices(None, i)
        except Exception:  # noqa: BLE001 - a felsorolas vege
            break
        if device is None:
            break
        flags = getattr(device, "StateFlags", 0)
        if not flags & DISPLAY_DEVICE_ATTACHED_TO_DESKTOP:
            continue
        if flags & DISPLAY_DEVICE_MIRRORING_DRIVER:
            continue
        device_name = device.DeviceName
        monitors.append(
            Monitor(
                index=len(monitors) + 1,
                device_name=device_name,
                friendly_name=_monitor_friendly_name(device_name),
                is_primary=bool(flags & DISPLAY_DEVICE_PRIMARY_DEVICE),
            )
        )
    else:  # pragma: no cover - csak hibas driver eseten
        logger.warning("A megjelenito-felsorolas elerte a %d-os korlatot.", MAX_ADAPTERS)
    return monitors


def resolve_monitor(selector: int | str) -> Monitor | None:
    """Monitor feloldasa sorszam (1-tol) vagy eszkoznev/nev-toredek alapjan."""
    monitors = enumerate_monitors()
    if not monitors:
        logger.error("Nem talalhato az asztalhoz csatolt monitor.")
        return None

    if isinstance(selector, int):
        if 1 <= selector <= len(monitors):
            return monitors[selector - 1]
        logger.error(
            "A(z) %d. monitor nem letezik. Elerheto: %s",
            selector,
            ", ".join(str(m) for m in monitors),
        )
        return None

    needle = selector.strip().lower()
    for monitor in monitors:
        if monitor.device_name.lower() == needle:
            return monitor
    for monitor in monitors:
        if needle in monitor.friendly_name.lower():
            return monitor
    logger.error(
        "Nincs %r nevu monitor. Elerheto: %s",
        selector,
        ", ".join(str(m) for m in monitors),
    )
    return None


def current_mode(device_name: str | None = None) -> DisplayMode:
    """A megadott megjelenito aktualis modja."""
    try:
        dm = win32api.EnumDisplaySettings(device_name, win32con.ENUM_CURRENT_SETTINGS)
    except Exception as exc:
        raise DisplayError(
            f"Nem sikerult lekerdezni a(z) {device_name or 'elsodleges'} monitor modjat: {exc}"
        ) from exc
    return DisplayMode(
        width=dm.PelsWidth,
        height=dm.PelsHeight,
        frequency=dm.DisplayFrequency,
        bits_per_pixel=dm.BitsPerPel,
    )


def current_refresh_rate(device_name: str | None = None) -> int:
    """A megadott megjelenito aktualis frissitesi frekvenciaja Hz-ben."""
    return current_mode(device_name).frequency


class RefreshRateCache:
    """Felbontasonkent gyorsitotarazza a tamogatott frekvenciakat.

    A kulcs tartalmazza a felbontast is, ezert felbontasvaltas utan
    automatikusan ujraszamolodik - nincs szukseg kezi urritesre.
    """

    def __init__(self) -> None:
        self._cache: dict[tuple[str, int, int], tuple[int, ...]] = {}

    def clear(self) -> None:
        self._cache.clear()

    def get(self, device_name: str | None, mode: DisplayMode) -> tuple[int, ...]:
        key = (device_name or "", mode.width, mode.height)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        rates = _query_supported_rates(device_name, mode)
        self._cache[key] = rates
        return rates


def _query_supported_rates(device_name: str | None, mode: DisplayMode) -> tuple[int, ...]:
    """Az aktualis felbontashoz tartozo tamogatott frekvenciak, novekvo sorrendben."""
    rates: set[int] = set()
    for i in range(MAX_MODES):
        try:
            dm = win32api.EnumDisplaySettings(device_name, i)
        except Exception:  # noqa: BLE001 - a felsorolas vege
            break
        if dm is None:
            break
        if dm.PelsWidth == mode.width and dm.PelsHeight == mode.height:
            rates.add(dm.DisplayFrequency)
    else:  # pragma: no cover - csak hibas driver eseten
        logger.warning("A mod-felsorolas elerte a %d-os korlatot.", MAX_MODES)
    return tuple(sorted(rates))


def supported_refresh_rates(device_name: str | None = None) -> tuple[int, ...]:
    """Kenyelmi fuggveny gyorsitotar nelkuli lekerdezeshez (CLI / diagnosztika)."""
    return _query_supported_rates(device_name, current_mode(device_name))


def set_refresh_rate(device_name: str | None, hz: int) -> bool:
    """Beallitja a frissitesi frekvenciat. ``True``, ha sikerult (vagy mar jo volt)."""
    mode = current_mode(device_name)
    if mode.frequency == hz:
        return True

    try:
        dm = win32api.EnumDisplaySettings(device_name, win32con.ENUM_CURRENT_SETTINGS)
    except Exception as exc:
        raise DisplayError(f"Nem sikerult lekerdezni a jelenlegi modot: {exc}") from exc

    dm.DisplayFrequency = hz
    dm.Fields = (
        win32con.DM_PELSWIDTH | win32con.DM_PELSHEIGHT | win32con.DM_BITSPERPEL | win32con.DM_DISPLAYFREQUENCY
    )

    # Eloszor csak teszteljuk: igy nem kockaztatunk fekete kepernyot.
    probe = win32api.ChangeDisplaySettingsEx(device_name, dm, CDS_TEST)
    if probe != 0:
        logger.warning(
            "A %d Hz nem allithato be a(z) %s monitoron: %s",
            hz,
            device_name or "elsodleges",
            DISP_CHANGE_NAMES.get(probe, f"ismeretlen hibakod: {probe}"),
        )
        return False

    result = win32api.ChangeDisplaySettingsEx(device_name, dm, CDS_DYNAMIC)
    if result == 0:
        logger.info("Frissitesi frekvencia beallitva: %d Hz (%s)", hz, device_name or "elsodleges")
        return True

    logger.error(
        "Nem sikerult beallitani a %d Hz-et a(z) %s monitoron: %s",
        hz,
        device_name or "elsodleges",
        DISP_CHANGE_NAMES.get(result, f"ismeretlen hibakod: {result}"),
    )
    return False
