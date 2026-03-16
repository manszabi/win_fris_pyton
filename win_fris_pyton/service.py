import logging
import threading

import servicemanager
import win32event
import win32service
import win32serviceutil

from refresh_switcher import monitor_loop


class RefreshSwitcherService(win32serviceutil.ServiceFramework):
    _svc_name_ = "RefreshRateSwitcher"
    _svc_display_name_ = "Display Refresh Rate Switcher"
    _svc_description_ = (
        "Automatikusan valtoztatja a kijelzo frissitesi frekvenciajat "
        "jatekok inditasakor es leallitasakor."
    )

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.stop_event = threading.Event()
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self.stop_event.set()
        win32event.SetEvent(self.hWaitStop)

    def SvcDoRun(self):
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, ""),
        )

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            handlers=[
                logging.FileHandler(
                    r"C:\Users\mansz\win_fris_pyton\service.log", encoding="utf-8"
                ),
            ],
        )

        monitor_loop(stop_event=self.stop_event)


if __name__ == "__main__":
    win32serviceutil.HandleCommandLine(RefreshSwitcherService)
