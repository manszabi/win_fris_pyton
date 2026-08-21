"""A tray felulet megjelenitesi logikaja (pystray dummy backenddel)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("PYSTRAY_BACKEND", "dummy")

pytest.importorskip("pystray", reason="a pystray nincs telepitve")
pytest.importorskip("PIL", reason="a Pillow nincs telepitve")


@pytest.fixture
def tray(win32, tmp_path):
    from refreshswitcher.config import ConfigWatcher
    from refreshswitcher.tray import TrayApp

    path = tmp_path / "config.json"
    path.write_text('{"default_refresh_rate": 120}', encoding="utf-8")
    return TrayApp(ConfigWatcher(path))


@pytest.fixture
def monitor():
    from refreshswitcher.display import Monitor

    return Monitor(1, r"\\.\DISPLAY1", "Fo monitor", True)


@pytest.mark.parametrize("text", ["1", "60", "120", "240", "1000", "!", ".."])
@pytest.mark.parametrize("size", [16, 20, 24, 32])
def test_icon_renders_at_the_requested_size(win32, text, size):
    from refreshswitcher.tray import render_icon

    image = render_icon(text, (0, 150, 70, 255), size)
    assert image.size == (size, size)
    assert image.mode == "RGBA"


def test_icon_colour_and_label_reflect_state(tray, monitor, monkeypatch):
    """Az ikon szine es felirata allapotonkent: szurke / zold / borostyan / piros."""
    import refreshswitcher.tray as tray_module
    from refreshswitcher.games import GameMatch
    from refreshswitcher.switcher import SwitcherState

    captured: list[tuple[str, tuple[int, int, int, int]]] = []
    monkeypatch.setattr(
        tray_module,
        "render_icon",
        lambda text, colour, size: captured.append((text, colour)) or _blank(size),
    )

    cases = [
        (None, "..", tray_module.COLOR_IDLE),
        (SwitcherState(120, None, monitor), "120", tray_module.COLOR_IDLE),
        (
            SwitcherState(240, GameMatch("cs2.exe", 240, 1, 1.0), monitor),
            "240",
            tray_module.COLOR_ACTIVE,
        ),
        (SwitcherState(120, None, monitor, warning="nem tamogatott"), "120", tray_module.COLOR_WARN),
        (SwitcherState(0, None, None, error="nincs monitor"), "!", tray_module.COLOR_ERROR),
    ]
    for state, expected_text, expected_colour in cases:
        captured.clear()
        tray._icon_cache.clear()
        tray._icon_for(state)
        assert captured == [(expected_text, expected_colour)]


def test_warning_colour_wins_over_game_colour(tray, monitor, monkeypatch):
    """Futo jatek mellett is borostyan, ha a kert Hz nem allithato be."""
    import refreshswitcher.tray as tray_module
    from refreshswitcher.games import GameMatch
    from refreshswitcher.switcher import SwitcherState

    captured = []
    monkeypatch.setattr(
        tray_module,
        "render_icon",
        lambda text, colour, size: captured.append(colour) or _blank(size),
    )
    tray._icon_for(SwitcherState(120, GameMatch("cs2.exe", 300, 1, 1.0), monitor, warning="nem tamogatott"))
    assert captured == [tray_module.COLOR_WARN]


def _blank(size):
    from PIL import Image

    return Image.new("RGBA", (size, size))


def test_icons_are_cached(tray, monitor):
    from refreshswitcher.switcher import SwitcherState

    state = SwitcherState(120, None, monitor)
    first = tray._icon_for(state)
    assert tray._icon_for(state) is first
    assert len(tray._icon_cache) == 1


def test_tooltip_stays_within_the_windows_limit(tray, monitor):
    from refreshswitcher.switcher import SwitcherState

    state = SwitcherState(240, None, monitor, warning="x" * 500)
    assert len(tray._tooltip_for(state)) <= 127


def test_tooltip_and_menu_include_the_game_name(tray, monitor):
    from refreshswitcher.games import GameMatch
    from refreshswitcher.switcher import SwitcherState

    tray._state = SwitcherState(240, GameMatch("cs2.exe", 240, 1, 1.0), monitor)
    assert "cs2" in tray._tooltip_for(tray._state)
    assert tray._status_text() == "240 Hz - cs2"
    assert "Fo monitor" in tray._monitor_text()


def test_state_callback_before_the_icon_exists_is_safe(tray, monitor):
    """A regi valtozatban az elso ertesites elveszett, mert az ikon meg None volt."""
    from refreshswitcher.switcher import SwitcherState

    state = SwitcherState(144, None, monitor)
    tray._on_state(state)  # nem dobhat
    assert tray._state is state
    # Amint az ikon letrejon, a tarolt allapot jelenik meg rajta.
    assert tray._status_text() == "144 Hz"


def test_menu_is_constructible(tray):
    assert tray._build_menu() is not None


def test_shutdown_without_a_worker_is_safe(tray):
    tray._shutdown()  # nem dobhat, ha a run() sosem indult el


def test_quit_stops_the_switcher(tray):
    class _Icon:
        visible = True

        def __init__(self):
            self.stopped = False

        def stop(self):
            self.stopped = True

    icon = _Icon()
    tray._on_quit(icon)
    assert icon.stopped
    assert tray._switcher.stopping


def test_open_helpers_do_not_raise(tray, monkeypatch):
    import refreshswitcher.tray as tray_module

    opened: list[Path] = []
    monkeypatch.setattr(tray_module, "_open_in_explorer", opened.append)
    tray._on_open_config()
    assert opened == [tray._watcher.path]
