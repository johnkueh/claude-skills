#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["click>=8.0", "Pillow>=10.0"]
# ///
"""Generate podcast artwork + shownotes from a rendered video.

Consumes:
    video/scripts/{slug}.json   (scene script)
    {out}/images/scene-01.webp  (first scene as artwork source)

Produces:
    {out}/artwork/episode-3000.jpg   (3000×3000 square JPG for Apple/Spotify)
    {out}/podcast/shownotes.md       (markdown with frontmatter + body)

Usage:
    uv run podcast.py \\
        --script /path/to/video-script.json \\
        --out /path/to/video-output-dir \\
        --source-article-slug food-noise \\
        --episode-number 1
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import click
from PIL import Image, ImageDraw, ImageFilter


ARTWORK_SIZE = 3000
ARTWORK_QUALITY = 75  # tuned to keep 3000x3000 artwork under Apple's 500 KB recommendation


def square_crop(img: Image.Image) -> Image.Image:
    """Center-crop an image to square based on its shorter side."""
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    return img.crop((left, top, left + side, top + side))


def build_artwork(scene1_path: Path, out_path: Path) -> int:
    """Load scene-1, square-crop, resize to 3000, save as high-quality JPG. Returns file size in KB."""
    img = Image.open(scene1_path).convert("RGB")
    img = square_crop(img)
    img = img.resize((ARTWORK_SIZE, ARTWORK_SIZE), Image.LANCZOS)

    # Soft vignette — keeps podcast thumbnails from blending with surrounding UI
    vignette = Image.new("L", (ARTWORK_SIZE, ARTWORK_SIZE), 255)
    draw = ImageDraw.Draw(vignette)
    draw.ellipse((-300, -300, ARTWORK_SIZE + 300, ARTWORK_SIZE + 300), fill=255)
    vignette = vignette.filter(ImageFilter.GaussianBlur(radius=200))
    img.putalpha(vignette)
    bg = Image.new("RGB", (ARTWORK_SIZE, ARTWORK_SIZE), (248, 243, 234))  # cream background
    bg.paste(img, (0, 0), img)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    bg.save(out_path, "JPEG", quality=ARTWORK_QUALITY, optimize=True, progressive=True)
    return out_path.stat().st_size // 1024


def format_duration(seconds: float) -> str:
    """Format seconds as H:MM:SS or MM:SS."""
    total = int(round(seconds))
    hours = total // 3600
    mins = (total % 3600) // 60
    secs = total % 60
    if hours:
        return f"{hours}:{mins:02d}:{secs:02d}"
    return f"{mins}:{secs:02d}"


def build_shownotes(
    script: dict,
    episode_number: int,
    source_article_slug: str,
    duration_seconds: float,
) -> str:
    """Build markdown shownotes from scene script data."""
    video_title = script.get("video_title", "")
    video_description = script.get("video_description_draft", "")
    scenes = script.get("scenes", [])

    pub_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Pull a list of the cited primary sources across all scene overlays
    citations = []
    for scene in scenes:
        overlay = scene.get("overlay") or {}
        cite = overlay.get("citation") or ""
        if cite and cite not in citations:
            citations.append(cite)

    # Chapters derived from scene start times
    chapters = []
    running = 0.0
    for s in scenes:
        section = (s.get("section") or f"scene-{s['id']:02d}").replace("_", " ").title()
        chapters.append({"time_s": running, "label": section})
        # duration derived from alignment if build_props ran; fall back to scene.end - scene.start
        running += max(1.0, (s.get("end", 0) - s.get("start", 0)))

    lines = []
    lines.append("---")
    lines.append(f"episode_number: {episode_number}")
    lines.append(f'title: "{video_title}"')
    lines.append(f"pub_date: {pub_date}")
    lines.append(f"duration_seconds: {round(duration_seconds)}")
    lines.append(f"duration_human: {format_duration(duration_seconds)}")
    lines.append(f"source_article_slug: {source_article_slug}")
    lines.append("---")
    lines.append("")

    # The video_description_draft already has chapters + CTA. Use it as the base.
    if video_description:
        lines.append(video_description.strip())
        lines.append("")

    # Append primary sources (always)
    if citations:
        lines.append("## Sources")
        lines.append("")
        for c in citations:
            lines.append(f"- {c}")
        lines.append("")

    # Full-transcript callback
    lines.append("## Full transcript")
    lines.append("")
    lines.append(f"Read the full episode transcript + article version at https://www.glp3.wiki/podcast/{source_article_slug}")
    lines.append("")

    # Disclaimer
    lines.append("---")
    lines.append("")
    lines.append("*Retatrutide is an investigational drug and has not been approved by the FDA. This content is for informational purposes only and is not medical advice.*")

    return "\n".join(lines)


@click.command()
@click.option("--script", "script_path", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--out", "out_dir", required=True, type=click.Path(exists=True, file_okay=False))
@click.option("--source-article-slug", required=True, help="The glp3.wiki article slug this episode is derived from")
@click.option("--episode-number", required=True, type=int)
def build(script_path: str, out_dir: str, source_article_slug: str, episode_number: int):
    """Generate podcast artwork + shownotes for a rendered video."""
    out = Path(out_dir)
    script = json.loads(Path(script_path).read_text())

    # Artwork from scene-1
    scene1 = out / "images" / "scene-01.webp"
    if not scene1.exists():
        click.echo(f"Error: {scene1} not found — images must be rendered first", err=True)
        sys.exit(1)
    artwork_path = out / "artwork" / "episode-3000.jpg"
    size_kb = build_artwork(scene1, artwork_path)
    click.echo(f"Artwork: {artwork_path} ({size_kb} KB)", err=True)
    if size_kb > 500:
        click.echo(f"⚠  Artwork > 500 KB — Apple recommends <500 KB. Consider reducing ARTWORK_QUALITY.", err=True)

    # Duration — prefer props.json (accurate per audio), fall back to script total_words / wpm heuristic
    props_path = out / "props.json"
    if props_path.exists():
        props = json.loads(props_path.read_text())
        duration_seconds = float(props.get("totalSeconds", 0)) or 300.0
    else:
        duration_seconds = float(script.get("target_duration_seconds", 300))

    # Shownotes
    notes = build_shownotes(script, episode_number, source_article_slug, duration_seconds)
    notes_path = out / "podcast" / "shownotes.md"
    notes_path.parent.mkdir(parents=True, exist_ok=True)
    notes_path.write_text(notes)
    click.echo(f"Shownotes: {notes_path}", err=True)
    click.echo(f"Duration: {format_duration(duration_seconds)} ({round(duration_seconds)}s)", err=True)


if __name__ == "__main__":
    build()
