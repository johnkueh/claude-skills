#!/usr/bin/env bash
set -euo pipefail

# deliver.sh — publish a project's build-output/ over the Cloudflare tunnel.
#
# Usage:
#   deliver.sh <build-output-dir> [--label NAME] [--persist|--unpersist]
#
# What it does:
#   - Starts (or restarts) install-server.mjs pointed at <build-output-dir>
#   - Wires the cloudflared ingress for <label>-install.<TUNNEL_TLD>
#   - Prints the install URL
#
# The install server reads <build-output-dir> directly; there is no copy step.
# Slots are derived from filenames matching <profile>-(ios|android).(ipa|apk):
# typically dev-ios.ipa, preview-ios.ipa, prod-ios.ipa, dev-android.apk,
# prod-android.apk. Anything else in the dir is ignored.
#
# Env:
#   TUNNEL_TLD   wildcard tunnel domain (default: example.dev)

err() { echo "deliver: $*" >&2; exit 1; }

export PATH="/opt/homebrew/bin:$PATH"   # real node ahead of bun's shim
TUNNEL_TLD="${TUNNEL_TLD:-example.dev}"
LABEL=""; PERSIST=0; UNPERSIST=0; INPUT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --persist)    PERSIST=1 ;;
    --unpersist)  UNPERSIST=1 ;;
    --label)      shift; LABEL="${1:-}"; [ -n "$LABEL" ] || err "--label needs a value" ;;
    -*)           err "unknown flag: $1" ;;
    *)            [ -z "$INPUT" ] || err "only one input dir allowed (got '$INPUT' and '$1')"; INPUT="$1" ;;
  esac
  shift
done

# --unpersist can run on its own (just needs a label, real or derived from the path)
if [ "$UNPERSIST" -eq 1 ]; then
  L="$(printf '%s' "${LABEL:-$INPUT}" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9-' '-' | sed 's/-\+/-/g; s/^-//; s/-$//')"
  [ -n "$L" ] || err "--unpersist needs --label <name>"
  AGENT="dev.jkyf.expo-localbuild.$L"; PLIST="$HOME/Library/LaunchAgents/$AGENT.plist"
  launchctl bootout "gui/$(id -u)/$AGENT" 2>/dev/null || launchctl unload "$PLIST" 2>/dev/null || true
  rm -f "$PLIST" && echo "deliver: removed LaunchAgent $AGENT" || echo "deliver: (no LaunchAgent $AGENT)"
  exit 0
fi

[ -n "$INPUT" ] || err "usage: deliver.sh <build-output-dir> [--label NAME] [--persist|--unpersist]"
[ -d "$INPUT" ] || err "not a directory: $INPUT"
ARTIFACT_DIR="$(cd "$INPUT" && pwd)"

# label: grandparent of the build-output dir (…/<project>/app/build-output -> <project>)
if [ -z "$LABEL" ]; then
  gp="$(basename "$(dirname "$(dirname "$ARTIFACT_DIR")")")"
  LABEL="${gp:-build}"
fi
LABEL="$(printf '%s' "$LABEL" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9-' '-' | sed 's/-\+/-/g; s/^-//; s/-$//')"
[ -n "$LABEL" ] || LABEL=build

count_ipa=$(find "$ARTIFACT_DIR" -maxdepth 1 -type f -name "*.ipa" 2>/dev/null | wc -l | tr -d ' ')
count_apk=$(find "$ARTIFACT_DIR" -maxdepth 1 -type f -name "*.apk" 2>/dev/null | wc -l | tr -d ' ')
echo "deliver: label = $LABEL"
echo "deliver: dir   = $ARTIFACT_DIR ($count_ipa IPA, $count_apk APK)"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR="$HOME/.expo-local-build/$LABEL"
mkdir -p "$STATE_DIR"

# deterministic port per label, 1360..1459
PORT=$(( 1360 + ( $(printf '%s' "$LABEL" | cksum | cut -d' ' -f1) % 100 ) ))
PIDFILE="$STATE_DIR/server.pid"
LOGFILE="$STATE_DIR/server.log"

# --- decide the public host + wire the tunnel BEFORE starting the server,
#     so the install page's links / OTA manifest point at the right host. ---
CF_CONFIG="$HOME/.cloudflared/config.yml"
if lsof -nP -iTCP:1354 -sTCP:LISTEN >/dev/null 2>&1; then
  # portless / pubproxy present: the server registers <label>-install.localhost
  # in ~/.portless/routes.json on startup; tunnel's *.<tld> wildcard -> pubproxy:1354.
  PUBLIC_HOST="$LABEL-install.$TUNNEL_TLD"
  echo "deliver: pubproxy detected on :1354 — using portless route ($PUBLIC_HOST)"
else
  # no pubproxy: wire a dedicated cloudflared ingress rule straight to our port.
  TUNNEL="$(ps -ax -o command= 2>/dev/null | grep -E 'cloudflared.* tunnel run ' | grep -oE 'tunnel run [A-Za-z0-9_.-]+' | awk '{print $3}' | head -1)"
  HOST_SUFFIX=""; case "${TUNNEL:-}" in dev) HOST_SUFFIX="" ;; dev-*) HOST_SUFFIX="-${TUNNEL#dev-}" ;; ?*) HOST_SUFFIX="-$TUNNEL" ;; esac
  PUBLIC_HOST="$LABEL-localbuild$HOST_SUFFIX.$TUNNEL_TLD"
  if [ -z "${TUNNEL:-}" ] || ! command -v cloudflared >/dev/null 2>&1; then
    echo "deliver: ⚠ no running 'cloudflared … tunnel run <name>' found — install server will be up locally on :$PORT," >&2
    echo "deliver:   but not internet-reachable until you start cloudflared, then re-run." >&2
    PUBLIC_HOST=""
  else
    echo "deliver: no pubproxy — wiring cloudflared ingress for $PUBLIC_HOST (tunnel: $TUNNEL)"
    route_out="$(cloudflared tunnel route dns "$TUNNEL" "$PUBLIC_HOST" 2>&1)" || true
    echo "deliver:   route dns: $(echo "$route_out" | tail -1)"
    if [ -f "$CF_CONFIG" ]; then
      node "$SCRIPT_DIR/wire-ingress.mjs" "$CF_CONFIG" "$PUBLIC_HOST" "$PORT" || \
        echo "deliver:   ⚠ couldn't update $CF_CONFIG — add manually: '- hostname: $PUBLIC_HOST' / 'service: http://127.0.0.1:$PORT' before the catch-all." >&2
      pkill -HUP -f 'cloudflared.*tunnel run' 2>/dev/null && echo "deliver:   reloaded cloudflared (SIGHUP)" || echo "deliver:   (couldn't SIGHUP cloudflared — it usually hot-reloads on its own; restart it if the URL 502s)"
    else
      echo "deliver:   ⚠ no $CF_CONFIG — create it with an ingress rule for $PUBLIC_HOST -> http://127.0.0.1:$PORT (see dev-up skill)." >&2
    fi
  fi
fi
EFFECTIVE_HOST="${PUBLIC_HOST:-$LABEL-install.$TUNNEL_TLD}"

NODE_BIN="$(command -v node || true)"; [ -n "$NODE_BIN" ] || err "node not on PATH — needed for the install server"
AGENT="dev.jkyf.expo-localbuild.$LABEL"; PLIST="$HOME/Library/LaunchAgents/$AGENT.plist"
is_running() { [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE" 2>/dev/null)" 2>/dev/null; }

if [ "$PERSIST" -eq 1 ]; then
  # ----- launchd-managed (survives logout/reboot, auto-restarts) -----
  echo "deliver: persisting install server via launchd ($AGENT)"
  is_running && { kill "$(cat "$PIDFILE")" 2>/dev/null || true; rm -f "$PIDFILE"; }
  launchctl bootout "gui/$(id -u)/$AGENT" 2>/dev/null || launchctl unload "$PLIST" 2>/dev/null || true
  mkdir -p "$HOME/Library/LaunchAgents"
  cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$AGENT</string>
  <key>ProgramArguments</key><array>
    <string>$NODE_BIN</string><string>$SCRIPT_DIR/install-server.mjs</string>
  </array>
  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/><key>ThrottleInterval</key><integer>5</integer>
  <key>WorkingDirectory</key><string>$HOME</string>
  <key>EnvironmentVariables</key><dict>
    <key>HOME</key><string>$HOME</string>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>PROJECT_LABEL</key><string>$LABEL</string>
    <key>ARTIFACT_DIR</key><string>$ARTIFACT_DIR</string>
    <key>INSTALL_SERVER_PORT</key><string>$PORT</string>
    <key>TUNNEL_TLD</key><string>$TUNNEL_TLD</string>
    <key>PUBLIC_HOST</key><string>$EFFECTIVE_HOST</string>
  </dict>
  <key>StandardOutPath</key><string>$STATE_DIR/server.out.log</string>
  <key>StandardErrorPath</key><string>$STATE_DIR/server.err.log</string>
</dict></plist>
PLISTEOF
  launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null || launchctl load -w "$PLIST"
  launchctl enable "gui/$(id -u)/$AGENT" 2>/dev/null || true
  sleep 1
  curl -s -o /dev/null --max-time 3 "http://127.0.0.1:$PORT/healthz" || \
    echo "deliver: ⚠ launchd-managed server not answering on :$PORT — check 'launchctl print gui/$(id -u)/$AGENT' and $STATE_DIR/server.err.log" >&2
  echo "deliver: launchd job $AGENT loaded (KeepAlive). Stop with:  deliver.sh --unpersist --label $LABEL"
else
  # ----- ad-hoc background process (dies with the shell/job) -----
  whoami_json="$(curl -s --max-time 2 "http://127.0.0.1:$PORT/whoami" 2>/dev/null || true)"
  running_host="$(printf '%s' "$whoami_json" | sed -n 's/.*"publicHost":"\([^"]*\)".*/\1/p')"
  running_dir="$(printf '%s' "$whoami_json"  | sed -n 's/.*"artifactDir":"\([^"]*\)".*/\1/p')"
  if is_running && [ "$running_host" = "$EFFECTIVE_HOST" ] && [ "$running_dir" = "$ARTIFACT_DIR" ]; then
    echo "deliver: install server already up (pid $(cat "$PIDFILE"), port $PORT, host $running_host) — re-scans dir per request."
  else
    if is_running; then
      echo "deliver: restarting install server (was host=$running_host dir=$running_dir, want host=$EFFECTIVE_HOST dir=$ARTIFACT_DIR)"
      kill "$(cat "$PIDFILE")" 2>/dev/null || true; sleep 1
    fi
    echo "deliver: starting install server on :$PORT (log: $LOGFILE) — ad-hoc; dies with shell, use --persist for launchd"
    PROJECT_LABEL="$LABEL" ARTIFACT_DIR="$ARTIFACT_DIR" INSTALL_SERVER_PORT="$PORT" TUNNEL_TLD="$TUNNEL_TLD" PUBLIC_HOST="$EFFECTIVE_HOST" \
      nohup "$NODE_BIN" "$SCRIPT_DIR/install-server.mjs" >>"$LOGFILE" 2>&1 &
    echo $! > "$PIDFILE"
    sleep 1
    is_running || { echo "deliver: install server failed to start — see $LOGFILE" >&2; tail -n 20 "$LOGFILE" >&2 || true; exit 1; }
  fi
fi

echo
if [ -n "${PUBLIC_HOST:-}" ]; then
  echo "deliver: ===> https://$PUBLIC_HOST/   (cache-stuck on the phone? try https://$PUBLIC_HOST/install — a fresh path can't be served from cache)"
  echo "deliver:      open it on the phone. iOS: tap an IPA's Install button. Android: download the APK."
  echo "deliver:      (give it a few seconds the first time — DNS + cloudflared reload. If it 502s, the tunnel/Mac is down.)"
else
  echo "deliver:      local install page: http://127.0.0.1:$PORT/  (not yet internet-reachable — see warnings above)"
fi
[ "$PERSIST" -eq 1 ] || echo "deliver:      stop serving:  kill \$(cat $PIDFILE)"

echo "deliver: done."
