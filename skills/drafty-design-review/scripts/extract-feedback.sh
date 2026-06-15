#!/bin/bash
# Extract UI/UX feedback from a screen-recording walkthrough using Gemini
# multimodal (video + audio), into a structured feedback.json the build script
# turns into a drafty canvas.
#
# The recording is someone narrating design critique while navigating an app.
# Gemini transcribes + structures every spoken feedback point with exact
# timestamps (which drive screenshot extraction), severity, category, and a fix.
#
# usage:
#   extract-feedback.sh <video> [--estimate] [--model M] [-o feedback.json]
#
#   --estimate   print the token/cost estimate and exit (no API call). ALWAYS
#                run this first and show John before spending — see SKILL.md.
#   --model M    gemini-3.5-flash (default, best timestamps/UI-text) |
#                gemini-2.5-flash (~5x cheaper, weaker) | gemini-3-flash-preview
#   -o FILE      output path (default feedback.json)
#
# needs: GEMINI_API_KEY, ffprobe (ffmpeg), curl, python3
set -euo pipefail

MODEL="gemini-3.5-flash"; OUT="feedback.json"; ESTIMATE=0; VIDEO=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --estimate) ESTIMATE=1; shift ;;
    --model)    MODEL="$2"; shift 2 ;;
    -o|--out)   OUT="$2";   shift 2 ;;
    -*) echo "unknown flag: $1" >&2; exit 1 ;;
    *)  VIDEO="$1"; shift ;;
  esac
done
[[ -n "$VIDEO" && -f "$VIDEO" ]] || { echo "usage: extract-feedback.sh <video> [--estimate] [--model M] [-o feedback.json]" >&2; exit 1; }
command -v ffprobe >/dev/null || { echo "ffprobe (ffmpeg) required" >&2; exit 1; }

DUR=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$VIDEO")
DUR_INT=${DUR%.*}

# --- cost estimate -----------------------------------------------------------
# Gemini 3.x defaults video to LOW media resolution (~86 tok/sec incl. audio,
# measured). 2.5 defaults higher (~290 tok/sec: 258 frame + 32 audio).
# Output for a feedback catalog ≈ 3k tokens.
python3 - "$MODEL" "$DUR" <<'PY'
import sys
model, dur = sys.argv[1], float(sys.argv[2])
rate = 290 if model.startswith("gemini-2.5") else 90   # tok/sec input (default media res)
price = {  # ($/1M input, $/1M output)
  "gemini-3.5-flash": (1.50, 9.00),
  "gemini-3-flash-preview": (0.50, 3.00),
  "gemini-2.5-flash": (0.30, 2.50),
}.get(model, (1.50, 9.00))
intok = dur * rate; outtok = 3000
cost = intok/1e6*price[0] + outtok/1e6*price[1]
mm = int(dur//60); ss = int(dur%60)
print(f"video: {mm}m{ss:02d}s ({dur:.0f}s)")
print(f"model: {model}  (input ${price[0]}/1M · output ${price[1]}/1M)")
print(f"est input ~{intok/1000:.0f}k tok (default media res) + ~3k out  →  ~${cost:.2f}")
print(f"  (high media res for dense UI text roughly doubles input cost)")
PY
[[ "$ESTIMATE" -eq 1 ]] && exit 0

[[ -n "${GEMINI_API_KEY:-}" ]] || { echo "GEMINI_API_KEY not set" >&2; exit 1; }
BASE="https://generativelanguage.googleapis.com"
NUM_BYTES=$(stat -f%z "$VIDEO" 2>/dev/null || stat -c%s "$VIDEO")
MIME=$(python3 -c "import mimetypes,sys;print(mimetypes.guess_type(sys.argv[1])[0] or 'video/mp4')" "$VIDEO")

echo "⬆ uploading ($((NUM_BYTES/1024/1024))MB) via Files API…" >&2
UPLOAD_URL=$(curl -s -D - -o /dev/null \
  "${BASE}/upload/v1beta/files?key=${GEMINI_API_KEY}" \
  -H "X-Goog-Upload-Protocol: resumable" -H "X-Goog-Upload-Command: start" \
  -H "X-Goog-Upload-Header-Content-Length: ${NUM_BYTES}" \
  -H "X-Goog-Upload-Header-Content-Type: ${MIME}" \
  -H "Content-Type: application/json" -d '{"file":{"display_name":"design-review-recording"}}' \
  | grep -i "x-goog-upload-url" | tr -d '\r' | sed 's/.*: //')
[[ -n "$UPLOAD_URL" ]] || { echo "failed to start upload" >&2; exit 1; }

FILE_JSON=$(curl -s "$UPLOAD_URL" \
  -H "Content-Length: ${NUM_BYTES}" -H "X-Goog-Upload-Offset: 0" \
  -H "X-Goog-Upload-Command: upload, finalize" --data-binary "@${VIDEO}")
FILE_URI=$(python3 -c "import json,sys;d=json.load(sys.stdin);f=d.get('file',d);print(f['uri'])" <<<"$FILE_JSON")
FILE_NAME=$(python3 -c "import json,sys;d=json.load(sys.stdin);f=d.get('file',d);print(f['name'])" <<<"$FILE_JSON")
echo "  $FILE_NAME" >&2

printf "  processing" >&2
for i in $(seq 1 40); do
  ST=$(curl -s "${BASE}/v1beta/${FILE_NAME}?key=${GEMINI_API_KEY}" | python3 -c "import json,sys;print(json.load(sys.stdin).get('state','?'))")
  [[ "$ST" == "ACTIVE" ]] && { echo " ✓" >&2; break; }
  [[ "$ST" == "FAILED" ]] && { echo " FAILED" >&2; exit 1; }
  printf "." >&2; sleep 6
done

REQ=$(mktemp)
python3 - "$FILE_URI" "$MIME" > "$REQ" <<'PY'
import json, sys
uri, mime = sys.argv[1], sys.argv[2]
prompt = """You are analyzing a screen-recording walkthrough of a mobile/web app. One or more people are talking aloud while navigating the app, giving DESIGN / UI / UX FEEDBACK — critiquing craft: layout, visual hierarchy, legibility, spacing, interaction feel, motion, navigation, copy, color, empty states, onboarding.

YOUR JOB: catalog every distinct piece of UI/UX feedback they voice, faithfully, tied to exact timestamps and on-screen context. This is handed to an engineer to fix the app, so each item must be concrete and actionable.

RULES:
1. Capture THEIR opinions — paraphrase closely what is said. Do not invent feedback. If you add your own observation of a UI issue they pointed at but didn't fully articulate, mark is_speaker_opinion=false.
2. EXACT timestamps in mm:ss. timestamp_start = the moment the relevant UI is best visible (it drives automatic screenshot extraction). Be precise.
3. Split distinct points into separate items; merge only true repetition.
4. Identify the screen/feature each item is about.
5. suggested_fix: a specific, implementable change aligned to what they want.
6. transcript_quote: a short near-verbatim snippet of what was said, if audible.

Also produce app_overview (2-4 sentences on what's covered + general design state) and screen_inventory (each distinct screen + the timestamp it first appears). Capture nits too (severity 'nit'). Order feedback_items by timestamp_start ascending."""
schema = {"type":"object","properties":{
  "app_overview":{"type":"string"},
  "screen_inventory":{"type":"array","items":{"type":"object","properties":{
    "screen":{"type":"string"},"first_seen":{"type":"string"}},"required":["screen","first_seen"]}},
  "feedback_items":{"type":"array","items":{"type":"object","properties":{
    "id":{"type":"integer"},"timestamp_start":{"type":"string"},"timestamp_end":{"type":"string"},
    "screen":{"type":"string"},"on_screen":{"type":"string"},"spoken_feedback":{"type":"string"},
    "transcript_quote":{"type":"string"},"ui_ux_problem":{"type":"string"},
    "severity":{"type":"string","enum":["high","medium","low","nit"]},
    "category":{"type":"string","enum":["layout","hierarchy","legibility","interaction","navigation","copy","motion","color","spacing","empty-state","onboarding","other"]},
    "suggested_fix":{"type":"string"},"is_speaker_opinion":{"type":"boolean"}},
    "required":["id","timestamp_start","screen","on_screen","spoken_feedback","ui_ux_problem","severity","category","suggested_fix","is_speaker_opinion"]}}},
  "required":["app_overview","screen_inventory","feedback_items"]}
body={"contents":[{"role":"user","parts":[
  {"file_data":{"mime_type":mime,"file_uri":uri}},{"text":prompt}]}],
  "generationConfig":{"responseMimeType":"application/json","responseSchema":schema,"temperature":0.3,"maxOutputTokens":32000}}
print(json.dumps(body))
PY

echo "  running ${MODEL}…" >&2
RESP=$(mktemp)
curl -s "${BASE}/v1beta/models/${MODEL}:generateContent?key=${GEMINI_API_KEY}" \
  -H "Content-Type: application/json" -X POST -d @"$REQ" -o "$RESP"
rm -f "$REQ"
python3 - "$RESP" "$OUT" <<'PY'
import json, sys
resp, out = sys.argv[1], sys.argv[2]
d = json.load(open(resp))
if 'error' in d:
    raise SystemExit("ERROR: " + json.dumps(d['error'])[:400])
u = d.get('usageMetadata', {})
txt = d['candidates'][0]['content']['parts'][0]['text']
open(out, "w").write(txt)
items = json.loads(txt).get('feedback_items', [])
print(f"✓ {len(items)} feedback items → {out}")
print(f"  tokens: {u.get('promptTokenCount',0)} in / {u.get('candidatesTokenCount',0)} out  (finish: {d['candidates'][0].get('finishReason')})")
PY
rm -f "$RESP"
