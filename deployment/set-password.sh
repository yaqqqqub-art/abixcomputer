#!/usr/bin/env bash
# Change the web login password.  bash deployment/set-password.sh
# Then apply it:  docker compose up -d      (recreates the desktop container; your files are kept; everyone is signed out)
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] || { echo "Run deployment/init.sh first."; exit 1; }
if [ -n "${ABIX_NEW_PASSWORD:-}" ]; then        # non-interactive: ABIX_NEW_PASSWORD='...' bash deployment/set-password.sh
  P1="$ABIX_NEW_PASSWORD"; P2="$P1"
else
  read -rsp "New password (10+ characters): " P1; echo
  read -rsp "Repeat it: " P2; echo
fi
[ "$P1" = "$P2" ] || { echo "Passwords differ. Nothing changed."; exit 1; }
[ "${#P1}" -ge 10 ] || { echo "Too short (need 10+). Nothing changed."; exit 1; }
H="$(ABIX_PW="$P1" python3 -c 'import os,sys; sys.path.insert(0,"backend"); import abix_api; print(abix_api.make_hash(os.environ["ABIX_PW"]))')"
sed -i "s|^ABIX_ADMIN_HASH=.*|ABIX_ADMIN_HASH=${H}|" .env
rm -f deployment/first-login.txt          # it no longer matches
echo "Saved. Now run:  docker compose up -d"
