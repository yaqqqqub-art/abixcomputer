#!/bin/bash
set -euo pipefail

: "${VNC_PASSWORD:?VNC_PASSWORD is not set}"
: "${DESKTOP_GEOMETRY:=1280x800}"
: "${ABIX_ADMIN_HASH:?ABIX_ADMIN_HASH is not set - run deployment/init.sh}"
# Generate the internal session secret on first boot and keep it in the persistent home volume.
# This lets managed hosts such as blitz.cloud start without a manually supplied ABIX_SECRET.
if [ -z "${ABIX_SECRET:-}" ]; then
  SECRET_FILE=/home/abix/.abix-secret
  if [ -s "$SECRET_FILE" ]; then
    ABIX_SECRET="$(cat "$SECRET_FILE")"
  else
    ABIX_SECRET="$(openssl rand -hex 32)"
    ( umask 077; printf '%s' "$ABIX_SECRET" > "$SECRET_FILE" )
  fi
fi
: "${ABIX_SECRET:?could not create ABIX_SECRET}"
: "${ABIX_ADMIN_USER:=admin}"

# Persistent home volume may be created root-owned; fix ownership once.
chown abix:abix /home/abix
mkdir -p /home/abix/.vnc /home/abix/Workspace
# VNC password file (VNC auth uses only the first 8 characters; the password is never written to the image).
# Ubuntu 24.04 has no vncpasswd binary in this image, so the password file is written by a small Python script (VNC_PASSWORD comes from the environment).
python3 /usr/local/bin/vncpw.py > /home/abix/.vnc/passwd
chmod 600 /home/abix/.vnc/passwd
chown -R abix:abix /home/abix/.vnc /home/abix/Workspace
# Desktop icons, panel and theme are now created by abix-ctl seed (run at session start as user abix).
mkdir -p /home/abix/Desktop /home/abix/Downloads /home/abix/Documents /home/abix/Pictures
chown abix:abix /home/abix/Desktop /home/abix/Downloads /home/abix/Documents /home/abix/Pictures
# Stage 2: secrets for the API go to a root-only file; they are then removed from the environment so desktop programs never see them.
mkdir -p /etc/abix
( umask 077; python3 - <<'PY'
import json, os
json.dump({"user": os.environ["ABIX_ADMIN_USER"], "hash": os.environ["ABIX_ADMIN_HASH"],
           "secret": os.environ["ABIX_SECRET"], "vnc_password": os.environ["VNC_PASSWORD"]},
          open("/etc/abix/backend.json", "w"))
PY
)
chown root:root /etc/abix/backend.json; chmod 600 /etc/abix/backend.json
unset VNC_PASSWORD ABIX_ADMIN_HASH ABIX_SECRET ABIX_ADMIN_USER

export DESKTOP_GEOMETRY
exec "$@"
