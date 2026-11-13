# ABIX Cloud Computer - Stage 3 (incremental)

Stage 3 is built **on top of** Stage 2. Login, lock, settings, wallpapers, Nginx and the Docker volume `abix-home` are unchanged.

## What was added
| Feature | Where | Status |
|---|---|---|
| Power on / shut down screens (Windows-like: "Shutting down..." -> black screen with power button -> boot logo -> login) | frontend | Code written, static test passes. **Not yet clicked through in a real browser.** |
| Power menu: Sleep (lock), Sign out, Shut down | frontend + `POST /api/power {action:"shutdown"}` | Backend **tested** (session really ends). UI untested in browser. |
| Brightness slider + Night light | frontend (CSS filter on the screen, stored in this browser) | Code written, untested in browser. It is not real hardware brightness: a cloud PC has no backlight. |
| Widgets panel (clock, date, quick notes, web-app hints) | frontend | Code written, untested in browser. |
| Files panel: browse, **download to your PC**, **upload from your PC**, new folder | frontend + `/api/files`, `/api/files/download`, `/api/files/upload`, `/api/files/mkdir` | Backend **tested** (see below). UI untested in browser. |
| Google Chrome (`abix-chrome`, runs with `--no-sandbox`, required because the container drops all capabilities) | Dockerfile | **Docker build NOT tested** (no Docker in the build environment). |
| Java (runs `.jar` launchers such as TLauncher), Wine (runs some `.exe`), 7zip/unzip | Dockerfile | **Docker build NOT tested.** Install failures are non-fatal and listed in `/usr/share/abix/optional-packages.txt`. |
| `.exe` opens with Wine instead of the Archive Manager | `docker/mimeapps.list`, `abix-session-init` | **Untested.** |
| Computer name `abix-computer` | `hostname:` in docker-compose, shown in the top bar | Not tested in a running container. |
| Non-interactive login setup (`ABIX_ADMIN_USER`, `ABIX_INIT_PASSWORD`, `ABIX_NEW_PASSWORD`) | `deployment/init.sh`, `set-password.sh` | **Tested** with the real hash function; password is never stored in clear text. |

## Tests that were actually run
* `python3 tests/unit/test_backend.py` : 15 tests (9 from Stage 2 + 6 new). Covers: login required for files, list/download, `../` / absolute path / `.ssh` / symlink-escape blocked, upload (name tricks stay in the folder, CSRF header required, size limit, no partial files), mkdir, locked screen blocks files, shutdown ends the session.
* `python3 tests/unit/test_frontend_ids.py` : every element id used by `app.js` exists, no duplicate ids, no inline script/style/handlers (Nginx CSP).

## NOT done in this stage (honest list)
The 20-application desktop-in-the-browser from the full specification (own window manager, own terminal, calculator, media player, App Store, AI assistant, full on-screen 104-key keyboard, multiple workspaces, task manager UI, ...) is **not built**. The actual desktop is still the real Xfce session shown through noVNC. That is a multi-stage project; do it one piece at a time.

## What cannot work on this design (and why)
* **Windows-only programs**: imo desktop and WhatsApp desktop have no Linux version. Use `imo.im` and `web.whatsapp.com` inside Chrome.
* **.exe installers and games**: Wine runs some simple programs. Heavy games (e.g. Cyberpunk 2077) will not run: the container has no GPU and 2 CPU cores. Minecraft via TLauncher needs Java and is very slow with software rendering.
* "Shut down" ends your web session and shows the off screen. The container keeps running, because a browser must not be able to stop the server (and downloads/files stay safe).

## Stage 3.1 - On-screen keyboard, Edge
| Feature | Status |
|---|---|
| **Keyboard** button in the top bar: full 104-key layout (A-Z, 0-9, F1-F12, Esc/Tab/Caps, Shift/Ctrl/Alt/Win/Menu, Enter/Space/Backspace/Delete, Ins/Home/End/PgUp/PgDn, arrows, Num Lock + keypad, all symbols, Print Screen/Scroll Lock/Pause) | Layout + press logic **tested** with a fake DOM (`node tests/unit/test_osk.js`: 104 unique keys, symbols, Shift/Ctrl latch, Caps Lock, keypad, held keys). **Not tested against the real noVNC screen in a browser.** |
| RGB glow (toggle), click sound (toggle), key name shown on hover/press, physical keys light up too, Power key opens the power menu | Code written; sound and RGB **untested in a browser**. |
| Microsoft Edge (`abix-edge`) | In Dockerfile, non-fatal. **Build not tested.** |
| `Fn` key | Deliberately absent: a real Fn key is handled by keyboard hardware and never reaches any computer. |

Keys are sent by dispatching keyboard events on the noVNC canvas. If a browser or noVNC version ignores synthetic events, the keyboard panel shows but typing into the desktop will not work; tell me and the fallback is a small bridge in noVNC itself.
