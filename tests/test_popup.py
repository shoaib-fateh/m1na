from mina.popup import MinaWindows


class FakeCanvas:
    def __init__(self):
        self.configured = []

    def itemconfigure(self, item, **kwargs):
        self.configured.append((item, kwargs))


class FakeRoot:
    def __init__(self):
        self.scheduled = []

    def after(self, delay, callback):
        self.scheduled.append((delay, callback))
        return "after-id"


def test_completed_message_holds_for_configured_duration():
    window = object.__new__(MinaWindows)
    window._canvas = FakeCanvas()
    window._popup = object()
    window._message = "M"
    window._typed = 0
    window._message_size = 12
    window._message_width = 100
    window._message_item = 4
    window._text_renderer = type("Renderer", (), {"render": lambda *_args, **_kwargs: "raster"})()
    window.config = {"popup": {"hold_ms": 8000}}
    window.root = FakeRoot()
    window._sound_playing = False
    window._dismiss_timer_job = None
    window._dismiss_timer_started_at = None
    window._dismiss_timer_remaining_ms = 0
    window._dismiss_callback = None
    window._popup_hovered = False

    window._type_next()

    assert window._typed == 1
    assert window.root.scheduled[0][0] == 8000
    assert window._dismiss_callback.__name__ == "_dismiss_dialogue"
    assert window._dismiss_timer_job == "after-id"


def test_minimize_slides_popup_away_without_exiting_companion():
    window = object.__new__(MinaWindows)
    window._popup = type("Popup", (), {"winfo_x": lambda _self: 120, "winfo_y": lambda _self: 500})()
    calls = []
    window._get_work_area = lambda: (0, 0, 1920, 1040)
    window._slide = lambda *args: calls.append(args)

    window._minimize_dialogue()

    assert calls == [(120, 500, 1042, 200, "out")]


def test_emoji_peek_draws_only_the_gif_without_dialogue_decoration():
    class Canvas:
        def __init__(self):
            self.images = []
            self.rectangles = []

        def create_image(self, *args, **kwargs):
            self.images.append((args, kwargs))
            return 7

        def create_rectangle(self, *args, **kwargs):
            self.rectangles.append((args, kwargs))

    frame = object()
    canvas = Canvas()
    window = object.__new__(MinaWindows)
    window._canvas = canvas
    window._frames = [frame]

    window._draw_popup(72, 72, peek=True)

    assert canvas.images == [((36, 36), {"image": frame})]
    assert canvas.rectangles == []


def test_emoji_peek_is_horizontally_centered():
    window = object.__new__(MinaWindows)

    x = window._popup_target_x(72, 0, 1920, "bottom_right", peek=True)

    assert x == 924


def test_emoji_animation_repeats_frames_until_popup_is_dismissed():
    class Canvas:
        def __init__(self):
            self.images = []

        def itemconfigure(self, _item, image):
            self.images.append(image)

    class Root:
        def __init__(self):
            self.callbacks = []

        def after(self, delay, callback):
            self.callbacks.append((delay, callback))
            return len(self.callbacks)

    first, second = object(), object()
    window = object.__new__(MinaWindows)
    window._frames = [first, second]
    window._frame_durations = [80, 80]
    window._frame_index = 0
    window._canvas = Canvas()
    window._popup = object()
    window._emoji_item = 1
    window.root = Root()

    window._animate_emoji()
    window.root.callbacks[0][1]()
    window.root.callbacks[1][1]()

    assert window._canvas.images == [first, second, first]
    assert [delay for delay, _callback in window.root.callbacks] == [80, 80, 80]


def test_cancel_popup_notifies_when_popup_disappears():
    calls = []

    class Popup:
        def destroy(self):
            calls.append("destroy")

    window = object.__new__(MinaWindows)
    window._popup = Popup()
    window._canvas = object()
    window._frame_job = None
    window._animation_job = None
    window._type_job = None
    window._hover_check_job = None
    window._dismiss_timer_job = None
    window._dismiss_timer_started_at = None
    window._dismiss_timer_remaining_ms = 0
    window._dismiss_callback = None
    window._sound_playing = False
    window._popup_static_photos = []
    window.on_popup_dismissed = lambda: calls.append("dismissed")
    window._stop_sound = lambda: None
    window.root = type("Root", (), {"after_cancel": lambda *_args: None})()

    window._cancel_popup()

    assert calls == ["destroy", "dismissed"]


def test_hover_pauses_dismiss_timer_and_resumes_remaining_time(monkeypatch):
    import mina.popup as popup_module

    clock = [10.0]
    monkeypatch.setattr(popup_module.time, "monotonic", lambda: clock[0])

    class Root:
        def __init__(self):
            self.scheduled = []
            self.cancelled = []

        def after(self, delay, callback):
            job = f"job-{len(self.scheduled) + 1}"
            self.scheduled.append((job, delay, callback))
            return job

        def after_cancel(self, job):
            self.cancelled.append(job)

    window = object.__new__(MinaWindows)
    window.root = Root()
    window._popup = object()
    window._popup_hovered = False
    window._dismiss_timer_job = None
    window._dismiss_timer_started_at = None
    window._dismiss_timer_remaining_ms = 0
    window._dismiss_callback = None

    window._start_dismiss_timer(8000, lambda: None)
    first_job = window._dismiss_timer_job
    clock[0] = 13.0
    window._on_popup_enter(None)

    assert first_job in window.root.cancelled
    assert window._dismiss_timer_remaining_ms == 5000
    assert window._dismiss_timer_job is None

    window._popup_hovered = False
    window._resume_dismiss_timer()

    assert window.root.scheduled[-1][1] == 5000
    assert window._dismiss_timer_job == window.root.scheduled[-1][0]
