"""Assemble the card SVG."""

from __future__ import annotations

from dataclasses import dataclass

from .art import Art
from .theme import Theme

FONT_STACK = "ui-monospace, SFMono-Regular, SF Mono, Menlo, Consolas, Liberation Mono, monospace"
CHAR_WIDTH_RATIO = 0.6


def n(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")


def escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


@dataclass
class Section:
    title: str | None
    fields: list[tuple[str | None, str]]
    layout: str = "list"


@dataclass
class Layout:
    font_size: float = 13.0
    line_height: float = 1.55
    padding: float = 22.0
    gap: float = 26.0
    chrome: bool = True
    chrome_height: float = 30.0
    radius: float = 8.0
    key_width: int = 13
    panel_align: str = "top"
    art_font_size: float | None = None
    leaders: bool = False
    panel_chars: int = 0
    title_rule: str = "under"
    art_caption: str = ""
    caption_font_size: float = 10.0
    caption_gap: float = 14.0
    interest_column_gap: int = 5

    @property
    def char_width(self) -> float:
        return self.font_size * CHAR_WIDTH_RATIO

    @property
    def text_line(self) -> float:
        return self.font_size * self.line_height

    @property
    def art_size(self) -> float:
        return self.art_font_size or self.font_size

    @property
    def art_char_width(self) -> float:
        return self.art_size * CHAR_WIDTH_RATIO

    @property
    def art_line(self) -> float:
        return self.art_size


def _art_svg(art: Art, x0: float, y0: float, lay: Layout) -> list[str]:
    cw, lh = lay.art_char_width, lay.art_line
    out = []

    rects: list[str] = []
    solid: list[list[bool]] = [[False] * len(row) for row in art.rows]

    for r, row in enumerate(art.rows):
        c = 0
        while c < len(row):
            bg = row[c].bg

            if bg is None:
                c += 1
                continue

            full = row[c].color == bg
            start = c

            while (
                c < len(row)
                and row[c].bg == bg
                and (row[c].color == bg) == full
            ):
                solid[r][c] = full
                c += 1

            rects.append(
                f'<rect x="{n(x0 + start * cw)}" y="{n(y0 + r * lh)}" '
                f'width="{n((c - start) * cw)}" height="{n(lh)}" fill="{bg}"/>'
            )

    if rects:
        out.append('<g shape-rendering="crispEdges">')
        out.extend(rects)
        out.append("</g>")

    for r, row in enumerate(art.rows):
        y = y0 + r * lh + lh * 0.82
        spans: list[str] = []
        run_start, run_color, run_chars = 0, None, []

        def flush():
            if run_chars and run_color:
                spans.append(
                    f'<tspan x="{n(x0 + run_start * cw)}" fill="{run_color}">'
                    f"{escape(''.join(run_chars))}</tspan>"
                )

        for c, cell in enumerate(row):
            if solid[r][c]:
                flush()
                run_start, run_color, run_chars = c + 1, None, []
                continue

            if cell.color != run_color:
                flush()
                run_start, run_color, run_chars = c, cell.color, [cell.char]
            else:
                run_chars.append(cell.char)

        flush()

        if spans:
            out.append(
                f'<text y="{n(y)}" font-size="{n(lay.art_size)}">'
                f'{"".join(spans)}</text>'
            )

    return out


def _grid_metrics(
    fields: list[tuple[str | None, str]],
    gap: int,
) -> tuple[int, int, int]:
    items = [value for _, value in fields]
    left_width = max(
        (len(item) for item in items[::2]),
        default=0,
    )
    right_width = max(
        (len(item) for item in items[1::2]),
        default=0,
    )
    total_width = left_width + gap + right_width
    rows = (len(items) + 1) // 2

    return left_width, total_width, rows


def _panel_svg(
    sections: list[Section],
    x0: float,
    y0: float,
    lay: Layout,
    theme: Theme,
) -> tuple[list[str], float, int]:
    cw, lh = lay.char_width, lay.text_line
    out: list[str] = []
    row = 0
    widest = 0
    width_chars = lay.panel_chars or 0

    for section_index, section in enumerate(sections):
        if section_index:
            row += 0.5

        if section.title is not None:
            y = y0 + row * lh + lh * 0.75

            if lay.title_rule == "inline" and width_chars:
                rule = "─" * max(
                    0,
                    width_chars - len(section.title) - 1,
                )
                out.append(
                    f'<text y="{n(y)}">'
                    f'<tspan x="{n(x0)}" fill="{theme.title}" font-weight="bold">'
                    f"{escape(section.title)}</tspan>"
                    f'<tspan x="{n(x0 + (len(section.title) + 1) * cw)}" '
                    f'fill="{theme.separator}">{escape(rule)}</tspan>'
                    f'</text>'
                )
                widest = max(widest, width_chars)
                row += 1
            else:
                out.append(
                    f'<text x="{n(x0)}" y="{n(y)}" fill="{theme.title}" '
                    f'font-weight="bold">{escape(section.title)}</text>'
                )
                widest = max(widest, len(section.title))
                row += 1

                y = y0 + row * lh + lh * 0.75
                rule = "─" * max(len(section.title), 1)
                out.append(
                    f'<text x="{n(x0)}" y="{n(y)}" '
                    f'fill="{theme.separator}">{escape(rule)}</text>'
                )
                row += 1

        if section.layout == "grid":
            items = [value for _, value in section.fields]
            left_width, total_width, grid_rows = _grid_metrics(
                section.fields,
                lay.interest_column_gap,
            )

            for index in range(grid_rows):
                left = items[index * 2]
                y = y0 + row * lh + lh * 0.75

                spans = [
                    f'<tspan x="{n(x0)}" fill="{theme.value}">'
                    f'{escape(left)}</tspan>'
                ]

                right_index = index * 2 + 1

                if right_index < len(items):
                    right = items[right_index]
                    right_x = x0 + (
                        left_width + lay.interest_column_gap
                    ) * cw

                    spans.append(
                        f'<tspan x="{n(right_x)}" fill="{theme.value}">'
                        f'{escape(right)}</tspan>'
                    )

                out.append(f'<text y="{n(y)}">{"".join(spans)}</text>')
                row += 1

            widest = max(widest, total_width)
            continue

        for key, value in section.fields:
            lines = value.splitlines() or [""]

            for line_index, line in enumerate(lines):
                y = y0 + row * lh + lh * 0.75

                if key is None:
                    out.append(
                        f'<text x="{n(x0)}" y="{n(y)}" '
                        f'fill="{theme.value}">{escape(line)}</text>'
                    )
                    widest = max(widest, len(line))

                elif lay.leaders and width_chars:
                    label = (
                        f"{key}:"
                        if key and line_index == 0
                        else ""
                    )
                    gap_start = len(label) + 1
                    gap_end = width_chars - len(line) - 1
                    dots = "." * max(0, gap_end - gap_start)
                    spans = []

                    if label:
                        spans.append(
                            f'<tspan x="{n(x0)}" fill="{theme.key}" '
                            f'font-weight="bold">{escape(label)}</tspan>'
                        )

                    if dots:
                        spans.append(
                            f'<tspan x="{n(x0 + gap_start * cw)}" '
                            f'fill="{theme.separator}">{dots}</tspan>'
                        )

                    spans.append(
                        f'<tspan x="{n(x0 + (width_chars - len(line)) * cw)}" '
                        f'fill="{theme.value}">{escape(line)}</tspan>'
                    )

                    out.append(f'<text y="{n(y)}">{"".join(spans)}</text>')
                    widest = max(widest, width_chars)

                else:
                    vx = x0 + lay.key_width * cw
                    label = (
                        f'<tspan x="{n(x0)}" fill="{theme.key}" '
                        f'font-weight="bold">{escape(key)}</tspan>'
                        if key and line_index == 0
                        else ""
                    )

                    out.append(
                        f'<text y="{n(y)}">{label}'
                        f'<tspan x="{n(vx)}" fill="{theme.value}">'
                        f'{escape(line)}</tspan></text>'
                    )
                    widest = max(
                        widest,
                        lay.key_width + len(line),
                    )

                row += 1

    return out, row * lh, widest


def build(
    art: Art | None,
    sections: list[Section],
    theme: Theme,
    lay: Layout | None = None,
    title: str = "",
) -> str:
    lay = lay or Layout()

    top = lay.padding + (
        lay.chrome_height if lay.chrome else 0
    )

    art_w = art.width * lay.art_char_width if art else 0.0
    art_h = art.height * lay.art_line if art else 0.0

    caption_lines = (
        lay.art_caption.splitlines()
        if lay.art_caption
        else []
    )
    caption_line_height = lay.caption_font_size * 1.4
    caption_h = (
        lay.caption_gap + len(caption_lines) * caption_line_height
        if caption_lines
        else 0.0
    )
    art_total_h = art_h + caption_h

    panel_x = lay.padding + (
        art_w + lay.gap if art else 0
    )

    _, panel_h, panel_chars = _panel_svg(
        sections,
        panel_x,
        top,
        lay,
        theme,
    )

    panel_y = top

    if lay.panel_align == "middle" and art_total_h > panel_h:
        panel_y = top + (art_total_h - panel_h) / 2
    elif lay.panel_align not in ("top", "middle"):
        raise ValueError(
            f"panel_align must be 'top' or 'middle', got {lay.panel_align!r}"
        )

    panel_lines, _, _ = _panel_svg(
        sections,
        panel_x,
        panel_y,
        lay,
        theme,
    )

    panel_w = panel_chars * lay.char_width
    width = panel_x + panel_w + lay.padding
    height = top + max(art_total_h, panel_h) + lay.padding

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{width:.0f}" height="{height:.0f}" '
        f'viewBox="0 0 {width:.0f} {height:.0f}" role="img" '
        f'aria-label="{escape(title or "terminal profile card")}">',
        f"<title>{escape(title or 'profile card')}</title>",
        f'<rect width="{width:.0f}" height="{height:.0f}" '
        f'rx="{lay.radius}" fill="{theme.background}" '
        f'stroke="{theme.border}"/>',
    ]

    if lay.chrome:
        parts.append(
            f'<path d="M0 {lay.radius} '
            f'A{lay.radius} {lay.radius} 0 0 1 {lay.radius} 0 '
            f'H{width - lay.radius:.0f} '
            f'A{lay.radius} {lay.radius} 0 0 1 {width:.0f} {lay.radius} '
            f'V{lay.chrome_height} H0 Z" fill="{theme.chrome}"/>'
        )

        for index, colour in enumerate(
            ("#ff5f56", "#ffbd2e", "#27c93f")
        ):
            parts.append(
                f'<circle cx="{18 + index * 18}" '
                f'cy="{lay.chrome_height / 2:.0f}" '
                f'r="5.5" fill="{colour}"/>'
            )

        if title:
            parts.append(
                f'<text x="{width / 2:.0f}" '
                f'y="{lay.chrome_height / 2 + 4:.0f}" '
                f'text-anchor="middle" fill="{theme.value}" '
                f'opacity="0.65" font-size="{lay.font_size - 1:.0f}">'
                f'{escape(title)}</text>'
            )

    parts.append(
        f'<g font-family="{FONT_STACK}" '
        f'font-size="{lay.font_size}" '
        f'xml:space="preserve" dominant-baseline="alphabetic">'
    )

    if art:
        parts.extend(
            _art_svg(art, lay.padding, top, lay)
        )

    if caption_lines and art:
        caption_x = lay.padding + art_w / 2
        caption_y = top + art_h + lay.caption_gap

        for index, line in enumerate(caption_lines):
            y = caption_y + index * caption_line_height

            parts.append(
                f'<text x="{n(caption_x)}" y="{n(y)}" '
                f'text-anchor="middle" fill="{theme.value}" '
                f'font-size="{n(lay.caption_font_size)}">'
                f'{escape(line)}</text>'
            )

    parts.extend(panel_lines)
    parts.extend(["</g>", "</svg>"])

    return "\n".join(parts) + "\n"
