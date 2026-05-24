#!/usr/bin/env bash
# doctor — verify the cloudflare-tunnel-portless setup is healthy.
#
# Runs infra checks fail-fast (✗), advisory checks as warnings (⚠).
# Exit 0 if all infra checks pass, 1 otherwise.

set -uo pipefail

green()  { printf '\033[32m✓\033[0m %s\n' "$*"; }
red()    { printf '\033[31m✗\033[0m %s\n' "$*"; }
yellow() { printf '\033[33m⚠\033[0m %s\n' "$*"; }
fix()    { printf '    \033[2mfix:\033[0m %s\n' "$*"; }

FAIL=0
WARN=0

ok()    { green "$1"; }
err()   { red "$1"; FAIL=$((FAIL+1)); }
warn()  { yellow "$1"; WARN=$((WARN+1)); }

# ---- 1. cloudflared binary --------------------------------------------------

CF=$(command -v cloudflared 2>/dev/null || true)
if [[ -z "$CF" ]]; then
  err "cloudflared not in PATH"
  fix "brew install cloudflare/cloudflare/cloudflared"
elif [[ "$CF" != *"$(brew --prefix 2>/dev/null)"* && "$CF" != /opt/homebrew/* && "$CF" != /usr/local/* ]]; then
  err "cloudflared at $CF is not the brew binary (likely the pnpm node-wrapper, breaks under launchd)"
  fix "pnpm rm -g cloudflared && brew install cloudflare/cloudflare/cloudflared"
else
  ok "cloudflared binary: $CF"
fi

# ---- 2. cloudflared LaunchAgent + connections -------------------------------

if launchctl list 2>/dev/null | grep -q 'com.cloudflare.cloudflared'; then
  STATUS=$(launchctl list | awk '$3=="com.cloudflare.cloudflared"{print $2}')
  if [[ "$STATUS" == "0" ]]; then
    ok "cloudflared LaunchAgent loaded (status 0)"
  else
    err "cloudflared LaunchAgent loaded but exit status $STATUS"
    fix "tail ~/.cloudflared/cloudflared.log; launchctl kickstart -k gui/\$(id -u)/com.cloudflare.cloudflared"
  fi
else
  err "cloudflared LaunchAgent not loaded"
  fix "launchctl load ~/Library/LaunchAgents/com.cloudflare.cloudflared.plist"
fi

LOG=$HOME/.cloudflared/cloudflared.log
if [[ -f "$LOG" ]]; then
  CONNS=$(grep -c "Registered tunnel connection" "$LOG" 2>/dev/null || true)
  RECENT=$(tail -200 "$LOG" 2>/dev/null | grep -c "Registered tunnel connection" || true)
  CONNS=${CONNS:-0}
  RECENT=${RECENT:-0}
  if [[ "$RECENT" -ge 3 ]]; then
    ok "cloudflared has $RECENT recent tunnel connections (need ≥3)"
  elif [[ "$CONNS" -ge 3 ]]; then
    warn "cloudflared has historical connections but <3 in tail; daemon may have flapped"
    fix "tail ~/.cloudflared/cloudflared.log"
  else
    err "cloudflared shows <3 'Registered tunnel connection' lines"
    fix "tail ~/.cloudflared/cloudflared.log"
  fi
else
  warn "cloudflared log not found at $LOG (daemon may not have run yet)"
fi

# ---- 3. config.yml ----------------------------------------------------------

CFG=$HOME/.cloudflared/config.yml
DOMAIN=""
if [[ ! -f "$CFG" ]]; then
  err "$CFG missing"
  fix "see SKILL.md step 5 for the template"
else
  TUNNEL_UUID=$(grep -E '^tunnel:' "$CFG" | awk '{print $2}' | tr -d '"' || true)
  CRED=$(grep -E '^credentials-file:' "$CFG" | awk '{print $2}' | tr -d '"' | sed "s|^~|$HOME|" || true)
  if [[ -n "$TUNNEL_UUID" && -f "$CRED" ]]; then
    if grep -q "$TUNNEL_UUID" "$CRED" 2>/dev/null; then
      ok "config.yml tunnel UUID matches credentials file"
    else
      err "config.yml tunnel UUID does not appear in credentials file"
    fi
  elif [[ -z "$TUNNEL_UUID" ]]; then
    err "config.yml has no 'tunnel:' line"
  else
    err "credentials file missing: $CRED"
  fi

  # Extract DOMAIN from the wildcard ingress rule (last *.<DOMAIN>)
  DOMAIN=$(grep -oE "hostname: ['\"]?\*\\.[a-zA-Z0-9.-]+" "$CFG" | head -1 | sed -E "s/hostname: ['\"]?\*\\.//" | tr -d "'\"" || true)
  if [[ -z "$DOMAIN" ]]; then
    err "config.yml has no '*.\$DOMAIN' wildcard rule"
    fix "add an ingress entry for *.<your-domain> → http://127.0.0.1:1354"
  else
    ok "config.yml wildcard domain: *.$DOMAIN"
  fi

  if grep -q "http_status:404" "$CFG"; then
    ok "config.yml has http_status:404 fallback"
  else
    warn "config.yml missing 'service: http_status:404' fallback rule"
  fi
fi

# ---- 4. portless ------------------------------------------------------------

if command -v portless >/dev/null 2>&1; then
  ok "portless installed: $(command -v portless)"
else
  err "portless not in PATH"
  fix "npm install -g portless"
fi

if lsof -nP -iTCP:1355 -sTCP:LISTEN >/dev/null 2>&1; then
  ok "portless proxy listening on :1355"
else
  err "nothing listening on :1355"
  fix "portless proxy start"
fi

# ---- 5. pubproxy ------------------------------------------------------------

PUBPROXY_LISTENER=$(lsof -nP -iTCP:1354 -sTCP:LISTEN 2>/dev/null | tail -1 || true)
if [[ -n "$PUBPROXY_LISTENER" ]]; then
  if [[ "$PUBPROXY_LISTENER" == *node* ]]; then
    ok "pubproxy (node) listening on :1354"
  else
    warn ":1354 listener is not node — possibly stale Caddy from old skill version"
    fix "brew services stop caddy; reload pubproxy"
  fi
else
  err "nothing listening on :1354"
  fix "launchctl load ~/Library/LaunchAgents/com.*.pubproxy.plist"
fi

if launchctl list 2>/dev/null | grep -q pubproxy; then
  STATUS=$(launchctl list | awk '/pubproxy/{print $2}' | head -1)
  if [[ "$STATUS" == "0" ]]; then
    ok "pubproxy LaunchAgent loaded (status 0)"
  else
    warn "pubproxy LaunchAgent status $STATUS"
  fi
else
  warn "no pubproxy LaunchAgent loaded (running foreground only?)"
fi

# ---- 6. DNS resolution ------------------------------------------------------

if [[ -n "$DOMAIN" ]]; then
  IPS=$(dig +short "doctor-probe.$DOMAIN" @1.1.1.1 2>/dev/null | grep -E '^[0-9]+\.[0-9]+' | head -3 || true)
  if [[ -n "$IPS" ]]; then
    ok "DNS *.$DOMAIN resolves: $(echo $IPS | tr '\n' ' ')"
  else
    err "DNS *.$DOMAIN does not resolve via 1.1.1.1"
    fix "cloudflared tunnel route dns -f dev '*.$DOMAIN'"
  fi
fi

# ---- 7. End-to-end ----------------------------------------------------------

if [[ -n "$DOMAIN" ]] && command -v portless >/dev/null 2>&1; then
  FIRST_PROJECT=$(portless list 2>/dev/null | grep -oE 'http://[a-zA-Z0-9.-]+\.localhost' | head -1 | sed 's|http://||;s|\.localhost||')
  if [[ -n "$FIRST_PROJECT" ]]; then
    CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "https://$FIRST_PROJECT.$DOMAIN/" 2>/dev/null || echo 000)
    if [[ "$CODE" =~ ^(200|301|302|307|308|401|403|404)$ ]]; then
      ok "end-to-end: https://$FIRST_PROJECT.$DOMAIN/ → $CODE"
    elif [[ "$CODE" == "502" || "$CODE" == "000" ]]; then
      err "end-to-end: https://$FIRST_PROJECT.$DOMAIN/ → $CODE (tunnel/proxy chain broken)"
    else
      warn "end-to-end: https://$FIRST_PROJECT.$DOMAIN/ → $CODE (unexpected but reachable)"
    fi
  else
    warn "no portless projects registered — start a dev server to test end-to-end"
  fi
fi

# ---- 8. Expo ingress entries -----------------------------------------------

if [[ -f "$CFG" ]]; then
  EXPO_ENTRIES=$(awk '
    /^ingress:/{in_ingress=1; next}
    in_ingress && /hostname:/ && !/\*\./ {host=$0}
    in_ingress && /service: http:\/\/127\.0\.0\.1:/ && host {
      gsub(/.*hostname: */, "", host); gsub(/['"'"'"]/, "", host);
      gsub(/.*:/, "", $0); gsub(/[^0-9].*/, "", $0);
      print host " " $0;
      host=""
    }
  ' "$CFG" 2>/dev/null || true)
  if [[ -n "$EXPO_ENTRIES" ]]; then
    while IFS= read -r entry; do
      h=$(echo "$entry" | awk '{print $1}')
      p=$(echo "$entry" | awk '{print $2}')
      if lsof -nP -iTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1; then
        ok "Expo ingress $h → :$p (Metro running)"
      else
        yellow "ℹ Expo ingress $h → :$p (Metro not running — fine if not in use)"
      fi
    done <<< "$EXPO_ENTRIES"
  fi
fi

# ---- 9. PUBLIC env audit (advisory) -----------------------------------------

if compgen -G ".env*" >/dev/null 2>&1; then
  HITS=$(grep -hE "^(EXPO_PUBLIC|NEXT_PUBLIC)_[A-Z0-9_]*=.*" .env* 2>/dev/null \
           | grep -iE 'secret|private|sk_(live|test)|api_key|password|token' || true)
  if [[ -n "$HITS" ]]; then
    warn "found *_PUBLIC_* vars matching secret-like patterns (compiled into client bundle):"
    echo "$HITS" | sed 's/^/    /'
    fix "move these to non-PUBLIC env vars, or confirm they're meant to be client-readable"
  fi
fi

# ---- summary ----------------------------------------------------------------

echo
if [[ "$FAIL" -eq 0 ]]; then
  green "doctor: $WARN warning(s), 0 failures"
  exit 0
else
  red "doctor: $FAIL failure(s), $WARN warning(s)"
  exit 1
fi
