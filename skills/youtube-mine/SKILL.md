---
name: youtube-mine
description: >-
  Mine YouTube comments for unanswered questions via yt-dlp — search videos by
  query or channel, pull top comments, extract question-shaped comments with
  reply-based answered detection, and cluster the unanswered ones. Output is
  drop-in compatible with reddit-miner's mine command, so the glp3-daily and
  johnkueh-daily SEO loops consume either source identically. No API key
  (yt-dlp scrapes the public site). Replaces the retired comment-mine YouTube
  path. Triggers on "mine youtube", "youtube comments for", "what are people
  asking on youtube", "youtube questions about", "yt mine", "pull comments from
  this video", "recent uploads from channel".
---

# youtube-mine

yt-dlp-backed comment miner. Two-stage: `ytsearch` (or a channel's /videos tab)
finds videos, then per-video comment extraction with
`--extractor-args "youtube:max_comments=N,...;comment_sort=top"`. Question
detection, answered heuristics, and clustering are a straight Python port of
reddit-miner's NLP, so both miners produce the same shapes and quality bar.

## Setup — nothing to configure

Only dependency is `yt-dlp` on PATH (`brew install yt-dlp`). No API key, no
config. Run `doctor` to confirm:

```bash
python3 ~/Projects/claude-skills/skills/youtube-mine/cli.py doctor
```

## Commands

```bash
CLI=~/Projects/claude-skills/skills/youtube-mine/cli.py

# End-to-end mine: search → comments → questions → clusters (the daily-loop entry point)
python3 $CLI mine --query "retatrutide dosing" --videos 8 --comments 250 \
  --topic-keywords "reta|retatrutide|glp|dose"        # optional regex filter

# List videos: by search query, or a channel's recent uploads
python3 $CLI videos --query "claude code" --limit 15
python3 $CLI videos --channel @LennysPodcast --limit 15

# Raw comments for one video (debugging / deeper reads)
python3 $CLI comments --video VIDEO_ID --limit 250
```

## Output shape (`mine`)

```json
{
  "query": "...", "videos_scanned": 8, "comments_scanned": 1900,
  "n_questions": 31, "n_unanswered": 12,
  "questions": [{ "q": "...", "score": 14, "answered": false, "n_replies": 0,
                  "source": "youtube-comment", "thread_title": "<video title>",
                  "permalink": "https://www.youtube.com/watch?v=..." }],
  "top_questions": [...],
  "clusters_unanswered": [{ "key": "dose + split", "count": 3, "top_score": 14,
                            "sample": "...", "permalink": "...", "examples": [...] }],
  "failures": [{ "video": "...", "error": "..." }]
}
```

Same `questions[]` / `clusters_unanswered` fields as reddit-miner — merge the
two sources by concatenating `questions` arrays.

## Behavior notes

- `--comments N` is per video, top-sorted; replies are capped at 10 per thread
  (enough for answered detection without paying for full reply trees).
- `answered` = a top-level question has at least one substantive reply (≥40
  chars, not itself a question, not "idk/same/yes/no").
- One dead/private video never kills the mine — it lands in `failures[]` and
  the rest proceed (the daily loops require best-effort mining).
- Cost: free; wall-clock ~20–60s per video at 250 comments. 8 videos ≈ 3–6 min.
- A small `n_questions` is normal: top-sorted comments skew to highly-replied
  (answered) threads, and `--topic-keywords` drops off-topic questions before
  extraction. Drop the topic filter for breadth, filter downstream instead.
- YouTube occasionally rate-limits comment fetches on cloud IPs; on residential
  connections (where the daily loops run) this is rare. A persistent
  `failures[]` wall means update yt-dlp (`brew upgrade yt-dlp`) first.
