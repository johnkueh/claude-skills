#!/bin/bash
# worktrees-gc — garbage-collect agent worktrees under .claude/worktrees/.
# Lifted from drafty.im's web/scripts/worktrees-gc.sh (repo-agnostic version:
# default branch detected, recency excludes cover web + Expo build dirs).
#
# A worktree is pruned only when ALL of:
#   - its working tree is clean (no uncommitted/untracked changes)
#   - its work landed: HEAD is an ancestor of origin/<default-branch>, OR (for
#     squash/rebase merges, where ancestry never holds) gh finds a merged PR
#     for the branch whose head SHA equals the worktree HEAD
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
  landed_via=""
  if git merge-base --is-ancestor "$head" "$LANDED_REF"; then
    landed_via="$LANDED_REF ancestry"
  elif [ "$branch" != "?" ] && command -v gh >/dev/null 2>&1; then
    # Squash/rebase merges rewrite SHAs, so ancestry never holds — ask GitHub
    # for a merged PR whose head is this branch. Only trust it if the merged
    # PR's head SHA equals the worktree's HEAD: a branch that grew new commits
    # after the merge is NOT landed.
    pr_info="$(gh pr list --head "$branch" --state merged --json number,headRefOid \
      --jq '.[0] // empty | "\(.number) \(.headRefOid)"' 2>/dev/null || true)"
    pr_num="${pr_info%% *}"
    pr_head="${pr_info##* }"
    if [ -n "$pr_num" ] && [ "$pr_head" = "$head" ]; then
      landed_via="merged PR #$pr_num (squash/rebase)"
    elif [ -n "$pr_num" ]; then
      echo "KEEP (PR #$pr_num merged but worktree has newer commits): $wt [$branch]"; continue
    fi
  fi
  if [ -z "$landed_via" ]; then
    echo "KEEP (commits not on $LANDED_REF, no merged PR): $wt [$branch]"; continue
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
    echo "WOULD PRUNE ($landed_via): $wt [$branch]"
  else
    git worktree remove "$wt" --force
    [ "$branch" != "?" ] && git branch -D "$branch" >/dev/null 2>&1 || true
    echo "pruned ($landed_via): $wt [$branch]"
  fi
done
git worktree prune
