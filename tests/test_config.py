import json

import pytest

from mina.config import load_config


def test_loads_default_project_configuration():
    config = load_config()
    assert config["profile"] == "development"
    assert config["profiles"]["development"]["daily_limit"] is None
    assert config["popup"]["animation"]["peek_duration_ms"] == 60_000


def test_rejects_invalid_timing_range(tmp_path):
    config = {
        "profile": "dev",
        "profiles": {"dev": {"interval_seconds": [5, 2], "cooldown_seconds": [1, 2]}},
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ValueError, match="interval_seconds"):
        load_config(path)
