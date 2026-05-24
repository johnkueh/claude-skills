#!/bin/bash
# Kill orphaned claude CLI processes, preserving active ghostty sessions

GHOSTTY_PID=$(pgrep -x ghostty 2>/dev/null)

if [ -z "$GHOSTTY_PID" ]; then
  echo "Ghostty not running. Refusing to kill all claude processes."
  echo "Use 'pkill -x claude' manually if you're sure."
  exit 1
fi

# Find active zsh shells under ghostty
ACTIVE_SHELLS=$(ps -eo pid,ppid,command | awk -v gpid="$GHOSTTY_PID" '
  $2==gpid {login_pids[$1]=1}
  /^[[:space:]]*[0-9]+[[:space:]]+[0-9]+[[:space:]]+-\/bin\/zsh/ {
    if($2 in login_pids || $2==gpid) print $1
  }
')

# Find claude processes that are children of active shells
ACTIVE_CLAUDE=""
for shell_pid in $ACTIVE_SHELLS; do
  claude_pid=$(ps -eo pid,ppid,command | awk -v ppid="$shell_pid" '$2==ppid && $3=="claude" {print $1}')
  if [ -n "$claude_pid" ]; then
    ACTIVE_CLAUDE="$ACTIVE_CLAUDE $claude_pid"
  fi
done

# Current session's claude
CURRENT_CLAUDE=$PPID

# Kill orphans
ALL_CLAUDE=$(pgrep -x claude)
KILLED=0

for pid in $ALL_CLAUDE; do
  is_active=false
  for active in $ACTIVE_CLAUDE $CURRENT_CLAUDE; do
    if [ "$pid" = "$active" ]; then
      is_active=true
      break
    fi
  done
  if [ "$is_active" = false ]; then
    kill "$pid" 2>/dev/null && echo "Killed $pid" && ((KILLED++))
  fi
done

echo ""
echo "Killed $KILLED orphaned claude processes."
echo "Preserved: $CURRENT_CLAUDE (current)$ACTIVE_CLAUDE"
