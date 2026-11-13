#!/usr/bin/env bash
# Creates / REPAIRS local secrets: .env, the web login (admin password hash), session secret and HTTPS certificate.
# Safe to run again at any time: it never changes a value that is already good.
#   bash deployment/init.sh [hostname]
set -euo pipefail
cd "$(dirname "$0")/.."
HOST="${1:-localhost}"

command -v openssl >/dev/null || { echo "openssl is required"; exit 1; }
command -v python3 >/dev/null || { echo "python3 is required on this machine (used once to hash the password)"; exit 1; }
rand() { openssl rand -base64 48 | tr -dc 'A-Za-z0-9' | head -c "$1"; }

[ -f .env ] || cp .env.example .env
sed -i 's/\r$//' .env                                   # Windows line endings break compose variables
[ -z "$(tail -c1 .env)" ] || echo >> .env               # make sure the file ends with a newline
getv() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- || true; }
setv() { if grep -q "^$1=" .env; then sed -i "s|^$1=.*|$1=$2|" .env; else echo "$1=$2" >> .env; fi; }

# 1) VNC password (internal only). Missing / empty / placeholder -> generate.
v="$(getv VNC_PASSWORD)"
if [ -z "$v" ] || [ "$v" = "change-me" ]; then setv VNC_PASSWORD "$(rand 8)"; echo "Repaired: VNC_PASSWORD was missing or a placeholder."; fi

# 2) Optional keys (never overwrite existing values)
for kv in DESKTOP_GEOMETRY=1280x800 DESKTOP_MEM_LIMIT=4g DESKTOP_CPUS=2.0 HTTP_PORT=80 HTTPS_PORT=443 \
          ABIX_DEFAULT_THEME=light ABIX_DEFAULT_ANIMATION=light ABIX_RESET_DESKTOP=0 ABIX_FLUENT=1 \
          ABIX_ADMIN_USER=admin ABIX_SESSION_HOURS=8; do
  [ -n "$(getv "${kv%%=*}")" ] || setv "${kv%%=*}" "${kv#*=}"
done

# 2b) Optional: choose the login name up front.   ABIX_ADMIN_USER=abix bash deployment/init.sh
if [ -n "${ABIX_ADMIN_USER:-}" ]; then setv ABIX_ADMIN_USER "$ABIX_ADMIN_USER"; echo "Login name set to: $ABIX_ADMIN_USER"; fi

# 3) Session secret (signs the login cookie)
[ -n "$(getv ABIX_SECRET)" ] || { setv ABIX_SECRET "$(openssl rand -hex 32)"; echo "Created: session secret."; }

# 4) Web login. If Stage 1 left a password in first-login.txt, KEEP using that same password.
if [ -z "$(getv ABIX_ADMIN_HASH)" ]; then
  PW="${ABIX_INIT_PASSWORD:-}"      # optional: ABIX_INIT_PASSWORD='...' bash deployment/init.sh  (never written to disk in clear text)
  if [ -z "$PW" ] && [ -f deployment/first-login.txt ]; then PW="$(grep -E '^[[:space:]]*password:' deployment/first-login.txt | head -1 | awk '{print $2}' || true)"; fi
  if [ -n "${ABIX_INIT_PASSWORD:-}" ]; then
    [ "${#PW}" -ge 10 ] || { echo "ABIX_INIT_PASSWORD is too short (need 10+). Nothing changed."; exit 1; }
    echo "Web login: using the password you supplied (only its hash is stored in .env)."
  elif [ -n "$PW" ]; then
    echo "Web login: reusing the password from deployment/first-login.txt (same as Stage 1)."
  else
    PW="$(rand 16)"
    printf 'Login for https://%s/\n  user: %s\n  password: %s\n' "$HOST" "$(getv ABIX_ADMIN_USER)" "$PW" > deployment/first-login.txt
    chmod 600 deployment/first-login.txt
    echo "Login saved to deployment/first-login.txt (delete it after you store the password)."
  fi
  setv ABIX_ADMIN_HASH "$(ABIX_PW="$PW" python3 -c 'import os,sys; sys.path.insert(0,"backend"); import abix_api; print(abix_api.make_hash(os.environ["ABIX_PW"]))')"
fi

# 5) Docker once created a DIRECTORY where a file must be? remove it if empty.
if [ -d deployment/nginx.conf ]; then
  if rmdir deployment/nginx.conf 2>/dev/null; then echo "Removed wrong empty directory deployment/nginx.conf."
  else echo "ERROR: deployment/nginx.conf is a non-empty directory; fix it by hand."; exit 1; fi
fi

# 6) HTTPS certificate
mkdir -p deployment/certs
if [ ! -f deployment/certs/fullchain.pem ]; then
  openssl req -x509 -nodes -newkey rsa:2048 -days 365 \
    -keyout deployment/certs/privkey.pem -out deployment/certs/fullchain.pem \
    -subj "/CN=${HOST}" -addext "subjectAltName=DNS:${HOST},DNS:localhost,IP:127.0.0.1" 2>/dev/null
  echo "Self-signed certificate created. For a real domain use Let's Encrypt (see documentation/DEPLOYMENT.md)."
fi

echo ".env keys now present (values hidden):"; sed 's/=.*/=<hidden>/' .env | tr '\n' ' '; echo
echo "Done. Next: docker compose up -d --build"
