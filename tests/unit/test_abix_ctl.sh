#!/usr/bin/env bash
# Logic test for docker/abix/abix-ctl using FAKE xfconf-query/picom/pgrep. Needs only bash + python3.
# It does NOT start a real desktop. It proves the decision logic (validation, fallback, files written).
#   bash tests/unit/test_abix_ctl.sh
cd "$(dirname "$0")/../.."
CTL="$PWD/docker/abix/abix-ctl"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
export ABIX_HOME="$T/home"; mkdir -p "$ABIX_HOME"
export DBUS_SESSION_BUS_ADDRESS=fake DISPLAY=:9
FAKE="$T/bin"; mkdir -p "$FAKE"; export FAKELOG="$T/xfconf.log" FAKEDIR="$T"
cat > "$FAKE/xfconf-query" <<'X'
#!/bin/bash
echo "$@" >> "$FAKELOG"; exit 0
X
cat > "$FAKE/xdpyinfo" <<'X'
#!/bin/bash
echo "number of extensions: 1"; echo "    Composite"
X
cat > "$FAKE/xfdesktop" <<'X'
#!/bin/bash
exit 0
X
cat > "$FAKE/pkill" <<'X'
#!/bin/bash
[ -f "$FAKEDIR/picom.pid" ] && kill "$(cat "$FAKEDIR/picom.pid")" 2>/dev/null; rm -f "$FAKEDIR/picom.pid"; exit 0
X
cat > "$FAKE/pgrep" <<'X'
#!/bin/bash
[ -f "$FAKEDIR/picom.pid" ] && kill -0 "$(cat "$FAKEDIR/picom.pid")" 2>/dev/null
X
cat > "$FAKE/picom-ok" <<'X'
#!/bin/bash
echo $$ > "$FAKEDIR/picom.pid"; exec sleep 60
X
cat > "$FAKE/picom-crash" <<'X'
#!/bin/bash
exit 1
X
chmod +x "$FAKE"/*
PASS=0; FAIL=0
t() { if eval "$2"; then echo "PASS  $1"; PASS=$((PASS+1)); else echo "FAIL  $1"; FAIL=$((FAIL+1)); fi; }
ctl() { PATH="$FAKE:$PATH" python3 -I "$CTL" "$@"; }
use_picom() { cp "$FAKE/$1" "$FAKE/picom"; }
rm -f "$FAKE/picom"

out="$(ctl seed)"
t "seed writes panel xml"            "[ -f $ABIX_HOME/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-panel.xml ]"
t "panel xml is well-formed"         "xmllint --noout $ABIX_HOME/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-panel.xml"
t "panel is at the bottom, locked"   "grep -q 'p=10' $ABIX_HOME/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-panel.xml && grep -q position-locked $ABIX_HOME/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-panel.xml"
t "settings.env + marker created"    "[ -f $ABIX_HOME/.config/abix/settings.env ] && [ -f $ABIX_HOME/.config/abix/profile-version ]"
t "user folders created"             "[ -d $ABIX_HOME/Downloads ] && [ -d $ABIX_HOME/Pictures/Wallpapers ]"
t "terminalrc written"               "grep -q ColorBackground $ABIX_HOME/.config/xfce4/terminal/terminalrc"
t "second seed is a no-op"           "ctl seed | grep -q '\"seeded\": false'"
t "seed --force backs up old config" "ctl seed --force | grep -q backup-"

t "anim off -> effective off"        "ctl anim off | grep -q '\"effective\": \"off\"'"
rm -f "$FAKE/picom"
t "no picom -> xfwm4 compositor fallback (honest)" "ctl anim light | grep -q xfwm4-compositor"
use_picom picom-crash
t "picom crashes -> fallback, not faked"          "ctl anim full | grep -q xfwm4-compositor"
use_picom picom-ok
t "picom works -> light"             "ctl anim light | grep -q 'picom-light'"
t "picom config has fading"          "grep -q 'fading = true' $ABIX_HOME/.config/abix/picom.conf"
t "picom works -> full"              "ctl anim full | grep -q 'picom-full'"
t "full config has shadows+corners"  "grep -q 'shadow = true' $ABIX_HOME/.config/abix/picom.conf && grep -q corner-radius $ABIX_HOME/.config/abix/picom.conf"
t "switching to off stops picom"     "ctl anim off >/dev/null; ! PATH=$FAKE:\$PATH pgrep -x picom"
t "bad level rejected"               "! ctl anim turbo 2>/dev/null"

t "theme dark saved"                 "ctl theme dark >/dev/null; grep -q THEME=dark $ABIX_HOME/.config/abix/settings.env"
t "theme sets GTK theme via xfconf"  "grep -q -- '/Net/ThemeName' $FAKELOG"
t "theme sets WM button layout"      "grep -q -- '|HMC' $FAKELOG"
t "theme light saved"                "ctl theme light >/dev/null; grep -q THEME=light $ABIX_HOME/.config/abix/settings.env"
t "gtk.css has accent"               "grep -q '#0067c0' $ABIX_HOME/.config/gtk-3.0/gtk.css"
t "accent accepted"                  "ctl accent '#ff8800' >/dev/null && grep -q '#ff8800' $ABIX_HOME/.config/gtk-3.0/gtk.css"
t "bad accent rejected (CSS inject)" "! ctl accent 'red;}x{' 2>/dev/null"
t "bad theme rejected"               "! ctl theme purple 2>/dev/null"

python3 - "$ABIX_HOME/Pictures/ok.png" <<'P'
import sys, struct, zlib
def chunk(t,d): c=struct.pack(">I",len(d))+t+d; return c+struct.pack(">I",zlib.crc32(t+d)&0xffffffff)
raw=b"\x00\xff\x00\x00"
open(sys.argv[1],"wb").write(b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",1,1,8,2,0,0,0))+chunk(b"IDAT",zlib.compress(raw))+chunk(b"IEND",b""))
P
echo "not an image" > "$ABIX_HOME/Pictures/evil.txt"
t "wallpaper in Pictures accepted"   "ctl wallpaper $ABIX_HOME/Pictures/ok.png >/dev/null"
t "wallpaper /etc/passwd refused"    "! ctl wallpaper /etc/passwd 2>/dev/null"
t "wallpaper non-image refused"      "! ctl wallpaper $ABIX_HOME/Pictures/evil.txt 2>/dev/null"
ln -s /etc/passwd "$ABIX_HOME/Pictures/link.png"
t "symlink escape refused"           "! ctl wallpaper $ABIX_HOME/Pictures/link.png 2>/dev/null"
t "wallpaper-add copies into folder" "ctl wallpaper-add $ABIX_HOME/Pictures/ok.png >/dev/null && [ -f $ABIX_HOME/Pictures/Wallpapers/ok.png ]"
t "status prints valid JSON"         "ctl status | python3 -c 'import json,sys; json.load(sys.stdin)'"
t "apply runs without crashing"      "ctl apply >/dev/null"
echo; echo "Passed: $PASS  Failed: $FAIL"; [ "$FAIL" -eq 0 ]
