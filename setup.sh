#!/usr/bin/env bash
# Mochi setup for Linux: creates .venv, installs packages and Playwright's Chromium, runs the offline tests,
# and adds `mochi` / `mochi-window` to ~/.local/bin plus an app-menu entry.
#   ./setup.sh            # full setup
#   ./setup.sh --no-browser   # skip the Chromium download (Mochi's browser_* tools will not work)
#   ./setup.sh --uninstall    # remove the ~/.local/bin links and the app-menu entry (keeps this folder)
set -euo pipefail
cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
here="$PWD"
bin="$HOME/.local/bin"; apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications"

if [[ "${1:-}" == "--uninstall" ]]; then
  rm -f "$bin/mochi" "$bin/mochi-window" "$apps/mochi.desktop"
  echo "Removed the mochi command and menu entry. This folder ($here) was left untouched."
  exit 0
fi

py=""
for c in python3.13 python3.12 python3.11 python3; do
  if command -v "$c" >/dev/null && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then py="$c"; break; fi
done
[[ -n "$py" ]] || { echo "Python 3.11+ not found. Install it (e.g. sudo apt install python3 python3-venv)." >&2; exit 1; }
echo "Using Python: $($py --version)"

[[ -d .venv ]] || "$py" -m venv .venv || { echo "Could not create a venv. On Debian/Ubuntu: sudo apt install python3-venv" >&2; exit 1; }
.venv/bin/python -m pip install --upgrade pip -q
.venv/bin/python -m pip install -r requirements.txt -q
if [[ "${1:-}" != "--no-browser" ]]; then .venv/bin/python -m playwright install chromium; fi

mkdir -p workspace logs
[[ -f config.local.yaml ]] || cp config.local.example.yaml config.local.yaml

echo "Running the offline tests..."
.venv/bin/python -m pytest -q || echo "Some tests failed (see above). Mochi may still work."

chmod +x mochi mochi-window
mkdir -p "$bin" "$apps"
ln -sf "$here/mochi" "$bin/mochi"
ln -sf "$here/mochi-window" "$bin/mochi-window"
icon="$here/assets/mochi_small.png"
cat > "$apps/mochi.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=Mochi
Comment=A cute, careful local AI agent
Exec=$here/mochi-window
Icon=$icon
Terminal=false
Categories=Utility;
DESK
case ":$PATH:" in *":$bin:"*) ;; *) echo "Note: $bin is not on your PATH; add it to use the 'mochi' command." ;; esac

cat <<MSG

Done! Next: start a model server and point Mochi at it. With Ollama:
  ollama pull qwen3:14b            # any tool-calling model
  cp config.linux-ollama.example.yaml config.local.yaml   # then edit llm.model
Then run:  mochi   (terminal)   or   mochi-window   (chat window)
MSG
