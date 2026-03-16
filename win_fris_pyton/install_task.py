"""Letrehoz egy Windows Task Scheduler feladatot, ami bejelentkezeskor
automatikusan elinditja a refresh_switcher.py-t a felhasznaloi session-ben.

Futtatas: python install_task.py install   (admin parancssorbol)
          python install_task.py remove
"""

import os
import subprocess
import sys

TASK_NAME = "DisplayRefreshRateSwitcher"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_PATH = os.path.join(SCRIPT_DIR, "tray.py")
PYTHON_EXE = sys.executable
LOG_PATH = os.path.join(SCRIPT_DIR, "service.log")


def install():
    # pythonw.exe-t hasznaljuk, hogy ne nyisson konzol ablakot
    pythonw = PYTHON_EXE.replace("python.exe", "pythonw.exe")
    if not os.path.exists(pythonw):
        pythonw = PYTHON_EXE

    cmd = [
        "schtasks", "/create",
        "/tn", TASK_NAME,
        "/tr", f'"{pythonw}" "{SCRIPT_PATH}"',
        "/sc", "onlogon",
        "/rl", "highest",
        "/f",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"Feladat '{TASK_NAME}' sikeresen letrehozva.")
        print("A program automatikusan elindul bejelentkezeskor.")
        print()
        print("Azonnali inditas:")
        start()
    else:
        print(f"Hiba: {result.stderr.strip()}")
        sys.exit(1)


def start():
    cmd = ["schtasks", "/run", "/tn", TASK_NAME]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"Feladat '{TASK_NAME}' elinditva.")
    else:
        print(f"Hiba: {result.stderr.strip()}")


def stop():
    # A futo pythonw processzt allitjuk le
    subprocess.run(
        ["taskkill", "/f", "/im", "pythonw.exe", "/fi", f"WINDOWTITLE eq {TASK_NAME}"],
        capture_output=True,
    )
    # Biztonsagbol a kozvetlen processt is
    subprocess.run(
        ["wmic", "process", "where",
         f"commandline like '%tray.py%'",
         "delete"],
        capture_output=True,
    )
    print("Refresh switcher leallitva.")


def remove():
    stop()
    cmd = ["schtasks", "/delete", "/tn", TASK_NAME, "/f"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"Feladat '{TASK_NAME}' torolve.")
    else:
        print(f"Hiba: {result.stderr.strip()}")


def main():
    if len(sys.argv) < 2:
        print("Hasznalat: python install_task.py [install|remove|start|stop]")
        sys.exit(1)

    action = sys.argv[1].lower()
    if action == "install":
        install()
    elif action == "remove":
        remove()
    elif action == "start":
        start()
    elif action == "stop":
        stop()
    else:
        print(f"Ismeretlen parancs: {action}")
        print("Hasznalat: python install_task.py [install|remove|start|stop]")
        sys.exit(1)


if __name__ == "__main__":
    main()
