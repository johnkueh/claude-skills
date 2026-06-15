---
name: marketing-youtube-transcribe
description: Transcribe YouTube videos. Tries auto/manual captions first via yt-dlp; if they're missing or empty, downloads audio and transcribes with Gemini 2.5 Flash. Use when processing YouTube URLs for content, fact-checking, or research. Triggers on YouTube URLs, "get transcript", "fetch captions", "youtube transcript", or "transcribe this video".
---

# YouTube Transcribe

Captions-first, audio-fallback transcripts for YouTube videos.

**Setup:** Python 3.10+, `yt-dlp`, `ffmpeg` on PATH, and `GEMINI_API_KEY` for the audio fallback. `uv` resolves the Python deps automatically.

## Commands

Run from this skill's base directory.

### Default — captions, audio fallback

```bash
uv run python cli.py "https://www.youtube.com/watch?v=VIDEO_ID"
```

Tries auto-generated captions, then manual captions. If both are empty/missing, downloads the audio as mp3 (lowest-quality LAME, smallest file), uploads it to Gemini Files API, and calls `gemini-2.5-flash` for a transcript.

### Force audio path (skip captions)

```bash
uv run python cli.py "https://www.youtube.com/watch?v=VIDEO_ID" --audio
```

Useful when captions exist but are low quality (auto-generated music videos, heavy accents, multi-speaker).

### Cap output length

```bash
uv run python cli.py "https://www.youtube.com/watch?v=VIDEO_ID" --max-chars 10000
```

## Output

```json
{
  "url": "https://www.youtube.com/watch?v=...",
  "title": "Video Title",
  "channel": "Channel Name",
  "duration": "16:12",
  "views": "284.3K",
  "published": "2026-03-27",
  "source": "captions",
  "transcript": "Full clean transcript text...",
  "transcript_length": 14419
}
```

`source` is `"captions"` when subs were used and `"gemini"` when the audio fallback ran. Saved to `results/` alongside stdout.
