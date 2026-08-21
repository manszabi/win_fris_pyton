"""Parancssori felulet: ``refreshswitcher <parancs>``."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from . import __version__
from .config import Config, ConfigError, ConfigWatcher, write_default_config
from .logging_setup import setup_logging
from .paths import config_path
from .single_instance import SingleInstance

if TYPE_CHECKING:
    from .scheduler import CommandResult

logger = logging.getLogger(__name__)

_ALREADY_RUNNING_MESSAGE = (
    "A RefreshSwitcher mar fut ebben a munkamenetben.\n"
    "Lepj ki a tray ikon menujebol, vagy futtasd: refreshswitcher stop"
)


def _load_config(path: Path) -> Config | None:
    try:
        return Config.load(path)
    except ConfigError as exc:
        print(f"HIBA: {exc}", file=sys.stderr)
        return None


# -- parancsok --------------------------------------------------------------


def cmd_tray(args: argparse.Namespace) -> int:
    from .tray import run_tray

    config_file = args.config or config_path()
    write_default_config(config_file)
    config = _load_config(config_file)
    setup_logging(config.log_level if config else logging.WARNING, console=args.verbose)

    # Hibas config eseten is elindulunk: a tray ikon pirosra valt, es a
    # menubol megnyithato a config es a naplo. Grafikus programnal ez sokkal
    # hasznalhatobb, mint a nema kilepes egy lathatatlan hibauzenettel.
    if config is None:
        logger.error("A konfiguracio ervenytelen; a tray hibajelzessel indul.")

    with SingleInstance() as guard:
        if not guard.acquired:
            logger.warning("Mar fut egy peldany, ez a folyamat kilep.")
            print(_ALREADY_RUNNING_MESSAGE, file=sys.stderr)
            return 3
        return run_tray(config_file)


def cmd_run(args: argparse.Namespace) -> int:
    """Tray nelkuli, konzolos futtatas - hibakeresehez."""
    from .switcher import RefreshSwitcher

    config_file = args.config or config_path()
    config = _load_config(config_file)
    setup_logging(logging.DEBUG if args.verbose else (config.log_level if config else "INFO"), console=True)
    if config is None:
        return 2

    with SingleInstance() as guard:
        if not guard.acquired:
            print(_ALREADY_RUNNING_MESSAGE, file=sys.stderr)
            return 3

        switcher = RefreshSwitcher(ConfigWatcher(config_file, fallback=config))
        print(f"Figyeles indul. Config: {config_file}  (Ctrl+C a kilepeshez)")
        try:
            switcher.run()
        except KeyboardInterrupt:
            print("\nKilepes...")
            switcher.stop()
        return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Kiirja a monitorokat, a tamogatott frekvenciakat es az aktualis beallitast."""
    from .display import current_mode, enumerate_monitors, resolve_monitor, supported_refresh_rates

    setup_logging(logging.DEBUG if args.verbose else logging.WARNING, console=True)
    config_file = args.config or config_path()
    config = _load_config(config_file)

    print(f"RefreshSwitcher {__version__}")
    print(f"Konfiguracio: {config_file}")
    print()

    monitors = enumerate_monitors()
    if not monitors:
        print("Nem talalhato az asztalhoz csatolt monitor.")
        return 1

    selected = resolve_monitor(config.monitor) if config else None
    print(f"Monitorok ({len(monitors)} db):")
    for monitor in monitors:
        try:
            mode = current_mode(monitor.device_name)
            rates = supported_refresh_rates(monitor.device_name)
            detail = (
                f"{mode.width}x{mode.height} @ {mode.frequency} Hz  "
                f"| tamogatott: {', '.join(str(r) for r in rates)}"
            )
        except Exception as exc:  # noqa: BLE001
            detail = f"nem lekerdezheto ({exc})"
        marker = "  <-- kivalasztva" if selected and selected.index == monitor.index else ""
        print(f"  {monitor}{marker}")
        print(f"      {detail}")

    if config is None:
        return 2

    print()
    print(f"Alapertelmezett frekvencia: {config.default_refresh_rate} Hz")
    print(f"Ellenorzesi gyakorisag:     {config.check_interval} s")
    print(f"Alapertelmezett kenyszerites: {'igen' if config.enforce_default else 'nem'}")
    print(f"Visszaallitas kilepeskor:     {'igen' if config.restore_on_exit else 'nem'}")
    print(f"Jatekok ({len(config.games)} db):")
    for name, rate in sorted(config.games.items()):
        print(f"  {name:<32} -> {rate} Hz")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """Csak a config.json ervenyesseget ellenorzi (nem igenyel Windowst)."""
    config_file = args.config or config_path()
    config = _load_config(config_file)
    if config is None:
        return 2
    print(f"A konfiguracio ervenyes: {config_file}")
    print(
        f"  monitor={config.monitor!r}, default={config.default_refresh_rate} Hz, "
        f"interval={config.check_interval}s, {len(config.games)} jatek"
    )
    return 0


def _report(result: CommandResult, success: str) -> int:
    """Egysegesen kiirja egy schtasks/powershell muvelet eredmenyet."""
    if result.ok:
        print(success)
        if result.stdout.strip():
            print(result.stdout.strip())
        return 0
    print(f"HIBA: {result.message}", file=sys.stderr)
    if result.access_denied:
        print(
            "Ehhez a muvelethez rendszergazdai parancssor szukseges "
            "(jobb klikk -> 'Futtatas rendszergazdakent').",
            file=sys.stderr,
        )
    return 1


def cmd_install(args: argparse.Namespace) -> int:
    from . import scheduler

    setup_logging(logging.INFO, console=True)
    result = scheduler.install(elevated=args.elevated)
    code = _report(result, f"A(z) '{scheduler.TASK_NAME}' feladat letrehozva.")
    if code != 0:
        return code
    print("A program minden bejelentkezeskor automatikusan elindul.")
    print()
    return _report(scheduler.start(), "Azonnali inditas kesz.")


def cmd_remove(_args: argparse.Namespace) -> int:
    from . import scheduler

    setup_logging(logging.INFO, console=True)
    return _report(scheduler.remove(), f"A(z) '{scheduler.TASK_NAME}' feladat torolve.")


def cmd_start(_args: argparse.Namespace) -> int:
    from . import scheduler

    setup_logging(logging.INFO, console=True)
    return _report(scheduler.start(), "Elinditva.")


def cmd_stop(_args: argparse.Namespace) -> int:
    from . import scheduler

    setup_logging(logging.INFO, console=True)
    return _report(scheduler.stop(), "Leallitva.")


def cmd_task_status(_args: argparse.Namespace) -> int:
    from . import scheduler

    result = scheduler.query()
    if not result.ok:
        print(f"A(z) '{scheduler.TASK_NAME}' feladat nincs telepitve.")
        return 1
    print(result.stdout.strip())
    return 0


# -- argumentum-feldolgozas -------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="refreshswitcher",
        description="Automatikus kijelzo-frissitesifrekvencia valtas jatekokhoz (Windows 11).",
    )
    parser.add_argument("--version", action="version", version=f"RefreshSwitcher {__version__}")
    parser.add_argument("-c", "--config", type=Path, default=None, help="A config.json utvonala.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Reszletes naplozas a konzolra.")

    sub = parser.add_subparsers(dest="command")
    sub.add_parser("tray", help="Tray ikon inditasa (alapertelmezett).").set_defaults(func=cmd_tray)
    sub.add_parser("run", help="Futtatas konzolon, tray nelkul.").set_defaults(func=cmd_run)
    sub.add_parser("status", help="Monitorok es beallitasok kiirasa.").set_defaults(func=cmd_status)
    sub.add_parser("check", help="A config.json ervenyessegenek ellenorzese.").set_defaults(func=cmd_check)

    install_parser = sub.add_parser("install", help="Automatikus inditas bekapcsolasa.")
    install_parser.add_argument(
        "--elevated",
        action="store_true",
        help="A feladat emelt jogosultsaggal fusson (rendszergazdai parancssor kell hozza).",
    )
    install_parser.set_defaults(func=cmd_install)

    sub.add_parser("remove", help="Automatikus inditas kikapcsolasa.").set_defaults(func=cmd_remove)
    sub.add_parser("start", help="A hattermuvelet inditasa.").set_defaults(func=cmd_start)
    sub.add_parser("stop", help="A futo peldanyok leallitasa.").set_defaults(func=cmd_stop)
    sub.add_parser("task-status", help="A utemezett feladat allapota.").set_defaults(func=cmd_task_status)

    parser.set_defaults(func=cmd_tray)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:  # pragma: no cover
        return 130


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
