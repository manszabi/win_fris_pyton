"""Jatek-felismeres: az *eloszor elinditott* jatek beallitasa nyer."""

from __future__ import annotations

from typing import ClassVar

import pytest

from refreshswitcher.games import find_active_game, iter_running_games

GAMES = {"a.exe": 240, "b.exe": 360, "c.exe": 144}


@pytest.fixture
def procs(fake_processes, monkeypatch):
    """A ``create_time`` is szamit, ezert sajat processz-listat hasznalunk."""
    import refreshswitcher.games as games_module

    entries: list[tuple[int, str, float]] = []

    class _Proc:
        def __init__(self, pid, name, started):
            self.info = {"pid": pid, "name": name, "create_time": started}

    monkeypatch.setattr(
        games_module.psutil,
        "process_iter",
        lambda attrs=None: [_Proc(*entry) for entry in entries],
    )
    return entries


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
    import refreshswitcher.games as games_module

    class _Proc:
        def __init__(self, info):
            self.info = info

    entries = [
        _Proc({"pid": 1, "name": "b.exe", "create_time": None}),  # AccessDenied eset
        _Proc({"pid": 2, "name": "a.exe", "create_time": 500.0}),
    ]
    games_module.psutil.process_iter = lambda attrs=None: entries
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

    class _Alive:
        info: ClassVar[dict] = {"pid": 2, "name": "a.exe", "create_time": 1.0}

    monkeypatch.setattr(games_module.psutil, "process_iter", lambda attrs=None: [_Dead(), _Alive()])
    assert find_active_game(GAMES).process_name == "a.exe"
