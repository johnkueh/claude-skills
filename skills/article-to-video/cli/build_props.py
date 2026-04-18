#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["click>=8.0"]
# ///
"""Build Remotion props + SRT captions from a scene script + audio alignments.

Usage:
    uv run build_props.py \\
        --script /path/to/scene-script.json \\
        --out /path/to/output-dir

Reads:
    <script>
    <out>/audio/manifest.json
    <out>/audio/scene-NN.alignment.json

Writes:
    <out>/props.json        — input for Remotion render
    <out>/captions.srt      — for YouTube upload
"""

import json
import re
import sys
from pathlib import Path

import click

FPS = 30
WIDTH = 1920
HEIGHT = 1080
CAPTION_WORDS_PER_CHUNK = 6


def chars_to_words(chars: list, starts: list, ends: list) -> list:
    words = []
    current = {"text": "", "start_s": None, "end_s": None}
    for ch, st, et in zip(chars, starts, ends):
        if ch.isspace():
            if current["text"]:
                words.append(current)
                current = {"text": "", "start_s": None, "end_s": None}
            continue
        if current["start_s"] is None:
            current["start_s"] = st
        current["end_s"] = et
        current["text"] += ch
    if current["text"]:
        words.append(current)
    return words


def chunk_words_to_captions(words: list, chunk_size: int = CAPTION_WORDS_PER_CHUNK) -> list:
    captions = []
    buf = []
    for w in words:
        buf.append(w)
        ends_sentence = bool(re.search(r"[.!?]$", w["text"]))
        if len(buf) >= chunk_size or ends_sentence:
            captions.append({
                "text": " ".join(x["text"] for x in buf),
                "start_s": buf[0]["start_s"],
                "end_s": buf[-1]["end_s"],
            })
            buf = []
    if buf:
        captions.append({
            "text": " ".join(x["text"] for x in buf),
            "start_s": buf[0]["start_s"],
            "end_s": buf[-1]["end_s"],
        })
    return captions


def seconds_to_srt_time(s: float) -> str:
    hours = int(s // 3600)
    minutes = int((s % 3600) // 60)
    seconds = int(s % 60)
    millis = int(round((s - int(s)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


@click.command()
@click.option("--script", "script_path", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--out", "out_dir", required=True, type=click.Path())
@click.option("--fps", default=FPS)
@click.option("--width", default=WIDTH)
@click.option("--height", default=HEIGHT)
def build(script_path: str, out_dir: str, fps: int, width: int, height: int):
    """Build props.json + captions.srt."""
    script = json.loads(Path(script_path).read_text())
    out_path = Path(out_dir)
    audio_dir = out_path / "audio"

    scene_props = []
    running_frame = 0
    srt_running_s = 0.0
    srt_lines = []
    srt_index = 1

    for s in script["scenes"]:
        sid = s["id"]
        align_path = audio_dir / f"scene-{sid:02d}.alignment.json"
        if not align_path.exists():
            click.echo(f"Missing alignment: {align_path}", err=True)
            sys.exit(1)
        align = json.loads(align_path.read_text())

        chars = align["characters"]
        starts = align["character_start_times_seconds"]
        ends = align["character_end_times_seconds"]

        words = chars_to_words(chars, starts, ends)
        captions = chunk_words_to_captions(words)

        duration_s = ends[-1] if ends else 0
        duration_frames = max(1, round(duration_s * fps))

        kb_directions = ["zoom-in-center", "zoom-in-left", "zoom-out-center", "zoom-in-right"]
        kb = kb_directions[(sid - 1) % len(kb_directions)]

        scene_props.append({
            "id": sid,
            "section": s.get("section", ""),
            "startFrame": running_frame,
            "durationInFrames": duration_frames,
            "durationSeconds": duration_s,
            "imageFile": f"scene-{sid:02d}.webp",
            "audioFile": f"scene-{sid:02d}.mp3",
            "overlay": s.get("overlay", {"headline": "", "subhead": "", "citation": ""}),
            "captions": [
                {"text": c["text"], "startMs": int(c["start_s"] * 1000), "endMs": int(c["end_s"] * 1000)}
                for c in captions
            ],
            "kenBurns": kb,
        })

        for c in captions:
            srt_lines.append(str(srt_index))
            srt_lines.append(f"{seconds_to_srt_time(srt_running_s + c['start_s'])} --> {seconds_to_srt_time(srt_running_s + c['end_s'])}")
            srt_lines.append(c["text"])
            srt_lines.append("")
            srt_index += 1

        srt_running_s += duration_s
        running_frame += duration_frames

    props = {
        "slug": script.get("slug", ""),
        "title": script.get("video_title", ""),
        "fps": fps,
        "width": width,
        "height": height,
        "totalFrames": running_frame,
        "totalSeconds": running_frame / fps,
        "scenes": scene_props,
    }

    (out_path / "props.json").write_text(json.dumps(props, indent=2))
    (out_path / "captions.srt").write_text("\n".join(srt_lines))

    click.echo(f"scenes: {len(scene_props)}", err=True)
    click.echo(f"total: {running_frame} frames ({running_frame / fps:.2f}s)", err=True)
    click.echo(f"captions: {srt_index - 1} lines", err=True)
    click.echo(f"\nWrote:", err=True)
    click.echo(f"  {out_path / 'props.json'}", err=True)
    click.echo(f"  {out_path / 'captions.srt'}", err=True)


if __name__ == "__main__":
    build()
