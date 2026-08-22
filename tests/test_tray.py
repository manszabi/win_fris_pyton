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


# --- a tooltip hossza: ez volt a naploban jelentett hiba gyokere ---------------


def test_error_tooltip_stays_within_the_windows_limit(tray):
    """A hibauzenet felsorolja a monitorokat is -- konnyen 200 karakter folott van.

    A pystray a cimet az ervenyesites *elott* tarolja el, ezert egy tul hosszu
    szoveg utan mar a trayre visszatetel is elszall: az ikon eltunik, a program
    pedig lathatatlanul fut tovabb. Ez tortent 2026-08-22-en a naplo szerint.
    """
    import refreshswitcher.tray as tray_module
    from refreshswitcher.switcher import SwitcherState

    error = (
        "A(z) 'VG27AQML5A' monitor nem talalhato (kihuztad, vagy elaludt a kijelzo?). "
        "Elerheto: 1. Generic PnP Monitor (\\\\.\\DISPLAY1) [elsodleges]; "
        "2. Masik Nagyon Hosszu Nevu Monitor (\\\\.\\DISPLAY2)"
    )
    state = SwitcherState(0, None, None, error=error)
    assert len(error) > tray_module.TOOLTIP_LIMIT, "az eset csak hosszu uzenettel eleteszeru"
    assert len(tray._tooltip_for(state)) <= tray_module.TOOLTIP_LIMIT


def test_every_tooltip_branch_is_clamped(tray, monitor):
    import refreshswitcher.tray as tray_module
    from refreshswitcher.games import GameMatch
    from refreshswitcher.switcher import SwitcherState

    long_text = "x" * 400
    long_monitor = type(monitor)(1, r"\\.\DISPLAY1", long_text, True)
    states = [
        None,
        SwitcherState(0, None, None, error=long_text),
        SwitcherState(240, GameMatch(long_text + ".exe", 240, 1, 1.0), long_monitor),
        SwitcherState(120, None, long_monitor, warning=long_text),
    ]
    for state in states:
        assert len(tray._tooltip_for(state)) <= tray_module.TOOLTIP_LIMIT


class _FlakyIcon:
    """Tray ikon, aminek az elso frissitese elszall (mint a pystray ValueError-ja)."""

    def __init__(self) -> None:
        self._visible = True
        self.title = ""
        self.icon = None
        self.transitions: list[bool] = []
        self.fail_next = True

    @property
    def visible(self) -> bool:
        return self._visible

    @visible.setter
    def visible(self, value: bool) -> None:
        self._visible = value
        self.transitions.append(value)

    def update_menu(self) -> None:
        if self.fail_next:
            self.fail_next = False
            raise ValueError("string too long (185, maximum length 128)")


def test_failed_update_puts_the_icon_back_on_the_tray(tray, monitor):
    import refreshswitcher.tray as tray_module
    from refreshswitcher.switcher import SwitcherState

    icon = _FlakyIcon()
    tray._icon = icon
    tray._on_state(SwitcherState(120, None, monitor))

    assert icon.transitions == [False, True], "a hibas frissites utan ujra ki kell tenni az ikont"
    assert icon.title == tray_module.APP_TITLE, "eloszor egy biztosan rovid cim kell"


def test_state_update_failure_does_not_reach_the_switcher(tray, monitor):
    """A tray hibaja nem szakithatja meg a figyelociklust."""
    from refreshswitcher.switcher import SwitcherState

    tray._icon = _FlakyIcon()
    tray._on_state(SwitcherState(120, None, monitor))  # nem dobhat


# --- az uzenethurok varatlan leallasa -----------------------------------------


def test_unexpected_message_loop_exit_is_retried(tray, monkeypatch, caplog):
    """Ha a pystray hurokja kilepesi keres nelkul all le, ujra kell epiteni az ikont."""
    import refreshswitcher.tray as tray_module

    runs: list[object] = []

    class _DeadIcon:
        def __init__(self, *args, **kwargs) -> None:
            self.visible = False

        def run(self, setup=None) -> None:
            runs.append(self)  # azonnal visszater, kilepest senki nem kert

    monkeypatch.setattr(tray_module.pystray, "Icon", _DeadIcon)
    monkeypatch.setattr(tray_module, "ICON_RESTART_DELAY", 0)

    with caplog.at_level("ERROR", logger="refreshswitcher.tray"):
        assert tray.run() == 1
    assert len(runs) == 1 + tray_module.MAX_ICON_RESTARTS
    assert any("ujraepites" in record.message for record in caplog.records)


def test_quit_from_the_menu_exits_without_a_restart(tray, monkeypatch):
    import refreshswitcher.tray as tray_module

    runs: list[object] = []

    class _QuittingIcon:
        def __init__(self, *args, **kwargs) -> None:
            self.visible = True

        def run(self, setup=None) -> None:
            runs.append(self)
            tray._on_quit(self)  # a felhasznalo a menubol lep ki

        def stop(self) -> None:
            pass

    monkeypatch.setattr(tray_module.pystray, "Icon", _QuittingIcon)
    assert tray.run() == 0
    assert len(runs) == 1
    assert tray._switcher.stopping


class _WindowsLikeIcon:
    """A pystray win32 backendjenek viselkedese, a hibaval egyutt.

    A cimet az ervenyesites *elott* tarolja el, es a ``NOTIFYICONDATAW``
    128 karakteres korlatja felett ``ValueError``-t dob. Emiatt egy tul hosszu
    tooltip utan a kepernyo modvaltasakor (``WM_DISPLAYCHANGE``) az ikon
    lekerul a trayrol, es mar nem tud visszakerulni.
    """

    LIMIT = 128

    def __init__(self) -> None:
        self._title = ""
        self.visible = True
        self.icon = None
        self.on_tray = True

    @property
    def title(self) -> str:
        return self._title

    @title.setter
    def title(self, value: str) -> None:
        self._title = value  # a pystray is elobb tarol, csak utana ervenyesit
        self._send(value)

    def _send(self, value: str) -> None:
        if len(value) >= self.LIMIT:
            raise ValueError(f"string too long ({len(value)}, maximum length {self.LIMIT})")

    def update_menu(self) -> None:
        pass

    def display_change(self) -> None:
        """A pystray ``WM_DISPLAYCHANGE`` kezeloje: leveszi, majd visszateszi az ikont."""
        self.on_tray = False
        self._send(self._title)
        self.on_tray = True


def test_long_error_does_not_knock_the_icon_off_the_tray(tray):
    """Vegponttol vegpontig: a 2026-08-22-i naploban rogzitett hibalanc."""
    from refreshswitcher.switcher import SwitcherState

    icon = _WindowsLikeIcon()
    tray._icon = icon
    error = (
        "A(z) 'VG27AQML5A' monitor nem talalhato (kihuztad, vagy elaludt a kijelzo?). "
        "Elerheto: 1. Generic PnP Monitor (\\\\.\\DISPLAY1) [elsodleges]"
    )
    tray._on_state(SwitcherState(0, None, None, error=error))

    icon.display_change()  # alvas/ebredes vagy sajat frekvenciavaltas
    assert icon.on_tray, "a hibauzenet miatt nem tunhet el a tray ikon"
