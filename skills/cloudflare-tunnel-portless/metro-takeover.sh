#!/usr/bin/env bash
# metro-takeover — kill any running Expo Metro, start it from the current
# worktree, wait for ready, emit a clickable dev-client deeplink.
#
# Designed for the cloudflare-tunnel-portless skill's Expo convention:
#   "dev": "EXPO_PACKAGER_PROXY_URL=https://<host> REACT_NATIVE_PACKAGER_HOSTNAME=<host> expo start --dev-client --port <N>"
#
# Autodetects everything from package.json + app.json/app.config.ts.
# Override via env vars for divergent projects:
#   MT_APP_DIR   absolute path to the Expo app directory
#   MT_PORT      Metro port (default: parse --port N from dev script, else 8081)
#   MT_URL       public tunnel URL (default: parse EXPO_PACKAGER_PROXY_URL from dev script)
#   MT_SCHEME    deeplink scheme (default: app.json expo.scheme, else `npx expo config`)

set -euo pipefail

red()    { printf '\033[31m%s\033[0m\n' "$*" >&2; }
yellow() { printf '\033[33m%s\033[0m\n' "$*" >&2; }
green()  { printf '\033[32m%s\033[0m\n' "$*" >&2; }
log()    { printf '%s\n' "$*" >&2; }

die() { red "metro-takeover: $*"; exit 1; }

# ---- locate project ---------------------------------------------------------

ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)

find_app_dir() {
  if [[ -n "${MT_APP_DIR:-}" ]]; then
    [[ -d "$MT_APP_DIR" ]] || die "MT_APP_DIR='$MT_APP_DIR' does not exist"
    printf '%s' "$MT_APP_DIR"
    return
  fi
  for cand in "$ROOT/app" "$ROOT"; do
    if [[ -f "$cand/package.json" ]] && grep -q '"expo"' "$cand/package.json"; then
      printf '%s' "$cand"
      return
    fi
  done
  die "no Expo app found at \$ROOT/app or \$ROOT (set MT_APP_DIR to override)"
}

APP_DIR=$(find_app_dir)
PKG_JSON="$APP_DIR/package.json"
[[ -f "$PKG_JSON" ]] || die "missing $PKG_JSON"

DEV_SCRIPT=$(node -e "
  const p = require('$PKG_JSON');
  process.stdout.write(p.scripts && p.scripts.dev ? p.scripts.dev : '');
")
[[ -n "$DEV_SCRIPT" ]] || die "no \"dev\" script in $PKG_JSON"

# ---- detect port ------------------------------------------------------------

PORT="${MT_PORT:-}"
if [[ -z "$PORT" ]]; then
  PORT=$(printf '%s' "$DEV_SCRIPT" | grep -oE -- '--port[= ]+[0-9]+' | grep -oE '[0-9]+' | head -1 || true)
fi
PORT="${PORT:-8081}"

# ---- detect tunnel URL ------------------------------------------------------

URL="${MT_URL:-}"
if [[ -z "$URL" ]]; then
  URL=$(printf '%s' "$DEV_SCRIPT" | grep -oE 'EXPO_PACKAGER_PROXY_URL=[^ ]+' | head -1 | cut -d= -f2- || true)
fi
if [[ -z "$URL" ]]; then
  yellow "metro-takeover: no EXPO_PACKAGER_PROXY_URL in dev script — falling back to http://localhost:$PORT (LAN-only)"
  URL="http://localhost:$PORT"
fi

# ---- detect scheme ----------------------------------------------------------

detect_scheme() {
  if [[ -n "${MT_SCHEME:-}" ]]; then
    printf '%s' "$MT_SCHEME"
    return
  fi
  # Try app.json first (cheap)
  if [[ -f "$APP_DIR/app.json" ]]; then
    local s
    s=$(node -e "
      try {
        const j = require('$APP_DIR/app.json');
        const v = (j.expo && typeof j.expo.scheme === 'string') ? j.expo.scheme : '';
        process.stdout.write(v);
      } catch(_) { process.stdout.write(''); }
    ")
    if [[ -n "$s" ]]; then
      printf '%s' "$s"
      return
    fi
  fi
  # Fall back to expo config — invoked with the dev script's env so
  # variant logic (isDev ? 'foo-dev' : 'foo') resolves correctly.
  log "metro-takeover: resolving scheme via 'npx expo config' (slow, ~3s)…"
  local env_args=()
  while IFS= read -r kv; do env_args+=("$kv"); done < <(
    printf '%s' "$DEV_SCRIPT" | grep -oE '[A-Z_][A-Z0-9_]*=[^ ]+' || true
  )
  # Resolve expo binary explicitly — pnpm monorepos hoist it to the root
  # node_modules/.bin and `npx --no-install` can fail to walk up.
  local expo_bin=""
  for cand in "$APP_DIR/node_modules/.bin/expo" \
              "$ROOT/node_modules/.bin/expo" \
              "$(command -v expo 2>/dev/null || true)"; do
    if [[ -n "$cand" && -x "$cand" ]]; then
      expo_bin="$cand"
      break
    fi
  done
  if [[ -z "$expo_bin" ]]; then
    log "metro-takeover: expo binary not found in node_modules — set MT_SCHEME"
    return
  fi
  local s
  s=$(cd "$APP_DIR" && env "${env_args[@]}" "$expo_bin" config --json 2>/dev/null \
        | node -e "
          let s='';
          process.stdin.on('data', d => s += d);
          process.stdin.on('end', () => {
            try { process.stdout.write(JSON.parse(s).scheme || ''); } catch(_) { process.stdout.write(''); }
          });
        " || true)
  printf '%s' "$s"
}

SCHEME=$(detect_scheme)
[[ -n "$SCHEME" ]] || die "could not resolve dev-client URL scheme (set MT_SCHEME)"

# ---- detect package manager -------------------------------------------------

if [[ -f "$ROOT/pnpm-lock.yaml" || -f "$APP_DIR/pnpm-lock.yaml" ]]; then
  PM=pnpm
elif [[ -f "$ROOT/yarn.lock" || -f "$APP_DIR/yarn.lock" ]]; then
  PM=yarn
elif [[ -f "$ROOT/bun.lockb" || -f "$APP_DIR/bun.lockb" ]]; then
  PM=bun
else
  PM=npm
fi

# ---- kill any existing Metro on the port ------------------------------------

PIDS=$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null || true)
if [[ -n "$PIDS" ]]; then
  log "metro-takeover: killing Metro on :$PORT (pid $(echo $PIDS | tr '\n' ' '))"
  # shellcheck disable=SC2086
  kill $PIDS 2>/dev/null || true
  for _ in 1 2 3; do
    sleep 1
    PIDS=$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null || true)
    [[ -z "$PIDS" ]] && break
  done
  if [[ -n "$PIDS" ]]; then
    yellow "metro-takeover: Metro didn't exit on SIGTERM, escalating to SIGKILL"
    # shellcheck disable=SC2086
    kill -9 $PIDS 2>/dev/null || true
    sleep 1
  fi
fi

# ---- start Metro from this worktree -----------------------------------------

BRANCH=$(git -C "$ROOT" branch --show-current 2>/dev/null || echo detached)
SAFE_BRANCH=${BRANCH//\//-}
LOG="/tmp/metro-${SAFE_BRANCH}.log"
log "metro-takeover: starting Metro in $APP_DIR ($PM dev) → $LOG"

# nohup + setsid keeps Metro alive after this script exits.
( cd "$APP_DIR" && nohup "$PM" run dev > "$LOG" 2>&1 < /dev/null & disown ) || die "failed to spawn Metro"

# ---- wait for ready ---------------------------------------------------------

printf 'metro-takeover: waiting for Metro on :%s' "$PORT" >&2
READY=0
for _ in $(seq 1 60); do
  if curl -sf -m 1 "http://127.0.0.1:$PORT/status" 2>/dev/null | grep -q "packager-status:running"; then
    READY=1
    break
  fi
  printf '.' >&2
  sleep 1
done
printf '\n' >&2

if [[ "$READY" -ne 1 ]]; then
  red "metro-takeover: Metro didn't report ready after 60s — tail $LOG for details"
  exit 1
fi
green "metro-takeover: Metro ready"

# ---- emit deeplink ----------------------------------------------------------

# urlencode just the scheme and path-unsafe chars in URL
encoded_url=$(node -e "process.stdout.write(encodeURIComponent('$URL'))")
DEEPLINK="${SCHEME}://expo-development-client/?url=${encoded_url}"

# OSC-8 hyperlink — terminals that support it (iTerm, Ghostty, Warp, WezTerm)
# render the label as a clickable link. Falls back to plain text elsewhere.
printf '\n  Deeplink: \033]8;;%s\033\\%s\033]8;;\033\\\n' "$DEEPLINK" "$DEEPLINK"
printf '  App dir:  %s\n' "$APP_DIR"
printf '  Branch:   %s\n' "$BRANCH"
printf '  Log:      %s\n\n' "$LOG"
