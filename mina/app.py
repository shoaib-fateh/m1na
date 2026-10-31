from __future__ import annotations

import ctypes
import queue
import random
import sqlite3
import sys
import threading
import tkinter as tk
from pathlib import Path

from mina.activity import get_fullscreen_game, get_visible_applications, is_user_active
from mina.config import PROJECT_ROOT, load_config
from mina.dataset import PersonalDataset
from mina.emoji_assets import EmojiLibrary, load_mapping
from mina.generator import LocalQwen
from mina.popup import MinaWindows
from mina.scheduler import InterruptionScheduler, ScheduleSettings
from mina.tray import MinaTrayIcon


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
        self._chat_generation_active = False
        self._manual_chat_active = False
        self._thought_generation_id = 0
        self._gaming_mode = False
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
            on_chat_request=self._send_chat_message,
            on_open_chat=self._open_chat,
            on_popup_dismissed=self._finish_interruption,
        )
        dataset_path = Path(self.config.get("dataset", {}).get("path", "data/mina.sqlite3"))
        if not dataset_path.is_absolute():
            dataset_path = PROJECT_ROOT / dataset_path
        try:
            self.dataset: PersonalDataset | None = PersonalDataset(dataset_path)
        except (OSError, sqlite3.Error) as error:
            self.dataset = None
            self.windows.set_status(f"Local dataset unavailable: {error}", error=True)
        self.scheduler: InterruptionScheduler | None = None
        self._tray_icon: MinaTrayIcon | None = None
        self._start_tray_icon()
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
                for error in self.windows.prepare_sounds():
                    self._events.put(("status", (error, True)))
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
        if (
            not self.windows.muted
            and not self._gaming_mode
            and not self._manual_chat_active
        ):
            self.scheduler.start()

    def _start_tray_icon(self) -> None:
        try:
            self._tray_icon = MinaTrayIcon(
                on_chat=lambda: self._events.put(("tray_chat", None)),
                on_exit=lambda: self._events.put(("tray_exit", None)),
            )
            self._tray_icon.start()
        except (ImportError, OSError, RuntimeError) as error:
            self._tray_icon = None
            self.windows.set_status(f"System tray unavailable: {error}", error=True)

    def _begin_interruption(self) -> None:
        if (
            self._closing
            or self.windows.muted
            or self._gaming_mode
            or not self._model_ready
        ):
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
        generation_id = self._thought_generation_id
        self.windows.set_status("Thinking of something silly…")

        def generation_worker() -> None:
            try:
                applications, application_error = self._get_applications()
                message = self.generator.generate(applications)
                self._events.put(
                    (
                        "message",
                        {
                            "generation_id": generation_id,
                            "text": message,
                            "applications": applications,
                            "application_error": application_error,
                        },
                    )
                )
            except Exception as error:
                self._events.put(
                    (
                        "generation_error",
                        (generation_id, f"{type(error).__name__}: {error}"),
                    )
                )

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
            if event == "tray_chat":
                self._open_chat()
            elif event == "tray_exit":
                self.close()
                return
            elif event == "model_loaded":
                self._model_ready = True
                self._create_scheduler()
            elif event == "model_error":
                self._load_error = str(payload)
                self.windows.set_status(f"Model load failed: {payload}", error=True)
                self._model_ready = False
            elif event == "message":
                result = payload if isinstance(payload, dict) else {"text": str(payload)}
                if (
                    self._gaming_mode
                    or result.get("generation_id") != self._thought_generation_id
                ):
                    continue
                self._generation_active = False
                applications = result.get("applications", [])
                errors = []
                if self.dataset is not None:
                    try:
                        self.dataset.add_message(
                            "thought", "assistant", str(result["text"]), applications
                        )
                    except (OSError, sqlite3.Error, ValueError) as error:
                        errors.append(f"Could not save Mina's thought locally: {error}")
                else:
                    errors.append("Could not save Mina's thought locally: dataset unavailable.")
                self._show_generated_message(str(result["text"]))
                application_error = result.get("application_error")
                if application_error:
                    errors.append(f"Application detection failed: {application_error}")
                if errors:
                    self.windows.set_status("; ".join(errors), error=True)
            elif event == "generation_error":
                if isinstance(payload, tuple):
                    generation_id, error_text = payload
                    if generation_id != self._thought_generation_id:
                        continue
                else:
                    error_text = payload
                self._generation_active = False
                self.windows.set_status(f"Thought failed: {error_text}", error=True)
                self._finish_interruption()
            elif event == "chat_reply":
                self._chat_generation_active = False
                message, applications, application_error = payload
                errors = []
                if self.dataset is not None:
                    try:
                        self.dataset.add_message("chat", "assistant", message, applications)
                    except (OSError, sqlite3.Error, ValueError) as error:
                        errors.append(f"Could not save Mina's reply locally: {error}")
                self.windows.show_dialogue(message, self._mood_for_message(message))
                if application_error:
                    errors.append(f"Application detection failed: {application_error}")
                if errors:
                    self.windows.set_status("; ".join(errors), error=True)
            elif event == "chat_error":
                self._chat_generation_active = False
                self.windows.set_status(f"Chat failed: {payload}", error=True)
                self.windows.show_chat()
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
        self.windows.show_dialogue(cleaned, mood)

    def _get_applications(self) -> tuple[list[str], str | None]:
        settings = self.config.get("application_awareness", {})
        if not settings.get("enabled", True):
            return [], None
        try:
            return (
                get_visible_applications(int(settings.get("max_applications", 5))),
                None,
            )
        except OSError as error:
            return [], str(error)

    def _open_chat(self) -> None:
        if self._chat_generation_active:
            self.windows.set_status("Mina is still replying to your last message.")
            return
        self._manual_chat_active = True
        if self.scheduler:
            self.scheduler.stop()
            self.scheduler.cancel_interruption()
        if self._generation_active:
            self._thought_generation_id += 1
            self._generation_active = False
        self.windows.show_chat()

    def _send_chat_message(self, message: str) -> None:
        cleaned = message.strip()
        if not cleaned:
            return
        if self._chat_generation_active:
            self.windows.set_status("Mina is still replying to the last message.")
            return
        if not self._model_ready:
            self.windows.set_status("Mina's local model is not ready yet.", error=True)
            return
        if self.dataset is None:
            self.windows.set_status("Chat unavailable: local dataset could not be opened.", error=True)
            return

        self._chat_generation_active = True
        self.windows.hide_popup_for_chat()

        def chat_worker() -> None:
            try:
                applications, application_error = self._get_applications()
                self.dataset.add_message("chat", "user", cleaned, applications)
                history = self.dataset.recent_chat(
                    int(self.config.get("chat", {}).get("memory_messages", 10))
                )
                reply = self.generator.generate_chat(history, applications)
                self._events.put(
                    ("chat_reply", (reply, applications, application_error))
                )
            except Exception as error:
                self._events.put(("chat_error", f"{type(error).__name__}: {error}"))

        threading.Thread(target=chat_worker, name="Mina-chat", daemon=True).start()

    def _finish_interruption(self) -> None:
        if self.scheduler:
            self.scheduler.finish_interruption()
        if self._manual_chat_active and not self._chat_generation_active:
            self._manual_chat_active = False
            if (
                self.scheduler
                and not self.windows.muted
                and not self._gaming_mode
                and self._model_ready
            ):
                self.scheduler.start()

    def _poll_activity(self) -> None:
        if self._closing:
            return
        gaming_settings = self.config.get("gaming_mode", {})
        interval = int(
            gaming_settings.get(
                "poll_interval_ms",
                self.config["activity"]["poll_interval_ms"],
            )
        )
        if gaming_settings.get("enabled", True):
            try:
                fullscreen_app = get_fullscreen_game(
                    set(gaming_settings.get("excluded_processes", []))
                )
                self._set_gaming_mode(fullscreen_app is not None, fullscreen_app)
            except OSError as error:
                self.windows.set_status(
                    f"Gaming mode detection failed: {error}", error=True
                )
        if self.scheduler:
            if self._gaming_mode or self._manual_chat_active:
                self.root.after(interval, self._poll_activity)
                return
            try:
                if self.scheduler.poll():
                    self.windows.set_status("Mina has appeared!")
            except OSError as error:
                self.scheduler.stop()
                self.windows.set_status(f"Activity check failed: {error}", error=True)
        self.root.after(interval, self._poll_activity)

    def _set_gaming_mode(self, active: bool, process_name: str | None = None) -> None:
        if self._gaming_mode == active:
            return
        self._gaming_mode = active
        if active:
            self._thought_generation_id += 1
            self._generation_active = False
            if self.scheduler:
                self.scheduler.stop()
            self.windows.set_gaming_mode(True)
            self.windows.set_status(
                f"Gaming Mode: {process_name or 'fullscreen app'}"
            )
            return

        self.windows.set_gaming_mode(False)
        if (
            self.scheduler
            and not self.windows.muted
            and not self._manual_chat_active
            and self._model_ready
        ):
            self.scheduler.cooldown_until = 0.0
            self.scheduler.start()
        self.windows.set_status("Gaming Mode off", transient_ms=3000)

    def toggle_mute(self) -> None:
        if not hasattr(self, "windows"):
            return
        muted = not self.windows.muted
        self.windows.set_muted(muted)
        if self.scheduler:
            if muted:
                self.scheduler.stop()
                self.windows.set_status("Mina is quietly napping.")
            elif (
                self._model_ready
                and not self._gaming_mode
                and not self._manual_chat_active
            ):
                self.scheduler.start()

    def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        if self.scheduler:
            self.scheduler.stop()
        if self._tray_icon is not None:
            try:
                self._tray_icon.stop()
            except (OSError, RuntimeError) as error:
                self.windows.set_status(
                    f"Could not stop system tray icon: {error}", error=True
                )
            self._tray_icon = None
        self.windows.close()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()
