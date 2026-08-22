"""Alvas/ebredes es kijelzovaltas: a rendszeruzenetek helyes feldolgozasa."""

from __future__ import annotations

import logging

from refreshswitcher import syswake


class _FakeIcon:
    """Annyit tud a pystray ikonjabol, amennyit a felirat hasznal."""

    def __init__(self, handlers: dict | None = None) -> None:
        self._message_handlers = {} if handlers is None else handlers


def test_attach_registers_both_handlers():
    icon = _FakeIcon()
    assert syswake.attach(icon, lambda reason: None) is True
    assert syswake.WM_POWERBROADCAST in icon._message_handlers
    assert syswake.WM_DISPLAYCHANGE in icon._message_handlers


def test_resume_triggers_an_immediate_recheck():
    woken: list[str] = []
    icon = _FakeIcon()
    syswake.attach(icon, woken.append)

    icon._message_handlers[syswake.WM_POWERBROADCAST](syswake.PBT_APMRESUMEAUTOMATIC, 0)
    icon._message_handlers[syswake.WM_POWERBROADCAST](syswake.PBT_APMRESUMESUSPEND, 0)
    assert len(woken) == 2


def test_suspend_is_logged_but_does_not_wake(caplog):
    """Az alvas ideje a naploban az egyetlen nyom, amibol az ebredes utani hiba ertheto."""
    woken: list[str] = []
    icon = _FakeIcon()
    syswake.attach(icon, woken.append)

    with caplog.at_level(logging.WARNING, logger="refreshswitcher.syswake"):
        icon._message_handlers[syswake.WM_POWERBROADCAST](syswake.PBT_APMSUSPEND, 0)
    assert woken == []
    assert any("alvo" in record.message for record in caplog.records)


def test_unknown_power_event_is_ignored():
    woken: list[str] = []
    icon = _FakeIcon()
    syswake.attach(icon, woken.append)
    assert icon._message_handlers[syswake.WM_POWERBROADCAST](0x0A, 0) == 1
    assert woken == []


def test_display_change_keeps_the_pystray_handler():
    """A pystray sajat kezeloje teszi ki ujra az ikont -- nem eshet ki."""
    called: list[tuple[int, int]] = []
    woken: list[str] = []

    def _pystray_handler(wparam, lparam):
        called.append((wparam, lparam))
        return 0

    icon = _FakeIcon({syswake.WM_DISPLAYCHANGE: _pystray_handler})

    syswake.attach(icon, woken.append)
    icon._message_handlers[syswake.WM_DISPLAYCHANGE](1, 2)
    assert called == [(1, 2)]
    assert woken == ["kijelzovaltas"]


def test_unknown_pystray_layout_is_tolerated():
    """Egy jovobeli pystray verzio nem allithatja meg a programot."""
    assert syswake.attach(object(), lambda reason: None) is False


def test_a_failing_callback_does_not_break_the_message_loop(caplog):
    icon = _FakeIcon()

    def _boom(_reason: str) -> None:
        raise RuntimeError("bumm")

    syswake.attach(icon, _boom)
    with caplog.at_level(logging.WARNING, logger="refreshswitcher.syswake"):
        assert icon._message_handlers[syswake.WM_POWERBROADCAST](syswake.PBT_APMRESUMEAUTOMATIC, 0) == 1
    assert any("nem sikerult" in record.message.lower() for record in caplog.records)
