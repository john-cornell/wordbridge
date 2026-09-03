# Deploy manifest (for Claude / future maintainers)

Deployment works by `git clone`-ing the whole repo onto the server (see
`../DEPLOY.md`), so nothing here is enforced by tooling — this file is just
the canonical list of what actually matters once it's there. **Whenever a
change touches what runs in production, update this file in the same
change**, not as an afterthought.

## Required in production

- `app.py` — entry point; loads the model and builds the `app:app` object gunicorn serves.
- `wordbridge/` — the actual application package (routes, game logic, model wrapper, db).
- `static/` — served directly by Flask (`index.html`, `scores.html`, `app.js`, `graph.js`, `scores.js`, `version.js`, `style.css`).
- `requirements.txt` — pinned deps. **Currently unsplit**: `flask`, `gensim`, `numpy`, `gunicorn` are the real runtime deps; `pytest` and `playwright` are dev/test-only but still get installed on the server today because there's one shared file. Fine for a toy app's install size — flag it if that ever needs to change.
- `deploy/wordbridge.service` — the systemd unit; copied to `/etc/systemd/system/` per `DEPLOY.md`.
- `deploy/nginx-wordbridge.conf` — the reverse-proxy config; copied to `/etc/nginx/sites-available/` per `DEPLOY.md`. **Required, not optional** — gunicorn binds to `127.0.0.1` only and is never reachable directly. See the "known gotcha" below for why.

## Known gotcha: fireworks-js is loaded from a CDN, not self-hosted

`index.html` loads `fireworks-js` (win-celebration animation) from
`cdn.jsdelivr.net`, pinned to an exact version with a Subresource
Integrity hash — this is the app's only external runtime dependency;
every other script (`app.js`, `graph.js`, `scores.js`, `version.js`) is
self-hosted. If that CDN request ever fails (outage, firewall, ad-blocker,
offline demo), `app.js` guards against it (`typeof Fireworks !== "undefined"`)
so the rest of the game keeps working with no fireworks, rather than the
whole script crashing on load. **If you touch this again, keep that guard**
— an earlier version of this feature had no guard, and a failed CDN load
would have thrown before any of the game's own button/event wiring ran,
taking down the entire page over a purely cosmetic feature. Bump both the
version in the `src` URL and the `integrity` hash together if upgrading;
jsdelivr publishes hashes at `https://data.jsdelivr.com/v1/packages/npm/fireworks-js@<version>?structure=flat`.

## Known gotcha: canvas-confetti's pinned URL is jsdelivr auto-minified, not a published file

`index.html` also loads `canvas-confetti` from `cdn.jsdelivr.net` (crying-face
confetti on a loss, same guard pattern as fireworks:
`typeof confetti === "undefined"`). Unlike `fireworks-js`, the npm package
for `canvas-confetti` does **not** ship a `dist/confetti.browser.min.js`
file — only `dist/confetti.browser.js` (unminified). The pinned `.min.js`
URL still resolves (HTTP 200) because jsdelivr auto-minifies on the fly for
any npm file requested with a `.min.js` suffix that doesn't exist verbatim.
That means jsdelivr's own hash-lookup API
(`https://data.jsdelivr.com/v1/packages/npm/canvas-confetti@<version>?structure=flat`)
**will not list this file or its hash** — if you bump the version, you must
download the exact pinned URL directly and compute the SRI hash from those
bytes yourself (`openssl dgst -sha384 -binary <file> | openssl base64 -A`),
the same as was done to pin it originally. Don't trust a hash you didn't
compute from the exact URL being served.

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

## Known gotcha: this repo's nginx config vs. certbot's live edits

`certbot --nginx` edits the *live* `/etc/nginx/sites-available/wordbridge`
file in place (adds the `listen 443 ssl` block, cert paths, the HTTP→HTTPS
redirect server block) — none of that was ever captured back into this
repo automatically. On 2026-08-23 a plain `cp` of the repo's (still
HTTP-only) `deploy/nginx-wordbridge.conf` over the live file during an
unrelated redeploy silently reverted the site to HTTP-only, and the loss
wasn't noticed until a user reported it. Fixed by pulling the real
certbot-generated config (`sudo cat /etc/nginx/sites-available/wordbridge`)
back into this file so it now matches production exactly, including the
`# managed by Certbot` blocks — a future `cp` of this file reproduces the
live TLS state instead of erasing it.

**If you ever edit this file again**: after copying it to the server, run
`sudo certbot --nginx -d wordbridge.monkeyskin.au` afterward regardless of
whether TLS looks like it's already there — it's safe (reuses the existing
cert, doesn't request or renew one, as long as it's still within its
validity window) and guarantees the `# managed by Certbot` blocks are
correct for whatever you just changed.

## Known gotcha: gensim's downloader can poison its own cache

`load_google_news_model()` used to call `api.load(..., return_path=True)`
just to resolve a path to the already-cached model file. That still makes
gensim's downloader do an unconditional network fetch of its remote
dataset catalog on *every single worker boot* — and `_load_info()` only
falls back to its own local cache file (`~/gensim-data/information.json`)
on a network *exception*, not on a "succeeded but empty" response. On
2026-08-24, one bad response overwrote that cache file with empty
content, and every subsequent boot crashed with a `JSONDecodeError`
(gunicorn crash-looping workers, nginx serving 502s) until someone
manually deleted the corrupted file. Fixed by checking the well-known,
fixed cache path (`~/gensim-data/word2vec-google-news-300/word2vec-google-news-300.gz`)
directly first, and only touching the network at all on a genuinely fresh
install with nothing downloaded yet. If this ever needs a true fresh
download again (new server, cache wiped), that first boot will be slower
and does need working network access - after that, boots never touch the
network again.

## Known gotcha: the session is a client-side cookie with a ~4KB limit

Flask's default session backend signs and stores the *entire* session in a
browser cookie - there's no server-side session store here. `Chain.to_dict()`
gets serialized into that cookie on every single request while a game is
in progress. On 2026-08-24, adding the full solver search trace
(`solution_trace` - many hops x many candidates each, easily tens of KB)
to that dict blew the cookie past browsers' ~4093-byte limit. Browsers
silently drop cookies over that limit rather than erroring, so this
didn't fail loudly - games just randomly lost their session mid-play
("No game in progress" / a generic server error), with `UserWarning: The
'session' cookie is too large` buried in the gunicorn journal log as the
only clue. Fixed by never putting `solution_trace` in the session at all;
it's recomputed fresh, once, only at the moment a game is actually won
and saved (see `_apply_step_and_check_win` in `routes.py`).

**If you add anything to `Chain.to_dict()`/`session["chain"]` in the
future**: keep it small (a handful of words/numbers, not search results,
candidate lists, or anything that scales with search breadth) or it needs
the same "compute on demand instead of carrying in session" treatment.

## Confirming a deploy actually landed

`GET /api/health` returns `{"status": "ok", "version": "<short git hash>"}`,
and both pages show that same hash as a small muted footer
(`wordbridge/version.py` shells out to `git rev-parse --short HEAD` against
the checkout at startup — no manual version bump to remember, and it can't
drift from what's actually deployed since this is a real `git pull`
checkout, not a copy). After running the update steps in `DEPLOY.md` §4,
check the footer (or `curl 127.0.0.1:8000/api/health`) matches the commit
you just pushed, rather than assuming the restart picked it up. Falls back
to `"unknown"` if `git` isn't available or the checkout somehow has no
`.git` — that itself is a signal something about the deploy is unusual.

**Standard deploy + confirm, for a change that touched Python code:**
```bash
cd /opt/wordbridge
sudo -u wordbridge git pull
sudo systemctl restart wordbridge
sleep 60
curl -s http://127.0.0.1:8000/api/health
```
The `sleep 60` before the `curl` matters — loading the word2vec model takes
30-60s per worker on every boot (see `app.py`'s own startup log line), and
`curl`ing before that finishes just hits "connection refused" rather than
a real answer, which reads as a failed deploy when it's actually still
booting. Skip the sleep only for a change that's purely static assets
(HTML/CSS/JS, no `.py` files) or docs — those don't need `systemctl restart`
at all, since Flask serves them straight off disk on every request.

**Aliases already set up on the VPS** (the `ubuntu` user's shell config —
not tracked in this repo, just documented here so they aren't forgotten):
```bash
alias wbcheck='curl -m 5 http://127.0.0.1:8000/api/health'
alias wblogs='sudo journalctl -u wordbridge -n 100 --no-pager'
alias wbrestart='sudo systemctl restart wordbridge'
alias wbstatus='sudo systemctl status wordbridge'
alias wbtail='sudo journalctl -u wordbridge -f'

# Function, not a plain alias, since it's a multi-step sequence - the
# standard deploy+confirm block above, chained together.
wbdeploy() {
  cd /opt/wordbridge || return
  sudo -u wordbridge git pull
  sudo systemctl restart wordbridge
  sleep 60
  wbcheck
}
```

## Keep this current when

- A new top-level package/module gets imported by `app.py` and isn't under `wordbridge/`.
- `requirements.txt` changes (new runtime dep, or the runtime/dev deps finally get split into two files).
- The systemd unit (`deploy/wordbridge.service`) changes what it references (paths, env vars, bind address).
- `deploy/nginx-wordbridge.conf` changes (timeouts, proxy target, added TLS/domain config via certbot).
- The deploy mechanism itself changes (e.g. away from `git clone` to a real upload/staging step) — if that happens, this file's whole premise changes and needs a rewrite, not a patch. It would also break `wordbridge/version.py`'s assumption that the checkout has a working `.git` directory to read from.
