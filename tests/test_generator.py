import pytest

from mina.generator import clean_message
from mina.generator import LocalQwen


def test_clean_message_compacts_newlines_and_quotes():
    assert clean_message('  "A tiny frog\nwears a hat."  ') == "A tiny frog wears a hat."


def test_clean_message_limits_to_two_sentences():
    assert clean_message("First. Second! Third?") == "First. Second!"


def test_empty_generation_is_an_explicit_error():
    with pytest.raises(ValueError, match="empty thought"):
        clean_message(" \n ")


def test_chat_prompt_preserves_mina_personality_and_context():
    generator = LocalQwen("unused")
    generator._tokenizer = object()
    generator._model = object()
    captured = {}

    def generate(messages, max_characters):
        captured["messages"] = messages
        captured["max_characters"] = max_characters
        return "A direct reply."

    generator._generate = generate
    reply = generator.generate_chat(
        [
            {"role": "user", "text": "I am editing a video."},
            {"role": "assistant", "text": "The timeline looks like a noodle."},
            {"role": "user", "text": "Exactly."},
        ],
        ["Premiere"],
    )

    assert reply == "A direct reply."
    assert captured["messages"][0]["role"] == "system"
    assert "not a generic assistant" in captured["messages"][0]["content"]
    assert "Premiere" in captured["messages"][0]["content"]
    assert [message["role"] for message in captured["messages"][1:]] == [
        "user",
        "assistant",
        "user",
    ]
    assert captured["max_characters"] == 400
