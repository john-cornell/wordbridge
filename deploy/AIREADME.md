# Deploy manifest (for Claude / future maintainers)

Deployment works by `git clone`-ing the whole repo onto the server (see
`../DEPLOY.md`), so nothing here is enforced by tooling — this file is just
the canonical list of what actually matters once it's there. **Whenever a
change touches what runs in production, update this file in the same
change**, not as an afterthought.

## Required in production

- `app.py` — entry point; loads the model and builds the `app:app` object gunicorn serves.
- `wordbridge/` — the actual application package (routes, game logic, model wrapper, db).
- `static/` — served directly by Flask (`index.html`, `scores.html`, `app.js`, `graph.js`, `style.css`).
- `requirements.txt` — pinned deps. **Currently unsplit**: `flask`, `gensim`, `numpy`, `gunicorn` are the real runtime deps; `pytest` and `playwright` are dev/test-only but still get installed on the server today because there's one shared file. Fine for a toy app's install size — flag it if that ever needs to change.
- `deploy/wordbridge.service` — the systemd unit; copied to `/etc/systemd/system/` per `DEPLOY.md`.
- `deploy/nginx-wordbridge.conf` — the reverse-proxy config; copied to `/etc/nginx/sites-available/` per `DEPLOY.md`. **Required, not optional** — gunicorn binds to `127.0.0.1` only and is never reachable directly. See the "known gotcha" below for why.

## Not needed on the server (harmless, just along for the ride via git clone)

- `tests/`, `scripts/`, `pytest.ini` — dev/CI only.
- `docs/`, `SPEC-*.md`, `TODO.md`, `README.md` — planning/reference docs.
- `server.sh` / `server.bat` — local dev entry points only (`python app.py`).
- `data/` — created at runtime by `app.py` (`os.makedirs`); any dev `.db` file here should never be shipped (already gitignored).

## Known gotcha: Python version

`gensim` (through at least 4.4.0) has no prebuilt wheel for Python 3.12+
and fails to compile from source against those versions — its
Cython-generated C extensions reference CPython internals (`ma_version_tag`,
`ob_digit`, `curexc_traceback`, `PyArray_Descr.subarray`) that were removed
or changed starting in 3.12. Confirmed failing on Ubuntu 26.04 (ships
Python 3.14 by default, no older `python3.1x` available via apt or
deadsnakes yet). `DEPLOY.md` covers building Python 3.11 via `pyenv` as
the workaround. If a future gensim release adds 3.12+ wheels, this whole
section (and the pyenv step in `DEPLOY.md`) can be deleted — check
`pip index versions gensim` and try a plain venv first before assuming
pyenv is still needed.

## Known gotcha: gunicorn must never be exposed directly

Confirmed in production (2026-08-22) via `py-spy dump` on a frozen
worker: a gunicorn sync worker was blocked inside its own HTTP parser,
reading from a client connection that never finished sending a request
— routine internet background noise (scanners/bots), not an attack.
With a small number of sync workers, one such stalled connection freezes
the *entire* app for every real user until gunicorn's own `--timeout`
watchdog eventually kills the whole worker (losing the loaded model,
forcing a fresh ~10-50s reload). nginx sits in front now specifically to
absorb this — it's event-driven and doesn't block on slow clients the
way a sync worker does. Don't ever change the systemd unit back to
`--bind 0.0.0.0:8000` without re-adding equivalent protection.

## Keep this current when

- A new top-level package/module gets imported by `app.py` and isn't under `wordbridge/`.
- `requirements.txt` changes (new runtime dep, or the runtime/dev deps finally get split into two files).
- The systemd unit (`deploy/wordbridge.service`) changes what it references (paths, env vars, bind address).
- `deploy/nginx-wordbridge.conf` changes (timeouts, proxy target, added TLS/domain config via certbot).
- The deploy mechanism itself changes (e.g. away from `git clone` to a real upload/staging step) — if that happens, this file's whole premise changes and needs a rewrite, not a patch.
