#!/bin/bash
# Installs OPTIONAL packages one by one. A missing/unavailable package is skipped and logged, never fatal.
# Result list: /usr/share/abix/optional-packages.txt  (INSTALLED / SKIPPED per package)
set -u
export DEBIAN_FRONTEND=noninteractive
OUT=/usr/share/abix/optional-packages.txt
mkdir -p /usr/share/abix; touch "$OUT"
apt-get update >/dev/null 2>&1 || echo "apt-get update failed" >> "$OUT"
for pkg in "$@"; do
  cand="$(apt-cache policy "$pkg" 2>/dev/null | awk '/Candidate:/ {print $2}')"
  if [ -z "$cand" ] || [ "$cand" = "(none)" ]; then
    echo "SKIPPED  $pkg (no candidate in this image's repos)" >> "$OUT"; continue
  fi
  if apt-get install -y --no-install-recommends "$pkg" >/dev/null 2>&1; then
    echo "INSTALLED $pkg $cand" >> "$OUT"
  else
    echo "SKIPPED  $pkg (install failed)" >> "$OUT"
  fi
done
apt-get clean; rm -rf /var/lib/apt/lists/*
cat "$OUT"
exit 0
