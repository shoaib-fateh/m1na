from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageTk, features


def _glyph_font(
    character: str,
    font: ImageFont.FreeTypeFont,
    fallback: ImageFont.FreeTypeFont | None,
    missing_glyph: tuple[tuple[int, int], bytes],
) -> ImageFont.FreeTypeFont:
    if fallback is None or character.isspace():
        return font
    try:
        mask = font.getmask(character)
    except (UnicodeEncodeError, ValueError):
        return fallback
    if mask.size == missing_glyph[0] and bytes(mask) == missing_glyph[1]:
        return fallback
    return font


def _measure_text(
    text: str,
    font: ImageFont.FreeTypeFont,
    fallback: ImageFont.FreeTypeFont | None,
    missing_glyph: tuple[tuple[int, int], bytes],
) -> float:
    return sum(
        _glyph_font(character, font, fallback, missing_glyph).getlength(character)
        for character in text
    )


def _wrap_text(
    text: str,
    font: ImageFont.FreeTypeFont,
    fallback: ImageFont.FreeTypeFont | None,
    missing_glyph: tuple[tuple[int, int], bytes],
    max_width: int | None,
) -> list[str]:
    if max_width is None or max_width < 1:
        return text.splitlines() or [""]

    wrapped: list[str] = []
    for paragraph in text.splitlines() or [""]:
        line = ""
        for word in paragraph.split():
            candidate = f"{line} {word}".strip()
            if line and _measure_text(candidate, font, fallback, missing_glyph) > max_width:
                wrapped.append(line)
                line = word
            else:
                line = candidate
            while line and _measure_text(line, font, fallback, missing_glyph) > max_width:
                prefix = ""
                remainder = ""
                for character in line:
                    if _measure_text(prefix + character, font, fallback, missing_glyph) > max_width:
                        remainder += character
                    elif remainder:
                        remainder += character
                    else:
                        prefix += character
                if prefix:
                    wrapped.append(prefix)
                    line = remainder
                else:
                    break
        wrapped.append(line)
    return wrapped


def rasterize_text(
    text: str,
    font_path: Path,
    size: int,
    color: str,
    max_width: int | None = None,
    fallback_font_path: Path | None = None,
) -> Image.Image:
    if size < 1:
        raise ValueError("Pixel font size must be a positive integer.")
    if not font_path.is_file():
        raise FileNotFoundError(f"UI font file not found: {font_path}")

    text = text.replace("…", "...")
    layout_engine = ImageFont.Layout.RAQM if features.check("raqm") else ImageFont.Layout.BASIC
    font = ImageFont.truetype(str(font_path), size=size, layout_engine=layout_engine)
    fallback = None
    if fallback_font_path and fallback_font_path.is_file() and fallback_font_path != font_path:
        fallback = ImageFont.truetype(str(fallback_font_path), size=size, layout_engine=layout_engine)
    missing = font.getmask(chr(0x10FFFF))
    missing_glyph = (missing.size, bytes(missing))
    lines = _wrap_text(text, font, fallback, missing_glyph, max_width)
    spacing = max(1, size // 6)
    ascent, descent = font.getmetrics()
    line_height = ascent + descent + spacing
    line_widths = [
        _measure_text(line, font, fallback, missing_glyph)
        for line in lines
    ]
    image = Image.new(
        "RGBA",
        (max(1, int(max(line_widths, default=0)) + 2), max(1, line_height * len(lines))),
        (0, 0, 0, 0),
    )
    draw = ImageDraw.Draw(image)
    for line_index, line in enumerate(lines):
        x = 1
        baseline = line_index * line_height + ascent
        for character in line:
            glyph_font = _glyph_font(character, font, fallback, missing_glyph)
            draw.text((x, baseline), character, font=glyph_font, fill=color, anchor="ls")
            x += glyph_font.getlength(character)
    return image


class PixelTextRenderer:
    def __init__(self, root, font_path: Path, persian_fallback_path: Path) -> None:
        self.root = root
        self.font_path = font_path
        self.persian_fallback_path = persian_fallback_path

    def render(
        self,
        text: str,
        size: int,
        color: str,
        max_width: int | None = None,
    ) -> ImageTk.PhotoImage:
        has_persian = any("\u0600" <= character <= "\u06ff" for character in text)
        font_path = self.persian_fallback_path if has_persian else self.font_path
        fallback_font_path = None if has_persian else self.persian_fallback_path
        image = rasterize_text(
            text, font_path, size, color, max_width, fallback_font_path
        )
        return ImageTk.PhotoImage(image, master=self.root)
