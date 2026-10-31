from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.json"


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as config_file:
        config = json.load(config_file)
    if not isinstance(config, dict):
        raise ValueError("The configuration file must contain a JSON object.")

    profile_name = config.get("profile", "development")
    profiles = config.get("profiles")
    if not isinstance(profiles, dict) or profile_name not in profiles:
        raise ValueError(f"Unknown timing profile: {profile_name!r}")

    profile = profiles[profile_name]
    _validate_range(profile, "interval_seconds")
    _validate_range(profile, "cooldown_seconds")
    daily_limit = profile.get("daily_limit")
    if daily_limit is not None and (
        not isinstance(daily_limit, int) or isinstance(daily_limit, bool) or daily_limit < 1
    ):
        raise ValueError("daily_limit must be a positive integer or null.")

    peek_chance = config.get("emoji_peek", {}).get("chance", 0.2)
    if not isinstance(peek_chance, (int, float)) or not 0 <= peek_chance <= 1:
        raise ValueError("emoji_peek.chance must be between 0 and 1.")

    chat = config.get("chat", {})
    memory_messages = chat.get("memory_messages", 10)
    if (
        not isinstance(memory_messages, int)
        or isinstance(memory_messages, bool)
        or memory_messages < 1
    ):
        raise ValueError("chat.memory_messages must be a positive integer.")

    awareness = config.get("application_awareness", {})
    enabled = awareness.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError("application_awareness.enabled must be a boolean.")
    max_applications = awareness.get("max_applications", 5)
    if (
        not isinstance(max_applications, int)
        or isinstance(max_applications, bool)
        or not 1 <= max_applications <= 5
    ):
        raise ValueError("application_awareness.max_applications must be 1 through 5.")

    gaming = config.get("gaming_mode", {})
    gaming_enabled = gaming.get("enabled", True)
    if not isinstance(gaming_enabled, bool):
        raise ValueError("gaming_mode.enabled must be a boolean.")
    gaming_interval = gaming.get("poll_interval_ms", 1000)
    if (
        not isinstance(gaming_interval, int)
        or isinstance(gaming_interval, bool)
        or gaming_interval < 100
    ):
        raise ValueError("gaming_mode.poll_interval_ms must be an integer of at least 100.")
    excluded_processes = gaming.get("excluded_processes", [])
    if not isinstance(excluded_processes, list) or any(
        not isinstance(name, str) or not name.strip() for name in excluded_processes
    ):
        raise ValueError("gaming_mode.excluded_processes must be a list of process names.")

    sound = config.get("sound", {})
    if not isinstance(sound, dict):
        raise ValueError("sound must be an object.")
    dialogue_mode = sound.get("dialogue_mode", "typing")
    if dialogue_mode not in {"animalese", "typing", "silent"}:
        raise ValueError("sound.dialogue_mode must be animalese, typing, or silent.")
    for mode in ("typing", "animalese", "click"):
        settings = sound.get(mode, {})
        if not isinstance(settings, dict):
            raise ValueError(f"sound.{mode} must be an object.")
        enabled = settings.get("enabled", mode == "typing")
        if not isinstance(enabled, bool):
            raise ValueError(f"sound.{mode}.enabled must be a boolean.")
        volume = settings.get("volume", 100)
        if (
            not isinstance(volume, int)
            or isinstance(volume, bool)
            or not 0 <= volume <= 100
        ):
            raise ValueError(f"sound.{mode}.volume must be an integer from 0 to 100.")
    typing_settings = sound.get("typing", {})
    typing_path = typing_settings.get("path", sound.get("typing_wav"))
    if not isinstance(typing_path, str) or not typing_path.strip():
        raise ValueError("sound.typing.path must be a non-empty local path.")
    animalese = sound.get("animalese", {})
    blip_files = animalese.get("files", [])
    if not isinstance(blip_files, list) or not blip_files or any(
        not isinstance(path, str) or not path.strip() for path in blip_files
    ):
        raise ValueError("sound.animalese.files must be a non-empty list of local paths.")
    if not isinstance(animalese.get("enabled", True), bool):
        raise ValueError("sound.animalese.enabled must be a boolean.")
    speed = animalese.get("playback_speed", 2.5)
    if (
        not isinstance(speed, (int, float))
        or isinstance(speed, bool)
        or not 0.25 <= speed <= 4
    ):
        raise ValueError("sound.animalese.playback_speed must be from 0.25 to 4.0.")
    char_interval = animalese.get("character_interval_ms", 70)
    if not isinstance(char_interval, int) or isinstance(char_interval, bool) or char_interval < 1:
        raise ValueError("sound.animalese.character_interval_ms must be a positive integer.")
    click = sound.get("click", {})
    click_path = click.get("path")
    if click.get("enabled", False) and (
        not isinstance(click_path, str) or not click_path.strip()
    ):
        raise ValueError("Enabled sound.click requires a non-empty local path.")

    dataset_path = config.get("dataset", {}).get("path", "data/mina.sqlite3")
    if not isinstance(dataset_path, str) or not dataset_path.strip():
        raise ValueError("dataset.path must be a non-empty local path.")
    return config


def _validate_range(profile: dict[str, Any], key: str) -> None:
    value = profile.get(key)
    if (
        not isinstance(value, list)
        or len(value) != 2
        or any(not isinstance(item, (int, float)) or isinstance(item, bool) for item in value)
        or value[0] < 0
        or value[0] > value[1]
    ):
        raise ValueError(f"{key} must be a two-number [minimum, maximum] range.")
