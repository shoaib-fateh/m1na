from __future__ import annotations

from collections.abc import Callable

from PIL import Image, ImageDraw


class MinaTrayIcon:
    def __init__(
        self, on_chat: Callable[[], None], on_exit: Callable[[], None]
    ) -> None:
        import pystray

        image = Image.new("RGBA", (64, 64), (24, 28, 34, 0))
        draw = ImageDraw.Draw(image)
        draw.rectangle((8, 8, 55, 47), fill="#526779", outline="#101419", width=4)
        draw.rectangle((14, 15, 49, 39), fill="#d9f1dc", outline="#101419", width=3)
        draw.rectangle((21, 22, 27, 29), fill="#344454")
        draw.rectangle((37, 22, 43, 29), fill="#344454")
        draw.rectangle((26, 33, 38, 36), fill="#8fcb75")
        draw.polygon(((21, 47), (32, 59), (43, 47)), fill="#8fcb75")

        self._icon = pystray.Icon(
            "Mina",
            image,
            "Mina",
            menu=pystray.Menu(
                pystray.MenuItem(
                    "Chat with Mina",
                    lambda _icon, _item: on_chat(),
                    default=True,
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Exit Mina", lambda _icon, _item: on_exit()),
            ),
        )

    def start(self) -> None:
        self._icon.run_detached()

    def stop(self) -> None:
        self._icon.stop()
