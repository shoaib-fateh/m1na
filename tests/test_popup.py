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
    window._sound_mode = None
    window._gaming_mode = False
    window._dismiss_timer_job = None
    window._dismiss_timer_started_at = None
    window._dismiss_timer_remaining_ms = 0
    window._dismiss_callback = None
    window._chat_input_open = False
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


def test_dialogue_can_be_dragged_from_title_area_and_remembers_position():
    class Popup:
        def __init__(self):
            self.geometry_value = None

        def winfo_x(self):
            return 100

        def winfo_y(self):
            return 200

        def winfo_width(self):
            return 420

        def winfo_height(self):
            return 142

        def geometry(self, value):
            self.geometry_value = value

    window = object.__new__(MinaWindows)
    window._popup = Popup()
    window._popup_kind = "dialogue"
    window._popup_drag_offset = None
    window._popup_drag_right = 240
    window._dialogue_position = None
    window._get_work_area = lambda: (0, 0, 1920, 1080)

    assert window._start_popup_drag(
        type("Event", (), {"x": 20, "y": 15, "x_root": 120, "y_root": 215})()
    ) == "break"
    window._drag_popup(
        type("Event", (), {"x_root": 320, "y_root": 415})()
    )

    assert window._popup.geometry_value == "+300+400"
    assert window._dialogue_position == (300, 400)
    window._end_popup_drag(None)
    assert window._popup_drag_offset is None


def test_dialogue_drag_ignores_buttons_and_clamps_to_desktop(monkeypatch):
    import ctypes
    from types import SimpleNamespace

    metrics = {76: 0, 77: 0, 78: 1920, 79: 1080}
    monkeypatch.setattr(
        ctypes,
        "windll",
        SimpleNamespace(
            user32=SimpleNamespace(GetSystemMetrics=lambda index: metrics[index])
        ),
        raising=False,
    )
    window = object.__new__(MinaWindows)
    window._popup = type(
        "Popup",
        (),
        {
            "winfo_x": lambda _self: 100,
            "winfo_y": lambda _self: 200,
            "winfo_width": lambda _self: 420,
            "winfo_height": lambda _self: 142,
            "geometry": lambda _self, value: setattr(_self, "geometry_value", value),
        },
    )()
    window._popup_kind = "dialogue"
    window._popup_drag_offset = None
    window._popup_drag_right = 240
    window._dialogue_position = None
    event = type("Event", (), {"x": 250, "y": 15, "x_root": 350, "y_root": 215})()

    assert window._start_popup_drag(event) is None
    window._popup_drag_offset = (10, 10)
    window._drag_popup(type("Event", (), {"x_root": 5000, "y_root": 5000})())

    assert window._popup.geometry_value == "+1500+938"
    assert window._dialogue_position == (1500, 938)


def test_emoji_peek_draws_only_the_gif_without_dialogue_decoration():
    class Frame:
        def width(self):
            return 48

        def height(self):
            return 48

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
    window._frames = [Frame()]
    window._pixel_button = lambda *_args, **_kwargs: (8, 9, None)
    window._popup_static_photos = []
    window.on_open_chat = lambda: None

    window._draw_popup(68, 80, peek=True)

    assert canvas.images == [((34, 26), {"image": window._frames[0]})]
    assert canvas.rectangles == []
    assert window._peek_emoji_bounds == (10, 2, 58, 50)
    assert window._peek_chat_bounds == (4, 48, 64, 78)


def test_hovering_emoji_only_peek_reveals_chat_button():
    class Canvas:
        def itemconfigure(self, _item, **kwargs):
            self.last_state = kwargs["state"]

    window = object.__new__(MinaWindows)
    window._canvas = Canvas()
    window._popup_kind = "peek"
    window._hover_chat_items = (1, 2)
    window._peek_emoji_bounds = (10, 2, 58, 50)
    window._peek_chat_bounds = (4, 48, 64, 78)

    window._on_popup_motion(type("Event", (), {"x": 34, "y": 26})())

    assert window._canvas.last_state == "normal"

    window._on_popup_motion(type("Event", (), {"x": 34, "y": 65})())

    assert window._canvas.last_state == "normal"

    window._on_popup_motion(type("Event", (), {"x": 2, "y": 2})())

    assert window._canvas.last_state == "hidden"


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
    window._chat_input_open = False
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
    window._chat_input_open = False

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


def test_chat_input_opens_under_the_existing_dialogue_popup(monkeypatch):
    import mina.popup as popup_module

    class Widget:
        def __init__(self, parent, **_kwargs):
            self.parent = parent
            self.options = _kwargs
            self.packed = False

        def pack(self, **_kwargs):
            self.packed = True

        def bind(self, *_args, **_kwargs):
            pass

        def place(self, **_kwargs):
            pass

        def winfo_x(self):
            return 0

        def winfo_y(self):
            return 0

        def winfo_width(self):
            return 320

        def winfo_height(self):
            return 36

        def focus_set(self):
            self.focused = True

        def delete(self, *_args):
            pass

        def create_rectangle(self, *_args, **_kwargs):
            return 1

        def create_image(self, *_args, **_kwargs):
            return 1

        def winfo_exists(self):
            return True

        def get(self):
            return "hello Mina"

    class Root:
        pass

    monkeypatch.setattr(popup_module.tk, "Frame", Widget)
    monkeypatch.setattr(popup_module.tk, "Button", Widget)
    monkeypatch.setattr(popup_module.tk, "Entry", Widget)
    monkeypatch.setattr(popup_module.tk, "Canvas", Widget)
    monkeypatch.setattr(popup_module.tk.Misc, "tkraise", lambda _self: None)
    monkeypatch.setattr(
        popup_module.tk,
        "Toplevel",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Chat must stay in Mina's existing window.")
        ),
    )
    root = Root()
    popup = Widget(root)
    popup.destroyed = False
    popup.destroy = lambda: setattr(popup, "destroyed", True)
    popup.deiconified = False
    popup.raised = False
    popup.deiconify = lambda: setattr(popup, "deiconified", True)
    popup.lift = lambda: setattr(popup, "raised", True)
    popup.update_idletasks = lambda: None
    popup.winfo_reqheight = lambda: 180
    popup.winfo_width = lambda: 420
    popup.winfo_height = lambda: 180
    popup_geometries = []
    popup.geometry = lambda geometry: popup_geometries.append(geometry)
    canvas = Widget(popup)
    canvas.winfo_width = lambda: 1
    canvas.winfo_reqwidth = lambda: 420
    window = object.__new__(MinaWindows)
    window.root = root
    window._popup = popup
    window._popup_kind = "dialogue"
    window._canvas = canvas
    window._animation_job = None
    window.config = {"ui": {"font": "Mojangles"}}
    window._chat_input_frame = None
    window._chat_entry_slot = None
    window._chat_entry = None
    window._chat_entry_canvas = None
    window._chat_input_open = False
    window._text_renderer = type(
        "Renderer", (), {"render": lambda *_args, **_kwargs: object()}
    )()
    window._pause_dismiss_timer = lambda: None
    window._get_work_area = lambda: (0, 0, 1920, 1080)
    window._recenter_popup = lambda: None
    window._refresh_chat_entry_display = lambda *_args: None
    requests = []
    window.on_chat_request = requests.append

    window.show_chat()

    assert window._chat_input_frame.parent is popup
    assert window._chat_entry.parent is window._chat_entry_slot
    assert window._chat_input_open
    assert window._chat_entry.options["font"] == ("Segoe UI", 11)
    assert window._chat_entry_canvas.parent is window._chat_entry_slot
    assert window._chat_send_button.options["image"] is window._chat_send_photo
    assert popup.deiconified
    assert popup.raised
    assert window._chat_entry.focused
    assert popup_geometries == ["420x180"]

    assert window._chat_send_button.options["command"]() == "break"

    assert requests == ["hello Mina"]
    assert not popup.destroyed


def test_chat_from_peek_replaces_it_with_visible_dialogue(monkeypatch):
    import mina.popup as popup_module

    class Widget:
        def __init__(self, parent, **_kwargs):
            self.parent = parent

        def pack(self, **_kwargs):
            pass

        def bind(self, *_args, **_kwargs):
            pass

        def place(self, **_kwargs):
            pass

        def winfo_x(self):
            return 0

        def winfo_y(self):
            return 0

        def winfo_width(self):
            return 320

        def winfo_height(self):
            return 36

        def focus_set(self):
            pass

        def update_idletasks(self):
            pass

        def winfo_reqheight(self):
            return 180

        def winfo_width(self):
            return 420

        def winfo_reqwidth(self):
            return 420

        def geometry(self, *_args):
            pass

        def deiconify(self):
            pass

        def lift(self):
            pass

    monkeypatch.setattr(popup_module.tk, "Frame", Widget)
    monkeypatch.setattr(popup_module.tk, "Entry", Widget)
    monkeypatch.setattr(popup_module.tk, "Button", Widget)
    monkeypatch.setattr(popup_module.tk, "Canvas", Widget)
    monkeypatch.setattr(popup_module.tk.Misc, "tkraise", lambda _self: None)

    window = object.__new__(MinaWindows)
    old_popup = Widget(None)
    window._popup = old_popup
    window._popup_kind = "peek"
    window._current_mood = "Curious"
    window._chat_input_frame = None
    window._chat_entry_slot = None
    window._chat_entry = None
    window._chat_entry_canvas = None
    window._chat_input_open = False
    window._text_renderer = type(
        "Renderer", (), {"render": lambda *_args, **_kwargs: object()}
    )()
    window._canvas = Widget(None)
    window._canvas.winfo_width = lambda: 420
    window._animation_job = None
    window.root = type("Root", (), {"after_cancel": lambda *_args: None})()
    window.config = {"ui": {"font": "Mojangles"}}
    window._pause_dismiss_timer = lambda: None
    window._get_work_area = lambda: (0, 0, 1920, 1080)
    window._recenter_popup = lambda: None
    window._refresh_chat_entry_display = lambda *_args: None
    replacements = []

    def show_dialogue(message, mood):
        replacements.append((message, mood))
        window._popup = Widget(None)
        window._popup_kind = "dialogue"

    window._cancel_popup = lambda notify=True: setattr(window, "_popup", None)
    window.show_dialogue = show_dialogue

    window.show_chat()

    assert replacements == [("Hey! What's up?", "Curious")]
    assert window._chat_input_frame.parent is window._popup


def test_dialogue_popup_grows_to_fit_wrapped_message():
    class Image:
        def height(self):
            return 184

    window = object.__new__(MinaWindows)
    window.config = {"popup": {"message_font_size": 16}}
    window._text_renderer = type(
        "Renderer", (), {"render": lambda *_args, **_kwargs: Image()}
    )()

    assert window._dialogue_popup_height("a long message", 420, 142) == 244
