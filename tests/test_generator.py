import pytest

from mina.generator import clean_message


def test_clean_message_compacts_newlines_and_quotes():
    assert clean_message('  "A tiny frog\nwears a hat."  ') == "A tiny frog wears a hat."


def test_clean_message_limits_to_two_sentences():
    assert clean_message("First. Second! Third?") == "First. Second!"


def test_empty_generation_is_an_explicit_error():
    with pytest.raises(ValueError, match="empty thought"):
        clean_message(" \n ")
