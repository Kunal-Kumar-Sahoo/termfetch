"""Command line entry point."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import textwrap
from pathlib import Path

from . import __version__
from . import art as art_mod
from . import gh, svg, theme as theme_mod


UNRESOLVED = re.compile(r"\{\{[a-zA-Z_][a-zA-Z0-9_]*\}\}")

DEFAULTS: dict = {
    "image": None,
    "imageCrop": None,
    "imageCols": 56,
    "charset": "blocks",
    "coloredImage": True,
    "contrast": 1.2,
    "brightness": 1.0,
    "gamma": 1.05,
    "colorStep": 8,
    "invert": False,
    "shadowLift": 0.0,
    "preserveForeground": False,
    "theme": "github-dark",
    "colors": None,
    "windowTitle": "{{username}}@github",
    "chrome": True,
    "fontSize": 13,
    "artFontSize": None,
    "keyWidth": 13,
    "panelAlign": "top",
    "leaders": False,
    "panelChars": 0,
    "titleRule": "under",
    "valueWrap": 0,
    "imageCaption": None,
    "captionFontSize": 10,
    "captionGap": 14,
    "interestColumnGap": 5,
    "github": None,
    "languageMode": "repos",
    "topLanguages": 5,
    "sections": [],
}


def load_config(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    unknown = set(raw) - set(DEFAULTS)

    if unknown:
        raise SystemExit(f"unknown config keys: {sorted(unknown)}")

    cfg = {**DEFAULTS, **raw}

    if not isinstance(cfg["sections"], list) or not cfg["sections"]:
        raise SystemExit("config needs a non-empty 'sections' array")

    return cfg


def wrap_value(value: str, width: int) -> list[str]:
    lines = []

    for line in value.splitlines():
        if not line:
            lines.append("")
            continue

        lines.extend(
            textwrap.wrap(
                line,
                width=width,
                break_long_words=True,
                break_on_hyphens=False,
            )
        )

    return lines or [value]


def build_sections(
    cfg: dict,
    variables: dict[str, str],
) -> list[svg.Section]:
    out = []

    # Minimal configurations used by callers and tests may omit these keys.
    panel_width = int(cfg.get("panelChars", DEFAULTS["panelChars"]) or 0)
    explicit_wrap = int(cfg.get("valueWrap", DEFAULTS["valueWrap"]) or 0)
    use_leaders = bool(cfg.get("leaders", DEFAULTS["leaders"]))

    for raw in cfg.get("sections", []):
        title = raw.get("title")

        if title is not None:
            title = gh.apply_templates(str(title), variables)

        section_layout = str(raw.get("layout", "list"))
        fields = []

        for field in raw.get("fields", []):
            if isinstance(field, str):
                key, value = None, field
            elif isinstance(field, (list, tuple)) and len(field) == 2:
                key, value = field
            elif isinstance(field, dict):
                key = field.get("key", "")
                value = field.get("value", "")
            else:
                raise SystemExit(f"bad field entry: {field!r}")

            value = gh.apply_templates(str(value), variables)

            if not value.strip() or UNRESOLVED.search(value):
                continue

            # Explicit valueWrap takes precedence. Otherwise, calculate the
            # available value width from the fixed leader-style panel.
            wrap_width = explicit_wrap

            if (
                wrap_width <= 0
                and use_leaders
                and panel_width > 0
                and key is not None
            ):
                label_width = len(str(key)) + 1 if key else 0
                wrap_width = max(1, panel_width - label_width - 2)

            # Plain string fields span the full panel and are not wrapped here.
            if (
                key is not None
                and wrap_width > 0
                and len(value) > wrap_width
            ):
                wrapped = wrap_value(value, wrap_width)

                fields.append((str(key), wrapped[0]))
                fields.extend(("", part) for part in wrapped[1:])
            else:
                fields.append((key if key is None else str(key), value))

        if fields or title:
            out.append(
                svg.Section(
                    title,
                    fields,
                    layout=section_layout,
                )
            )

    return out


def starter_config(
    username: str,
    image: str | None,
    theme: str = "github-dark",
) -> dict:
    return {
        "github": username,
        "image": image,
        "imageCols": 46,
        "charset": "blocks",
        "coloredImage": True,
        "contrast": 1.2,
        "gamma": 1.05,
        "theme": theme,
        "windowTitle": "{{username}}@github",
        "panelAlign": "middle",
        "valueWrap": 36,
        "languageMode": "repos",
        "topLanguages": 5,
        "sections": [
            {
                "title": "{{username}}@github",
                "fields": [
                    ["Name", "{{name}}"],
                    ["Location", "{{location}}"],
                    ["Bio", "{{bio}}"],
                    ["Member for", "{{uptime}}"],
                ],
            },
            {
                "title": "GitHub Stats",
                "fields": [
                    ["Repositories", "{{repos}}"],
                    ["Stars", "{{stars}}"],
                    ["Followers", "{{followers}}"],
                    ["Languages", "{{languages}}"],
                ],
            },
        ],
    }


def init_main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        prog="termfetch init",
        description="Create a starter configuration for a GitHub profile card.",
    )

    ap.add_argument(
        "--config",
        type=Path,
        default=Path("termfetch.json"),
        help="config path (default: termfetch.json)",
    )
    ap.add_argument(
        "--user",
        help="GitHub username; prompted for in an interactive terminal",
    )
    ap.add_argument(
        "--image",
        type=Path,
        help="portrait or logo to render; stored relative to the config",
    )
    ap.add_argument(
        "--theme",
        choices=sorted(theme_mod.THEMES),
        default="github-dark",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="replace an existing config",
    )

    args = ap.parse_args(argv)

    username = (args.user or "").strip()

    if not username and sys.stdin.isatty():
        username = input("GitHub username: ").strip()

    if not username:
        ap.error("--user is required when stdin is not interactive")

    image_arg = args.image

    if image_arg is None and sys.stdin.isatty():
        entered = input("Portrait or logo path (optional): ").strip()
        image_arg = Path(entered) if entered else None

    config_path = args.config.expanduser()

    if config_path.exists() and not args.force:
        ap.error(f"{config_path} already exists; use --force to replace it")

    image_value = None

    if image_arg is not None:
        image_path = image_arg.expanduser()

        if not image_path.is_file():
            ap.error(f"image not found: {image_path}")

        image_value = Path(
            os.path.relpath(
                image_path.resolve(),
                config_path.resolve().parent,
            )
        ).as_posix()

    config_path.parent.mkdir(parents=True, exist_ok=True)

    config_path.write_text(
        json.dumps(
            starter_config(username, image_value, args.theme),
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    print(f"wrote {config_path}")
    print(f"next: termfetch --config {config_path} --out termfetch.svg")

    return 0


def render_main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        prog="termfetch",
        description="Generate a neofetch-style GitHub profile card as SVG.",
        epilog="First time? Run 'termfetch init --help'.",
    )

    ap.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    ap.add_argument(
        "--config",
        type=Path,
        default=Path("termfetch.json"),
        help="config path (default: termfetch.json)",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=Path("termfetch.svg"),
        help="SVG output path (default: termfetch.svg)",
    )
    ap.add_argument(
        "--user",
        help="GitHub username (overrides config 'github')",
    )
    ap.add_argument(
        "--token",
        help="GitHub token; defaults to $GITHUB_TOKEN",
    )
    ap.add_argument(
        "--theme",
        help="override the config's theme",
    )
    ap.add_argument(
        "--invert",
        choices=("true", "false"),
        help="override the config's invert flag",
    )
    ap.add_argument(
        "--no-fetch",
        action="store_true",
        help="skip the GitHub API; leave variables blank",
    )
    ap.add_argument(
        "--preview",
        type=Path,
        help="also write a plain-text version of the art",
    )

    args = ap.parse_args(argv)

    cfg = load_config(args.config)

    if args.theme:
        cfg["theme"] = args.theme

    if args.invert:
        cfg["invert"] = args.invert == "true"

    base = args.config.parent

    variables: dict[str, str] = {}
    user = args.user or cfg.get("github")

    if user and not args.no_fetch:
        try:
            variables = gh.fetch(
                user,
                args.token or os.environ.get("GITHUB_TOKEN"),
                top_languages=int(cfg["topLanguages"]),
                language_mode=str(cfg["languageMode"]),
            )
        except gh.GitHubError as exc:
            print(
                f"warning: {exc}; rendering without live stats",
                file=sys.stderr,
            )
            variables = {
                "username": user,
                "name": user,
            }
    elif user:
        variables = {
            "username": user,
            "name": user,
        }

    picture = None
    active_theme = theme_mod.get(cfg["theme"])

    if cfg["image"]:
        image_path = Path(cfg["image"])

        if not image_path.is_absolute():
            image_path = base / image_path

        crop = cfg["imageCrop"]

        picture = art_mod.render(
            str(image_path),
            cols=int(cfg["imageCols"]),
            charset=cfg["charset"],
            colored=bool(cfg["coloredImage"]),
            mono_color=active_theme.mono,
            crop=tuple(crop) if crop else None,
            char_aspect=svg.CHAR_WIDTH_RATIO,
            contrast=float(cfg["contrast"]),
            brightness=float(cfg["brightness"]),
            gamma=float(cfg["gamma"]),
            color_step=int(cfg["colorStep"]),
            invert=bool(cfg["invert"]),
            background_color=active_theme.background,
            shadow_lift=float(cfg["shadowLift"]),
            preserve_foreground=bool(cfg["preserveForeground"]),
        )

    active = active_theme.merged(cfg["colors"])

    layout = svg.Layout(
        font_size=float(cfg["fontSize"]),
        chrome=bool(cfg["chrome"]),
        key_width=int(cfg["keyWidth"]),
        panel_align=str(cfg["panelAlign"]),
        art_font_size=(
            float(cfg["artFontSize"])
            if cfg["artFontSize"]
            else None
        ),
        leaders=bool(cfg["leaders"]),
        panel_chars=int(cfg.get("panelChars", DEFAULTS["panelChars"]) or 0),
        title_rule=str(cfg["titleRule"]),
        art_caption=cfg["imageCaption"],
        caption_font_size=float(cfg["captionFontSize"]),
        caption_gap=float(cfg["captionGap"]),
        interest_column_gap=float(cfg["interestColumnGap"]),
    )

    title = gh.apply_templates(
        str(cfg["windowTitle"] or ""),
        variables,
    )

    document = svg.build(
        picture,
        build_sections(cfg, variables),
        active,
        layout,
        title,
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(document, encoding="utf-8")

    print(f"wrote {args.out} ({len(document) // 1024} KB)")

    if args.preview and picture:
        args.preview.parent.mkdir(parents=True, exist_ok=True)
        args.preview.write_text(
            picture.as_text() + "\n",
            encoding="utf-8",
        )
        print(f"wrote {args.preview}")

    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if args[:1] == ["init"]:
        return init_main(args[1:])

    return render_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
