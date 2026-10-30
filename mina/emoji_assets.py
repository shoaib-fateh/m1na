from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageSequence, ImageTk


@dataclass(frozen=True)
class EmojiAnimation:
    frames: list[ImageTk.PhotoImage]
    durations_ms: list[int]


def load_mapping(path: Path) -> dict[str, list[str]]:
    with path.open("r", encoding="utf-8-sig") as mapping_file:
        mapping = json.load(mapping_file)
    if not isinstance(mapping, dict) or not mapping:
        raise ValueError("Emoji mapping must be a non-empty JSON object.")
    if any(
        not isinstance(mood, str)
        or not isinstance(files, list)
        or not files
        or any(not isinstance(filename, str) or Path(filename).suffix.lower() != ".gif" for filename in files)
        for mood, files in mapping.items()
    ):
        raise ValueError("Each emoji mood must map to a list of GIF filenames.")
    return mapping


class EmojiLibrary:
    def __init__(
        self, asset_directory: Path, mapping: dict[str, list[str]], scale: int = 3
    ) -> None:
        if scale < 1:
            raise ValueError("Emoji scale must be a positive integer.")
        self.asset_directory = asset_directory
        self.mapping = mapping
        self.scale = scale
        self._animation_cache: dict[tuple[str, int], EmojiAnimation] = {}
        self._rng = random.Random()

    @property
    def moods(self) -> tuple[str, ...]:
        return tuple(self.mapping)

    def random_mood(self) -> str:
        return self._rng.choice(self.moods)

    def animation(self, mood: str, scale: int | None = None) -> EmojiAnimation:
        if mood not in self.mapping:
            raise KeyError(f"Unknown emoji mood: {mood}")
        selected_scale = self.scale if scale is None else scale
        if selected_scale < 1:
            raise ValueError("Emoji scale must be a positive integer.")
        cache_key = (mood, selected_scale)
        if cache_key not in self._animation_cache:
            filename = self._rng.choice(self.mapping[mood])
            self._animation_cache[cache_key] = self._load_gif(filename, selected_scale)
        return self._animation_cache[cache_key]

    def _load_gif(self, filename: str, scale: int) -> EmojiAnimation:
        path = self.asset_directory / filename
        if path.suffix.lower() != ".gif":
            raise ValueError(f"Emoji assets must be GIF animations: {path}")
        if not path.is_file():
            raise FileNotFoundError(f"Emoji GIF not found: {path}")

        frames: list[ImageTk.PhotoImage] = []
        durations: list[int] = []
        with Image.open(path) as gif:
            if gif.format != "GIF":
                raise ValueError(f"Emoji file is not a GIF animation: {path}")
            for frame in ImageSequence.Iterator(gif):
                rgba = frame.convert("RGBA")
                if scale != 1:
                    rgba = rgba.resize(
                        (rgba.width * scale, rgba.height * scale),
                        Image.Resampling.NEAREST,
                    )
                frames.append(ImageTk.PhotoImage(rgba))
                durations.append(max(20, int(frame.info.get("duration", 80))))

        if not frames:
            raise ValueError(f"Emoji GIF has no frames: {path}")
        return EmojiAnimation(frames, durations)
