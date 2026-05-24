#!/bin/bash
# Show top processes by CPU and memory usage (macOS)

echo "=== TOP CPU CONSUMERS ==="
echo ""
printf "%-40s %8s %8s %10s %5s\n" "PROCESS" "CPU%" "MEM%" "RSS(MB)" "COUNT"
printf "%-40s %8s %8s %10s %5s\n" "-------" "----" "----" "-------" "-----"

ps -axo %cpu,%mem,rss,command | awk 'NR>1 {
  cmd=$4
  for(i=5;i<=NF;i++) cmd=cmd" "$i
  gsub(/.*\//, "", cmd)
  gsub(/ .*/, "", cmd)
  cpu[cmd]+=$1
  mem[cmd]+=$2
  rss[cmd]+=$3
  count[cmd]++
}
END {
  for(c in cpu) {
    if(cpu[c]>0.5 || mem[c]>0.5)
      printf "%-40s %8.1f %8.1f %10.0f %5d\n", substr(c,1,40), cpu[c], mem[c], rss[c]/1024, count[c]
  }
}' | sort -t' ' -k2 -rn | head -20

echo ""
echo "=== TOP MEMORY CONSUMERS ==="
echo ""
printf "%-40s %8s %8s %10s %5s\n" "PROCESS" "CPU%" "MEM%" "RSS(MB)" "COUNT"
printf "%-40s %8s %8s %10s %5s\n" "-------" "----" "----" "-------" "-----"

ps -axo %cpu,%mem,rss,command | awk 'NR>1 {
  cmd=$4
  for(i=5;i<=NF;i++) cmd=cmd" "$i
  gsub(/.*\//, "", cmd)
  gsub(/ .*/, "", cmd)
  cpu[cmd]+=$1
  mem[cmd]+=$2
  rss[cmd]+=$3
  count[cmd]++
}
END {
  for(c in cpu) {
    if(cpu[c]>0.5 || mem[c]>0.5)
      printf "%-40s %8.1f %8.1f %10.0f %5d\n", substr(c,1,40), cpu[c], mem[c], rss[c]/1024, count[c]
  }
}' | sort -t' ' -k3 -rn | head -20

echo ""
echo "=== TOTAL MEMORY ==="
ps -axo rss= | awk '{sum+=$1} END {printf "Total process memory: %.1f GB\n", sum/1024/1024}'

echo ""
echo "=== LONG TAIL ==="
ps -axo %mem,rss,command | awk 'NR>1 && $1<0.3 {sum+=$2; count++} END {printf "%d small processes (<0.3%% each): %.0f MB total\n", count, sum/1024}'
