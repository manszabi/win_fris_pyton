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


def get_current_refresh_rate():
    dm = win32api.EnumDisplaySettings(None, win32con.ENUM_CURRENT_SETTINGS)
    return dm.DisplayFrequency


def get_supported_refresh_rates():
    rates = set()
    i = 0
    while True:
        try:
            dm = win32api.EnumDisplaySettings(None, i)
            rates.add(dm.DisplayFrequency)
            i += 1
        except Exception:
            break
    return sorted(rates)


def set_refresh_rate(hz):
    current = get_current_refresh_rate()
    if current == hz:
        return True

    dm = win32api.EnumDisplaySettings(None, win32con.ENUM_CURRENT_SETTINGS)
    dm.DisplayFrequency = hz
    dm.Fields = (
        win32con.DM_PELSWIDTH
        | win32con.DM_PELSHEIGHT
        | win32con.DM_BITSPERPEL
        | win32con.DM_DISPLAYFREQUENCY
    )

    result = win32api.ChangeDisplaySettings(dm, 0)
    if result == win32con.DISP_CHANGE_SUCCESSFUL:
        logger.info("Frissitesi frekvencia beallitva: %d Hz", hz)
        return True
    else:
        logger.error("Nem sikerult beallitani a frekvenciat: %d Hz (hibakod: %d)", hz, result)
        return False


def is_any_game_running(games):
    game_names = {g.lower() for g in games}
    for proc in psutil.process_iter(["name"]):
        try:
            if proc.info["name"] and proc.info["name"].lower() in game_names:
                return proc.info["name"]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


def monitor_loop(stop_event=None):
    config = load_config()
    default_rate = config["default_refresh_rate"]
    game_rate = config["game_refresh_rate"]
    games = config["games"]
    interval = config.get("check_interval", 5)

    supported = get_supported_refresh_rates()
    logger.info("Tamogatott frissitesi frekvenciak: %s", supported)
    logger.info("Alapertelmezett: %d Hz, Jatekhoz: %d Hz", default_rate, game_rate)
    logger.info("Figyelt jatekok: %s", games)

    if game_rate not in supported:
        logger.warning("A %d Hz nem tamogatott frekvencia! Tamogatott: %s", game_rate, supported)

    game_was_running = False

    while True:
        if stop_event and stop_event.is_set():
            break

        try:
            # Ujratoltjuk a configot minden ciklusban, igy menet kozben is modosithato
            config = load_config()
            default_rate = config["default_refresh_rate"]
            game_rate = config["game_refresh_rate"]
            games = config["games"]

            running_game = is_any_game_running(games)

            if running_game and not game_was_running:
                logger.info("Jatek elinditva: %s -> valtas %d Hz-re", running_game, game_rate)
                set_refresh_rate(game_rate)
                game_was_running = True
            elif not running_game and game_was_running:
                logger.info("Jatek befejezve -> visszaallas %d Hz-re", default_rate)
                set_refresh_rate(default_rate)
                game_was_running = False

        except Exception as e:
            logger.error("Hiba a monitorozas soran: %s", e)

        time.sleep(interval)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    print("Display Refresh Rate Switcher")
    print(f"Jelenlegi frekvencia: {get_current_refresh_rate()} Hz")
    print(f"Tamogatott frekvenciak: {get_supported_refresh_rates()}")
    print("Monitorozas indul... (Ctrl+C a kilepeshez)")

    try:
        monitor_loop()
    except KeyboardInterrupt:
        print("\nKilepes.")
