#!/bin/sh
# Send a script to the running Blender and print its output
f=$1; n=$(basename "$f" .py)_$(date +%s%N)
d=$(dirname "$0")/bridge
rm -f "$d/outbox/$n.log"; cp "$f" "$d/inbox/$n.py"
i=0; while [ ! -f "$d/outbox/$n.log" ] && [ $i -lt 600 ]; do sleep 0.2; i=$((i+1)); done
cat "$d/outbox/$n.log" 2>/dev/null || echo "TIMEOUT"
