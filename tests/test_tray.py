import sys
from types import SimpleNamespace

from mina.tray import MinaTrayIcon


def test_tray_menu_dispatches_chat_and_exit(monkeypatch):
    class Menu:
        SEPARATOR = object()

        def __init__(self, *items):
            self.items = items

    class MenuItem:
        def __init__(self, label, action, **kwargs):
            self.label = label
            self.action = action
            self.options = kwargs

    class Icon:
        def __init__(self, *_args, menu, **_kwargs):
            self.menu = menu
            self.detached = False
            self.stopped = False

        def run_detached(self):
            self.detached = True

        def stop(self):
            self.stopped = True

    monkeypatch.setitem(
        sys.modules,
        "pystray",
        SimpleNamespace(Icon=Icon, Menu=Menu, MenuItem=MenuItem),
    )
    calls = []
    tray = MinaTrayIcon(lambda: calls.append("chat"), lambda: calls.append("exit"))

    tray.start()
    tray._icon.menu.items[0].action(None, None)
    tray._icon.menu.items[2].action(None, None)
    tray.stop()

    assert tray._icon.detached
    assert tray._icon.stopped
    assert tray._icon.menu.items[0].options["default"]
    assert calls == ["chat", "exit"]
