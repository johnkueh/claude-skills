#!/usr/bin/env bash
# expo-qa — fingerprint gate + EAS Update publish for Expo worktree QA.
#
# Two verbs:
#   expo-qa.sh gate     Is this worktree's native layer identical to the
#                       baseline checkout's? Match → the installed dev client
#                       is valid for this branch (Metro or EAS Update both
#                       fine). Mismatch → this branch needs its own dev build;
#                       any "verified on sim" claim via the shared client is
#                       invalid. Exit 0 match / 2 mismatch / 1 error.
#   expo-qa.sh publish  Run the gate, then `eas update --branch wt/<branch>`
#                       and emit a dev-client deeplink. The wt/ prefix is
#                       enforced so a publish can never land on a release
#                       channel (channels map to branches explicitly; nothing
#                       maps to wt/*).
#   expo-qa.sh record   Pin the fingerprint the dev client was just built
#                       from (~/.expo-qa/<app>-<platform>.json). Run after
#                       building+installing a dev client (the expo-local-build
#                       wrapper does). With a record present, gate/publish
#                       also detect a STALE INSTALLED CLIENT (exit 3): tree
#                       matches baseline but the client predates it — the
#                       published update would be greyed out on the device.
#
# Composes with metro-takeover.sh: Metro is the inner loop (HMR, one worktree
# at a time on the pinned port); publish is the review path (N worktrees
# concurrently, loadable on any dev client incl. a physical phone).
#
# Conventions shared with metro-takeover.sh: app dir is $ROOT/app (or $ROOT)
# with an expo dep; the package.json "dev" script carries the env (APP_VARIANT
# etc.) used to resolve app config; scheme from app.json else `expo config`.
#
# Env overrides:
#   EQ_APP_DIR        absolute path to the Expo app directory
#   EQ_BASELINE_DIR   baseline repo root (default: the git worktree checked
#                     out on the repo's default branch)
#   EQ_PLATFORM       ios | android (default ios)
#   EQ_SCHEME         deeplink scheme (default: app.json / expo config)
#
# Flags:
#   gate    [--platform <p>] [--json]
#   publish [--platform <p>] [--message "<msg>"] [--skip-gate] [--dry-run]

set -euo pipefail

red()    { printf '\033[31m%s\033[0m\n' "$*" >&2; }
yellow() { printf '\033[33m%s\033[0m\n' "$*" >&2; }
green()  { printf '\033[32m%s\033[0m\n' "$*" >&2; }
log()    { printf '%s\n' "$*" >&2; }
die()    { red "expo-qa: $*"; exit 1; }

VERB="${1:-}"
[[ "$VERB" == "gate" || "$VERB" == "publish" || "$VERB" == "record" ]] \
  || die "usage: expo-qa.sh gate|publish|record [flags]"
shift

PLATFORM="${EQ_PLATFORM:-ios}"
EAS_ENV="${EQ_EAS_ENV:-development}"   # eas-cli requires --environment in non-interactive mode
MESSAGE=""
SKIP_GATE=0
DRY_RUN=0
JSON_OUT=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --platform)    PLATFORM="$2"; shift 2 ;;
    --message)     MESSAGE="$2"; shift 2 ;;
    --environment) EAS_ENV="$2"; shift 2 ;;
    --skip-gate)   SKIP_GATE=1; shift ;;
    --dry-run)     DRY_RUN=1; shift ;;
    --json)        JSON_OUT=1; shift ;;
    *) die "unknown flag: $1" ;;
  esac
done
[[ "$PLATFORM" == "ios" || "$PLATFORM" == "android" ]] || die "--platform must be ios or android"

# ---- locate project (same conventions as metro-takeover.sh) -----------------

ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || die "not inside a git repository"

find_app_dir() {
  local base="$1"
  for cand in "$base/app" "$base"; do
    if [[ -f "$cand/package.json" ]] && grep -q '"expo"' "$cand/package.json"; then
      printf '%s' "$cand"
      return
    fi
  done
  return 1
}

if [[ -n "${EQ_APP_DIR:-}" ]]; then
  APP_DIR="$EQ_APP_DIR"
  [[ -d "$APP_DIR" ]] || die "EQ_APP_DIR='$APP_DIR' does not exist"
else
  APP_DIR=$(find_app_dir "$ROOT") || die "no Expo app at \$ROOT/app or \$ROOT (set EQ_APP_DIR)"
fi
APP_REL="${APP_DIR#"$ROOT"}"   # e.g. "/app" or ""

# ---- locate baseline checkout ------------------------------------------------

default_branch() {
  git -C "$ROOT" symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|^origin/||' && return
  for b in main master; do
    git -C "$ROOT" show-ref --verify --quiet "refs/heads/$b" && { echo "$b"; return; }
  done
  echo main
}

BASELINE_DIR="${EQ_BASELINE_DIR:-}"
DEFAULT_BRANCH=$(default_branch)
if [[ -z "$BASELINE_DIR" ]]; then
  BASELINE_DIR=$(git -C "$ROOT" worktree list --porcelain | awk -v want="refs/heads/$DEFAULT_BRANCH" '
    /^worktree /  { wt=$2 }
    /^branch /    { if ($2 == want) { print wt; exit } }
  ')
fi
[[ -n "$BASELINE_DIR" ]] || die "no checkout of '$DEFAULT_BRANCH' found among worktrees (set EQ_BASELINE_DIR)"
[[ -d "$BASELINE_DIR" ]] || die "baseline dir '$BASELINE_DIR' does not exist"
BASELINE_APP="$BASELINE_DIR$APP_REL"
[[ -d "$BASELINE_APP" ]] || die "baseline app dir '$BASELINE_APP' does not exist"

BRANCH=$(git -C "$ROOT" branch --show-current 2>/dev/null || echo detached)
IS_BASELINE=0
[[ "$(cd "$ROOT" && pwd -P)" == "$(cd "$BASELINE_DIR" && pwd -P)" ]] && IS_BASELINE=1

# ---- fingerprint bin ---------------------------------------------------------
# Each tree MUST be fingerprinted by its own bin: with pnpm, a bin from another
# checkout resolves sources through its own symlinked node_modules and the hash
# comes out different for an identical tree (verified in practice).

find_fp_bin() {  # $1 = app dir
  local tree_root
  tree_root=$(git -C "$1" rev-parse --show-toplevel 2>/dev/null || dirname "$1")
  for cand in "$1/node_modules/.bin/fingerprint" "$tree_root/node_modules/.bin/fingerprint"; do
    [[ -x "$cand" ]] && { printf '%s' "$cand"; return; }
  done
  return 1
}

fp_version() {  # $1 = fingerprint bin path
  node -e "
    const path = require('path');
    const pkg = path.join(path.dirname(require('fs').realpathSync('$1')), '..', 'package.json');
    try { process.stdout.write(require(pkg).version); } catch (_) {}
  "
}

FP_BIN=$(find_fp_bin "$APP_DIR") \
  || die "@expo/fingerprint not found in this tree's node_modules — install deps first (it ships with expo-updates)"

TMP_DIR=$(mktemp -d /tmp/expo-qa.XXXXXX)
trap 'rm -rf "$TMP_DIR"' EXIT

generate_fp() {  # $1 = dir to fingerprint, $2 = output file
  local bin
  bin=$(find_fp_bin "$1") || die "@expo/fingerprint not found for $1 — install deps in that tree first"
  ( cd "$1" && "$bin" fingerprint:generate --platform "$PLATFORM" ) > "$2" \
    || die "fingerprint:generate failed in $1"
}

fp_hash() { node -e "process.stdout.write(require('$1').hash)"; }

# ---- recorded client fingerprint ----------------------------------------------
# `record` is run right after building+installing a dev client (the
# expo-local-build wrapper calls it). It pins what native baseline the
# installed client was built from, so `gate` can detect a third failure leg:
# branch == main natively, but the *installed client* predates main — a
# published update would list on the device but refuse to open (fingerprint
# runtime policy) or load against wrong natives (pinned runtime).

APP_SLUG=$(node -e "
  try { process.stdout.write((require('$APP_DIR/package.json').name || '').replace(/[^a-zA-Z0-9._-]/g, '-')); } catch (_) {}
")
[[ -n "$APP_SLUG" ]] || APP_SLUG=$(basename "$ROOT")
RECORD_DIR="$HOME/.expo-qa"
RECORD_FILE="$RECORD_DIR/${APP_SLUG}-${PLATFORM}.json"

run_record() {
  log "expo-qa: recording client fingerprint for $APP_SLUG [$PLATFORM]…"
  generate_fp "$APP_DIR" "$TMP_DIR/rec.json"
  local hash commit
  hash=$(fp_hash "$TMP_DIR/rec.json")
  commit=$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo "?")
  mkdir -p "$RECORD_DIR"
  node -e "
    require('fs').writeFileSync('$RECORD_FILE', JSON.stringify({
      hash: '$hash',
      platform: '$PLATFORM',
      fingerprintVersion: '$(fp_version "$FP_BIN")',
      recordedAt: new Date().toISOString(),
      commit: '$commit',
      branch: '$BRANCH',
      appDir: '$APP_DIR',
    }, null, 2) + '\n');
  "
  green "expo-qa: recorded $hash → $RECORD_FILE"
  green "  (gate will now flag when the installed client goes stale vs the tree being QA'd)"
}

# Returns 0 = fresh or no record; 1 = stale. Sets REC_HASH / REC_AT when a record exists.
check_recorded() {  # $1 = hash the client must match
  REC_HASH=""; REC_AT=""
  [[ -f "$RECORD_FILE" ]] || {
    log "expo-qa: no recorded client fingerprint ($RECORD_FILE) — run 'expo-qa.sh record' after building a dev client to enable stale-client detection"
    return 0
  }
  REC_HASH=$(node -e "try{process.stdout.write(require('$RECORD_FILE').hash||'')}catch(_){}")
  REC_AT=$(node -e "try{process.stdout.write(require('$RECORD_FILE').recordedAt||'?')}catch(_){}")
  local rec_fpver
  rec_fpver=$(node -e "try{process.stdout.write(require('$RECORD_FILE').fingerprintVersion||'')}catch(_){}")
  [[ -n "$rec_fpver" && "$rec_fpver" != "$(fp_version "$FP_BIN")" ]] && \
    yellow "expo-qa: @expo/fingerprint version skew vs recorded client ($rec_fpver → $(fp_version "$FP_BIN")) — staleness below may be algorithm drift"
  [[ "$REC_HASH" == "$1" ]] && return 0
  return 1
}

# ---- gate --------------------------------------------------------------------

stale_client_report() {
  red "expo-qa: CLIENT STALE"
  red "  tree fingerprint:              $WT_HASH"
  red "  installed client (recorded $REC_AT): $REC_HASH"
  red "  → the installed dev client was built from an older native baseline."
  red "    A published update will list on the device but won't open"
  red "    (fingerprint runtime) or will run against wrong natives (pinned)."
  red "    Rebuild + reinstall the dev client (expo-local-build), then re-run"
  red "    'expo-qa.sh record'. Override with --skip-gate if a fresher device exists."
}

run_gate() {
  log "expo-qa: fingerprinting worktree ($BRANCH) [$PLATFORM]…"
  generate_fp "$APP_DIR" "$TMP_DIR/wt.json"
  WT_HASH=$(fp_hash "$TMP_DIR/wt.json")

  if [[ "$IS_BASELINE" -eq 1 ]]; then
    green "expo-qa: this IS the baseline checkout ($DEFAULT_BRANCH) — fingerprint $WT_HASH"
    if ! check_recorded "$WT_HASH"; then
      stale_client_report
      [[ "$JSON_OUT" -eq 1 ]] && printf '{"match":true,"baseline":true,"hash":"%s","clientFresh":false,"clientHash":"%s"}\n' "$WT_HASH" "$REC_HASH"
      return 3
    fi
    [[ "$JSON_OUT" -eq 1 ]] && printf '{"match":true,"baseline":true,"hash":"%s","clientFresh":true}\n' "$WT_HASH"
    return 0
  fi

  log "expo-qa: fingerprinting baseline ($DEFAULT_BRANCH @ $BASELINE_DIR)…"
  generate_fp "$BASELINE_APP" "$TMP_DIR/base.json"
  BASE_HASH=$(fp_hash "$TMP_DIR/base.json")

  local wt_ver base_ver
  wt_ver=$(fp_version "$FP_BIN")
  base_ver=$(fp_version "$(find_fp_bin "$BASELINE_APP")")
  [[ -n "$wt_ver" && "$wt_ver" != "$base_ver" ]] && \
    yellow "expo-qa: @expo/fingerprint version skew (worktree $wt_ver vs baseline $base_ver) — a MISMATCH below may be algorithm drift, not native drift"

  if [[ "$WT_HASH" == "$BASE_HASH" ]]; then
    green "expo-qa: MATCH ($WT_HASH)"
    green "  → branch '$BRANCH' is JS-only relative to $DEFAULT_BRANCH."
    if ! check_recorded "$WT_HASH"; then
      stale_client_report
      [[ "$JSON_OUT" -eq 1 ]] && printf '{"match":true,"baseline":false,"hash":"%s","clientFresh":false,"clientHash":"%s"}\n' "$WT_HASH" "$REC_HASH"
      return 3
    fi
    green "  → the installed dev client is valid: QA via Metro (metro-takeover) or EAS Update."
    [[ "$JSON_OUT" -eq 1 ]] && printf '{"match":true,"baseline":false,"hash":"%s","clientFresh":true}\n' "$WT_HASH"
    return 0
  fi

  red "expo-qa: MISMATCH"
  red "  worktree ($BRANCH):          $WT_HASH"
  red "  baseline ($DEFAULT_BRANCH):  $BASE_HASH"
  red "  → branch '$BRANCH' changes the native layer. The shared dev client"
  red "    will NOT reflect it — 'verified on sim' via Metro or EAS Update"
  red "    would be a false positive. This branch needs its own dev build:"
  red "      eas build --profile development --platform $PLATFORM"
  log ""
  log "Differing sources:"
  "$FP_BIN" fingerprint:diff "$TMP_DIR/base.json" "$TMP_DIR/wt.json" 2>/dev/null \
    | node -e '
      let s = "";
      process.stdin.on("data", d => s += d);
      process.stdin.on("end", () => {
        try {
          const diffs = JSON.parse(s);
          for (const d of diffs.slice(0, 20)) {
            const src = d.addedSource || d.removedSource || d.beforeSource || d.afterSource || d;
            const what = src.filePath || src.id || JSON.stringify(src).slice(0, 100);
            console.log(`  ${d.op || "changed"}: ${what}`);
          }
          if (diffs.length > 20) console.log(`  … and ${diffs.length - 20} more`);
        } catch (_) { console.log(s); }
      });
    ' >&2 || true
  [[ "$JSON_OUT" -eq 1 ]] && printf '{"match":false,"baseline":false,"hash":"%s","baselineHash":"%s"}\n' "$WT_HASH" "$BASE_HASH"
  return 2
}

if [[ "$VERB" == "record" ]]; then
  run_record
  exit 0
fi

if [[ "$VERB" == "gate" ]]; then
  run_gate
  exit $?
fi

# ---- publish -----------------------------------------------------------------

if [[ "$SKIP_GATE" -eq 1 ]]; then
  yellow "expo-qa: gate skipped (--skip-gate) — you are asserting this branch is JS-only"
else
  gate_rc=0; run_gate || gate_rc=$?
  if [[ "$gate_rc" -eq 3 ]]; then
    die "installed dev client is stale — rebuild + reinstall it first (expo-local-build), or --skip-gate if you'll load this on a fresher device"
  elif [[ "$gate_rc" -ne 0 ]]; then
    die "gate failed — refusing to publish an update the installed client can't faithfully run"
  fi
fi

command -v eas >/dev/null 2>&1 || die "eas CLI not found"

[[ "$BRANCH" == "detached" ]] && die "detached HEAD — check out a branch before publishing"
if [[ "$IS_BASELINE" -eq 1 || "$BRANCH" == "$DEFAULT_BRANCH" ]]; then
  die "refusing to publish from the baseline branch ($DEFAULT_BRANCH) — this verb is for worktree/branch QA, releases have their own flow"
fi

SAFE_BRANCH=${BRANCH//\//-}
EAS_BRANCH="wt/$SAFE_BRANCH"
[[ -n "$MESSAGE" ]] || MESSAGE=$(git -C "$ROOT" log -1 --format=%s 2>/dev/null || echo "expo-qa publish")

# Resolve app config with the dev script's env (APP_VARIANT etc.) so the
# publish targets the same variant the dev client runs.
DEV_SCRIPT=$(node -e "
  const p = require('$APP_DIR/package.json');
  process.stdout.write(p.scripts && p.scripts.dev ? p.scripts.dev : '');
")
ENV_ARGS=()
while IFS= read -r kv; do ENV_ARGS+=("$kv"); done < <(
  printf '%s' "$DEV_SCRIPT" | grep -oE '[A-Z_][A-Z0-9_]*=[^ ]+' || true
)

EAS_CMD=(eas update --branch "$EAS_BRANCH" --message "$MESSAGE" --platform "$PLATFORM" --environment "$EAS_ENV" --non-interactive --json)

if [[ "$DRY_RUN" -eq 1 ]]; then
  log ""
  yellow "expo-qa: dry run — would execute in $APP_DIR:"
  log "  env: ${ENV_ARGS[*]:-"(none)"}"
  log "  cmd: ${EAS_CMD[*]}"
  exit 0
fi

log "expo-qa: publishing '$MESSAGE' to EAS branch $EAS_BRANCH [$PLATFORM]…"
UPDATE_JSON=$(cd "$APP_DIR" && env "${ENV_ARGS[@]}" "${EAS_CMD[@]}") || die "eas update failed"

# ---- emit deeplink -----------------------------------------------------------

detect_scheme() {
  if [[ -n "${EQ_SCHEME:-}" ]]; then printf '%s' "$EQ_SCHEME"; return; fi
  if [[ -f "$APP_DIR/app.json" ]]; then
    local s
    s=$(node -e "
      try {
        const j = require('$APP_DIR/app.json');
        process.stdout.write((j.expo && typeof j.expo.scheme === 'string') ? j.expo.scheme : '');
      } catch(_) {}
    ")
    [[ -n "$s" ]] && { printf '%s' "$s"; return; }
  fi
  local expo_bin=""
  for cand in "$APP_DIR/node_modules/.bin/expo" "$ROOT/node_modules/.bin/expo"; do
    [[ -x "$cand" ]] && { expo_bin="$cand"; break; }
  done
  [[ -n "$expo_bin" ]] || return 0
  ( cd "$APP_DIR" && env "${ENV_ARGS[@]}" "$expo_bin" config --json 2>/dev/null ) | node -e '
    let s = "";
    process.stdin.on("data", d => s += d);
    process.stdin.on("end", () => {
      try { process.stdout.write(JSON.parse(s).scheme || ""); } catch (_) {}
    });
  ' || true
}

printf '%s' "$UPDATE_JSON" | node -e "
  let s = '';
  process.stdin.on('data', d => s += d);
  process.stdin.on('end', () => {
    let updates;
    try { updates = JSON.parse(s); } catch (e) { console.error('expo-qa: could not parse eas output:'); console.error(s); process.exit(1); }
    if (!Array.isArray(updates)) updates = [updates];
    const scheme = process.argv[1];
    for (const u of updates) {
      const url = 'https://u.expo.dev/update/' + u.group;
      console.log('');
      console.log('  Platform:   ' + u.platform);
      console.log('  EAS branch: ' + (u.branch || '$EAS_BRANCH'));
      console.log('  Runtime:    ' + u.runtimeVersion);
      console.log('  Update URL: ' + url);
      if (scheme) {
        const dl = scheme + '://expo-development-client/?url=' + encodeURIComponent(url);
        console.log('  Deeplink:   \x1b]8;;' + dl + '\x1b\\\\' + dl + '\x1b]8;;\x1b\\\\');
      }
      if (u.manifestPermalink) console.log('  Manifest:   ' + u.manifestPermalink);
    }
    console.log('');
    console.log('  Load it: open the deeplink on a sim (argent open-url), or on a phone:');
    console.log('  dev client → login → branch picker → ' + '$EAS_BRANCH');
    console.log('');
  });
" "$(detect_scheme)"
green "expo-qa: published. Channels never map to wt/* branches — users cannot receive this."
