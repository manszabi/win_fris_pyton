"""A Win32 kijelzo-burkolat viselkedese hamis driver mogott."""

from __future__ import annotations

import pytest

from tests.conftest import FakeDisplay


@pytest.fixture
def displays():
    return [
        FakeDisplay(r"\\.\DISPLAY1", "Fake 240Hz", supported=(60, 120, 240), primary=True),
        FakeDisplay(r"\\.\DISPLAY2", "Fake 60Hz", frequency=60, supported=(60,), primary=False),
    ]


def test_enumerate_monitors_numbers_from_one(win32):
    from refreshswitcher.display import enumerate_monitors

    monitors = enumerate_monitors()
    assert [m.index for m in monitors] == [1, 2]
    assert monitors[0].device_name == r"\\.\DISPLAY1"
    assert monitors[0].friendly_name == "Fake 240Hz"
    assert monitors[0].is_primary and not monitors[1].is_primary


def test_mirroring_drivers_are_skipped(win32, displays):
    """Virtualis/tukrozo kijelzok elcsusztatnak a sorszamozast -- ki kell hagyni oket."""
    from refreshswitcher.display import enumerate_monitors

    displays.insert(0, FakeDisplay(r"\\.\DISPLAYV", "Virtual mirror", mirroring=True, primary=False))
    monitors = enumerate_monitors()
    assert [m.friendly_name for m in monitors] == ["Fake 240Hz", "Fake 60Hz"]


def test_resolve_monitor_by_index_and_by_name(win32):
    from refreshswitcher.display import resolve_monitor

    assert resolve_monitor(2).device_name == r"\\.\DISPLAY2"
    assert resolve_monitor(r"\\.\DISPLAY2").index == 2
    assert resolve_monitor("240hz").index == 1  # nev-toredek, kis/nagybetu-fuggetlen


def test_resolve_monitor_out_of_range_returns_none(win32):
    from refreshswitcher.display import resolve_monitor

    assert resolve_monitor(3) is None
    assert resolve_monitor("nincs ilyen") is None


def test_supported_rates_are_filtered_to_current_resolution(win32):
    from refreshswitcher.display import supported_refresh_rates

    # A hamis driver 1920x1080-hoz is kinal modokat; azok nem szerepelhetnek.
    assert supported_refresh_rates(r"\\.\DISPLAY1") == (60, 120, 240)


def test_rate_cache_avoids_repeated_enumeration(win32):
    from refreshswitcher.display import RefreshRateCache, current_mode

    cache = RefreshRateCache()
    mode = current_mode(r"\\.\DISPLAY1")
    before = win32.enum_settings_calls
    cache.get(r"\\.\DISPLAY1", mode)
    after_first = win32.enum_settings_calls
    cache.get(r"\\.\DISPLAY1", mode)
    assert win32.enum_settings_calls == after_first  # a masodik hivas gyorsitotarbol jott
    assert after_first > before


def test_set_refresh_rate_applies_and_is_idempotent(win32, displays):
    from refreshswitcher.display import set_refresh_rate

    assert set_refresh_rate(r"\\.\DISPLAY1", 240) is True
    assert displays[0].frequency == 240

    calls_before = len(win32.change_calls)
    assert set_refresh_rate(r"\\.\DISPLAY1", 240) is True
    assert len(win32.change_calls) == calls_before  # mar jo volt -> nincs API hivas


def test_set_refresh_rate_tests_before_applying(win32):
    """CDS_TEST elozi meg az eles valtast -- igy nem lesz fekete kepernyo."""
    from refreshswitcher.display import CDS_TEST, set_refresh_rate

    set_refresh_rate(r"\\.\DISPLAY1", 240)  # a jelenlegi 120 Hz-rol
    assert win32.change_calls[0][2] == CDS_TEST
    assert win32.change_calls[1][2] == 0  # dinamikus valtas, registry-iras nelkul


def test_rejected_mode_is_not_applied(win32, displays):
    from refreshswitcher.display import set_refresh_rate

    displays[0].reject = {240}
    assert set_refresh_rate(r"\\.\DISPLAY1", 240) is False
    assert displays[0].frequency == 120  # valtozatlan
    assert len(win32.change_calls) == 1  # csak a teszthivas tortent meg


def test_current_mode_of_detached_device_raises_display_error(win32):
    from refreshswitcher.display import DisplayError, current_mode

    with pytest.raises(DisplayError):
        current_mode(r"\\.\DISPLAY9")


def test_enumeration_is_bounded(win32, monkeypatch):
    """Hibas driver eseten sem szabad vegtelen ciklusba kerulni."""
    import refreshswitcher.display as display_module

    monkeypatch.setattr(
        display_module.win32api,
        "EnumDisplayDevices",
        lambda device, index: type(
            "D", (), {"DeviceName": f"\\\\.\\D{index}", "DeviceString": "x", "StateFlags": 1}
        )(),
    )
    assert len(display_module.enumerate_monitors()) == display_module.MAX_ADAPTERS
