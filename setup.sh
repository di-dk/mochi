#!/usr/bin/env bash
# Mochi setup for Linux: creates .venv, installs packages and Playwright's Chromium, runs the offline tests,
# and adds `mochi` / `mochi-window` to ~/.local/bin plus an app-menu entry.
#   ./setup.sh            # full setup
#   ./setup.sh --no-browser   # skip the Chromium download (Mochi's browser_* tools will not work)
#   ./setup.sh --no-skillspector   # skip NVIDIA SkillSpector (then she cannot import skills: every skill must be scanned)
#   ./setup.sh --uninstall    # remove the ~/.local/bin links and the app-menu entry (keeps this folder)
set -euo pipefail
cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
here="$PWD"
bin="$HOME/.local/bin"; apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
NO_BROWSER=0; NO_SS=0
for a in "$@"; do case "$a" in --no-browser) NO_BROWSER=1;; --no-skillspector) NO_SS=1;; esac; done

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

# App control (app_inspect, app_click, ...) uses AT-SPI through PyGObject, which comes from the system packages
# (sudo apt install python3-gi gir1.2-atspi-2.0). If they are present, let the venv see them.
venv_args=()
if "$py" -c 'import gi; gi.require_version("Atspi", "2.0")' 2>/dev/null; then venv_args=(--system-site-packages); fi
[[ -d .venv ]] || "$py" -m venv "${venv_args[@]}" .venv || { echo "Could not create a venv. On Debian/Ubuntu: sudo apt install python3-venv" >&2; exit 1; }
if [[ ${#venv_args[@]} -eq 0 ]]; then
  echo "Note: PyGObject/AT-SPI not found, so Windows/app control tools will be unavailable."
  echo "      Install with: sudo apt install python3-gi gir1.2-atspi-2.0 at-spi2-core   (then re-run ./setup.sh in a fresh .venv)"
fi
.venv/bin/python -m pip install --upgrade pip -q
.venv/bin/python -m pip install -r requirements.txt -q
if [[ $NO_BROWSER -eq 0 ]]; then .venv/bin/python -m playwright install chromium; fi


# Her voice (all local): Kokoro text-to-speech and Whisper speech recognition model files, about 840 MB, fetched once.
mkdir -p models/voice/whisper-small
K=https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0
for f in kokoro-v1.0.onnx voices-v1.0.bin; do [[ -s models/voice/$f ]] || curl -fsSL -o models/voice/$f "$K/$f" || echo "Could not download $f (voice stays off)"; done
for f in config.json model.bin tokenizer.json vocabulary.txt; do
  [[ -s models/voice/whisper-small/$f ]] || curl -fsSL -o models/voice/whisper-small/$f "https://huggingface.co/Systran/faster-whisper-small/resolve/main/$f" || echo "Could not download $f (listening stays off)"
done

# NVIDIA SkillSpector (Apache-2.0) scans every skill BEFORE she installs it. It brings many dependencies, so it gets its
# own virtual environment in .skillspector/ (it needs Python 3.12 or 3.13).
if [[ $NO_SS -eq 0 ]]; then
  sp=""
  for c in python3.13 python3.12; do if command -v "$c" >/dev/null; then sp="$c"; break; fi; done
  if [[ -z "$sp" ]]; then
    echo "Note: SkillSpector needs Python 3.12 or 3.13, so she cannot import skills until it is installed (see the README)."
  else
    [[ -d .skillspector ]] || "$sp" -m venv .skillspector
    .skillspector/bin/python -m pip install --upgrade pip -q
    if .skillspector/bin/python -m pip install -q "skillspector==2.13.7"; then
      echo "SkillSpector installed: $(.skillspector/bin/skillspector --version)"
    else
      echo "Note: could not install SkillSpector; she cannot import skills until it is installed."
    fi
  fi
fi

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
