import queue

from mina.app import MinaApp


class FakeRoot:
    def __init__(self):
        self.scheduled = []
        self.deiconified = False

    def after(self, delay, callback):
        self.scheduled.append((delay, callback))

    def deiconify(self):
        self.deiconified = True


class FakeWindows:
    def set_status(self, *_args, **_kwargs):
        pass

    def show(self):
        raise AssertionError("The persistent companion panel must stay hidden.")


def test_model_ready_does_not_show_persistent_companion_panel():
    app = object.__new__(MinaApp)
    app._closing = False
    app._model_ready = False
    app._events = queue.Queue()
    app._events.put(("model_loaded", None))
    app.root = FakeRoot()
    app.windows = FakeWindows()
    app._create_scheduler = lambda: None

    app._drain_events()

    assert app._model_ready
    assert not app.root.deiconified
