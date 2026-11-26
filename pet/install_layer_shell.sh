#!/usr/bin/env bash
# Pet mode needs gtk4-layer-shell (it lets her window sit on top of everything). Pop!_OS / Ubuntu 24.04 do not package the GTK4
# version, so this builds it from source into ~/.local (nothing system-wide changes). Needs, once (sudo):
#   sudo apt install -y meson ninja-build libgtk-4-dev gobject-introspection libgirepository1.0-dev
set -euo pipefail
command -v meson >/dev/null || { echo "meson is missing: run the sudo apt line in this file first"; exit 1; }
src="$HOME/.local/src/gtk4-layer-shell"
mkdir -p "$HOME/.local/src"
[ -d "$src" ] || git clone --depth 1 --branch v1.3.0 https://github.com/wmww/gtk4-layer-shell "$src"
cd "$src"
meson setup build --prefix="$HOME/.local" -Dexamples=false -Ddocs=false -Dtests=false -Dintrospection=true -Dvapi=false --reconfigure >/dev/null 2>&1 \
  || meson setup build --prefix="$HOME/.local" -Dexamples=false -Ddocs=false -Dtests=false -Dintrospection=true -Dvapi=false
ninja -C build
ninja -C build install
echo "Done. Start her with: ./mochi --pet"
