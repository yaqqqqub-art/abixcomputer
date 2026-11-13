# ABIX Cloud Computer - Ubuntu LTS desktop (Xfce) reachable through noVNC
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    DISPLAY=:1

RUN apt-get update && apt-get install -y --no-install-recommends \
      xfce4 xfce4-terminal thunar mousepad dbus-x11 \
      tigervnc-standalone-server tigervnc-common novnc websockify supervisor nginx \
      python3 python3-pip python3-venv nodejs npm git curl wget ca-certificates \
      nano sudo procps fonts-dejavu fonts-noto-core xdg-utils \
      x11-utils x11-xserver-utils fontconfig python3-gi gir1.2-gtk-3.0 gir1.2-gdkpixbuf-2.0 \
    && apt-get purge -y light-locker xfce4-screensaver 2>/dev/null || true \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Apps. Ubuntu's own firefox/chromium packages are snap stubs that do not work in Docker,
# so Firefox comes from Mozilla's official apt repo (pinned above Ubuntu's).
RUN install -d -m 0755 /etc/apt/keyrings \
 && wget -q https://packages.mozilla.org/apt/repo-signing-key.gpg -O /etc/apt/keyrings/packages.mozilla.org.asc \
 && echo "deb [signed-by=/etc/apt/keyrings/packages.mozilla.org.asc] https://packages.mozilla.org/apt mozilla main" > /etc/apt/sources.list.d/mozilla.list \
 && printf 'Package: *\nPin: origin packages.mozilla.org\nPin-Priority: 1000\n' > /etc/apt/preferences.d/mozilla \
 && apt-get update && apt-get install -y --no-install-recommends \
      firefox evince ristretto file-roller gnome-calculator xfce4-taskmanager \
      papirus-icon-theme arc-theme fonts-noto-color-emoji \
 && (update-alternatives --set x-www-browser /usr/bin/firefox 2>/dev/null || true) \
 && test -x /usr/bin/firefox \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

# --- Stage 3: Chrome, Java runtime and (optional) Wine -------------------------------------------------------
# Windows .exe files cannot run natively on Ubuntu. Wine runs many simple Windows programs (no GPU games,
# no anti-cheat). Java runs .jar launchers (TLauncher etc). Everything here is NON-FATAL: if a download fails
# the image still builds and the result is listed in /usr/share/abix/optional-packages.txt.
ARG ABIX_WINE=1
# Stage 5: after every apt install, point Chrome / Edge / VS Code Start-menu entries at launchers that pass --no-sandbox.
COPY docker/abix/abix-fix-apps docker/abix/abix-chrome docker/abix/abix-edge /usr/local/bin/
RUN chmod 755 /usr/local/bin/abix-fix-apps /usr/local/bin/abix-chrome /usr/local/bin/abix-edge \
 && printf 'DPkg::Post-Invoke { "/usr/local/bin/abix-fix-apps || true"; };\n' > /etc/apt/apt.conf.d/99abix-fix-apps
# Stage 5: Chrome is only published for amd64, and a flaky download used to be skipped silently. Now: arch check,
# 5 download retries, and the result is verified by looking for the real binary.
RUN mkdir -p /usr/share/abix && touch /usr/share/abix/optional-packages.txt \
 && if [ "$(dpkg --print-architecture)" = "amd64" ]; then \
      ( wget -q --tries=5 --waitretry=3 --timeout=60 -O /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
        && apt-get update && apt-get install -y --no-install-recommends /tmp/chrome.deb \
        && test -x /opt/google/chrome/chrome \
        && echo "INSTALLED google-chrome-stable" >> /usr/share/abix/optional-packages.txt ) \
      || echo "SKIPPED  google-chrome-stable (download/install failed - install it later from ABIX Apps)" >> /usr/share/abix/optional-packages.txt ; \
    else echo "SKIPPED  google-chrome-stable (Google publishes Chrome for amd64 only; this is $(dpkg --print-architecture))" >> /usr/share/abix/optional-packages.txt ; fi \
 ; rm -f /tmp/chrome.deb; apt-get clean; rm -rf /var/lib/apt/lists/*
COPY docker/install-optional.sh /tmp/install-optional.sh
RUN bash /tmp/install-optional.sh default-jre unzip p7zip-full xdg-user-dirs \
 && if [ "${ABIX_WINE}" = "1" ]; then dpkg --add-architecture i386 && bash /tmp/install-optional.sh wine wine64 winetricks; fi \
 ; rm -f /tmp/install-optional.sh
COPY docker/desktop-entries/abix-chrome.desktop docker/desktop-entries/abix-java-jar.desktop /usr/share/applications/
COPY docker/abix/abix-chrome /usr/local/bin/abix-chrome
COPY docker/mimeapps.list /etc/xdg/mimeapps.list
COPY docker/policies/abix-chrome.json /etc/opt/chrome/policies/managed/abix.json
RUN chmod 755 /usr/local/bin/abix-chrome && chmod 644 /etc/opt/chrome/policies/managed/abix.json

# --- Abix look & feel (Stage 1) ---------------------------------------------------------------
# Optional packages are installed one by one; unavailable ones are skipped (see /usr/share/abix/optional-packages.txt).
#   whisker menu = Start menu, picom = compositor with fade, dmz cursor = Windows-like pointer,
#   fonts-inter = UI font, fonts-beng = extra Bangla fonts, fonts-firacode = terminal font
COPY docker/install-optional.sh /tmp/install-optional.sh
RUN bash /tmp/install-optional.sh xfce4-whiskermenu-plugin picom dmz-cursor-theme fonts-inter fonts-beng fonts-firacode xfce4-appfinder \
 && rm -f /tmp/install-optional.sh

# Whisker menu is not in Ubuntu 24.04's repos: build it from source (non-fatal if it fails).
COPY docker/build-whisker.sh /tmp/build-whisker.sh
RUN bash /tmp/build-whisker.sh && rm -f /tmp/build-whisker.sh

ARG ABIX_FLUENT=1
COPY docker/install-fluent.sh /tmp/install-fluent.sh
RUN ABIX_FLUENT=${ABIX_FLUENT} bash /tmp/install-fluent.sh && rm -f /tmp/install-fluent.sh

COPY assets/wallpapers/ /usr/share/backgrounds/abix/
COPY assets/icons/abix-start.svg /usr/share/icons/hicolor/scalable/apps/abix-start.svg
RUN gtk-update-icon-cache -f /usr/share/icons/hicolor >/dev/null 2>&1 || true
COPY docker/abix/abix-ctl docker/abix/abix-personalize docker/abix/abix-session-start docker/abix/abix-session-init /usr/local/bin/
COPY docker/desktop-entries/abix-personalize.desktop docker/desktop-entries/abix-restart-session.desktop /usr/share/applications/
COPY docker/desktop-entries/abix-session-init.desktop /etc/xdg/autostart/
RUN chmod 755 /usr/local/bin/abix-ctl /usr/local/bin/abix-personalize /usr/local/bin/abix-session-start /usr/local/bin/abix-session-init \
 && python3 -m py_compile /usr/local/bin/abix-ctl /usr/local/bin/abix-personalize

# Non-root desktop user. UID 1000 may already exist in the base image, so remove it first.
RUN (userdel -r ubuntu 2>/dev/null || true) \
 && useradd -m -s /bin/bash -u 1000 abix

# X11 socket dir must exist and be sticky/world-writable so the non-root Xtigervnc can create its socket.
RUN mkdir -p /tmp/.X11-unix && chmod 1777 /tmp/.X11-unix \
 && ls /usr/bin/Xtigervnc

# Stage 2: API (login, lock, settings, power). Stdlib only; runs as root inside the container so the desktop user cannot read its secrets.
COPY backend/abix_api.py backend/abix_apps.py backend/abix_launch.py backend/abix_prefs.py /usr/local/lib/abix/
COPY backend/apps-catalog.json /usr/local/share/abix/apps-catalog.json
RUN python3 -m py_compile /usr/local/lib/abix/abix_api.py /usr/local/lib/abix/abix_apps.py /usr/local/lib/abix/abix_launch.py /usr/local/lib/abix/abix_prefs.py && chmod 755 /usr/local/lib/abix/abix_api.py \
 && install -d -m 700 /etc/abix && install -d -m 755 /var/cache/abix

# Stage 3.1: Microsoft Edge (non-fatal, like Chrome). Placed late so earlier cached layers are not rebuilt.
RUN ( install -d -m 0755 /etc/apt/keyrings \
      && wget -q -O /etc/apt/keyrings/microsoft.asc https://packages.microsoft.com/keys/microsoft.asc \
      && echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/microsoft.asc] https://packages.microsoft.com/repos/edge stable main" > /etc/apt/sources.list.d/microsoft-edge.list \
      && apt-get update && apt-get install -y --no-install-recommends microsoft-edge-stable \
      && echo "INSTALLED microsoft-edge-stable" >> /usr/share/abix/optional-packages.txt ) \
    || echo "SKIPPED  microsoft-edge-stable (download/install failed, or this is not an amd64 build)" >> /usr/share/abix/optional-packages.txt \
 ; apt-get clean; rm -rf /var/lib/apt/lists/*
# ---- V6: ABIX Browser, web apps, browser start page
COPY docker/abix/abix-browser docker/abix/abix-webapp /usr/local/bin/
COPY docker/desktop-entries/abix-browser.desktop /usr/share/applications/abix-browser.desktop
COPY assets/browser/browser-home.html /usr/share/abix/browser-home.html
RUN chmod 755 /usr/local/bin/abix-browser /usr/local/bin/abix-webapp && chmod 644 /usr/share/abix/browser-home.html
COPY docker/policies/abix-chrome.json /etc/opt/edge/policies/managed/abix.json
COPY docker/abix/abix-edge /usr/local/bin/abix-edge
COPY docker/desktop-entries/abix-edge.desktop /usr/share/applications/abix-edge.desktop
RUN chmod 755 /usr/local/bin/abix-edge

# --- Stage 4: development languages (Java, Python, Node.js) -----------------------------------------
# Java 21 JDK (compile + run), Python 3 with pip/venv/pipx + compiler tools, Node.js LTS from NodeSource
# (Ubuntu's own nodejs is old). NodeSource is non-fatal: if it cannot be reached, Ubuntu's nodejs+npm stay.
# System packages are also brought up to date once at build time (apt-get upgrade).
ARG NODE_MAJOR=24
RUN apt-get update && apt-get upgrade -y \
 && apt-get install -y --no-install-recommends openjdk-21-jdk python3-dev python3-pip python3-venv python3-wheel pipx \
      build-essential pkg-config zip unzip jq less \
 && ( curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" -o /tmp/nodesource.sh \
      && bash /tmp/nodesource.sh && apt-get install -y nodejs \
      && echo "INSTALLED nodejs (NodeSource ${NODE_MAJOR}.x)" >> /usr/share/abix/optional-packages.txt ) \
    || echo "SKIPPED  NodeSource nodejs (download failed) - Ubuntu's nodejs/npm are used" >> /usr/share/abix/optional-packages.txt \
 ; rm -f /tmp/nodesource.sh; apt-get clean; rm -rf /var/lib/apt/lists/* \
 && java -version && javac -version && python3 --version && pip3 --version && node --version && npm --version
# pip: Ubuntu 24.04 blocks "pip install" system-wide (PEP 668). Allow it for the desktop user (goes to ~/.local, kept in the volume).
# npm: global packages go to ~/.npm-global so "npm install -g" works without root.
RUN printf '[global]\nbreak-system-packages = true\n' > /etc/pip.conf \
 && mkdir -p /usr/etc && printf 'prefix=/home/abix/.npm-global\n' > /usr/etc/npmrc \
 && printf '\n# ABIX dev tools\nexport PATH="$HOME/.local/bin:$HOME/.npm-global/bin:$PATH"\nexport JAVA_HOME="$(dirname "$(dirname "$(readlink -f "$(command -v javac)")")")"\n' >> /etc/bash.bashrc
ENV NPM_CONFIG_PREFIX=/home/abix/.npm-global
ENV PATH="/home/abix/.local/bin:/home/abix/.npm-global/bin:${PATH}"
COPY docker/abix/abix-versions docker/abix/abix-xvnc docker/abix/abix-smooth /usr/local/bin/
RUN chmod 755 /usr/local/bin/abix-versions /usr/local/bin/abix-xvnc /usr/local/bin/abix-smooth

# --- Stage 5: optional extra Ubuntu packages baked into the image (survive every rebuild) ----------------------
# docker compose build --build-arg ... or set ABIX_EXTRA_APT="vlc gimp" in .env
ARG ABIX_EXTRA_APT=""
RUN if [ -n "${ABIX_EXTRA_APT}" ]; then apt-get update && apt-get install -y --no-install-recommends ${ABIX_EXTRA_APT} ; fi ; apt-get clean; rm -rf /var/lib/apt/lists/*

COPY docker/supervisord.blitz.conf /etc/supervisor/conf.d/abix.conf
COPY deployment/nginx-blitz.conf /etc/nginx/conf.d/default.conf
COPY frontend/ /usr/share/nginx/abix/
RUN rm -f /etc/nginx/sites-enabled/default
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
COPY docker/vncpw.py /usr/local/bin/vncpw.py
RUN chmod +x /usr/local/bin/entrypoint.sh /usr/local/bin/vncpw.py

# Only the internal noVNC web port. VNC itself listens on localhost inside the container.
EXPOSE 6080
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]
