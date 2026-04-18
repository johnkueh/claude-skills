#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["click>=8.0", "requests>=2.28"]
# ///
"""ElevenLabs TTS for scene-based video scripts.

Reads a scene script JSON, generates one MP3 + alignment JSON per scene.

Usage:
    ELEVENLABS_API_KEY=... uv run tts.py generate \\
        --script /path/to/scene-script.json \\
        --out /path/to/output-dir
    uv run tts.py voices
"""

import base64
import json
import os
import sys
from pathlib import Path

import click
import requests

API_BASE = "https://api.elevenlabs.io/v1"

VOICES = {
    "brian": "nPczCjzI2devNBz1zQrb",
    "bill": "pqHfZKP75CvOlQylNhV4",
    "daniel": "onwK4e9ZLuTAKqWW03F9",
    "adam": "pNInz6obpgDQGcFmaJgB",
    "rachel": "21m00Tcm4TlvDq8ikWAM",
    "sarah": "EXAVITQu4vr4xnSDxMaL",
    "george": "JBFqnCBsd6RMkjVDRZzb",
}

DEFAULT_VOICE = "brian"
DEFAULT_MODEL = "eleven_multilingual_v2"


def auth_header() -> dict:
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        click.echo("Error: ELEVENLABS_API_KEY not set in env.", err=True)
        sys.exit(1)
    return {"xi-api-key": key, "Content-Type": "application/json"}


def tts_with_timestamps(text: str, voice_id: str, model: str) -> dict:
    url = f"{API_BASE}/text-to-speech/{voice_id}/with-timestamps"
    payload = {
        "text": text,
        "model_id": model,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.2,
            "use_speaker_boost": True,
        },
    }
    resp = requests.post(url, headers=auth_header(), json=payload, timeout=120)
    if not resp.ok:
        click.echo(f"API error {resp.status_code}: {resp.text}", err=True)
        sys.exit(1)
    return resp.json()


@click.group()
def cli():
    """ElevenLabs TTS for scene video scripts."""
    pass


@cli.command()
def voices():
    """List curated narrator voices."""
    for name, vid in VOICES.items():
        click.echo(f"  {name:<10} {vid}")


@cli.command()
@click.option("--script", "script_path", required=True, type=click.Path(exists=True, dir_okay=False), help="Path to scene script JSON")
@click.option("--out", "out_dir", required=True, type=click.Path(), help="Output directory for audio")
@click.option("--voice", default=DEFAULT_VOICE, type=click.Choice(list(VOICES.keys())))
@click.option("--model", default=DEFAULT_MODEL)
@click.option("--scene", type=int, default=None, help="Regenerate only this scene id")
@click.option("--force/--no-force", default=False, help="Regenerate even if MP3 exists")
def generate(script_path: str, out_dir: str, voice: str, model: str, scene: int | None, force: bool):
    """Generate per-scene MP3s + alignment JSON from a scene script."""
    script = json.loads(Path(script_path).read_text())
    scenes = script["scenes"]
    voice_id = VOICES[voice]

    out_path = Path(out_dir) / "audio"
    out_path.mkdir(parents=True, exist_ok=True)

    click.echo(f"script: {script_path}", err=True)
    click.echo(f"voice: {voice} ({voice_id})", err=True)
    click.echo(f"model: {model}", err=True)
    click.echo(f"scenes: {len(scenes)}", err=True)

    targets = [s for s in scenes if (scene is None or s["id"] == scene)]
    total_chars = sum(len(s["narration"]) for s in targets)
    click.echo(f"chars: {total_chars} (~${total_chars * 0.0001:.3f} at Creator tier)\n", err=True)

    results = []
    for s in targets:
        sid = s["id"]
        mp3_path = out_path / f"scene-{sid:02d}.mp3"
        align_path = out_path / f"scene-{sid:02d}.alignment.json"

        if mp3_path.exists() and not force:
            click.echo(f"  scene {sid:02d}: cached ({mp3_path.name})", err=True)
            results.append({"scene": sid, "mp3": mp3_path.name, "cached": True})
            continue

        click.echo(f"  scene {sid:02d}: generating ({len(s['narration'])} chars)...", err=True)
        data = tts_with_timestamps(s["narration"], voice_id, model)

        audio_bytes = base64.b64decode(data["audio_base64"])
        mp3_path.write_bytes(audio_bytes)

        alignment = data.get("alignment") or {}
        align_payload = {
            "scene_id": sid,
            "section": s.get("section", ""),
            "narration": s["narration"],
            "characters": alignment.get("characters", []),
            "character_start_times_seconds": alignment.get("character_start_times_seconds", []),
            "character_end_times_seconds": alignment.get("character_end_times_seconds", []),
        }
        align_path.write_text(json.dumps(align_payload, indent=2))

        duration = alignment.get("character_end_times_seconds", [0])[-1] if alignment.get("character_end_times_seconds") else None
        msg = f"    → {mp3_path.name} ({len(audio_bytes)//1024} KB"
        msg += f", {duration:.2f}s)" if duration else ")"
        click.echo(msg, err=True)
        results.append({"scene": sid, "mp3": mp3_path.name, "duration_s": duration, "cached": False})

    manifest = {
        "voice": voice,
        "voice_id": voice_id,
        "model": model,
        "scenes": results,
    }
    (out_path / "manifest.json").write_text(json.dumps(manifest, indent=2))
    click.echo(f"\nWrote manifest: {out_path / 'manifest.json'}", err=True)


if __name__ == "__main__":
    cli()
