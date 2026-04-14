#!/usr/bin/env python3
"""Fetch clean transcripts from YouTube videos using yt-dlp."""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path


def clean_vtt(vtt_text: str) -> str:
    """Remove VTT formatting, timestamps, and deduplicate lines."""
    lines = vtt_text.split("\n")
    text_lines = []
    for line in lines:
        line = line.strip()
        # Skip VTT metadata and timestamps
        if (
            not line
            or line == "WEBVTT"
            or line.startswith("Kind:")
            or line.startswith("Language:")
            or re.match(r"^\d+$", line)
            or re.match(r"^\d{2}:\d{2}", line)
        ):
            continue
        # Remove VTT tags like <c>, </c>, <00:00:01.234>
        line = re.sub(r"<[^>]+>", "", line)
        line = line.strip()
        # Skip empty or duplicate consecutive lines
        if line and (not text_lines or line != text_lines[-1]):
            text_lines.append(line)

    clean = " ".join(text_lines)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def get_video_metadata(url: str) -> dict:
    """Fetch video metadata via yt-dlp --dump-json."""
    try:
        result = subprocess.run(
            [
                sys.executable, "-m", "yt_dlp",
                "--dump-json",
                "--skip-download",
                "--extractor-args", "youtube:player_client=android",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        pass
    return {}


def fetch_transcript(url: str) -> dict:
    """Fetch and clean a YouTube transcript."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_template = os.path.join(tmpdir, "video")

        # Download auto-generated subtitles using android client (bypasses PO token requirement)
        result = subprocess.run(
            [
                sys.executable, "-m", "yt_dlp",
                "--write-auto-sub",
                "--sub-lang", "en",
                "--skip-download",
                "--extractor-args", "youtube:player_client=android",
                "-o", output_template,
                url,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Find the subtitle file
        vtt_path = None
        for f in Path(tmpdir).iterdir():
            if f.suffix == ".vtt":
                vtt_path = f
                break

        if not vtt_path:
            # Try manual subs as fallback
            result = subprocess.run(
                [
                    sys.executable, "-m", "yt_dlp",
                    "--write-sub",
                    "--sub-lang", "en",
                    "--skip-download",
                    "--extractor-args", "youtube:player_client=android",
                    "-o", output_template,
                    url,
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            for f in Path(tmpdir).iterdir():
                if f.suffix == ".vtt":
                    vtt_path = f
                    break

        if not vtt_path:
            return {"error": f"No subtitles found. yt-dlp output: {result.stderr}"}

        vtt_text = vtt_path.read_text(encoding="utf-8")
        transcript = clean_vtt(vtt_text)

    # Get metadata
    meta = get_video_metadata(url)

    duration_secs = meta.get("duration", 0)
    minutes = duration_secs // 60
    seconds = duration_secs % 60
    duration_str = f"{minutes}:{seconds:02d}" if duration_secs else "unknown"

    view_count = meta.get("view_count", 0)
    if view_count >= 1_000_000:
        views_str = f"{view_count / 1_000_000:.1f}M"
    elif view_count >= 1_000:
        views_str = f"{view_count / 1_000:.1f}K"
    else:
        views_str = str(view_count)

    upload_date = meta.get("upload_date", "")
    if upload_date and len(upload_date) == 8:
        published = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}"
    else:
        published = "unknown"

    return {
        "url": url,
        "title": meta.get("title", "Unknown"),
        "channel": meta.get("channel", meta.get("uploader", "Unknown")),
        "duration": duration_str,
        "views": views_str,
        "published": published,
        "transcript": transcript,
        "transcript_length": len(transcript),
    }


def main():
    parser = argparse.ArgumentParser(description="Fetch YouTube transcripts")
    parser.add_argument("url", help="YouTube video URL")
    parser.add_argument(
        "--max-chars",
        type=int,
        default=0,
        help="Truncate transcript to this many characters (0 = no limit)",
    )
    args = parser.parse_args()

    result = fetch_transcript(args.url)

    if "error" in result:
        print(json.dumps(result, indent=2))
        sys.exit(1)

    if args.max_chars and len(result["transcript"]) > args.max_chars:
        result["transcript"] = result["transcript"][: args.max_chars]
        result["truncated"] = True

    # Save to results directory
    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    slug = re.sub(r"[^a-z0-9]+", "-", result["title"].lower())[:50].strip("-")
    output_path = results_dir / f"transcript_{slug}_{timestamp}.json"
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(json.dumps(result, indent=2))
    print(f"\nSaved to {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
