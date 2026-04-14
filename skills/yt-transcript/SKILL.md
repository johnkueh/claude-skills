---
name: yt-transcript
description: Fetch clean transcripts from YouTube videos. Extracts auto-generated or manual captions and returns deduplicated plain text. Use when processing YouTube URLs for content, fact-checking, or research. Triggers on YouTube URLs, "get transcript", "fetch captions", or "youtube transcript".
---

# YouTube Transcript

Fetch clean, deduplicated transcripts from YouTube videos using yt-dlp.

**Setup:** Requires Python 3.9+ and yt-dlp (`pip3 install yt-dlp`). No API key needed.

## Commands

Run all commands from this skill's base directory (shown above).

### Fetch a transcript

```bash
uv run python cli.py "https://www.youtube.com/watch?v=VIDEO_ID"
```

Returns clean plain text transcript to stdout. Also saves to `results/` directory.

### Fetch with max character limit

```bash
uv run python cli.py "https://www.youtube.com/watch?v=VIDEO_ID" --max-chars 10000
```

### Output

Returns a JSON object:

```json
{
  "url": "https://www.youtube.com/watch?v=...",
  "title": "Video Title",
  "channel": "Channel Name",
  "duration": "16:12",
  "views": "284.3K",
  "published": "2026-03-27",
  "transcript": "Full clean transcript text...",
  "transcript_length": 14419
}
```
