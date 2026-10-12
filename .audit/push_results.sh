#!/usr/bin/env bash
# usage: push_results.sh <src_dir> <dest_subdir_under_results/>
set -u
SRC="$(cd "$1" && pwd)"; DEST="$2"
WORK="$(mktemp -d)"
cd "$WORK"
git init -q
git config user.name "audit-bot"; git config user.email "audit-bot@users.noreply.github.com"
git config core.autocrlf false
git remote add origin "https://x-access-token:${GH_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"
for i in 1 2 3 4 5 6; do
  rm -rf ./* ./.git/index 2>/dev/null
  git fetch -q --depth 1 origin audit-results && git checkout -q -f -B r FETCH_HEAD || { sleep 5; continue; }
  mkdir -p "results/$DEST" && cp -R "$SRC/." "results/$DEST/"
  git add -A results && git commit -q -m "results: $DEST (run ${GITHUB_RUN_ID})" || true
  if git push -q origin HEAD:audit-results; then echo "pushed results/$DEST"; exit 0; fi
  sleep $(( (RANDOM % 10) + 3 ))
done
echo "push failed"; exit 1
