"""A frissitesi frekvencia figyelo- es valtologika.

Tervezesi dontesek a regi ``monitor_loop``-hoz kepest:

* **Nincs ``game_was_running`` allapotjelzo.** A regi harom-agu logika a
  tenyleges kijelzo-allapottol fuggetlenul vezetett sajat allapotot, ami
  elcsuszhatott (pl. alvas utan a Windows visszaall 60 Hz-re, de a program
  azt hitte, minden rendben). Itt minden korben a *kivant* es a *tenyleges*
  frekvenciat hasonlitjuk ossze -- onmagat javito rendszer.
* **``stop_event.wait()`` a ``time.sleep()`` helyett.** A regi valtozatban a
  kilepes akar egy teljes ``check_interval``-t varakozott (nagy intervallum
  eseten a program "lefagyottnak" latszott).
* **Kilepeskor visszaall az alapertelmezett frekvencia.**
* **Hibaelnyomas es exponencialis ritkitas**: ismetlodo hiba nem irodik ki
  masodpercenkent a logba, es nem terheli feleslegesen a rendszert.
* **Monitor-azonossag kovetese**: ha futas kozben kihuzol egy kijelzot, a
  sorszamok elcsusznak; ilyenkor a program figyelmeztet, es nem allitgatja
  csendben a rossz monitort.
* **Nev szerinti kivalasztas rogzitese**: a Windows egy ebredes vagy
  ujracsatlakozas utan atmenetileg ``Generic PnP Monitor``-kent jelenti a
  kijelzot, ilyenkor a nevre allitott kivalasztas nem talalna semmit. A
  korabban azonositott eszkozt ezert megjegyezzuk, es addig hasznaljuk, amig
  csatlakozik.
* **Ebresztes**: alvas/hibernalas utan (es kijelzovaltaskor) a tray kivulrol
  ``wake()``-el jelez, igy a kovetkezo ellenorzes azonnal lefut, es a
  hibaritkitas is nullazodik -- nem kell akar egy percet varni arra, hogy a
  frekvencia helyrealljon.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from .config import Config, ConfigWatcher
from .display import (
    DisplayError,
    DisplayMode,
    Monitor,
    RefreshRateCache,
    current_mode,
    describe_monitors,
    resolve_monitor,
    set_refresh_rate,
)
from .games import GameMatch, find_active_game

logger = logging.getLogger(__name__)

#: Ennyi egymast koveto sikertelen kor utan ritkitjuk az ujraprobalkozast.
_BACKOFF_AFTER_FAILURES = 3
#: A ritkitott ujraprobalkozas felso hatara masodpercben.
_MAX_BACKOFF_SECONDS = 60.0
#: Ennyi ideig varunk ket kor kozott, ha meg egyaltalan nincs ervenyes config.
_NO_CONFIG_INTERVAL = 5.0


@dataclass(frozen=True, slots=True)
class SwitcherState:
    """A felhasznaloi feluletnek (tray) atadott pillanatnyi allapot."""

    #: A monitor *tenyleges* frekvenciaja, nem a kivant.
    refresh_rate: int
    game: GameMatch | None = None
    monitor: Monitor | None = None
    #: Vegzetes hiba (nincs config, nincs monitor) -- a program nem tud dolgozni.
    error: str | None = None
    #: Nem vegzetes problema (pl. a kert Hz nem tamogatott) -- a program fut tovabb.
    warning: str | None = None

    @property
    def game_name(self) -> str | None:
        return self.game.display_name if self.game else None

    @property
    def healthy(self) -> bool:
        return self.error is None and self.warning is None


class StateListener(Protocol):
    """Allapotvaltozas-ertesito (a tray ikon implementalja)."""

    def __call__(self, state: SwitcherState) -> None: ...


class RefreshSwitcher:
    """A figyelociklus. Szalbiztosan leallithato a ``stop`` metodussal."""

    def __init__(
        self,
        watcher: ConfigWatcher,
        listener: StateListener | Callable[[SwitcherState], None] | None = None,
    ) -> None:
        self._watcher = watcher
        self._listener = listener
        self._stop_event = threading.Event()
        #: A varakozas megszakitasa: a leallas es az ebresztes is ezt allitja be.
        self._interrupt = threading.Event()
        #: Ebredes utan a kovetkezo korben eldobjuk a gyorsitotarazott dontesteket.
        self._resync = False
        self._rate_cache = RefreshRateCache()
        self._state: SwitcherState | None = None
        self._state_lock = threading.Lock()
        #: (eszkoznev, hz) -> indoklas; amirol mar tudjuk, hogy nem allithato be.
        #: Az uzenetet is taroljuk, hogy korrol korre ugyanazt jelentsuk
        #: (kulonben a tray allapota feleslegesen valtozna).
        self._rejected: dict[tuple[str, int], str] = {}
        self._consecutive_failures = 0
        #: Az utolso eszkoz, amin valtoztattunk -- ezt allitjuk vissza kilepeskor.
        self._touched_device: str | None = None
        #: (config-generacio, felbontas): valtozasakor ujraertekeljuk az elutasitasokat.
        self._fingerprint: tuple[int, int, int] | None = None
        #: Az elozo korben feloldott monitor azonossaga (kihuzas eszlelesehez).
        self._monitor_identity: tuple[str, str] | None = None
        #: Nev szerinti kivalasztashoz: (a config szovege, a hozza talalt eszkoz).
        self._pinned: tuple[str, str] | None = None
        #: Igaz, ha epp a rogzitett eszkozre esunk vissza (csak egyszer naplozzuk).
        self._pinned_fallback = False

    # -- vezerles ----------------------------------------------------------

    def stop(self) -> None:
        """Jelzi a ciklusnak, hogy alljon le. Tobbszor is hivhato."""
        self._stop_event.set()
        self._interrupt.set()

    def wake(self, reason: str = "") -> None:
        """Azonnali ujraellenorzest ker (alvas utani ebredes, kijelzovaltas).

        Szalbiztos es nem blokkolo: a hivo -- tipikusan a Windows
        uzenethurokja -- csak jelez, minden munka a figyelociklusban tortenik.
        """
        self._resync = True
        self._interrupt.set()
        if reason:
            logger.debug("Ebresztes: %s", reason)

    @property
    def stopping(self) -> bool:
        return self._stop_event.is_set()

    @property
    def state(self) -> SwitcherState | None:
        with self._state_lock:
            return self._state

    def _publish(self, state: SwitcherState) -> None:
        with self._state_lock:
            if self._state == state:
                return
            self._state = state
        if self._listener is None:
            return
        try:
            self._listener(state)
        except Exception:
            logger.exception("Az allapot-ertesito hibat dobott.")

    # -- fociklus ----------------------------------------------------------

    def run(self) -> None:
        """A figyelociklus. Blokkol, amig a ``stop`` meg nem hivodik."""
        logger.info("Figyelociklus indul (config: %s)", self._watcher.path)
        try:
            while not self._stop_event.is_set():
                interval = self._tick()
                self._interrupt.wait(interval)
                if self._stop_event.is_set():
                    break
                # Az esetleg kozben erkezo ujabb ebresztest nem veszitjuk el:
                # a torles utan azonnal kovetkezik egy teljes ellenorzes.
                self._interrupt.clear()
        finally:
            self._restore_on_exit()
            logger.info("Figyelociklus leallt.")

    def _tick(self) -> float:
        """Egy ellenorzesi kor. A kovetkezo varakozas hosszat adja vissza."""
        if self._resync:
            self._apply_resync()
        config = self._watcher.reload_if_changed()
        if config is None:
            # Meg soha nem sikerult ervenyes configot betolteni.
            return self._handle_failure(None, f"Ervenytelen vagy hianyzo config: {self._watcher.path}")

        try:
            return self._apply_config(config)
        except DisplayError as exc:
            return self._handle_failure(config, str(exc))
        except Exception as exc:
            logger.exception("Varatlan hiba a figyelociklusban.")
            return self._handle_failure(config, str(exc))

    def _apply_resync(self) -> None:
        """Ebredes utani ujrakezdes: minden korabbi megfigyeles elavult.

        Alvas/hibernalas alatt a kijelzo mas modra allhat, mas nevvel
        jelentkezhet, es a driver mas frekvenciakat kinalhat, ezert a
        gyorsitotarakat eldobjuk. A hibaritkitast is visszavesszuk: egy
        ebredes uj helyzet, nem a korabbi hiba folytatasa.
        """
        self._resync = False
        self._rate_cache.clear()
        self._rejected.clear()
        self._monitor_identity = None
        self._consecutive_failures = min(self._consecutive_failures, 1)

    def _apply_config(self, config: Config) -> float:
        monitor = self._resolve_monitor(config)
        if monitor is None:
            # Tipikus ok: futas kozben kihuzott kijelzo.
            # Az elerheto monitorok felsorolasa a leghasznosabb resz a
            # felhasznalonak: ebbol latja, mire kell atirnia a configot.
            return self._handle_failure(
                config,
                f"A(z) {config.monitor!r} monitor nem talalhato "
                f"(kihuztad, vagy elaludt a kijelzo?). Elerheto: {describe_monitors()}",
            )

        self._check_monitor_identity(monitor, config)

        game = find_active_game(config.games)
        desired = game.refresh_rate if game else config.default_refresh_rate

        mode = current_mode(monitor.device_name)
        self._invalidate_if_changed(mode.width, mode.height)

        changed, warning = self._ensure_rate(config, monitor, mode, desired, game)
        if changed:
            # A valtas megtortent -- olvassuk vissza a tenyleges erteket.
            mode = current_mode(monitor.device_name)

        if self._consecutive_failures:
            logger.warning("A monitorozas helyreallt (%s).", monitor.friendly_name)
        self._consecutive_failures = 0

        self._publish(
            SwitcherState(
                refresh_rate=mode.frequency,
                game=game,
                monitor=monitor,
                warning=warning,
            )
        )
        return config.check_interval

    def _ensure_rate(
        self,
        config: Config,
        monitor: Monitor,
        mode: DisplayMode,
        desired: int,
        game: GameMatch | None,
    ) -> tuple[bool, str | None]:
        """Beallitja a kivant frekvenciat, ha kell.

        Visszateres: ``(valtozott_e, figyelmeztetes)``. A figyelmeztetes nem
        vegzetes -- a program tovabb fut a monitor jelenlegi modjan.
        """
        if mode.frequency == desired:
            return False, None

        key = (monitor.device_name, desired)
        known = self._rejected.get(key)
        if known is not None:
            # Mar probaltuk, es nem ment: ne hivogassuk feleslegesen a drivert.
            return False, known

        if game is None and not config.enforce_default:
            # A felhasznalo kikapcsolta az alapertelmezett kenyszeriteset:
            # jatek nelkul nem nyulunk a kezzel allitott frekvenciahoz.
            return False, None

        supported = self._rate_cache.get(monitor.device_name, mode)
        if supported and desired not in supported:
            message = (
                f"A {desired} Hz nem tamogatott a(z) {monitor.friendly_name} monitoron "
                f"{mode.width}x{mode.height} felbontason. "
                f"Tamogatott: {', '.join(f'{rate} Hz' for rate in supported)}"
            )
            self._rejected[key] = message
            logger.warning("%s", message)
            return False, message

        if game is not None:
            logger.warning(
                "Jatek fut: %s -> valtas %d Hz-re (%s)",
                game.display_name,
                desired,
                monitor.friendly_name,
            )
        else:
            logger.warning("Visszaallas alapertelmezettre: %d Hz (%s)", desired, monitor.friendly_name)

        if set_refresh_rate(monitor.device_name, desired):
            self._touched_device = monitor.device_name
            return True, None

        message = f"A {desired} Hz beallitasa nem sikerult (a driver visszautasitotta)."
        self._rejected[key] = message
        return False, message

    def _resolve_monitor(self, config: Config) -> Monitor | None:
        """Feloldja a configban megadott monitort, ebredes utan is.

        Nev szerinti kivalasztasnal megjegyezzuk, melyik eszkoz felelt meg a
        nevnek. A Windows ugyanis egy ebredes vagy ujracsatlakozas utan
        atmenetileg -- neha veglegesen, amig a monitor INF-je be nem tolt --
        ``Generic PnP Monitor``-kent jelenti a kijelzot; ilyenkor a nev nem
        talal, es a program hasznalhatatlanna valna. Ha a korabban azonositott
        eszkoz meg csatlakozik, tovabb hasznaljuk.
        """
        selector = config.monitor if isinstance(config.monitor, str) else None
        monitor = resolve_monitor(config.monitor)

        if monitor is not None:
            if selector is not None:
                if self._pinned_fallback:
                    logger.warning(
                        "A(z) %r monitor ujra a nevevel azonosithato (%s).",
                        selector,
                        monitor.friendly_name,
                    )
                self._pinned = (selector, monitor.device_name)
            self._pinned_fallback = False
            return monitor

        if selector is None or self._pinned is None or self._pinned[0] != selector:
            self._pinned_fallback = False
            return None

        fallback = resolve_monitor(self._pinned[1])
        if fallback is None:
            self._pinned_fallback = False
            return None

        if not self._pinned_fallback:
            self._pinned_fallback = True
            logger.warning(
                "A(z) %r nev most nem talal (a Windows %r nevet jelent), ezert a "
                "korabban hozza azonositott %s eszkozt hasznalom tovabb. Ha ez nem "
                "a kivant kijelzo, ird at a 'monitor' beallitast eszkoznevre.",
                selector,
                fallback.friendly_name,
                fallback.device_name,
            )
        return fallback

    def _check_monitor_identity(self, monitor: Monitor, config: Config) -> None:
        """Figyelmeztet, ha a kivalasztott sorszam mas fizikai kijelzore mutat."""
        identity = (monitor.device_name, monitor.friendly_name)
        previous = self._monitor_identity
        if previous is not None and previous != identity:
            if previous[0] != identity[0]:
                # Mas eszkoz: a sorszam mashova mutat, mint az elozo korben.
                logger.warning(
                    "A kivalasztott monitor megvaltozott: %s -> %s. "
                    "Valoszinuleg kijelzot csatlakoztattal vagy huztal ki. "
                    "Rogzitett kivalasztashoz add meg a monitor nevet szovegkent a "
                    "'monitor' beallitasban (jelenleg: %r).",
                    previous[1],
                    monitor.friendly_name,
                    config.monitor,
                )
            else:
                # Ugyanaz az eszkoz, mas nevvel: a Windows ebredes vagy
                # driver-betoltes kozben elobb 'Generic PnP Monitor'-t jelent,
                # majd a valodi nevet. Ez nem hiba, es nem is figyelmeztetes --
                # kulonben minden ebredes ket sort irna a naploba.
                logger.info(
                    "A(z) %s monitor neve megvaltozott: %s -> %s",
                    identity[0],
                    previous[1],
                    identity[1],
                )
            # A regi kijelzore vonatkozo dontesek ervenyuket vesztik.
            self._rejected.clear()
            self._rate_cache.clear()
            if previous[0] != identity[0]:
                self._touched_device = None
        self._monitor_identity = identity

    def _invalidate_if_changed(self, width: int, height: int) -> None:
        """Config- vagy felbontasvaltas utan ujraertekeljuk a "nem tamogatott" dontest."""
        fingerprint = (self._watcher.generation, width, height)
        if fingerprint != self._fingerprint:
            self._fingerprint = fingerprint
            self._rejected.clear()

    def _handle_failure(self, config: Config | None, message: str) -> float:
        self._consecutive_failures += 1
        if self._consecutive_failures == 1:
            logger.error("%s", message)
        elif self._consecutive_failures == _BACKOFF_AFTER_FAILURES:
            logger.error("%s (a tovabbi azonos hibak elnyomva)", message)

        base = config.check_interval if config else _NO_CONFIG_INTERVAL
        state = self.state
        self._publish(
            SwitcherState(
                refresh_rate=state.refresh_rate if state else 0,
                game=state.game if state else None,
                monitor=state.monitor if state else None,
                error=message,
            )
        )
        if self._consecutive_failures < _BACKOFF_AFTER_FAILURES:
            return base
        # Exponencialis ritkitas, hogy egy tartos hiba ne terhelje a rendszert.
        factor = 2 ** min(self._consecutive_failures - _BACKOFF_AFTER_FAILURES, 6)
        return min(base * factor, _MAX_BACKOFF_SECONDS)

    def _restore_on_exit(self) -> None:
        """Kilepeskor visszaallitja az alapertelmezett frekvenciat."""
        if self._touched_device is None:
            return
        config = self._watcher.current
        if config is None or not config.restore_on_exit:
            return
        device_name = self._touched_device
        default_rate = config.default_refresh_rate
        try:
            if current_mode(device_name).frequency != default_rate:
                logger.warning("Kilepes -> visszaallas %d Hz-re", default_rate)
                set_refresh_rate(device_name, default_rate)
        except Exception:
            logger.exception("Nem sikerult visszaallitani az alapertelmezett frekvenciat.")


def run_forever(watcher: ConfigWatcher, listener: StateListener | None = None) -> RefreshSwitcher:
    """Kenyelmi fuggveny: letrehoz es elindit egy switchert az aktualis szalon."""
    switcher = RefreshSwitcher(watcher, listener)
    switcher.run()
    return switcher
