#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["click>=8.0", "google-genai>=0.3", "Pillow>=10.0"]
# ///
"""Generate a 1280x720 YouTube thumbnail — "minimal bloom" template.

Two-step pipeline:
  1. Gemini 2.5 Flash Image generates a watercolor base — a small deep-rose
     bloom contained to the LOWER-LEFT THIRD with a modern auto-injector pen
     silhouette inside it. Rest of the canvas is empty cream paper.
  2. Pillow overlays:
       - Headline (big Impact near-black) centered in the right two-thirds
       - Optional subhead (Impact plum, all-caps) below headline
       - Brand mark bottom-right: blue circle + "GLP-3 Wiki" in Inter Bold

Design decisions (derived from 2026 thumbnail research + iteration):
  - High contrast: headline in near-black (#1a1a1a) on cream (~14:1 ratio),
    not plum (which was ~3:1 and failed the contrast threshold).
  - Single dominant focal: just the number. Subhead is OPTIONAL — only adds
    value for cold audiences on a 0-sub channel. Drop it once we have brand
    recognition.
  - Bloom contained to lower-left 1/3 so the headline gets massive negative
    space. Competitor thumbnails in this niche are face-led and cluttered;
    our editorial-illustration restraint is the differentiator (Kurzgesagt /
    Vox crushed on views with similar minimalism).
  - Brand mark matches the site nav: tailwind blue-500 circle + Inter Bold
    "GLP-3 Wiki" (not all-caps) in near-black.

Defaults (pull from script.thumbnail or scene[0].overlay):
  headline → script.thumbnail.headline OR scene[0].overlay.headline
  subhead  → script.thumbnail.subhead  OR scene[0].overlay.subhead (if short)
  brand    → "GLP-3 Wiki"

Override via CLI flags. Pass --no-subhead to force minimal layout.

One-time setup — Inter font is required:
  curl -sL https://github.com/rsms/inter/releases/download/v4.0/Inter-4.0.zip -o /tmp/Inter.zip
  unzip -q /tmp/Inter.zip -d /tmp/Inter
  cp /tmp/Inter/extras/ttf/Inter-Bold.ttf ~/Library/Fonts/

Output: 1280x720 JPG, quality 90, typically 100-200 KB.
"""

import json
import os
import sys
from io import BytesIO
from pathlib import Path

import click
from google import genai
from google.genai import types
from PIL import Image, ImageDraw, ImageFont

MODEL = "gemini-2.5-flash-image"
TARGET_SIZE = (1280, 720)
JPEG_QUALITY = 90

# Palette (matches site)
NEAR_BLACK = (26, 26, 26)   # headline — high contrast on cream
PLUM = (74, 21, 32)         # subhead accent
NAV_TEXT = (28, 25, 23)     # brand text (matches site nav)
BLUE_500 = (59, 130, 246)   # brand dot — tailwind blue-500

IMPACT = "/System/Library/Fonts/Supplemental/Impact.ttf"
HELVETICA = "/System/Library/Fonts/Helvetica.ttc"
INTER_BOLD = str(Path.home() / "Library/Fonts/Inter-Bold.ttf")

BASE_PROMPT = """The attached image shows the painting MEDIUM to match — soft transparent watercolor on cream paper.

Generate a 16:9 LANDSCAPE YouTube thumbnail base. Composition is intentionally minimal. THE ENTIRE CANVAS uses ONE single uniform cream paper texture with no seams, no divisions, no panels — it is one continuous sheet of cream paper.

LAYOUT:
- LOWER-LEFT THIRD: a single watercolor bloom in deep crimson rose. Soft organic edges. Bloom diameter is about 1/4 of the canvas width. Position: centered around (x=18%, y=70%) of the canvas.
- INSIDE the bloom: a clean, instantly-recognizable silhouette of a MODERN AUTO-INJECTOR INSULIN PEN (long, slim, vertical cylinder with a thin needle tip and a button cap on top — like an Ozempic or Mounjaro pen — NOT a vintage syringe with a finger-grip plunger). {subject_accent} Sage green watercolor wash. Pen height ≈ 1.5x the bloom radius.
- EVERYWHERE ELSE: pure empty cream paper, one continuous surface, no marks, no splatter, no wash, no seams.

Rules:
- Single uniform cream paper background (#fdf8f2) — NO vertical or horizontal seams or color divisions
- Generous negative space, especially the upper-right two-thirds
- High contrast — deep rose bloom must POP against cream
- NO text, NO letters, NO numbers, NO brand marks
- No hard borders, no frames

Output: 16:9 landscape, one continuous cream paper, small dramatic bloom + modern auto-injector pen in lower-left, rest empty."""


def build_base_prompt(script: dict) -> str:
    """The hero subject is always the auto-injector pen; scene 1's visual brief
    can tune the mood but should not alter the layout or override the pen."""
    scenes = script.get("scenes") or []
    first = scenes[0] if scenes else {}
    brief = (first.get("visual_brief") or "").strip()
    # Treat scene brief as an accent hint only; the layout is fixed.
    accent = f"(Scene mood reference: {brief[:180]})" if brief else ""
    return BASE_PROMPT.format(subject_accent=accent)


def crop_to_16_9(img: Image.Image) -> Image.Image:
    w, h = img.size
    target_ratio = 16 / 9
    if w / h > target_ratio:
        new_w = int(h * target_ratio)
        return img.crop(((w - new_w) // 2, 0, (w - new_w) // 2 + new_w, h))
    new_h = int(w / target_ratio)
    return img.crop((0, (h - new_h) // 2, w, (h - new_h) // 2 + new_h))


def fit_font_width(text: str, font_path: str, max_size: int, max_width: int,
                   draw: ImageDraw.ImageDraw) -> ImageFont.FreeTypeFont:
    """Largest font size ≤ max_size whose text fits within max_width."""
    size = max_size
    while size > 24:
        font = ImageFont.truetype(font_path, size)
        bbox = draw.textbbox((0, 0), text, font=font)
        if (bbox[2] - bbox[0]) <= max_width:
            return font
        size -= 8
    return font


def derive_text(script: dict) -> tuple[str, str, str]:
    """headline, subhead, brand from script.thumbnail or scene[0].overlay."""
    thumb = script.get("thumbnail") or {}
    scenes = script.get("scenes") or []
    overlay = (scenes[0] if scenes else {}).get("overlay") or {}

    headline = thumb.get("headline") or overlay.get("headline") or ""
    # Subhead is optional — auto-shorten long scene-1 subheads or require
    # an explicit override via script.thumbnail.subhead for thumbnail copy.
    raw_subhead = thumb.get("subhead") or overlay.get("subhead") or ""
    subhead = raw_subhead if len(raw_subhead) <= 16 else ""
    brand = thumb.get("brand") or "GLP-3 Wiki"
    return headline, subhead, brand


def draw_brand_mark(draw: ImageDraw.ImageDraw, canvas_w: int, canvas_h: int,
                    brand: str) -> None:
    """Blue circle + Inter Bold brand text, bottom-right (matches site nav)."""
    DOT_SIZE = 32
    GAP = 14
    FONT_SIZE = 36
    PAD_RIGHT = 36
    PAD_BOTTOM = 36

    if not Path(INTER_BOLD).exists():
        raise click.ClickException(
            f"Inter-Bold.ttf not found at {INTER_BOLD}. Install from "
            "https://github.com/rsms/inter/releases (see SKILL.md)."
        )

    font = ImageFont.truetype(INTER_BOLD, FONT_SIZE)
    bbox = draw.textbbox((0, 0), brand, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    block_right = canvas_w - PAD_RIGHT
    block_bottom = canvas_h - PAD_BOTTOM
    block_h = max(DOT_SIZE, text_h)
    block_left = block_right - (DOT_SIZE + GAP + text_w)

    dot_y_center = block_bottom - block_h // 2
    draw.ellipse(
        [block_left, dot_y_center - DOT_SIZE // 2,
         block_left + DOT_SIZE, dot_y_center + DOT_SIZE // 2],
        fill=BLUE_500,
    )
    text_x = block_left + DOT_SIZE + GAP
    text_y = dot_y_center - text_h // 2 - bbox[1]
    draw.text((text_x, text_y), brand, font=font, fill=NAV_TEXT)


def render_overlay(img: Image.Image, headline: str, subhead: str,
                   brand: str) -> Image.Image:
    draw = ImageDraw.Draw(img)
    RIGHT = 1280
    RIGHT_PAD = 50
    MAX_WIDTH = 820  # generous right-half cap

    if headline:
        max_size = 300 if not subhead else 280
        font_h = fit_font_width(headline, IMPACT, max_size, MAX_WIDTH, draw)
        bbox = draw.textbbox((0, 0), headline, font=font_h)
        text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = RIGHT - text_w - RIGHT_PAD
        y = 230 if subhead else (720 - text_h) // 2 - 50
        draw.text((x, y), headline, font=font_h, fill=NEAR_BLACK)

        if subhead:
            sub_text = subhead.upper()
            font_s = fit_font_width(sub_text, IMPACT, 80, MAX_WIDTH, draw)
            bbox_s = draw.textbbox((0, 0), sub_text, font=font_s)
            x_s = RIGHT - (bbox_s[2] - bbox_s[0]) - RIGHT_PAD
            draw.text((x_s, y + text_h + 30), sub_text, font=font_s, fill=PLUM)

    if brand:
        draw_brand_mark(draw, 1280, 720, brand)

    return img


def gemini_base(script: dict, reference_path: Path) -> Image.Image:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise click.ClickException("GEMINI_API_KEY env var required")
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=MODEL,
        contents=[
            types.Part.from_bytes(data=reference_path.read_bytes(), mime_type="image/webp"),
            build_base_prompt(script),
        ],
    )
    for part in response.candidates[0].content.parts:
        if getattr(part, "inline_data", None) and part.inline_data.data:
            img = Image.open(BytesIO(part.inline_data.data)).convert("RGB")
            return crop_to_16_9(img).resize(TARGET_SIZE, Image.LANCZOS)
    raise click.ClickException("Gemini returned no image")


@click.group()
def cli():
    """Thumbnail CLI."""


@cli.command()
@click.option("--script", "script_path", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--reference", "reference_path", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--out", "out_path", required=True, type=click.Path())
@click.option("--headline", default=None, help="Big text. Default: script.thumbnail.headline or scene[0].overlay.headline")
@click.option("--subhead", default=None, help="Optional small line under headline (kept short, ≤16 chars recommended).")
@click.option("--no-subhead", is_flag=True, help="Force minimal layout (headline + brand only).")
@click.option("--brand", default=None, help="Brand mark text. Default: 'GLP-3 Wiki'")
@click.option("--keep-base/--no-keep-base", default=False, help="Save the pre-text base image alongside.")
def generate(script_path: str, reference_path: str, out_path: str,
             headline: str | None, subhead: str | None, no_subhead: bool,
             brand: str | None, keep_base: bool):
    """Generate a 1280x720 JPG thumbnail with minimal text overlay."""
    script = json.loads(Path(script_path).read_text())
    h, s, b = derive_text(script)
    h = headline if headline is not None else h
    if no_subhead:
        s = ""
    elif subhead is not None:
        s = subhead
    b = brand if brand is not None else b

    base = gemini_base(script, Path(reference_path))
    if keep_base:
        base_path = Path(out_path).with_suffix(".base.jpg")
        base.save(base_path, "JPEG", quality=JPEG_QUALITY, optimize=True)
        click.echo(f"Wrote base {base_path} ({base_path.stat().st_size // 1024} KB)", err=True)

    final = render_overlay(base.copy(), h, s, b)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    final.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True)
    click.echo(f"Wrote {out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    cli()
