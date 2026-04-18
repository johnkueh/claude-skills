#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["click>=8.0", "google-genai>=0.3"]
# ///
"""Nano Banana (Gemini 2.5 Flash Image) scene generator for video scripts.

Reads a scene script JSON, generates one 16:9 scene image per scene
using an optional style reference image for visual consistency.

Usage:
    GEMINI_API_KEY=... uv run images.py generate \\
        --script /path/to/scene-script.json \\
        --out /path/to/output-dir \\
        --reference /path/to/style-ref.webp
"""

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import click
from google import genai
from google.genai import types

MODEL = "gemini-2.5-flash-image"

DEFAULT_STYLE_PROMPT = """The attached image shows the painting MEDIUM and STYLE to match — soft transparent alcohol ink / watercolor on cream paper, Helen Frankenthaler soak-stain technique. Match only the medium, not the composition.

Now generate a COMPLETELY DIFFERENT painting in that same medium to illustrate this scene:

{subject}

Technique rules:
- Transparent diluted washes on cream/off-white paper
- 30-50% of canvas is bare background — generous negative space
- No black, no dark borders, no heavy saturated pigment
- Soft organic edges where colors bleed into paper

The image must contain NO text, letters, words, numbers, or writing of any kind — overlays are added separately in post. 16:9 landscape, editorial quality, suitable as a video scene frame.
"""

NO_REFERENCE_PROMPT = """A watercolor painting inspired by Helen Frankenthaler's soak-stain technique, illustrating this scene:

{subject}

Technique:
- Transparent diluted washes on cream/off-white paper
- 30-50% bare background — generous negative space
- Soft organic edges, muted palette

The image must contain NO text, letters, words, numbers, or writing. 16:9 landscape, editorial quality, suitable as a video scene frame.
"""


def generate_one(client: genai.Client, scene: dict, ref_bytes: bytes | None, ref_mime: str, out_path: Path, style_prompt: str) -> tuple[int, bool, str]:
    sid = scene["id"]
    subject = scene["visual_brief"]

    parts = []
    if ref_bytes:
        parts.append(types.Part.from_bytes(data=ref_bytes, mime_type=ref_mime))
    parts.append(types.Part.from_text(text=style_prompt.format(subject=subject)))

    config = types.GenerateContentConfig(
        response_modalities=["IMAGE"],
        image_config=types.ImageConfig(aspect_ratio="16:9"),
    )

    try:
        resp = client.models.generate_content(
            model=MODEL,
            contents=[types.Content(role="user", parts=parts)],
            config=config,
        )
        for part in resp.parts:
            if part.inline_data and part.inline_data.data:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(part.inline_data.data)
                return sid, True, f"{len(part.inline_data.data)//1024} KB"
        return sid, False, "no image in response"
    except Exception as e:
        return sid, False, str(e)


@click.group()
def cli():
    """Nano Banana scene generator."""
    pass


@cli.command()
@click.option("--script", "script_path", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--out", "out_dir", required=True, type=click.Path())
@click.option("--reference", default=None, type=click.Path(exists=True, dir_okay=False), help="Style reference image path")
@click.option("--scene", type=int, default=None, help="Regenerate only this scene id")
@click.option("--force/--no-force", default=False, help="Regenerate even if image exists")
@click.option("--workers", default=4, help="Parallel generations")
def generate(script_path: str, out_dir: str, reference: str | None, scene: int | None, force: bool, workers: int):
    """Generate scene images from a script."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        click.echo("Error: GEMINI_API_KEY not set", err=True)
        sys.exit(1)

    script = json.loads(Path(script_path).read_text())
    scenes = script["scenes"]

    ref_bytes = None
    ref_mime = "image/webp"
    style_prompt = NO_REFERENCE_PROMPT
    if reference:
        ref_path = Path(reference)
        ref_bytes = ref_path.read_bytes()
        suffix = ref_path.suffix.lower()
        ref_mime = "image/webp" if suffix == ".webp" else f"image/{suffix.lstrip('.')}"
        style_prompt = DEFAULT_STYLE_PROMPT

    out_path = Path(out_dir) / "images"
    out_path.mkdir(parents=True, exist_ok=True)

    targets = []
    for s in scenes:
        if scene is not None and s["id"] != scene:
            continue
        scene_out = out_path / f"scene-{s['id']:02d}.webp"
        if scene_out.exists() and not force:
            click.echo(f"  scene {s['id']:02d}: cached", err=True)
            continue
        targets.append((s, scene_out))

    if not targets:
        click.echo("Nothing to generate.", err=True)
        return

    click.echo(f"script: {script_path}", err=True)
    click.echo(f"reference: {reference or '(none — using no-reference prompt)'}", err=True)
    click.echo(f"scenes to generate: {len(targets)} (parallel: {workers})", err=True)
    click.echo(f"estimated cost: ${len(targets) * 0.04:.2f}\n", err=True)

    client = genai.Client(api_key=api_key)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(generate_one, client, s, ref_bytes, ref_mime, p, style_prompt): s["id"] for s, p in targets}
        for fut in as_completed(futures):
            sid, ok, info = fut.result()
            mark = "✓" if ok else "✗"
            click.echo(f"  {mark} scene {sid:02d}: {info}", err=True)

    click.echo(f"\nImages in: {out_path}", err=True)


if __name__ == "__main__":
    cli()
