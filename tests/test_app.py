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
    def __init__(self):
        self.gaming_modes = []

    def set_status(self, *_args, **_kwargs):
        pass

    def set_gaming_mode(self, active):
        self.gaming_modes.append(active)

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


def test_gaming_mode_pauses_scheduler_and_resumes_with_fresh_schedule():
    class Scheduler:
        def __init__(self):
            self.enabled = True
            self.cooldown_until = 99
            self.starts = 0
            self.stops = 0

        def stop(self):
            self.enabled = False
            self.stops += 1

        def start(self):
            self.enabled = True
            self.starts += 1

    app = object.__new__(MinaApp)
    app._gaming_mode = False
    app._thought_generation_id = 4
    app._generation_active = True
    app._model_ready = True
    app._manual_chat_active = False
    app.windows = FakeWindows()
    app.windows.muted = False
    app.scheduler = Scheduler()
    app._set_gaming_mode(True, "SomeGame")

    assert app._gaming_mode
    assert app._thought_generation_id == 5
    assert not app._generation_active
    assert not app.scheduler.enabled
    assert app.windows.gaming_modes == [True]

    app._set_gaming_mode(False)

    assert not app._gaming_mode
    assert app.scheduler.enabled
    assert app.scheduler.cooldown_until == 0
    assert app.windows.gaming_modes == [True, False]


def test_starting_manual_chat_cancels_pending_interruption():
    class Scheduler:
        def __init__(self):
            self.stopped = False
            self.cancelled = False

        def stop(self):
            self.stopped = True

        def cancel_interruption(self):
            self.cancelled = True

    class Windows(FakeWindows):
        def __init__(self):
            super().__init__()
            self.chat_opened = False

        def show_chat(self):
            self.chat_opened = True

    app = object.__new__(MinaApp)
    app._chat_generation_active = False
    app._manual_chat_active = False
    app._generation_active = True
    app._thought_generation_id = 4
    app.scheduler = Scheduler()
    app.windows = Windows()

    app._open_chat()

    assert app.scheduler.stopped
    assert app.scheduler.cancelled
    assert app._thought_generation_id == 5
    assert not app._generation_active
    assert app._manual_chat_active
    assert app.windows.chat_opened


def test_thought_generated_before_game_mode_is_discarded():
    class Root(FakeRoot):
        pass

    class Windows(FakeWindows):
        def __init__(self):
            super().__init__()
            self.shown = []

        def append_chat_notice(self, *_args):
            pass

        def set_chat_busy(self, *_args):
            pass

        def set_gaming_mode(self, *_args):
            pass

    app = object.__new__(MinaApp)
    app._closing = False
    app._gaming_mode = True
    app._thought_generation_id = 2
    app._generation_active = False
    app._events = queue.Queue()
    app._events.put(
        (
            "message",
            {"generation_id": 1, "text": "A late thought.", "applications": []},
        )
    )
    app.root = Root()
    app.windows = Windows()
    app._drain_events()

    assert not app.windows.shown
    assert len(app.root.scheduled) == 1
