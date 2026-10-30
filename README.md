# Mina

Mina is a tiny, silly Windows desktop creature. She occasionally displays a short absurd thought or peeks from a screen corner as an animated pixel emoji. She uses a local Qwen model only; she does not record keyboard input or use cloud services.

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

If a compatible CPU build of PyTorch is already installed, skip the first `pip install` command. After dependencies are installed, Mina immediately loads the configured local model on CPU in a background thread. The small top-right panel remains responsive while loading; errors appear in its status text.

## Configuration

Edit `config.json`:

- `model.path`: local model directory; default is the existing Qwen model.
- `profile`: `development` or `normal`.
- `profiles.development`: random 20–60 second intervals and 10–30 second cooldowns after each popup disappears, no daily cap.
- `profiles.normal`: random 30–60 minute intervals and 30–45 minute cooldowns after each popup disappears, capped at 8/day.
- `activity.active_within_seconds`: recent-input window. Mina checks only Windows' last-input timestamp and never reads or stores keys or typed text.
- `emoji_peek.chance`: chance to show an emoji-only peek instead of generating dialogue. A peek lasts 60 seconds and consumes the same interruption/cooldown slot, but uses no model generation or typing sound.
- `sound.typing_wav`: WAV played in a loop only while Mina types; set to `null` to disable sound. The included retro key-clack clip is attenuated by 6 dB for a gentler peak volume.
- `ui.font_path` and `ui.persian_fallback`: Mojangles and Persian-capable fallback font paths/family. The persistent companion panel stays hidden; only Mina's dialogue and emoji popups appear. Model and runtime errors are reported in the hidden status area.

Mina's popup animation, typewriter speed, size, hold time, and mute-button header padding are configurable too; dialogue stays for 8 seconds after typing finishes by default. Its minimize control slides the dialogue away while leaving Mina running. Emoji-only peeks display only the animated GIF, with no title, frame, text, or controls. Emoji mappings live in `assets/emojis/moods.json`, and the ready-to-use transparent GIFs live in `assets/emojis/animations/`. Pillow loads each GIF's frames and frame durations directly; scaling uses nearest-neighbor resampling to preserve sharp pixels. No PNG emoji assets are used. Text is rasterized directly at pixel size with Mojangles; unsupported punctuation uses the configured system fallback. Add GIF animations by updating the mood mapping, not application code.

The supplied emoji pack is CC0 1.0. Mojangles is provided for local personal use alongside its readme and license; its license is non-commercial and does not permit redistribution.

## Notes

- Mina is designed to run on Windows. Activity detection uses `GetLastInputInfo` through `ctypes`.
- Model loading and generation use worker threads; Tkinter animations use scheduled callbacks.
- If an emoji sheet or configured sound file is unavailable, Mina displays an explicit status error.
- The included typing effect is derived from the user-provided retro-terminal key-clacks WAV. The full clip is looped while text is being revealed and stops when typing completes or the popup is dismissed.
- To exit Mina, use the `X` control on her companion panel. The dialogue's underscore control minimizes only that message.
