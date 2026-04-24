#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["click>=8.0"]
# ///
"""Manifest read/write for per-slug distribution state.

One JSON file per slug at {manifest_dir}/{slug}.json. Shape:

    {
      "slug": "food-noise",
      "published_at": "2026-04-24T...",
      "youtube": {
        "status": "uploaded",
        "video_id": "abc123",
        "url": "https://youtube.com/watch?v=abc123",
        "privacy": "unlisted",
        "caption_id": "...",
        "thumbnail_set": true,
        "playlist_id": "...",
        "pinned_comment_id": "..."
      }
    }
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import click


def manifest_path(manifest_dir: str, slug: str) -> Path:
    return Path(manifest_dir) / f"{slug}.json"


def load(manifest_dir: str, slug: str) -> dict[str, Any]:
    p = manifest_path(manifest_dir, slug)
    if not p.exists():
        return {"slug": slug}
    return json.loads(p.read_text())


def save(manifest_dir: str, slug: str, data: dict[str, Any]) -> Path:
    p = manifest_path(manifest_dir, slug)
    p.parent.mkdir(parents=True, exist_ok=True)
    data.setdefault("slug", slug)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    p.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return p


@click.group()
def cli():
    """Manifest CLI."""


@cli.command()
@click.option("--slug", required=True)
@click.option("--manifest-dir", "manifest_dir", required=True, type=click.Path())
def show(slug: str, manifest_dir: str):
    """Print the manifest for a slug."""
    p = manifest_path(manifest_dir, slug)
    if not p.exists():
        click.echo(f"No manifest at {p}")
        return
    click.echo(p.read_text())


if __name__ == "__main__":
    cli()
