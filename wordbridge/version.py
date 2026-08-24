import subprocess
from pathlib import Path


def get_version():
    """Short git commit hash the running app was checked out at.

    Wordbridge deploys via a real `git pull` on the server (see DEPLOY.md),
    so the checkout always has full history available - no manual version
    bump to remember, and it can never drift out of sync with what's
    actually deployed. Returns "unknown" outside a git checkout (e.g. a
    stripped-down deploy, or if git itself isn't available).
    """
    repo_root = Path(__file__).resolve().parent.parent
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"
