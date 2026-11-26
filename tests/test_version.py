"""Which version of Mochi is running: the label in the chat window, the terminal and --version."""
import re
import subprocess

import pytest

from agent import version
from agent.cli import main


@pytest.fixture(autouse=True)
def fresh():
    version.detail.cache_clear()
    yield
    version.detail.cache_clear()


def describe(monkeypatch, out, git_dir=True, tmp=None):
    monkeypatch.setattr(version, "ROOT", tmp if tmp is not None else version.ROOT)
    if tmp is not None and git_dir:
        (tmp / ".git").mkdir(exist_ok=True)
    monkeypatch.setattr(version.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, out + "\n", ""))
    version.detail.cache_clear()
    return version.detail()


def test_the_version_is_a_release_number():
    assert re.fullmatch(r"\d+\.\d+\.\d+", version.__version__)


@pytest.mark.parametrize("git_out,expected", [
    ("v{v}", "v{v}"),                                                                # exactly the release
    ("v{v}-dirty", "v{v} (development: local changes)"),
    ("v{v}-3-gabc1234", "v{v} (development: 3 newer commits, abc1234)"),
    ("v{v}-1-gabc1234-dirty", "v{v} (development: 1 newer commit, abc1234, local changes)"),
    ("v0.1.0", "v{v} (development: after v0.1.0)"),                                   # code newer than the last tag
    ("abc1234", "v{v} (development: abc1234)"),                                       # no tags at all
])
def test_a_development_checkout_says_so(monkeypatch, tmp_path, git_out, expected):
    v = version.__version__
    assert describe(monkeypatch, git_out.format(v=v), tmp=tmp_path) == expected.format(v=v)


def test_without_git_it_is_just_the_release(monkeypatch, tmp_path):
    assert describe(monkeypatch, "v9.9.9", git_dir=False, tmp=tmp_path) == f"v{version.__version__}"   # no .git folder
    monkeypatch.setattr(version, "ROOT", tmp_path)
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(version.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError("no git")))
    version.detail.cache_clear()
    assert version.detail() == f"v{version.__version__}"                                               # git missing


def test_the_short_label(monkeypatch, tmp_path):
    describe(monkeypatch, f"v{version.__version__}", tmp=tmp_path)
    assert version.short() == f"v{version.__version__}"
    describe(monkeypatch, f"v{version.__version__}-2-gabcdef0", tmp=tmp_path)
    assert version.short() == f"v{version.__version__} · dev"


def test_mochi_dash_dash_version(capsys):
    assert main(["--version"]) == 0
    assert capsys.readouterr().out.startswith(f"Mochi v{version.__version__}")
