from __future__ import annotations

import os
import random
import time
import tkinter as tk
from collections.abc import Callable
from pathlib import Path

from mina.emoji_assets import EmojiLibrary
from mina.pixel_text import PixelTextRenderer
from mina.sound import AnimaleseBlips, SoundPlayer


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
        on_chat_request: Callable[[str], None],
        on_open_chat: Callable[[], None],
        on_popup_dismissed: Callable[[], None] | None = None,
    ) -> None:
        self.root = root
        self.emoji_library = emoji_library
        self.config = config
        self.on_mute = on_mute
        self.on_exit = on_exit
        self.on_chat_request = on_chat_request
        self.on_open_chat = on_open_chat
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
        self._sound_mode: str | None = None
        self._sound_player = SoundPlayer()
        animalese_files = config.get("sound", {}).get("animalese", {}).get("files", [])
        self._animalese_blips = AnimaleseBlips(
            [self._resolve_sound_path(path) for path in animalese_files],
            random.Random(),
        ) if animalese_files else None
        self._dialogue_sound_started = False
        self._reported_sound_errors: set[str] = set()
        self._gaming_mode = False
        self._status_clear_job: str | None = None
        self._hover_chat_items: tuple[int, ...] | None = None
        self._chat_input_frame: tk.Frame | None = None
        self._chat_entry_slot: tk.Frame | None = None
        self._chat_entry: tk.Entry | None = None
        self._chat_entry_canvas: tk.Canvas | None = None
        self._chat_entry_photo: object | None = None
        self._chat_send_button: tk.Button | None = None
        self._chat_send_photo: tk.PhotoImage | None = None
        self._chat_input_open = False
        self._frames = []
        self._frame_durations = []
        self._frame_index = 0
        self._companion_frames = []
        self._companion_frame_durations = []
        self._companion_frame_index = 0
        self._companion_animation_job: str | None = None
        self._companion_static_photos: list[tk.PhotoImage] = []
        self._popup_static_photos: list[tk.PhotoImage] = []
        self._companion_mute_photo: tk.PhotoImage | None = None
        self._popup_mute_photo: tk.PhotoImage | None = None
        self._message = ""
        self._typed = 0
        self._popup_kind = ""
        self._current_mood = "Neutral"
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

    @property
    def popup_active(self) -> bool:
        return self._popup is not None

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
        initially_hidden: bool = False,
    ) -> tuple[int, int, tk.PhotoImage | None]:
        width = 28 if small else max(56, len(label or "") * 8 + 12)
        x1, y1 = x - width // 2, y - 10
        if not initially_hidden:
            canvas.create_rectangle(
                x1 + 2,
                y1 + 2,
                x1 + width + 2,
                y1 + 20,
                fill=PIXEL["border"],
                outline="",
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
        if initially_hidden:
            for item in (button, text):
                canvas.itemconfigure(item, state="hidden")
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
        self._show(mood, None, message=message)

    def show_peek(self, mood: str, corner: str = "bottom_right") -> None:
        self._show(mood, None, corner=corner, peek=True)

    def show_chat(self) -> None:
        if self._popup is None or self._popup_kind != "dialogue":
            mood = self._current_mood or "Neutral"
            self._cancel_popup(notify=False)
            self.show_dialogue("Hey! What's up?", mood)
        if self._popup is None:
            return
        if self._chat_input_frame is not None:
            self._popup.deiconify()
            self._popup.lift()
            self._chat_entry.focus_set()
            return
        self._pause_dismiss_timer()
        self._chat_input_open = True
        self._chat_input_frame = tk.Frame(
            self._popup,
            bg=PIXEL["panel_dark"],
            padx=6,
            pady=5,
            highlightthickness=2,
            highlightbackground=PIXEL["border"],
        )
        self._chat_input_frame.pack(fill="x", padx=4, pady=(0, 4))
        self._chat_send_photo = self._text_renderer.render(
            "SEND", 12, PIXEL["text"]
        )
        self._chat_entry_slot = tk.Frame(
            self._chat_input_frame,
            bg=PIXEL["panel_dark"],
        )
        self._chat_entry_slot.pack(side="left", fill="x", expand=True)
        self._chat_entry = tk.Entry(
            self._chat_entry_slot,
            bg=PIXEL["panel_dark"],
            fg=PIXEL["panel_dark"],
            insertbackground=PIXEL["panel_dark"],
            selectbackground=PIXEL["panel_dark"],
            selectforeground=PIXEL["panel_dark"],
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=PIXEL["panel_light"],
            highlightcolor=PIXEL["accent"],
            font=("Segoe UI", 11),
            insertwidth=0,
        )
        self._chat_entry.pack(fill="both", expand=True, ipady=6)
        self._chat_entry.bind("<Return>", self._submit_chat)
        self._chat_entry.bind("<KeyRelease>", self._refresh_chat_entry_display, add="+")
        self._chat_entry.bind("<FocusIn>", self._refresh_chat_entry_display, add="+")
        self._chat_entry.bind("<FocusOut>", self._refresh_chat_entry_display, add="+")
        self._chat_entry_canvas = tk.Canvas(
            self._chat_entry_slot,
            bg=PIXEL["panel_dark"],
            highlightthickness=0,
            bd=0,
            cursor="xterm",
        )
        self._chat_entry_canvas.place(relx=0, rely=0, relwidth=1, relheight=1)
        tk.Misc.tkraise(self._chat_entry_canvas)
        self._chat_entry_canvas.bind("<Button-1>", self._focus_chat_entry)
        self._chat_entry_canvas.bind("<Configure>", self._refresh_chat_entry_display)
        self._chat_send_button = tk.Button(
            self._chat_input_frame,
            image=self._chat_send_photo,
            command=self._submit_chat,
            bg=PIXEL["panel"],
            fg=PIXEL["text"],
            activebackground=PIXEL["panel_light"],
            relief="flat",
            bd=2,
            highlightthickness=1,
            highlightbackground=PIXEL["border"],
            padx=10,
            pady=5,
        )
        self._chat_send_button.pack(side="right", padx=(6, 0))
        if self._animation_job is not None:
            try:
                self.root.after_cancel(self._animation_job)
            except tk.TclError:
                pass
            self._animation_job = None
        self._popup.update_idletasks()
        width = (
            self._canvas.winfo_reqwidth()
            if self._canvas is not None
            else self._popup.winfo_width()
        )
        height = self._popup.winfo_reqheight()
        self._popup.geometry(f"{width}x{height}")
        self._popup.update_idletasks()
        self._recenter_popup()
        self._popup.deiconify()
        self._popup.lift()
        self._chat_entry.focus_set()
        self._refresh_chat_entry_display()

    def _focus_chat_entry(self, event: tk.Event) -> None:
        if self._chat_entry is None:
            return
        self._chat_entry.focus_set()
        self._chat_entry.icursor(self._chat_entry.index(f"@{event.x}"))
        self._refresh_chat_entry_display()

    def _refresh_chat_entry_display(self, _event: tk.Event | None = None) -> None:
        canvas = self._chat_entry_canvas
        entry = self._chat_entry
        if canvas is None or entry is None:
            return
        canvas.delete("all")
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width < 2 or height < 2:
            return
        text = entry.get()
        cursor_index = entry.index(tk.INSERT)
        cursor_photo = self._text_renderer.render(
            text[:cursor_index], 12, PIXEL["text"]
        )
        cursor_x = cursor_photo.width()
        scroll_x = max(0, cursor_x - (width - 10))
        canvas.create_rectangle(
            0, 0, width - 1, height - 1,
            fill=PIXEL["panel_dark"],
            outline=PIXEL["accent"] if entry == entry.focus_get() else PIXEL["panel_light"],
        )
        selected_start = selected_end = None
        try:
            selected_start = entry.index(tk.SEL_FIRST)
            selected_end = entry.index(tk.SEL_LAST)
        except tk.TclError:
            pass

        text_y = max(1, (height - 16) // 2)
        if selected_start is not None and selected_end is not None:
            before = text[:selected_start]
            selected = text[selected_start:selected_end]
            after = text[selected_end:]
            before_photo = self._text_renderer.render(before, 12, PIXEL["text"])
            selected_photo = self._text_renderer.render(
                selected, 12, PIXEL["panel_dark"]
            )
            after_photo = self._text_renderer.render(after, 12, PIXEL["text"])
            x = 5 - scroll_x
            canvas.create_image(x, text_y, image=before_photo, anchor="nw")
            x += before_photo.width()
            canvas.create_rectangle(
                x, text_y, x + selected_photo.width(), text_y + selected_photo.height(),
                fill=PIXEL["accent"],
                outline="",
            )
            canvas.create_image(x, text_y, image=selected_photo, anchor="nw")
            x += selected_photo.width()
            canvas.create_image(x, text_y, image=after_photo, anchor="nw")
            self._chat_entry_photo = (before_photo, selected_photo, after_photo)
        else:
            text_photo = self._text_renderer.render(text, 12, PIXEL["text"])
            canvas.create_image(5 - scroll_x, text_y, image=text_photo, anchor="nw")
            self._chat_entry_photo = text_photo

        if entry == entry.focus_get() and selected_start is None:
            canvas.create_rectangle(
                5 + cursor_x - scroll_x,
                text_y,
                7 + cursor_x - scroll_x,
                min(height - 2, text_y + 15),
                fill=PIXEL["text"],
                outline="",
            )

    def _submit_chat(self, _event: tk.Event | None = None) -> str:
        if self._chat_entry is None:
            return "break"
        message = self._chat_entry.get()
        if message.strip():
            self.on_chat_request(message)
        return "break"

    def hide_popup_for_chat(self) -> None:
        if self._popup is None:
            return
        self._chat_input_open = False
        self._cancel_popup()
        self._play_click_sound()

    def set_gaming_mode(self, active: bool) -> None:
        if self._gaming_mode == active:
            return
        self._gaming_mode = active
        self._stop_sound()
        if active:
            self._set_hover_chat_visible(False)
            self._cancel_popup()
            if self._companion_animation_job is not None:
                try:
                    self.root.after_cancel(self._companion_animation_job)
                except tk.TclError:
                    pass
                self._companion_animation_job = None
            self._companion_canvas.itemconfigure(self._companion_emoji, state="hidden")
        else:
            self._companion_canvas.itemconfigure(self._companion_emoji, state="normal")
            self._animate_companion()

    def close(self) -> None:
        self._stop_sound()
        self._sound_player.close()

    def prepare_sounds(self) -> list[str]:
        errors = []
        sound_config = self.config.get("sound", {})
        mode = self._dialogue_mode()
        if mode == "typing":
            settings = sound_config.get("typing", {})
            path = settings.get("path", sound_config.get("typing_wav"))
            if settings.get("enabled", True) and path:
                try:
                    self._sound_player.prepare(
                        self._resolve_sound_path(path),
                        int(settings.get("volume", 100)),
                    )
                except (OSError, ValueError) as error:
                    self._reported_sound_errors.add(str(self._resolve_sound_path(path)))
                    errors.append(f"Could not prepare typing sound: {error}")
        elif mode == "animalese":
            settings = sound_config.get("animalese", {})
            if settings.get("enabled", True):
                speed = float(settings.get("playback_speed", 2.5))
                for path in settings.get("files", []):
                    try:
                        self._sound_player.prepare(
                            self._resolve_sound_path(path),
                            int(settings.get("volume", 100)),
                            speed,
                        )
                    except (OSError, ValueError) as error:
                        self._reported_sound_errors.add(
                            str(self._resolve_sound_path(path))
                        )
                        errors.append(f"Could not prepare Animalese blip: {error}")
        click = sound_config.get("click", {})
        if click.get("enabled", False) and click.get("path"):
            try:
                self._sound_player.prepare(
                    self._resolve_sound_path(click["path"]),
                    int(click.get("volume", 100)),
                )
            except (OSError, ValueError) as error:
                self._reported_sound_errors.add(
                    str(self._resolve_sound_path(click["path"]))
                )
                errors.append(f"Could not prepare click sound: {error}")
        return errors

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
        self._current_mood = mood
        self._popup_hovered = False
        self._popup_static_photos.clear()
        self._message = message
        self._dialogue_sound_started = False
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
            width = max(frame.width() + 8, 68)
            height = frame.height() + 32
        else:
            width, height = popup_config.get("size", [420, 142])
            height = self._dialogue_popup_height(message, width, height)
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
        self._canvas.bind("<Motion>", self._on_popup_motion)

        work_left, work_top, work_right, work_bottom = self._get_work_area()
        if peek:
            target_x = self._popup_target_x(width, work_left, work_right, corner, True)
            target_y = work_bottom - height - 4
        else:
            target_x = work_left + (work_right - work_left - width) // 2
            target_y = work_top + (work_bottom - work_top - height) // 2
        start_y = work_bottom + 2
        popup.geometry(f"{width}x{height}+{target_x}+{start_y}")

        if not peek:
            mode = self._dialogue_mode()
            if mode == "typing":
                self._play_typing_sound()

        animation = popup_config.get("animation", {})
        slide_ms = max(1, int(animation.get("slide_ms", 200)))
        self._slide(target_x, start_y, target_y, slide_ms, "in")
        self._animate_emoji()
        if peek:
            self._start_dismiss_timer(
                int(animation.get("peek_duration_ms", 8000)), self._dismiss_peek
            )
        else:
            self._type_next()

    def _dialogue_popup_height(
        self, message: str, width: int, minimum_height: int
    ) -> int:
        message_size = int(self.config["popup"].get("message_font_size", 16))
        message_width = width - 104
        preview = self._text_renderer.render(
            message, message_size, PIXEL["text"], max_width=message_width
        )
        return max(minimum_height, 60 + preview.height())

    def _recenter_popup(self) -> None:
        popup = self._popup
        if popup is None:
            return
        work_left, work_top, work_right, work_bottom = self._get_work_area()
        width = popup.winfo_width()
        height = popup.winfo_height()
        x = work_left + (work_right - work_left - width) // 2
        y = max(work_top + 8, work_top + (work_bottom - work_top - height) // 2)
        popup.geometry(f"+{x}+{y}")

    @staticmethod
    def _popup_target_x(
        width: int,
        work_left: int,
        work_right: int,
        corner: str,
        peek: bool,
    ) -> int:
        if peek:
            return work_left + (work_right - work_left - width) // 2
        if corner.endswith("left"):
            return work_left + 12
        return work_right - width - 12

    def _draw_popup(self, width: int, height: int, peek: bool) -> None:
        canvas = self._canvas
        if canvas is None:
            return
        if peek:
            emoji_y = (height - 28) // 2
            self._emoji_item = canvas.create_image(
                width // 2, emoji_y, image=self._frames[0]
            )
            frame = self._frames[0]
            self._peek_emoji_bounds = (
                (width - frame.width()) // 2,
                emoji_y - frame.height() // 2,
                (width + frame.width()) // 2,
                emoji_y + frame.height() // 2,
            )
            self._peek_chat_bounds = (
                width // 2 - 30,
                self._peek_emoji_bounds[3] - 2,
                width // 2 + 30,
                height - 2,
            )
            hover_button, hover_label, _ = self._pixel_button(
                canvas,
                width // 2,
                height - 14,
                "CHAT",
                self.on_open_chat,
                photo_store=self._popup_static_photos,
                initially_hidden=True,
            )
            self._hover_chat_items = (hover_button, hover_label)
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
        self._pixel_button(
            canvas,
            mute_center_x - 70,
            15,
            "MESSAGE",
            self.on_open_chat,
            photo_store=self._popup_static_photos,
        )
        hover_button, hover_label, _ = self._pixel_button(
            canvas,
            37,
            110,
            "CHAT",
            self.on_open_chat,
            photo_store=self._popup_static_photos,
            initially_hidden=True,
        )
        self._hover_chat_items = (hover_button, hover_label)

    def _on_popup_motion(self, event: tk.Event) -> None:
        if self._canvas is None or self._hover_chat_items is None:
            return
        if self._popup_kind == "peek":
            left, top, right, bottom = self._peek_emoji_bounds
            over_emoji = left <= event.x <= right and top <= event.y <= bottom
            left, top, right, bottom = self._peek_chat_bounds
            over_button = left <= event.x <= right and top <= event.y <= bottom
            self._set_hover_chat_visible(over_emoji or over_button)
            return
        near_emoji = 8 <= event.x <= 66 and 38 <= event.y <= 128
        self._set_hover_chat_visible(near_emoji)

    def _set_hover_chat_visible(self, visible: bool) -> None:
        if self._canvas is None or self._hover_chat_items is None:
            return
        state = "normal" if visible else "hidden"
        for item in self._hover_chat_items:
            self._canvas.itemconfigure(item, state=state)

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
        self._play_dialogue_character(self._message[self._typed - 1])
        if self._typed < len(self._message):
            delay = self._dialogue_character_delay()
            self._type_job = self.root.after(max(1, delay), self._type_next)
        else:
            if self._sound_mode in {"typing", "animalese"}:
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
            or self._chat_input_open
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
            self._set_hover_chat_visible(False)
            self._resume_dismiss_timer()

    def _animate_emoji(self) -> None:
        if not self._frames or self._canvas is None or self._popup is None:
            return
        frame_index = self._frame_index
        self._canvas.itemconfigure(self._emoji_item, image=self._frames[frame_index])
        delay = self._frame_durations[frame_index]
        self._frame_index = (frame_index + 1) % len(self._frames)
        self._frame_job = self.root.after(delay, self._animate_emoji)

    def _animate_companion(self) -> None:
        if self._gaming_mode or not self._companion_frames or not self.root.winfo_exists():
            return
        frame_index = self._companion_frame_index
        self._companion_canvas.itemconfigure(
            self._companion_emoji,
            image=self._companion_frames[frame_index],
        )
        delay = self._companion_frame_durations[frame_index]
        self._companion_frame_index = (frame_index + 1) % len(self._companion_frames)
        self._companion_animation_job = self.root.after(
            delay, self._animate_companion
        )

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
            self._animation_job = None
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

    def _cancel_popup(self, notify: bool = True) -> None:
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
            if notify and self.on_popup_dismissed is not None:
                self.on_popup_dismissed()
        self._popup = None
        self._canvas = None
        self._hover_chat_items = None
        self._chat_input_frame = None
        self._chat_entry_slot = None
        self._chat_entry = None
        self._chat_entry_canvas = None
        self._chat_entry_photo = None
        self._chat_send_button = None
        self._chat_send_photo = None
        self._chat_input_open = False
        self._popup_kind = ""
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

    def _play_sound(
        self,
        sound_path: str,
        mode: str = "typing",
        volume: int = 100,
        loop: bool = True,
        speed: float = 1.0,
    ) -> None:
        import sys

        if sys.platform != "win32":
            return
        path = self._resolve_sound_path(sound_path)
        error_key = str(path.resolve())
        if error_key in self._reported_sound_errors:
            return
        try:
            self._sound_player.play(mode, path, volume, loop, speed)
            self._sound_playing = True
            self._sound_mode = mode
        except (OSError, RuntimeError, ValueError) as error:
            if error_key not in self._reported_sound_errors:
                self._reported_sound_errors.add(error_key)
                self.set_status(f"Could not play {mode} sound: {error}", error=True)

    @staticmethod
    def _resolve_sound_path(sound_path: str) -> Path:
        from mina.config import PROJECT_ROOT

        path = Path(sound_path)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path.resolve()

    def _stop_sound(self) -> None:
        self._sound_playing = False
        self._sound_mode = None
        if hasattr(self, "_sound_player"):
            try:
                self._sound_player.stop()
            except RuntimeError as error:
                self.set_status(f"Could not stop sound: {error}", error=True)
            return
        import sys

        if sys.platform == "win32":
            import winsound

            winsound.PlaySound(None, 0)

    def _dialogue_mode(self) -> str:
        return self.config.get("sound", {}).get("dialogue_mode", "typing")

    def _dialogue_character_delay(self) -> int:
        if self._dialogue_mode() == "animalese":
            configured = int(
                self.config.get("sound", {})
                .get("animalese", {})
                .get("character_interval_ms", 70)
            )
            return max(1, configured)
        return max(1, int(self.config["popup"].get("typewriter_ms", 35)))

    def _play_dialogue_character(self, character: str) -> None:
        if self._gaming_mode or not character.isalnum():
            return
        mode = self._dialogue_mode()
        if mode != "animalese":
            return
        settings = self.config.get("sound", {}).get("animalese", {})
        if not settings.get("enabled", True) or self._animalese_blips is None:
            return
        if self._dialogue_sound_started:
            return
        self._dialogue_sound_started = True
        self._play_sound(
            str(self._animalese_blips.next_path()),
            mode="animalese",
            volume=int(settings.get("volume", 100)),
            loop=True,
            speed=float(settings.get("playback_speed", 2.5)),
        )

    def _play_typing_sound(self) -> None:
        self._stop_sound()
        if self._dialogue_mode() != "typing":
            return
        settings = self.config.get("sound", {}).get("typing", {})
        if not settings.get("enabled", True):
            return
        path = settings.get(
            "path", self.config.get("sound", {}).get("typing_wav")
        )
        if path:
            self._play_sound(
                path,
                mode="typing",
                volume=int(settings.get("volume", 100)),
                loop=True,
            )

    def _play_click_sound(self) -> None:
        if self._gaming_mode:
            return
        settings = self.config.get("sound", {}).get("click", {})
        if not settings.get("enabled", False):
            return
        path = settings.get("path")
        if path:
            self._play_sound(
                path,
                mode="click",
                volume=int(settings.get("volume", 100)),
                loop=False,
            )
