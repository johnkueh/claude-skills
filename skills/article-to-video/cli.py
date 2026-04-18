#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["click>=8.0"]
# ///
"""Unified CLI for article-to-video.

Pipeline: scene script JSON + reference image → MP4 + SRT + audio + images.

Subcommands:
    tts        Generate per-scene narration audio
    images     Generate per-scene watercolor images (Nano Banana)
    props      Build Remotion props.json + captions.srt from audio alignments
    render     Run Remotion to produce final.mp4 (requires `npm install` in this dir)
    all        Run tts → images → props → render sequentially

Usage:
    uv run cli.py all \\
        --script /path/to/script.json \\
        --ref /path/to/style-reference.webp \\
        --out /path/to/output-dir

Environment:
    ELEVENLABS_API_KEY    Required for tts / all
    GEMINI_API_KEY        Required for images / all
"""

import subprocess
import sys
from pathlib import Path

import click

SKILL_DIR = Path(__file__).resolve().parent
CLI_DIR = SKILL_DIR / "cli"


def run(cmd: list[str], cwd: Path | None = None) -> None:
    click.echo(f"\n$ {' '.join(str(c) for c in cmd)}", err=True)
    result = subprocess.run(cmd, cwd=cwd)
    if result.returncode != 0:
        click.echo(f"Command failed with exit code {result.returncode}", err=True)
        sys.exit(result.returncode)


def check_node_modules() -> None:
    if not (SKILL_DIR / "node_modules").exists():
        click.echo(
            "Error: Remotion not installed. Run `npm install` in the skill directory:\n"
            f"  cd {SKILL_DIR} && npm install",
            err=True,
        )
        sys.exit(1)


@click.group()
def cli():
    """Article-to-video pipeline."""
    pass


@cli.command()
@click.option("--script", "script_path", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--out", "out_dir", required=True, type=click.Path())
@click.option("--voice", default="brian")
@click.option("--scene", type=int, default=None)
@click.option("--force/--no-force", default=False)
def tts(script_path: str, out_dir: str, voice: str, scene: int | None, force: bool):
    """Generate per-scene narration audio."""
    cmd = ["uv", "run", str(CLI_DIR / "tts.py"), "generate",
           "--script", script_path, "--out", out_dir, "--voice", voice]
    if scene is not None:
        cmd += ["--scene", str(scene)]
    if force:
        cmd += ["--force"]
    run(cmd)


@cli.command()
@click.option("--script", "script_path", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--out", "out_dir", required=True, type=click.Path())
@click.option("--ref", "reference", default=None, type=click.Path(exists=True, dir_okay=False))
@click.option("--scene", type=int, default=None)
@click.option("--force/--no-force", default=False)
@click.option("--workers", default=4)
def images(script_path: str, out_dir: str, reference: str | None, scene: int | None, force: bool, workers: int):
    """Generate per-scene watercolor images (Nano Banana)."""
    cmd = ["uv", "run", str(CLI_DIR / "images.py"), "generate",
           "--script", script_path, "--out", out_dir, "--workers", str(workers)]
    if reference:
        cmd += ["--reference", reference]
    if scene is not None:
        cmd += ["--scene", str(scene)]
    if force:
        cmd += ["--force"]
    run(cmd)


@cli.command()
@click.option("--script", "script_path", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--out", "out_dir", required=True, type=click.Path())
def props(script_path: str, out_dir: str):
    """Build Remotion props.json + captions.srt from alignments."""
    cmd = ["uv", "run", str(CLI_DIR / "build_props.py"),
           "--script", script_path, "--out", out_dir]
    run(cmd)


@cli.command()
@click.option("--out", "out_dir", required=True, type=click.Path(exists=True, file_okay=False))
@click.option("--filename", default="final.mp4", help="Output filename inside --out")
def render(out_dir: str, filename: str):
    """Render MP4 from prepared props + assets."""
    check_node_modules()
    out = Path(out_dir).resolve()
    props_path = out / "props.json"
    if not props_path.exists():
        click.echo(f"Missing: {props_path} — run `props` first", err=True)
        sys.exit(1)
    final_path = out / filename
    cmd = [
        "npx", "remotion", "render",
        "remotion/index.ts", "VideoArticle",
        str(final_path),
        f"--props={props_path}",
        f"--public-dir={out}",
    ]
    run(cmd, cwd=SKILL_DIR)


@cli.command(name="all")
@click.option("--script", "script_path", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--out", "out_dir", required=True, type=click.Path())
@click.option("--ref", "reference", default=None, type=click.Path(exists=True, dir_okay=False))
@click.option("--voice", default="brian")
@click.option("--filename", default="final.mp4")
@click.option("--force/--no-force", default=False, help="Regenerate audio + images even if cached")
@click.pass_context
def run_all(ctx, script_path: str, out_dir: str, reference: str | None, voice: str, filename: str, force: bool):
    """Run the full pipeline: tts → images → props → render."""
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    ctx.invoke(tts, script_path=script_path, out_dir=out_dir, voice=voice, scene=None, force=force)
    ctx.invoke(images, script_path=script_path, out_dir=out_dir, reference=reference, scene=None, force=force, workers=4)
    ctx.invoke(props, script_path=script_path, out_dir=out_dir)
    ctx.invoke(render, out_dir=out_dir, filename=filename)


if __name__ == "__main__":
    cli()
