"""Task Scheduler parancsok osszeallitasa es kimenet-dekodolas."""

from __future__ import annotations

import subprocess

import pytest

from refreshswitcher import scheduler


@pytest.fixture
def captured(monkeypatch):
    calls: list[list[str]] = []

    def _fake_run(command, **kwargs):
        calls.append(command)
        return scheduler.CommandResult(0, "ok", "")

    monkeypatch.setattr(scheduler, "_run", _fake_run)
    return calls


def test_install_builds_an_onlogon_task(captured):
    scheduler.install()
    command = captured[0]
    assert command[:2] == ["schtasks", "/create"]
    assert "/f" in command and "/it" in command
    assert command[command.index("/sc") + 1] == "onlogon"
    assert command[command.index("/tn") + 1] == scheduler.TASK_NAME
    assert "/rl" not in command, "alapertelmezetten ne igenyeljen rendszergazdai jogot"


def test_install_elevated_adds_highest_run_level(captured):
    scheduler.install(elevated=True)
    command = captured[0]
    assert command[command.index("/rl") + 1] == "highest"
    assert command[-1] == "/f"


def test_remove_stops_before_deleting(captured):
    scheduler.remove()
    assert captured[0][0] == "powershell"
    assert captured[1][:2] == ["schtasks", "/delete"]


def test_stop_uses_cim_not_get_process():
    """A ``Get-Process`` objektumnak nincs CommandLine mezoje -- ez volt a regi hiba."""
    script = scheduler._stop_powershell_script()
    assert "Get-CimInstance Win32_Process" in script
    assert "Get-Process" not in script
    assert "CommandLine" in script


def test_stop_never_kills_its_own_process():
    import os

    assert f"$_.ProcessId -ne {os.getpid()}" in scheduler._stop_powershell_script()


def test_launch_target_uses_pythonw_when_available(monkeypatch, tmp_path):
    interpreter = tmp_path / "python.exe"
    interpreter.touch()
    (tmp_path / "pythonw.exe").touch()
    monkeypatch.setattr(scheduler.sys, "executable", str(interpreter))
    monkeypatch.setattr(scheduler.sys, "frozen", False, raising=False)

    exe, script = scheduler.launch_target()
    assert exe.endswith("pythonw.exe"), "konzolablak nelkul kell indulnia"
    assert script is not None and script.endswith("tray.py")


def test_launch_target_falls_back_when_pythonw_is_missing(monkeypatch, tmp_path):
    interpreter = tmp_path / "python.exe"
    interpreter.touch()
    monkeypatch.setattr(scheduler.sys, "executable", str(interpreter))
    exe, _ = scheduler.launch_target()
    assert exe == str(interpreter)


def test_launch_target_for_frozen_exe(monkeypatch, tmp_path):
    exe_path = tmp_path / "RefreshSwitcher.exe"
    exe_path.touch()
    monkeypatch.setattr(scheduler.sys, "frozen", True, raising=False)
    monkeypatch.setattr(scheduler.sys, "executable", str(exe_path))

    exe, script = scheduler.launch_target()
    assert script is None, "az exe onmagat inditja, nem a forraskodot"
    assert exe == str(exe_path)


def test_task_command_is_quoted_for_paths_with_spaces(monkeypatch, tmp_path):
    exe_path = tmp_path / "Program Files" / "RefreshSwitcher.exe"
    exe_path.parent.mkdir()
    exe_path.touch()
    monkeypatch.setattr(scheduler.sys, "frozen", True, raising=False)
    monkeypatch.setattr(scheduler.sys, "executable", str(exe_path))
    assert scheduler._task_command() == f'"{exe_path}"'


def test_decode_handles_non_utf8_console_output():
    """Magyar Windows OEM (852) kimenete nem dobhat UnicodeDecodeError-t."""
    assert scheduler._decode("SIKERES".encode("cp852")) == "SIKERES"
    assert isinstance(scheduler._decode(b"\xff\xfe\x00 invalid"), str)


def test_missing_executable_is_reported_not_raised(monkeypatch):
    monkeypatch.setattr(
        scheduler.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError())
    )
    result = scheduler._run(["nincs-ilyen-parancs"])
    assert not result.ok
    assert "nem talalhato" in result.message


def test_timeout_is_reported_not_raised(monkeypatch):
    def _timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="schtasks", timeout=1)

    monkeypatch.setattr(scheduler.subprocess, "run", _timeout)
    result = scheduler._run(["schtasks"])
    assert not result.ok and "idotullepes" in result.message


def test_access_denied_is_detected():
    result = scheduler.CommandResult(1, "", "ERROR: Access is denied.")
    assert result.access_denied
    assert not scheduler.CommandResult(1, "", "ERROR: egyeb").access_denied
