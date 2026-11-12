#!/usr/bin/env bash
# SessionStart hook (matcher "compact"): after a compaction, print the framing of each
# design-loop run this session is working on, so the run stays on goal.
#
# A run belongs to this session when its design/<run>/cost-log.tsv lists the session id
# (cost.py mark links a session to a run). Runs whose **Status:** is Closed are skipped.
# Prints nothing when the session has no open run in its repo.
set -uo pipefail

read -r sid cwd < <(python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except ValueError:
    d = {}
print(d.get("session_id") or "-", d.get("cwd") or "-")' 2>/dev/null)
[ "${sid:--}" != "-" ] || exit 0
[ "${cwd:--}" != "-" ] || cwd=$PWD
root=$(git -C "$cwd" rev-parse --show-toplevel 2>/dev/null) || exit 0

for log in "$root"/design/*/cost-log.tsv; do
  [ -f "$log" ] || continue
  grep -qF "$sid" "$log" || continue
  f="$(dirname "$log")/framing.md"
  [ -f "$f" ] || continue
  grep -qiE '^\**Status:?\**:?[[:space:]]*Closed\b' "$f" && continue
  echo "=== Design-loop run for this session: ${f#"$root"/} (re-surfaced after compaction) ==="
  cat "$f"
  echo "=== End of framing. It bounds the run: re-read it, and the run's decisions.md, before the next step. ==="
done
