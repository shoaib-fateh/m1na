import os
from pathlib import Path

from mina.pixel_text import rasterize_text


FONT = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "mojangles.otf"


def test_rasterizes_pixel_font_text_at_native_size():
    image = rasterize_text("MINA", FONT, 16, "#f2eccb")
    assert image.width > 30
    assert image.height >= 10
    assert image.getchannel("A").getbbox() is not None


def test_wraps_text_within_pixel_width():
    image = rasterize_text("Mina is waking up", FONT, 16, "#f2eccb", max_width=60)
    assert image.height > rasterize_text("Mina", FONT, 16, "#f2eccb").height


def test_missing_punctuation_uses_fallback_font():
    fallback = Path(os.environ["WINDIR"]) / "Fonts" / "segoeui.ttf"
    if not fallback.is_file():
        return
    image = rasterize_text("!", FONT, 16, "#f2eccb", fallback_font_path=fallback)
    assert image.width < 10
