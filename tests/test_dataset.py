import json
import sqlite3

import pytest

from mina.dataset import PersonalDataset


def test_dataset_keeps_full_history_and_returns_only_latest_chat_messages(tmp_path):
    store = PersonalDataset(tmp_path / "mina.sqlite3")
    store.add_message("thought", "assistant", "A tiny thought.")
    store.add_message("chat", "user", "First.")
    store.add_message("chat", "assistant", "Reply one.")
    store.add_message("chat", "user", "Second.")
    store.add_message("chat", "assistant", "Reply two.", ["Code", "Photoshop"])

    assert store.recent_chat(2) == [
        {"role": "user", "text": "Second."},
        {"role": "assistant", "text": "Reply two."},
    ]

    with sqlite3.connect(store.path) as connection:
        rows = connection.execute(
            "SELECT timestamp, kind, role, text, active_applications "
            "FROM messages ORDER BY id"
        ).fetchall()
    assert len(rows) == 5
    assert all(row[0] for row in rows)
    assert rows[-1][1:4] == ("chat", "assistant", "Reply two.")
    assert json.loads(rows[-1][4]) == ["Code", "Photoshop"]


def test_dataset_rejects_invalid_memory_limit(tmp_path):
    store = PersonalDataset(tmp_path / "mina.sqlite3")
    with pytest.raises(ValueError, match="positive integer"):
        store.recent_chat(0)
