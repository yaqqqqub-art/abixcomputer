# Stage 2 - web login, dashboard, lock screen, Settings, power

## What is tested and what is not
| Item | Status |
|---|---|
| Backend API (login, cookie flags, forged cookie, throttle, CSRF header, lock/unlock, settings validation, wallpapers, power, logout, expiry, size limit) | **Tested**: `python3 tests/unit/test_backend.py` (9 tests, real HTTP, fake `abix-ctl`) and a live curl run |
| `init.sh` on a fresh folder, on a broken `.env` (CRLF, missing VNC_PASSWORD), reuse of the Stage 1 password | **Tested** in a temp copy |
| Syntax: all bash, Python, JS, compose YAML | **Tested** |
| Frontend JS start-up with a fake DOM (unauthenticated -> login view), every element id used by the JS exists | **Tested** (static) |
| Frontend in a real browser (layout, touch, lock screen look, noVNC inside the frame) | **NOT tested** - no browser/Docker in the authoring sandbox |
| `nginx.conf` (`auth_request`, websocket pass-through), Docker image build, supervisord starting the API, privilege drop to user `abix`, `pkill` from the API | **NOT tested** - `tests/smoke.sh` now has 24 Stage 2 checks that test exactly these on your machine |
| Whisker menu | Cause found: the apt package is named `xfce4-whiskermenu-plugin` (Stage 1 used `xfce4-whisker-menu-plugin`, which does not exist, so it was skipped and the source build had to carry it). Now installed from apt first. **Not yet confirmed by a real build** |

## How it works
    Browser --HTTPS--> Nginx --/               static login/dashboard (frontend/)
                             |--/api/*         -> API inside the desktop container (port 8080, internal only)
                             '--/desktop/*     -> noVNC, only after the API says "logged in and not locked" (auth_request)
- **Login**: username + password (PBKDF2-SHA256, 200 000 rounds, hash in `.env`). Signed HttpOnly/Secure/SameSite=Strict cookie; the session itself lives in the API's memory. Idle timeout `ABIX_SESSION_HOURS` (default 8), hard limit 24 h. 5 wrong passwords per 5 min per address are blocked (plus Nginx 5/min on `/api/login`).
- **Lock**: sets the session to locked. Nginx then refuses `/desktop/` (403), the VNC password is no longer handed out, settings/power are refused, and open noVNC connections are cut. Your apps keep running. Unlock needs the password. Lock state survives a page reload.
- **Settings**: Mode, Animation, Accent, Wallpaper. Every value is checked against a fixed list; the API runs `abix-ctl` (Stage 1) as user `abix`, as an argument list, never a shell. "Really active" animation and Start-menu type are read back from the desktop, not assumed.
- **Power**: Restart desktop session, Restart whole desktop (screen server + session), Sign out. Shutting down the container is deliberately not offered (that needs the Docker socket, which is never mounted).
- **Touch**: viewport meta, 44 px tap targets, bar can be hidden, noVNC's own touch gestures (tap = click, drag = move, two fingers = scroll) and its keyboard button are used.

## Honest limits
- The lock protects **browser access**. It is not an in-desktop screen lock (someone who already has the VNC password and network access to port 6080 would bypass it, but that port exists only on the internal Docker network).
- Sessions are in memory: restarting the desktop container signs everyone out.
- One admin account (multi-user = Stage 4). No 2FA yet.
- The viewer URL contains the VNC password (only for a logged-in, unlocked session). Nginx does not log `/desktop/` requests for that reason.
- The API is root inside the container (needed to hide secrets from user `abix`). It has no network exposure outside Nginx, and the container has `cap_drop: ALL` + a small allow-list.
- No auto-lock after idle time yet.

## Upgrading from Stage 1 (your files are kept)
    cd abix-cloud-computer
    bash deployment/init.sh localhost        # repairs .env, adds the login hash; reuses your old password
    docker compose up -d --build             # NEVER use: docker compose down -v
    bash tests/smoke.sh
Then open https://localhost/ and sign in with the user/password from `deployment/first-login.txt`.
Change password: `bash deployment/set-password.sh` then `docker compose up -d`.

## Rollback
Restore the Stage 1 zip, run `docker compose up -d --build`. The `abix-home` volume is untouched by Stage 2. (Stage 1 needs its old `deployment/htpasswd`; Stage 2 does not delete it.)
