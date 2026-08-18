# Wordbridge v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local, single-player web app where you connect a start word to a target word with a chain of intermediate words, scored using real `word2vec-google-news-300` embeddings.

**Architecture:** A Flask backend holds a single in-process `WordVectorModel` (wrapping gensim `KeyedVectors`) loaded once at startup. Pure-Python `Chain` game logic (no Flask/gensim dependency) computes per-step similarity, digressions, score, and win state. Flask sessions hold the in-progress chain (serialized to/from `Chain`); completed (won) attempts are written to a local SQLite file. A small vanilla-JS frontend talks to a handful of JSON endpoints. No build step, no framework beyond Flask.

**Tech Stack:** Python 3.12, Flask, gensim (`word2vec-google-news-300`), stdlib `sqlite3`, pytest, vanilla HTML/CSS/JS.

## Global Constraints

- `word2vec-google-news-300` is a ~3.6GB in-memory model (~1.6GB compressed download via `gensim.downloader`) — load it once at process start, never per-request.
- Local-only, single-user app — no auth, no multi-user session handling.
- Win condition: last word's similarity to the target ≥ 0.7 (tunable constant).
- Score formula: `100 - (10 × chain_length) - (5 × num_digressions)`.
- Soft cap on chain length: 15 words — warn only, never hard-block further play.
- Restart clears the in-progress chain; abandoned/restarted attempts are never persisted.
- Only completed (won) attempts are persisted, to a local SQLite file.
- Project lives at `~/Code/wordbridge`, a standalone repo (not part of the billing repo).
- Automated tests must never load the real 3.6GB model — they use small synthetic `KeyedVectors` fixtures so the suite stays fast (no network, sub-second).

---

### Task 1: Project scaffolding + Flask health check

**Files:**
- Create: `requirements.txt`
- Create: `wordbridge/__init__.py`
- Create: `app.py`
- Create: `tests/conftest.py`
- Test: `tests/test_app.py`

**Interfaces:**
- Produces: `wordbridge.create_app(vector_model=None, db_path=":memory:") -> Flask` — used by every later task.

- [ ] **Step 1: Create directory structure and dependency list**

```bash
mkdir -p ~/Code/wordbridge/wordbridge ~/Code/wordbridge/tests ~/Code/wordbridge/static ~/Code/wordbridge/scripts
cd ~/Code/wordbridge
git init
```

Create `requirements.txt`:

```
flask>=3.0,<4.0
gensim>=4.3,<5.0
numpy>=1.24,<2.0
pytest>=8.0,<9.0
```

Create a virtualenv and install:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_app.py`:

```python
def test_health_check(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}
```

Create `tests/conftest.py`:

```python
import pytest

from wordbridge import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def client(app):
    return app.test_client()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_app.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'wordbridge'`

- [ ] **Step 4: Write minimal implementation**

Create `wordbridge/__init__.py`:

```python
from flask import Flask, jsonify


def create_app(vector_model=None, db_path=":memory:"):
    app = Flask(__name__, static_folder="../static", static_url_path="")
    app.config["VECTOR_MODEL"] = vector_model
    app.config["DB_PATH"] = db_path

    @app.get("/api/health")
    def health():
        return jsonify(status="ok")

    return app
```

Create `app.py`:

```python
from wordbridge import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_app.py -v`
Expected: PASS (1 passed)

- [ ] **Step 6: Commit**

```bash
git add requirements.txt wordbridge/__init__.py app.py tests/
git commit -m "feat: scaffold Flask app with health check"
```

---

### Task 2: Word vector model abstraction

**Files:**
- Create: `wordbridge/model.py`
- Modify: `tests/conftest.py` (add `tiny_model` fixture, shared by later tasks)
- Test: `tests/test_model.py`

**Interfaces:**
- Consumes: nothing project-specific (gensim `KeyedVectors` directly).
- Produces: `wordbridge.model.WordVectorModel(keyed_vectors, vocab_limit=50000)` with `.contains(word) -> bool`, `.similarity(word_a, word_b) -> float`, `.random_pair(rng=random) -> (str, str)`. Also `wordbridge.model.load_google_news_model(vocab_limit=50000) -> WordVectorModel`. Task 3 and Task 5 depend on this exact interface.

- [ ] **Step 1: Write the failing tests**

Add to `tests/conftest.py`:

```python
import numpy as np
import pytest
from gensim.models import KeyedVectors

from wordbridge import create_app
from wordbridge.model import WordVectorModel


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def tiny_model():
    kv = KeyedVectors(vector_size=3)
    words = ["cat", "dog", "car", "auto", "multi_word", "Capital"]
    vectors = np.array([
        [1.0, 0.0, 0.0],   # cat
        [0.9, 0.1, 0.0],   # dog - close to cat
        [0.0, 1.0, 0.0],   # car
        [0.0, 0.9, 0.1],   # auto - close to car
        [0.5, 0.5, 0.5],   # multi_word - should be filtered (underscore)
        [0.2, 0.2, 0.2],   # Capital - should be filtered (not lowercase-alpha)
    ])
    kv.add_vectors(words, vectors)
    return WordVectorModel(kv, vocab_limit=10)
```

Create `tests/test_model.py`:

```python
import random

from wordbridge.model import WordVectorModel


def test_contains_known_word(tiny_model):
    assert tiny_model.contains("cat") is True


def test_contains_unknown_word(tiny_model):
    assert tiny_model.contains("nonexistent") is False


def test_similarity_close_words_higher_than_far_words(tiny_model):
    close = tiny_model.similarity("cat", "dog")
    far = tiny_model.similarity("cat", "car")
    assert close > far


def test_filtered_vocab_excludes_multi_word_and_capitalized(tiny_model):
    assert "multi_word" not in tiny_model._filtered_vocab
    assert "Capital" not in tiny_model._filtered_vocab
    assert "cat" in tiny_model._filtered_vocab


def test_random_pair_returns_two_distinct_filtered_words(tiny_model):
    word_a, word_b = tiny_model.random_pair(rng=random.Random(42))
    assert word_a != word_b
    assert word_a in tiny_model._filtered_vocab
    assert word_b in tiny_model._filtered_vocab
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_model.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'wordbridge.model'`

- [ ] **Step 3: Write minimal implementation**

Create `wordbridge/model.py`:

```python
import random
import re

_TOKEN_RE = re.compile(r"^[a-z]+$")


class WordVectorModel:
    """Wraps a gensim KeyedVectors instance with the operations Wordbridge needs."""

    def __init__(self, keyed_vectors, vocab_limit=50000):
        self._kv = keyed_vectors
        self._filtered_vocab = self._build_filtered_vocab(vocab_limit)

    def _build_filtered_vocab(self, vocab_limit):
        filtered = [word for word in self._kv.index_to_key if _TOKEN_RE.match(word)]
        return filtered[:vocab_limit]

    def contains(self, word):
        return word in self._kv

    def similarity(self, word_a, word_b):
        return float(self._kv.similarity(word_a, word_b))

    def random_pair(self, rng=random):
        word_a, word_b = rng.sample(self._filtered_vocab, 2)
        return word_a, word_b


def load_google_news_model(vocab_limit=50000):
    import gensim.downloader as api

    keyed_vectors = api.load("word2vec-google-news-300")
    return WordVectorModel(keyed_vectors, vocab_limit=vocab_limit)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_model.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add wordbridge/model.py tests/conftest.py tests/test_model.py
git commit -m "feat: add WordVectorModel wrapping gensim KeyedVectors"
```

---

### Task 3: Chain game logic

**Files:**
- Create: `wordbridge/game.py`
- Test: `tests/test_game.py`

**Interfaces:**
- Consumes: `WordVectorModel.contains(word) -> bool`, `WordVectorModel.similarity(a, b) -> float` (Task 2).
- Produces: `wordbridge.game.Step` (dataclass: `word, neighbor_similarity, target_similarity, is_digression`) and `wordbridge.game.Chain(model, start_word, target_word, threshold=0.7, soft_cap=15)` with `.add_word(word) -> Step` (raises `ValueError` if word not in model), `.is_won() -> bool`, `.is_over_soft_cap() -> bool`, `.num_digressions() -> int`, `.score() -> int`, `.restart() -> None`. Task 4 and Task 5 depend on this exact interface (including `.to_dict()`/`.from_dict()` added in Task 5).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_game.py`:

```python
import pytest

from wordbridge.game import Chain


def test_add_word_computes_similarities(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.99)
    step = chain.add_word("dog")
    assert step.word == "dog"
    assert step.neighbor_similarity == pytest.approx(tiny_model.similarity("dog", "cat"))
    assert step.target_similarity == pytest.approx(tiny_model.similarity("dog", "auto"))


def test_digression_detected_when_target_similarity_drops(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.99)
    chain.add_word("car")   # much closer to target than the cat->auto baseline
    step = chain.add_word("dog")  # further from target than car was -> digression
    assert step.is_digression is True


def test_add_word_rejects_unknown_word(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto")
    with pytest.raises(ValueError):
        chain.add_word("nonexistent")


def test_is_won_when_target_similarity_meets_threshold(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.5)
    assert chain.is_won() is False
    chain.add_word("auto")
    assert chain.is_won() is True


def test_score_penalizes_length_and_digressions(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.99)
    chain.add_word("car")
    chain.add_word("dog")  # digression, per test above
    assert chain.score() == 100 - (10 * 2) - (5 * 1)


def test_is_over_soft_cap(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto", soft_cap=1)
    chain.add_word("car")
    assert chain.is_over_soft_cap() is False
    chain.add_word("dog")
    assert chain.is_over_soft_cap() is True


def test_restart_clears_steps(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto")
    chain.add_word("car")
    chain.restart()
    assert chain.steps == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_game.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'wordbridge.game'`

- [ ] **Step 3: Write minimal implementation**

Create `wordbridge/game.py`:

```python
from dataclasses import dataclass


@dataclass
class Step:
    word: str
    neighbor_similarity: float
    target_similarity: float
    is_digression: bool


class Chain:
    def __init__(self, model, start_word, target_word, threshold=0.7, soft_cap=15):
        self._model = model
        self.start_word = start_word
        self.target_word = target_word
        self.threshold = threshold
        self.soft_cap = soft_cap
        self.steps = []

    def add_word(self, word):
        if not self._model.contains(word):
            raise ValueError(f"'{word}' is not a recognized word")

        previous_word = self.steps[-1].word if self.steps else self.start_word
        previous_target_similarity = (
            self.steps[-1].target_similarity
            if self.steps
            else self._model.similarity(self.start_word, self.target_word)
        )

        neighbor_similarity = self._model.similarity(word, previous_word)
        target_similarity = self._model.similarity(word, self.target_word)
        is_digression = target_similarity < previous_target_similarity

        step = Step(word, neighbor_similarity, target_similarity, is_digression)
        self.steps.append(step)
        return step

    def is_won(self):
        return bool(self.steps) and self.steps[-1].target_similarity >= self.threshold

    def is_over_soft_cap(self):
        return len(self.steps) > self.soft_cap

    def num_digressions(self):
        return sum(1 for step in self.steps if step.is_digression)

    def score(self):
        return 100 - (10 * len(self.steps)) - (5 * self.num_digressions())

    def restart(self):
        self.steps = []
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_game.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add wordbridge/game.py tests/test_game.py
git commit -m "feat: add Chain game logic with scoring and digression detection"
```

---

### Task 4: SQLite persistence for completed attempts

**Files:**
- Create: `wordbridge/db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: `Chain.start_word, Chain.target_word, Chain.steps, Chain.num_digressions(), Chain.score()` (Task 3).
- Produces: `wordbridge.db.init_db(db_path) -> sqlite3.Connection`, `wordbridge.db.save_attempt(conn, chain) -> None`, `wordbridge.db.list_attempts(conn) -> list[dict]`. Task 5 depends on this exact interface.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_db.py`:

```python
from wordbridge.db import init_db, list_attempts, save_attempt
from wordbridge.game import Chain


def test_init_db_creates_attempts_table():
    conn = init_db(":memory:")
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='attempts'"
    )
    assert cursor.fetchone() is not None


def test_save_and_list_attempt(tiny_model):
    conn = init_db(":memory:")
    chain = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.5)
    chain.add_word("auto")

    save_attempt(conn, chain)
    attempts = list_attempts(conn)

    assert len(attempts) == 1
    assert attempts[0]["start_word"] == "cat"
    assert attempts[0]["target_word"] == "auto"
    assert attempts[0]["chain"] == ["auto"]
    assert attempts[0]["score"] == chain.score()


def test_list_attempts_orders_most_recent_first(tiny_model):
    conn = init_db(":memory:")
    first = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.5)
    first.add_word("auto")
    save_attempt(conn, first)

    second = Chain(tiny_model, start_word="car", target_word="dog", threshold=0.01)
    second.add_word("dog")
    save_attempt(conn, second)

    attempts = list_attempts(conn)
    assert attempts[0]["start_word"] == "car"
    assert attempts[1]["start_word"] == "cat"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_db.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'wordbridge.db'`

- [ ] **Step 3: Write minimal implementation**

Create `wordbridge/db.py`:

```python
import json
import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_word TEXT NOT NULL,
    target_word TEXT NOT NULL,
    chain_json TEXT NOT NULL,
    num_digressions INTEGER NOT NULL,
    score INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
"""


def init_db(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute(SCHEMA)
    conn.commit()
    return conn


def save_attempt(conn, chain):
    conn.execute(
        """
        INSERT INTO attempts (start_word, target_word, chain_json, num_digressions, score, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            chain.start_word,
            chain.target_word,
            json.dumps([step.word for step in chain.steps]),
            chain.num_digressions(),
            chain.score(),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()


def list_attempts(conn):
    rows = conn.execute(
        "SELECT id, start_word, target_word, chain_json, num_digressions, score, created_at "
        "FROM attempts ORDER BY id DESC"
    ).fetchall()
    return [
        {
            "id": row[0],
            "start_word": row[1],
            "target_word": row[2],
            "chain": json.loads(row[3]),
            "num_digressions": row[4],
            "score": row[5],
            "created_at": row[6],
        }
        for row in rows
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_db.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add wordbridge/db.py tests/test_db.py
git commit -m "feat: persist completed attempts to SQLite"
```

---

### Task 5: Flask routes wiring game + persistence together

**Files:**
- Modify: `wordbridge/game.py` (add `Chain.to_dict()` / `Chain.from_dict()` for session serialization)
- Create: `wordbridge/routes.py`
- Modify: `wordbridge/__init__.py` (register blueprint, add `secret_key` param, drop inline health route)
- Modify: `tests/conftest.py` (`app` fixture now injects `tiny_model`)
- Test: `tests/test_routes.py`

**Interfaces:**
- Consumes: `WordVectorModel` (Task 2), `Chain`/`Step` (Task 3), `init_db`/`save_attempt`/`list_attempts` (Task 4).
- Produces: HTTP API — `POST /api/game/new`, `POST /api/game/word`, `POST /api/game/restart`, `GET /api/history`, `GET /api/health` — consumed by the frontend in Task 6.

- [ ] **Step 1: Add session serialization to Chain**

Add to `wordbridge/game.py` (inside the `Chain` class, and `Step` import already present):

```python
    def to_dict(self):
        return {
            "start_word": self.start_word,
            "target_word": self.target_word,
            "threshold": self.threshold,
            "soft_cap": self.soft_cap,
            "steps": [
                {
                    "word": step.word,
                    "neighbor_similarity": step.neighbor_similarity,
                    "target_similarity": step.target_similarity,
                    "is_digression": step.is_digression,
                }
                for step in self.steps
            ],
        }

    @classmethod
    def from_dict(cls, model, data):
        chain = cls(
            model,
            start_word=data["start_word"],
            target_word=data["target_word"],
            threshold=data["threshold"],
            soft_cap=data["soft_cap"],
        )
        chain.steps = [Step(**step) for step in data["steps"]]
        return chain
```

- [ ] **Step 2: Update conftest.py's `app` fixture to inject tiny_model**

Change in `tests/conftest.py`:

```python
@pytest.fixture
def app(tiny_model):
    return create_app(vector_model=tiny_model, db_path=":memory:", secret_key="test-secret")
```

- [ ] **Step 3: Write the failing tests**

Create `tests/test_routes.py`:

```python
def test_new_game_random_mode_returns_word_pair(client):
    response = client.post("/api/game/new", json={"mode": "random"})
    assert response.status_code == 200
    data = response.get_json()
    assert data["start_word"] != data["target_word"]


def test_new_game_manual_mode_rejects_unknown_word(client):
    response = client.post(
        "/api/game/new",
        json={"mode": "manual", "word1": "cat", "word2": "nonexistent"},
    )
    assert response.status_code == 400


def test_new_game_manual_mode_accepts_known_words(client):
    response = client.post(
        "/api/game/new",
        json={"mode": "manual", "word1": "cat", "word2": "auto"},
    )
    assert response.status_code == 200
    assert response.get_json() == {"start_word": "cat", "target_word": "auto"}


def test_add_word_without_active_game_returns_error(client):
    response = client.post("/api/game/word", json={"word": "dog"})
    assert response.status_code == 400


def test_add_word_progresses_chain_and_persists_on_win(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    response = client.post("/api/game/word", json={"word": "auto"})
    data = response.get_json()

    assert response.status_code == 200
    assert data["won"] is True
    assert data["score"] == 90  # 100 - 10*1 - 5*0

    history_response = client.get("/api/history")
    attempts = history_response.get_json()["attempts"]
    assert len(attempts) == 1
    assert attempts[0]["target_word"] == "auto"


def test_restart_clears_chain(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/word", json={"word": "car"})
    response = client.post("/api/game/restart")
    assert response.get_json() == {"start_word": "cat", "target_word": "auto"}
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/test_routes.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'wordbridge.routes'`

- [ ] **Step 5: Write minimal implementation**

Create `wordbridge/routes.py`:

```python
from flask import Blueprint, current_app, jsonify, request, session

from .db import init_db, list_attempts, save_attempt
from .game import Chain

bp = Blueprint("routes", __name__)


def _get_model():
    return current_app.config["VECTOR_MODEL"]


def _get_db_conn():
    if "_db_conn" not in current_app.config:
        current_app.config["_db_conn"] = init_db(current_app.config["DB_PATH"])
    return current_app.config["_db_conn"]


@bp.get("/api/health")
def health():
    return jsonify(status="ok")


@bp.post("/api/game/new")
def new_game():
    model = _get_model()
    payload = request.get_json(force=True) or {}
    mode = payload.get("mode", "random")

    if mode == "manual":
        word1 = payload.get("word1", "").strip().lower()
        word2 = payload.get("word2", "").strip().lower()
        if not model.contains(word1):
            return jsonify(error=f"'{word1}' is not a recognized word"), 400
        if not model.contains(word2):
            return jsonify(error=f"'{word2}' is not a recognized word"), 400
        start_word, target_word = word1, word2
    else:
        start_word, target_word = model.random_pair()

    chain = Chain(model, start_word=start_word, target_word=target_word)
    session["chain"] = chain.to_dict()

    return jsonify(start_word=start_word, target_word=target_word)


@bp.post("/api/game/word")
def add_word():
    model = _get_model()
    if "chain" not in session:
        return jsonify(error="No game in progress"), 400

    chain = Chain.from_dict(model, session["chain"])
    payload = request.get_json(force=True) or {}
    word = payload.get("word", "").strip().lower()

    try:
        step = chain.add_word(word)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    session["chain"] = chain.to_dict()

    won = chain.is_won()
    if won:
        save_attempt(_get_db_conn(), chain)

    return jsonify(
        word=step.word,
        neighbor_similarity=step.neighbor_similarity,
        target_similarity=step.target_similarity,
        is_digression=step.is_digression,
        score=chain.score(),
        won=won,
        over_soft_cap=chain.is_over_soft_cap(),
    )


@bp.post("/api/game/restart")
def restart_game():
    model = _get_model()
    if "chain" not in session:
        return jsonify(error="No game in progress"), 400

    chain = Chain.from_dict(model, session["chain"])
    chain.restart()
    session["chain"] = chain.to_dict()

    return jsonify(start_word=chain.start_word, target_word=chain.target_word)


@bp.get("/api/history")
def history():
    return jsonify(attempts=list_attempts(_get_db_conn()))
```

Replace `wordbridge/__init__.py` entirely with:

```python
from flask import Flask


def create_app(vector_model=None, db_path=":memory:", secret_key="dev-secret-key"):
    app = Flask(__name__, static_folder="../static", static_url_path="")
    app.config["VECTOR_MODEL"] = vector_model
    app.config["DB_PATH"] = db_path
    app.secret_key = secret_key

    from .routes import bp as routes_bp

    app.register_blueprint(routes_bp)

    return app
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/ -v`
Expected: PASS (all tests across test_app.py, test_model.py, test_game.py, test_db.py, test_routes.py)

- [ ] **Step 7: Commit**

```bash
git add wordbridge/game.py wordbridge/routes.py wordbridge/__init__.py tests/conftest.py tests/test_routes.py
git commit -m "feat: wire Flask routes for game session and persisted history"
```

---

### Task 6: Frontend UI

**Files:**
- Modify: `wordbridge/routes.py` (add `/` route serving `index.html`)
- Create: `static/index.html`
- Create: `static/app.js`
- Create: `static/style.css`
- Test: `tests/test_static.py`

**Interfaces:**
- Consumes: the API from Task 5 (`/api/game/new`, `/api/game/word`, `/api/game/restart`, `/api/history`).
- Produces: nothing consumed by later tasks (this is the UI leaf).

- [ ] **Step 1: Write the failing test**

Create `tests/test_static.py`:

```python
def test_index_page_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Wordbridge" in response.data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_static.py -v`
Expected: FAIL with 404 (no route for `/` yet)

- [ ] **Step 3: Write minimal implementation**

Add to `wordbridge/routes.py`:

```python
@bp.get("/")
def index():
    return current_app.send_static_file("index.html")
```

Create `static/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Wordbridge</title>
  <link rel="stylesheet" href="/style.css">
</head>
<body>
  <h1>Wordbridge</h1>

  <section id="setup">
    <button id="random-btn">Random pair</button>
    <input id="word1-input" placeholder="start word">
    <input id="word2-input" placeholder="target word">
    <button id="manual-btn">Use these words</button>
  </section>

  <section id="game" hidden>
    <p>Connect <strong id="start-word"></strong> to <strong id="target-word"></strong></p>
    <ol id="chain-list"></ol>
    <input id="word-input" placeholder="next word">
    <button id="add-word-btn">Add word</button>
    <button id="restart-btn">Restart</button>
    <p id="score"></p>
    <p id="status"></p>
  </section>

  <script src="/app.js"></script>
</body>
</html>
```

Create `static/app.js`:

```javascript
const setupSection = document.getElementById("setup");
const gameSection = document.getElementById("game");
const startWordEl = document.getElementById("start-word");
const targetWordEl = document.getElementById("target-word");
const chainList = document.getElementById("chain-list");
const scoreEl = document.getElementById("score");
const statusEl = document.getElementById("status");

async function postJSON(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "Request failed");
  }
  return data;
}

function showGame(startWord, targetWord) {
  startWordEl.textContent = startWord;
  targetWordEl.textContent = targetWord;
  chainList.innerHTML = "";
  scoreEl.textContent = "";
  statusEl.textContent = "";
  setupSection.hidden = true;
  gameSection.hidden = false;
}

document.getElementById("random-btn").addEventListener("click", async () => {
  const data = await postJSON("/api/game/new", { mode: "random" });
  showGame(data.start_word, data.target_word);
});

document.getElementById("manual-btn").addEventListener("click", async () => {
  const word1 = document.getElementById("word1-input").value.trim();
  const word2 = document.getElementById("word2-input").value.trim();
  try {
    const data = await postJSON("/api/game/new", { mode: "manual", word1, word2 });
    showGame(data.start_word, data.target_word);
  } catch (err) {
    statusEl.textContent = err.message;
  }
});

document.getElementById("add-word-btn").addEventListener("click", async () => {
  const input = document.getElementById("word-input");
  const word = input.value.trim();
  try {
    const data = await postJSON("/api/game/word", { word });
    const li = document.createElement("li");
    li.textContent = `${data.word} (neighbor: ${data.neighbor_similarity.toFixed(2)}, target: ${data.target_similarity.toFixed(2)})${data.is_digression ? " ⚠ digression" : ""}`;
    chainList.appendChild(li);
    scoreEl.textContent = `Score: ${data.score}`;
    input.value = "";

    if (data.won) {
      statusEl.textContent = "You connected the words!";
    } else if (data.over_soft_cap) {
      statusEl.textContent = "Chain is getting long — score is dropping fast.";
    } else {
      statusEl.textContent = "";
    }
  } catch (err) {
    statusEl.textContent = err.message;
  }
});

document.getElementById("restart-btn").addEventListener("click", async () => {
  const data = await postJSON("/api/game/restart");
  showGame(data.start_word, data.target_word);
});
```

Create `static/style.css`:

```css
body {
  font-family: sans-serif;
  max-width: 40rem;
  margin: 2rem auto;
  padding: 0 1rem;
}

#chain-list li {
  margin-bottom: 0.25rem;
}

#status {
  font-weight: bold;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_static.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Manual verification**

This uses the fast in-memory test model, not the full download — run:

```bash
python3 -c "
from wordbridge import create_app
from wordbridge.model import WordVectorModel
from gensim.models import KeyedVectors
import numpy as np

kv = KeyedVectors(vector_size=3)
kv.add_vectors(['cat', 'dog', 'car', 'auto'], np.array([[1,0,0],[0.9,0.1,0],[0,1,0],[0,0.9,0.1]]))
model = WordVectorModel(kv, vocab_limit=10)
app = create_app(vector_model=model, db_path=':memory:', secret_key='dev')
app.run(debug=True)
"
```

Open http://127.0.0.1:5000, click "Use these words" with `cat` / `auto`, type `auto` into the word input and click "Add word". Confirm the chain list shows the step with similarity numbers, the score reads `Score: 90`, and the status shows "You connected the words!". Click Restart and confirm the chain list clears.

- [ ] **Step 6: Commit**

```bash
git add wordbridge/routes.py static/ tests/test_static.py
git commit -m "feat: add vanilla JS frontend for playing a chain"
```

---

### Task 7: Wire in the real word2vec-google-news-300 model

**Files:**
- Create: `scripts/download_model.py`
- Modify: `app.py` (load the real model at startup, use a real SQLite file)
- Create: `.gitignore`
- Create: `README.md`

**Interfaces:**
- Consumes: `wordbridge.model.load_google_news_model()` (Task 2), `wordbridge.create_app()` (Task 1/5).
- Produces: nothing (this is the final integration task).

- [ ] **Step 1: Create the one-time model download script**

Create `scripts/download_model.py`:

```python
"""One-time download of word2vec-google-news-300 into gensim's local cache.

Run this once before starting the app for the first time:
    python scripts/download_model.py
"""
import gensim.downloader as api


def main():
    print("Downloading word2vec-google-news-300 (~1.6GB)... this can take a few minutes.")
    api.load("word2vec-google-news-300")
    print("Done. The model is cached locally; app.py will still take ~30-60s to load it into RAM on each run.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Wire the real model and a real DB file into app.py**

Replace `app.py` entirely with:

```python
import os

from wordbridge import create_app
from wordbridge.model import load_google_news_model

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "wordbridge.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

print("Loading word2vec-google-news-300 into memory (this can take 30-60s)...")
vector_model = load_google_news_model()
print("Model loaded.")

app = create_app(vector_model=vector_model, db_path=DB_PATH, secret_key=os.urandom(24))

if __name__ == "__main__":
    app.run(debug=True)
```

- [ ] **Step 3: Add .gitignore and README**

Create `.gitignore`:

```
__pycache__/
*.pyc
.venv/
venv/
data/*.db
```

Create `README.md`:

```markdown
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
```

- [ ] **Step 4: Run the fast test suite to confirm nothing broke**

Run: `pytest -v`
Expected: PASS (all tests) — `app.py` is never imported by the tests, so this still runs in seconds without touching the real model.

- [ ] **Step 5: Manual end-to-end verification with the real model**

```bash
python scripts/download_model.py   # first time only
python app.py
```

Confirm the console prints "Loading word2vec-google-news-300 into memory..." then "Model loaded." before the Flask dev server starts. Open http://127.0.0.1:5000, click "Random pair", and build a chain to a win. Confirm the similarity scores look sensible for real English words, the score updates as you add words, and after a win `GET /api/history` (or a page refresh once a history view exists) reflects the completed attempt.

- [ ] **Step 6: Commit**

```bash
git add scripts/download_model.py app.py .gitignore README.md
git commit -m "feat: load real word2vec-google-news-300 model and add setup docs"
```
