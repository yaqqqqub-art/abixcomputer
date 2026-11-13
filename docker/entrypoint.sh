#!/bin/bash
set -euo pipefail

: "${VNC_PASSWORD:?VNC_PASSWORD is not set}"
: "${DESKTOP_GEOMETRY:=1280x800}"

# Runtime is UID 1000 (abix). The backend config is private to this container user;
# no chown, sudo, setuid, or privilege escalation is needed at startup.
if [ -n "${ABIX_INIT_PASSWORD:-}" ]; then
  [ "${#ABIX_INIT_PASSWORD}" -ge 10 ] || { echo "ABIX_INIT_PASSWORD must be at least 10 characters" >&2; exit 1; }
  ABIX_ADMIN_HASH="$(ABIX_PW="$ABIX_INIT_PASSWORD" python3 - <<'PY'
import hashlib, os, secrets
password = os.environ["ABIX_PW"]
salt = secrets.token_hex(16)
digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200000).hex()
print("pbkdf2:200000:%s:%s" % (salt, digest))
PY
)"
  unset ABIX_INIT_PASSWORD ABIX_PW
fi
: "${ABIX_ADMIN_HASH:?ABIX_ADMIN_HASH is not set - set ABIX_INIT_PASSWORD in the app environment or run deployment/init.sh}"
# Fail early instead of silently accepting a plain-text or malformed hash.
ABIX_ADMIN_HASH="$ABIX_ADMIN_HASH" python3 - <<'PY'
import os, re, sys
value = os.environ["ABIX_ADMIN_HASH"]
if not re.fullmatch(r"pbkdf2:[1-9][0-9]*:[0-9a-f]{32}:[0-9a-f]{64}", value):
    print("ABIX_ADMIN_HASH is invalid. Set ABIX_INIT_PASSWORD in Blitz Environment (10+ characters) and redeploy.", file=sys.stderr)
    sys.exit(1)
PY

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
: "${ABIX_ADMIN_USER:=abixone}"
echo "[abix] Login username configured: $ABIX_ADMIN_USER"

mkdir -p /home/abix/.config/abix /home/abix/.runtime /home/abix/.vnc /home/abix/Workspace
mkdir -p /home/abix/Desktop /home/abix/Downloads /home/abix/Documents /home/abix/Pictures
mkdir -p /etc/abix
chmod 700 /home/abix/.config/abix /home/abix/.runtime

# One canonical path shared by entrypoint, Supervisor and API.
ABIX_BACKEND_CONF=/etc/abix/backend.json
export ABIX_BACKEND_CONF

mkdir -p /tmp/nginx-client-body /tmp/nginx-proxy /tmp/nginx-fastcgi /tmp/nginx-uwsgi /tmp/nginx-scgi
python3 /usr/local/bin/vncpw.py > /home/abix/.vnc/passwd
chmod 600 /home/abix/.vnc/passwd

# Write the configuration to the canonical location before starting any services.
( umask 077; python3 - <<'PY'
import json, os
path = "/etc/abix/backend.json"
with open(path, "w") as f:
    json.dump({"user": os.environ["ABIX_ADMIN_USER"], "hash": os.environ["ABIX_ADMIN_HASH"],
               "secret": os.environ["ABIX_SECRET"], "vnc_password": os.environ["VNC_PASSWORD"]}, f)
PY
)
chmod 600 /etc/abix/backend.json
# Keep a copy for any older component that still reads the home-directory location.
cp /etc/abix/backend.json /home/abix/.config/abix/backend.json
chmod 600 /home/abix/.config/abix/backend.json
echo "[abix] Backend config created at /etc/abix/backend.json"
unset VNC_PASSWORD ABIX_ADMIN_HASH ABIX_SECRET ABIX_ADMIN_USER

export DESKTOP_GEOMETRY
exec "$@"
