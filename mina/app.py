from __future__ import annotations

import ctypes
import queue
import random
import sys
import threading
import tkinter as tk
from pathlib import Path

from mina.activity import is_user_active
from mina.config import PROJECT_ROOT, load_config
from mina.emoji_assets import EmojiLibrary, load_mapping
from mina.generator import LocalQwen
from mina.popup import MinaWindows
from mina.scheduler import InterruptionScheduler, ScheduleSettings


class MinaApp:
    def __init__(self, config_path: Path | None = None) -> None:
        if sys.platform != "win32":
            raise OSError("Mina is a Windows desktop companion and requires Windows.")
        self.config = load_config(config_path) if config_path else load_config()
        self.root = tk.Tk()
        self.root.title("Mina")
        self.root.withdraw()
        self._events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._rng = random.Random()
        self._closing = False
        self._model_ready = False
        self._generation_active = False
        self._load_error: str | None = None
        self._last_mood = "Neutral"

        if self.config["ui"].get("register_font", True):
            self._register_private_font()

        emoji_config = self.config["emoji"]
        self.emoji_library = EmojiLibrary(
            PROJECT_ROOT / emoji_config["directory"],
            load_mapping(PROJECT_ROOT / emoji_config["mapping"]),
            scale=int(emoji_config.get("scale", 3)),
        )
        self.windows = MinaWindows(
            self.root,
            self.emoji_library,
            self.config,
            on_mute=self.toggle_mute,
            on_exit=self.close,
            on_popup_dismissed=self._finish_interruption,
        )
        self.scheduler: InterruptionScheduler | None = None
        self._load_model_eagerly()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(100, self._drain_events)
        self.root.after(500, self._poll_activity)

    def _register_private_font(self) -> None:
        font_path = PROJECT_ROOT / self.config["ui"].get("font_path", "")
        if not font_path.is_file():
            return
        try:
            add_font = ctypes.windll.gdi32.AddFontResourceExW
            add_font.argtypes = [ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p]
            add_font.restype = ctypes.c_int
            if add_font(str(font_path), 0x10, None) == 0:
                self._events.put(("status", ("Mojangles font could not be loaded; using fallback.", True)))
        except (AttributeError, OSError) as error:
            self._events.put(("status", (f"Could not register Mojangles: {error}", True)))

    def _load_model_eagerly(self) -> None:
        model_config = self.config["model"]
        model_path = Path(model_config["path"])
        self.generator = LocalQwen(
            model_path,
            max_new_tokens=int(model_config.get("max_new_tokens", 48)),
            cpu_threads=int(model_config.get("cpu_threads", 4)),
        )

        def load_worker() -> None:
            try:
                self.generator.load()
                self._events.put(("model_loaded", None))
            except Exception as error:
                self._events.put(("model_error", f"{type(error).__name__}: {error}"))

        threading.Thread(target=load_worker, name="Mina-model-loader", daemon=True).start()

    def _create_scheduler(self) -> None:
        profile = self.config["profiles"][self.config.get("profile", "development")]
        self.scheduler = InterruptionScheduler(
            settings=ScheduleSettings(
                interval_seconds=tuple(profile["interval_seconds"]),
                cooldown_seconds=tuple(profile["cooldown_seconds"]),
                daily_limit=profile.get("daily_limit"),
                active_idle_limit_seconds=float(self.config["activity"]["active_within_seconds"]),
                poll_interval_ms=int(self.config["activity"]["poll_interval_ms"]),
            ),
            is_active=is_user_active,
            on_interrupt=self._begin_interruption,
        )
        if not self.windows.muted:
            self.scheduler.start()

    def _begin_interruption(self) -> None:
        if self._closing or self.windows.muted or not self._model_ready:
            self._finish_interruption()
            return
        peek_config = self.config["emoji_peek"]
        if self._rng.random() < float(peek_config["chance"]):
            mood = self._choose_mood()
            self.windows.show_peek(mood, str(peek_config.get("corner", "bottom_right")))
            return
        if self._generation_active:
            self._finish_interruption()
            return
        self._generation_active = True
        self.windows.set_status("Thinking of something silly…")

        def generation_worker() -> None:
            try:
                message = self.generator.generate()
                self._events.put(("message", message))
            except Exception as error:
                self._events.put(("generation_error", f"{type(error).__name__}: {error}"))

        threading.Thread(target=generation_worker, name="Mina-thought", daemon=True).start()

    def _choose_mood(self) -> str:
        moods = self.emoji_library.moods
        if len(moods) > 1:
            choices = [mood for mood in moods if mood != self._last_mood]
            self._last_mood = self._rng.choice(choices)
        else:
            self._last_mood = moods[0]
        return self._last_mood

    def _mood_for_message(self, message: str) -> str:
        lower = message.casefold()
        rules = self.config["emoji"].get("keywords", {})
        for keyword, mood in rules.items():
            if keyword.casefold() in lower and mood in self.emoji_library.moods:
                self._last_mood = mood
                return mood
        return self._choose_mood()

    def _drain_events(self) -> None:
        if self._closing:
            return
        while True:
            try:
                event, payload = self._events.get_nowait()
            except queue.Empty:
                break
            if event == "model_loaded":
                self._model_ready = True
                self._create_scheduler()
            elif event == "model_error":
                self._load_error = str(payload)
                self.windows.set_status(f"Model load failed: {payload}", error=True)
                self._model_ready = False
            elif event == "message":
                self._generation_active = False
                self._show_generated_message(str(payload))
            elif event == "generation_error":
                self._generation_active = False
                self.windows.set_status(f"Thought failed: {payload}", error=True)
                self._finish_interruption()
            elif event == "status":
                text, is_error = payload
                self.windows.set_status(str(text), error=bool(is_error))
        self.root.after(100, self._drain_events)

    def _show_generated_message(self, message: str) -> None:
        if self.windows.muted or self._closing:
            self._finish_interruption()
            return
        try:
            if not is_user_active(float(self.config["activity"]["active_within_seconds"])):
                self.windows.set_status("Mina waited; you wandered off.")
                self._finish_interruption()
                return
        except OSError as error:
            self.windows.set_status(f"Activity check failed: {error}", error=True)
            if self.scheduler:
                self.scheduler.stop()
            return

        cleaned = message.strip()
        if not cleaned:
            self.windows.set_status("Mina's thought was mysteriously empty.", error=True)
            self._finish_interruption()
            return
        self.windows.set_status("Mina has a thought!")
        mood = self._mood_for_message(cleaned)
        sound_path = self.config.get("sound", {}).get("typing_wav")
        self.windows.show_dialogue(cleaned, mood, sound_path)

    def _finish_interruption(self) -> None:
        if self.scheduler:
            self.scheduler.finish_interruption()

    def _poll_activity(self) -> None:
        if self._closing:
            return
        interval = int(self.config["activity"]["poll_interval_ms"])
        if self.scheduler:
            try:
                if self.scheduler.poll():
                    self.windows.set_status("Mina has appeared!")
            except OSError as error:
                self.scheduler.stop()
                self.windows.set_status(f"Activity check failed: {error}", error=True)
        self.root.after(interval, self._poll_activity)

    def toggle_mute(self) -> None:
        if not hasattr(self, "windows"):
            return
        muted = not self.windows.muted
        self.windows.set_muted(muted)
        if self.scheduler:
            if muted:
                self.scheduler.stop()
                self.windows.set_status("Mina is quietly napping.")
            elif self._model_ready:
                self.scheduler.start()

    def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        if self.scheduler:
            self.scheduler.stop()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()
