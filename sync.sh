#!/bin/bash
# Commit the ONE store (store/) + the ONE export (public/data.json) and push. Merge (not rebase) so files the engine
# has open (paper.db) are never rewritten; on conflicts keep ours (our export is rebuilt from the full store next tick).
cd "$(dirname "$0")"
git add -A store public 2>/dev/null; git commit -qm "${1:-session state} " >/dev/null 2>&1 || true
for i in 1 2 3; do
  git fetch -q origin main && git merge -q --no-edit -X ours origin/main >/dev/null 2>&1 && git push -q origin HEAD:main && exit 0
  sleep $((i*2))
done; exit 1
