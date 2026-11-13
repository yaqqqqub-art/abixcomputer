# ABIX V6 - slice 1: Start menu, app launcher, ABIX Browser, animated logo

Built on Stage 5. Nothing from Stage 5 was removed. This is the FIRST slice of the V6 master prompt, not all of it (see section 5).

## 1. What is new
| Feature | Where |
|---|---|
| **Start menu** (button in the top bar): search, apps grouped by category, real status chips, power section (Sleep, Restart session, Restart desktop, Shut down, Sign out - each asks first) | `frontend/start.js`, `app.css`, `index.html` |
| **Launcher API**: `GET /api/launcher`, `POST /api/launcher/launch` (login + CSRF + not-locked, commands fixed on the server, the browser sends only an app id) | `backend/abix_launch.py` |
| **24 apps with icons**: File Manager, ABIX Notepad, Calculator, Archive Manager, Terminal, Task Manager, System Monitor, Screenshot Tool, Settings, **ABIX Browser**, Chrome, Firefox, Edge, **WhatsApp**, **imo**, Telegram, **Adobe Premiere Pro**, **Adobe After Effects**, GIMP, Inkscape, Krita, Audacity, Kdenlive, VS Code | `frontend/icons/` |
| **ABIX Browser**: ABIX-branded REAL browser (Chrome/Edge/Chromium engine, else Firefox) with its own persistent profile `~/.config/abix-browser` and an ABIX start page. Tabs, bookmarks, history, downloads come from the engine | `docker/abix/abix-browser` |
| **Web apps** WhatsApp / imo / Telegram: own window, own saved login `~/.config/abix-webapps/<id>` | `docker/abix/abix-webapp` |
| **Animated ABIX logo**: 5 styles (Pulse, Orbit, Draw, Bloom, Aurora) x 3 levels (Off, Light, Full), shown on boot, login, lock, restart, sign-out, shutdown; saved on the server (`~/.config/abix/ui.json`) so it survives restarts | `start.js`, `backend/abix_prefs.py` |
| **Restart / sign-out / start-up screens** with the animated logo; with animation Off they are skipped | `app.js` |

## 2. Honest status of each app
| State shown | Meaning |
|---|---|
| (no label) installed | the program was found on the server |
| Not installed | missing. Tiles with an App Center entry open the App Center |
| Web app | opens in a browser window; needs Chrome/Edge/Chromium or Firefox in the image |
| Windows only | **Premiere Pro and After Effects have no Linux version.** They show as launchable only after a verified Wine launcher is registered in `~/.config/abix/windows-apps.json` (the file must exist inside the home folder). Adobe's current apps are not known to run under Wine; nothing here claims they work. The "register an installed Windows app" screen is NOT built yet |

A launch is reported as success only if the process really started (still running = "starting", exited 0 = "started", exited with an error = the program's own error text).

## 3. Icons
All icons are original drawings made by `tools/gen_icons.py`, except File Manager and Screenshot Tool, which are the pictures you supplied. Brand icons (Chrome, WhatsApp, Adobe...) are simplified look-alikes, not the official logos. To use an official one, replace `frontend/icons/<id>.svg`.

## 4. Testing report (this build environment: no Docker, no real desktop, no internet)
| Test | Result |
|---|---|
| Stage 5 unit tests (apps 18, backend 15, abix-ctl 32, pointer, OSK) | all PASS, unchanged |
| `test_launch.py` (13): catalog sound, every icon exists, every install id exists in the App Center, running/started/failed with REAL fake programs, refusals, rate limit, Wine registry rejects paths outside home, prefs validation | PASS |
| `test_launch_api.py` (5): login required, CSRF, locked screen blocks, unknown/injected ids give 404, commands never sent to the browser | PASS |
| `test_frontend_ids.py` (7), CSP-friendly (no inline script/style/handler) | PASS |
| `tests/ui/test_ui.py` in real Chromium (49 checks): Start menu, icons load, chips, launch POST, Windows-only refusal, Off/Light/Full + all 5 styles really animate (computed CSS), choice survives reload, restart confirm + screen + return, Off skips the screen | PASS |
| `docker-compose.yml`: `cap_drop ALL`, `no-new-privileges`, not privileged, no docker.sock | unchanged, verified by reading |

NOT tested here, needs your server:
1. **Docker image build** with the new COPY lines.
2. **Real launch of each GUI app** inside the desktop (needs the real Xfce session). Test: Start menu > File Manager, Notepad, Terminal, Task Manager, Settings, ABIX Browser each open a window.
3. **ABIX Browser / WhatsApp / imo / Telegram** with real Chrome (installed only on amd64 builds with internet). Without Chrome they fall back to Firefox.
4. **Wine and Adobe apps**: unverified.
5. Smoothness of the animations through VNC: the animation runs in your browser, not in the cloud desktop, but low-end phones may stutter; choose Light or Off.

## 4b. Existing-image note
`Screenshot Tool` and `System Monitor` need `xfce4-screenshooter` and `htop`; install them from the App Center (the screenshooter entry was added).

## 5. Not done yet (V6 master prompt)
Windows-11 style taskbar/virtual desktops/window snapping inside the VNC desktop, desktop shortcuts and drag-and-drop, notification centre, full File Manager (rename/delete/copy/ZIP), Task Manager with graphs, EXE/MSI installer system with per-app Wine prefixes and persistent app records, ABIX Browser as a custom UI, full Settings app, wallpaper gallery with upload, sleep/volume/brightness hardware controls, performance modes beyond the existing Smooth/Turbo/Sharp presets. Each is a separate slice.

## 6. Update steps
1. Back up: `docker compose down` is NOT needed; copy the volume or run your usual backup first. Never run `docker compose down -v` (it deletes the home volume).
2. Replace the project folder with this one, keep your `.env`.
3. `docker compose build` then `docker compose up -d`.
4. Open the page, press **Start**.
