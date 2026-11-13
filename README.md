# ABIX Cloud Computer

**YOUR COMPUTER. YOUR CLOUD. YOUR CONTROL.**

A real Ubuntu 24.04 desktop (Xfce) running in a Docker container, reachable from any browser through
noVNC behind Nginx with HTTPS and a login. This is **Stage 5 (see documentation/STAGE5.md: Chrome fix, App Center, smooth mode)**; Stage 4 is in documentation/STAGE4.md; stages below are kept for history. Stage 2 was: V1 infrastructure + Windows-style desktop (Stage 1) + web login, dashboard, lock screen and Settings (Stage 2)**.

> **Honest status:** the backend, `init.sh` and `abix-ctl` logic are tested (see `documentation/STAGE2.md`); the Docker build, Nginx config and
> the browser UI have **not** been run by the author (no Docker or browser in the build environment). Run `tests/smoke.sh` and send the result.

## Quick start
```bash
bash deployment/init.sh localhost
docker compose up -d --build
bash tests/smoke.sh
```
Then open https://localhost/ (accept the certificate warning). Sign in on the web page with the login in `deployment/first-login.txt`. Stage details: `documentation/STAGE2.md`.
Full instructions: `documentation/DEPLOYMENT.md`. Security notes: `documentation/SECURITY.md`.

## V1 contents
| Item | State |
|---|---|
| Ubuntu 24.04 + Xfce desktop in Docker | written, untested |
| noVNC desktop in the browser (mouse, keyboard, scroll, fullscreen via noVNC UI) | written, untested |
| Nginx HTTPS + login + rate limit | written, untested |
| Resource limits, non-root user, dropped capabilities | written, untested |
| Persistent home volume | written, untested (smoke test covers it) |

## Not built yet
Terminal and file manager (V3), accounts and per-user isolation (V4), applications and
monitoring (V5), backup/recovery (V6), production hardening (V7), AI agent (V8). Folders for them exist
and contain only a README marked NOT IMPLEMENTED.
