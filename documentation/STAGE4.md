# ABIX Cloud Computer - Stage 4 (incremental, built on Stage 3)

Login, lock, Settings, wallpapers, Nginx and the `abix-home` volume are unchanged.

## What was added
| Feature | Where | How it was checked |
|---|---|---|
| **Java 21 (JDK), Python 3 (pip, venv, pipx, build tools), Node.js LTS + npm**, `apt-get upgrade` at build time | `docker/Dockerfile.desktop` | **Docker build NOT run** (no Docker here). The build fails on purpose if `java`, `javac`, `python3`, `pip3`, `node` or `npm` is missing. `tests/smoke.sh` has 7 checks for them. |
| `pip install` and `npm install -g` work without root (go to `~/.local` and `~/.npm-global`, kept in the volume) | `/etc/pip.conf`, `/etc/npmrc`, `/etc/bash.bashrc` | untested in a container |
| `abix-versions` command prints all versions | `docker/abix/abix-versions` | script written, not run in a container |
| **Mouse button** (top bar) with 3 modes + normal: **Touchpad** (laptop-style), **Mouse pad** (on-screen pad with Left/Right buttons and scroll strip), **Direct touch** | `frontend/pointer.js` | Gesture logic: `node tests/unit/test_pointer.js` (passes). Real Chromium against a fake noVNC page: `python3 tests/ui/test_ui.py` (passes). **Not tested against the real noVNC on a phone.** |
| **Copy / Paste** (top bar menu and on the keyboard panel): Copy, Cut, Paste, Select all, Terminal copy, Terminal paste, fallback text box | `frontend/extras.js`, `vncconfig` in `supervisord.conf` | Same Chromium test (keys reach the canvas, text goes into noVNC's clipboard box). **Real clipboard sync with the Ubuntu desktop is untested.** |
| **Click sounds** on every button and on touchpad taps (toggle in Settings) | `frontend/extras.js` | code runs without errors in Chromium; the sound itself was not heard |
| **Smoother**: eased panel/menu/page animations, Speed presets Smooth / Balanced / Sharp, gzip + `tcp_nodelay` in Nginx, drag-and-drop file upload | `app.css`, `app.js`, `nginx.conf` | Preset URL parameters tested; real speed gain not measured |
| **Public link with password** (Cloudflare Tunnel) | `docker-compose.public.yml` | YAML checked only; **never started** |

## Using the mouse modes
* **Touchpad**: drag = move the arrow. Tap = left click. Tap, then touch and drag = drag. Two-finger tap = right click. Two fingers up/down = scroll.
* **Mouse pad**: a small pad at the bottom. Hold Left/Right to keep a button down. The strip on the right scrolls.
* **Direct touch**: tap where you want. Long press = right click. Drag to drag. Two fingers = scroll.
* Settings has pointer speed and natural scrolling. A real mouse still works in every mode. The choice is remembered. Phones/tablets start in Touchpad mode, PCs in Normal.

## Copy / Paste
* **Paste**: copy text on your device as usual, press **Paste**. The text is sent to the cloud PC and Ctrl+V is pressed. In the terminal use **Terminal paste** (Ctrl+Shift+V).
* **Copy**: select text in the cloud PC, press **Copy**. It is sent to your device's clipboard. If the browser blocks clipboard access, the text appears in the box of the menu so you can copy it by hand.
* The first time, the browser asks for clipboard permission. Allow it.
* Needs `vncconfig` (started by supervisor). If Copy says "Nothing was copied", check `docker exec abix-desktop pgrep -u abix vncconfig`.

## Share it with a password (public link)
**Read first.** Whoever signs in controls a Linux desktop with a browser and a terminal. There is **one** login (`ABIX_ADMIN_USER`). Separate accounts per person are Stage V4 and are not built. Do not give the password to people you do not trust.
1. Set a long password: `ABIX_NEW_PASSWORD='a-long-passphrase-12+' bash deployment/set-password.sh && docker compose up -d`
2. Start with the tunnel: `docker compose -f docker-compose.yml -f docker-compose.public.yml up -d --build`
3. Get the address: `docker compose -f docker-compose.yml -f docker-compose.public.yml logs tunnel | grep trycloudflare.com`
4. Open that `https://....trycloudflare.com` link in Chrome, on any device, and sign in. The quick link changes when the tunnel restarts. For a fixed name use a Cloudflare account + domain and `CLOUDFLARE_TUNNEL_TOKEN` (see the header of `docker-compose.public.yml`).
5. Stop sharing: `docker compose -f docker-compose.yml -f docker-compose.public.yml stop tunnel`

Protection that exists: HTTPS, password (PBKDF2), 5 login tries per minute per address, lockout in the API, no VNC port published, locked screen blocks the desktop. Not built: 2FA, per-user accounts, idle auto-lock.
Alternative for a VPS with a domain: point DNS to the server, put a Let's Encrypt certificate in `deployment/certs/` (see `DEPLOYMENT.md`) and open ports 80/443.

## Honest notes
* "ubuntu": the desktop already is Ubuntu 24.04. Stage 4 updates its packages at build time and adds the dev tools. `sudo` for the desktop user stays off on purpose (`no-new-privileges`, all capabilities dropped), so system-wide `apt install` inside the running desktop does not work: add packages to the Dockerfile and rebuild.
* Image size grows by roughly 600-900 MB (JDK, compilers, Node). The first build takes longer.
* Minecraft / TLauncher is still slow: no GPU, 2 CPU cores.
