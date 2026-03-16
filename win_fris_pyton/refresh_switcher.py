import json
import logging
import os
import time

import psutil
import win32api
import win32con

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

logger = logging.getLogger("RefreshSwitcher")


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_monitors():
    """Visszaadja az osszes aktiv monitor nevet (pl. '\\\\.\\DISPLAY1')."""
    monitors = []
    i = 0
    while True:
        try:
            device = win32api.EnumDisplayDevices(None, i)
            if device.StateFlags & win32con.DISPLAY_DEVICE_ATTACHED_TO_DESKTOP:
                monitors.append(device.DeviceName)
            i += 1
        except Exception:
            break
    return monitors


def get_monitor_device(monitor_number):
    """Visszaadja a megadott szamu monitor device nevet (1-tol szamozva)."""
    monitors = get_monitors()
    if monitor_number < 1 or monitor_number > len(monitors):
        logger.error(
            "Monitor %d nem letezik! Elerheto monitorok: %d db (%s)",
            monitor_number, len(monitors), monitors,
        )
        return None
    return monitors[monitor_number - 1]


def get_current_refresh_rate(device=None):
    dm = win32api.EnumDisplaySettings(device, win32con.ENUM_CURRENT_SETTINGS)
    return dm.DisplayFrequency


def get_supported_refresh_rates(device=None):
    """Visszaadja a tamogatott frekvenciakat az aktualis felbontashoz."""
    current = win32api.EnumDisplaySettings(device, win32con.ENUM_CURRENT_SETTINGS)
    rates = set()
    i = 0
    while True:
        try:
            dm = win32api.EnumDisplaySettings(device, i)
            if dm.PelsWidth == current.PelsWidth and dm.PelsHeight == current.PelsHeight:
                rates.add(dm.DisplayFrequency)
            i += 1
        except Exception:
            break
    return sorted(rates)


def set_refresh_rate(hz, device=None):
    current = get_current_refresh_rate(device)
    if current == hz:
        return True

    supported = get_supported_refresh_rates(device)
    if hz not in supported:
        logger.warning(
            "A %d Hz nem tamogatott ezen a monitoron (%s). Tamogatott: %s",
            hz, device or "primary", supported,
        )
        return False

    dm = win32api.EnumDisplaySettings(device, win32con.ENUM_CURRENT_SETTINGS)
    dm.DisplayFrequency = hz
    dm.Fields = (
        win32con.DM_PELSWIDTH
        | win32con.DM_PELSHEIGHT
        | win32con.DM_BITSPERPEL
        | win32con.DM_DISPLAYFREQUENCY
    )

    result = win32api.ChangeDisplaySettingsEx(device, dm, 0)
    if result == win32con.DISP_CHANGE_SUCCESSFUL:
        logger.info("Frissitesi frekvencia beallitva: %d Hz (%s)", hz, device or "primary")
        return True
    else:
        logger.error(
            "Nem sikerult beallitani a frekvenciat: %d Hz (%s, hibakod: %d)",
            hz, device or "primary", result,
        )
        return False


def find_running_game(games):
    """Megkeresi a futo jatekot es visszaadja (nev, hz) parost, vagy None-t."""
    game_map = {name.lower(): hz for name, hz in games.items()}
    for proc in psutil.process_iter(["name"]):
        try:
            name = proc.info["name"]
            if name and name.lower() in game_map:
                return name, game_map[name.lower()]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


def monitor_loop(stop_event=None, on_state_change=None):
    config = load_config()
    monitor_number = config.get("monitor", 1)
    default_rate = config["default_refresh_rate"]
    games = config["games"]
    interval = config.get("check_interval", 5)

    # Osszes monitor kilistazasa
    all_monitors = get_monitors()
    for idx, mon in enumerate(all_monitors, 1):
        current = get_current_refresh_rate(mon)
        supported = get_supported_refresh_rates(mon)
        marker = " <-- kivalasztva" if idx == monitor_number else ""
        logger.info("Monitor %d: %s - %d Hz, tamogatott: %s%s", idx, mon, current, supported, marker)

    device = get_monitor_device(monitor_number)
    if device is None:
        logger.error("Kilpes: ervenytelen monitor szam.")
        return

    logger.info("Kivalasztott monitor: %d (%s)", monitor_number, device)
    logger.info("Alapertelmezett: %d Hz", default_rate)
    for game_name, game_hz in games.items():
        logger.info("  %s -> %d Hz", game_name, game_hz)

    if on_state_change:
        on_state_change(default_rate, None)

    game_was_running = False

    while True:
        if stop_event and stop_event.is_set():
            break

        try:
            config = load_config()
            monitor_number = config.get("monitor", 1)
            default_rate = config["default_refresh_rate"]
            games = config["games"]

            device = get_monitor_device(monitor_number)
            if device is None:
                time.sleep(interval)
                continue

            result = find_running_game(games)

            if result and not game_was_running:
                game_name, game_hz = result
                logger.info("Jatek elinditva: %s -> valtas %d Hz-re (monitor %d)", game_name, game_hz, monitor_number)
                set_refresh_rate(game_hz, device)
                game_was_running = True
                if on_state_change:
                    on_state_change(game_hz, game_name)
            elif not result and game_was_running:
                logger.info("Jatek befejezve -> visszaallas %d Hz-re (monitor %d)", default_rate, monitor_number)
                set_refresh_rate(default_rate, device)
                game_was_running = False
                if on_state_change:
                    on_state_change(default_rate, None)
            elif result and game_was_running:
                game_name, game_hz = result
                current = get_current_refresh_rate(device)
                if current != game_hz:
                    logger.info("Jatek valtas: %s -> valtas %d Hz-re (monitor %d)", game_name, game_hz, monitor_number)
                    set_refresh_rate(game_hz, device)
                    if on_state_change:
                        on_state_change(game_hz, game_name)

        except Exception as e:
            logger.error("Hiba a monitorozas soran: %s", e)

        time.sleep(interval)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    config = load_config()
    monitor_number = config.get("monitor", 1)
    monitors = get_monitors()

    print("Display Refresh Rate Switcher")
    print(f"Talalt monitorok: {len(monitors)}")
    for idx, mon in enumerate(monitors, 1):
        rate = get_current_refresh_rate(mon)
        supported = get_supported_refresh_rates(mon)
        marker = " <-- kivalasztva" if idx == monitor_number else ""
        print(f"  Monitor {idx} ({mon}): {rate} Hz (tamogatott: {supported}){marker}")
    print(f"\nAlapertelmezett: {config['default_refresh_rate']} Hz")
    print("Jatekok:")
    for game_name, game_hz in config["games"].items():
        print(f"  {game_name} -> {game_hz} Hz")
    print("\nMonitorozas indul... (Ctrl+C a kilepeshez)")

    try:
        monitor_loop()
    except KeyboardInterrupt:
        print("\nKilepes.")
