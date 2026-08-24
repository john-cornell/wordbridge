import subprocess

import wordbridge.version as version_module
from wordbridge.version import get_version


def test_get_version_returns_the_current_git_short_hash():
    expected = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    assert get_version() == expected


def test_get_version_returns_unknown_outside_a_git_checkout(tmp_path, monkeypatch):
    # tmp_path has no .git anywhere above it, so `git rev-parse` run there
    # fails - get_version must degrade gracefully rather than raise.
    monkeypatch.setattr(version_module, "__file__", str(tmp_path / "wordbridge" / "version.py"))
    assert version_module.get_version() == "unknown"
