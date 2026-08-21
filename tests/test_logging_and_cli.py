"""Naplozas, egypeldany-vedelem, utvonalak es CLI."""

from __future__ import annotations

import json
import logging
import threading

import pytest


@pytest.fixture(autouse=True)
def isolated_logging(tmp_path, monkeypatch):
    """Minden teszt sajat log fajlt es friss modul-allapotot kap."""
    import importlib

    from refreshswitcher import logging_setup

    monkeypatch.setenv("REFRESHSWITCHER_LOG", str(tmp_path / "log" / "app.log"))
    module = importlib.reload(logging_setup)
    yield module
    logger = logging.getLogger("refreshswitcher")
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


def test_log_file_is_created_and_written(isolated_logging, tmp_path):
    path = isolated_logging.setup_logging(logging.INFO)
    assert path == tmp_path / "log" / "app.log"

    logging.getLogger("refreshswitcher.test").info("proba uzenet")
    for handler in logging.getLogger("refreshswitcher").handlers:
        handler.flush()
    assert "proba uzenet" in path.read_text(encoding="utf-8")


def test_logger_does_not_propagate_to_root(isolated_logging):
    isolated_logging.setup_logging(logging.INFO)
    assert logging.getLogger("refreshswitcher").propagate is False


def test_falls_back_to_user_dir_when_app_dir_is_unwritable(isolated_logging, tmp_path, monkeypatch):
    """C:\\Program Files alol futva sem szabad elszallnia az indulasnak."""
    unwritable = tmp_path / "readonly" / "app.log"
    monkeypatch.setenv("REFRESHSWITCHER_LOG", str(unwritable))
    fallback = tmp_path / "userdata"
    monkeypatch.setattr(isolated_logging, "user_data_dir", lambda: fallback)

    real_handler = isolated_logging._build_file_handler

    def _fail_for_app_dir(path):
        if path == unwritable:
            return None
        return real_handler(path)

    monkeypatch.setattr(isolated_logging, "_build_file_handler", _fail_for_app_dir)
    assert isolated_logging.setup_logging(logging.INFO) == fallback / isolated_logging.LOG_FILENAME


def test_setup_is_idempotent(isolated_logging):
    isolated_logging.setup_logging(logging.INFO)
    count = len(logging.getLogger("refreshswitcher").handlers)
    isolated_logging.setup_logging(logging.DEBUG)
    assert len(logging.getLogger("refreshswitcher").handlers) == count


def test_no_stream_handler_without_stderr(isolated_logging, monkeypatch):
    """pythonw.exe alatt a sys.stderr None -- nem szabad StreamHandlert felvenni."""
    monkeypatch.setattr(isolated_logging.sys, "stderr", None)
    isolated_logging.setup_logging(logging.INFO, console=True)
    handlers = logging.getLogger("refreshswitcher").handlers
    assert not any(type(h) is logging.StreamHandler for h in handlers)


def test_worker_thread_crash_is_logged(isolated_logging, tmp_path):
    """Kezeletlen szal-kivetel nem tunhet el nyomtalanul."""
    path = isolated_logging.setup_logging(logging.INFO)

    def _boom():
        raise ValueError("szal-hiba")

    thread = threading.Thread(target=_boom)
    thread.start()
    thread.join()
    for handler in logging.getLogger("refreshswitcher").handlers:
        handler.flush()

    content = path.read_text(encoding="utf-8")
    assert "szal-hiba" in content and "Kezeletlen kivetel" in content


def test_single_instance_is_reentrant_off_windows():
    from refreshswitcher.single_instance import SingleInstance

    with SingleInstance() as guard:
        assert guard.acquired


def test_config_path_env_override(tmp_path, monkeypatch):
    from refreshswitcher.paths import config_path

    target = tmp_path / "sajat.json"
    monkeypatch.setenv("REFRESHSWITCHER_CONFIG", str(target))
    assert config_path() == target


def test_frozen_app_dir_is_next_to_the_exe(tmp_path, monkeypatch):
    """A felhasznalo az exe mellett szerkeszti a configot -- oda kell nezni."""
    from refreshswitcher import paths

    exe = tmp_path / "dist" / "RefreshSwitcher.exe"
    exe.parent.mkdir()
    exe.touch()
    monkeypatch.setattr(paths.sys, "frozen", True, raising=False)
    monkeypatch.setattr(paths.sys, "executable", str(exe))
    assert paths.app_dir() == exe.parent


class TestCli:
    def test_check_accepts_a_valid_config(self, tmp_path, capsys):
        from refreshswitcher.cli import main

        path = tmp_path / "config.json"
        path.write_text(json.dumps({"default_refresh_rate": 144, "games": {"cs2": 240}}), encoding="utf-8")
        assert main(["--config", str(path), "check"]) == 0
        assert "ervenyes" in capsys.readouterr().out

    def test_check_rejects_an_invalid_config(self, tmp_path, capsys):
        from refreshswitcher.cli import main

        path = tmp_path / "config.json"
        path.write_text('{"default_refresh_rate": 5}', encoding="utf-8")
        assert main(["--config", str(path), "check"]) == 2
        assert "HIBA" in capsys.readouterr().err

    def test_check_reports_a_missing_config(self, tmp_path):
        from refreshswitcher.cli import main

        assert main(["--config", str(tmp_path / "nincs.json"), "check"]) == 2

    def test_version_flag(self, capsys):
        from refreshswitcher.cli import main

        with pytest.raises(SystemExit) as exc:
            main(["--version"])
        assert exc.value.code == 0
        assert "RefreshSwitcher" in capsys.readouterr().out

    def test_every_subcommand_is_wired_up(self):
        from refreshswitcher.cli import build_parser

        parser = build_parser()
        for command in ("tray", "run", "status", "check", "install", "remove", "start", "stop"):
            assert hasattr(parser.parse_args([command]), "func")

    def test_no_command_defaults_to_tray(self):
        from refreshswitcher.cli import build_parser, cmd_tray

        assert build_parser().parse_args([]).func is cmd_tray


class TestCompatibilityShims:
    """A regi inditoszkriptek tovabbra is mukodjenek, es *irjanak is ki* valamit.

    Ezek a tesztek azert vannak, mert egy `ruff --fix --unsafe-fixes` futas
    korabban csendben eltavolitotta az `install_task.py` hasznalati uzenetet:
    a szkript szo nelkul lepett ki 1-es koddal.
    """

    @staticmethod
    def _load(name: str):
        import importlib.util
        import sys
        from pathlib import Path

        path = Path(__file__).resolve().parent.parent / name
        assert path.is_file(), f"hianyzo inditoszkript: {path}"
        spec = importlib.util.spec_from_file_location(f"_shim_{name.replace('.', '_')}", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    def test_install_task_prints_usage_without_arguments(self, capsys):
        module = self._load("install_task.py")
        assert module.run([]) == 1
        assert "Hasznalat" in capsys.readouterr().err

    def test_install_task_prints_usage_for_an_unknown_command(self, capsys):
        module = self._load("install_task.py")
        assert module.run(["nincs-ilyen"]) == 1
        assert "install" in capsys.readouterr().err

    def test_install_task_forwards_known_commands(self, monkeypatch):
        module = self._load("install_task.py")
        seen: list[list[str]] = []
        monkeypatch.setattr(module, "main", lambda argv: seen.append(argv) or 0)
        assert module.run(["INSTALL"]) == 0
        assert seen == [["install"]]

    def test_every_shim_exposes_the_cli_entry_point(self):
        for name in ("tray.py", "install_task.py", "refresh_switcher.py"):
            assert callable(self._load(name).main), name
