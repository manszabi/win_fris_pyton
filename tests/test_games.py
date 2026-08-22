"""Jatek-felismeres: az *eloszor elinditott* jatek beallitasa nyer."""

from __future__ import annotations

import pytest

from refreshswitcher.games import find_active_game, iter_running_games, reset_name_cache
from tests.conftest import FakeProcess, fake_process_iter

GAMES = {"a.exe": 240, "b.exe": 360, "c.exe": 144}


@pytest.fixture
def name_calls(fake_processes, monkeypatch):
    """A ``Process.name()`` hivasok naploja -- a gyorsitotar meresehez."""
    import refreshswitcher.games as games_module

    calls: list[int] = []
    monkeypatch.setattr(games_module.psutil, "process_iter", fake_process_iter(fake_processes, calls))
    return calls


@pytest.fixture
def procs(name_calls, fake_processes):
    """A processzlista ``(pid, nev, inditasi ido)`` harmasokkal."""
    return fake_processes


def test_no_games_configured_returns_none(procs):
    procs.append((1, "a.exe", 100.0))
    assert find_active_game({}) is None


def test_no_matching_process_returns_none(procs):
    procs.append((1, "explorer.exe", 100.0))
    assert find_active_game(GAMES) is None


def test_single_game_is_matched(procs):
    procs.append((1, "a.exe", 100.0))
    match = find_active_game(GAMES)
    assert match is not None
    assert match.refresh_rate == 240
    assert match.display_name == "a"


def test_first_launched_game_wins_not_the_highest_hz(procs):
    """1. forgatokonyv: a masodikkent inditott jatek beallitasa nem ervenyesul."""
    procs.append((1, "a.exe", 100.0))  # eloszor indult, 240 Hz
    procs.append((2, "b.exe", 200.0))  # kesobb indult, 360 Hz
    match = find_active_game(GAMES)
    assert match is not None
    assert match.process_name == "a.exe"
    assert match.refresh_rate == 240


def test_detection_order_does_not_matter(procs):
    """A processzek bejarasi sorrendje nem befolyasolja az eredmenyt."""
    procs.append((2, "b.exe", 200.0))
    procs.append((1, "a.exe", 100.0))
    assert find_active_game(GAMES).process_name == "a.exe"


def test_second_game_takes_over_when_first_exits(procs):
    procs.extend([(1, "a.exe", 100.0), (2, "b.exe", 200.0), (3, "c.exe", 300.0)])
    assert find_active_game(GAMES).process_name == "a.exe"

    procs.remove((1, "a.exe", 100.0))
    assert find_active_game(GAMES).process_name == "b.exe"

    procs.remove((2, "b.exe", 200.0))
    assert find_active_game(GAMES).process_name == "c.exe"

    procs.clear()
    assert find_active_game(GAMES) is None


def test_two_instances_of_the_same_game(procs):
    procs.extend([(5, "a.exe", 100.0), (6, "a.exe", 150.0)])
    match = find_active_game(GAMES)
    assert match is not None and match.pid == 5


def test_unknown_start_time_sorts_last(procs):
    procs.append((1, "b.exe", None))  # AccessDenied eset: nincs inditasi ido
    procs.append((2, "a.exe", 500.0))
    assert find_active_game(GAMES).process_name == "a.exe"


def test_iter_running_games_is_sorted_by_start_time(procs):
    procs.extend([(3, "c.exe", 300.0), (1, "a.exe", 100.0), (2, "b.exe", 200.0)])
    assert [m.process_name for m in iter_running_games(GAMES)] == ["a.exe", "b.exe", "c.exe"]


def test_dead_process_during_iteration_is_skipped(monkeypatch):
    import refreshswitcher.games as games_module

    class _Dead:
        @property
        def info(self):
            raise games_module.psutil.NoSuchProcess(1)

    reset_name_cache()
    alive = FakeProcess(2, "a.exe", 1.0)
    monkeypatch.setattr(games_module.psutil, "process_iter", lambda attrs=None: [_Dead(), alive])
    assert find_active_game(GAMES).process_name == "a.exe"


def test_process_name_is_queried_only_once_per_process(procs, name_calls):
    """A nev lekerdezese rendszerhivas; koronkent nem ismetelheto meg."""
    procs.extend([(pid, f"other{pid}.exe", float(pid)) for pid in range(1, 51)])
    procs.append((99, "a.exe", 5.0))

    assert find_active_game(GAMES).process_name == "a.exe"
    assert len(name_calls) == 51, "az elso korben minden processz nevet le kell kerdezni"

    name_calls.clear()
    for _ in range(10):
        assert find_active_game(GAMES).process_name == "a.exe"
    assert name_calls == [], "a mar ismert processzek nevet nem szabad ujra lekerdezni"

    procs.append((100, "b.exe", 600.0))  # egy uj processz indul
    find_active_game(GAMES)
    assert name_calls == [100], "csak az uj processz nevet kerdezzuk le"


def test_reused_pid_does_not_inherit_the_old_name(procs, name_calls):
    """A pid ujrahasznositasa uj inditasi idot jelent -- uj lekerdezest is."""
    procs.append((7, "a.exe", 100.0))
    assert find_active_game(GAMES).process_name == "a.exe"

    name_calls.clear()
    procs.clear()
    procs.append((7, "explorer.exe", 200.0))  # ugyanaz a pid, mas processz
    assert find_active_game(GAMES) is None
    assert name_calls == [7]


def test_cache_does_not_grow_with_dead_processes(procs):
    import refreshswitcher.games as games_module

    procs.extend([(pid, "other.exe", float(pid)) for pid in range(1, 31)])
    find_active_game(GAMES)
    assert len(games_module._name_cache) == 30

    procs.clear()
    procs.append((1, "other.exe", 1.0))
    find_active_game(GAMES)
    assert len(games_module._name_cache) == 1, "a megszunt processzek bejegyzesei kiesnek"
