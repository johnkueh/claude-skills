#!/usr/bin/env python3
"""Fetch clean transcripts from YouTube videos.

Primary path: yt-dlp captions (auto-generated or manual).
Fallback: download audio with yt-dlp + transcribe via Gemini 2.5 Flash.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_PROMPT = (
    "Transcribe this audio verbatim into clean, readable text in the spoken "
    "language. Return only the transcript — no preamble, no timestamps, no "
    "speaker labels unless clearly distinguishable. Preserve sentence punctuation."
)


def clean_vtt(vtt_text: str) -> str:
    """Remove VTT formatting, timestamps, and deduplicate lines."""
    lines = vtt_text.split("\n")
    text_lines = []
    for line in lines:
        line = line.strip()
        if (
            not line
            or line == "WEBVTT"
            or line.startswith("Kind:")
            or line.startswith("Language:")
            or re.match(r"^\d+$", line)
            or re.match(r"^\d{2}:\d{2}", line)
        ):
            continue
        line = re.sub(r"<[^>]+>", "", line)
        line = line.strip()
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


def fetch_captions(url: str) -> str | None:
    """Try auto-generated then manual subs. Returns clean transcript or None."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_template = os.path.join(tmpdir, "video")

        for flag in ("--write-auto-sub", "--write-sub"):
            subprocess.run(
                [
                    sys.executable, "-m", "yt_dlp",
                    flag,
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
                    transcript = clean_vtt(f.read_text(encoding="utf-8"))
                    if transcript:
                        return transcript
                    f.unlink()

    return None


def download_audio(url: str, dest_dir: Path) -> Path:
    """Extract audio as mp3 (low bitrate to keep file small)."""
    output_template = str(dest_dir / "audio.%(ext)s")
    result = subprocess.run(
        [
            sys.executable, "-m", "yt_dlp",
            "-f", "bestaudio/best",
            "--extract-audio",
            "--audio-format", "mp3",
            "--audio-quality", "9",
            "--extractor-args", "youtube:player_client=android",
            "-o", output_template,
            url,
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp audio download failed: {result.stderr}")

    for f in dest_dir.iterdir():
        if f.suffix == ".mp3":
            return f
    raise RuntimeError("yt-dlp produced no mp3 file")


def transcribe_with_gemini(audio_path: Path) -> str:
    """Upload audio to Gemini Files API and request a transcript."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY env var required for audio transcription fallback"
        )

    from google import genai

    client = genai.Client(api_key=api_key)
    uploaded = client.files.upload(file=str(audio_path))
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[uploaded, GEMINI_PROMPT],
        )
        text = (response.text or "").strip()
        if not text:
            raise RuntimeError("Gemini returned empty transcript")
        return text
    finally:
        try:
            client.files.delete(name=uploaded.name)
        except Exception:
            pass


def fetch_transcript(url: str, force_audio: bool = False) -> dict:
    transcript = None
    source = None

    if not force_audio:
        transcript = fetch_captions(url)
        if transcript:
            source = "captions"

    if not transcript:
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                audio_path = download_audio(url, Path(tmpdir))
                transcript = transcribe_with_gemini(audio_path)
                source = "gemini"
        except Exception as e:
            return {"error": f"Captions empty and audio fallback failed: {e}"}

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
        "source": source,
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
    parser.add_argument(
        "--audio",
        action="store_true",
        help="Skip captions and transcribe directly from audio via Gemini",
    )
    args = parser.parse_args()

    result = fetch_transcript(args.url, force_audio=args.audio)

    if "error" in result:
        print(json.dumps(result, indent=2))
        sys.exit(1)

    if args.max_chars and len(result["transcript"]) > args.max_chars:
        result["transcript"] = result["transcript"][: args.max_chars]
        result["truncated"] = True

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
