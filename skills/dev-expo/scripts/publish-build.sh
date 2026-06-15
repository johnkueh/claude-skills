#!/usr/bin/env bash
# publish-build — durable, Mac-independent delivery of a locally-built IPA.
#
# Uploads the IPA + an iOS OTA manifest.plist to Vercel Blob (so installs work
# with the Mac asleep), then creates/updates ONE drafty canvas per project
# ("<label> builds") with an Install button for the latest build and a history
# table. The canvas URL is stable — bookmark it on the phone.
#
#   publish-build.sh <build-output-dir|ipa> [--label NAME] [--slot dev-ios]
#
# Token resolution (one SHARED store for all projects, path-namespaced under
# build-artifacts/<label>/): $BLOB_READ_WRITE_TOKEN, else
# ~/.expo-local-build/blob-token (a file holding the token). Swap the store by
# swapping that file.
#
# State per project in ~/.expo-local-build/<label>/:
#   builds.json   append-only build history (rendered into the canvas)
#   canvas-slug   the drafty slug after the first push
#
# Android note: APKs are just files — the same Blob upload works, the canvas
# links them as a plain download (no manifest needed). iOS is the fiddly path
# this script automates.
set -euo pipefail

red()   { printf '\033[31m%s\033[0m\n' "$*" >&2; }
green() { printf '\033[32m%s\033[0m\n' "$*" >&2; }
log()   { printf '%s\n' "$*" >&2; }
die()   { red "publish-build: $*"; exit 1; }

SRC="${1:-}"; [[ -n "$SRC" ]] || die "usage: publish-build.sh <build-output-dir|ipa> [--label NAME] [--slot dev-ios]"
shift
LABEL=""; SLOT="dev-ios"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --label) LABEL="$2"; shift 2 ;;
    --slot)  SLOT="$2"; shift 2 ;;
    *) die "unknown flag: $1" ;;
  esac
done

if [[ -d "$SRC" ]]; then
  IPA="$SRC/$SLOT.ipa"
else
  IPA="$SRC"
fi
[[ -f "$IPA" ]] || die "no IPA at $IPA"
# Absolutize before any `cd` (metadata extraction cd's into $TMP first, which
# breaks a relative IPA path — exactly what post-build.sh passes via --output).
IPA="$(cd "$(dirname "$IPA")" && pwd)/$(basename "$IPA")"
if [[ -z "$LABEL" ]]; then
  # Default label = the repo the IPA lives in (e.g. myapp.com → myapp-com),
  # matching deliver.sh's convention. Fall back to the grandparent dir name.
  repo_root=$(cd "$(dirname "$IPA")" && git rev-parse --show-toplevel 2>/dev/null || true)
  if [[ -n "$repo_root" ]]; then
    LABEL=$(basename "$repo_root" | tr '.' '-')
  else
    LABEL=$(basename "$(dirname "$(dirname "$IPA")")" | tr '.' '-')
  fi
fi

# ---- token -------------------------------------------------------------------
TOKEN="${BLOB_READ_WRITE_TOKEN:-}"
TOKEN_FILE="$HOME/.expo-local-build/blob-token"
[[ -z "$TOKEN" && -f "$TOKEN_FILE" ]] && TOKEN=$(tr -d '[:space:]' < "$TOKEN_FILE")
[[ -n "$TOKEN" ]] || die "no Blob token: set BLOB_READ_WRITE_TOKEN or put one in $TOKEN_FILE"
export BLOB_READ_WRITE_TOKEN="$TOKEN"

command -v vercel >/dev/null || die "vercel CLI not found"
command -v drafty >/dev/null || die "drafty CLI not found (drafty plugin)"

STATE_DIR="$HOME/.expo-local-build/$LABEL"
mkdir -p "$STATE_DIR"
TMP=$(mktemp -d /tmp/publish-build.XXXXXX)
trap 'rm -rf "$TMP"' EXIT

# ---- IPA metadata ------------------------------------------------------------
log "publish-build: reading IPA metadata…"
( cd "$TMP" && unzip -q -o "$IPA" 'Payload/*/Info.plist' 'Payload/*/EXUpdates.bundle/fingerprint' 2>/dev/null ) || true
INFO=$(find "$TMP/Payload" -maxdepth 2 -name Info.plist | head -1)
[[ -n "$INFO" ]] || die "could not extract Info.plist from $IPA"
BUNDLE_ID=$(plutil -extract CFBundleIdentifier raw "$INFO")
VERSION=$(plutil -extract CFBundleShortVersionString raw "$INFO")
TITLE=$(plutil -extract CFBundleDisplayName raw "$INFO" 2>/dev/null || plutil -extract CFBundleName raw "$INFO")
RUNTIME=$(find "$TMP/Payload" -path '*EXUpdates.bundle/fingerprint' -exec cat {} \; 2>/dev/null || echo "")

# Git context if the IPA lives inside a repo
REPO=$(cd "$(dirname "$IPA")" && git rev-parse --show-toplevel 2>/dev/null || true)
COMMIT="" ; BRANCH=""
if [[ -n "$REPO" ]]; then
  COMMIT=$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || true)
  BRANCH=$(git -C "$REPO" branch --show-current 2>/dev/null || true)
fi
STAMP="${COMMIT:-$(date +%Y%m%d%H%M)}"
SIZE_MB=$(du -m "$IPA" | cut -f1)

# ---- upload IPA + manifest ----------------------------------------------------
blob_put() {  # $1 = file, $2 = pathname, $3 = content-type (optional)
  # vercel CLI prints the Success URL to stderr when stdout is piped — capture
  # both streams, strip ANSI, and never let grep's no-match kill the script.
  local ct=() out
  [[ -n "${3:-}" ]] && ct=(--content-type "$3")
  out=$(vercel blob put "$1" --access public --pathname "$2" --add-random-suffix true "${ct[@]}" 2>&1 || true)
  printf '%s' "$out" | sed $'s/\x1b\\[[0-9;]*m//g' | grep -oE 'https://[^ ]*\.blob\.vercel-storage\.com[^ ]*' | head -1 || true
}

log "publish-build: uploading IPA ($SIZE_MB MB) to Blob…"
IPA_URL=$(blob_put "$IPA" "build-artifacts/$LABEL/$SLOT-$STAMP.ipa" "application/octet-stream") || true
[[ -n "$IPA_URL" ]] || die "IPA upload failed (check the Blob token / vercel CLI output)"
green "publish-build: IPA → $IPA_URL"

cat > "$TMP/manifest.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>items</key><array><dict>
    <key>assets</key><array><dict>
      <key>kind</key><string>software-package</string>
      <key>url</key><string>$IPA_URL</string>
    </dict></array>
    <key>metadata</key><dict>
      <key>bundle-identifier</key><string>$BUNDLE_ID</string>
      <key>bundle-version</key><string>$VERSION</string>
      <key>kind</key><string>software</string>
      <key>title</key><string>$TITLE</string>
    </dict>
  </dict></array>
</dict></plist>
EOF
MANIFEST_URL=$(blob_put "$TMP/manifest.plist" "build-artifacts/$LABEL/$SLOT-$STAMP-manifest.plist" "text/xml") || true
[[ -n "$MANIFEST_URL" ]] || die "manifest upload failed"
ITMS="itms-services://?action=download-manifest&url=$(node -e "process.stdout.write(encodeURIComponent('$MANIFEST_URL'))")"
green "publish-build: manifest → $MANIFEST_URL"

# ---- record history -----------------------------------------------------------
BUILDS_JSON="$STATE_DIR/builds.json"
[[ -f "$BUILDS_JSON" ]] || echo "[]" > "$BUILDS_JSON"
node -e "
  const fs = require('fs');
  const builds = JSON.parse(fs.readFileSync('$BUILDS_JSON', 'utf8'));
  builds.unshift({
    slot: '$SLOT', version: '$VERSION', commit: '$COMMIT', branch: '$BRANCH',
    runtime: '$RUNTIME', sizeMb: $SIZE_MB, date: new Date().toISOString(),
    ipaUrl: '$IPA_URL', itms: '$ITMS',
  });
  fs.writeFileSync('$BUILDS_JSON', JSON.stringify(builds.slice(0, 50), null, 2));
"

# ---- render + push the canvas ---------------------------------------------------
node -e "
  const fs = require('fs');
  const builds = JSON.parse(fs.readFileSync('$BUILDS_JSON', 'utf8'));
  const [latest, ...rest] = builds;
  const esc = (s) => String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;');
  const row = (b) => \`<tr><td>\${esc(b.slot)}</td><td>\${esc(b.version)}</td><td><code>\${esc(b.commit || '?')}</code> \${esc(b.branch || '')}</td><td>\${new Date(b.date).toISOString().slice(0,16).replace('T',' ')}</td><td><a href=\"\${b.itms}\" target=\"_top\">install</a></td></tr>\`;
  const html = \`<!doctype html><html><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><style>
    :root { color-scheme: light dark; }
    body { font: 16px/1.5 -apple-system, system-ui, sans-serif; max-width: 640px; margin: 2rem auto; padding: 0 1rem; }
    .latest { border: 1px solid color-mix(in srgb, currentColor 20%, transparent); border-radius: 12px; padding: 1.25rem; }
    .install { display: inline-block; background: #c800de; color: #fff; padding: .65rem 1.6rem; border-radius: 10px; font-weight: 600; text-decoration: none; }
    table { border-collapse: collapse; width: 100%; font-size: 14px; margin-top: .5rem; }
    td, th { text-align: left; padding: .3rem .5rem; border-bottom: 1px solid color-mix(in srgb, currentColor 15%, transparent); }
    .meta { font-size: 14px; opacity: .75; } code { font-size: 13px; }
  </style></head><body>
  <h1>$LABEL builds</h1>
  <div class=\"latest\">
    <h2 style=\"margin-top:0\">Latest — \${esc(latest.slot)} \${esc(latest.version)}</h2>
    <p class=\"meta\"><code>\${esc(latest.commit || '?')}</code> on \${esc(latest.branch || '?')} · \${latest.sizeMb} MB · runtime <code>\${esc((latest.runtime||'').slice(0,12))}</code> · \${new Date(latest.date).toUTCString()}</p>
    <p><a class=\"install\" href=\"\${latest.itms}\" target=\"_top\">Install on iPhone</a></p>
    <p class=\"meta\">Tap from Safari on the phone. If nothing happens inside this canvas, open the <a href=\"\${latest.ipaUrl}\">raw IPA</a>'s install via the history link below in a full tab.</p>
  </div>
  \${rest.length ? \`<h2>Previous builds</h2><table><tr><th>slot</th><th>version</th><th>commit</th><th>date (UTC)</th><th></th></tr>\${rest.map(row).join('')}</table>\` : ''}
  </body></html>\`;
  fs.writeFileSync('$TMP/canvas.html', html);
"

SLUG_FILE="$STATE_DIR/canvas-slug"
PUSH_ARGS=(--title "$LABEL builds" --project "$LABEL" --tag builds)
[[ -f "$SLUG_FILE" ]] && PUSH_ARGS+=(--slug "$(cat "$SLUG_FILE")")
log "publish-build: pushing canvas…"
PUSH_OUT=$(drafty canvas push "$TMP/canvas.html" "${PUSH_ARGS[@]}" 2>&1) || die "drafty push failed: $PUSH_OUT"
CANVAS_URL=$(printf '%s' "$PUSH_OUT" | grep -oE 'https://drafty.im/canvas/[a-z0-9-]+' | head -1)
[[ -n "$CANVAS_URL" && ! -f "$SLUG_FILE" ]] && basename "$CANVAS_URL" > "$SLUG_FILE"

green "publish-build: done."
printf '\n  Canvas:  %s\n  Install: %s\n  IPA:     %s\n\n' "${CANVAS_URL:-?}" "$ITMS" "$IPA_URL"
