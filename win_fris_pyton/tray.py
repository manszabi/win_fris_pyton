import logging
import logging.handlers
import os
import threading

from PIL import Image, ImageDraw, ImageFont
import pystray

from refresh_switcher import (
    get_current_refresh_rate,
    get_monitor_device,
    load_config,
    monitor_loop,
)

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "service.log")


class TrayApp:
    def __init__(self):
        self.stop_event = threading.Event()
        self.current_hz = 0
        self.current_game = None
        self.icon = None

    def create_icon_image(self, hz, game=None):
        """Generál egy éles ikont 4x supersampling-gel."""
        final_size = 256
        render_size = final_size * 4  # 1024px-en rajzolunk, majd lekicsinyitjuk
        img = Image.new("RGBA", (render_size, render_size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        radius = 160
        bg_color = (0, 150, 70, 255) if game else (50, 50, 50, 255)
        draw.rounded_rectangle([16, 16, render_size - 17, render_size - 17], radius=radius, fill=bg_color)

        text = str(hz)
        font_size = 560 if len(text) <= 2 else 440 if len(text) == 3 else 320
        try:
            font = ImageFont.truetype("arialbd.ttf", font_size)
        except OSError:
            try:
                font = ImageFont.truetype("arial.ttf", font_size)
            except OSError:
                font = ImageFont.load_default()

        cx, cy = render_size / 2, render_size / 2
        for dx, dy in [(-1,-1),(0,-1),(1,-1),(-1,0),(1,0),(-1,1),(0,1),(1,1)]:
            draw.text((cx + dx * 8, cy + dy * 8), text, fill=(0, 0, 0, 180), font=font, anchor="mm")
        draw.text((cx, cy), text, fill="white", font=font, anchor="mm")

        # Lekicsinyites LANCZOS filterrel — eles, antialias-olt eredmeny
        img = img.resize((final_size, final_size), Image.LANCZOS)

        return img

    def _make_tooltip(self, hz, game_name=None):
        title = "Display Refresh Rate Switcher by ManSzabi"
        if game_name:
            return f"{title}\n{hz} Hz - {game_name}"
        return f"{title}\n{hz} Hz"

    def on_state_change(self, hz, game_name):
        """Callback a monitor_loop-bol — frissiti az ikont."""
        self.current_hz = hz
        self.current_game = game_name
        if self.icon:
            self.icon.icon = self.create_icon_image(hz, game_name)
            self.icon.title = self._make_tooltip(hz, game_name)

    def on_quit(self, icon, item):
        """Kilepes gomb."""
        self.stop_event.set()
        icon.stop()

    def get_status_text(self, item):
        if self.current_game:
            return f"{self.current_hz} Hz - {self.current_game}"
        return f"{self.current_hz} Hz"

    def run(self):
        # Kezdeti allapot lekerdezese
        config = load_config()
        monitor_number = config.get("monitor", 1)
        device = get_monitor_device(monitor_number)
        if device:
            self.current_hz = get_current_refresh_rate(device)
        else:
            self.current_hz = config["default_refresh_rate"]

        # Monitor loop kulon szalban
        monitor_thread = threading.Thread(
            target=monitor_loop,
            args=(self.stop_event, self.on_state_change),
            daemon=True,
        )
        monitor_thread.start()

        # Tray ikon letrehozasa
        menu = pystray.Menu(
            pystray.MenuItem(self.get_status_text, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Kilepes", self.on_quit),
        )

        self.icon = pystray.Icon(
            "RefreshSwitcher",
            self.create_icon_image(self.current_hz),
            title=self._make_tooltip(self.current_hz),
            menu=menu,
        )

        self.icon.run()


if __name__ == "__main__":
    handler = logging.handlers.RotatingFileHandler(
        LOG_PATH, maxBytes=500_000, backupCount=1, encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

    logger = logging.getLogger("RefreshSwitcher")
    logger.setLevel(logging.WARNING)
    logger.addHandler(handler)

    app = TrayApp()
    app.run()
