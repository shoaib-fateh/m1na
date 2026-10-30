import sys
from types import SimpleNamespace

from mina.config import PROJECT_ROOT
from mina.popup import MinaWindows


def test_typing_sound_loops_and_stops_with_playback(monkeypatch):
    calls = []
    fake_winsound = SimpleNamespace(
        SND_FILENAME=0x20000,
        SND_ASYNC=0x1,
        SND_NODEFAULT=0x2,
        SND_LOOP=0x8,
        PlaySound=lambda source, flags: calls.append((source, flags)),
    )
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "winsound", fake_winsound)

    window = object.__new__(MinaWindows)
    window._sound_playing = False
    window.set_status = lambda *_args, **_kwargs: None
    window._play_sound("assets/sounds/typing.wav")

    assert window._sound_playing
    assert calls[0][0] == str(PROJECT_ROOT / "assets" / "sounds" / "typing.wav")
    assert calls[0][1] & fake_winsound.SND_LOOP
    assert calls[0][1] & fake_winsound.SND_ASYNC

    window._stop_sound()

    assert not window._sound_playing
    assert calls[1] == (None, 0)
