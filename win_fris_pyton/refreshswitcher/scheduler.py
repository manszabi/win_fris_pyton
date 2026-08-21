"""Windows Task Scheduler integracio (automatikus inditas bejelentkezeskor).

Javitott hibak a korabbi ``install_task.py``-hoz kepest:

* A ``stop`` parancs **nem mukodott**: a ``Get-Process`` altal visszaadott
  objektumnak nincs ``CommandLine`` tulajdonsaga a Windows PowerShell 5.1-ben,
  igy a szuro soha nem talalt semmit -- a parancs "Leallitva" uzenettel tert
  vissza, kozben a program tovabb futott. Helyette CIM (``Win32_Process``)
  lekerdezes megy, aminek *van* ``CommandLine`` mezoje.
* A ``schtasks`` kimenete **nem UTF-8**: magyar Windowson OEM kodlapot (852)
  hasznal, es a ``text=True`` dekodolas ``UnicodeDecodeError``-t dobhatott.
* A ``python.exe`` -> ``pythonw.exe`` csere naiv sztringcsere volt; ha az
  utvonalban barhol szerepelt a "python.exe" reszlet, elromlott.
* PyInstaller-rel keszult exe eseten a regi valtozat a *forraskodot* probalta
  volna inditani, ami az exe mellett nem letezik.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .paths import app_dir

logger = logging.getLogger(__name__)

TASK_NAME = "DisplayRefreshRateSwitcher"
#: A schtasks /tr parametere legfeljebb ennyi karakter lehet.
_MAX_TR_LENGTH = 261

_ACCESS_DENIED_HINTS = ("access is denied", "hozzaferes megtagadva", "hozzáférés megtagadva")


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Egy lefuttatott kulso parancs eredmenye."""

    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    @property
    def message(self) -> str:
        return (self.stderr.strip() or self.stdout.strip()) or f"hibakod: {self.returncode}"

    @property
    def access_denied(self) -> bool:
        blob = f"{self.stdout}\n{self.stderr}".lower()
        return any(hint in blob for hint in _ACCESS_DENIED_HINTS)


def _decode(raw: bytes) -> str:
    """Konzolos kimenet dekodolasa: OEM kodlap -> ANSI -> UTF-8, veszteseg nelkul."""
    for encoding in ("oem", "mbcs", "utf-8"):
        try:
            return raw.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", errors="replace")


def _run(command: list[str], *, timeout: float = 60.0) -> CommandResult:
    """Kulso parancs futtatasa konzolablak es kodolasi hiba nelkul."""
    creationflags = 0
    if sys.platform == "win32":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = subprocess.run(  # noqa: S603 - fix, nem felhasznaloi parancs
            command,
            capture_output=True,
            timeout=timeout,
            check=False,
            creationflags=creationflags,
        )
    except FileNotFoundError:
        return CommandResult(127, "", f"A(z) {command[0]!r} parancs nem talalhato.")
    except subprocess.TimeoutExpired:
        return CommandResult(124, "", f"A(z) {command[0]!r} parancs idotullepes miatt megszakadt.")
    return CommandResult(completed.returncode, _decode(completed.stdout), _decode(completed.stderr))


def launch_target() -> tuple[str, str | None]:
    """A bejelentkezeskor inditando program: ``(exe, script vagy None)``.

    Frozen (PyInstaller) modban maga az exe indul. Fejlesztoi modban a
    ``pythonw.exe`` a ``tray.py`` inditoval -- konzolablak nelkul.
    """
    if getattr(sys, "frozen", False):
        return str(Path(sys.executable).resolve()), None

    interpreter = Path(sys.executable).resolve()
    # Csak a fajlnevet csereljuk, nem az egesz utvonalban keresunk.
    pythonw = interpreter.with_name(interpreter.name.replace("python", "pythonw", 1))
    if not pythonw.is_file():
        pythonw = interpreter
    return str(pythonw), str(app_dir() / "tray.py")


def _task_command() -> str:
    exe, script = launch_target()
    command = f'"{exe}"' if script is None else f'"{exe}" "{script}"'
    if len(command) > _MAX_TR_LENGTH:
        logger.warning(
            "A parancs hossza (%d) meghaladja a schtasks %d karakteres korlatjat; "
            "helyezd a programot rovidebb utvonalra.",
            len(command),
            _MAX_TR_LENGTH,
        )
    return command


def install(*, elevated: bool = False) -> CommandResult:
    """Letrehozza (vagy felulirja) a bejelentkezeskori inditasi feladatot."""
    command = [
        "schtasks",
        "/create",
        "/tn",
        TASK_NAME,
        "/tr",
        _task_command(),
        "/sc",
        "onlogon",
        "/it",  # interaktiv token -> a tray ikon lathato a felhasznaloi munkamenetben
        "/f",
    ]
    if elevated:
        # Csak akkor kell, ha a program adminkent futo jatekokat is figyelni akar.
        command[-1:-1] = ["/rl", "highest"]
    return _run(command)


def remove() -> CommandResult:
    """Torli a feladatot (elotte leallitja a futo peldanyt)."""
    stop()
    return _run(["schtasks", "/delete", "/tn", TASK_NAME, "/f"])


def start() -> CommandResult:
    """Azonnal elinditja a feladatot."""
    return _run(["schtasks", "/run", "/tn", TASK_NAME])


def query() -> CommandResult:
    """Lekerdezi a feladat allapotat."""
    return _run(["schtasks", "/query", "/tn", TASK_NAME, "/v", "/fo", "list"])


def is_installed() -> bool:
    return query().ok


def _stop_powershell_script() -> str:
    """A futo peldanyokat leallito PowerShell script.

    ``Win32_Process`` (CIM) hasznalata, mert a ``Get-Process`` altal visszaadott
    ``System.Diagnostics.Process`` objektumnak nincs ``CommandLine`` mezoje --
    ez volt a regi ``stop`` parancs nema (csendes) hibaja.
    """
    own_pid = os.getpid()
    return (
        "$ErrorActionPreference = 'SilentlyContinue';"
        "$targets = Get-CimInstance Win32_Process | Where-Object {"
        "  ($_.Name -eq 'RefreshSwitcher.exe') -or"
        "  ($_.Name -in @('python.exe','pythonw.exe') -and"
        "   $_.CommandLine -match '(tray\\.py|refreshswitcher)')"
        f"}} | Where-Object {{ $_.ProcessId -ne {own_pid} }};"
        "if ($targets) {"
        "  $targets | ForEach-Object { Stop-Process -Id $_.ProcessId -Force };"
        "  Write-Output ('Leallitva: ' + $targets.Count + ' folyamat.')"
        "} else { Write-Output 'Nem futott peldany.' }"
    )


def stop() -> CommandResult:
    """Leallitja a futo tray peldanyokat (a hivo folyamatot kihagyva)."""
    return _run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            _stop_powershell_script(),
        ],
        timeout=90.0,
    )
