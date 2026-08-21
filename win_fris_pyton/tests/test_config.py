"""Konfiguracio-validalas es biztonsagos ujratoltes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from refreshswitcher.config import Config, ConfigError, ConfigWatcher


def write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_valid_config_normalises_game_names():
    config = Config.from_mapping({"games": {"CS2": 240, "Diablo IV.exe": 300, r"C:\Games\GTA5.EXE": 144}})
    assert dict(config.games) == {"cs2.exe": 240, "diablo iv.exe": 300, "gta5.exe": 144}


def test_defaults_are_sane():
    config = Config.from_mapping({})
    assert config.monitor == 1
    assert config.default_refresh_rate == 60
    assert config.check_interval == 5.0
    assert config.restore_on_exit is True
    assert config.enforce_default is True


def test_monitor_can_be_a_device_name():
    assert Config.from_mapping({"monitor": r"\\.\DISPLAY2"}).monitor == r"\\.\DISPLAY2"


@pytest.mark.parametrize(
    "raw",
    [
        {"monitor": 0},
        {"monitor": ""},
        {"default_refresh_rate": 5},
        {"default_refresh_rate": "120"},
        {"default_refresh_rate": 1.5},
        {"check_interval": 0},
        {"check_interval": 100000},
        {"games": []},
        {"games": {"a.exe": 0}},
        {"games": {"a.exe": "240"}},
        {"log_level": "LOUD"},
    ],
)
def test_invalid_values_are_rejected(raw):
    with pytest.raises(ConfigError):
        Config.from_mapping(raw)


def test_conflicting_duplicate_game_names_are_rejected():
    with pytest.raises(ConfigError):
        Config.from_mapping({"games": {"cs2": 240, "CS2.exe": 165}})


def test_identical_duplicate_game_names_are_allowed():
    assert dict(Config.from_mapping({"games": {"cs2": 240, "CS2.exe": 240}}).games) == {"cs2.exe": 240}


def test_bom_prefixed_file_is_readable(tmp_path):
    path = tmp_path / "config.json"
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps({"default_refresh_rate": 120}).encode())
    assert Config.load(path).default_refresh_rate == 120


def test_missing_file_raises_config_error(tmp_path):
    with pytest.raises(ConfigError, match="nem talalhato"):
        Config.load(tmp_path / "nincs.json")


def test_broken_json_reports_line_and_column(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"monitor": 1,,}', encoding="utf-8")
    with pytest.raises(ConfigError, match="sor"):
        Config.load(path)


class TestConfigWatcher:
    def test_reloads_only_when_file_changes(self, tmp_path):
        path = write(tmp_path / "config.json", {"default_refresh_rate": 120})
        watcher = ConfigWatcher(path)

        first = watcher.reload_if_changed()
        assert first is not None
        assert watcher.reload_if_changed() is first  # nincs felesleges I/O
        assert watcher.generation == 1

        write(path, {"default_refresh_rate": 144})
        second = watcher.reload_if_changed()
        assert second is not None
        assert second.default_refresh_rate == 144
        assert watcher.generation == 2

    def test_keeps_last_good_config_when_file_becomes_invalid(self, tmp_path):
        path = write(tmp_path / "config.json", {"default_refresh_rate": 120})
        watcher = ConfigWatcher(path)
        good = watcher.reload_if_changed()

        path.write_text("{ ez nem json", encoding="utf-8")
        assert watcher.reload_if_changed() is good
        assert watcher.generation == 1

        # A javitas utan magatol ujratolt.
        write(path, {"default_refresh_rate": 165})
        recovered = watcher.reload_if_changed()
        assert recovered is not None
        assert recovered.default_refresh_rate == 165

    def test_returns_none_when_no_config_ever_loaded(self, tmp_path):
        watcher = ConfigWatcher(tmp_path / "nincs.json")
        assert watcher.reload_if_changed() is None

    def test_deleted_file_keeps_last_good_config(self, tmp_path):
        path = write(tmp_path / "config.json", {"default_refresh_rate": 120})
        watcher = ConfigWatcher(path)
        good = watcher.reload_if_changed()
        path.unlink()
        assert watcher.reload_if_changed() is good


class TestDefaultConfigCreation:
    """Elso inditas: az exe ne "csinaljon semmit" neman, ha nincs config."""

    def test_creates_a_valid_default_when_missing(self, tmp_path):
        from refreshswitcher.config import write_default_config

        path = tmp_path / "config.json"
        assert write_default_config(path) is True
        assert path.exists()
        Config.load(path)  # ervenyesnek kell lennie

    def test_never_overwrites_an_existing_file(self, tmp_path):
        from refreshswitcher.config import write_default_config

        path = write(tmp_path / "config.json", {"default_refresh_rate": 165})
        assert write_default_config(path) is False
        assert Config.load(path).default_refresh_rate == 165

    def test_leaves_no_temporary_file_behind(self, tmp_path):
        from refreshswitcher.config import write_default_config

        write_default_config(tmp_path / "config.json")
        assert [p.name for p in tmp_path.iterdir()] == ["config.json"]

    def test_unwritable_location_is_not_fatal(self, tmp_path, monkeypatch):
        from refreshswitcher.config import write_default_config

        target = tmp_path / "config.json"
        monkeypatch.setattr(Path, "write_text", lambda *a, **k: (_ for _ in ()).throw(PermissionError()))
        assert write_default_config(target) is False
