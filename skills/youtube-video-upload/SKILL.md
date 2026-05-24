---
name: youtube-video-upload
description: Upload a rendered explainer video to YouTube programmatically via the YouTube Data API v3. Uploads the MP4, SRT captions, a Gemini-generated thumbnail, sets privacy + AI-content disclosure, adds to a playlist, and pins a comment linking back to the source article. Triggers on "upload to YouTube", "publish to YouTube", "youtube upload", "upload mp4 to youtube", "set youtube thumbnail", "schedule youtube video", "youtube data api", "add captions to youtube", or "publish video".
---

# YouTube Video Upload

YouTube upload pipeline for rendered explainer videos. Driven by a scene-script JSON describing the video metadata + thumbnail copy.

## What it does per run

1. Generate a 1280×720 JPG thumbnail with Gemini 2.5 Flash Image (if one isn't provided)
2. Resumable upload of the MP4 via `videos().insert`
3. Upload `captions.srt` via `captions().insert`
4. Set the custom thumbnail via `thumbnails().set`
5. Optionally add the video to a playlist
6. Post a pinned comment linking to the source article
7. Write a per-slug manifest JSON recording every ID and URL

Privacy defaults to `unlisted` — caller reviews the video in YouTube Studio and flips to `public` (or uses `--publish-at` to schedule).

## Setup (one-time, user)

### YouTube account + channel
1. Create/pick a Google account for the channel
2. Activate YouTube on that account → create channel
3. Phone-verify at https://www.youtube.com/verify — unlocks custom thumbnails + long-form uploads

### Google Cloud project
1. https://console.cloud.google.com → new project (e.g. `my-youtube-uploads`)
2. APIs & Services → Library → enable **YouTube Data API v3**
3. OAuth consent screen → External → Testing mode → add your Gmail as a test user
4. Credentials → Create OAuth client → **Desktop app** → download JSON
5. Save to `~/.config/youtube-upload/client-secret.json`

### One-time OAuth handshake
```bash
cd <skill-dir>
uv run cli.py auth youtube
```
Opens a browser → pick account → grant scopes. Refresh token is saved to `~/.config/youtube-upload/token.json` (tokens never go into the repo).

## Environment

- `YOUTUBE_CLIENT_SECRET_PATH` — default `~/.config/youtube-upload/client-secret.json`
- `YOUTUBE_TOKEN_PATH` — default `~/.config/youtube-upload/token.json`
- `GEMINI_API_KEY` — required for thumbnail generation

## One-time font install (thumbnail brand mark)

The thumbnail brand mark renders your site name in Inter Bold. Install once:

```bash
curl -sL https://github.com/rsms/inter/releases/download/v4.0/Inter-4.0.zip -o /tmp/Inter.zip
unzip -q /tmp/Inter.zip -d /tmp/Inter
cp /tmp/Inter/extras/ttf/Inter-Bold.ttf ~/Library/Fonts/
```

The generator fails loudly with install instructions if `Inter-Bold.ttf` isn't in `~/Library/Fonts/`.

## Thumbnail design

The "minimal bloom" template — derived from 2026 thumbnail research + iteration on competitor thumbnails in the GLP-1 niche (Stanfield, Norwitz, Attia, Kurzgesagt, Vox). Key choices:

- **High contrast**: headline in near-black (#1a1a1a) on cream (~14:1 ratio), not plum (~3:1 fails the threshold)
- **Single dominant focal**: just the number. Subhead is optional — only add for cold audiences on a new channel
- **Watercolor bloom contained to lower-left 1/3**: massive negative space for the headline. Differentiates from the face-led doctor-channel wall
- **Brand matches site nav**: tailwind blue-500 dot + Inter Bold brand text in near-black (set via --brand or YOUTUBE_BRAND env)
- **Modern auto-injector pen** (not vintage syringe) inside the bloom

Thumbnail copy comes from the scene script JSON:

```json
"thumbnail": {
  "headline": "28.7%",
  "subhead": "WEIGHT LOSS"
}
```

If the script has no `thumbnail` block, the generator falls back to `scene[0].overlay.headline/subhead`. Use `--no-subhead` to force the pure-minimal (headline + brand only) layout.

## Input contract

- **Scene script JSON** — must have `slug`, `video_title`, `video_description_draft`. Chapters should already be inlined into the description draft by the upstream renderer.
- **Rendered MP4** — any resolution YouTube accepts (1920×1080 is the typical target).
- **Captions SRT** — optional but recommended.
- **Style reference image** — optional; if provided (same reference used for scene art), Gemini will generate a thumbnail in that medium.

## CLI reference

```bash
# One-time auth
uv run cli.py auth youtube [--client-secret PATH] [--token PATH]

# Generate thumbnail only
uv run cli.py thumbnail \
  --script video/scripts/<slug>.json \
  --reference public/images/<slug>.webp \
  --out video/out/<slug>/thumb.jpg

# Upload video (requires thumbnail already generated)
uv run cli.py upload \
  --script video/scripts/<slug>.json \
  --video video/out/<slug>/final.mp4 \
  --captions video/out/<slug>/captions.srt \
  --thumbnail video/out/<slug>/thumb.jpg \
  --privacy unlisted \
  --playlist-id PL... \
  --manifest-dir seo/distribution \
  [--dry-run]

# Full pipeline: thumbnail -> upload -> playlist -> pin comment -> manifest
uv run cli.py publish \
  --script video/scripts/<slug>.json \
  --video video/out/<slug>/final.mp4 \
  --captions video/out/<slug>/captions.srt \
  --reference public/images/<slug>.webp \
  --manifest-dir seo/distribution \
  --privacy unlisted

# Read current manifest
uv run cli.py status --slug <slug> --manifest-dir seo/distribution
```

## Quota

- Default: 10,000 units/day
- `videos.insert` = 1,600 units → **~6 uploads/day** without a quota increase
- `captions.insert` = 400, `thumbnails.set` = 50, `playlistItems.insert` = 50, `commentThreads.insert` = 50
- Fine at current cadence (~1/week). Apply for a quota increase in the Google Cloud Console only if scaling past 3/day.

## AI-content disclosure

Each upload sets `status.containsSyntheticMedia = true` and prepends a disclosure line to the description. That covers YouTube's 2026 requirement for altered/synthetic content. If the API rejects the field on a future SDK version, the disclosure in the description still satisfies the policy.

## Manifest shape

One JSON file per slug at `{manifest_dir}/{slug}.json`:

```json
{
  "slug": "food-noise",
  "published_at": "2026-04-24T12:34:56+00:00",
  "youtube": {
    "status": "uploaded",
    "video_id": "abc123",
    "url": "https://www.youtube.com/watch?v=abc123",
    "privacy": "unlisted",
    "caption_id": "...",
    "thumbnail_set": true,
    "playlist_id": "PL...",
    "playlist_item_id": "...",
    "pinned_comment_id": "..."
  }
}
```

## Limits & known gaps (not automated)

- **End screens and info cards** — must be added manually in YouTube Studio. No public API.
- **Community-tab posts** — no public API.
- **Monetization settings** — limited API, configure once in Studio.
- **Channel art / About page** — set once manually.

## Editorial wrapper

For project-specific editorial (e.g. YMYL disclaimer, default tags, default playlist), use the project-level `publish-video` skill, which invokes this one.
