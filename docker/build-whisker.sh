#!/bin/bash
# Fallback only: the apt package xfce4-whiskermenu-plugin is tried first (install-optional.sh).
# This builds Whisker from source ONLY if the apt package did not install. Any failure is non-fatal.
set -u
export DEBIAN_FRONTEND=noninteractive
LIBGLOB="/usr/lib/*/xfce4/panel/plugins/libwhiskermenu.so /usr/lib/xfce4/panel/plugins/libwhiskermenu.so"
if ls $LIBGLOB >/dev/null 2>&1; then echo "whisker already installed"; exit 0; fi
BUILD_DEPS="cmake meson ninja-build g++ make gettext git ca-certificates pkg-config libgtk-3-dev libxfce4panel-2.0-dev libxfce4ui-2-dev libxfce4util-dev libgarcon-1-dev libgarcon-gtk3-1-dev libexo-2-dev libxfconf-0-dev"
T="$(mktemp -d)"
build_dir() {
  if [ -f "$1/CMakeLists.txt" ]; then
    ( cd "$1" && cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr \
        && cmake --build build -j2 && cmake --install build )
  elif [ -f "$1/meson.build" ]; then
    ( cd "$1" && meson setup build --prefix=/usr --buildtype=release \
        && ninja -C build && ninja -C build install )
  else
    echo "no CMakeLists.txt or meson.build in $1"; return 1
  fi
}
try_remote() {
  echo "== remote: $1"
  local tags
  tags="$(git ls-remote --tags --refs "$1" 2>&1 | sed 's#.*refs/tags/##' | grep -E '2\.[78]\.[0-9]+$' | sort -V -r | head -6)"
  if [ -z "$tags" ]; then echo "no usable tags found at $1"; return 1; fi
  echo "tags to try: $(echo $tags | tr '\n' ' ')"
  for tag in $tags; do
    rm -rf "$T/w"
    git clone --depth 1 --branch "$tag" "$1" "$T/w" || { echo "clone $tag failed"; continue; }
    if build_dir "$T/w"; then echo "whisker $tag built and installed from $1"; return 0; fi
    echo "build of $tag failed"
  done
  return 1
}
if apt-get update && apt-get install -y --no-install-recommends $BUILD_DEPS; then
  try_remote https://gitlab.xfce.org/panel-plugins/xfce4-whisker-menu-plugin.git \
    || try_remote https://github.com/gottcode/xfce4-whisker-menu-plugin.git \
    || echo "whisker build FAILED - Xfce Applications menu will be used"
else
  echo "could not install build dependencies - Xfce Applications menu will be used"
fi
apt-get purge -y cmake meson ninja-build g++ make >/dev/null 2>&1
apt-get clean; rm -rf /var/lib/apt/lists/* "$T"
ls $LIBGLOB 2>/dev/null || echo "NO whisker present"
exit 0
