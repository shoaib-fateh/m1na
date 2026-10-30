import json

import pytest
from PIL import Image, ImageTk

from mina.emoji_assets import EmojiLibrary, load_mapping


class FakePhoto:
    def __init__(self, image):
        self.size = image.size


def create_test_gif(path):
    first = Image.new("RGBA", (8, 8), (255, 0, 0, 255))
    second = Image.new("RGBA", (8, 8), (0, 255, 0, 255))
    first.save(
        path,
        format="GIF",
        save_all=True,
        append_images=[second],
        duration=[60, 140],
        loop=0,
        transparency=0,
        disposal=2,
    )


def test_loads_gif_frames_with_original_timing_and_nearest_scaling(tmp_path, monkeypatch):
    monkeypatch.setattr(ImageTk, "PhotoImage", FakePhoto)
    create_test_gif(tmp_path / "happy.gif")
    library = EmojiLibrary(tmp_path, {"happy": ["happy.gif"]}, scale=3)

    animation = library.animation("happy")

    assert len(animation.frames) == 2
    assert [frame.size for frame in animation.frames] == [(24, 24), (24, 24)]
    assert animation.durations_ms == [60, 140]


def test_animation_cache_distinguishes_scale(tmp_path, monkeypatch):
    monkeypatch.setattr(ImageTk, "PhotoImage", FakePhoto)
    create_test_gif(tmp_path / "happy.gif")
    library = EmojiLibrary(tmp_path, {"happy": ["happy.gif"]}, scale=2)

    small = library.animation("happy")
    large = library.animation("happy", scale=4)

    assert small is library.animation("happy")
    assert small.frames[0].size == (16, 16)
    assert large.frames[0].size == (32, 32)


def test_mapping_lists_local_gif_names(tmp_path):
    path = tmp_path / "moods.json"
    path.write_text("\ufeff" + json.dumps({"happy": ["happy.gif"]}), encoding="utf-8")
    assert load_mapping(path) == {"happy": ["happy.gif"]}


def test_mapping_rejects_png_files(tmp_path):
    path = tmp_path / "moods.json"
    path.write_text(json.dumps({"happy": ["face.png"]}), encoding="utf-8")
    with pytest.raises(ValueError, match="GIF"):
        load_mapping(path)


def test_rejects_png_animation_asset(tmp_path):
    Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(tmp_path / "face.png")
    library = EmojiLibrary(tmp_path, {"happy": ["face.png"]}, scale=1)

    with pytest.raises(ValueError, match="GIF"):
        library._load_gif("face.png", 1)
