#!/usr/bin/env bash
# dev-flow — project-agnostic master dev workflow runner.
#
# A thin deterministic layer the dev-flow REASONING skill calls. It never
# hardcodes a repo's script name — every verb resolves through the nearest
# <repo-root>/.workflow.json manifest (walked up from cwd, like git). Parse
# with python3 (NOT jq — not guaranteed on macOS; ship-check.sh uses python3).
#
# Symlink to ~/.local/bin/dev-flow (like dev.sh's dev-up/dev-down/dev-status).
#
#   dev-flow info                 print the parsed manifest
#   dev-flow doctor [--fix]       validate manifest + hook files + package mgr
#   dev-flow prep                 run hooks.prep (else: dev-up covers env seed)
#   dev-flow gate                 run hooks.gate (REQUIRED; passes exit code)
#   dev-flow smoke [args...]      run hooks.smoke (forwards args, e.g. --email)
#   dev-flow gc                   run hooks.gc, else dev-up's worktrees-gc.sh
#   dev-flow deploy-type          print the deploy field
#   dev-flow init                 scaffold a starter .workflow.json
#   dev-flow pr open  --title T [--body-file F] [--canvas URL] [--proof img...]
#   dev-flow pr merge [--squash]
#
# Idempotent. Every error prints the concrete fix command (doctor.sh house
# style). set -euo pipefail.

set -euo pipefail

# ---- house-style helpers (lifted from dev-up: dev.sh + doctor.sh) -----------

green()  { printf '\033[32m✓\033[0m %s\n' "$*"; }
red()    { printf '\033[31m✗\033[0m %s\n' "$*" >&2; }
yellow() { printf '\033[33m⚠\033[0m %s\n' "$*"; }
note()   { printf '\033[2m%s\033[0m\n' "$*"; }
fix()    { printf '    \033[2mfix:\033[0m %s\n' "$*" >&2; }
die()    { red "$1"; [[ -n "${2:-}" ]] && fix "$2"; exit 1; }

# dev-up skill dir (for the generic gc fallback). Resolve via PATH first
# (dev-up symlink -> dev.sh -> SCRIPT_DIR), else the known checkout location.
DEVUP_DIR=""
resolve_devup_dir() {
  [[ -n "$DEVUP_DIR" ]] && { printf '%s' "$DEVUP_DIR"; return; }
  local link
  if link=$(command -v dev-up 2>/dev/null); then
    DEVUP_DIR=$(cd "$(dirname "$(readlink -f "$link" 2>/dev/null || echo "$link")")" && pwd 2>/dev/null || true)
  fi
  if [[ -z "$DEVUP_DIR" || ! -f "$DEVUP_DIR/worktrees-gc.sh" ]]; then
    DEVUP_DIR="$HOME/Projects/claude-skills/skills/dev-up"
  fi
  printf '%s' "$DEVUP_DIR"
}

# ---- manifest resolution -----------------------------------------------------

MANIFEST=""
REPO_ROOT=""

find_manifest() {
  # Walk up from cwd to the nearest .workflow.json. Sets MANIFEST + REPO_ROOT.
  local dir; dir=$(pwd -P)
  while [[ "$dir" != "/" ]]; do
    if [[ -f "$dir/.workflow.json" ]]; then
      MANIFEST="$dir/.workflow.json"
      REPO_ROOT="$dir"
      return 0
    fi
    dir=$(dirname "$dir")
  done
  return 1
}

require_manifest() {
  find_manifest && return 0
  local root; root=$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)
  die "no .workflow.json found walking up from $(pwd -P)" \
      "dev-flow init    # scaffold one at $root"
}

# Read one field from the manifest with python3. $1 = python expression over
# the parsed dict `m`. Prints empty string for missing/None.
mf() {
  python3 - "$MANIFEST" "$1" <<'PY'
import json, sys
path, expr = sys.argv[1], sys.argv[2]
try:
    with open(path) as f:
        m = json.load(f)
except Exception as e:
    sys.stderr.write("parse error: %s\n" % e)
    sys.exit(3)
try:
    v = eval(expr, {"m": m, "__builtins__": {}})
except Exception:
    v = None
if v is None:
    v = ""
sys.stdout.write(str(v))
PY
}

# Infer package manager from the lockfile under REPO_ROOT (or its web/ subdir),
# matching the manifest's documented default + ship-it's lockfile rule.
infer_pm() {
  local d
  for d in "$REPO_ROOT" "$REPO_ROOT/web"; do
    [[ -f "$d/bun.lock"          || -f "$d/bun.lockb"      ]] && { echo bun;  return; }
    [[ -f "$d/pnpm-lock.yaml"    ]] && { echo pnpm; return; }
    [[ -f "$d/package-lock.json" ]] && { echo npm;  return; }
    [[ -f "$d/yarn.lock"         ]] && { echo yarn; return; }
  done
  echo ""
}

resolved_pm() {
  local declared; declared=$(mf 'm.get("packageManager")')
  [[ -n "$declared" ]] && { echo "$declared"; return; }
  infer_pm
}

# Run a hook command from REPO_ROOT, forwarding any extra args.
run_hook() { # $1=hook command string; $2.. = forwarded args
  local cmd="$1"; shift || true
  ( cd "$REPO_ROOT" && eval "$cmd" "$@" )
}

# ---- subcommands -------------------------------------------------------------

cmd_info() {
  require_manifest
  # surface a parse error explicitly rather than printing blanks
  mf 'm.get("name")' >/dev/null 2>&1 || die "could not parse $MANIFEST (invalid JSON)" \
      "dev-flow doctor --fix    # validate + scaffold gaps"
  local name deploy pm prep gate smoke gc
  name=$(mf 'm.get("name")')
  deploy=$(mf 'm.get("deploy")')
  pm=$(resolved_pm)
  prep=$(mf 'm.get("hooks",{}).get("prep")')
  gate=$(mf 'm.get("hooks",{}).get("gate")')
  smoke=$(mf 'm.get("hooks",{}).get("smoke")')
  gc=$(mf 'm.get("hooks",{}).get("gc")')
  printf 'manifest: %s\n' "$MANIFEST"
  printf '  name:           %s\n' "${name:-(unset)}"
  printf '  deploy:         %s\n' "${deploy:-(unset)}"
  printf '  packageManager: %s%s\n' "${pm:-(unknown)}" \
    "$([[ -z $(mf 'm.get("packageManager")') ]] && echo '  (inferred from lockfile)')"
  printf '  hooks.prep:     %s\n' "${prep:-(none — dev-up covers generic env seeding)}"
  printf '  hooks.gate:     %s\n' "${gate:-(MISSING — required)}"
  printf '  hooks.smoke:    %s\n' "${smoke:-(none)}"
  printf '  hooks.gc:       %s\n' "${gc:-(none — falls back to dev-up worktrees-gc.sh)}"
}

cmd_deploy_type() {
  require_manifest
  local deploy; deploy=$(mf 'm.get("deploy")')
  [[ -n "$deploy" ]] || die "manifest has no \"deploy\" field" \
      'dev-flow doctor --fix    # fills it with a default'
  printf '%s\n' "$deploy"
}

cmd_prep() {
  require_manifest
  local prep; prep=$(mf 'm.get("hooks",{}).get("prep")')
  if [[ -z "$prep" ]]; then
    note "no hooks.prep — dev-up covers generic env seeding + install for worktrees; nothing repo-specific to run"
    return 0
  fi
  note "prep: $prep  (in $REPO_ROOT)"
  run_hook "$prep"
}

cmd_gate() {
  require_manifest
  local gate; gate=$(mf 'm.get("hooks",{}).get("gate")')
  [[ -n "$gate" ]] || die "hooks.gate is required but missing in $MANIFEST" \
      'add  "hooks":{"gate":"bash web/scripts/ship-check.sh"}  (then: dev-flow doctor)'
  note "gate: $gate  (in $REPO_ROOT)"
  run_hook "$gate"   # propagate exit code: nonzero = DO NOT ship
}

cmd_smoke() {
  require_manifest
  local smoke; smoke=$(mf 'm.get("hooks",{}).get("smoke")')
  if [[ -z "$smoke" ]]; then
    note "no hooks.smoke — skipping post-deploy prod smoke (add one to verify prod-only failure classes)"
    return 0
  fi
  note "smoke: $smoke $*  (in $REPO_ROOT)"
  run_hook "$smoke" "$@"
}

cmd_gc() {
  require_manifest
  local gc; gc=$(mf 'm.get("hooks",{}).get("gc")')
  if [[ -n "$gc" ]]; then
    note "gc: $gc  (in $REPO_ROOT)"
    run_hook "$gc" "$@"
    return $?
  fi
  local devup; devup=$(resolve_devup_dir)
  local fallback="$devup/worktrees-gc.sh"
  [[ -f "$fallback" ]] || die "no hooks.gc and dev-up fallback not found at $fallback" \
      "set hooks.gc in $MANIFEST, or install the dev-up skill at $devup"
  note "no hooks.gc — falling back to dev-up's generic worktrees-gc.sh"
  ( cd "$REPO_ROOT" && bash "$fallback" "$@" )
}

# ---- doctor ------------------------------------------------------------------

FAIL=0

scaffold_manifest() { # $1=target path  $2=repo root
  local target="$1" root="$2" name pm deploy gate
  name=$(basename "$root")
  REPO_ROOT="$root"; pm=$(infer_pm)
  deploy=none
  # infer a sensible default gate hook if a known script exists
  gate=""
  if   [[ -f "$root/web/scripts/ship-check.sh" ]]; then gate="bash web/scripts/ship-check.sh"
  elif [[ -f "$root/scripts/ship-check.sh"     ]]; then gate="bash scripts/ship-check.sh"
  fi
  python3 - "$target" "$name" "$pm" "$deploy" "$gate" <<'PY'
import json, sys
target, name, pm, deploy, gate = sys.argv[1:6]
m = {
    "name": name,
    "deploy": deploy,  # auto-vercel | ota | native-rebuild | none
    "hooks": {
        "gate": gate or "bash web/scripts/ship-check.sh",  # REQUIRED: full local confidence gate
        # "prep":  "bash web/scripts/worktree-prep.sh",     # OPTIONAL repo-specific bootstrap
        # "smoke": "bash web/scripts/prod-smoke.sh",        # OPTIONAL read-only post-deploy smoke
        # "gc":    "bash web/scripts/worktrees-gc.sh",      # OPTIONAL; absent => dev-up fallback
    },
}
if pm:
    m["packageManager"] = pm
with open(target, "w") as f:
    f.write(json.dumps(m, indent=2) + "\n")
PY
}

cmd_init() {
  if find_manifest; then
    yellow "manifest already exists: $MANIFEST"
    note "run 'dev-flow doctor --fix' to fill gaps instead"
    return 0
  fi
  local root; root=$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)
  scaffold_manifest "$root/.workflow.json" "$root"
  green "scaffolded $root/.workflow.json (deploy=none — edit it, then: dev-flow doctor)"
}

cmd_doctor() {
  local do_fix=0
  [[ "${1:-}" == "--fix" ]] && do_fix=1

  if ! find_manifest; then
    local root; root=$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)
    if [[ "$do_fix" == 1 ]]; then
      scaffold_manifest "$root/.workflow.json" "$root"
      green "scaffolded $root/.workflow.json by inference"
      find_manifest
    else
      red "no .workflow.json found walking up from $(pwd -P)"
      fix "dev-flow doctor --fix    # scaffold one at $root by inference"
      exit 1
    fi
  fi
  green "manifest: $MANIFEST"

  # 1. valid JSON
  if ! mf 'm.get("name")' >/dev/null 2>&1; then
    red "manifest is not valid JSON"
    fix "fix the JSON syntax in $MANIFEST, then re-run dev-flow doctor"
    exit 1
  fi

  # 2. required fields: name, deploy
  local name deploy
  name=$(mf 'm.get("name")')
  deploy=$(mf 'm.get("deploy")')
  if [[ -n "$name" ]]; then green "name: $name"; else
    red "missing \"name\""
    fix "add  \"name\": \"$(basename "$REPO_ROOT")\"  to $MANIFEST"
    FAIL=$((FAIL+1))
  fi
  case "$deploy" in
    auto-vercel|ota|native-rebuild|none) green "deploy: $deploy" ;;
    "") red "missing \"deploy\""
        fix "add  \"deploy\": \"auto-vercel|ota|native-rebuild|none\"  to $MANIFEST"
        FAIL=$((FAIL+1)) ;;
    *)  red "deploy \"$deploy\" is not one of auto-vercel|ota|native-rebuild|none"
        fix "set  \"deploy\": \"none\"  (or the correct value) in $MANIFEST"
        FAIL=$((FAIL+1)) ;;
  esac

  # 3. packageManager matches the lockfile
  local declared inferred
  declared=$(mf 'm.get("packageManager")')
  inferred=$(infer_pm)
  if [[ -z "$declared" ]]; then
    if [[ -n "$inferred" ]]; then
      green "packageManager: (unset) — inferred $inferred from lockfile"
    else
      yellow "packageManager unset and no lockfile found under $REPO_ROOT or $REPO_ROOT/web"
      fix "add a lockfile, or set \"packageManager\" explicitly in $MANIFEST"
    fi
  elif [[ -z "$inferred" ]]; then
    yellow "packageManager declared \"$declared\" but no lockfile found to confirm it"
    fix "ensure the lockfile for $declared exists under $REPO_ROOT (bun->bun.lock, pnpm->pnpm-lock.yaml)"
  elif [[ "$declared" == "$inferred" ]]; then
    green "packageManager: $declared (matches lockfile)"
  else
    red "packageManager \"$declared\" but lockfile implies \"$inferred\""
    fix "set  \"packageManager\": \"$inferred\"  in $MANIFEST (the lockfile wins; a wrong-tool install manufactures phantom type errors)"
    FAIL=$((FAIL+1))
  fi

  # 3b. ambiguity: more than one lockfile present — infer_pm silently picks the
  # first by fixed precedence (bun>pnpm>npm>yarn, REPO_ROOT before web/). Warn so
  # a stray second lockfile doesn't quietly decide the package manager.
  # Count with [[ -f ]] tests, NOT `ls glob | wc` — under `set -euo pipefail` a
  # brace-glob with any missing file makes ls exit nonzero, pipefail propagates,
  # and doctor aborts before the hook checks ever run.
  local lf=() _d _f
  for _d in "$REPO_ROOT" "$REPO_ROOT/web"; do
    for _f in bun.lock bun.lockb pnpm-lock.yaml package-lock.json yarn.lock; do
      [[ -f "$_d/$_f" ]] && lf+=("$_d/$_f")
    done
  done
  if [[ ${#lf[@]} -gt 1 ]]; then
    yellow "multiple lockfiles found (${#lf[@]}) — inference picks bun>pnpm>npm>yarn, REPO_ROOT before web/"
    fix "set \"packageManager\" explicitly in $MANIFEST to remove the ambiguity"
  fi

  # 4. each declared hook's script file exists, and gate is present
  check_hook() { # $1=hook key  $2=required(0/1)
    local key="$1" required="$2" cmd file
    cmd=$(mf "m.get(\"hooks\",{}).get(\"$key\")")
    if [[ -z "$cmd" ]]; then
      if [[ "$required" == 1 ]]; then
        red "hooks.$key missing (required)"
        fix "add  \"hooks\":{\"$key\":\"bash web/scripts/ship-check.sh\"}  to $MANIFEST"
        FAIL=$((FAIL+1))
      else
        note "hooks.$key: (none)"
      fi
      return
    fi
    # extract the script path token (the first arg that looks like a path)
    file=$(printf '%s\n' "$cmd" | tr ' ' '\n' | grep -E '/' | head -1 || true)
    if [[ -z "$file" ]]; then
      yellow "hooks.$key: \"$cmd\" — no file path to verify (inline command?)"
      return
    fi
    if [[ -f "$REPO_ROOT/$file" || -f "$file" ]]; then
      green "hooks.$key: $cmd"
    else
      red "hooks.$key points at \"$file\" which does not exist (relative to $REPO_ROOT)"
      fix "create $REPO_ROOT/$file, or correct the path in $MANIFEST"
      FAIL=$((FAIL+1))
    fi
  }
  check_hook prep 0
  check_hook gate 1
  check_hook smoke 0
  check_hook gc 0

  # 5. dev-up gc fallback availability (advisory when no hooks.gc)
  if [[ -z "$(mf 'm.get("hooks",{}).get("gc")')" ]]; then
    local devup; devup=$(resolve_devup_dir)
    if [[ -f "$devup/worktrees-gc.sh" ]]; then
      green "gc fallback: $devup/worktrees-gc.sh"
    else
      yellow "no hooks.gc and dev-up fallback missing at $devup/worktrees-gc.sh"
      fix "set hooks.gc in $MANIFEST, or install the dev-up skill"
    fi
  fi

  echo
  if [[ "$FAIL" -eq 0 ]]; then
    green "doctor: 0 failures"
    exit 0
  fi
  red "doctor: $FAIL failure(s)"
  [[ "$do_fix" == 1 ]] && note "(--fix scaffolds a missing manifest by inference; field/hook gaps above are yours to fill)"
  exit 1
}

# ---- pr ----------------------------------------------------------------------

require_gh() {
  command -v gh >/dev/null 2>&1 || die "gh CLI not found" \
      "brew install gh && gh auth login"
  gh auth status >/dev/null 2>&1 || die "gh is not authenticated" \
      "gh auth login"
}

pr_open() {
  require_gh
  local title="" body_file="" canvas="" proofs=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --title)     title="$2"; shift 2 ;;
      --body-file) body_file="$2"; shift 2 ;;
      --canvas)    canvas="$2"; shift 2 ;;
      --proof)     proofs+=("$2"); shift 2 ;;
      *) die "dev-flow pr open: unknown arg \"$1\"" \
             'dev-flow pr open --title T [--body-file F] [--canvas URL] [--proof img...]' ;;
    esac
  done
  [[ -n "$title" ]] || die "dev-flow pr open requires --title" \
      'dev-flow pr open --title "what shipped" [--canvas URL] [--proof img...]'

  local branch; branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null) \
    || die "not inside a git checkout"
  [[ "$branch" != "HEAD" ]] || die "detached HEAD — cannot open a PR" \
      "git switch -c <feature-branch>"

  # Refuse to open a PR from the default branch (the worktree ships from a
  # feature branch; never PR main->main).
  local default_branch
  default_branch=$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|^origin/||' || true)
  default_branch="${default_branch:-main}"
  if [[ "$branch" == "$default_branch" ]]; then
    die "current branch is the default branch ($branch) — open a PR from a feature branch" \
        "git switch -c <feature-branch>"
  fi

  # Refuse to open a PR with uncommitted changes: the PR body is built from the
  # commit log (origin/<default>..HEAD), so unstaged/uncommitted work is silently
  # excluded from the PR and never pushed — you'd open a PR missing the change.
  # Warn rather than auto-stage (concurrent WIP: stage hunks, not whole files).
  # `git status --porcelain` catches BOTH tracked modifications and UNTRACKED new
  # files (diff-index misses untracked — a forgotten `git add` of a new source
  # file would be silently excluded from the PR). Respects .gitignore.
  if [[ -n "$(git status --porcelain 2>/dev/null)" ]]; then
    die "uncommitted or untracked changes in the worktree — commit them before opening the PR (they won't be pushed otherwise)" \
        "git status   # then: git add -p && git commit -m '<msg>'   # then re-run dev-flow pr open"
  fi

  git remote get-url origin >/dev/null 2>&1 || die "no 'origin' remote configured" \
      "git remote add origin <url>   # then re-run dev-flow pr open"

  note "pushing $branch to origin"
  git push -u origin "$branch" || die "git push to origin failed" \
      "check the remote + your network/auth, then re-run dev-flow pr open"

  # Build the PR body: optional file + canvas link + proof image refs +
  # a generated commit summary.
  local body; body=$(mktemp)
  if [[ -n "$body_file" ]]; then
    [[ -f "$body_file" ]] || die "--body-file not found: $body_file"
    cat "$body_file" >> "$body"
    printf '\n\n' >> "$body"
  fi
  if [[ -n "$canvas" ]]; then
    printf 'Proof canvas: %s\n\n' "$canvas" >> "$body"
  fi
  if [[ ${#proofs[@]} -gt 0 ]]; then
    printf '## Proof\n\n' >> "$body"
    local p
    for p in "${proofs[@]}"; do
      printf '![proof](%s)\n' "$p" >> "$body"
    done
    printf '\n' >> "$body"
  fi
  printf '## Changes\n\n' >> "$body"
  git log "origin/$default_branch..HEAD" --pretty='- %s' 2>/dev/null >> "$body" || true

  local url
  url=$(gh pr create --title "$title" --body-file "$body" --base "$default_branch" 2>&1) || {
    # already exists? surface its URL idempotently
    if printf '%s' "$url" | grep -q 'already exists'; then
      url=$(gh pr view --json url -q .url 2>/dev/null || true)
      yellow "PR already exists for $branch"
      [[ -n "$url" ]] && printf '%s\n' "$url"
      rm -f "$body"; return 0
    fi
    rm -f "$body"
    die "gh pr create failed: $url"
  }
  rm -f "$body"
  green "PR opened"
  printf '%s\n' "$url"
}

pr_merge() {
  require_gh
  local squash=(--merge)
  if [[ "${1:-}" == "--squash" ]]; then squash=(--squash); shift; fi
  # merge now — this is the deploy trigger
  local out
  if out=$(gh pr merge "${squash[@]}" 2>&1); then
    green "PR merged"
    printf '%s\n' "$out"
    return 0
  fi
  printf '%s\n' "$out" >&2
  if printf '%s' "$out" | grep -qiE 'not.*fast.forward|behind|not mergeable|conflict'; then
    local default_branch
    default_branch=$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|^origin/||' || true)
    default_branch="${default_branch:-main}"
    die "merge blocked — branch is behind/conflicting with base" \
        "git fetch origin && git merge origin/$default_branch --no-edit  # resolve in the worktree, re-run gate, then: dev-flow pr merge"
  fi
  die "gh pr merge failed (see output above)" \
      "gh pr checks   # inspect failing checks, then retry"
}

cmd_pr() {
  case "${1:-}" in
    open)  shift; pr_open "$@" ;;
    merge) shift; pr_merge "$@" ;;
    *) die "usage: dev-flow pr open --title T [...] | dev-flow pr merge [--squash]" ;;
  esac
}

# ---- help / dispatch ---------------------------------------------------------

usage() {
  cat <<'EOF'
dev-flow — project-agnostic dev workflow runner (reads <repo>/.workflow.json)

  dev-flow info                 print the parsed manifest
  dev-flow doctor [--fix]       validate manifest + hook files + package manager
                                --fix scaffolds a missing .workflow.json by inference
  dev-flow prep                 run hooks.prep (else: dev-up covers env seeding)
  dev-flow gate                 run hooks.gate (REQUIRED; nonzero exit = do NOT ship)
  dev-flow smoke [args...]      run hooks.smoke, forwarding args (e.g. --email)
  dev-flow gc [args...]         run hooks.gc, else dev-up's worktrees-gc.sh
  dev-flow deploy-type          print the deploy field (auto-vercel|ota|native-rebuild|none)
  dev-flow init                 scaffold a starter .workflow.json
  dev-flow pr open  --title T [--body-file F] [--canvas URL] [--proof img...]
  dev-flow pr merge [--squash]

The manifest lives at <repo-root>/.workflow.json (walked up from cwd, like git).
EOF
}

main() {
  local sub="${1:-}"; shift || true
  case "$sub" in
    info)        cmd_info "$@" ;;
    doctor)      cmd_doctor "$@" ;;
    prep)        cmd_prep "$@" ;;
    gate)        cmd_gate "$@" ;;
    smoke)       cmd_smoke "$@" ;;
    gc)          cmd_gc "$@" ;;
    deploy-type) cmd_deploy_type "$@" ;;
    init)        cmd_init "$@" ;;
    pr)          cmd_pr "$@" ;;
    -h|--help|help|"") usage ;;
    *) red "unknown subcommand: $sub"; echo; usage >&2; exit 1 ;;
  esac
}

main "$@"
