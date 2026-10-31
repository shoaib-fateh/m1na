import sys
import wave
from types import SimpleNamespace

from mina.config import PROJECT_ROOT
from mina.popup import MinaWindows
from mina.sound import AnimaleseBlips, SoundPlayer, _scale_pcm


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
    window._sound_mode = None
    window._sound_player = SoundPlayer()
    window._reported_sound_errors = set()
    window.set_status = lambda *_args, **_kwargs: None
    window._play_sound("assets/sounds/typing.wav")

    assert window._sound_playing
    assert calls[0][0] == str(PROJECT_ROOT / "assets" / "sounds" / "typing.wav")
    assert calls[0][1] & fake_winsound.SND_LOOP
    assert calls[0][1] & fake_winsound.SND_ASYNC

    window._stop_sound()

    assert not window._sound_playing
    assert calls[1] == (None, 0)


def test_switching_sound_modes_stops_the_previous_sound(monkeypatch, tmp_path):
    calls = []
    fake_winsound = SimpleNamespace(
        SND_FILENAME=0x20000,
        SND_ASYNC=0x1,
        SND_NODEFAULT=0x2,
        SND_LOOP=0x8,
        PlaySound=lambda source, flags: calls.append((source, flags)),
    )
    monkeypatch.setitem(sys.modules, "winsound", fake_winsound)
    typing_path = PROJECT_ROOT / "assets" / "sounds" / "typing.wav"
    speaking_path = tmp_path / "bliptalk.wav"
    speaking_path.write_bytes(typing_path.read_bytes())
    player = SoundPlayer()

    player.play("typing", typing_path, 100, loop=True)
    player.play("speaking", speaking_path, 100)

    assert calls[0][0] == str(typing_path.resolve())
    assert calls[0][1] & fake_winsound.SND_LOOP
    assert calls[1] == (None, 0)
    assert calls[2][0] == str(speaking_path.resolve())
    assert not calls[2][1] & fake_winsound.SND_LOOP
    assert player.active_mode == "speaking"
    player.close()


def test_pcm_volume_scaling_preserves_silence_and_scales_samples():
    assert _scale_pcm(bytes([0, 128, 255]), 1, 50) == bytes([64, 128, 192])
    assert _scale_pcm((1000).to_bytes(2, "little", signed=True), 2, 50) == (
        500
    ).to_bytes(2, "little", signed=True)


def test_sound_player_writes_volume_adjusted_pcm_wav(monkeypatch, tmp_path):
    calls = []
    fake_winsound = SimpleNamespace(
        SND_FILENAME=0x20000,
        SND_ASYNC=0x1,
        SND_NODEFAULT=0x2,
        SND_LOOP=0x8,
        PlaySound=lambda source, flags: calls.append((source, flags)),
    )
    monkeypatch.setitem(sys.modules, "winsound", fake_winsound)
    source = tmp_path / "source.wav"
    with wave.open(str(source), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes((1000).to_bytes(2, "little", signed=True))
    player = SoundPlayer()

    player.play("speaking", source, 50)

    prepared_path = calls[0][0]
    with wave.open(prepared_path, "rb") as audio:
        assert int.from_bytes(audio.readframes(1), "little", signed=True) == 500
    player.close()


def test_prepared_volume_file_is_reused_during_async_playback(monkeypatch, tmp_path):
    import mina.sound as sound_module

    calls = []
    fake_winsound = SimpleNamespace(
        SND_FILENAME=0x20000,
        SND_ASYNC=0x1,
        SND_NODEFAULT=0x2,
        SND_LOOP=0x8,
        PlaySound=lambda source, flags: calls.append((source, flags)),
    )
    monkeypatch.setitem(sys.modules, "winsound", fake_winsound)
    source = tmp_path / "source.wav"
    with wave.open(str(source), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes((1000).to_bytes(2, "little", signed=True))
    scale_calls = []
    original_scale = sound_module._scale_pcm

    def track_scaling(frames, width, volume):
        scale_calls.append(volume)
        return original_scale(frames, width, volume)

    monkeypatch.setattr(sound_module, "_scale_pcm", track_scaling)
    player = SoundPlayer()
    player.prepare(source, 45)
    player.play("speaking", source, 45)

    assert scale_calls == [45]
    assert calls[0][0].endswith(".wav")
    player.close()


def test_animalese_does_not_play_for_whitespace_or_punctuation():
    window = object.__new__(MinaWindows)
    window._gaming_mode = False
    window._sound_mode = "typing"
    window._popup_kind = ""
    window.config = {
        "sound": {
            "dialogue_mode": "animalese",
            "animalese": {
                "enabled": True,
                "files": ["one.wav", "two.wav"],
                "volume": 55,
                "playback_speed": 2.5,
            }
        }
    }
    window._animalese_blips = AnimaleseBlips(["one.wav", "two.wav"])
    calls = []
    window._play_sound = lambda *args, **kwargs: calls.append((args, kwargs))

    window._play_dialogue_character(" ")
    window._play_dialogue_character("!")
    assert calls == []
    window._play_dialogue_character("M")
    window._play_dialogue_character("i")
    assert len(calls) == 2
    assert calls[0][0][0] != calls[1][0][0]
    assert calls[0][1] == {"mode": "animalese", "volume": 55, "speed": 2.5}


def test_configured_dialogue_audio_plays_one_blip_per_character():
    window = object.__new__(MinaWindows)
    window._gaming_mode = False
    window.config = {
        "sound": {
            "dialogue_mode": "animalese",
            "animalese": {
                "enabled": True,
                "files": ["dialogue_1.wav", "dialogue_2.wav"],
                "volume": 55,
                "playback_speed": 1.0,
            },
        }
    }
    window._animalese_blips = AnimaleseBlips(["dialogue_1.wav", "dialogue_2.wav"])
    calls = []
    window._play_sound = lambda *args, **kwargs: calls.append((args, kwargs))

    window._play_dialogue_character("H")
    window._play_dialogue_character("i")

    assert len(calls) == 2
    assert calls[0][0][0] != calls[1][0][0]
    assert all(call[1]["speed"] == 1.0 for call in calls)
    assert all(call[1].get("loop", False) is False for call in calls)


def test_final_animalese_blip_is_not_cut_off_when_typewriter_finishes():
    window = object.__new__(MinaWindows)
    window._canvas = type("Canvas", (), {"itemconfigure": lambda *_args, **_kwargs: None})()
    window._popup = object()
    window._message = "M"
    window._typed = 0
    window._message_size = 12
    window._message_width = 100
    window._message_item = 4
    window._text_renderer = type("Renderer", (), {"render": lambda *_args, **_kwargs: "raster"})()
    window.config = {"popup": {"hold_ms": 8000}}
    window._sound_mode = "animalese"
    calls = []
    window._stop_sound = lambda: calls.append("stop")
    window.root = type("Root", (), {"after": lambda *_args: "after-id"})()
    window._start_dismiss_timer = lambda *_args: None
    window._play_dialogue_character = lambda _character: None

    window._type_next()

    assert calls == []


def test_animalese_blips_use_cached_low_latency_mixer_samples(monkeypatch, tmp_path):
    class FakeChannel:
        def __init__(self):
            self.played = []
            self.stop_count = 0

        def play(self, sound):
            self.played.append(sound)

        def stop(self):
            self.stop_count += 1

    class FakeMixer:
        def __init__(self):
            self.channel = FakeChannel()
            self.sound_paths = []
            self.initialized = False
            self.pre_init_args = None
            self.quit_called = False

        def get_init(self):
            return (44100, -16, 2) if self.initialized else None

        def pre_init(self, *args):
            self.pre_init_args = args

        def init(self):
            self.initialized = True

        def Sound(self, path):
            self.sound_paths.append(path)
            return path

        def Channel(self, index):
            assert index == 0
            return self.channel

        def quit(self):
            self.quit_called = True

    mixer = FakeMixer()
    fake_pygame = SimpleNamespace(error=RuntimeError, mixer=mixer)
    monkeypatch.setitem(sys.modules, "pygame", fake_pygame)
    source = tmp_path / "blip.wav"
    with wave.open(str(source), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes((1000).to_bytes(2, "little", signed=True))

    player = SoundPlayer()
    player.play_blip("animalese", source, 100, speed=2.0)
    player.play_blip("animalese", source, 100, speed=2.0)

    assert mixer.pre_init_args == (44100, -16, 2, 256)
    assert len(mixer.sound_paths) == 1
    assert len(mixer.channel.played) == 2
    assert mixer.channel.stop_count == 1
    assert player.active_mode == "animalese"
    player.close()
    assert mixer.quit_called


def test_animalese_blips_never_repeat_consecutively():
    class ChoiceFirst:
        def choice(self, choices):
            return choices[0]

    blips = AnimaleseBlips(["one.wav", "two.wav", "three.wav"], ChoiceFirst())
    sounds = [blips.next_path() for _ in range(5)]

    assert all(first != second for first, second in zip(sounds, sounds[1:]))


def test_sound_speed_changes_wav_playback_rate(monkeypatch, tmp_path):
    calls = []
    fake_winsound = SimpleNamespace(
        SND_FILENAME=0x20000,
        SND_ASYNC=0x1,
        SND_NODEFAULT=0x2,
        SND_LOOP=0x8,
        PlaySound=lambda source, flags: calls.append((source, flags)),
    )
    monkeypatch.setitem(sys.modules, "winsound", fake_winsound)
    source = tmp_path / "source.wav"
    with wave.open(str(source), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes((1000).to_bytes(2, "little", signed=True))
    player = SoundPlayer()
    duration_ms = player.prepare(source, 100, speed=2)
    player.play("animalese", source, 100, speed=2)

    assert duration_ms == 1
    with wave.open(calls[0][0], "rb") as audio:
        assert audio.getframerate() == 16000
    player.close()
