#!/usr/bin/env bash
# add-project — wire a project into the dev-up tunnel chain.
#
#   add-project.sh web  [name]              # print the package.json change (nothing to wire)
#   add-project.sh expo <hostname> <port>   # ingress entry + cloudflared reload + dev script to paste
#
# Web projects need ZERO tunnel config (the wildcard → pubproxy → portless
# chain handles any `portless run`/`portless <name>` dev server). Expo apps
# need one specific ingress entry per app, ordered before the wildcard —
# that's the part this script edits (idempotent; config.yml backed up once).
set -euo pipefail

red()    { printf '\033[31m%s\033[0m\n' "$*" >&2; }
green()  { printf '\033[32m%s\033[0m\n' "$*" >&2; }
log()    { printf '%s\n' "$*" >&2; }
die()    { red "add-project: $*"; exit 1; }

MODE="${1:-}"
CONFIG="${DEV_UP_CONFIG:-$HOME/.cloudflared/config.yml}"

domain_from_config() {
  grep -oE "hostname: '\*\.[^']+'" "$CONFIG" | head -1 | sed "s/hostname: '\*\.//; s/'//"
}

case "$MODE" in
  web)
    NAME="${2:-<project>}"
    DOMAIN=$( [[ -f "$CONFIG" ]] && domain_from_config || echo "<DOMAIN>" )
    log ""
    log "Nothing to wire — web projects ride the wildcard. Make the dev script:"
    log ""
    log '  { "scripts": { "dev": "portless run next dev" } }'
    log "  (or explicit naming for monorepo workspaces: \"portless ${NAME}-web next dev\")"
    log ""
    log "Drop any hardcoded -p/--port flag (portless injects PORT), delete old ngrok"
    log "scripts, repoint webhook URLs to https://$NAME.$DOMAIN, then smoke:"
    log "  pnpm dev && curl -s -o /dev/null -w '%{http_code}' https://$NAME.$DOMAIN/"
    log ""
    log "Worktrees: use the direct form 'portless <branch>-$NAME <cmd>' — flat,"
    log "single-label hosts only (nested worktree hosts have no TLS cert)."
    ;;

  expo)
    HOSTNAME="${2:-}"; PORT="${3:-}"
    [[ -n "$HOSTNAME" && -n "$PORT" ]] || die "usage: add-project.sh expo <hostname> <port>   e.g. add-project.sh expo myapp-app.jkyf.dev 8084"
    [[ -f "$CONFIG" ]] || die "no $CONFIG — run setup.sh first"
    DOMAIN=$(domain_from_config)
    [[ "$HOSTNAME" == *".$DOMAIN" ]] || die "hostname $HOSTNAME is not under the tunnel domain $DOMAIN"

    if grep -q "hostname: $HOSTNAME" "$CONFIG"; then
      green "add-project: $HOSTNAME already in $CONFIG — leaving as-is"
    else
      [[ -f "$CONFIG.bak" ]] || cp "$CONFIG" "$CONFIG.bak"
      # Insert the entry immediately before the wildcard rule.
      node -e "
        const fs = require('fs');
        const lines = fs.readFileSync('$CONFIG', 'utf8').split('\n');
        const i = lines.findIndex(l => l.includes(\"hostname: '*.\"));
        if (i < 0) { console.error('no wildcard rule found in $CONFIG'); process.exit(1); }
        lines.splice(i, 0, '  - hostname: $HOSTNAME', '    service: http://127.0.0.1:$PORT', '');
        fs.writeFileSync('$CONFIG', lines.join('\n'));
      " || die "could not edit $CONFIG"
      green "add-project: added $HOSTNAME → 127.0.0.1:$PORT"
    fi

    CF_PLIST="$HOME/Library/LaunchAgents/com.cloudflare.cloudflared.plist"
    if [[ -f "$CF_PLIST" ]]; then
      launchctl unload "$CF_PLIST" 2>/dev/null || true
      launchctl load "$CF_PLIST"
      green "add-project: cloudflared reloaded"
    else
      log "add-project: restart cloudflared manually (no LaunchAgent found)"
    fi

    log ""
    log "Dev script for the Expo app's package.json (pin the port so the ingress holds):"
    log ""
    log "  \"dev\": \"EXPO_PACKAGER_PROXY_URL=https://$HOSTNAME REACT_NATIVE_PACKAGER_HOSTNAME=$HOSTNAME expo start --dev-client --port $PORT\""
    log ""
    log "Reminder: if Cloudflare Access gates *.$DOMAIN, add a Bypass application"
    log "for $HOSTNAME — the Expo dev client can't render the Access login page."
    ;;

  *)
    die "usage: add-project.sh web [name] | add-project.sh expo <hostname> <port>"
    ;;
esac
