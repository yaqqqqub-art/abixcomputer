# Stage 1 - Windows-style desktop

## What is tested and what is not
| Item | Status |
|---|---|
| `abix-ctl` logic: validation, file writing, fallback decisions, panel XML well-formed | **Tested** with fake commands (`bash tests/unit/test_abix_ctl.sh`, 32 checks) |
| Python/Bash syntax of every script, compose YAML parses | **Tested** (py_compile, bash -n, YAML load) |
| Wallpapers + logo generated and valid | **Tested** (files created, SVG valid) |
| Docker image build, Xfce/panel/Whisker/picom actually running under Xtigervnc | **Written, NOT tested** (no Docker daemon or internet in the authoring sandbox) |
| Panel position value `p=10` = bottom edge | **Written, NOT tested** (from Xfce defaults; if the bar appears elsewhere use Panel Preferences) |
| Fluent theme download/install flags | **Written, NOT tested** - failure is non-fatal, Arc is used |
| picom `corner-radius` on xrender backend | **Unknown** - if picom refuses, Full falls back to Light, then to the Xfce compositor |
| GTK Personalization window | **Written, NOT tested** (needs real GTK) |

## Honest limits (no GPU)
- No blur. Blur needs OpenGL; not enabled.
- picom 10.x (Ubuntu 24.04) has fade in/out only, no zoom/slide window animations. "Full" = fade + shadows (+ rounded corners if picom accepts it).
- The taskbar is centred with two expanding spacers, so it is only approximately centred (the tray on the right shifts it a little).
- No real lock screen yet (Stage 2). The Lock button is hidden in the Start menu.
- Windows-like Start menu = Whisker menu, not a pixel copy. Search is Whisker's search box (pill on the taskbar).

## Risks found while reading the project
1. Persistent volume: your old `/home/abix/.config/xfce4` exists. Seeding backs it up to `~/.config/abix/backup-<time>/` before writing the new panel.
2. A second Xfce session start must not lose the compositor state: `abix-session-init` re-applies settings each session.
3. picom may outlive a logged-out session: `abix-ctl anim` always kills the old picom first.
4. Build needs internet for the optional Fluent theme; offline build still works (Arc).
5. New packages can be missing in the base image: they are installed one by one and listed in `/usr/share/abix/optional-packages.txt`.

## Handy commands (inside the container as abix)
    abix-ctl status
    abix-ctl theme dark          # or light
    abix-ctl anim full           # off | light | full
    abix-ctl wallpaper /usr/share/backgrounds/abix/abix-aurora.jpg
    abix-ctl seed --force        # rebuild taskbar/menu/icons (old config backed up)

## Rollback
- Whole stage: restore the previous project zip, then `docker compose up -d --build` (the `abix-home` volume is kept).
- Only the desktop look: put the backup back: `cp -r ~/.config/abix/backup-<time>/xfce4 ~/.config/` and restart the session.
- Never run `docker compose down -v` (it deletes your home volume).
