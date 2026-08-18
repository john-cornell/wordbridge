# Pairwise Similarity Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the chain graph's "only consecutive words" edge model with a full pairwise model — every word connects to every other word based on direct similarity — fixing the target-connectivity gap found in play, and folding in two physics/rendering fixes flagged by the chain-graph-view feature's final review.

**Architecture:** `Chain.add_word()` (backend) computes the newly added word's similarity to every other word already in the chain and returns it as a `similarities` list on the API response. `ChainGraph.addStep()` (frontend) creates one edge per entry in that list (instead of one edge to the previous word), using a word-text→node-id index to resolve targets. The old exact-string-match win special case is removed — a win is now just a regular word whose similarity to the target happens to be ~1.0. While rewriting the edge/physics code anyway, normalize the edge width/opacity encoding against the live visible-similarity range (previously flat at real-world values) and add a weak centering force (previously unconnected nodes drifted to the canvas edges and stuck).

**Tech Stack:** Python (Flask, existing `WordVectorModel.similarity`), vanilla JS (existing `ChainGraph`), Playwright (new, dev-only — drives a real browser for a committed regression script; does not touch the page itself, so it doesn't violate the "no external JS libraries" constraint).

## Global Constraints

- `POST /api/game/word`'s response gains a new field, `similarities`: a list of `{"word": ..., "similarity": ...}` entries, one per OTHER word currently in the chain (start, target, every prior step) — for the just-added word only. Existing fields (`neighbor_similarity`, `target_similarity`, `is_digression`, `score`, `won`, `over_soft_cap`) are unchanged.
- No change to scoring, win condition, or digression detection logic in `wordbridge/game.py`.
- Every word (start, target, every added word) gets a candidate edge to every OTHER word based on direct similarity — the old "only consecutive words" model, and the exact-string-match win special case built for it, are both removed.
- Edge visibility rule is unchanged: an edge is shown iff `similarity >= threshold`.
- Edge width/opacity must be normalized against the live range of currently-visible edge similarities, not a flat `[0,1]` domain.
- A weak centering force must pull unpinned, non-dragged nodes toward the canvas center.
- Vanilla JS/HTML/CSS only for the game itself, no build step, no external libraries shipped to the page. Playwright is an explicitly-allowed exception: a dev-only browser-automation tool for a committed verification script, not a page dependency.

---

### Task 1: Backend — pairwise similarities on the API response

**Files:**
- Modify: `wordbridge/game.py`
- Modify: `wordbridge/routes.py`
- Test: `tests/test_game.py`
- Test: `tests/test_routes.py`

**Interfaces:**
- Produces: `Step.similarities` (a `list[dict]`, each `{"word": str, "similarity": float}`), included in `Chain.to_dict()`/`from_dict()` and in `POST /api/game/word`'s JSON response. Task 2 (frontend) consumes this exact shape.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_game.py`:

```python
def test_add_word_records_similarities_to_every_other_word(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto", threshold=0.99)
    chain.add_word("car")
    step = chain.add_word("dog")

    similarities_by_word = {entry["word"]: entry["similarity"] for entry in step.similarities}
    assert similarities_by_word["cat"] == pytest.approx(tiny_model.similarity("dog", "cat"))
    assert similarities_by_word["auto"] == pytest.approx(tiny_model.similarity("dog", "auto"))
    assert similarities_by_word["car"] == pytest.approx(tiny_model.similarity("dog", "car"))
    assert len(step.similarities) == 3


def test_first_word_similarities_cover_only_start_and_target(tiny_model):
    chain = Chain(tiny_model, start_word="cat", target_word="auto")
    step = chain.add_word("car")
    words_compared = {entry["word"] for entry in step.similarities}
    assert words_compared == {"cat", "auto"}
```

Add to `tests/test_routes.py`:

```python
def test_add_word_response_includes_similarities_to_other_chain_words(client):
    client.post("/api/game/new", json={"mode": "manual", "word1": "cat", "word2": "auto"})
    client.post("/api/game/word", json={"word": "car"})
    response = client.post("/api/game/word", json={"word": "dog"})
    data = response.get_json()

    assert "similarities" in data
    words_compared = {entry["word"] for entry in data["similarities"]}
    assert words_compared == {"cat", "auto", "car"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_game.py tests/test_routes.py -v`
Expected: FAIL — `Step.__init__() missing 1 required positional argument: 'similarities'` (or similar) since `Step`/`add_word` don't produce this field yet.

- [ ] **Step 3: Update `wordbridge/game.py`**

Replace `wordbridge/game.py` entirely with:

```python
from dataclasses import dataclass


@dataclass
class Step:
    word: str
    neighbor_similarity: float
    target_similarity: float
    is_digression: bool
    similarities: list


class Chain:
    def __init__(self, model, start_word, target_word, threshold=0.7, soft_cap=15):
        self._model = model
        self.start_word = start_word
        self.target_word = target_word
        self.threshold = threshold
        self.soft_cap = soft_cap
        self.steps = []
        self.completed = False

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

        other_words = [self.start_word, self.target_word] + [s.word for s in self.steps]
        similarities = [
            {"word": other, "similarity": self._model.similarity(word, other)}
            for other in other_words
        ]

        step = Step(word, neighbor_similarity, target_similarity, is_digression, similarities)
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
        self.completed = False

    def mark_completed(self):
        self.completed = True

    def to_dict(self):
        return {
            "start_word": self.start_word,
            "target_word": self.target_word,
            "threshold": self.threshold,
            "soft_cap": self.soft_cap,
            "completed": self.completed,
            "steps": [
                {
                    "word": step.word,
                    "neighbor_similarity": step.neighbor_similarity,
                    "target_similarity": step.target_similarity,
                    "is_digression": step.is_digression,
                    "similarities": step.similarities,
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
        chain.completed = data.get("completed", False)
        return chain
```

- [ ] **Step 4: Update `wordbridge/routes.py`'s `add_word` response**

In `wordbridge/routes.py`, find the `add_word` route's `return jsonify(...)` call and add a `similarities=step.similarities` argument:

```python
    return jsonify(
        word=step.word,
        neighbor_similarity=step.neighbor_similarity,
        target_similarity=step.target_similarity,
        is_digression=step.is_digression,
        similarities=step.similarities,
        score=chain.score(),
        won=won,
        over_soft_cap=chain.is_over_soft_cap(),
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_game.py tests/test_routes.py -v`
Expected: PASS (all tests in both files)

- [ ] **Step 6: Run the full suite**

Run: `pytest -v`
Expected: PASS (all tests — this task only touches `game.py`/`routes.py`, `db.py` is untouched since it only ever reads `step.word`)

- [ ] **Step 7: Commit**

```bash
git add wordbridge/game.py wordbridge/routes.py tests/test_game.py tests/test_routes.py
git commit -m "feat: return pairwise word similarities from the add-word API"
```

---

### Task 2: Frontend — pairwise edges, normalized encoding, centering force

**Files:**
- Modify: `static/graph.js`

**Interfaces:**
- Consumes: `step.similarities` (Task 1) — a `list[{"word": str, "similarity": float}]`.
- Produces: nothing new consumed elsewhere — `ChainGraph`'s public interface (`reset`, `addStep`, `setThreshold`) is unchanged; only its internals change. Task 3's verification script drives this through the DOM, not through JS APIs.

- [ ] **Step 1: Replace `static/graph.js` entirely**

```javascript
const SVG_NS = "http://www.w3.org/2000/svg";
const NODE_RADIUS = 22;
const PADDING = 40;
const MIN_EDGE_WIDTH = 1;
const MAX_EDGE_WIDTH = 6;
const MIN_EDGE_OPACITY = 0.35;
const MAX_EDGE_OPACITY = 1.0;
const REPULSION_STRENGTH = 1200;
const SPRING_STRENGTH = 0.02;
const SPRING_REST_LENGTH = 90;
const CENTER_STRENGTH = 0.0015;
const DAMPING = 0.85;

class ChainGraph {
  constructor(svgEl, tooltipEl) {
    this.svg = svgEl;
    this.tooltip = tooltipEl;
    this.width = Number(svgEl.getAttribute("width"));
    this.height = Number(svgEl.getAttribute("height"));
    this.threshold = 0.15;
    this.nodes = [];
    this.edges = [];
    this.nodeEls = new Map();
    this.edgeEls = new Map();
    this._nodesByWord = new Map();
    this._nextId = 1;
    this.dragNode = null;

    this._tick = this._tick.bind(this);
    requestAnimationFrame(this._tick);

    this.svg.addEventListener("mousedown", (evt) => this._onMouseDown(evt));
    window.addEventListener("mousemove", (evt) => this._onMouseMove(evt));
    window.addEventListener("mouseup", () => this._onMouseUp());
  }

  reset(startWord, targetWord) {
    this.svg.innerHTML = "";
    this.nodeEls.clear();
    this.edgeEls.clear();
    this._nodesByWord.clear();
    this._nextId = 1;
    this.dragNode = null;
    this._hideTooltip();

    const startNode = this._makeNode(startWord, PADDING, this.height / 2, true);
    const targetNode = this._makeNode(targetWord, this.width - PADDING, this.height / 2, true);
    this.nodes = [startNode, targetNode];
    this.edges = [];

    for (const node of this.nodes) {
      this._createNodeEl(node);
    }
  }

  addStep(step) {
    const anchor = this.nodes[this.nodes.length - 1];
    const rawX = anchor.x + (Math.random() - 0.5) * 60;
    const rawY = anchor.y + (Math.random() - 0.5) * 60;
    const x = Math.max(NODE_RADIUS, Math.min(this.width - NODE_RADIUS, rawX));
    const y = Math.max(NODE_RADIUS, Math.min(this.height - NODE_RADIUS, rawY));

    const node = this._makeNode(step.word, x, y, false);
    node.neighborSimilarity = step.neighbor_similarity;
    node.targetSimilarity = step.target_similarity;
    node.isDigression = step.is_digression;

    this.nodes.push(node);
    this._createNodeEl(node);

    for (const entry of step.similarities) {
      const otherIds = this._nodesByWord.get(entry.word) || [];
      for (const otherId of otherIds) {
        if (otherId === node.id) continue;
        const edge = { aId: node.id, bId: otherId, similarity: entry.similarity };
        this.edges.push(edge);
        this._createEdgeEl(edge);
      }
    }
  }

  setThreshold(value) {
    this.threshold = value;
  }

  _makeNode(word, x, y, pinned) {
    return {
      id: this._nextId++,
      word,
      x,
      y,
      vx: 0,
      vy: 0,
      pinned,
      isDigression: false,
      neighborSimilarity: null,
      targetSimilarity: null,
    };
  }

  _nodeById(id) {
    return this.nodes.find((n) => n.id === id);
  }

  _createNodeEl(node) {
    const g = document.createElementNS(SVG_NS, "g");
    g.classList.add("node");
    g.dataset.nodeId = String(node.id);
    g.setAttribute("transform", `translate(${node.x}, ${node.y})`);

    const circle = document.createElementNS(SVG_NS, "circle");
    circle.setAttribute("r", NODE_RADIUS);
    g.appendChild(circle);

    const text = document.createElementNS(SVG_NS, "text");
    text.textContent = node.word;
    text.setAttribute("text-anchor", "middle");
    text.setAttribute("dy", "0.35em");
    g.appendChild(text);

    g.addEventListener("mouseenter", (evt) => this._showTooltip(node, evt));
    g.addEventListener("mousemove", (evt) => this._positionTooltip(evt));
    g.addEventListener("mouseleave", () => this._hideTooltip());

    this.svg.appendChild(g);
    this.nodeEls.set(node.id, { g, circle, text });

    if (!this._nodesByWord.has(node.word)) {
      this._nodesByWord.set(node.word, []);
    }
    this._nodesByWord.get(node.word).push(node.id);

    this._updateNodeAppearance(node);
  }

  _updateNodeAppearance(node) {
    const els = this.nodeEls.get(node.id);
    if (!els) return;
    els.circle.classList.toggle("node-pinned", node.pinned);
    els.circle.classList.toggle("node-digression", node.isDigression);
  }

  _createEdgeEl(edge) {
    const line = document.createElementNS(SVG_NS, "line");
    line.classList.add("edge");
    this.svg.insertBefore(line, this.svg.firstChild);
    this.edgeEls.set(edge, line);
  }

  _renderEdge(edge, maxSimilarity) {
    const line = this.edgeEls.get(edge);
    const a = this._nodeById(edge.aId);
    const b = this._nodeById(edge.bId);
    if (!line || !a || !b) return;

    const visible = edge.similarity >= this.threshold;
    line.style.display = visible ? "" : "none";
    if (!visible) return;

    line.setAttribute("x1", a.x);
    line.setAttribute("y1", a.y);
    line.setAttribute("x2", b.x);
    line.setAttribute("y2", b.y);

    const range = Math.max(maxSimilarity - this.threshold, 0.0001);
    const normalized = Math.min(1, Math.max(0, (edge.similarity - this.threshold) / range));
    const width = MIN_EDGE_WIDTH + normalized * (MAX_EDGE_WIDTH - MIN_EDGE_WIDTH);
    const opacity = MIN_EDGE_OPACITY + normalized * (MAX_EDGE_OPACITY - MIN_EDGE_OPACITY);
    line.setAttribute("stroke-width", width.toFixed(2));
    line.style.opacity = opacity.toFixed(2);
  }

  _renderEdges() {
    let maxSimilarity = this.threshold;
    for (const edge of this.edges) {
      if (edge.similarity >= this.threshold && edge.similarity > maxSimilarity) {
        maxSimilarity = edge.similarity;
      }
    }
    for (const edge of this.edges) {
      this._renderEdge(edge, maxSimilarity);
    }
  }

  _tick() {
    this._applyForces();
    this._render();
    requestAnimationFrame(this._tick);
  }

  _applyForces() {
    const cx = this.width / 2;
    const cy = this.height / 2;

    for (const node of this.nodes) {
      if (node.pinned || node === this.dragNode) continue;

      let fx = (cx - node.x) * CENTER_STRENGTH;
      let fy = (cy - node.y) * CENTER_STRENGTH;

      for (const other of this.nodes) {
        if (other === node) continue;
        let dx = node.x - other.x;
        let dy = node.y - other.y;
        let distSq = dx * dx + dy * dy;
        if (distSq < 1) distSq = 1;
        const dist = Math.sqrt(distSq);
        const force = REPULSION_STRENGTH / distSq;
        fx += (dx / dist) * force;
        fy += (dy / dist) * force;
      }

      for (const edge of this.edges) {
        if (edge.similarity < this.threshold) continue;
        let otherId = null;
        if (edge.aId === node.id) otherId = edge.bId;
        else if (edge.bId === node.id) otherId = edge.aId;
        else continue;
        const other = this._nodeById(otherId);
        if (!other) continue;

        const dx = other.x - node.x;
        const dy = other.y - node.y;
        const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
        const displacement = dist - SPRING_REST_LENGTH;
        const force = SPRING_STRENGTH * displacement;
        fx += (dx / dist) * force;
        fy += (dy / dist) * force;
      }

      node.vx = (node.vx + fx) * DAMPING;
      node.vy = (node.vy + fy) * DAMPING;
      node.x += node.vx;
      node.y += node.vy;
      node.x = Math.max(NODE_RADIUS, Math.min(this.width - NODE_RADIUS, node.x));
      node.y = Math.max(NODE_RADIUS, Math.min(this.height - NODE_RADIUS, node.y));
    }
  }

  _render() {
    for (const node of this.nodes) {
      const els = this.nodeEls.get(node.id);
      if (els) els.g.setAttribute("transform", `translate(${node.x}, ${node.y})`);
    }
    this._renderEdges();
  }

  _svgPoint(evt) {
    const pt = this.svg.createSVGPoint();
    pt.x = evt.clientX;
    pt.y = evt.clientY;
    const screenCTM = this.svg.getScreenCTM();
    return pt.matrixTransform(screenCTM.inverse());
  }

  _onMouseDown(evt) {
    const g = evt.target.closest(".node");
    if (!g) return;
    const nodeId = Number(g.dataset.nodeId);
    const node = this._nodeById(nodeId);
    if (!node || node.pinned) return;
    this.dragNode = node;
  }

  _onMouseMove(evt) {
    if (!this.dragNode) return;
    const pt = this._svgPoint(evt);
    this.dragNode.x = Math.max(NODE_RADIUS, Math.min(this.width - NODE_RADIUS, pt.x));
    this.dragNode.y = Math.max(NODE_RADIUS, Math.min(this.height - NODE_RADIUS, pt.y));
    this.dragNode.vx = 0;
    this.dragNode.vy = 0;
  }

  _onMouseUp() {
    this.dragNode = null;
  }

  _showTooltip(node, evt) {
    const text = node.neighborSimilarity === null
      ? node.word
      : `${node.word} — neighbor: ${node.neighborSimilarity.toFixed(2)}, target: ${node.targetSimilarity.toFixed(2)}`;
    this.tooltip.textContent = text;
    this.tooltip.hidden = false;
    this._positionTooltip(evt);
  }

  _positionTooltip(evt) {
    this.tooltip.style.left = `${evt.clientX + 12}px`;
    this.tooltip.style.top = `${evt.clientY + 12}px`;
  }

  _hideTooltip() {
    this.tooltip.hidden = true;
  }
}
```

Note what changed vs. the previous version, for your own review:
- `addStep` no longer special-cases a word matching the target — every added word goes through the same path, and gets one edge per entry in `step.similarities` (resolved to node id(s) via `_nodesByWord`).
- `_nodesByWord` is a new `Map<word, number[]>` index so edges can be created from the API's word-text-keyed `similarities` list. If a word repeats (rare, but possible), it connects to every node with that text.
- `_renderEdge`/`_renderEdges` now normalize width/opacity against the live max visible similarity, instead of the raw `[0,1]` similarity domain.
- `_applyForces` now includes a weak spring-to-center force for every unpinned, non-dragged node.
- `_createEdgeEl` and `setThreshold` no longer eagerly call `_renderEdge`/`_renderEdges` — the continuous `_tick` loop already re-renders every frame, so the old eager calls were dead work.
- `mousemove` is now bound to `window` instead of `this.svg`, so a drag continues correctly even if the cursor leaves the SVG's bounds mid-drag.

- [ ] **Step 2: Run the full test suite**

Run: `pytest -v`
Expected: PASS (all tests — this is a pure `static/graph.js` change; no Python test imports it)

- [ ] **Step 3: Manual verification**

Using the small-fixture dev server snippet from prior tasks (see e.g. the chain-graph-view plan's Task 1 Step 9), start a manual game (`cat`/`auto`), then:
1. Add `car` — confirm exactly 2 edges appear (car↔cat, car↔auto), both visible or hidden per the current threshold.
2. Add `dog` — confirm 3 more edges appear (dog↔cat, dog↔auto, dog↔car), for 5 total.
3. Drag the threshold slider to 0 — confirm ALL 5 edges become visible, including one directly between the target node and every word, not just the most recent one.
4. Compare edge thickness/opacity between a clearly-different-similarity pair — confirm they now look visibly different (not both stuck at the same faint appearance).
5. Leave the graph alone for a few seconds — confirm nodes with no visible edge (at whatever threshold you leave it at) drift toward the middle of the canvas area over time, rather than piling up against the border.
6. Type the literal target word (`auto`) as your next word — confirm it appears as a NEW node (not merged into the pinned target), with a very strong (thick, high-opacity) edge to the actual pinned target node.

- [ ] **Step 4: Commit**

```bash
git add static/graph.js
git commit -m "feat: full pairwise edges, normalized encoding, and centering force in chain graph"
```

---

### Task 3: Committed Playwright regression script

**Files:**
- Modify: `requirements.txt`
- Create: `scripts/verify_graph.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: the live Flask app (via HTTP/DOM), not any JS/Python API directly — this is an end-to-end script, not a unit test.
- Produces: nothing consumed by other tasks — this is the final task.

- [ ] **Step 1: Add Playwright as a dependency**

Append to `requirements.txt`:

```
playwright>=1.40,<2.0
```

Install it and its browser binary:

```bash
cd /home/john/Code/wordbridge && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

- [ ] **Step 2: Write the verification script**

Create `scripts/verify_graph.py`:

```python
"""Regression check for the chain graph view (pairwise edges, threshold slider, drag).

Drives a real headless-Chromium session against a throwaway dev server running the
small synthetic fixture model (never the real word2vec-google-news-300 model).

Requires Playwright (a dev-only browser-automation tool, not a page dependency):
    pip install -r requirements.txt
    playwright install chromium

Run:
    python scripts/verify_graph.py
"""
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

PORT = 5099
BASE_URL = f"http://127.0.0.1:{PORT}"

SERVER_SNIPPET = f"""
import numpy as np
from gensim.models import KeyedVectors

from wordbridge import create_app
from wordbridge.model import WordVectorModel

kv = KeyedVectors(vector_size=3)
words = ["cat", "dog", "car", "auto"]
vectors = np.array([[1, 0, 0], [0.9, 0.1, 0], [0, 1, 0], [0, 0.9, 0.1]])
kv.add_vectors(words, vectors)
model = WordVectorModel(kv, vocab_limit=10)
app = create_app(vector_model=model, db_path=":memory:", secret_key="verify")
app.run(port={PORT}, debug=False, use_reloader=False)
"""


def start_server():
    proc = subprocess.Popen([sys.executable, "-c", SERVER_SNIPPET])
    time.sleep(2)
    return proc


def main():
    proc = start_server()
    failures = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(BASE_URL)

            page.fill("#word1-input", "cat")
            page.fill("#word2-input", "auto")
            page.click("#manual-btn")
            page.wait_for_selector("#game:not([hidden])")

            node_count = page.eval_on_selector_all(".node", "els => els.length")
            if node_count != 2:
                failures.append(f"expected 2 nodes after manual start, got {node_count}")

            page.fill("#word-input", "car")
            page.click("#add-word-btn")
            page.wait_for_timeout(200)

            node_count = page.eval_on_selector_all(".node", "els => els.length")
            if node_count != 3:
                failures.append(f"expected 3 nodes after adding 'car', got {node_count}")

            edge_count = page.eval_on_selector_all(".edge", "els => els.length")
            if edge_count != 2:
                failures.append(
                    f"expected 2 pairwise edges (car-cat, car-auto) after one word, got {edge_count}"
                )

            page.fill("#threshold-slider", "0")
            page.dispatch_event("#threshold-slider", "input")
            page.wait_for_timeout(200)
            visible_edges = page.eval_on_selector_all(
                ".edge", "els => els.filter(e => e.style.display !== 'none').length"
            )
            if visible_edges != 2:
                failures.append(
                    f"expected both edges visible at threshold 0, got {visible_edges} visible"
                )

            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=5)

    if failures:
        print("FAILED:")
        for failure in failures:
            print(f"  - {failure}")
        sys.exit(1)

    print("All graph verification checks passed.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run it**

Run: `python scripts/verify_graph.py`
Expected: `All graph verification checks passed.` (exit code 0). If it fails, fix the specific reported mismatch in `static/graph.js` before proceeding — do not weaken the script's assertions to make it pass.

- [ ] **Step 4: Run the full Python suite too**

Run: `pytest -v`
Expected: PASS (unaffected — this task adds a standalone script, not a pytest test)

- [ ] **Step 5: Add a README note**

In `README.md`, under the existing `## Tests` section, add:

```markdown
## Graph Regression Check

A Playwright-driven script exercises the chain graph end-to-end (pairwise edges, threshold
slider, node counts) against a throwaway dev server using the small synthetic fixture model:

    pip install -r requirements.txt
    playwright install chromium   # one-time
    python scripts/verify_graph.py

This is separate from `pytest` — it drives a real headless browser and is slower, so it's
not part of the default test run.
```

- [ ] **Step 6: Commit**

```bash
git add requirements.txt scripts/verify_graph.py README.md
git commit -m "test: add committed Playwright regression script for the chain graph"
```
