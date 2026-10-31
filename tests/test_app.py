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


def test_create_scheduler_uses_production_profile_and_persistent_state(
    monkeypatch, tmp_path
):
    class Scheduler:
        def __init__(self, *, settings, is_active, on_interrupt, clock):
            self.settings = settings
            self.is_active = is_active
            self.on_interrupt = on_interrupt
            self.clock = clock
            self.started = False

        def start(self):
            self.started = True

    monkeypatch.setattr("mina.app.InterruptionScheduler", Scheduler)
    app = object.__new__(MinaApp)
    app.config = {
        "profile": "normal",
        "profiles": {
            "normal": {
                "interval_seconds": [1800, 3600],
                "cooldown_seconds": [1800, 2700],
                "daily_limit": 8,
            }
        },
        "scheduler": {
            "enabled": True,
            "state_path": str(tmp_path / "scheduler.sqlite3"),
        },
        "activity": {
            "active_within_seconds": 300,
            "poll_interval_ms": 1000,
        },
    }
    app.windows = FakeWindows()
    app.windows.muted = False
    app._gaming_mode = False
    app._manual_chat_active = False
    app._begin_interruption = lambda: None

    app._create_scheduler()

    assert app.scheduler.settings.interval_seconds == (1800, 3600)
    assert app.scheduler.settings.daily_limit == 8
    assert app.scheduler.settings.state_path == tmp_path / "scheduler.sqlite3"
    assert app.scheduler.is_active is not None
    assert app.scheduler.started


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


def test_time_behavior_monitor_runs_before_model_is_ready(monkeypatch):
    class Monitor:
        def __init__(self):
            self.polled = []

        def poll(self, now, uptime_seconds, idle_seconds):
            self.polled.append((now, uptime_seconds, idle_seconds))
            return None

    app = object.__new__(MinaApp)
    app._closing = False
    app._behavior_generation_active = False
    app._model_ready = False
    app._generation_active = False
    app._chat_generation_active = False
    app._manual_chat_active = False
    app._gaming_mode = False
    app.time_behavior = Monitor()
    app.config = {"time_behavior": {"poll_interval_ms": 5000}}
    app.root = FakeRoot()
    app.windows = FakeWindows()

    monkeypatch.setattr("mina.app.get_system_uptime_seconds", lambda: 7200)
    monkeypatch.setattr("mina.app.get_idle_seconds", lambda: 30)

    app._poll_time_behavior()

    assert len(app.time_behavior.polled) == 1
    assert app.time_behavior.polled[0][1:] == (7200, 30)
    assert app.root.scheduled[-1][0] == 5000


def test_behavior_reply_can_be_silent_or_shown_and_acknowledged():
    class Monitor:
        def __init__(self):
            self.acknowledged = []
            self.spoken = 0

        def acknowledge(self, event_id):
            self.acknowledged.append(event_id)

        def mark_spoken(self):
            self.spoken += 1

    class Windows(FakeWindows):
        def __init__(self):
            super().__init__()
            self.muted = False
            self.dialogues = []

        def show_dialogue(self, message, mood):
            self.dialogues.append((message, mood))

    app = object.__new__(MinaApp)
    app._closing = False
    app._gaming_mode = False
    app._manual_chat_active = False
    app._chat_generation_active = False
    app._behavior_generation_active = True
    app._behavior_event_id = 7
    app._events = queue.Queue()
    app._events.put(("behavior_reply", (7, "A little clock frog!")))
    app.root = FakeRoot()
    app.windows = Windows()
    app.time_behavior = Monitor()
    app.dataset = None
    app._mood_for_message = lambda _message: "Cute"
    app._drain_events()

    assert app.windows.dialogues == [("A little clock frog!", "Cute")]
    assert app.time_behavior.acknowledged == [7]
    assert app.time_behavior.spoken == 1

    app._behavior_generation_active = True
    app._behavior_event_id = 8
    app._events.put(("behavior_reply", (8, None)))
    app._drain_events()

    assert app.windows.dialogues == [("A little clock frog!", "Cute")]
    assert app.time_behavior.acknowledged == [7, 8]
