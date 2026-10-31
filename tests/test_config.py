import json

import pytest

from mina.config import PROJECT_ROOT, load_config


def test_loads_default_project_configuration():
    config = load_config()
    assert config["profile"] == "normal"
    assert config["profiles"]["normal"]["daily_limit"] == 8
    assert config["scheduler"]["enabled"]
    assert config["scheduler"]["state_path"] == "data/mina_scheduler.sqlite3"
    assert config["popup"]["animation"]["peek_duration_ms"] == 8_000
    assert config["chat"]["memory_messages"] == 10
    assert config["application_awareness"]["max_applications"] == 5
    assert config["sound"]["typing"]["enabled"]
    assert config["sound"]["dialogue_mode"] == "animalese"
    assert config["sound"]["animalese"]["files"] == [
        "assets/sounds/blips/blip_1_root.wav",
        "assets/sounds/blips/blip_2_second.wav",
        "assets/sounds/blips/blip_3_third.wav",
        "assets/sounds/blips/blip_4_fifth.wav",
        "assets/sounds/blips/blip_5_sixth.wav",
    ]
    assert all(
        (PROJECT_ROOT / path).is_file()
        for path in config["sound"]["animalese"]["files"]
    )
    assert config["sound"]["animalese"]["playback_speed"] == 2.1
    assert config["gaming_mode"]["enabled"]
    assert config["time_behavior"]["enabled"]
    assert config["time_behavior"]["poll_interval_ms"] == 30_000


def test_time_behavior_can_be_omitted_from_older_config(tmp_path):
    from mina.config import DEFAULT_CONFIG_PATH

    config = json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    config.pop("time_behavior")
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")

    assert load_config(path)["profile"] == config["profile"]


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("enabled", "yes", "scheduler.enabled"),
        ("state_path", "", "scheduler.state_path"),
    ],
)
def test_rejects_invalid_scheduler_settings(tmp_path, key, value, message):
    from mina.config import DEFAULT_CONFIG_PATH

    config = json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    config["scheduler"][key] = value
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_config(path)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda section: section.update(poll_interval_ms=500), "poll_interval_ms"),
        (lambda section: section.update(delay_seconds=[30, 10]), "delay_seconds"),
        (
            lambda section: section["rules"][0].update(type="unknown"),
            "rule type",
        ),
    ],
)
def test_rejects_invalid_time_behavior_settings(tmp_path, mutation, message):
    from mina.config import DEFAULT_CONFIG_PATH

    config = json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    mutation(config["time_behavior"])
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_config(path)


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_rejects_invalid_chat_memory_limit(tmp_path, value):
    from mina.config import DEFAULT_CONFIG_PATH

    config = json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    config["chat"]["memory_messages"] = value
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ValueError, match="chat.memory_messages"):
        load_config(path)


@pytest.mark.parametrize(
    ("section", "key", "value", "message"),
    [
        ("sound", "volume", 101, "volume"),
        ("sound", "volume", True, "volume"),
        ("gaming_mode", "poll_interval_ms", 50, "poll_interval_ms"),
    ],
)
def test_rejects_invalid_sound_and_gaming_settings(
    tmp_path, section, key, value, message
):
    from mina.config import DEFAULT_CONFIG_PATH

    config = json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    if section == "sound":
        config["sound"]["typing"][key] = value
    else:
        config[section][key] = value
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_config(path)


def test_rejects_invalid_timing_range(tmp_path):
    config = {
        "profile": "dev",
        "profiles": {"dev": {"interval_seconds": [5, 2], "cooldown_seconds": [1, 2]}},
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ValueError, match="interval_seconds"):
        load_config(path)
