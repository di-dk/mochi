"""Shortcuts must stay the kind antivirus engines leave alone.

A .lnk that starts cmd.exe / wt.exe / powershell with arguments is what engines call "Trojan.Loader". Mochi's own
shortcut once used that form and was quarantined (Malwarebytes). The installer must point shortcuts straight at the
launcher files, with no arguments.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_setup_shortcuts_point_at_launchers_with_no_arguments():
    text = (ROOT / "setup.ps1").read_text(encoding="utf-8")
    block = text[text.index("# 5. Desktop shortcuts"):text.index("# 6.")]
    block = "\n".join(l for l in block.splitlines() if not l.lstrip().startswith("#"))   # code only, not comments
    assert "$s.Arguments = ''" in block
    assert not re.search(r"\.Arguments\s*=\s*[\"'`][^\"']", block), "shortcut arguments are what antivirus flags"
    for bad in ("wt.exe", "cmd /k", "powershell", "ComSpec", "-WindowStyle", "Hidden"):
        assert bad.lower() not in block.lower(), f"setup.ps1 shortcut step uses {bad}"
    assert "mochi.cmd" in block and "mochi-window.cmd" in block


def test_launchers_exist_and_the_window_one_starts_pythonw_without_tricks():
    assert (ROOT / "mochi.cmd").is_file()
    win = (ROOT / "mochi-window.cmd").read_text(encoding="utf-8")
    assert "pythonw.exe" in win and "-m agent.cli --gui" in win
    for bad in ("powershell", "-enc", "-w hidden", "bitsadmin", "certutil", "curl", "http"):
        assert bad not in win.lower(), f"mochi-window.cmd contains {bad}"
