#!/bin/bash
# Find orphaned claude CLI processes not attached to active terminal sessions

echo "=== CLAUDE CLI PROCESSES ==="
echo ""

# Get ghostty's direct children (login processes -> zsh shells)
GHOSTTY_PID=$(pgrep -x ghostty 2>/dev/null)

if [ -z "$GHOSTTY_PID" ]; then
  echo "Ghostty not running. All claude CLI processes may be orphaned."
  echo ""
  pgrep -x claude
  exit 0
fi

# Find active zsh shells under ghostty
ACTIVE_SHELLS=$(ps -eo pid,ppid,command | awk -v gpid="$GHOSTTY_PID" '
  $2==gpid {login_pids[$1]=1}
  /^[[:space:]]*[0-9]+[[:space:]]+[0-9]+[[:space:]]+-\/bin\/zsh/ {
    if($2 in login_pids || $2==gpid) print $1
  }
')

# Find claude processes that are children of active shells
echo "Active ghostty shells: $ACTIVE_SHELLS"
echo ""

ACTIVE_CLAUDE=""
for shell_pid in $ACTIVE_SHELLS; do
  claude_pid=$(ps -eo pid,ppid,command | awk -v ppid="$shell_pid" '$2==ppid && $3=="claude" {print $1}')
  if [ -n "$claude_pid" ]; then
    ACTIVE_CLAUDE="$ACTIVE_CLAUDE $claude_pid"
  fi
done

echo "Active claude PIDs (in ghostty):$ACTIVE_CLAUDE"
echo ""

# Get current shell's parent (likely the claude process running this)
CURRENT_CLAUDE=$PPID

echo "Current session claude PID: $CURRENT_CLAUDE"
echo ""

# List all claude processes
ALL_CLAUDE=$(pgrep -x claude)
echo "All claude CLI PIDs:"
echo "$ALL_CLAUDE"
echo ""

# Identify orphans
echo "=== ORPHANED (safe to kill) ==="
for pid in $ALL_CLAUDE; do
  is_active=false
  for active in $ACTIVE_CLAUDE $CURRENT_CLAUDE; do
    if [ "$pid" = "$active" ]; then
      is_active=true
      break
    fi
  done
  if [ "$is_active" = false ]; then
    echo "$pid"
  fi
done
