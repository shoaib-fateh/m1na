# Mina

Mina is a tiny, silly Windows desktop creature. She occasionally displays a short absurd thought near the center of the screen or peeks from a screen corner as an animated pixel emoji. She can also chat using the local Qwen model. She does not record keyboard input or use cloud services.

## Requirements

- Windows 10/11 and Python 3.12
- The existing local model at `D:\DAVYAN\models\Qwen2.5-0.5B-Instruct`
- Python packages in `requirements.txt` (PyTorch, Transformers, Pillow)

No model is downloaded by Mina. `local_files_only=True` is used for model and tokenizer loading.

## Run

Open PowerShell in this folder:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r requirements.txt
python mina.py
```

If a compatible CPU build of PyTorch is already installed, skip the first `pip install` command. After dependencies are installed, Mina immediately loads the configured local model on CPU in a background thread. Tkinter remains responsive while it loads and generates; errors appear in the status text.

For everyday use, install Mina as a per-user Windows logon task from PowerShell:

```powershell
.\install_mina_task.ps1
```

The task starts Mina in the logged-in desktop session (required for Tkinter and the notification-area icon), uses the project virtual environment when present, ignores overlapping task launches, and retries a crashed process. It does not run elevated or as a Windows service. Remove it with `.\uninstall_mina_task.ps1`. The launcher also prevents a second Mina process if the app is started manually while the task is already running.
If Mina fails before its status panel can initialize, the launcher records the traceback in `data/mina.log` (rotated at 1 MB, retaining three backups).

## Configuration

Edit `config.json`:

- `model.path`: local model directory; default is the existing Qwen model.
- `profile`: the production `normal` schedule.
- `profiles.normal`: random 30–60 minute intervals and 30–45 minute cooldowns after each popup disappears, capped at 8/day.
- `scheduler.enabled`: enable or disable spontaneous interruption scheduling.
- `scheduler.state_path`: local SQLite file used to preserve the next due time, cooldown, and daily count across Mina restarts. An overdue interruption is rescheduled instead of being replayed immediately after restart.
- `activity.active_within_seconds`: recent-input window. Mina checks only Windows' last-input timestamp and never reads or stores keys or typed text.
- `time_behavior.enabled`: enable or disable the independent local time-based trigger monitor.
- `time_behavior.poll_interval_ms`: interval for checking wall-clock time, Windows uptime, and idle duration (30 seconds by default).
- `time_behavior.path`: separate local SQLite file for trigger cooldowns, fired-event windows, last-speaking time, and pending randomized events.
- `time_behavior.cooldown_seconds` and `time_behavior.delay_seconds`: randomized global cooldown and pre-generation delay ranges. Both use wall-clock timestamps so delays survive Mina restarts and Windows sleep/hibernation.
- `time_behavior.rules`: ordered event rules with configurable `priority`; higher priorities are considered first. Built-in rule types cover startup, uptime milestones, time ranges, idle/no-interaction thresholds, new days, time-period changes, and time since Mina last spoke. The startup rule fires once when Mina first observes a Windows boot. Inactivity rules can share an `exclusive_group` to avoid duplicate idle triggers during one uninterrupted idle period.
- Time-trigger events run through Mina's local Qwen personality prompt. Mina can decide to say a short line or return `[SILENT]`; only an actual displayed line updates the persisted last-speaking time. Time, uptime, idle duration, and interaction timestamps remain local and are not sent to any external service.
- `application_awareness.enabled`: enable or disable lightweight local detection of up to five visible applications. Detection uses foreground/z-order windows and executable names only; it does not read window titles or contents, take screenshots, or inspect input.
- `application_awareness.max_applications`: maximum number of visible applications to consider (1–5).
- `gaming_mode.enabled`: automatically pause Mina when the foreground window fills its monitor. Windows does not expose a universal game-identification signal, so Mina uses a lightweight fullscreen-foreground heuristic; known non-game apps can be added to `gaming_mode.excluded_processes`. Detection uses only window bounds and the executable name. No screenshots or game contents are inspected. While active, scheduled thoughts and peeks are discarded, popups and sounds stop, and the scheduler resumes with a fresh interval after fullscreen focus ends.
- `gaming_mode.poll_interval_ms`: local fullscreen check interval.
- `chat.memory_messages`: number of latest chat messages included in the next Qwen prompt (default 10). Older messages remain in the local dataset but are not added to active model context.
- `dataset.path`: local SQLite dataset path. It records timestamps, message roles and text, message type, and detected application names. This archive is separate from active chat memory and is never sent outside the computer.
- `emoji_peek.chance`: chance to show an emoji-only peek instead of generating dialogue. A peek lasts 8 seconds and consumes the same interruption/cooldown slot, but uses no model generation or typing sound. Hover over the emoji to reveal its Chat button.
- `sound.dialogue_mode`: choose `animalese` (default), `typing` (keyboard sound as an alternative), or `silent`. Only the selected dialogue mode plays during Mina's text; Animalese disables the keyboard typing loop.
- `sound.animalese`: independently enable the retro dialogue sound, configure its local WAV file, volume (0–100), and playback speed (0.25–4.0). By default Mina loops the supplied `assets/sounds/dialogue_blip.wav` at natural 1.0× speed while text is being revealed, then stops it as soon as the typewriter finishes.
- `sound.typing`: configure the separate looping keyboard WAV alternative with its local `path`, `enabled`, and `volume` (0–100).
- `sound.click`: optionally play a configured local WAV when sending a chat message; disabled by default and has its own volume.
- `ui.font_path` and `ui.persian_fallback`: Mojangles and Persian-capable fallback font paths/family. Mina's Message/Chat buttons open a pixel-styled message input directly beneath the current popup. The chat text and Send label use Mina's pixel-font renderer while the editable field preserves normal keyboard editing and selection. The popup stays visible while you type; after sending, it disappears while Qwen responds, then Mina shows her reply in a new, pixel-art dialogue popup. Popup height grows to fit wrapped text, preventing long messages from overlapping the frame. Hover over the animated Mina GIF or an emoji-only peek to reveal a Chat shortcut. Manual chat pauses and cancels pending interruptions until the reply popup closes. Mina stays available from the system tray; choose “Chat with Mina” to start a conversation or “Exit Mina” to quit. Spontaneous thoughts use the pixel-art typewriter near screen center, separate from the corner-peek animation. Model and runtime errors are reported in Mina's status area.

Mina's popup animation, typewriter speed, size, hold time, and mute-button header padding are configurable too; dialogue stays for 8 seconds after typing finishes by default. The auto-hide timer pauses while the pointer is over a message or emoji popup, then resumes with the remaining time when the pointer leaves. Its minimize control slides the dialogue away while leaving Mina running. Emoji-only peeks show just the animated GIF until you hover it to reveal the Chat button. Emoji mappings live in `assets/emojis/moods.json`, and the ready-to-use transparent GIFs live in `assets/emojis/animations/`. Pillow loads each GIF's frames and frame durations directly; scaling uses nearest-neighbor resampling to preserve sharp pixels. No PNG emoji assets are used. Text is rasterized directly at pixel size with Mojangles; unsupported punctuation uses the configured system fallback. Add GIF animations by updating the mood mapping, not application code.

The supplied emoji pack is CC0 1.0. Mojangles is provided for local personal use alongside its readme and license; its license is non-commercial and does not permit redistribution.

## Notes

- Mina is designed to run on Windows. Activity detection uses `GetLastInputInfo` through `ctypes`.
- `pystray` provides Mina's persistent Windows notification-area icon and manual chat/exit menu.
- Model loading and generation use worker threads; Tkinter animations use scheduled callbacks.
- The Windows logon task launches only in the interactive user session; its restart policy handles process crashes. A per-session mutex prevents duplicate Mina windows and model loads.
- Spontaneous interruption scheduling remains in Mina's Tk event loop, checks activity on its configured timer, and stores its daily limit/cooldown/next due state locally in SQLite. This is separate from the independent time-behavior trigger database.
- Time-based trigger evaluation is lightweight and runs independently of model loading; only due event generation uses a worker thread. Windows uptime comes from `GetTickCount64`, while persisted trigger delays and cooldowns use local wall-clock timestamps.
- Sound playback is asynchronous. Sound volume and playback speed are prepared locally from uncompressed PCM WAV data in the background; adjusted temporary files are removed when Mina exits. At most one sound mode is active at a time.
- If an emoji sheet or configured sound file is unavailable, Mina displays an explicit status error.
- The included typing effect is derived from the user-provided retro-terminal key-clacks WAV. The full clip is looped while text is being revealed and stops when typing completes or the popup is dismissed.
- To exit Mina, use the `X` control on her companion panel. The dialogue's underscore control minimizes only that message.
