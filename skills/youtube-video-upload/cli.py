#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["click>=8.0"]
# ///
"""Unified CLI for video-distribute.

YouTube-first distribution for rendered explainer videos. Reads the same scene
script JSON produced by the article-to-video pipeline, uploads the MP4 + SRT
captions + a generated thumbnail, wires the video into a playlist, and pins a
comment linking back to the source article.

Subcommands:
    auth        One-time OAuth flow (YouTube)
    thumbnail   Generate 1280x720 thumbnail via Gemini 2.5 Flash Image
    upload      Upload video + captions + thumbnail + metadata to YouTube
    publish     Full pipeline: thumbnail -> upload -> playlist -> pin comment
    status      Show manifest for a slug

Usage:
    uv run cli.py auth youtube --client-secret ~/.config/youtube-upload/client-secret.json
    uv run cli.py publish \\
        --script /path/to/video-script.json \\
        --video /path/to/final.mp4 \\
        --captions /path/to/captions.srt \\
        --reference /path/to/style-reference.webp \\
        --manifest-dir /path/to/seo/distribution \\
        --privacy unlisted

Environment:
    YOUTUBE_CLIENT_SECRET_PATH  (default ~/.config/youtube-upload/client-secret.json)
    YOUTUBE_TOKEN_PATH          (default ~/.config/youtube-upload/token.json)
    GEMINI_API_KEY              Required for thumbnail generation
"""

import subprocess
import sys
from pathlib import Path

import click

SKILL_DIR = Path(__file__).resolve().parent
CLI_DIR = SKILL_DIR / "cli"


def run(cmd: list[str]) -> None:
    click.echo(f"\n$ {' '.join(str(c) for c in cmd)}", err=True)
    result = subprocess.run(cmd)
    if result.returncode != 0:
        click.echo(f"Command failed with exit code {result.returncode}", err=True)
        sys.exit(result.returncode)


@click.group()
def cli():
    """Video distribution CLI (YouTube)."""


@cli.group()
def auth():
    """OAuth flows."""


@auth.command("youtube")
@click.option("--client-secret", "client_secret", type=click.Path(exists=True, dir_okay=False),
              help="Path to client_secret.json from Google Cloud Console. "
                   "Defaults to $YOUTUBE_CLIENT_SECRET_PATH.")
@click.option("--token", "token_path", type=click.Path(),
              help="Where to save the refresh token. Defaults to $YOUTUBE_TOKEN_PATH.")
def auth_youtube(client_secret: str | None, token_path: str | None):
    """Run one-time OAuth flow and cache refresh token."""
    cmd = ["uv", "run", str(CLI_DIR / "auth.py"), "youtube"]
    if client_secret:
        cmd += ["--client-secret", client_secret]
    if token_path:
        cmd += ["--token", token_path]
    run(cmd)


@cli.command()
@click.option("--script", "script_path", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--reference", "reference_path", required=True, type=click.Path(exists=True, dir_okay=False),
              help="Style reference image (same watercolor reference used for scene art).")
@click.option("--out", "out_path", required=True, type=click.Path(),
              help="Output path for the thumbnail (1280x720 JPG).")
def thumbnail(script_path: str, reference_path: str, out_path: str):
    """Generate a 1280x720 thumbnail via Gemini 2.5 Flash Image."""
    cmd = ["uv", "run", str(CLI_DIR / "thumbnail.py"), "generate",
           "--script", script_path, "--reference", reference_path, "--out", out_path]
    run(cmd)


@cli.command()
@click.option("--script", "script_path", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--video", "video_path", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--captions", "captions_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--thumbnail", "thumbnail_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--privacy", type=click.Choice(["private", "unlisted", "public"]), default="unlisted")
@click.option("--publish-at", "publish_at", type=str, default=None,
              help="ISO8601 timestamp for scheduled publish (privacy must be 'private').")
@click.option("--category-id", "category_id", type=int, default=27,
              help="YouTube category (27=Education).")
@click.option("--playlist-id", "playlist_id", type=str, default=None)
@click.option("--pin-comment/--no-pin-comment", default=True,
              help="Post and pin a comment linking to the source article.")
@click.option("--manifest-dir", "manifest_dir", type=click.Path(), default=None)
@click.option("--token", "token_path", type=click.Path(), default=None)
@click.option("--dry-run/--no-dry-run", default=False)
def upload(script_path: str, video_path: str, captions_path: str | None,
           thumbnail_path: str | None, privacy: str, publish_at: str | None,
           category_id: int, playlist_id: str | None, pin_comment: bool,
           manifest_dir: str | None, token_path: str | None, dry_run: bool):
    """Upload video + captions + thumbnail to YouTube."""
    cmd = ["uv", "run", str(CLI_DIR / "youtube.py"), "upload",
           "--script", script_path, "--video", video_path,
           "--privacy", privacy, "--category-id", str(category_id)]
    if captions_path:
        cmd += ["--captions", captions_path]
    if thumbnail_path:
        cmd += ["--thumbnail", thumbnail_path]
    if publish_at:
        cmd += ["--publish-at", publish_at]
    if playlist_id:
        cmd += ["--playlist-id", playlist_id]
    if not pin_comment:
        cmd += ["--no-pin-comment"]
    if manifest_dir:
        cmd += ["--manifest-dir", manifest_dir]
    if token_path:
        cmd += ["--token", token_path]
    if dry_run:
        cmd += ["--dry-run"]
    run(cmd)


@cli.command()
@click.option("--script", "script_path", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--video", "video_path", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--captions", "captions_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--reference", "reference_path", type=click.Path(exists=True, dir_okay=False),
              help="Style reference for thumbnail (skipped if --thumbnail is given).")
@click.option("--thumbnail", "thumbnail_path", type=click.Path(),
              help="Use an existing thumbnail (skip Gemini generation).")
@click.option("--privacy", type=click.Choice(["private", "unlisted", "public"]), default="unlisted")
@click.option("--publish-at", "publish_at", type=str, default=None)
@click.option("--category-id", "category_id", type=int, default=27)
@click.option("--playlist-id", "playlist_id", type=str, default=None)
@click.option("--manifest-dir", "manifest_dir", type=click.Path(), required=True)
@click.option("--token", "token_path", type=click.Path(), default=None)
@click.option("--dry-run/--no-dry-run", default=False)
@click.pass_context
def publish(ctx, script_path: str, video_path: str, captions_path: str | None,
            reference_path: str | None, thumbnail_path: str | None,
            privacy: str, publish_at: str | None, category_id: int,
            playlist_id: str | None, manifest_dir: str, token_path: str | None,
            dry_run: bool):
    """Full pipeline: generate thumbnail (if missing) -> upload -> playlist -> pin comment -> manifest."""
    if not thumbnail_path:
        if not reference_path:
            click.echo("Error: --reference required when --thumbnail is not provided.", err=True)
            sys.exit(2)
        script_p = Path(script_path)
        thumbnail_path = str(script_p.parent / f"{script_p.stem}-thumb.jpg")
        ctx.invoke(thumbnail, script_path=script_path, reference_path=reference_path,
                   out_path=thumbnail_path)

    ctx.invoke(upload, script_path=script_path, video_path=video_path,
               captions_path=captions_path, thumbnail_path=thumbnail_path,
               privacy=privacy, publish_at=publish_at, category_id=category_id,
               playlist_id=playlist_id, pin_comment=True, manifest_dir=manifest_dir,
               token_path=token_path, dry_run=dry_run)


@cli.command()
@click.option("--slug", required=True)
@click.option("--manifest-dir", "manifest_dir", type=click.Path(exists=True), required=True)
def status(slug: str, manifest_dir: str):
    """Print manifest for a slug."""
    cmd = ["uv", "run", str(CLI_DIR / "manifest.py"), "show",
           "--slug", slug, "--manifest-dir", manifest_dir]
    run(cmd)


if __name__ == "__main__":
    cli()
