---
name: claude-fm
description: Toggle Claude FM — a single command that starts or stops background YouTube audio (lo-fi by default) playing straight in the terminal while you work. Use when the user says "play music", "claude fm", "start the music", "lofi", "stop the music", "background music", or "/music". One call toggles: plays if silent, stops if already playing.
---

# claude-fm

A toggle for background audio in the terminal. Run it once and lo-fi (or any
YouTube URL) starts playing; run it again and it stops. No window, no tab — the
audio is streamed by `yt-dlp` and played headless by `ffplay`.

This is a deliberate one-line tool: the user hits it, gets a single status line
back, and keeps working. Don't add commentary beyond the script's output.

## How to run it

The toggle script ships next to this file. Run it and report **only** the line
it prints:

```bash
"${CLAUDE_PLUGIN_ROOT}/skills/claude-fm/music-toggle.sh"
```

- No argument → toggles the default station (lo-fi).
- A YouTube URL argument → starts that URL instead (only when nothing is
  playing; if audio is already playing, any call just stops it).

```bash
# Start a specific stream
"${CLAUDE_PLUGIN_ROOT}/skills/claude-fm/music-toggle.sh" "https://www.youtube.com/watch?v=<id>"
```

If `${CLAUDE_PLUGIN_ROOT}` isn't set in your environment, run the
`music-toggle.sh` that sits in this skill's own directory.

## Output lines

The script prints exactly one of:

- `▶  ✨ Claude FM playing` — started
- `⏹  Claude FM stopped` — stopped
- `⚠  Claude FM needs: …` — a dependency is missing (see Setup)
- `⚠  Couldn't start playback…` — bad URL / no playable format

Relay that line verbatim. Nothing else is needed.

## Setup

Two CLI tools must be on PATH:

```bash
brew install yt-dlp ffmpeg
```

`yt-dlp` pulls the audio stream; `ffmpeg` provides `ffplay`, which plays it
headless (`-nodisp`). The script preflight-checks both and tells the user the
exact `brew` line if either is missing — so you don't need to check first, just
run it and relay the message.

## Optional: a "now playing" statusline indicator

The toggle already confirms start/stop, so this is purely a persistent reminder.
Claude Code allows only **one** statusline command, so this isn't bundled — it
would clobber whatever statusline the user already has. If they want the
indicator, add this one line to their own `statusline.sh` (a `pgrep` on the
player process):

```bash
# Shows "✨ Claude FM" only while audio is playing
pgrep -x ffplay >/dev/null 2>&1 && printf ' | ✨ Claude FM'
```
