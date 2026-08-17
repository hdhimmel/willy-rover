#!/bin/bash
set -e
cd /home/hhimmel/rover
git add -A
if ! git diff --cached --quiet; then
    git commit -m "Automated backup: $(date '+%Y-%m-%d %H:%M:%S %Z')"
    git push origin main
fi
