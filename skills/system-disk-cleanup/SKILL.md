---
name: system-disk-cleanup
description: Scan and clean up disk space on macOS. Use when the user asks about disk space, storage, freeing up space, cleaning their Mac, or mentions their disk is full. Triggers on requests like "check disk space", "free up space", "what's using my disk", "clean up my Mac", "disk is full", or "storage hogs".
---

# Disk Cleanup for macOS

## Quick Scan

```bash
df -h /                       # macOS shows the sealed system snapshot here — usually misleading
df -h /System/Volumes/Data    # THIS is the real user data volume on Apple Silicon — always check
df -h | grep -v "devfs\|map " # all volumes (catches simulator runtime APFS partitions)
```

`/` on Apple Silicon is a sealed read-only snapshot. The actual user disk usage is on
`/System/Volumes/Data`. Always report the Data volume to the user, not the root snapshot —
they can diverge by hundreds of GB.

## Find Space Hogs — go wide first

Don't just look at `~/Library`. Scan all the places that commonly hide tens of GB:

```bash
# Top-level user folders
du -sh ~/Projects ~/Downloads ~/Documents ~/Movies ~/Desktop ~/Music ~/Pictures 2>/dev/null

# Hidden directories in home (the big surprise — often 50+ GB hidden here)
du -sh ~/.[!.]* 2>/dev/null | sort -hr | head -20

# Library breakdown
du -sh ~/Library/* 2>/dev/null | sort -hr | head -10

# System Library (Xcode/CoreSimulator can hide 30+ GB here, owned by root)
du -sh /Library/* 2>/dev/null | sort -hr | head -10

# Applications
du -sh /Applications/* 2>/dev/null | sort -hr | head -15

# Caches breakdown
du -sh ~/Library/Caches/* 2>/dev/null | sort -hr | head -10
du -sh ~/.cache/* 2>/dev/null | sort -hr | head -10
```

## Common Hidden Hogs (in ~/.something)

These are NOT in `~/Library` and are missed by default scans. Check them first.

| Location | Typical Size | What It Is | Safe to Clean? |
|---|---|---|---|
| `~/.cache/uv` | 5–10G | uv (Python) package cache | Yes — `uv cache clean` |
| `~/.cache/huggingface` | 5–20G | Downloaded ML models | Only if you don't need them locally |
| `~/.cache/puppeteer` | 500M–2G | Puppeteer Chromium | Regenerates |
| `~/.gradle/caches` | 10–20G | Gradle build cache | Yes — regenerates |
| `~/.android/avd` | 5–30G | Android emulator disk images | Only if you don't use emulator |
| `~/.expo` | 1–5G | Expo CLI cache | Yes |
| `~/.bun` | 500M–2G | Bun runtime | Only if not using Bun |
| `~/.rustup` | 2–5G | Rust toolchains | Only if not using Rust |
| `~/.npm` | 1–5G | npm cache | `npm cache clean --force` |
| `~/.claude` | 1–3G | Claude Code state | ⚠️ Careful — contains plugins/skills |

## Known Space Hogs Reference

### CocoaPods Cache
`~/Library/Caches/CocoaPods/Pods` can grow to **20G+**. Safe to delete.
```bash
rm -rf ~/Library/Caches/CocoaPods/Pods
```

### CoreSimulator (TWO locations!)
```bash
# User devices (apps installed grow these)
du -sh ~/Library/Developer/CoreSimulator/Devices/* | sort -hr

# System runtime volumes — often 15G+ EACH, separate APFS partitions
du -sh /Library/Developer/CoreSimulator/Volumes/*
ls /Library/Developer/CoreSimulator/Volumes/   # one folder per installed iOS version

# Check what runtimes are installed
xcrun simctl runtime list

# Delete old runtimes via Xcode → Settings → Platforms, or:
sudo rm -rf /Library/Developer/CoreSimulator/Volumes/iOS_OLDVERSION
# (Xcode needs to be quit first)

# Remove unavailable simulators (often does nothing if all sims are still "available")
xcrun simctl delete unavailable

# To shrink a specific bloated device, erase it instead of deleting:
xcrun simctl erase <UUID>
```

Note: A single iOS simulator device with apps installed and run can hit 10–15G on its own.
List individual device sizes to find the offenders.

### Xcode Multiple Versions
Users sometimes have `Xcode.app` AND `Xcode-26.4.1.app` etc — each is 4–7G.
Flag duplicate Xcode installs.

### Git Worktrees with node_modules (huge for monorepos)
**This is invisible to most users.** A pnpm/npm monorepo with N git worktrees has N copies of
`node_modules`. Each can be 3–5G. 10 worktrees = 30–50G.

```bash
# In any git repo, list worktrees
git worktree list

# For each, check size + safety to delete
for wt in .claude/worktrees/*/; do
  name=$(basename "$wt")
  branch=$(git -C "$wt" branch --show-current 2>/dev/null)
  dirty=$(git -C "$wt" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
  last=$(git -C "$wt" log -1 --format='%cr' 2>/dev/null)
  merged=$(git -C "$wt" merge-base --is-ancestor HEAD origin/master 2>/dev/null && echo MERGED || echo unmerged)
  unpushed=$(git -C "$wt" log @{u}..HEAD --oneline 2>/dev/null | wc -l | tr -d ' ')
  size=$(du -sh "$wt" 2>/dev/null | cut -f1)
  echo "$name | $branch | $size | dirty=$dirty | $last | $merged | unpushed=$unpushed"
done

# Remove safely (preserves branch, just removes the checkout)
git worktree remove --force <path>
```

**Always check `dirty` and `unpushed` before removing.** Worktrees with unpushed commits
or uncommitted changes need user confirmation. Offer to push the branch first as a safety net.

### Stale Project Build Artifacts
Scan ALL projects, not just current one:
```bash
# Next.js, dist, build, turbo caches
find ~/Projects -type d \( -name ".next" -o -name "dist" -o -name "build" -o -name ".turbo" \) -prune 2>/dev/null \
  | xargs du -sh 2>/dev/null | sort -hr | head -15

# Python virtualenvs in projects (separate from system Python)
find ~/Projects -type d \( -name ".venv" -o -name "venv" \) -prune 2>/dev/null \
  | xargs du -sh 2>/dev/null | sort -hr | head -10

# All node_modules (find duplicates across worktrees)
find ~/Projects -type d -name "node_modules" -prune 2>/dev/null \
  | xargs du -sh 2>/dev/null | sort -hr | head -15
```

### Old Log Directories (the "what is this?" finds)
Apps sometimes leave behind log directories that grow unbounded and are forgotten when
the app is uninstalled. Look for hidden dirs in `~/` with names you don't recognize:
```bash
ls -la ~/.??* | grep ^d   # dot-directories
```
Examples encountered: `~/.happy/logs` (319 files, 7G, from a tool no longer in use).
Always investigate before deleting (`ls`, `cat settings.json`, etc.) — show contents to the
user and confirm.

## Package Manager Caches

| Item | Check Size | Clean Command |
|------|-----------|---------------|
| pnpm | `du -sh ~/Library/pnpm/store` | `pnpm store prune` |
| npm | `du -sh ~/.npm` | `npm cache clean --force` (or `rm -rf ~/.npm`) |
| yarn | `du -sh ~/Library/Caches/Yarn` | `yarn cache clean` |
| pip | `du -sh ~/Library/Caches/pip` | `pip cache purge` |
| uv | `du -sh ~/.cache/uv` | `uv cache clean` |
| CocoaPods | `du -sh ~/Library/Caches/CocoaPods` | `rm -rf ~/Library/Caches/CocoaPods/Pods` |
| Gradle | `du -sh ~/.gradle/caches` | `rm -rf ~/.gradle/caches` |
| HuggingFace | `du -sh ~/.cache/huggingface` | `rm -rf ~/.cache/huggingface` |

**Note on pnpm:** Because pnpm hardlinks across node_modules, deleting a project's
node_modules may free less actual space than `du` suggests. Don't over-promise the
savings — show the actual `df` delta afterward.

## Docker (when running)
```bash
docker system df          # show usage
docker system prune -a -f # prune everything
docker builder prune -f   # just build cache
```

## Xcode / iOS
```bash
# DerivedData — always safe, rebuilds
rm -rf ~/Library/Developer/Xcode/DerivedData/*

# Device support (old iOS device symbols)
du -sh ~/Library/Developer/Xcode/iOS\ DeviceSupport
```

## App Caches (safe to nuke)
```bash
rm -rf ~/Library/Caches/Google/*           # Chrome
rm -rf ~/Library/Caches/com.spotify.client/*
rm -rf ~/Library/Caches/ms-playwright      # Playwright browsers
rm -rf ~/Library/Caches/Cypress
```

## Android SDK
```bash
du -sh ~/Library/Android/sdk    # 15–25G typically
du -sh ~/.gradle                # 10–20G
du -sh ~/.android               # 5–30G (mostly AVDs)
# If not doing Android dev, all three can go (plus Android Studio.app in /Applications)
```

## APFS Snapshots (rare but worth knowing)
If you delete a lot but disk doesn't free, snapshots may be holding the data:
```bash
tmutil listlocalsnapshots /
# OS-update snapshots usually clear themselves; a reboot helps APFS settle.
# To force-thin:
sudo tmutil thinlocalsnapshots / 999999999999 4
```

## Workflow

1. **Run `df -h /System/Volumes/Data`** (NOT just `df -h /`) — that's the real usage on Apple Silicon.
2. Run the wide scan: `~/Library`, `~/.*`, `~/Projects`, `/Library`, `/Applications`.
3. For projects, scan for node_modules, .next/dist/build, .venv across ALL of `~/Projects`.
4. For monorepos with git worktrees, enumerate worktrees with dirty/unpushed status.
5. Present findings as a table with sizes and cleanup recommendations, ranked by payoff.
6. **Ask user which items to clean before deleting.** Never delete without confirmation,
   especially for worktrees, .happy-style mystery dirs, or anything with possible user state.
7. After cleanup, run `df -h /System/Volumes/Data` to show actual space recovered.
8. If `df` doesn't show expected savings, suspect APFS snapshots or concurrent macOS activity.

## Tips and Gotchas

- **`df -h /` lies** on Apple Silicon — always check `/System/Volumes/Data` for real numbers.
- **Hidden dot-dirs in `~/` hold the most surprises**: `~/.cache/*`, `~/.gradle`, `~/.android`,
  `~/.happy`, etc. Default `~/Library` scans miss these entirely.
- **pnpm hardlinks**: deleted node_modules frees less than `du` reports. Promise the `df`
  delta, not the `du` sum.
- **Git worktrees are silent disk hogs** in monorepos. Always enumerate before recommending.
- **CoreSimulator has TWO locations** — devices (`~/Library/...`) and runtime volumes
  (`/Library/Developer/CoreSimulator/Volumes`, separate APFS partitions).
- **Sim runtime volumes** show up as separate filesystems in `df -h` — easy to miss.
- **Disk space can go DOWN during cleanup** because macOS does background writes
  (Spotlight reindex, etc.). Don't panic — just keep going.
- **CocoaPods cache regrows fast** when iOS devs use it — don't promise it stays gone.
- **OS update snapshots** sometimes hold deleted file space; reboot often helps APFS reclaim.
- Some caches regenerate (npm, Chrome, uv, Gradle) — note this to user so they're not surprised
  when the next build is slow.
