#!/usr/bin/env bash
# Claude FM — toggle YouTube audio playback in the terminal.
# Usage: music-toggle.sh [youtube-url]
#   - If audio is playing, stops it.
#   - Otherwise starts the given URL (or the default station).
set -u

DEFAULT_URL="https://www.youtube.com/watch?v=YmQ7jRgf4f0"
LOG="/tmp/claude-fm.log"

is_playing() { pgrep -x ffplay >/dev/null 2>&1; }

# Stopping never needs the deps — handle it before the preflight.
if is_playing; then
  pkill -x ffplay 2>/dev/null
  pkill -f "yt-dlp.*-o -" 2>/dev/null
  echo "⏹  Claude FM stopped"
  exit 0
fi

# Preflight: both tools must be on PATH to start playback.
missing=()
command -v yt-dlp >/dev/null 2>&1 || missing+=("yt-dlp")
command -v ffplay >/dev/null 2>&1 || missing+=("ffplay (ffmpeg)")
if [ "${#missing[@]}" -gt 0 ]; then
  echo "⚠  Claude FM needs: ${missing[*]}"
  echo "   Install with:  brew install yt-dlp ffmpeg"
  exit 127
fi

URL="${1:-$DEFAULT_URL}"

# bestaudio for normal videos; live streams have no audio-only track, so fall
# back to the lowest combined stream and let ffplay drop the video (-nodisp).
( yt-dlp -f "bestaudio/worstaudio/worst" -o - "$URL" 2>"$LOG" \
    | ffplay -nodisp -autoexit -loglevel quiet - >/dev/null 2>&1 ) &

# Give it a moment to fail fast on a bad URL / format.
sleep 3
if is_playing; then
  echo "▶  ✨ Claude FM playing"
else
  echo "⚠  Couldn't start playback. Last yt-dlp output:"
  tail -3 "$LOG" 2>/dev/null
  exit 1
fi
