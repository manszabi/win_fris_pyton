"""System tray felulet.

Javitasok a korabbi valtozathoz kepest:

* A munkaszal **a tray ikon elkeszulte utan** indul (``pystray`` ``setup``
  callback). Regen az elso allapotertesites elveszett, mert ``self.icon`` meg
  ``None`` volt -- az ikon indulaskor rossz Hz-et mutatott.
* A munkaszal **nem daemon**, es kilepeskor megvarjuk: igy lefut a
  frekvencia-visszaallitas. A daemon szal a folyamat kilepesekor azonnal
  meghalt volna, a ``finally`` ag lefutasa nelkul.
* Az ikonok **gyorsitotarazottak**, es pontosan a rendszer altal kert
  meretben (SM_CXSMICON) keszulnek, 8x supersampling utan LANCZOS
  kicsinyitessel -- eles kep minden DPI-skalazason.
* Hiba eseten (rossz config, nem letezo monitor) az ikon **pirosra valt**, es
  a tooltip megmutatja az okot -- nem nemul el csendben.
* A tooltip **minden agon** a Windows-limitre vagva megy at a pystray-nek.
  Ez nem szepitgetes: a hosszu szoveg ValueError-t dob, a pystray viszont
  *elobb eltarolja*, es csak utana probalja kiirni -- onnantol az ikon
  allapota "megmergezodik". A kovetkezo ``WM_DISPLAYCHANGE`` uzenetnel (alvas,
  ebredes, sajat frekvenciavaltas) a pystray leszedi az ikont a trayrol, es a
  ValueError miatt mar nem tudja visszatenni: az ikon eltunik, a folyamat
  pedig lathatatlanul tovabb fut.
* A ``pystray`` uzenethurokja **nem nemulhat el eszrevetlenul**: ha vegzetes
  hiba miatt leall, azt naplozzuk, es ujraepitjuk az ikont.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pystray
from PIL import Image, ImageDraw, ImageFont

from . import syswake
from .config import ConfigWatcher
from .dpi import enable_dpi_awareness, small_icon_size
from .logging_setup import current_log_file
from .paths import config_path
from .switcher import RefreshSwitcher, SwitcherState

logger = logging.getLogger(__name__)

APP_TITLE = "Display Refresh Rate Switcher by ManSzabi"

COLOR_IDLE = (48, 48, 48, 255)
COLOR_ACTIVE = (0, 150, 70, 255)
COLOR_WARN = (190, 120, 0, 255)
COLOR_ERROR = (176, 32, 32, 255)

#: Ennyiszeres felbontason rajzolunk, majd LANCZOS-szal kicsinyitunk.
SUPERSAMPLE = 8
#: A munkaszalra varakozas felso hatara kilepeskor (masodperc).
SHUTDOWN_TIMEOUT = 8.0

#: A ``NOTIFYICONDATAW.szTip`` mezo 128 karakteres, a lezaro nullaval egyutt --
#: ennel hosszabb tooltipet a pystray ``ValueError``-ral utasit vissza.
TOOLTIP_LIMIT = 127
#: A menusorok hossza; itt nincs kemeny rendszerkorlat, csak olvashatosag.
MENU_TEXT_LIMIT = 64
#: Ennyiszer epitjuk ujra az ikont, ha a Windows uzenethurok varatlanul leall.
MAX_ICON_RESTARTS = 3
#: Varakozas ket ujraepites kozott (masodperc).
ICON_RESTART_DELAY = 2.0

#: A ket PIL betutipus-osztaly; az ImageDraw.text() mindkettot elfogadja.
AnyFont = ImageFont.ImageFont | ImageFont.FreeTypeFont

_FONT_CANDIDATES = ("arialbd.ttf", "seguisb.ttf", "segoeui.ttf", "arial.ttf", "DejaVuSans-Bold.ttf")


def clamp(text: str, limit: int) -> str:
    """A szoveget a megadott hosszra vagja, jelezve, hogy folytatodna."""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def _load_font(size: int) -> AnyFont:
    for name in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def render_icon(text: str, background: tuple[int, int, int, int], size: int) -> Image.Image:
    """Lekerekitett hatteru ikon a megadott szoveggel, adott elmereten."""
    render_size = size * SUPERSAMPLE
    image = Image.new("RGBA", (render_size, render_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    margin = max(1, render_size // 16)
    radius = render_size // 5
    draw.rounded_rectangle(
        [margin, margin, render_size - margin - 1, render_size - margin - 1],
        radius=radius,
        fill=background,
    )

    # Hosszabb szoveg -> kisebb betu, hogy elferjen a keretben.
    ratio = {1: 0.72, 2: 0.62, 3: 0.48}.get(len(text), 0.38)
    font = _load_font(max(8, int(render_size * ratio)))

    center = render_size / 2
    outline = max(1, render_size // 32)
    # Kontur: a szam sotet es vilagos tray-hatteren egyarant olvashato marad.
    for dx, dy in ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)):
        draw.text(
            (center + dx * outline, center + dy * outline),
            text,
            fill=(0, 0, 0, 190),
            font=font,
            anchor="mm",
        )
    draw.text((center, center), text, fill=(255, 255, 255, 255), font=font, anchor="mm")

    return image.resize((size, size), Image.Resampling.LANCZOS)


def _open_in_explorer(path: Path) -> None:
    """Megnyitja a fajlt a rendszer alapertelmezett alkalmazasaval."""
    try:
        if sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined] # noqa: S606
        else:  # pragma: no cover - csak fejlesztoi kornyezetben fut
            # Fix parancs, nem felhasznaloi bemenet; a PATH feloldasa itt szandekos.
            subprocess.Popen(["xdg-open", str(path)])  # noqa: S603, S607
    except OSError:
        logger.warning("Nem sikerult megnyitni: %s", path, exc_info=True)


class TrayApp:
    """A tray ikon es a hozza tartozo eletciklus."""

    def __init__(self, watcher: ConfigWatcher) -> None:
        self._watcher = watcher
        self._switcher = RefreshSwitcher(watcher, listener=self._on_state)
        self._icon: pystray.Icon | None = None
        self._worker: threading.Thread | None = None
        self._state: SwitcherState | None = None
        self._icon_cache: dict[tuple[str, tuple[int, int, int, int], int], Image.Image] = {}
        #: Igaz, ha a felhasznalo kert kilepest -- csak igy szabad kilepni.
        self._quit_requested = False

    # -- megjelenites ------------------------------------------------------

    def _icon_for(self, state: SwitcherState | None) -> Image.Image:
        size = small_icon_size()
        if state is None:
            text, color = "..", COLOR_IDLE
        elif state.error is not None:
            text, color = "!", COLOR_ERROR
        else:
            text = str(state.refresh_rate) if state.refresh_rate else "?"
            # Borostyan: a program mukodik, de a kert Hz nem allithato be.
            active = COLOR_ACTIVE if state.game else COLOR_IDLE
            color = COLOR_WARN if state.warning is not None else active

        key = (text, color, size)
        cached = self._icon_cache.get(key)
        if cached is None:
            cached = render_icon(text, color, size)
            self._icon_cache[key] = cached
        return cached

    def _tooltip_for(self, state: SwitcherState | None) -> str:
        """A tray tooltip szovege -- garantaltan a Windows-limiten belul.

        A vagas egyetlen, kozos helyen tortenik: egyetlen ki nem vagott ag is
        eleg ahhoz, hogy a hibauzenet (ami a monitorok felsorolasat is
        tartalmazza) hasznalhatatlanna tegye az ikont.
        """
        if state is None:
            line = "Indulas..."
        elif state.error is not None:
            line = f"Hiba: {state.error}"
        else:
            line = f"{state.refresh_rate} Hz"
            if state.game_name:
                line += f" - {state.game_name}"
            if state.monitor is not None:
                line += f"\n{state.monitor.friendly_name}"
            if state.warning is not None:
                line += f"\nFigyelem: {state.warning}"
        return clamp(f"{APP_TITLE}\n{line}", TOOLTIP_LIMIT)

    def _status_text(self, _item: object = None) -> str:
        state = self._state
        if state is None:
            return "Indulas..."
        if state.error is not None:
            return clamp(f"Hiba: {state.error}", MENU_TEXT_LIMIT)
        if state.warning is not None:
            return clamp(f"{state.refresh_rate} Hz - {state.warning}", MENU_TEXT_LIMIT)
        if state.game_name:
            return f"{state.refresh_rate} Hz - {state.game_name}"
        return f"{state.refresh_rate} Hz"

    def _monitor_text(self, _item: object = None) -> str:
        state = self._state
        if state is None or state.monitor is None:
            return "Monitor: ismeretlen"
        return clamp(f"Monitor: {state.monitor.friendly_name}", MENU_TEXT_LIMIT)

    # -- esemenyek ---------------------------------------------------------

    def _on_state(self, state: SwitcherState) -> None:
        """A munkaszalbol hivodik minden allapotvaltozaskor."""
        self._state = state
        icon = self._icon
        if icon is None or not getattr(icon, "visible", False):
            return
        try:
            icon.icon = self._icon_for(state)
            icon.title = self._tooltip_for(state)
            icon.update_menu()
        except Exception:  # a UI hibaja nem allithatja meg a switchert
            logger.warning("Nem sikerult frissiteni a tray ikont.", exc_info=True)
            self._restore_icon(icon)

    def _restore_icon(self, icon: pystray.Icon) -> None:
        """Ujra kiteszi az ikont egy sikertelen frissites utan.

        A pystray a cimet az ervenyesites *elott* tarolja el, ezert egy hibas
        ertek benne ragad, es utana mar a trayre visszatetel is elszall. Eloszor
        tehat egy biztosan rovid cimet adunk neki, es csak azutan tesszuk ki
        ujra az ikont.
        """
        try:
            icon.title = APP_TITLE
            icon.visible = False
            icon.visible = True
        except Exception:
            logger.warning("Nem sikerult ujra kitenni a tray ikont.", exc_info=True)

    def _on_open_config(self, _icon: object = None, _item: object = None) -> None:
        _open_in_explorer(self._watcher.path)

    def _on_open_log(self, _icon: object = None, _item: object = None) -> None:
        path = current_log_file()
        if path is not None:
            _open_in_explorer(path)

    def _has_log(self, _item: object = None) -> bool:
        return current_log_file() is not None

    def _on_quit(self, icon: pystray.Icon, _item: object = None) -> None:
        logger.info("Kilepes a tray menubol.")
        self._quit_requested = True
        self._switcher.stop()
        icon.visible = False
        icon.stop()

    def _setup(self, icon: pystray.Icon) -> None:
        """A pystray hivja, amint az ikon lathato -- itt indul a munkaszal."""
        icon.visible = True
        # Alvas/ebredes es kijelzovaltas eszlelese: ehhez kell a mar felallt
        # ablak, ezert csak most iratkozunk fel.
        syswake.attach(icon, self._switcher.wake)
        # Az ikon ujraepitesekor a munkaszal mar fut: nem inditunk masodikat.
        worker = self._worker
        if worker is not None and worker.is_alive():
            state = self._state
            if state is not None:
                # Az ujraepitett ikon azonnal a valos allapotot mutassa.
                self._on_state(state)
            return
        worker = threading.Thread(
            target=self._switcher.run,
            name="refresh-switcher",
            # Daemon, de a _shutdown kifejezetten megvarja: normal esetben
            # igy is lefut a frekvencia-visszaallitas, viszont ha a szal
            # beragadna, nem tartja eletben a folyamatot lathatatlan
            # "szellem" processzkent.
            daemon=True,
        )
        self._worker = worker
        worker.start()

    # -- eletciklus --------------------------------------------------------

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem(self._status_text, None, enabled=False),
            pystray.MenuItem(self._monitor_text, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Beallitasok szerkesztese", self._on_open_config),
            pystray.MenuItem("Naplo megnyitasa", self._on_open_log, visible=self._has_log),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Kilepes", self._on_quit),
        )

    def run(self) -> int:
        enable_dpi_awareness()
        try:
            for attempt in range(1 + MAX_ICON_RESTARTS):
                if self._run_icon():
                    return 0
                if attempt == MAX_ICON_RESTARTS:
                    break
                # Ide csak akkor jutunk, ha a Windows uzenethurok kilepesi
                # keres nelkul allt le. A switcher ilyenkor is dolgozik tovabb,
                # csak a tray ikon tunt el -- ezt epitjuk ujra.
                logger.error(
                    "A tray uzenethurok varatlanul leallt; ujraepites (%d/%d).",
                    attempt + 1,
                    MAX_ICON_RESTARTS,
                )
                time.sleep(ICON_RESTART_DELAY)
            logger.error("A tray ikont nem sikerult ujraepiteni; a program kilep.")
            return 1
        finally:
            self._shutdown()

    def _run_icon(self) -> bool:
        """Egy teljes ikon-eletciklus. ``True``, ha rendezett kilepes tortent."""
        try:
            self._icon = pystray.Icon(
                "RefreshSwitcher",
                icon=self._icon_for(self._state),
                title=self._tooltip_for(self._state),
                menu=self._build_menu(),
            )
            self._icon.run(setup=self._setup)
        except KeyboardInterrupt:  # pragma: no cover
            logger.info("Megszakitas (Ctrl+C).")
            return True
        except Exception:
            # A pystray sajat uzenethurokja elkapja a sajat hibait, ide csak a
            # felallitas kozbeni hiba juthat el -- naploznunk viszont kell,
            # kulonben pythonw.exe alatt nyomtalanul tunne el a program.
            logger.exception("A tray ikon vegzetes hibaval leallt.")
            return False
        finally:
            self._icon = None
        return self._quit_requested

    def _shutdown(self) -> None:
        self._quit_requested = True
        self._switcher.stop()
        worker = self._worker
        if worker is not None and worker.is_alive():
            worker.join(timeout=SHUTDOWN_TIMEOUT)
            if worker.is_alive():  # pragma: no cover - vedohalo
                logger.warning("A munkaszal nem allt le %.0f mp alatt.", SHUTDOWN_TIMEOUT)


def run_tray(config_file: Path | None = None) -> int:
    """Elinditja a tray alkalmazast. A folyamat kilepesi kodjat adja vissza."""
    watcher = ConfigWatcher(config_file or config_path())
    return TrayApp(watcher).run()
