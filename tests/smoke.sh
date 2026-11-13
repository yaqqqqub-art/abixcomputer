#!/usr/bin/env bash
# Smoke test (V1 checks + Stage 1 desktop checks). Run after `docker compose up -d --build` from the project root:
#   bash tests/smoke.sh
# Needs: docker, curl. Reads the login from deployment/first-login.txt.
cd "$(dirname "$0")/.."
PASS=0; FAIL=0
ok()   { echo "PASS  $1"; PASS=$((PASS+1)); }
bad()  { echo "FAIL  $1"; FAIL=$((FAIL+1)); }
check() { if eval "$2" >/dev/null 2>&1; then ok "$1"; else bad "$1"; fi; }

PW="${ABIX_TEST_PASSWORD:-$(grep -E '^[[:space:]]*password:' deployment/first-login.txt 2>/dev/null | awk '{print $2}')}"   # set ABIX_TEST_PASSWORD if you removed first-login.txt
BASE="${BASE:-https://localhost}"
USR="${ABIX_TEST_USER:-$(grep -E '^ABIX_ADMIN_USER=' .env 2>/dev/null | tail -1 | cut -d= -f2-)}"; USR="${USR:-admin}"

check "desktop container is running"          "[ \"\$(docker inspect -f '{{.State.Running}}' abix-desktop)\" = true ]"
check "nginx container is running"            "[ \"\$(docker inspect -f '{{.State.Running}}' abix-nginx)\" = true ]"
check "VNC/noVNC ports are NOT published"     "[ -z \"\$(docker port abix-desktop)\" ]"
check "memory limit is set"                   "[ \"\$(docker inspect -f '{{.HostConfig.Memory}}' abix-desktop)\" -gt 0 ]"
check "CPU limit is set"                      "[ \"\$(docker inspect -f '{{.HostConfig.NanoCpus}}' abix-desktop)\" -gt 0 ]"
check "no-new-privileges is on"               "docker inspect -f '{{.HostConfig.SecurityOpt}}' abix-desktop | grep -q no-new-privileges"
check "Xtigervnc is running as user abix"     "docker exec abix-desktop pgrep -u abix Xtigervnc"
check "Xfce session is running"               "docker exec abix-desktop pgrep -u abix xfce4-session"
check "noVNC bridge is running"               "docker exec abix-desktop pgrep -u abix websockify"
check "desktop user is not root"              "[ \"\$(docker exec -u abix abix-desktop id -u)\" != 0 ]"
check "HTTP redirects to HTTPS"               "curl -s -o /dev/null -w '%{http_code}' http://localhost/ | grep -q 301"

# Persistence: a file in the home volume must survive a container restart
docker exec -u abix abix-desktop bash -c 'echo persist-ok > /home/abix/Workspace/.smoke' >/dev/null 2>&1
docker restart abix-desktop >/dev/null 2>&1; sleep 8
check "workspace file survives restart"       "docker exec -u abix abix-desktop grep -q persist-ok /home/abix/Workspace/.smoke"
docker exec -u abix abix-desktop rm -f /home/abix/Workspace/.smoke >/dev/null 2>&1

# ---------------- Stage 1: Windows-style desktop ----------------
# After the restart above Xfce needs a little time; wait until the panel is up (max 60 s).
for i in $(seq 1 30); do docker exec abix-desktop pgrep -u abix xfce4-panel >/dev/null 2>&1 && break; sleep 2; done
sleep 6   # let abix-session-init apply the saved settings
CTL="docker exec -u abix abix-desktop /usr/local/bin/abix-ctl"
check "S1 abix-ctl is installed"               "$CTL status | python3 -c 'import json,sys; json.load(sys.stdin)'"
check "S1 panel (taskbar) is running"          "docker exec abix-desktop pgrep -u abix xfce4-panel"
check "S1 window manager is running"           "docker exec abix-desktop pgrep -u abix xfwm4"
check "S1 desktop (icons) is running"          "docker exec abix-desktop pgrep -u abix xfdesktop"
check "S1 panel config was seeded"             "docker exec -u abix abix-desktop grep -q position-locked /home/abix/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-panel.xml"
check "S1 six or more wallpapers installed"    "[ \"\$(docker exec abix-desktop sh -c 'ls /usr/share/backgrounds/abix | wc -l')\" -ge 6 ]"
check "S1 desktop icons exist (3 or more)"     "[ \"\$(docker exec abix-desktop sh -c 'ls /home/abix/Desktop/*.desktop | wc -l')\" -ge 3 ]"
echo "INFO  start menu in use: $(docker exec -u abix abix-desktop grep -Eo 'whiskermenu|applicationsmenu' /home/abix/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-panel.xml | sort -u | tr '\n' ' ')"
check "S1 Start menu plugin or fallback chosen" "docker exec -u abix abix-desktop grep -Eq 'whiskermenu|applicationsmenu' /home/abix/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-panel.xml"
check "S1 GTK theme is set in the live session" "$CTL get-theme | grep -q ."
check "S1 non-root: abix has no sudo"          "! docker exec -u abix abix-desktop sudo -n true"
check "S1 dark mode switch works"              "$CTL theme dark | grep -q '\"ok\": true'"
check "S1 light mode switch works"             "$CTL theme light | grep -q '\"ok\": true'"
check "S1 animation Off works"                 "$CTL anim off | grep -q '\"effective\": \"off\"'"
check "S1 animation Light active (picom or xfwm4)" "$CTL anim light | grep -Eq 'picom-light|xfwm4-compositor'"
check "S1 animation Full active (any real mode)"   "$CTL anim full | grep -Eq 'picom-full|picom-light|xfwm4-compositor'"
check "S1 picom really running when picom-*"   "docker exec abix-desktop sh -c 'pgrep -u abix picom || grep -q xfwm4-compositor /home/abix/.config/abix/state.json'"
check "S1 wallpaper change works"              "$CTL wallpaper /usr/share/backgrounds/abix/abix-ocean.jpg | grep -q ocean"
check "S1 wallpaper outside allowed folders is refused" "! $CTL wallpaper /etc/passwd"
$CTL anim light >/dev/null 2>&1; $CTL wallpaper /usr/share/backgrounds/abix/abix-bloom-light.jpg >/dev/null 2>&1
check "docker-compose refuses missing bind files (no silent directory)" "grep -q 'create_host_path: false' docker-compose.yml"


# ---------------- Stage 2: web login, lock, settings API ----------------
# (the restart above ended every web session, so log in now; Nginx allows 5 login calls per minute - do not rerun this twice in 60 s)
JAR="$(mktemp)"; trap 'rm -f "$JAR"' EXIT
api() { curl -ks -b "$JAR" -c "$JAR" -H 'X-Abix: 1' -H 'Content-Type: application/json' "$@"; }
code() { curl -ks -o /dev/null -w '%{http_code}' "$@"; }
for i in $(seq 1 20); do [ "$(code $BASE/api/health)" = 200 ] && break; sleep 2; done
check "S2 login page is served at /"                  "curl -ks $BASE/ | grep -q 'ABIX Cloud Computer'"
check "S2 API health answers through Nginx"           "[ \"\$(code $BASE/api/health)\" = 200 ]"
check "S2 desktop is refused without login (401)"     "[ \"\$(code $BASE/desktop/vnc.html)\" = 401 ]"
check "S2 settings API is refused without login (401)" "[ \"\$(code $BASE/api/settings)\" = 401 ]"
check "S2 wrong password is refused (401)"            "[ \"\$(code -X POST -H 'X-Abix: 1' -H 'Content-Type: application/json' -d '{\"username\":\"admin\",\"password\":\"wrong-password\"}' $BASE/api/login)\" = 401 ]"
check "S2 login without the X-Abix header is refused" "[ \"\$(code -X POST -H 'Content-Type: application/json' -d '{}' $BASE/api/login)\" = 400 ]"
check "S2 login with the right password works"        "api -X POST -d '{\"username\":\"$USR\",\"password\":\"$PW\"}' $BASE/api/login | grep -q '\"ok\": true'"
check "S2 cookie is HttpOnly+Secure+SameSite"         "grep -q '#HttpOnly_' $JAR && grep -q 'abix_session' $JAR"
check "S2 desktop is served after login (200)"        "[ \"\$(code -b $JAR $BASE/desktop/vnc.html)\" = 200 ]"
check "S2 desktop VNC websocket path is reachable"    "[ \"\$(code -b $JAR -H 'Connection: Upgrade' -H 'Upgrade: websocket' -H 'Sec-WebSocket-Version: 13' -H 'Sec-WebSocket-Key: c21va2U=' $BASE/desktop/websockify)\" != 401 ]"
check "S2 API process runs as root, desktop user cannot read its secrets" "docker exec abix-desktop pgrep -u root -f abix_api && ! docker exec -u abix abix-desktop cat /etc/abix/backend.json"
no_secret_env() {  # look at the real desktop processes (children of supervisord), NOT the docker-exec shell, which always receives the container env
  docker exec -u abix abix-desktop bash -c 'n=0; for p in $(pgrep -u abix "xfce4-session|xfce4-panel|xfwm4|Xtigervnc|websockify"); do tr "\\0" "\\n" < /proc/$p/environ 2>/dev/null | grep -qE "^(ABIX_SECRET|ABIX_ADMIN_HASH|VNC_PASSWORD)=" && n=$((n+1)); done; exit $n'
}
check "S2 secrets are not in the desktop user's environment" "no_secret_env"
check "S2 settings API reports the real state"        "api $BASE/api/settings | grep -q '\"available\": true'"
echo "INFO  settings API: $(api $BASE/api/settings)"
check "S2 settings: dark mode via API"                "api -X POST -d '{\"theme\":\"dark\"}' $BASE/api/settings | grep -q '\"ok\": true' && api $BASE/api/settings | grep -q '\"theme\": \"dark\"'"
check "S2 settings: light mode via API"               "api -X POST -d '{\"theme\":\"light\"}' $BASE/api/settings | grep -q '\"ok\": true'"
check "S2 settings: bad accent refused (400)"         "[ \"\$(code -b $JAR -X POST -H 'X-Abix: 1' -H 'Content-Type: application/json' -d '{\"accent\":\"red;ls\"}' $BASE/api/settings)\" = 400 ]"
check "S2 wallpapers list has 6 or more"              "[ \"\$(api $BASE/api/wallpapers | grep -o 'sys-' | wc -l)\" -ge 6 ]"
check "S2 lock works"                                 "api -X POST -d '{}' $BASE/api/lock | grep -q '\"locked\": true'"
check "S2 desktop is refused while locked (403)"      "[ \"\$(code -b $JAR $BASE/desktop/vnc.html)\" = 403 ]"
check "S2 settings are refused while locked (403)"    "[ \"\$(code -b $JAR $BASE/api/settings)\" = 403 ]"
check "S2 wrong password does not unlock (401)"       "[ \"\$(code -b $JAR -X POST -H 'X-Abix: 1' -H 'Content-Type: application/json' -d '{\"password\":\"wrong-password\"}' $BASE/api/unlock)\" = 401 ]"
check "S2 right password unlocks"                     "api -X POST -d '{\"password\":\"$PW\"}' $BASE/api/unlock | grep -q '\"locked\": false'"
up_after_unlock() { for i in $(seq 1 15); do [ "$(code -b $JAR $BASE/desktop/vnc.html)" = 200 ] && return 0; sleep 1; done; return 1; }   # lock restarts websockify; give it a moment
check "S2 desktop works again after unlock (200)"     "up_after_unlock"
check "S2 logout ends the session (401 afterwards)"   "api -X POST -d '{}' $BASE/api/logout >/dev/null; [ \"\$(code -b $JAR $BASE/api/settings)\" = 401 ]"

# ---------------- Stage 4: dev tools, clipboard bridge, new frontend files ----------------
U="docker exec -u abix abix-desktop bash -lc"
check "S4 Java (java + javac) works"                 "$U 'java -version && javac -version'"
check "S4 Python 3 + pip + venv work"                "$U 'python3 --version && pip3 --version && python3 -m venv /tmp/abix-venv-test && rm -rf /tmp/abix-venv-test'"
check "S4 pip install works for the desktop user"    "$U 'pip3 install --quiet --user six && python3 -c \"import six\"'"
check "S4 Node.js + npm work"                        "$U 'node --version && npm --version'"
check "S4 npm install -g works without root"         "$U 'npm install -g --silent is-odd && test -d ~/.npm-global/lib/node_modules/is-odd'"
check "S4 abix-versions prints all tools"            "$U abix-versions | grep -q Node"
check "S4 clipboard bridge (vncconfig) is running"   "docker exec abix-desktop pgrep -u abix vncconfig"
check "S4 pointer.js / extras.js / cursor.svg served" "for f in pointer.js extras.js cursor.svg; do [ \"\$(code $BASE/\$f)\" = 200 ] || exit 1; done"

# ---------------- Stage 5: Chrome, App Center, smoothness ----------------
check "S5 Chrome binary is installed (amd64 only)"    "[ \"\$(docker exec abix-desktop dpkg --print-architecture)\" != amd64 ] || docker exec abix-desktop test -x /opt/google/chrome/chrome"
check "S5 Chrome starts and shows a window"           "[ \"\$(docker exec abix-desktop dpkg --print-architecture)\" != amd64 ] || { docker exec -d -u abix -e DISPLAY=:1 abix-desktop /usr/local/bin/abix-chrome about:blank; for i in \$(seq 1 20); do docker exec -u abix -e DISPLAY=:1 abix-desktop xdotool search --class chrome >/dev/null 2>&1 || docker exec -u abix -e DISPLAY=:1 abix-desktop sh -c 'wmctrl -l 2>/dev/null | grep -qi chrome || xwininfo -root -tree | grep -qi chrome'; [ \$? = 0 ] && exit 0; sleep 1; done; exit 1; }"
check "S5 Start-menu Chrome entry uses --no-sandbox launcher" "[ \"\$(docker exec abix-desktop dpkg --print-architecture)\" != amd64 ] || docker exec abix-desktop grep -q abix-chrome /usr/share/applications/google-chrome.desktop"
check "S5 App Center API refuses anonymous users"     "[ \"\$(code $BASE/api/apps)\" = 401 ]"
check "S5 App Center catalog is installed"            "docker exec abix-desktop python3 -c 'import json; print(len(json.load(open(\"/usr/local/share/abix/apps-catalog.json\"))[\"apps\"]))'"
check "S5 Wine is available for Windows setup files"  "docker exec abix-desktop sh -c 'command -v wine'"
check "S5 desktop can reach the internet (apt/downloads)" "docker exec abix-desktop sh -c 'wget -q --spider --timeout=15 https://dl.google.com/ || curl -sI --max-time 15 https://deb.debian.org >/dev/null'"
check "S5 VNC runs with the speed options"            "docker exec abix-desktop sh -c 'tr \"\\\\0\" \" \" < /proc/\$(pgrep -u abix -x Xtigervnc | head -1)/cmdline' | grep -q FrameRate"
check "S5 abix-smooth command exists"                 "docker exec -u abix abix-desktop abix-smooth status"
check "S5 apps.js is served"                          "[ \"\$(code $BASE/apps.js)\" = 200 ]"

echo "INFO  animation really active: $($CTL status | python3 -c 'import json,sys; print(json.load(sys.stdin)["active"].get("animation"))')"
echo; echo "Passed: $PASS  Failed: $FAIL"
[ "$FAIL" -eq 0 ]
