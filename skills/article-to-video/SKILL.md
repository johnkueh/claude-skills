---
name: article-to-video
description: Turn a scene-script JSON into a narrated 5-minute video (MP4) with watercolor visuals and a matching SRT caption file. Captions are NOT burned into the MP4 — the SRT is uploaded to YouTube's caption layer separately so viewers can toggle + YouTube auto-translates. Uses ElevenLabs TTS (voice narration with word-level timings), Gemini 2.5 Flash Image (Nano Banana) for scene stills, and Remotion for composition. Invoke when the user wants to produce a video from a structured scene script, or says "article to video", "render video", "produce narrated video", or when another skill needs a video render backend.
---

# Article-to-Video

Render a structured scene-script JSON into a 1920×1080 MP4 with synced narration, scene images, overlays, and burned-in captions. Also emits an SRT for platform upload (YouTube, etc.).

**This skill is mechanical — it does not write scene scripts.** Scene-script authoring (hook, pacing, tone) is the caller's job. See the Input Contract below.

## Setup (one-time)

```bash
cd /Users/johnkueh/.claude/plugins/cache/johnkueh-skills/claude-skills/1.0.0/skills/article-to-video
npm install
```

If the plugin isn't installed yet, fall back to the local clone:
```bash
cd /Users/johnkueh/Projects/claude-skills/skills/article-to-video
npm install
```

Remotion (~200 MB) installs into `node_modules`. Required once per skill install.

## Environment

- `ELEVENLABS_API_KEY` — narration
- `GEMINI_API_KEY` — scene image generation

Both are read from the environment at call time. Set them in `~/.claude/settings.json` under `env` if not already there.

## Input contract — scene script JSON

The caller must provide a JSON file with this shape:

```json
{
  "slug": "food-noise",
  "video_title": "Scientists Watched 'Food Noise' Go Quiet…",
  "video_description_draft": "…multi-line description with chapter timestamps…",
  "target_duration_seconds": 300,
  "scenes": [
    {
      "id": 1,
      "section": "cold_open",
      "start": 0,
      "end": 15,
      "narration": "Exact words to be spoken in this scene.",
      "visual_brief": "Plain-English description of what Nano Banana should render for this scene. Aim for abstract watercolor style, no text in image.",
      "overlay": {
        "headline": "Penn Medicine, 2025",
        "subhead": "Electrodes in a brain, watching food thoughts",
        "citation": "Allison et al., Nature Medicine 2025"
      }
    },
    { "id": 2, "...": "..." }
  ]
}
```

**Required per scene:** `id`, `narration`, `visual_brief`.
**Optional per scene:** `section`, `overlay.{headline,subhead,citation}`.

- Narration should be speakable prose — expand symbols (`%` → "percent"), hyphens in drug codes (`LY3437943` is fine), avoid bracketed asides.
- Visual briefs should focus on composition + mood. Avoid specifying text to appear on the image — overlays handle all text separately.
- Scene timing is derived from audio length, not from `start`/`end` in the JSON. Those fields are advisory for the author.

## Commands

Run all commands from this skill's base directory.

### Full pipeline (most common)

```bash
uv run cli.py all \
    --script /absolute/path/to/scene-script.json \
    --ref /absolute/path/to/style-reference.webp \
    --out /absolute/path/to/output-directory \
    --voice brian \
    --filename final.mp4
```

This runs `tts → images → props → render` in sequence. Outputs land in `--out`:
- `audio/scene-NN.mp3` + `scene-NN.alignment.json` + `manifest.json`
- `images/scene-NN.webp`
- `props.json` — Remotion input
- `captions.srt` — YouTube-upload-ready
- `final.mp4` — 1920×1080 h264

### Individual steps (for iteration)

```bash
# Just audio — preview voice quality before spending on images
uv run cli.py tts --script SCRIPT --out OUT --voice brian

# Just images — preview visual style
uv run cli.py images --script SCRIPT --out OUT --ref REFERENCE

# Regen a single scene's audio or image without full rerun
uv run cli.py tts --script SCRIPT --out OUT --scene 5 --force
uv run cli.py images --script SCRIPT --out OUT --ref REFERENCE --scene 5 --force

# Build props from existing audio
uv run cli.py props --script SCRIPT --out OUT

# Render final MP4 from existing props + assets
uv run cli.py render --out OUT
```

### List available voices

```bash
uv run cli/tts.py voices
```

## Voice presets

`brian` (default) — resonant documentary narrator · `bill` — trustworthy older American · `daniel` — deep British · `adam` — warm American · `rachel` / `sarah` — calm female · `george` — warm British male.

Pass `--voice <name>` to the `tts` or `all` subcommand. To use a voice not in the preset list, edit `cli/tts.py` and add the ElevenLabs voice ID to the `VOICES` dict.

## Defaults

- Aspect ratio: 16:9 (1920×1080)
- FPS: 30
- Codec: h264
- Caption chunking: 6 words max per caption, break on sentence boundary
- Ken Burns alternates direction per scene (`zoom-in-center` → `zoom-in-left` → `zoom-out-center` → `zoom-in-right`)
- Scene audio uses ElevenLabs `eleven_multilingual_v2`

## Style reference image

Optional but recommended. Pass `--ref /path/to/image.webp` to hand Nano Banana a visual style to match. The skill uses a soak-stain watercolor prompt that tells Gemini to copy the medium/texture, not the composition. If no reference is passed, Gemini falls back to a no-reference watercolor prompt.

## Preview in Remotion Studio

```bash
cd skill-dir
npm run studio -- --props=/path/to/out/props.json --public-dir=/path/to/out
```

Scrub timeline, check scene transitions, edit TSX files and hot-reload.

## Cost (per 5-min video)

| Item | Cost |
|---|---|
| ElevenLabs (~4k chars) | $0.25–$0.40 |
| Nano Banana (~11 scenes × $0.04) | $0.44 |
| Remotion render | $0 (local) |
| **Total** | **~$0.70–$0.85** |

## What this skill does NOT do

- Write scene scripts (editorial work; caller's job)
- Decide hooks or target audience
- Upload to YouTube
- Generate thumbnails (Nano Banana for thumbs is a separate follow-up)
- Background music (drop a file into the composition manually if needed — TODO)

## Troubleshooting

- **"text_to_speech permission missing"** — your ElevenLabs API key was created with limited scopes. Regenerate with all permissions enabled.
- **"node_modules not found"** — run `npm install` once inside this skill directory.
- **Render output has wrong duration** — the composition uses `calculateMetadata` to adapt to whatever `props.json` is passed. If duration looks wrong, check that `--props` points to the correct file and `props.json.totalFrames` is sane.
- **Image scenes drift in style** — regenerate specific scenes with `--force --scene N`. Nano Banana is non-deterministic; 1-in-10 images need a reroll.
