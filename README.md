# Wordbridge

Local word-chain game using `word2vec-google-news-300` embeddings. See `SPEC.md` for
the design and `docs/superpowers/plans/2026-08-18-wordbridge-v1.md` for the build plan.

## Setup

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    python scripts/download_model.py   # one-time, ~1.6GB download
    python app.py

Then open http://127.0.0.1:5000 in a browser.

## Tests

    pytest

Tests use small synthetic embeddings, not the real model — they run in seconds
and need no download.
