#!/bin/bash
# worktrees-gc — garbage-collect agent worktrees under .claude/worktrees/.
# Lifted from drafty.im's web/scripts/worktrees-gc.sh (repo-agnostic version:
# default branch detected, recency excludes cover web + Expo build dirs).
#
# A worktree is pruned only when ALL of:
#   - its working tree is clean (no uncommitted/untracked changes)
#   - its HEAD is an ancestor of origin/<default-branch> (the work landed)
#   - nothing in it (outside node_modules/.next/.expo/ios/android build dirs)
#     was touched in the last 6 hours (a co-running agent session shows up as
#     recent mtimes — never yank a live session's floor out)
# Everything else is listed with the reason it was kept. Run at the end of a
# ship, or any time: idempotent, never touches the main checkout.
#
#   worktrees-gc.sh [--dry-run]
set -euo pipefail
DRY="${1:-}"
cd "$(git rev-parse --show-toplevel)"
git fetch origin -q

DEFAULT_BRANCH="$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|^origin/||' || true)"
if [ -z "$DEFAULT_BRANCH" ]; then
  for b in main master; do
    git show-ref --verify --quiet "refs/remotes/origin/$b" && { DEFAULT_BRANCH="$b"; break; }
  done
fi
[ -n "$DEFAULT_BRANCH" ] || { echo "worktrees-gc: cannot determine default branch" >&2; exit 1; }
LANDED_REF="origin/$DEFAULT_BRANCH"

MAIN_ROOT="$(git worktree list --porcelain | awk '/^worktree /{print $2; exit}')"

git worktree list --porcelain | awk '/^worktree /{print $2}' | while read -r wt; do
  [ "$wt" = "$MAIN_ROOT" ] && continue
  case "$wt" in */.claude/worktrees/*) ;; *) echo "KEEP (outside .claude/worktrees): $wt"; continue ;; esac
  if [ ! -d "$wt" ]; then continue; fi
  branch="$(git -C "$wt" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "?")"
  head="$(git -C "$wt" rev-parse HEAD 2>/dev/null || echo "")"
  if [ -z "$head" ]; then echo "KEEP (unreadable): $wt"; continue; fi
  if [ -n "$(git -C "$wt" status --porcelain | head -1)" ]; then
    echo "KEEP (dirty working tree): $wt"; continue
  fi
  if ! git merge-base --is-ancestor "$head" "$LANDED_REF"; then
    echo "KEEP (commits not on $LANDED_REF): $wt [$branch]"; continue
  fi
  recent="$(find "$wt" \
    -path '*/node_modules' -prune -o \
    -path '*/.next' -prune -o \
    -path '*/.expo' -prune -o \
    -path '*/ios/build' -prune -o \
    -path '*/ios/Pods' -prune -o \
    -path '*/android/build' -prune -o \
    -path '*/android/.gradle' -prune -o \
    -newermt '-6 hours' -print -quit 2>/dev/null || true)"
  if [ -n "$recent" ]; then
    echo "SKIP (recent activity — possibly a live session): $wt"; continue
  fi
  if [ "$DRY" = "--dry-run" ]; then
    echo "WOULD PRUNE: $wt [$branch]"
  else
    git worktree remove "$wt" --force
    [ "$branch" != "?" ] && git branch -D "$branch" >/dev/null 2>&1 || true
    echo "pruned: $wt [$branch]"
  fi
done
git worktree prune
