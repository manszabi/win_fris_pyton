"""Alvas / ebredes / kijelzovaltas eszlelese a tray ablakan keresztul.

Miert kell ez? Alvas (S3) es hibernalas (S4) utan a Windows sajat magatol
visszaallitja a kijelzo modjat, es a monitor gyakran csak masodpercekkel
kesobb jelentkezik be ujra. A figyelociklus emiatt eppen az ebredes utani
pillanatokban futhat hibara, es a hibaritkitas miatt akar egy percet is
varhatna a kovetkezo probalkozassal -- kozben a kepernyo 60 Hz-en all.

Ahelyett, hogy suruvebben kerdezgetnenk a rendszert (az CPU-t egetne), a
Windows *sajat* ertesiteseire iratkozunk fel. A pystray ikonjanak amugy is van
egy legfelso szintu ablaka, es minden legfelso szintu ablak megkapja a
``WM_POWERBROADCAST`` es ``WM_DISPLAYCHANGE`` uzeneteket -- nincs szukseg sem
uj szalra, sem uj ablakra, sem varakozo ciklusra.

A pystray uzenetkezelo-tablaja (``Icon._message_handlers``) nem publikus API,
ezert minden lepes vedett: ha egy jovobeli pystray verzioban maskepp nez ki, a
felirat egyszeruen elmarad, es a program a szokasos idozitessel dolgozik
tovabb.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

#: A kepernyo modja (felbontas vagy frissitesi frekvencia) megvaltozott.
WM_DISPLAYCHANGE = 0x007E
#: Energiagazdalkodasi esemeny (alvas, ebredes, akkumulator).
WM_POWERBROADCAST = 0x0218

PBT_APMSUSPEND = 0x0004
PBT_APMRESUMESUSPEND = 0x0007
PBT_APMRESUMEAUTOMATIC = 0x0012

#: Az ebredest jelzo esemenyek. A Windows az automatikus ebredest
#: (``PBT_APMRESUMEAUTOMATIC``) mindig elkuldi; a felhasznaloi ebredest
#: (``PBT_APMRESUMESUSPEND``) csak akkor, ha a gepnel ul valaki.
_RESUME_EVENTS = {
    PBT_APMRESUMEAUTOMATIC: "automatikus ebredes",
    PBT_APMRESUMESUSPEND: "ebredes felhasznaloi beavatkozasra",
}

#: A ``WM_POWERBROADCAST`` valasza a dokumentacio szerint ``TRUE``.
_TRUE = 1


def attach(icon: object, on_wake: Callable[[str], None]) -> bool:
    """Felirat a tray ablakanak energia- es kijelzo-esemenyeire.

    ``on_wake`` a Windows uzenethurokjabol hivodik, ezert *nem* vegezhet
    erdemi munkat: csak jelezzen a figyelociklusnak.

    Visszateres: sikerult-e felkapcsolodni.
    """
    handlers = getattr(icon, "_message_handlers", None)
    if not isinstance(handlers, dict):
        logger.info("A rendszeresemenyek nem figyelhetok (ismeretlen pystray valtozat).")
        return False

    previous_display = handlers.get(WM_DISPLAYCHANGE)

    def _on_display_change(wparam: int, lparam: int) -> int:
        # A pystray sajat kezeloje teszi ki ujra az ikont a modvaltas utan --
        # ezt meg kell hivnunk, kulonben elveszne az ikon elesse tetele.
        result = previous_display(wparam, lparam) if previous_display is not None else 0
        # Ezt a program sajat frekvenciavaltasa is kivaltja, ezert csak debug.
        _notify(on_wake, "kijelzovaltas", level=logging.DEBUG)
        return int(result or 0)

    def _on_power(wparam: int, lparam: int) -> int:
        if wparam == PBT_APMSUSPEND:
            # Nem ebresztes, de a naploban ez mutatja meg, hogy a gep aludt --
            # e nelkul az ebredes utani hibak elozmeny nelkul allnanak ott.
            logger.warning("A rendszer alvo/hibernalt allapotba megy.")
            return _TRUE
        reason = _RESUME_EVENTS.get(wparam)
        if reason is not None:
            _notify(on_wake, reason, level=logging.WARNING)
        return _TRUE

    handlers[WM_DISPLAYCHANGE] = _on_display_change
    handlers[WM_POWERBROADCAST] = _on_power
    logger.debug("Rendszeresemeny-figyeles bekapcsolva (energia, kijelzovaltas).")
    return True


def _notify(on_wake: Callable[[str], None], reason: str, *, level: int) -> None:
    """Ertesiti a figyelociklust; a hibaja nem allithatja meg az uzenethurkot."""
    logger.log(level, "Rendszeresemeny: %s -> azonnali ellenorzes.", reason)
    try:
        on_wake(reason)
    except Exception:
        logger.warning("A rendszeresemeny feldolgozasa nem sikerult.", exc_info=True)
