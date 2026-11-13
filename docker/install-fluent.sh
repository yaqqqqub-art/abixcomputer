#!/bin/bash
# OPTIONAL, best effort: Fluent GTK theme (MIT, vinceliuice/Fluent-gtk-theme) for a more Windows-11-like look.
# Needs internet during `docker compose build`. If anything fails we keep going: abix-ctl falls back to Arc.
# Switch off with the build arg ABIX_FLUENT=0.
set -u
[ "${ABIX_FLUENT:-1}" = "1" ] || { echo "Fluent theme disabled (ABIX_FLUENT=0)"; exit 0; }
T="$(mktemp -d)"
if git clone --depth 1 https://github.com/vinceliuice/Fluent-gtk-theme.git "$T/f" >/dev/null 2>&1; then
  ( cd "$T/f" && ./install.sh -d /usr/share/themes -c light -c dark --tweaks round >/dev/null 2>&1 ) \
    && echo "Fluent theme installed" || echo "Fluent install.sh failed - using Arc"
else
  echo "Fluent clone failed (no network?) - using Arc"
fi
rm -rf "$T"
ls /usr/share/themes | grep -i fluent || true
exit 0
