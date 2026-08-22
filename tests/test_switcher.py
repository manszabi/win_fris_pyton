"""Vegponttol vegpontig tesztek a valtologikara.

Kulon lefedve a felhasznalo altal kert forgatokonyvek:

1. Ket parhuzamosan futo jatek -> az elsokent inditott beallitasa marad.
2. Tobb kepernyo; kijelzo eltavolitasa futas kozben.
3. A monitor altal nem tamogatott frekvencia kerese.
4. A Windowsban beallitott frekvencia alacsonyabb a kertnel.
5. Visszateres az alapertelmezetthez a jatekok bezarasakor.
6. A jatek a hatterben fut (asztalra valtottunk) -> ne valtogasson.
"""

from __future__ import annotations

import json

import pytest

from refreshswitcher.config import ConfigWatcher
from tests.conftest import FakeDisplay, fake_process_iter


@pytest.fixture
def displays():
    return [
        FakeDisplay(
            r"\\.\DISPLAY1", "Fo monitor", frequency=120, supported=(60, 120, 240, 360), primary=True
        ),
        FakeDisplay(r"\\.\DISPLAY2", "Masodik monitor", frequency=60, supported=(60, 75), primary=False),
    ]


@pytest.fixture
def config_file(tmp_path):
    def _write(**overrides):
        data = {
            "monitor": 1,
            "default_refresh_rate": 120,
            "check_interval": 0.5,
            "games": {"a.exe": 240, "b.exe": 360, "slow.exe": 60},
        }
        data.update(overrides)
        path = tmp_path / "config.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    return _write


@pytest.fixture
def processes(monkeypatch):
    """Beallithato ``(pid, nev, inditasi_ido)`` lista."""
    import refreshswitcher.games as games_module

    games_module.reset_name_cache()
    entries: list[tuple[int, str, float]] = []
    monkeypatch.setattr(games_module.psutil, "process_iter", fake_process_iter(entries, []))
    return entries


@pytest.fixture
def make_switcher(win32, config_file, processes):
    """Egy switcher, aminek a ciklusai kezzel leptethetok (``_tick``)."""
    import importlib

    import refreshswitcher.switcher as switcher_module

    importlib.reload(switcher_module)

    def _make(**overrides):
        watcher = ConfigWatcher(config_file(**overrides))
        states = []
        switcher = switcher_module.RefreshSwitcher(watcher, listener=states.append)
        return switcher, states

    return _make


# --- 5. forgatokonyv: alapertelmezett frekvencia --------------------------------


def test_default_rate_is_enforced_at_startup(make_switcher, displays):
    displays[0].frequency = 60
    switcher, states = make_switcher()
    switcher._tick()
    assert displays[0].frequency == 120
    assert states[-1].refresh_rate == 120
    assert states[-1].game is None


def test_game_start_raises_rate_and_exit_restores_it(make_switcher, displays, processes):
    """5. forgatokonyv: a jatek bezarasa utan visszaall az alapertelmezett."""
    switcher, states = make_switcher()
    switcher._tick()
    assert displays[0].frequency == 120

    processes.append((1, "a.exe", 100.0))
    switcher._tick()
    assert displays[0].frequency == 240
    assert states[-1].game_name == "a"

    processes.clear()
    switcher._tick()
    assert displays[0].frequency == 120
    assert states[-1].game is None


def test_restore_on_exit_after_hard_shutdown(make_switcher, displays, processes):
    """Kilepes jatek kozben -> a monitor nem marad emelt Hz-en."""
    switcher, _ = make_switcher()
    processes.append((1, "a.exe", 100.0))
    switcher._tick()
    assert displays[0].frequency == 240

    switcher._restore_on_exit()
    assert displays[0].frequency == 120


def test_restore_on_exit_can_be_disabled(make_switcher, displays, processes):
    switcher, _ = make_switcher(restore_on_exit=False)
    processes.append((1, "a.exe", 100.0))
    switcher._tick()
    switcher._restore_on_exit()
    assert displays[0].frequency == 240


# --- 1. forgatokonyv: tobb jatek egyszerre -------------------------------------


def test_second_game_does_not_override_the_first(make_switcher, displays, processes):
    switcher, _ = make_switcher()
    processes.append((1, "a.exe", 100.0))  # 240 Hz, eloszor indult
    switcher._tick()
    assert displays[0].frequency == 240

    processes.append((2, "b.exe", 200.0))  # 360 Hz, kesobb indult
    calls_before = len(win32_calls(switcher))
    switcher._tick()
    assert displays[0].frequency == 240, "a masodik jatek nem irhatja felul az elsot"
    assert len(win32_calls(switcher)) == calls_before, "felesleges modvaltas tortent"


def test_second_game_takes_over_after_the_first_closes(make_switcher, displays, processes):
    switcher, _ = make_switcher()
    processes.extend([(1, "a.exe", 100.0), (2, "b.exe", 200.0)])
    switcher._tick()
    assert displays[0].frequency == 240

    processes.remove((1, "a.exe", 100.0))  # az elso jatek bezarul
    switcher._tick()
    assert displays[0].frequency == 360

    processes.clear()
    switcher._tick()
    assert displays[0].frequency == 120


def test_first_game_wins_even_if_it_wants_a_lower_rate(make_switcher, displays, processes):
    """A prioritas az inditas sorrendje, nem a magasabb Hz."""
    switcher, _ = make_switcher()
    processes.append((1, "slow.exe", 100.0))  # 60 Hz
    processes.append((2, "b.exe", 200.0))  # 360 Hz
    switcher._tick()
    assert displays[0].frequency == 60


# --- 6. forgatokonyv: hatterben futo jatek -------------------------------------


def test_backgrounded_game_keeps_its_rate_without_flapping(make_switcher, displays, processes):
    """Asztalra valtas kozben a jatek tovabb fut -> a frekvencia valtozatlan."""
    switcher, states = make_switcher()
    processes.append((1, "a.exe", 100.0))
    switcher._tick()
    assert displays[0].frequency == 240

    calls_before = len(win32_calls(switcher))
    for _ in range(10):  # tobb kor, mintha percekig az asztalon lennenk
        switcher._tick()
    assert displays[0].frequency == 240
    assert len(win32_calls(switcher)) == calls_before, "nem szabad modvaltast kezdemenyezni"
    # Az allapot sem valtozott, tehat a tray ikon sem villog.
    assert len(states) == 1


def test_manual_windows_change_is_corrected_while_a_game_runs(make_switcher, displays, processes):
    """Ha a Windows visszaesik (pl. alvas utan), a program helyreallitja."""
    switcher, _ = make_switcher()
    processes.append((1, "a.exe", 100.0))
    switcher._tick()
    assert displays[0].frequency == 240

    displays[0].frequency = 60  # a Windows visszaallitotta
    switcher._tick()
    assert displays[0].frequency == 240


# --- 4. forgatokonyv: alacsonyabb Windows-beallitas ----------------------------


def test_lower_windows_rate_is_raised_to_the_configured_default(make_switcher, displays):
    displays[0].frequency = 60
    switcher, _ = make_switcher(default_refresh_rate=240)
    switcher._tick()
    assert displays[0].frequency == 240


def test_enforce_default_false_leaves_a_manually_set_rate_alone(make_switcher, displays, processes):
    """Aki kezzel allitja a Hz-et, kikapcsolhatja a kenyszeritest."""
    displays[0].frequency = 60
    switcher, _ = make_switcher(enforce_default=False)
    switcher._tick()
    assert displays[0].frequency == 60, "jatek nelkul nem szabad hozzanyulni"

    processes.append((1, "a.exe", 100.0))
    switcher._tick()
    assert displays[0].frequency == 240, "jatek indulasakor viszont valtania kell"


# --- 3. forgatokonyv: nem tamogatott frekvencia --------------------------------


def test_unsupported_rate_warns_once_and_keeps_running(make_switcher, displays, processes, caplog):
    switcher, states = make_switcher(games={"a.exe": 500})
    processes.append((1, "a.exe", 100.0))

    with caplog.at_level("WARNING", logger="refreshswitcher.switcher"):
        switcher._tick()
        first_warnings = len([r for r in caplog.records if "nem tamogatott" in r.message])
        for _ in range(5):
            switcher._tick()
        total_warnings = len([r for r in caplog.records if "nem tamogatott" in r.message])

    assert displays[0].frequency == 120, "a monitor a korabbi ervenyes modjan marad"
    assert first_warnings == 1
    assert total_warnings == 1, "a figyelmeztetes nem ismetlodhet minden korben"
    assert states[-1].warning is not None
    assert states[-1].error is None, "ez nem vegzetes hiba, a program fut tovabb"


def test_driver_rejection_is_handled_gracefully(make_switcher, displays, processes):
    """A mod szerepel a listaban, de a driver megis visszautasitja."""
    displays[0].reject = {240}
    switcher, states = make_switcher()
    processes.append((1, "a.exe", 100.0))
    switcher._tick()
    assert displays[0].frequency == 120
    assert states[-1].warning is not None


def test_config_fix_clears_the_rejection(make_switcher, displays, processes, config_file):
    switcher, _ = make_switcher(games={"a.exe": 500})
    processes.append((1, "a.exe", 100.0))
    switcher._tick()
    assert displays[0].frequency == 120

    config_file(games={"a.exe": 240})  # a felhasznalo javitja a configot
    switcher._tick()
    assert displays[0].frequency == 240


# --- 2. forgatokonyv: tobb kepernyo, kijelzo eltavolitasa ----------------------


def test_second_monitor_is_controlled_independently(make_switcher, displays, processes):
    switcher, _ = make_switcher(monitor=2, default_refresh_rate=75)
    switcher._tick()
    assert displays[1].frequency == 75
    assert displays[0].frequency == 120, "a masik monitorhoz nem nyulhat"


def test_unplugged_monitor_reports_an_error_and_recovers(make_switcher, displays):
    switcher, states = make_switcher(monitor=2, default_refresh_rate=75)
    switcher._tick()
    assert states[-1].error is None

    removed = displays.pop()  # kihuzzuk a masodik kijelzot
    delay = switcher._tick()
    assert states[-1].error is not None
    assert "nem talalhato" in states[-1].error
    assert delay > 0, "a ciklus nem allhat le"

    displays.append(removed)  # visszadugjuk
    switcher._tick()
    assert states[-1].error is None


def test_repeated_failures_back_off(make_switcher, displays):
    switcher, _ = make_switcher(monitor=2)
    displays.pop()
    delays = [switcher._tick() for _ in range(8)]
    assert delays[0] <= delays[-1]
    assert delays[-1] >= delays[0] * 2, "tartos hiba eseten ritkitani kell az ujraprobalkozast"
    assert max(delays) <= 60.0


def test_monitor_index_pointing_to_a_different_display_is_reported(make_switcher, displays, caplog):
    """Kijelzo kihuzasakor a sorszamok elcsusznak -- ezt eszre kell venni."""
    switcher, _ = make_switcher(monitor=1)
    switcher._tick()

    displays.pop(0)  # az elso monitort huzzuk ki -> a masodik lesz az 1-es
    with caplog.at_level("WARNING", logger="refreshswitcher.switcher"):
        switcher._tick()
    assert any("megvaltozott" in record.message for record in caplog.records)


def test_monitor_can_be_pinned_by_name(make_switcher, displays):
    """Nev szerinti kivalasztas eseten a sorszam-elcsuszas nem szamit."""
    switcher, states = make_switcher(monitor="Masodik monitor", default_refresh_rate=75)
    switcher._tick()
    assert displays[1].frequency == 75

    displays.pop(0)  # az elso monitor kihuzasa
    switcher._tick()
    assert states[-1].error is None
    assert states[-1].monitor.friendly_name == "Masodik monitor"


# --- altalanos robusztussag ----------------------------------------------------


def test_missing_config_does_not_kill_the_loop(win32, tmp_path):
    import refreshswitcher.switcher as switcher_module

    switcher = switcher_module.RefreshSwitcher(ConfigWatcher(tmp_path / "nincs.json"))
    for _ in range(3):
        assert switcher._tick() > 0


def test_unexpected_exception_is_contained(make_switcher, monkeypatch):
    import refreshswitcher.switcher as switcher_module

    switcher, states = make_switcher()
    monkeypatch.setattr(
        switcher_module, "find_active_game", lambda games: (_ for _ in ()).throw(RuntimeError("bumm"))
    )
    assert switcher._tick() > 0  # a ciklus tulel
    assert states[-1].error == "bumm"


def test_stop_event_short_circuits_the_wait(make_switcher):
    import threading

    switcher, _ = make_switcher(check_interval=3600)
    thread = threading.Thread(target=switcher.run)
    thread.start()
    switcher.stop()
    thread.join(timeout=5)
    assert not thread.is_alive(), "a kilepes nem varhatja meg a teljes check_interval-t"


def win32_calls(switcher):
    """A hamis driver fele indult modvaltasi hivasok (a CDS_TEST-eket is beleertve)."""
    import refreshswitcher.display as display_module

    return display_module.win32api.change_calls


def test_unplug_error_lists_the_available_monitors(make_switcher, displays):
    """A felhasznalo ebbol latja, mire kell atirnia a configot."""
    switcher, states = make_switcher(monitor=2)
    switcher._tick()
    displays.pop()
    switcher._tick()
    assert "Fo monitor" in states[-1].error


def test_unplugged_monitor_does_not_spam_the_log(make_switcher, displays, caplog):
    """Egy ejszakan at kihuzott kijelzo nem irhatja tele a naplot."""
    switcher, _ = make_switcher(monitor=2)
    displays.pop()
    with caplog.at_level("WARNING", logger="refreshswitcher"):
        for _ in range(20):
            switcher._tick()
    errors = [r for r in caplog.records if r.levelname in {"ERROR", "WARNING"}]
    assert len(errors) <= 2, f"tul sok naplobejegyzes: {[r.message for r in errors]}"


# --- alvas / ebredes -----------------------------------------------------------


def test_wake_shortens_the_backoff_after_a_resume(make_switcher, displays):
    """Ebredeskor nem varhatunk egy percet arra, hogy a kepernyo helyrealljon."""
    switcher, _ = make_switcher(monitor=2)
    displays.pop()  # a masodik kijelzo (meg) nem jelentkezett be
    for _ in range(8):
        switcher._tick()
    assert switcher._tick() > 1.0, "tartos hiba eseten ritkitani kell"

    switcher.wake("ebredes")
    assert switcher._tick() <= 1.0, "ebredes utan azonnal ujra kell probalni"


def test_wake_drops_the_cached_decisions(make_switcher, processes):
    """Alvas alatt a driver mas modokat kinalhat, mint elotte: ujra megkerdezzuk."""
    import refreshswitcher.display as display_module

    switcher, states = make_switcher(games={"a.exe": 500})
    processes.append((1, "a.exe", 100.0))
    switcher._tick()
    assert states[-1].warning is not None
    assert switcher._rejected, "az elutasitast megjegyeztuk"

    before = display_module.win32api.enum_settings_calls
    switcher._tick()
    quiet_round = display_module.win32api.enum_settings_calls - before

    before = display_module.win32api.enum_settings_calls
    switcher.wake("ebredes")
    switcher._tick()
    after_wake = display_module.win32api.enum_settings_calls - before
    assert after_wake > quiet_round, "ebredes utan ujra vegig kell kerdezni a modokat"


def test_wake_interrupts_the_waiting_loop(make_switcher):
    import threading

    switcher, _ = make_switcher(check_interval=3600)
    ticks = threading.Semaphore(0)
    original = switcher._tick

    def _counting_tick():
        result = original()
        ticks.release()
        return result

    switcher._tick = _counting_tick
    thread = threading.Thread(target=switcher.run)
    thread.start()
    try:
        assert ticks.acquire(timeout=5), "az elso kornek azonnal le kell futnia"
        switcher.wake("ebredes")
        assert ticks.acquire(timeout=5), "az ebresztes nem varhatja meg a check_interval-t"
    finally:
        switcher.stop()
        thread.join(timeout=5)
    assert not thread.is_alive()


# --- nev szerinti kivalasztas ebredes utan -------------------------------------


def test_named_monitor_survives_a_generic_windows_name(make_switcher, displays):
    """Ebredes utan a Windows atmenetileg 'Generic PnP Monitor'-t jelent.

    A naploban ez a hiba latszott: a nevre allitott kivalasztas nem talalt
    semmit, es a program hasznalhatatlanna valt.
    """
    switcher, states = make_switcher(monitor="Masodik monitor", default_refresh_rate=75)
    switcher._tick()
    assert displays[1].frequency == 75

    displays[1].friendly_name = "Generic PnP Monitor"
    displays[1].frequency = 60  # a Windows visszaallitotta ebredeskor
    switcher._tick()

    assert states[-1].error is None, "a kijelzo ott van, csak mas nevet mond"
    assert displays[1].frequency == 75


def test_generic_name_fallback_is_logged_once(make_switcher, displays, caplog):
    switcher, _ = make_switcher(monitor="Masodik monitor", default_refresh_rate=75)
    switcher._tick()
    displays[1].friendly_name = "Generic PnP Monitor"

    with caplog.at_level("WARNING", logger="refreshswitcher.switcher"):
        for _ in range(5):
            switcher._tick()
        fallback_warnings = [r for r in caplog.records if "nem talal" in r.message]
        assert len(fallback_warnings) == 1, "korrol korre nem ismetelheto"

        displays[1].friendly_name = "Masodik monitor"  # a driver betoltott
        switcher._tick()
    assert any("ujra a nevevel" in r.message for r in caplog.records)


def test_unplugged_named_monitor_still_reports_an_error(make_switcher, displays):
    """A rogzites nem fedheti el, ha a kijelzo tenylegesen eltunt."""
    switcher, states = make_switcher(monitor="Masodik monitor", default_refresh_rate=75)
    switcher._tick()
    displays.pop()  # kihuzzuk
    switcher._tick()
    assert states[-1].error is not None


def test_renamed_monitor_is_not_reported_as_a_different_display(make_switcher, displays, caplog):
    """Ugyanaz az eszkoz uj nevvel nem 'monitorcsere' -- ez spammelte a naplot."""
    switcher, _ = make_switcher(monitor=1)
    switcher._tick()

    displays[0].friendly_name = "Generic PnP Monitor"
    with caplog.at_level("WARNING", logger="refreshswitcher.switcher"):
        switcher._tick()
    assert not [r for r in caplog.records if "megvaltozott" in r.message]
