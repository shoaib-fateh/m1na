from __future__ import annotations

import tempfile
import wave
import random
import math
from pathlib import Path


class AnimaleseBlips:
    def __init__(
        self,
        paths: list[str | Path],
        random_source: random.Random | None = None,
    ) -> None:
        if not paths:
            raise ValueError("Animalese requires at least one blip WAV.")
        self.paths = tuple(Path(path) for path in paths)
        self.random = random_source or random.Random()
        self._previous_index: int | None = None

    def next_path(self) -> Path:
        if len(self.paths) == 1:
            self._previous_index = 0
            return self.paths[0]
        choices = [
            index for index in range(len(self.paths)) if index != self._previous_index
        ]
        index = self.random.choice(choices)
        self._previous_index = index
        return self.paths[index]

class SoundPlayer:
    """Non-blocking Windows WAV playback with one exclusive active sound mode."""

    def __init__(self) -> None:
        self.active_mode: str | None = None
        self._temporary_directory: tempfile.TemporaryDirectory[str] | None = None
        self._scaled_paths: dict[tuple[Path, int, int, int, int], Path] = {}

    def prepare(self, path: str | Path, volume: int, speed: float = 1.0) -> int:
        if not isinstance(volume, int) or isinstance(volume, bool) or not 0 <= volume <= 100:
            raise ValueError("Sound volume must be an integer from 0 to 100.")
        _validate_speed(speed)
        source = Path(path).resolve()
        if not source.is_file():
            raise FileNotFoundError(f"Sound file not found: {source}")
        try:
            with wave.open(str(source), "rb") as audio:
                duration_ms = math.ceil(audio.getnframes() * 1000 / audio.getframerate() / speed)
        except (wave.Error, EOFError) as error:
            raise ValueError(f"Could not read PCM WAV sound effect: {error}") from error
        if volume != 0 and (volume != 100 or speed != 1):
            self._scaled_path(source, volume, speed)
        return duration_ms

    def play(
        self,
        mode: str,
        path: str | Path,
        volume: int,
        loop: bool = False,
        speed: float = 1.0,
    ) -> None:
        if mode not in {"typing", "animalese", "click", "speaking"}:
            raise ValueError(f"Unsupported sound mode: {mode!r}")
        if not isinstance(volume, int) or isinstance(volume, bool) or not 0 <= volume <= 100:
            raise ValueError("Sound volume must be an integer from 0 to 100.")
        _validate_speed(speed)
        source = Path(path).resolve()
        if not source.is_file():
            raise FileNotFoundError(f"Sound file not found: {source}")

        self.stop()
        if volume == 0:
            return
        playback_path = (
            source
            if volume == 100 and speed == 1
            else self._scaled_path(source, volume, speed)
        )

        import winsound

        flags = winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT
        if loop:
            flags |= winsound.SND_LOOP
        winsound.PlaySound(str(playback_path), flags)
        self.active_mode = mode

    def stop(self) -> None:
        if self.active_mode is None:
            return
        import winsound

        winsound.PlaySound(None, 0)
        self.active_mode = None

    def close(self) -> None:
        self.stop()
        self._scaled_paths.clear()
        if self._temporary_directory is not None:
            self._temporary_directory.cleanup()
            self._temporary_directory = None

    def _scaled_path(self, source: Path, volume: int, speed: float = 1.0) -> Path:
        stat = source.stat()
        speed_milli = round(speed * 1000)
        key = (source, stat.st_mtime_ns, stat.st_size, volume, speed_milli)
        cached = self._scaled_paths.get(key)
        if cached is not None and cached.is_file():
            return cached
        try:
            with wave.open(str(source), "rb") as audio:
                if audio.getcomptype() != "NONE":
                    raise ValueError("Only uncompressed PCM WAV sound effects are supported.")
                params = audio.getparams()
                frames = audio.readframes(audio.getnframes())
        except (wave.Error, EOFError) as error:
            raise ValueError(f"Could not read PCM WAV sound effect: {error}") from error

        scaled = _scale_pcm(frames, params.sampwidth, volume)
        adjusted_params = params._replace(
            framerate=max(1, round(params.framerate * speed))
        )
        if self._temporary_directory is None:
            self._temporary_directory = tempfile.TemporaryDirectory(prefix="mina-audio-")
        target = Path(self._temporary_directory.name) / f"{len(self._scaled_paths)}.wav"
        try:
            with wave.open(str(target), "wb") as audio:
                audio.setparams(adjusted_params)
                audio.writeframes(scaled)
        except (wave.Error, OSError) as error:
            raise OSError(f"Could not prepare volume-adjusted sound: {error}") from error
        self._scaled_paths[key] = target
        return target


def _scale_pcm(frames: bytes, sample_width: int, volume: int) -> bytes:
    if sample_width not in {1, 2, 3, 4}:
        raise ValueError(f"Unsupported PCM sample width: {sample_width} bytes.")
    if len(frames) % sample_width:
        raise ValueError("PCM WAV data ends with an incomplete sample.")
    factor = volume / 100
    result = bytearray(len(frames))
    for offset in range(0, len(frames), sample_width):
        sample_bytes = frames[offset : offset + sample_width]
        if sample_width == 1:
            centered = sample_bytes[0] - 128
            scaled = round(centered * factor) + 128
            result[offset] = max(0, min(255, scaled))
            continue
        sample = int.from_bytes(sample_bytes, "little", signed=True)
        scaled = round(sample * factor)
        minimum = -(1 << (sample_width * 8 - 1))
        maximum = (1 << (sample_width * 8 - 1)) - 1
        result[offset : offset + sample_width] = max(
            minimum, min(maximum, scaled)
        ).to_bytes(sample_width, "little", signed=True)
    return bytes(result)


def _validate_speed(speed: float) -> None:
    if (
        not isinstance(speed, (int, float))
        or isinstance(speed, bool)
        or not 0.25 <= speed <= 4.0
    ):
        raise ValueError("Sound speed must be from 0.25 to 4.0.")
