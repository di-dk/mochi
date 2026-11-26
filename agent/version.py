"""Which Mochi this is. __version__ is bumped when a release is made and matches its git tag (vX.Y.Z); when the code runs
from a git checkout that is ahead of that tag (or has local changes) the displayed version says so."""
from __future__ import annotations

import re
import subprocess
from functools import lru_cache
from pathlib import Path

__version__ = "0.14.0"
ROOT = Path(__file__).resolve().parent.parent


@lru_cache(maxsize=1)
def detail() -> str:
    """'v0.13.0' for a clean release, or e.g. 'v0.13.0 (development: 3 newer commits, abc1234, local changes)'."""
    base = f"v{__version__}"
    if not (ROOT / ".git").exists():
        return base
    try:
        out = subprocess.run(["git", "describe", "--tags", "--always", "--dirty"], cwd=ROOT, capture_output=True,
                             text=True, timeout=3).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return base
    m = re.fullmatch(r"v(\d+\.\d+\.\d+)(?:-(\d+)-g([0-9a-f]+))?(-dirty)?", out)
    if not m:                                     # no tags reachable: just a commit id
        h = re.fullmatch(r"([0-9a-f]{7,})(-dirty)?", out)
        return f"{base} (development: {h.group(1)}{', local changes' if h.group(2) else ''})" if h else base
    tag, ahead, short, dirty = m.groups()
    extras = ([f"after v{tag}"] if tag != __version__ else []) + \
             ([f"{ahead} newer commit{'s' if ahead != '1' else ''}"] if ahead else []) + \
             ([short] if short else []) + (["local changes"] if dirty else [])
    return f"{base} (development: {', '.join(extras)})" if extras else base


def short() -> str:
    """The version for a small label: 'v0.13.0', with ' · dev' when this is not exactly the release."""
    return f"v{__version__}" + (" · dev" if "(development" in detail() else "")
