#!/usr/bin/env bash
# setup — one-time machine onboarding for the dev-up tunnel chain.
# Idempotent: safe to re-run; skips anything already in place, never clobbers
# an existing config.yml (backs up before any write).
#
#   setup.sh <domain> [--tag <short-tag>]
#
# Prereqs the HUMAN does first (dashboard clicks — this script checks and
# stops with instructions if missing):
#   - domain added as a zone on Cloudflare, nameservers switched
#   - `cloudflared tunnel login` authorized for the domain (browser)
#
# What it automates (the old SKILL.md steps 1-9):
#   brew cloudflared → tunnel create → wildcard DNS → config.yml →
#   pubproxy + cloudflared LaunchAgents → smoke test via doctor.sh
set -euo pipefail

red()    { printf '\033[31m%s\033[0m\n' "$*" >&2; }
yellow() { printf '\033[33m%s\033[0m\n' "$*" >&2; }
green()  { printf '\033[32m%s\033[0m\n' "$*" >&2; }
log()    { printf '%s\n' "$*" >&2; }
die()    { red "setup: $*"; exit 1; }

DOMAIN="${1:-}"; [[ -n "$DOMAIN" && "$DOMAIN" != --* ]] || die "usage: setup.sh <domain> [--tag <short-tag>]"
shift
TAG="jkyf"
TUNNEL_NAME="dev"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --tag)    TAG="$2"; shift 2 ;;
    --tunnel) TUNNEL_NAME="$2"; shift 2 ;;
    *) die "unknown flag: $1" ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CF_DIR="$HOME/.cloudflared"
CONFIG="$CF_DIR/config.yml"

# ---- 0. human prerequisites ----------------------------------------------------
NS=$(dig +short "$DOMAIN" NS @1.1.1.1 2>/dev/null | head -1 || true)
case "$NS" in
  *cloudflare.com.*|*cloudflare.com) green "setup: ✓ $DOMAIN is on Cloudflare DNS ($NS)" ;;
  *) die "$DOMAIN is not on Cloudflare nameservers (got: ${NS:-none}). Human steps first:
  1. Sign up at https://dash.cloudflare.com (free) and add $DOMAIN as a zone.
  2. Switch nameservers at the registrar to the two Cloudflare assigns.
  3. Wait 5-30 min, confirm: dig +short $DOMAIN NS @1.1.1.1
  Then re-run this script." ;;
esac

# ---- 1. cloudflared binary (brew, never the pnpm node-wrapper) ------------------
# Prefer the brew binary even when PATH resolves to a pnpm node-wrapper first
# (the wrapper fails under launchd: 'exec: node: not found').
CF_BIN=""
for cand in "$(brew --prefix 2>/dev/null)/opt/cloudflared/bin/cloudflared" \
            /opt/homebrew/bin/cloudflared /usr/local/bin/cloudflared; do
  [[ -x "$cand" ]] && { CF_BIN="$cand"; break; }
done
if [[ -z "$CF_BIN" ]]; then
  log "setup: installing cloudflared via brew…"
  brew install cloudflare/cloudflare/cloudflared
  CF_BIN="$(brew --prefix)/opt/cloudflared/bin/cloudflared"
fi
[[ -x "$CF_BIN" ]] || die "no usable brew cloudflared found"
cloudflared() { "$CF_BIN" "$@"; }
green "setup: ✓ cloudflared at $CF_BIN"

# ---- 2. auth --------------------------------------------------------------------
[[ -f "$CF_DIR/cert.pem" ]] || die "no $CF_DIR/cert.pem — run 'cloudflared tunnel login' (opens a browser; authorize $DOMAIN), then re-run."
green "setup: ✓ cert.pem present"

# ---- 3. tunnel ------------------------------------------------------------------
UUID=$(cloudflared tunnel list --output json 2>/dev/null | node -e "
  let s=''; process.stdin.on('data',d=>s+=d); process.stdin.on('end',()=>{
    try { const t=JSON.parse(s).find(t=>t.name==='$TUNNEL_NAME'); process.stdout.write(t?t.id:''); } catch(_){}
  });
")
if [[ -z "$UUID" ]]; then
  log "setup: creating tunnel '$TUNNEL_NAME'…"
  cloudflared tunnel create "$TUNNEL_NAME" >/dev/null
  UUID=$(cloudflared tunnel list --output json | node -e "
    let s=''; process.stdin.on('data',d=>s+=d); process.stdin.on('end',()=>{
      process.stdout.write(JSON.parse(s).find(t=>t.name==='$TUNNEL_NAME').id);
    });
  ")
fi
[[ -f "$CF_DIR/$UUID.json" ]] || die "tunnel '$TUNNEL_NAME' ($UUID) exists but $CF_DIR/$UUID.json is missing — delete the tunnel (cloudflared tunnel delete $TUNNEL_NAME) and re-run."
green "setup: ✓ tunnel '$TUNNEL_NAME' ($UUID)"

# ---- 4. wildcard DNS --------------------------------------------------------------
if ! cloudflared tunnel route dns -f "$TUNNEL_NAME" "*.$DOMAIN" 2>/dev/null; then
  yellow "setup: wildcard route failed — usually a leftover A/AAAA/CNAME for '*'."
  die "Delete the '*' record in the Cloudflare dashboard (DNS → Records) and re-run."
fi
green "setup: ✓ wildcard DNS *.$DOMAIN → tunnel"

# ---- 5. config.yml (never clobber) -----------------------------------------------
if [[ -f "$CONFIG" ]]; then
  green "setup: ✓ $CONFIG exists — leaving it alone (add-project.sh edits ingress)"
else
  cat > "$CONFIG" <<EOF
tunnel: $UUID
credentials-file: $HOME/.cloudflared/$UUID.json

ingress:
  # --- Expo projects (specific entries, ordered before the wildcard) ---
  # added by add-project.sh

  # --- Web projects via pubproxy (catch-all) ---
  - hostname: '*.$DOMAIN'
    service: http://127.0.0.1:1354

  - service: http_status:404
EOF
  green "setup: ✓ wrote $CONFIG"
fi

# ---- 6+9. pubproxy LaunchAgent ----------------------------------------------------
NODE_BIN=$(command -v node) || die "node not found"
PP_PLIST="$HOME/Library/LaunchAgents/com.$TAG.pubproxy.plist"
mkdir -p "$HOME/.portless"
if [[ ! -f "$PP_PLIST" ]]; then
  cat > "$PP_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key><string>com.$TAG.pubproxy</string>
    <key>ProgramArguments</key>
    <array>
      <string>$NODE_BIN</string>
      <string>$SCRIPT_DIR/pubproxy.js</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>$HOME/.portless/pubproxy.log</string>
    <key>StandardErrorPath</key><string>$HOME/.portless/pubproxy.log</string>
    <key>EnvironmentVariables</key>
    <dict>
      <key>HOME</key><string>$HOME</string>
      <key>PUBPROXY_PORT</key><string>1354</string>
      <key>PUBPROXY_TLD</key><string>$DOMAIN</string>
    </dict>
  </dict>
</plist>
EOF
  launchctl load "$PP_PLIST"
fi
launchctl list | grep -q "com.$TAG.pubproxy" || launchctl load "$PP_PLIST"
green "setup: ✓ pubproxy LaunchAgent loaded"

# ---- cloudflared LaunchAgent -------------------------------------------------------
CF_PLIST="$HOME/Library/LaunchAgents/com.cloudflare.cloudflared.plist"
if [[ ! -f "$CF_PLIST" ]]; then
  cat > "$CF_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key><string>com.cloudflare.cloudflared</string>
    <key>ProgramArguments</key>
    <array>
      <string>$CF_BIN</string>
      <string>tunnel</string>
      <string>--config</string>
      <string>$HOME/.cloudflared/config.yml</string>
      <string>run</string>
      <string>$TUNNEL_NAME</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>$HOME/.cloudflared/cloudflared.log</string>
    <key>StandardErrorPath</key><string>$HOME/.cloudflared/cloudflared.log</string>
    <key>EnvironmentVariables</key>
    <dict><key>HOME</key><string>$HOME</string></dict>
  </dict>
</plist>
EOF
  launchctl load "$CF_PLIST"
fi
launchctl list | grep -q "com.cloudflare.cloudflared" || launchctl load "$CF_PLIST"
green "setup: ✓ cloudflared LaunchAgent loaded"

# ---- smoke ---------------------------------------------------------------------------
sleep 3
if [[ -x "$SCRIPT_DIR/doctor.sh" ]]; then
  log ""
  log "setup: running doctor…"
  "$SCRIPT_DIR/doctor.sh" || yellow "setup: doctor reported issues — see above (a fresh tunnel can take ~30s to register)"
fi

log ""
green "setup: done. NEXT (manual, free, do it now): lock down access —"
log "  1. Zero Trust → Access → Applications → Add (Self-hosted), domain *.$DOMAIN,"
log "     Allow policy on your email. (Expo apps need a Bypass app per <project>-app host.)"
log "  2. Security → Bots → Bot Fight Mode → On."
log "  See SKILL.md 'Lock down access' for why and the Expo caveat."
