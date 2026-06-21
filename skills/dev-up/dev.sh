#!/usr/bin/env bash
# dev-up / dev-down / dev-status — one-verb dev-server lifecycle for any
# project or worktree behind the dev-up chain.
#
#   dev-up      start (or report) the dev server for the current checkout,
#               seed env into worktrees, print local + public URLs.
#   dev-down    stop the server dev-up started here (or: dev-down <name>,
#               dev-down --all).
#   dev-status  list infra health + every running route.
#
# Symlink all three names at this file; behavior dispatches on $(basename $0).
#
# Conventions it understands (zero per-project config):
#   - web dev script `portless <name> <cmd>`  -> name + cmd taken from it
#   - web dev script `portless run <cmd>`     -> name from package.json name
#   - plain dev script (`next dev`)           -> wrapped in portless, name =
#                                                repo dir basename (dots->hyphens)
#   - worktrees: name becomes <branch>-<name> (flat, single label — two-level
#     subdomains have no TLS cert on free Universal SSL)
#   - worktrees missing .env/.env.local get them copied from the main checkout;
#     a project can override by providing scripts/dev-env-seed.sh
#   - cwd inside app/ with an expo dep -> delegates to metro-takeover.sh
#
# Env overrides: DEVUP_TLD (public suffix), DEVUP_NAME (route name).
#
# Simulator pool (Expo): `dev-up --sim` (or DEVUP_HANGAR=1) leases a sim from the
# hangar pool before starting Metro, so many worktrees/agents each get their own
# sim + Metro port without colliding; `dev-down` releases it. Default behavior is
# unchanged when --sim is absent. Per-project, machine-local overrides (never
# committed — for a team monorepo that can't carry a dev script, e.g. MT_CMD /
# MT_APP_DIR / MT_SCHEME) are sourced from ~/.dev-up/projects/<repo>.env.

set -uo pipefail

SCRIPT_DIR=$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)
STATE_DIR="$HOME/.dev-up"
ROUTES_JSON="$HOME/.portless/routes.json"
PORTLESS_LOCAL_PORT=1355
PUBPROXY_PORT=1354

green()  { printf '\033[32m✓\033[0m %s\n' "$*"; }
red()    { printf '\033[31m✗\033[0m %s\n' "$*" >&2; }
yellow() { printf '\033[33m⚠\033[0m %s\n' "$*"; }
note()   { printf '\033[2m%s\033[0m\n' "$*"; }
die()    { red "$*"; exit 1; }

# ---- shared helpers ----------------------------------------------------------

detect_tld() {
  if [[ -n "${DEVUP_TLD:-}" ]]; then printf '%s' "$DEVUP_TLD"; return; fi
  local plist tld
  for plist in "$HOME"/Library/LaunchAgents/com.*.pubproxy.plist; do
    [[ -f "$plist" ]] || continue
    tld=$(plutil -extract EnvironmentVariables.PUBPROXY_TLD raw "$plist" 2>/dev/null || true)
    if [[ -n "$tld" ]]; then printf '%s' "$tld"; return; fi
  done
  # fall back to the wildcard rule in cloudflared config
  tld=$(grep -oE "hostname: ['\"]?\*\.[a-zA-Z0-9.-]+" "$HOME/.cloudflared/config.yml" 2>/dev/null \
          | head -1 | sed -E "s/hostname: ['\"]?\*\.//" | tr -d "'\"" || true)
  printf '%s' "${tld:-jkyf.dev}"
}

sanitize() { # -> lowercase, [a-z0-9-], collapse runs, trim
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//'
}

route_port() { # $1=hostname-label -> port or empty
  [[ -f "$ROUTES_JSON" ]] || return 0
  node -e "
    const r = require('$ROUTES_JSON');
    const hit = r.find(x => x.hostname === '$1.localhost');
    if (hit) process.stdout.write(String(hit.port));
  " 2>/dev/null || true
}

port_listening() { lsof -nP -iTCP:"$1" -sTCP:LISTEN -t >/dev/null 2>&1; }

kill_tree() { # $1=pid — TERM the whole descendant tree, then KILL stragglers
  local pid=$1 kids k
  kids=$(pgrep -P "$pid" 2>/dev/null || true)
  for k in $kids; do kill_tree "$k"; done
  kill "$pid" 2>/dev/null || true
}

ensure_infra() {
  local uid; uid=$(id -u)
  if ! port_listening $PUBPROXY_PORT; then
    yellow "pubproxy not listening on :$PUBPROXY_PORT — kickstarting LaunchAgent"
    local plist label
    for plist in "$HOME"/Library/LaunchAgents/com.*.pubproxy.plist; do
      [[ -f "$plist" ]] || continue
      label=$(basename "$plist" .plist)
      launchctl kickstart -k "gui/$uid/$label" 2>/dev/null \
        || launchctl load "$plist" 2>/dev/null || true
    done
    sleep 1
    port_listening $PUBPROXY_PORT || yellow "pubproxy still down — public URLs won't work (doctor.sh for details)"
  fi
  if ! launchctl list 2>/dev/null | grep -q 'com.cloudflare.cloudflared'; then
    yellow "cloudflared LaunchAgent not loaded — loading"
    launchctl load "$HOME/Library/LaunchAgents/com.cloudflare.cloudflared.plist" 2>/dev/null \
      || yellow "could not load cloudflared — public URLs won't work"
  fi
  if ! port_listening $PORTLESS_LOCAL_PORT; then
    yellow "portless proxy not on :$PORTLESS_LOCAL_PORT — starting"
    portless proxy start -p $PORTLESS_LOCAL_PORT >/dev/null 2>&1 || true
  fi
}

# ---- project resolution --------------------------------------------------------

ROOT="" MAIN="" IS_WORKTREE=0 BRANCH="" SURFACE="" WEB_DIR=""
NAME="" BASE_NAME="" CMD=""

resolve_project() {
  ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || die "not inside a git checkout"
  MAIN=$(git -C "$ROOT" worktree list --porcelain | head -1 | sed 's/^worktree //')
  [[ "$MAIN" != "$ROOT" ]] && IS_WORKTREE=1
  BRANCH=$(git -C "$ROOT" branch --show-current 2>/dev/null || echo detached)

  # surface: expo if cwd is inside an app/ dir with an expo dep (or forced)
  local forced="${1:-}"
  if [[ "$forced" == "app" ]] || { [[ "$PWD" == "$ROOT/app"* && -f "$ROOT/app/package.json" ]] \
       && grep -q '"expo"' "$ROOT/app/package.json"; }; then
    SURFACE=expo
    return
  fi
  SURFACE=web
  if [[ -f "$ROOT/web/package.json" ]]; then
    WEB_DIR="$ROOT/web"
  elif [[ -f "$ROOT/package.json" ]]; then
    WEB_DIR="$ROOT"
  else
    die "no package.json at $ROOT or $ROOT/web"
  fi
}

resolve_name_and_cmd() {
  local dev_script pkg_name dir_slug
  dev_script=$(node -e "
    const p = require('$WEB_DIR/package.json');
    process.stdout.write((p.scripts && p.scripts.dev) || '');
  ")
  [[ -n "$dev_script" ]] || die "no \"dev\" script in $WEB_DIR/package.json"

  dir_slug=$(sanitize "$(basename "$MAIN")")
  if [[ "$dev_script" =~ ^portless[[:space:]]+run[[:space:]]+(.*)$ ]]; then
    CMD="${BASH_REMATCH[1]}"
    pkg_name=$(node -e "process.stdout.write(require('$WEB_DIR/package.json').name || '')")
    BASE_NAME=$(sanitize "${pkg_name:-$dir_slug}")
  elif [[ "$dev_script" =~ ^portless[[:space:]]+([A-Za-z0-9._-]+)[[:space:]]+(.*)$ ]]; then
    BASE_NAME=$(sanitize "${BASH_REMATCH[1]}")
    CMD="${BASH_REMATCH[2]}"
  else
    BASE_NAME="$dir_slug"
    CMD="$dev_script"
  fi

  if [[ -n "${DEVUP_NAME:-}" ]]; then
    NAME=$(sanitize "$DEVUP_NAME")
  elif [[ "$IS_WORKTREE" == 1 ]]; then
    NAME="$(sanitize "$BRANCH")-$BASE_NAME"
  else
    NAME="$BASE_NAME"
  fi
  NAME=${NAME:0:63}
}

seed_worktree_env() {
  [[ "$IS_WORKTREE" == 1 ]] || return 0
  local hook
  for hook in "$WEB_DIR/scripts/dev-env-seed.sh" "$ROOT/scripts/dev-env-seed.sh"; do
    if [[ -x "$hook" ]]; then
      note "env: running project seed hook $hook"
      DEVUP_MAIN_CHECKOUT="$MAIN" DEVUP_ROOT="$ROOT" "$hook" || yellow "env seed hook failed (continuing)"
      return 0
    fi
  done
  local rel="${WEB_DIR#"$ROOT"}" f src dst copied=0
  for f in .env .env.local .env.development.local; do
    src="$MAIN$rel/$f"; dst="$WEB_DIR/$f"
    if [[ -f "$src" && ! -f "$dst" ]]; then
      cp "$src" "$dst"
      note "env: copied $f from main checkout"
      copied=1
    fi
  done
  [[ "$copied" == 0 ]] && note "env: nothing to seed (worktree already has env files, or main has none)"
}

ensure_deps() {
  [[ -d "$WEB_DIR/node_modules" ]] && return 0
  local install_dir="$WEB_DIR"
  [[ -f "$ROOT/pnpm-workspace.yaml" ]] && install_dir="$ROOT"
  yellow "node_modules missing — running pnpm install in $install_dir (one-time for this worktree)"
  (cd "$install_dir" && pnpm install) || die "pnpm install failed"
}

print_summary() { # $1=name $2=port $3=tld $4=log
  printf '\n'
  green "$1 up"
  printf '  Local:   http://%s.localhost:%s  (direct: http://127.0.0.1:%s)\n' "$1" "$PORTLESS_LOCAL_PORT" "$2"
  printf '  Public:  https://%s.%s\n' "$1" "$3"
  [[ -n "${4:-}" ]] && printf '  Log:     %s\n' "$4"
  printf '  Stop:    dev-down %s\n\n' "$1"
}

# Source machine-local, never-committed per-project overrides (MT_CMD / MT_APP_DIR
# / MT_SCHEME / MT_PORT …) keyed by the main checkout's dir name. This is how a
# team monorepo that can't carry a dev script opts in fully out-of-repo.
source_project_overrides() {
  local ovr="$STATE_DIR/projects/$(basename "$MAIN").env"
  if [[ -f "$ovr" ]]; then
    note "env: sourcing per-project overrides ($ovr)"
    set -a; . "$ovr"; set +a
  fi
}

# ---- dev-up -------------------------------------------------------------------

cmd_up() {
  local forced="" want_sim="${DEVUP_HANGAR:-0}" a
  for a in "$@"; do
    case "$a" in
      app|web) forced="$a" ;;
      --sim)   want_sim=1 ;;
    esac
  done
  resolve_project "$forced"
  source_project_overrides

  if [[ "$SURFACE" == "expo" ]]; then
    if [[ "$want_sim" == "1" ]]; then
      command -v hangar >/dev/null 2>&1 || die "--sim/DEVUP_HANGAR=1 needs 'hangar' on PATH (install the hangar skill)"
      note "hangar: leasing a simulator from the pool…"
      local leasesh; leasesh=$(hangar lease --app "$(basename "$MAIN")") || die "hangar lease failed"
      eval "$leasesh"
      note "hangar: leased UDID=${HANGAR_UDID:-?} on port ${HANGAR_PORT:-?}"
    fi
    note "expo surface — delegating to metro-takeover.sh (Metro on port ${MT_PORT:-<dev-script default>})"
    exec "$SCRIPT_DIR/metro-takeover.sh"
  fi

  local TLD; TLD=$(detect_tld)
  resolve_name_and_cmd
  ensure_infra

  # already running?
  local port; port=$(route_port "$NAME")
  if [[ -n "$port" ]] && port_listening "$port"; then
    note "$NAME already running on :$port"
    print_summary "$NAME" "$port" "$TLD" "$(cat "$STATE_DIR/$NAME/log.path" 2>/dev/null || true)"
    return 0
  fi

  seed_worktree_env
  ensure_deps

  mkdir -p "$STATE_DIR/$NAME"
  local LOG="$STATE_DIR/$NAME/server.log"
  printf '%s' "$LOG" > "$STATE_DIR/$NAME/log.path"
  printf '%s' "$WEB_DIR" > "$STATE_DIR/$NAME/dir"
  : > "$LOG"

  note "starting: portless $NAME sh -c '$CMD'  (in $WEB_DIR)"
  (
    cd "$WEB_DIR" \
      && PATH="$WEB_DIR/node_modules/.bin:$ROOT/node_modules/.bin:$PATH" \
         nohup portless "$NAME" sh -c "$CMD" > "$LOG" 2>&1 < /dev/null &
    echo $! > "$STATE_DIR/$NAME/server.pid"
  )
  local pid; pid=$(cat "$STATE_DIR/$NAME/server.pid")

  printf 'waiting for %s' "$NAME"
  local ready=0 i
  for i in $(seq 1 90); do
    if ! kill -0 "$pid" 2>/dev/null; then
      printf '\n'; red "server process died — last log lines:"; tail -15 "$LOG" >&2
      exit 1
    fi
    port=$(route_port "$NAME")
    if [[ -n "$port" ]] && curl -s -o /dev/null --max-time 2 "http://127.0.0.1:$port/" 2>/dev/null; then
      ready=1; break
    fi
    printf '.'; sleep 1
  done
  printf '\n'
  [[ "$ready" == 1 ]] || { red "not ready after 90s — tail $LOG"; exit 1; }

  # public probe (first hit may trigger a dev compile — be generous)
  local code
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 25 "https://$NAME.$TLD/" 2>/dev/null || echo 000)
  if [[ "$code" =~ ^(000|502|530)$ ]]; then
    yellow "public probe https://$NAME.$TLD/ → $code (local server is fine; tunnel chain suspect — run doctor.sh)"
  else
    note "public probe https://$NAME.$TLD/ → $code"
  fi

  print_summary "$NAME" "$port" "$TLD" "$LOG"
}

# ---- dev-down -----------------------------------------------------------------

stop_one() { # $1=name
  local name=$1 pidfile="$STATE_DIR/$1/server.pid" pid port
  port=$(route_port "$name")
  if [[ -f "$pidfile" ]]; then
    pid=$(cat "$pidfile")
    if kill -0 "$pid" 2>/dev/null; then
      kill_tree "$pid"
      sleep 1
      kill -0 "$pid" 2>/dev/null && { kill -9 "$pid" 2>/dev/null || true; }
    fi
    rm -f "$pidfile"
  fi
  # whatever still holds the route's port (orphaned next process etc.)
  if [[ -n "$port" ]] && port_listening "$port"; then
    if [[ -f "$STATE_DIR/$name/dir" || -n "${FORCE:-}" ]]; then
      local p
      for p in $(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null); do kill_tree "$p"; done
      sleep 1
    else
      yellow "$name on :$port was not started by dev-up — refusing to kill it (rerun with --force)"
      return 1
    fi
  fi
  green "$name stopped"
}

cmd_down() {
  FORCE=""
  local args=() a
  for a in "$@"; do
    [[ "$a" == "--force" ]] && FORCE=1 || args+=("$a")
  done
  # `app`/`web` forces the surface (mirrors dev-up) so dev-down works for an Expo
  # app that isn't at $ROOT/app (resolved via a per-project override, e.g. clove).
  local forced=""
  if [[ "${args[0]:-}" == "app" || "${args[0]:-}" == "web" ]]; then forced="${args[0]}"; args=("${args[@]:1}"); fi
  if [[ "${args[0]:-}" == "--all" ]]; then
    local d found=0
    for d in "$STATE_DIR"/*/; do
      [[ -f "$d/server.pid" ]] || continue
      stop_one "$(basename "$d")"; found=1
    done
    [[ "$found" == 0 ]] && note "nothing managed by dev-up is running"
    return 0
  fi
  if [[ -n "${args[0]:-}" ]]; then
    stop_one "${args[0]}"
    return $?
  fi
  # infer from cwd (or the forced surface)
  resolve_project "$forced"
  if [[ "$SURFACE" == "expo" ]]; then
    source_project_overrides
    local devs port=""
    # leased port wins (a hangar lease held for this branch), then MT_PORT, then
    # the dev script's --port, then 8081.
    if command -v hangar >/dev/null 2>&1; then
      port=$(hangar ls --json 2>/dev/null | node -e "
        let s='';process.stdin.on('data',d=>s+=d);process.stdin.on('end',()=>{
          try{const j=JSON.parse(s);const l=(j.leases||[]).find(x=>x.agent===process.argv[1]);
            process.stdout.write(l&&l.metroPort?String(l.metroPort):'');}
          catch(_){process.stdout.write('');}});" "$BRANCH" 2>/dev/null || true)
    fi
    if [[ -z "$port" ]]; then
      port="${MT_PORT:-}"
      if [[ -z "$port" ]]; then
        devs=$(node -e "process.stdout.write((require('$ROOT/app/package.json').scripts||{}).dev||'')" 2>/dev/null || true)
        port=$(printf '%s' "$devs" | grep -oE -- '--port[= ]+[0-9]+' | grep -oE '[0-9]+' | head -1)
      fi
      port="${port:-8081}"
    fi
    if port_listening "$port"; then
      local p; for p in $(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t); do kill_tree "$p"; done
      green "Metro on :$port stopped"
    else
      note "Metro not running on :$port"
    fi
    command -v hangar >/dev/null 2>&1 && { hangar release >/dev/null 2>&1 && note "hangar: released lease (sim returned to pool)"; } || true
    return 0
  fi
  resolve_name_and_cmd
  stop_one "$NAME"
}

# ---- dev-status -----------------------------------------------------------------

cmd_status() {
  local TLD; TLD=$(detect_tld)
  local cf="✗" pp="✗" pl="✗"
  launchctl list 2>/dev/null | grep -q com.cloudflare.cloudflared && cf="✓"
  port_listening $PUBPROXY_PORT && pp="✓"
  port_listening $PORTLESS_LOCAL_PORT && pl="✓"
  printf 'infra: cloudflared %s  pubproxy(:%s) %s  portless(:%s) %s  tld %s\n\n' \
    "$cf" "$PUBPROXY_PORT" "$pp" "$PORTLESS_LOCAL_PORT" "$pl" "$TLD"

  [[ -f "$ROUTES_JSON" ]] || { note "no portless routes registered"; return 0; }
  node -e "
    const routes = require('$ROUTES_JSON');
    for (const r of routes) {
      const name = r.hostname.replace(/\.localhost\$/, '');
      console.log([name, r.port, r.pid || 'alias'].join('\t'));
    }
  " | while IFS=$'\t' read -r name port pid; do
    local state="down" managed=""
    port_listening "$port" && state="up"
    [[ -d "$STATE_DIR/$name" ]] && managed=" [dev-up]"
    printf '  %-38s :%-6s %-5s%s' "$name" "$port" "$state" "$managed"
    [[ "$state" == "up" ]] && printf '  https://%s.%s' "$name" "$TLD"
    printf '\n'
  done

  # Expo ingress entries from cloudflared config
  local cfgf="$HOME/.cloudflared/config.yml"
  if [[ -f "$cfgf" ]]; then
    awk '/hostname:/ && !/\*\./ {h=$NF} /service: http:\/\/127\.0\.0\.1:/ && h {gsub(/.*:/,"",$NF); print h" "$NF; h=""}' "$cfgf" 2>/dev/null \
    | while read -r h p; do
        local state="down"
        port_listening "$p" && state="up"
        printf '  %-38s :%-6s %-5s (expo ingress)\n' "$h" "$p" "$state"
      done
  fi
}

# ---- dispatch --------------------------------------------------------------------

case "$(basename "$0")" in
  dev-up)     cmd_up "$@" ;;
  dev-down)   cmd_down "$@" ;;
  dev-status) cmd_status "$@" ;;
  *)
    case "${1:-}" in
      up)     shift; cmd_up "$@" ;;
      down)   shift; cmd_down "$@" ;;
      status) shift; cmd_status "$@" ;;
      *) die "usage: dev-up [web|app] | dev-down [name|--all] [--force] | dev-status" ;;
    esac
    ;;
esac
