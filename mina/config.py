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
