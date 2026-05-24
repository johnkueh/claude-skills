---
name: system-memory-cleanup
description: Monitor and clean up system resources on macOS. Use when the user wants to check CPU/memory usage, find resource hogs, kill orphaned processes, or free up system resources. Triggers on requests like "what's using CPU", "memory hogs", "clean up processes", "kill Chrome", "system slow", or "activity monitor".
---

# System Cleanup

Monitor system resources and clean up wasteful processes on macOS.

## Quick Commands

### Show top processes
```bash
bash scripts/top-processes.sh
```

### Find orphaned claude CLI processes
```bash
bash scripts/find-orphan-claude.sh
```

### Kill orphaned claude CLI processes (preserves active ghostty sessions)
```bash
bash scripts/kill-orphan-claude.sh
```

## Manual Commands

### Top CPU consumers
```bash
ps -arcwwwxo "pid %cpu %mem rss command" | head -20
```

### Top memory consumers
```bash
ps -amcwwwxo "pid %cpu %mem rss command" | head -20
```

### Total memory usage
```bash
ps -axo rss= | awk '{sum+=$1} END {printf "%.1f GB\n", sum/1024/1024}'
```

### Kill all processes by name
```bash
pkill -f "Google Chrome"
pkill -f "chrome-headless-shell"
```

### Force kill (if regular kill doesn't work)
```bash
pkill -9 -f "Process Name"
```

## Common Cleanup Targets

| Process | What it is | Safe to kill? |
|---------|-----------|---------------|
| claude | Claude CLI sessions | Yes, if orphaned |
| chrome-headless-shell | Headless Chrome (MCP) | Yes |
| Google Chrome | Browser | Yes |
| node | Node.js processes | Check what's using it |
| Electron apps | Various apps | Depends on app |

## Workflow

1. Run `bash scripts/top-processes.sh` to see what's consuming resources
2. Identify targets (orphaned processes, unused apps)
3. Kill specific processes with `pkill -f "name"` or use the cleanup scripts
4. Verify cleanup with another top-processes check

## Notes

- Claude CLI processes become orphaned when terminal tabs are closed without exiting claude first
- Always use `/exit` or Ctrl+C before closing terminal tabs
- WindowServer, launchd, and kernel_task are essential system processes - never kill them
