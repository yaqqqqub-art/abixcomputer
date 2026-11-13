# Stage 5 - Chrome fix, App Center (setup .exe download), smooth / no-lag

## What was wrong with Chrome
1. **The Start-menu entry that Google's .deb installs has no `--no-sandbox`.** In this container (all capabilities dropped)
   Chrome refuses to start without it, so clicking "Google Chrome" did nothing. Fixed by `abix-fix-apps`, which apt runs after
   every install (`/etc/apt/apt.conf.d/99abix-fix-apps`): it points the Chrome / Edge entries at `abix-chrome` / `abix-edge`
   and adds `--no-sandbox` to VS Code.
2. A stale profile lock after a container restart ("profile in use") - `abix-chrome` removes it when no Chrome is running.
3. A crashing GPU process gave a blank window - `--disable-gpu` (and the matching Chrome policy) now.
4. The Chrome download at build time failed silently - now 5 retries, amd64 check, and the real binary is verified.
   If Chrome is missing (or the server is arm64: Google publishes no arm64 Chrome) clicking it shows a message and opens Firefox.
   Install it later from **Apps**.

## App Center (top bar > Apps)
* **Catalog apps** (Chrome, VS Code, VLC, LibreOffice, GIMP, Inkscape, Krita, Audacity, Kdenlive, FileZilla, Transmission, htop):
  Install / Remove with a progress bar and a details log. Edit `backend/apps-catalog.json` to add your own (apt package or fixed https .deb).
* **Windows setup .exe / .msi**: paste the https download link, press *Download and run*. The file goes to `~/Downloads`
  and starts in Wine as the desktop user (never root). You can also upload a setup file with **Files** and double-click it.
* Apps installed from the catalog are remembered in `~/.config/abix/apps-installed.json` (inside the persistent volume) and
  reinstalled automatically if the container is re-created (`ABIX_APPS_RESTORE=0` turns this off). To bake apps into the image:
  `ABIX_EXTRA_APT="vlc gimp"` in `.env`, then `docker compose up -d --build`.

### Safety rules of the download
https only, port 443 only, no `user:pass@`, every redirect re-checked, the host must resolve to **public** addresses only
(blocks localhost, 10.x, 172.16-31.x, 192.168.x, 169.254.x, the Docker network), the connection is pinned to the checked
address (no DNS rebinding), size limit `ABIX_MAX_DOWNLOAD_MB` (2048), 30 minute limit, `.exe` must start with `MZ`, `.msi` with the OLE header
(a fake file is deleted). Custom links can **not** install `.deb` files, because that would give root to any link you paste.
Everything needs the login session, the CSRF header and an unlocked screen.

### Honest limits
* Wine runs many simple Windows programs. It does **not** run most games, anti-cheat, or programs needing a real GPU or .NET installers that cannot download.
  WhatsApp / imo / Telegram Desktop for Windows are better used as web apps inside Chrome.
* Android `.apk` is not supported (needs an Android runtime such as Waydroid, which needs kernel features Docker does not give).
* Apt installs go into the container, not the volume: a rebuild removes them unless restore (default on) or `ABIX_EXTRA_APT` brings them back.

## Smooth / no lag
| Change | Why it helps |
|---|---|
| `abix-xvnc` starts Xtigervnc with `FrameRate 60`, `MaxProcessorUsage 90`, `DeferUpdate 1`, `CompareFB 2` (each only if this build supports it) | the default 35 % encoder limit throttles a busy desktop |
| New default speed **Smooth** (quality 5, compression 1) and new **Turbo** (quality 2, compression 0) | less CPU per frame; Turbo for slow internet |
| Brightness filter is removed at 100 % and the night-light layer is `display:none` when off | a permanent CSS filter forced the whole VNC picture through an extra compositing pass |
| Nginx: `/desktop/` unbuffered, keepalive, no gzip on the VNC stream; noVNC files cached 1 day | no waiting in buffers, faster start, fewer reconnects |
| Chrome: no GPU, no smooth scrolling, no background networking | fewer frames to send |
| Compose defaults: 3 CPUs, 4 GB, 1024 processes (was 2 / 2 GB / 512) | Chrome + Wine need headroom |
| `abix-smooth on` (terminal) | animations off + compositor off in one command; `abix-smooth off` reverts |

Fastest setup for a weak server or phone: `abix-smooth on`, Speed = Turbo, and a smaller `DESKTOP_GEOMETRY` (for example `1280x720`) in `.env`.
Lag also depends on your internet and on the server's CPU; no setting can fix a 1-core server.

## Tests
Run and passing in the authoring sandbox: `tests/unit/test_apps.py` (18), `test_backend.py` (15), `test_frontend_ids.py` (6), pointer + keyboard JS tests,
`test_abix_ctl.sh` (32), `tests/ui/test_ui.py` (30, real Chromium against a fake noVNC page, includes App Center).
**Not run (no Docker, no internet here):** the image build, real Chrome start, real apt/.deb installs, real downloads over HTTPS, Wine launching a real
installer, and the speed options on a real Xtigervnc. `tests/smoke.sh` has 10 new `S5` checks for these - run it and send the result.
