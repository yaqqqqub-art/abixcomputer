# Security (V1 state)

Implemented in configuration (not yet verified by the author, see tests/smoke.sh):
- Only Nginx publishes ports. VNC (5901) listens on localhost inside the container; noVNC (6080) is reachable only on the internal Docker network.
- Everything is behind HTTPS and HTTP basic auth (one admin account). Real multi-user auth is V4.
- Nginx rate limiting, security headers, `server_tokens off`, read-only Nginx filesystem.
- Desktop container: non-root user, memory/CPU/PID limits, `no-new-privileges`, all capabilities dropped except a minimal set.
- Secrets are generated locally into `.env` and `deployment/`, which are git-ignored. No secrets are in the image or source.
- The Docker socket is never mounted into any container.

Known V1 limits:
- One shared desktop and one login. No per-user isolation yet (V4).
- VNC password uses only 8 characters (protocol limit); it is protected by the HTTPS+login layer in front of it.
- No audit logs, no brute-force lockout beyond Nginx rate limits, no clipboard control yet.
- The desktop has outbound internet access; network restrictions come in V7.

## Stage 1 additions
- No new capabilities, no new ports, no sudo, no privileged mode, no Docker socket.
- `abix-ctl` runs as user `abix` only. It never uses a shell; accent colour is checked against `#RRGGBB` (stops CSS injection), wallpaper files must be images up to 30 MB inside Pictures/Downloads/Abix folder (symlinks are resolved first).
- Optional Fluent theme is downloaded from GitHub during the image build (supply-chain risk: unpinned `main` branch; set `ABIX_FLUENT=0` to disable).
- NOT protected: anything running as `abix` can change its own desktop settings; the lock screen is not implemented yet (Stage 2).

## Stage 2 additions
- HTTP basic auth is replaced by a web login: PBKDF2-SHA256 hash (200k rounds) in `.env`, HttpOnly + Secure + SameSite=Strict cookie, server-side sessions with idle (8 h) and absolute (24 h) expiry, logout really ends the session.
- Brute force: 5 failed attempts per address per 5 min (API) and 5 login calls/min (Nginx). Every state-changing call needs `X-Abix: 1` + JSON (CSRF defence on top of SameSite).
- `/desktop/*` is gated by Nginx `auth_request`; locked sessions get 403 and open VNC connections are cut.
- Secrets (hash, session secret, VNC password) live in `/etc/abix/backend.json` (root, mode 600) and are removed from the environment; the desktop user cannot read them (checked by smoke test).
- Settings input is whitelisted; no shell is ever used; wallpaper ids map to files in two fixed folders (path traversal tested).
- Strict Content-Security-Policy on the web app; no external scripts or fonts.
- Audit lines (login ok/failed, lock, unlock, settings, power) go to the container log: `docker logs abix-desktop | grep abix-api`. No passwords are logged.
- Still open: single account, no 2FA, no idle auto-lock, sessions lost on container restart, API runs as root inside the container, VNC password appears in the (unlogged) viewer URL.
