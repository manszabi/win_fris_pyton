"""Per-monitor DPI-tudatossag bekapcsolasa (Windows 10 1703+ / Windows 11).

DPI-tudatossag nelkul a ``GetSystemMetrics(SM_CXSMICON)`` a 96 DPI-s (skalazatlan)
meretet adja vissza, es a tray ikon 150%-os skalazason elmosodott lesz.
"""

from __future__ import annotations

import ctypes
import logging
import sys

logger = logging.getLogger(__name__)

#: DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)
#: PROCESS_PER_MONITOR_DPI_AWARE
_PROCESS_PER_MONITOR_DPI_AWARE = 2

_DEFAULT_SMALL_ICON = 16


def enable_dpi_awareness() -> bool:
    """Bekapcsolja a legjobb elerheto DPI-tudatossagot. Hiba eseten csendben kihagyja."""
    if sys.platform != "win32":
        return False
    try:
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    except (AttributeError, OSError):  # pragma: no cover
        return False

    # Windows 10 1703+ - a legpontosabb valtozat.
    try:
        if user32.SetProcessDpiAwarenessContext(_PER_MONITOR_AWARE_V2):
            return True
    except (AttributeError, OSError):
        pass

    # Windows 8.1+
    try:
        shcore = ctypes.windll.shcore  # type: ignore[attr-defined]
        if shcore.SetProcessDpiAwareness(_PROCESS_PER_MONITOR_DPI_AWARE) == 0:
            return True
    except (AttributeError, OSError):
        pass

    # Vista+
    try:
        return bool(user32.SetProcessDPIAware())
    except (AttributeError, OSError):  # pragma: no cover
        return False


def small_icon_size() -> int:
    """A rendszer altal kert tray-ikon meret pixelben (SM_CXSMICON)."""
    if sys.platform != "win32":
        return _DEFAULT_SMALL_ICON
    try:
        size = int(ctypes.windll.user32.GetSystemMetrics(49))  # SM_CXSMICON
    except (AttributeError, OSError, ValueError):  # pragma: no cover
        return _DEFAULT_SMALL_ICON
    # Erteles korlatok: hibas driver ne generaljon oriasi bitmapet.
    return max(_DEFAULT_SMALL_ICON, min(size, 256))
