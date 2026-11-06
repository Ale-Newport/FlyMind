#!/usr/bin/env bash
# Publish the tail of a CI log as a GitHub Actions error annotation.
# Annotations are readable through the public checks API without signing in, unlike
# job logs, so failures on public repositories can be diagnosed from anywhere.
set -euo pipefail
log="${1:?log file}"
title="${2:-failure}"
lines="${3:-60}"
if [ ! -f "$log" ]; then
  echo "::error title=$title::no log at $log (the step failed before producing output)"
  exit 0
fi
msg=$(tail -n "$lines" "$log" | sed -e 's/%/%25/g' -e 's/\r//g' -e 's/\x1b\[[0-9;]*m//g' \
  | awk 'BEGIN { ORS = "%0A" } { print }')
echo "::error title=$title::$msg"
