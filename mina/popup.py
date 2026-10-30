from __future__ import annotations

import os
import time
import tkinter as tk
from collections.abc import Callable
from pathlib import Path

from mina.emoji_assets import EmojiLibrary
from mina.pixel_text import PixelTextRenderer


PIXEL = {
    "background": "#181c22",
    "panel": "#344454",
    "panel_light": "#526779",
    "panel_dark": "#202a34",
    "border": "#101419",
    "accent": "#8fcb75",
    "text": "#f2eccb",
    "muted": "#c7c2a8",
    "error": "#ff9c89",
}


class MinaWindows:
    def __init__(
        self,
        root: tk.Tk,
        emoji_library: EmojiLibrary,
        config: dict,
        on_mute: Callable[[], None],
        on_exit: Callable[[], None],
        on_popup_dismissed: Callable[[], None] | None = None,
    ) -> None:
        self.root = root
        self.emoji_library = emoji_library
        self.config = config
        self.on_mute = on_mute
        self.on_exit = on_exit
        self.on_popup_dismissed = on_popup_dismissed
        self.muted = False
        self._popup: tk.Toplevel | None = None
        self._canvas: tk.Canvas | None = None
        self._frame_job: str | None = None
        self._animation_job: str | None = None
        self._type_job: str | None = None
        self._dismiss_timer_job: str | None = None
        self._hover_check_job: str | None = None
        self._dismiss_timer_remaining_ms = 0
        self._dismiss_timer_started_at: float | None = None
        self._dismiss_callback: Callable[[], None] | None = None
        self._popup_hovered = False
        self._sound_playing = False
        self._status_clear_job: str | None = None
        self._frames = []
        self._frame_durations = []
        self._frame_index = 0
        self._companion_frames = []
        self._companion_frame_durations = []
        self._companion_frame_index = 0
        self._companion_static_photos: list[tk.PhotoImage] = []
        self._popup_static_photos: list[tk.PhotoImage] = []
        self._companion_mute_photo: tk.PhotoImage | None = None
        self._popup_mute_photo: tk.PhotoImage | None = None
        self._message = ""
        self._typed = 0
        self._popup_kind = ""
        self._status = ""
        ui_config = config["ui"]
        font_path = Path(ui_config.get("font_path", "assets/fonts/mojangles.otf"))
        if not font_path.is_absolute():
            from mina.config import PROJECT_ROOT

            font_path = PROJECT_ROOT / font_path
        fallback_path = Path(
            os.path.expandvars(
                ui_config.get("persian_fallback_path", r"%WINDIR%\Fonts\segoeui.ttf")
            )
        )
        self._text_renderer = PixelTextRenderer(root, font_path, fallback_path)

        self._build_companion()
        try:
            companion_scale = int(config["ui"].get("emoji_scale", 2))
            companion_animation = self.emoji_library.animation("Neutral", scale=companion_scale)
            self._companion_frames = companion_animation.frames
            self._companion_frame_durations = companion_animation.durations_ms
            canvas = self.root.winfo_children()[0]
            canvas.itemconfigure(self._companion_emoji, image=self._companion_frames[0])
            self._animate_companion()
        except (KeyError, OSError, ValueError) as error:
            self.set_status(f"Emoji assets unavailable: {error}", error=True)
        self.root.after(500, self._position_companion)
        self.root.bind("<Configure>", self._on_root_configure)

    def _create_pixel_text(
        self,
        canvas: tk.Canvas,
        x: int,
        y: int,
        text: str,
        size: int,
        color: str,
        anchor: str = "center",
        max_width: int | None = None,
    ) -> tuple[int, tk.PhotoImage]:
        photo = self._text_renderer.render(text, size, color, max_width)
        item = canvas.create_image(x, y, image=photo, anchor=anchor)
        return item, photo

    def _build_companion(self) -> None:
        ui = self.config["ui"]
        width, height = ui.get("companion_size", [230, 68])
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=PIXEL["border"])
        self.root.geometry(f"{width}x{height}")

        canvas = tk.Canvas(
            self.root,
            width=width,
            height=height,
            bg=PIXEL["border"],
            highlightthickness=0,
            bd=0,
        )
        canvas.pack(fill="both", expand=True)
        canvas.create_rectangle(2, 2, width - 2, height - 2, fill=PIXEL["panel_dark"], outline="")
        canvas.create_rectangle(4, 4, width - 4, height - 4, fill=PIXEL["panel"], outline="")
        canvas.create_rectangle(5, 5, width - 5, 27, fill=PIXEL["panel_light"], outline="")
        _, title_photo = self._create_pixel_text(
            canvas, 12, 16, "MINA", 16, PIXEL["text"], anchor="w"
        )
        self._companion_static_photos.append(title_photo)
        self._companion_emoji = canvas.create_image(24, 57)
        self._companion_status, self._companion_status_photo = self._create_pixel_text(
            canvas,
            50,
            56,
            self._status,
            14,
            PIXEL["muted"],
            anchor="w",
            max_width=width - 62,
        )
        self._companion_canvas = canvas

        (
            self._mute_button,
            self._mute_label,
            self._companion_mute_photo,
        ) = self._pixel_button(
            canvas,
            width - 85,
            16,
            "MUTE",
            self._toggle_mute,
            photo_store=self._companion_static_photos,
        )
        self._exit_button, _, _ = self._pixel_button(
            canvas, width - 35, 16, "X", self.on_exit, small=True
        )

        self.root.bind("<Button-1>", self._start_drag)
        self.root.bind("<B1-Motion>", self._drag)
        self._drag_origin = None

    def _pixel_button(
        self,
        canvas: tk.Canvas,
        x: int,
        y: int,
        label: str | None,
        command: Callable[[], None],
        small: bool = False,
        photo_store: list[tk.PhotoImage] | None = None,
    ) -> tuple[int, int, tk.PhotoImage | None]:
        width = 28 if small else 56
        x1, y1 = x - width // 2, y - 10
        canvas.create_rectangle(
            x1 + 2, y1 + 2, x1 + width + 2, y1 + 20, fill=PIXEL["border"], outline=""
        )
        button = canvas.create_rectangle(
            x1, y1, x1 + width, y1 + 18, fill=PIXEL["panel"], outline=PIXEL["border"]
        )
        if label is None:
            text = canvas.create_rectangle(
                x - 5,
                y + 3,
                x + 5,
                y + 5,
                fill=PIXEL["text"],
                outline="",
            )
            photo = None
        else:
            text, photo = self._create_pixel_text(
                canvas, x, y, label, 12, PIXEL["text"]
            )
            if photo_store is not None:
                photo_store.append(photo)
        for item in (button, text):
            canvas.tag_bind(item, "<Button-1>", lambda _event: command())
            canvas.tag_bind(
                item,
                "<Enter>",
                lambda _event, button=button: canvas.itemconfigure(button, fill=PIXEL["panel_light"]),
            )
            canvas.tag_bind(
                item,
                "<Leave>",
                lambda _event, button=button: canvas.itemconfigure(button, fill=PIXEL["panel"]),
            )
        return button, text, photo

    def _position_companion(self) -> None:
        if not self.root.winfo_exists():
            return
        screen_width = self.root.winfo_screenwidth()
        x = screen_width - self.root.winfo_width() - 12
        self.root.geometry(f"+{x}+18")

    def _on_root_configure(self, _event: tk.Event) -> None:
        return

    def _start_drag(self, event: tk.Event) -> None:
        self._drag_origin = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())

    def _drag(self, event: tk.Event) -> None:
        if self._drag_origin:
            dx, dy = self._drag_origin
            self.root.geometry(f"+{event.x_root - dx}+{event.y_root - dy}")

    def _toggle_mute(self) -> None:
        self.on_mute()

    def set_muted(self, muted: bool) -> None:
        self.muted = muted
        if muted:
            self._stop_sound()
        label = "UNMUTE" if muted else "MUTE"
        self._companion_mute_photo = self._text_renderer.render(label, 12, PIXEL["text"])
        self._companion_canvas.itemconfigure(self._mute_label, image=self._companion_mute_photo)
        if self._canvas is not None and hasattr(self, "_mute_item"):
            self._popup_mute_photo = self._text_renderer.render(label, 12, PIXEL["text"])
            self._canvas.itemconfigure(self._mute_item, image=self._popup_mute_photo)

    def set_status(
        self, status: str, error: bool = False, transient_ms: int | None = None
    ) -> None:
        if self._status_clear_job:
            self.root.after_cancel(self._status_clear_job)
            self._status_clear_job = None
        self._status = status
        color = PIXEL["error"] if error else PIXEL["muted"]
        self._companion_status_photo = self._text_renderer.render(
            status, 14, color, max_width=self.config["ui"].get("companion_size", [280, 84])[0] - 62
        )
        self._companion_canvas.itemconfigure(
            self._companion_status, image=self._companion_status_photo
        )
        if transient_ms is not None and not error:
            self._status_clear_job = self.root.after(
                max(1, transient_ms), self._clear_status
            )

    def _clear_status(self) -> None:
        self._status_clear_job = None
        self._status = ""
        self._companion_status_photo = self._text_renderer.render(
            "", 14, PIXEL["muted"]
        )
        self._companion_canvas.itemconfigure(
            self._companion_status, image=self._companion_status_photo
        )

    def show_dialogue(self, message: str, mood: str, sound_path: str | None = None) -> None:
        self._show(mood, sound_path, message=message)

    def show_peek(self, mood: str, corner: str = "bottom_right") -> None:
        self._show(mood, None, corner=corner, peek=True)

    def _show(
        self,
        mood: str,
        sound_path: str | None,
        message: str = "",
        corner: str = "bottom_right",
        peek: bool = False,
    ) -> None:
        self._cancel_popup()
        self._popup_kind = "peek" if peek else "dialogue"
        self._popup_hovered = False
        self._popup_static_photos.clear()
        self._message = message
        self._typed = 0
        self._frame_index = 0
        try:
            animation = self.emoji_library.animation(mood)
            self._frames = animation.frames
            self._frame_durations = animation.durations_ms
        except Exception as error:
            self.set_status(f"Emoji error: {error}", error=True)
            if self.on_popup_dismissed is not None:
                self.on_popup_dismissed()
            return

        popup_config = self.config["popup"]
        if peek:
            frame = self._frames[0]
            width, height = frame.width() + 8, frame.height() + 8
        else:
            width, height = popup_config.get("size", [420, 142])
        self._popup = tk.Toplevel(self.root)
        popup = self._popup
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        popup.configure(bg=PIXEL["border"])
        if peek:
            popup.attributes("-transparentcolor", PIXEL["border"])
        self._canvas = tk.Canvas(
            popup,
            width=width,
            height=height,
            bg=PIXEL["border"],
            highlightthickness=0,
            bd=0,
        )
        self._canvas.pack()
        self._draw_popup(width, height, peek)
        popup.bind("<Enter>", self._on_popup_enter)
        popup.bind("<Leave>", self._on_popup_leave)
        self._canvas.bind("<Enter>", self._on_popup_enter)
        self._canvas.bind("<Leave>", self._on_popup_leave)

        work_left, work_top, work_right, work_bottom = self._get_work_area()
        if corner.endswith("left"):
            target_x = work_left + 12
        else:
            target_x = work_right - width - 12
        target_y = work_bottom - height - 4
        start_y = work_bottom + 2
        popup.geometry(f"+{target_x}+{start_y}")

        if not peek and sound_path:
            self._play_sound(sound_path)

        animation = popup_config.get("animation", {})
        slide_ms = max(1, int(animation.get("slide_ms", 200)))
        self._slide(target_x, start_y, target_y, slide_ms, "in")
        self._animate_emoji()
        if peek:
            self._start_dismiss_timer(
                int(animation.get("peek_duration_ms", 1500)), self._dismiss_peek
            )
        else:
            self._type_next()

    def _draw_popup(self, width: int, height: int, peek: bool) -> None:
        canvas = self._canvas
        if canvas is None:
            return
        if peek:
            self._emoji_item = canvas.create_image(
                width // 2, height // 2, image=self._frames[0]
            )
            return

        canvas.create_rectangle(2, 2, width - 2, height - 2, fill=PIXEL["panel_dark"], outline="")
        canvas.create_rectangle(4, 4, width - 4, height - 4, fill=PIXEL["panel"], outline=PIXEL["border"], width=2)
        canvas.create_rectangle(6, 6, width - 6, 25, fill=PIXEL["panel_light"], outline="")
        _, title_photo = self._create_pixel_text(
            canvas, 14, 15, "MINA", 16, PIXEL["text"], anchor="w"
        )
        self._popup_static_photos.append(title_photo)
        self._emoji_item = canvas.create_image(37, 70, image=self._frames[0])

        self._message_size = int(self.config["popup"].get("message_font_size", 16))
        self._message_width = width - 104
        self._message_photo = self._text_renderer.render(
            "", self._message_size, PIXEL["text"], max_width=self._message_width
        )
        self._message_item = canvas.create_image(
            84, 48, anchor="nw", image=self._message_photo
        )
        mute_right_padding = int(
            self.config["popup"].get("mute_header_right_padding", 16)
        )
        minimize_center_x = width - mute_right_padding - 14
        minimize_center_y = 15
        self._minimize_button, self._minimize_item, _ = self._pixel_button(
            canvas,
            minimize_center_x,
            minimize_center_y,
            None,
            self._minimize_dialogue,
            small=True,
        )
        mute_center_x = minimize_center_x - 14 - 8 - 28
        (
            self._mute_button_item,
            self._mute_item,
            self._popup_mute_photo,
        ) = self._pixel_button(
            canvas,
            mute_center_x,
            15,
            "MUTE",
            self._toggle_mute,
            photo_store=self._popup_static_photos,
        )

    def _type_next(self) -> None:
        if self._canvas is None or self._popup is None:
            return
        self._typed = min(len(self._message), self._typed + 1)
        self._message_photo = self._text_renderer.render(
            self._message[: self._typed],
            self._message_size,
            PIXEL["text"],
            max_width=self._message_width,
        )
        self._canvas.itemconfigure(self._message_item, image=self._message_photo)
        if self._typed < len(self._message):
            delay = int(self.config["popup"].get("typewriter_ms", 35))
            self._type_job = self.root.after(max(1, delay), self._type_next)
        else:
            self._stop_sound()
            hold = int(self.config["popup"].get("hold_ms", 3000))
            self._start_dismiss_timer(hold, self._dismiss_dialogue)

    def _start_dismiss_timer(
        self, delay_ms: int, callback: Callable[[], None]
    ) -> None:
        self._cancel_dismiss_timer()
        self._dismiss_timer_remaining_ms = max(0, delay_ms)
        self._dismiss_callback = callback
        self._resume_dismiss_timer()

    def _resume_dismiss_timer(self) -> None:
        if (
            self._popup is None
            or self._popup_hovered
            or self._dismiss_callback is None
            or self._dismiss_timer_job is not None
        ):
            return
        self._dismiss_timer_started_at = time.monotonic()
        self._dismiss_timer_job = self.root.after(
            self._dismiss_timer_remaining_ms, self._run_dismiss_timer
        )

    def _pause_dismiss_timer(self) -> None:
        if self._dismiss_timer_job is None:
            return
        started_at = self._dismiss_timer_started_at
        elapsed_ms = int(
            (time.monotonic() - started_at) * 1000
        ) if started_at is not None else 0
        self._dismiss_timer_remaining_ms = max(
            0, self._dismiss_timer_remaining_ms - elapsed_ms
        )
        self.root.after_cancel(self._dismiss_timer_job)
        self._dismiss_timer_job = None
        self._dismiss_timer_started_at = None

    def _cancel_dismiss_timer(self) -> None:
        if self._dismiss_timer_job is not None:
            try:
                self.root.after_cancel(self._dismiss_timer_job)
            except tk.TclError:
                pass
        self._dismiss_timer_job = None
        self._dismiss_timer_started_at = None
        self._dismiss_timer_remaining_ms = 0
        self._dismiss_callback = None

    def _run_dismiss_timer(self) -> None:
        self._dismiss_timer_job = None
        self._dismiss_timer_started_at = None
        self._dismiss_timer_remaining_ms = 0
        callback = self._dismiss_callback
        self._dismiss_callback = None
        if callback is not None:
            callback()

    def _on_popup_enter(self, _event: tk.Event) -> None:
        self._popup_hovered = True
        self._pause_dismiss_timer()

    def _on_popup_leave(self, _event: tk.Event) -> None:
        if self._hover_check_job is None:
            self._hover_check_job = self.root.after_idle(
                self._resume_dismiss_timer_if_pointer_left
            )

    def _resume_dismiss_timer_if_pointer_left(self) -> None:
        self._hover_check_job = None
        popup = self._popup
        if popup is None:
            return
        pointer_x, pointer_y = popup.winfo_pointerxy()
        inside = (
            popup.winfo_rootx() <= pointer_x < popup.winfo_rootx() + popup.winfo_width()
            and popup.winfo_rooty() <= pointer_y < popup.winfo_rooty() + popup.winfo_height()
        )
        if not inside:
            self._popup_hovered = False
            self._resume_dismiss_timer()

    def _animate_emoji(self) -> None:
        if not self._frames or self._canvas is None or self._popup is None:
            return
        frame_index = self._frame_index
        self._canvas.itemconfigure(self._emoji_item, image=self._frames[frame_index])
        delay = self._frame_durations[frame_index]
        self._frame_index = (frame_index + 1) % len(self._frames)
        self._frame_job = self.root.after(
            delay,
            self._animate_emoji,
        )

    def _animate_companion(self) -> None:
        if not self._companion_frames or not self.root.winfo_exists():
            return
        frame_index = self._companion_frame_index
        self._companion_canvas.itemconfigure(
            self._companion_emoji,
            image=self._companion_frames[frame_index],
        )
        delay = self._companion_frame_durations[frame_index]
        self._companion_frame_index = (frame_index + 1) % len(self._companion_frames)
        self.root.after(delay, self._animate_companion)

    def _slide(self, x: int, start_y: int, target_y: int, duration_ms: int, direction: str) -> None:
        if self._popup is None:
            return
        steps = max(1, duration_ms // 16)
        if direction == "in":
            self._slide_step(x, start_y, target_y, steps, 0)
        else:
            self._slide_step(x, start_y, target_y, steps, 0, dismiss=True)

    def _slide_step(
        self,
        x: int,
        start_y: int,
        target_y: int,
        steps: int,
        step: int,
        dismiss: bool = False,
    ) -> None:
        if self._popup is None or not self._popup.winfo_exists():
            return
        progress = min(1.0, step / steps)
        eased = progress * progress * (3 - 2 * progress)
        y = round(start_y + (target_y - start_y) * eased)
        self._popup.geometry(f"+{x}+{y}")
        if step >= steps:
            if dismiss:
                self._cancel_popup()
            return
        self._animation_job = self.root.after(
            16, lambda: self._slide_step(x, start_y, target_y, steps, step + 1, dismiss)
        )

    def _dismiss_dialogue(self) -> None:
        self._minimize_dialogue()

    def _minimize_dialogue(self) -> None:
        if self._popup is None:
            return
        x = self._popup.winfo_x()
        y = self._popup.winfo_y()
        work_bottom = self._get_work_area()[3]
        self._slide(x, y, work_bottom + 2, 200, "out")

    def _dismiss_peek(self) -> None:
        if self._popup is None:
            return
        x = self._popup.winfo_x()
        y = self._popup.winfo_y()
        work_bottom = self._get_work_area()[3]
        self._slide(x, y, work_bottom + 2, 200, "out")

    def _cancel_popup(self) -> None:
        self._stop_sound()
        for job in (
            self._frame_job,
            self._animation_job,
            self._type_job,
            self._hover_check_job,
        ):
            if job:
                try:
                    self.root.after_cancel(job)
                except tk.TclError:
                    pass
        self._frame_job = self._animation_job = self._type_job = None
        self._hover_check_job = None
        self._cancel_dismiss_timer()
        if self._popup is not None:
            try:
                self._popup.destroy()
            except tk.TclError:
                pass
            if self.on_popup_dismissed is not None:
                self.on_popup_dismissed()
        self._popup = None
        self._canvas = None
        self._popup_static_photos.clear()

    def _get_work_area(self) -> tuple[int, int, int, int]:
        try:
            import ctypes
            from ctypes import wintypes

            rect = wintypes.RECT()
            if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
                return rect.left, rect.top, rect.right, rect.bottom
        except (AttributeError, OSError):
            pass
        return (0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight() - 48)

    def _play_sound(self, sound_path: str) -> None:
        import sys

        from mina.config import PROJECT_ROOT

        if sys.platform != "win32":
            return
        path = Path(sound_path)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        path = path.resolve()
        if not path.is_file():
            self.set_status(f"Sound file not found: {path}", error=True)
            return
        try:
            import winsound

            flags = winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT
            winsound.PlaySound(str(path), flags | winsound.SND_LOOP)
            self._sound_playing = True
        except RuntimeError as error:
            self.set_status(f"Could not play typing sound: {error}", error=True)

    def _stop_sound(self) -> None:
        if not self._sound_playing:
            return
        import sys

        self._sound_playing = False
        if sys.platform != "win32":
            return
        try:
            import winsound

            winsound.PlaySound(None, 0)
        except RuntimeError as error:
            self.set_status(f"Could not stop typing sound: {error}", error=True)
