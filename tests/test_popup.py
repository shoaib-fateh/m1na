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

    window._type_next()

    assert window._typed == 1
    assert window.root.scheduled[0][0] == 8000
    assert window.root.scheduled[0][1].__self__ is window
    assert window.root.scheduled[0][1].__name__ == "_dismiss_dialogue"


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
    window._sound_playing = False
    window._popup_static_photos = []
    window.on_popup_dismissed = lambda: calls.append("dismissed")
    window._stop_sound = lambda: None
    window.root = type("Root", (), {"after_cancel": lambda *_args: None})()

    window._cancel_popup()

    assert calls == ["destroy", "dismissed"]
