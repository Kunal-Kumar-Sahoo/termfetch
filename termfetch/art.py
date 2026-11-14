"""Turn an image into a grid of coloured characters."""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageColor, ImageEnhance

RAMPS = {
    "ascii": " .`':,^;~-+=*x?%#&@$",
    "blocks": " ░▒▓█",
    "solid": "█",
}

HALF_BLOCK = "▀"
HALFBLOCK_CHARSET = "halfblocks"
DEFAULT_CHAR_ASPECT = 0.6
ALPHA_THRESHOLD = 16


@dataclass(frozen=True)
class Cell:
    char: str
    color: str
    bg: str | None = None


@dataclass(frozen=True)
class Art:
    rows: list[list[Cell]]

    @property
    def height(self) -> int:
        return len(self.rows)

    @property
    def width(self) -> int:
        return max((len(row) for row in self.rows), default=0)

    def as_text(self) -> str:
        return "\n".join(
            "".join(cell.char for cell in row)
            for row in self.rows
        )

    def as_ansi(self) -> str:
        output = []

        for row in self.rows:
            line = []

            for cell in row:
                r, g, b = (
                    int(cell.color[i:i + 2], 16)
                    for i in (1, 3, 5)
                )
                line.append(
                    f"\x1b[38;2;{r};{g};{b}m{cell.char}"
                )

            output.append("".join(line) + "\x1b[0m")

        return "\n".join(output)


def _quantize_channel(value: int, step: int) -> int:
    if step <= 1:
        return value

    return min(255, (value + step // 2) // step * step)


def _blend_color(
    foreground: str,
    background: str,
    alpha: int,
) -> str:
    fg = ImageColor.getrgb(foreground)
    bg = ImageColor.getrgb(background)
    opacity = alpha / 255

    channels = [
        round(f * opacity + b * (1 - opacity))
        for f, b in zip(fg, bg)
    ]

    return "#%02x%02x%02x" % tuple(channels)


def render(
    path: str,
    cols: int = 56,
    charset: str = "ascii",
    colored: bool = True,
    mono_color: str = "#c9d1d9",
    crop: tuple[int, int, int, int] | None = None,
    char_aspect: float = DEFAULT_CHAR_ASPECT,
    contrast: float = 1.0,
    brightness: float = 1.0,
    gamma: float = 1.0,
    color_step: int = 8,
    invert: bool = False,
    background_color: str = "#0d1117",
    shadow_lift: float = 0.0,
    preserve_foreground: bool = False,
) -> Art:
    half = charset == HALFBLOCK_CHARSET

    if not half and charset not in RAMPS:
        raise ValueError(
            f"unknown charset {charset!r}; expected one of "
            f"{sorted([*RAMPS, HALFBLOCK_CHARSET])}"
        )

    if cols < 1:
        raise ValueError("cols must be positive")

    if char_aspect <= 0:
        raise ValueError("char_aspect must be positive")

    if gamma <= 0:
        raise ValueError("gamma must be positive")

    if not 0.0 <= shadow_lift <= 1.0:
        raise ValueError("shadow_lift must be between 0 and 1")

    ramp = RAMPS.get(charset, "")

    source = Image.open(path).convert("RGBA")

    if crop:
        x, y, w, h = crop
        source = source.crop((x, y, x + w, y + h))

    alpha = source.getchannel("A")

    background_rgb = ImageColor.getrgb(background_color)
    background = Image.new(
        "RGBA",
        source.size,
        (*background_rgb, 255),
    )

    image = Image.alpha_composite(
        background,
        source,
    ).convert("RGB")

    if contrast != 1.0:
        image = ImageEnhance.Contrast(image).enhance(contrast)

    if brightness != 1.0:
        image = ImageEnhance.Brightness(image).enhance(brightness)

    rows = max(
        1,
        round(cols * char_aspect * image.height / image.width),
    )

    image_size = (
        cols,
        rows * 2 if half else rows,
    )

    image = image.resize(
        image_size,
        Image.Resampling.LANCZOS,
    )

    alpha = alpha.resize(
        image_size,
        Image.Resampling.LANCZOS,
    )

    def colour_at(x: int, y: int) -> str:
        r, g, b = image.getpixel((x, y))

        if not colored:
            return mono_color

        return "#%02x%02x%02x" % (
            _quantize_channel(r, color_step),
            _quantize_channel(g, color_step),
            _quantize_channel(b, color_step),
        )

    if half:
        return Art([
            [
                Cell(
                    HALF_BLOCK,
                    colour_at(x, y * 2),
                    colour_at(x, y * 2 + 1),
                )
                for x in range(cols)
            ]
            for y in range(rows)
        ])

    grid: list[list[Cell]] = []

    for y in range(rows):
        line: list[Cell] = []

        for x in range(cols):
            a = alpha.getpixel((x, y))

            if a < ALPHA_THRESHOLD:
                line.append(Cell(" ", mono_color))
                continue

            r, g, b = image.getpixel((x, y))

            lum = (
                0.2126 * r
                + 0.7152 * g
                + 0.0722 * b
            ) / 255

            if shadow_lift:
                lift = shadow_lift * (1.0 - lum)

                r = round(r + (255 - r) * lift)
                g = round(g + (255 - g) * lift)
                b = round(b + (255 - b) * lift)

                lum = (
                    0.2126 * r
                    + 0.7152 * g
                    + 0.0722 * b
                ) / 255

            if gamma != 1.0:
                lum = lum ** (1.0 / gamma)

            if invert:
                lum = 1.0 - lum

            index = min(
                len(ramp) - 1,
                int(lum * len(ramp)),
            )

            if preserve_foreground and len(ramp) > 1:
                index = max(1, index)

            char = ramp[index]

            if colored:
                color = "#%02x%02x%02x" % (
                    _quantize_channel(r, color_step),
                    _quantize_channel(g, color_step),
                    _quantize_channel(b, color_step),
                )
            else:
                color = _blend_color(
                    mono_color,
                    background_color,
                    a,
                )

            line.append(Cell(char, color))

        grid.append(line)

    return Art(grid)
