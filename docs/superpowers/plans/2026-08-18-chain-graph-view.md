# Chain Graph View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the plain `<ol>` chain list with a force-directed, draggable node/edge graph — connected words pull together, unrelated words float apart — driven entirely by data the API already returns.

**Architecture:** A new `ChainGraph` class in `static/graph.js` owns an in-memory node/edge model (one node per chain word, one edge per consecutive pair) and renders it to an inline SVG element via a `requestAnimationFrame` physics loop (spring attraction on above-threshold edges, generic repulsion between all pairs). `static/app.js` feeds it `reset()`/`addStep()` calls at the same points it used to touch `#chain-list`, and wires a threshold `<input type="range">` to `chainGraph.setThreshold()`. No Python file changes.

**Tech Stack:** Vanilla JS (ES2015 class, inline SVG DOM manipulation, `requestAnimationFrame`), no build step, no external libraries — same constraint as the rest of the project.

## Global Constraints

- Vanilla JS/HTML/CSS only, no build step, no external libraries.
- No changes to `wordbridge/game.py`, `wordbridge/routes.py`, or the JSON API contract — `neighbor_similarity`, `target_similarity`, `is_digression` per word already come from `POST /api/game/word`.
- Edges only ever connect **consecutive** chain words (word[i] to word[i+1]) — never a full pairwise graph.
- Edge exists iff `neighbor_similarity >= threshold`. Default threshold: **0.15**, range 0–1, step 0.01.
- Start word and target word are pinned at fixed positions; every other chain word is a free-floating, draggable node.
- Edge thickness/opacity scales with the underlying similarity value.
- A digression word (`is_digression: true`) renders in a visually distinct color from non-digression words.
- Exact `neighbor_similarity`/`target_similarity` are shown via hover/click on a node, not visible by default.
- Restart and New game must fully reset the graph to just the two pinned anchor nodes.

---

### Task 1: Scaffolding, data model, and static rendering

**Files:**
- Modify: `static/index.html`
- Modify: `static/style.css`
- Create: `static/graph.js`
- Modify: `static/app.js`
- Test: `tests/test_static.py`

**Interfaces:**
- Produces: `class ChainGraph` with `constructor(svgEl, tooltipEl)`, `.reset(startWord, targetWord)`, `.addStep(step)` where `step` is exactly the JSON object returned by `POST /api/game/word` (`word`, `neighbor_similarity`, `target_similarity`, `is_digression`), and `.setThreshold(value)`. Tasks 2 and 3 add methods to this same class — do not rename any of the above.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_static.py`:

```python
def test_index_page_uses_graph_instead_of_list(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b'id="chain-list"' not in response.data
    assert b'id="chain-graph"' in response.data
    assert b'id="threshold-slider"' in response.data
    assert b'id="graph-tooltip"' in response.data


def test_graph_js_served(client):
    response = client.get("/graph.js")
    assert response.status_code == 200
    assert b"class ChainGraph" in response.data
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_static.py -v`
Expected: FAIL — `test_index_page_uses_graph_instead_of_list` fails because `#chain-list` still exists and the new ids don't; `test_graph_js_served` fails with 404 (no `static/graph.js` yet).

- [ ] **Step 3: Replace the chain list with the graph markup**

In `static/index.html`, replace this line:

```html
    <ol id="chain-list"></ol>
```

with:

```html
    <div id="graph-controls">
      <label for="threshold-slider">Connection threshold: <span id="threshold-value">0.15</span></label>
      <input type="range" id="threshold-slider" min="0" max="1" step="0.01" value="0.15">
    </div>
    <svg id="chain-graph" viewBox="0 0 600 300" width="600" height="300"></svg>
```

And add this line right after the `</section>` closing `#game`, still inside `<body>` (so it's a page-level element, not nested in the hidden setup/game sections):

```html
  <div id="graph-tooltip" hidden></div>
```

Add `static/graph.js` as a script tag **before** `app.js` (since `app.js` references the global `ChainGraph` class):

```html
  <script src="/graph.js"></script>
  <script src="/app.js"></script>
```

The full `static/index.html` should now read:

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
    <div id="graph-controls">
      <label for="threshold-slider">Connection threshold: <span id="threshold-value">0.15</span></label>
      <input type="range" id="threshold-slider" min="0" max="1" step="0.01" value="0.15">
    </div>
    <svg id="chain-graph" viewBox="0 0 600 300" width="600" height="300"></svg>
    <input id="word-input" placeholder="next word">
    <button id="add-word-btn">Add word</button>
    <button id="restart-btn">Restart</button>
    <button id="new-game-btn">New game</button>
    <p id="score"></p>
    <p id="status"></p>
  </section>

  <div id="graph-tooltip" hidden></div>

  <script src="/graph.js"></script>
  <script src="/app.js"></script>
</body>
</html>
```

- [ ] **Step 4: Add graph styles**

Append to `static/style.css`:

```css
#graph-controls {
  margin: 0.5rem 0;
}

#chain-graph {
  border: 1px solid #ccc;
  background: #fafafa;
}

.node circle {
  fill: #4a90d9;
  stroke: #2c5f8a;
  stroke-width: 1.5;
  cursor: grab;
}

.node circle.node-pinned {
  fill: #444;
  stroke: #222;
  cursor: default;
}

.node circle.node-digression {
  fill: #e08a2b;
  stroke: #a05e10;
}

.node text {
  font-size: 12px;
  fill: #fff;
  pointer-events: none;
  user-select: none;
}

.edge {
  stroke: #888;
}

#graph-tooltip {
  position: fixed;
  background: #222;
  color: #fff;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  pointer-events: none;
  z-index: 10;
}
```

- [ ] **Step 5: Create the ChainGraph data model and static renderer**

Create `static/graph.js`:

```javascript
const SVG_NS = "http://www.w3.org/2000/svg";
const NODE_RADIUS = 22;
const PADDING = 40;
const MIN_EDGE_WIDTH = 1;
const MAX_EDGE_WIDTH = 6;

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
    this._nextId = 1;
  }

  reset(startWord, targetWord) {
    this.svg.innerHTML = "";
    this.nodeEls.clear();
    this.edgeEls.clear();
    this._nextId = 1;
    this.nodes = [
      this._makeNode(startWord, PADDING, this.height / 2, true),
      this._makeNode(targetWord, this.width - PADDING, this.height / 2, true),
    ];
    this.edges = [];
    for (const node of this.nodes) {
      this._createNodeEl(node);
    }
  }

  addStep(step) {
    const prevNode = this.nodes[this.nodes.length - 2];
    const rawX = prevNode.x + (Math.random() - 0.5) * 60;
    const rawY = prevNode.y + (Math.random() - 0.5) * 60;
    const x = Math.max(NODE_RADIUS, Math.min(this.width - NODE_RADIUS, rawX));
    const y = Math.max(NODE_RADIUS, Math.min(this.height - NODE_RADIUS, rawY));

    const node = this._makeNode(step.word, x, y, false);
    node.neighborSimilarity = step.neighbor_similarity;
    node.targetSimilarity = step.target_similarity;
    node.isDigression = step.is_digression;

    this.nodes.splice(this.nodes.length - 1, 0, node);
    const edge = { aId: prevNode.id, bId: node.id, similarity: step.neighbor_similarity };
    this.edges.push(edge);

    this._createNodeEl(node);
    this._createEdgeEl(edge);
  }

  setThreshold(value) {
    this.threshold = value;
    this._renderEdges();
  }

  _makeNode(word, x, y, pinned) {
    return {
      id: this._nextId++,
      word,
      x,
      y,
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
    if (node.pinned) circle.classList.add("node-pinned");
    if (node.isDigression) circle.classList.add("node-digression");
    g.appendChild(circle);

    const text = document.createElementNS(SVG_NS, "text");
    text.textContent = node.word;
    text.setAttribute("text-anchor", "middle");
    text.setAttribute("dy", "0.35em");
    g.appendChild(text);

    this.svg.appendChild(g);
    this.nodeEls.set(node.id, { g, circle, text });
  }

  _createEdgeEl(edge) {
    const line = document.createElementNS(SVG_NS, "line");
    line.classList.add("edge");
    this.svg.insertBefore(line, this.svg.firstChild);
    this.edgeEls.set(edge, line);
    this._renderEdge(edge);
  }

  _renderEdge(edge) {
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
    const width = MIN_EDGE_WIDTH + edge.similarity * (MAX_EDGE_WIDTH - MIN_EDGE_WIDTH);
    line.setAttribute("stroke-width", width.toFixed(2));
    line.style.opacity = Math.max(0.25, edge.similarity).toFixed(2);
  }

  _renderEdges() {
    for (const edge of this.edges) {
      this._renderEdge(edge);
    }
  }
}
```

- [ ] **Step 6: Wire ChainGraph into app.js in place of the chain list**

Replace `static/app.js` entirely with:

```javascript
const setupSection = document.getElementById("setup");
const gameSection = document.getElementById("game");
const startWordEl = document.getElementById("start-word");
const targetWordEl = document.getElementById("target-word");
const scoreEl = document.getElementById("score");
const statusEl = document.getElementById("status");

const chainGraph = new ChainGraph(
  document.getElementById("chain-graph"),
  document.getElementById("graph-tooltip")
);

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
  chainGraph.reset(startWord, targetWord);
  scoreEl.textContent = "";
  statusEl.textContent = "";
  document.getElementById("word-input").disabled = false;
  document.getElementById("add-word-btn").disabled = false;
  setupSection.hidden = true;
  gameSection.hidden = false;
}

document.getElementById("random-btn").addEventListener("click", async () => {
  try {
    const data = await postJSON("/api/game/new", { mode: "random" });
    showGame(data.start_word, data.target_word);
  } catch (err) {
    statusEl.textContent = err.message;
  }
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
    chainGraph.addStep(data);
    scoreEl.textContent = `Score: ${data.score}`;
    input.value = "";

    if (data.won) {
      statusEl.textContent = "You connected the words!";
      document.getElementById("word-input").disabled = true;
      document.getElementById("add-word-btn").disabled = true;
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
  try {
    const data = await postJSON("/api/game/restart");
    showGame(data.start_word, data.target_word);
  } catch (err) {
    statusEl.textContent = err.message;
  }
});

document.getElementById("new-game-btn").addEventListener("click", () => {
  setupSection.hidden = false;
  gameSection.hidden = true;
});
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_static.py -v`
Expected: PASS (both new tests, plus the pre-existing `test_index_page_served`)

- [ ] **Step 8: Run the full suite to confirm nothing else broke**

Run: `pytest -v`
Expected: PASS (all tests — this task touches no Python game/route logic)

- [ ] **Step 9: Manual verification (static rendering, no motion yet)**

Start the dev server against the small fixture model (same trick used for prior frontend manual checks):

```bash
cd /home/john/Code/wordbridge && source .venv/bin/activate
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

Open http://127.0.0.1:5000, click "Use these words" with `cat` / `auto`. Confirm two circles appear (dark-filled, pinned-looking) labeled "cat" and "auto" at opposite sides of the SVG. Type `car`, click "Add word" — confirm a third (blue) circle labeled "car" appears, and a line connects it to "cat" (since `similarity(car, cat)` in this fixture is low — check via the score/response, but a line should NOT appear here since it's below the 0.15 default threshold in this fixture's geometry; if a line does appear that's also fine as long as it's consistent with the similarity value, since the exact fixture vectors weren't tuned for this specific threshold check). Open the browser console and run `chainGraph.setThreshold(0)` — confirm every edge becomes visible immediately. Run `chainGraph.setThreshold(1)` — confirm edges disappear.

- [ ] **Step 10: Commit**

```bash
git add static/index.html static/style.css static/graph.js static/app.js tests/test_static.py
git commit -m "feat: replace chain list with graph data model and static rendering"
```

---

### Task 2: Physics animation loop

**Files:**
- Modify: `static/graph.js`

**Interfaces:**
- Consumes: the node/edge model and `_renderEdges()`/`_nodeById()` from Task 1 — do not rename these.
- Produces: continuous node movement via `_tick()`/`_applyForces()`/`_render()`, running automatically from construction. Task 3 adds drag handling that must coexist with `_applyForces()`'s per-node loop — it already includes a `node === this.dragNode` skip condition for this reason.

- [ ] **Step 1: Add physics constants and velocity fields**

At the top of `static/graph.js`, add these constants alongside the existing ones (`NODE_RADIUS`, `PADDING`, etc.):

```javascript
const REPULSION_STRENGTH = 1200;
const SPRING_STRENGTH = 0.02;
const SPRING_REST_LENGTH = 90;
const DAMPING = 0.85;
```

In `_makeNode`, add velocity and drag-tracking fields to the returned object:

```javascript
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
```

- [ ] **Step 2: Start the animation loop from the constructor**

In the `ChainGraph` constructor, add `this.dragNode = null;` and start the loop:

```javascript
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
    this._nextId = 1;
    this.dragNode = null;
    this._tick = this._tick.bind(this);
    requestAnimationFrame(this._tick);
  }
```

- [ ] **Step 3: Add the force simulation and per-frame render**

Add these methods to `ChainGraph` (anywhere after the constructor):

```javascript
  _tick() {
    this._applyForces();
    this._render();
    requestAnimationFrame(this._tick);
  }

  _applyForces() {
    for (const node of this.nodes) {
      if (node.pinned || node === this.dragNode) continue;

      let fx = 0;
      let fy = 0;

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
```

- [ ] **Step 4: Run the full test suite to confirm nothing broke**

Run: `pytest -v`
Expected: PASS (this task only touches `static/graph.js`, which no Python test imports)

- [ ] **Step 5: Manual verification**

Using the same manual dev-server snippet as Task 1's Step 9: start a manual game, add 3-4 words with a mix of similarities (try obviously related and unrelated words once you're on the real model — with the small fixture, `car`/`auto` are close and `dog` is far from both). Confirm:
- Newly added words visibly drift and settle over roughly a second rather than staying frozen at their spawn point.
- Words connected by a visible edge visibly pull closer together over time.
- Words with no edge (below threshold) drift apart instead of clustering.
- The two pinned nodes (start/target) never move, regardless of what else is happening.

- [ ] **Step 6: Commit**

```bash
git add static/graph.js
git commit -m "feat: add force-directed physics simulation to chain graph"
```

---

### Task 3: Drag, threshold slider, hover tooltip, and final walkthrough

**Files:**
- Modify: `static/graph.js`
- Modify: `static/app.js`

**Interfaces:**
- Consumes: `_nodeById()`, `this.dragNode` (Task 2), `setThreshold()` (Task 1).
- Produces: nothing new consumed by later work — this is the final task for this feature.

- [ ] **Step 1: Add drag handling**

Add these methods to `ChainGraph`:

```javascript
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
```

In the constructor, register the listeners (add after `requestAnimationFrame(this._tick);`):

```javascript
    this.svg.addEventListener("mousedown", (evt) => this._onMouseDown(evt));
    this.svg.addEventListener("mousemove", (evt) => this._onMouseMove(evt));
    window.addEventListener("mouseup", () => this._onMouseUp());
```

- [ ] **Step 2: Add hover tooltip**

Add these methods to `ChainGraph`:

```javascript
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
```

In `_createNodeEl`, add these three listeners right after the `g.appendChild(text);` line:

```javascript
    g.addEventListener("mouseenter", (evt) => this._showTooltip(node, evt));
    g.addEventListener("mousemove", (evt) => this._positionTooltip(evt));
    g.addEventListener("mouseleave", () => this._hideTooltip());
```

- [ ] **Step 3: Wire the threshold slider in app.js**

Add to `static/app.js` (anywhere after the `chainGraph` declaration, e.g. right below it):

```javascript
const thresholdSlider = document.getElementById("threshold-slider");
const thresholdValueEl = document.getElementById("threshold-value");

thresholdSlider.addEventListener("input", () => {
  const value = Number(thresholdSlider.value);
  thresholdValueEl.textContent = value.toFixed(2);
  chainGraph.setThreshold(value);
});
```

- [ ] **Step 4: Run the full test suite**

Run: `pytest -v`
Expected: PASS (all tests — no Python files changed in this task)

- [ ] **Step 5: Manual verification — full walkthrough against every acceptance criterion**

Using the manual dev-server snippet from Task 1's Step 9, walk through and confirm each of these (from `SPEC-graph-view.md`'s Acceptance Criteria):

1. Start a manual game (`cat`/`auto`) — only two pinned nodes appear, no edges, nothing floating.
2. Add `car` — a third node appears and floats/settles via physics (not frozen).
3. Drag the `car` node with the mouse — it follows the cursor while held, and resumes physics-driven movement on release. Try dragging `cat` or `auto` (the pinned nodes) — nothing should happen, they don't move.
4. Move the threshold slider — watch edges appear/disappear live as you cross each word's similarity value; open the browser Network tab first and confirm moving the slider makes zero new requests.
5. Confirm edge thickness/opacity visibly differs between a high-similarity connection and a low-but-still-above-threshold one (try dragging the slider to different points to compare two different edges).
6. Hover over a non-pinned node — a tooltip appears near the cursor showing the word and its exact neighbor/target similarity numbers; move the mouse away — it disappears.
7. Add words until one triggers `is_digression: true` (check the score response — with this same fixture, adding `car` then `dog` right after reproduces a digression on `dog`, per `tests/test_game.py::test_digression_detected_when_target_similarity_drops`) — confirm that node renders in the distinct digression color.
8. Click Restart mid-chain — confirm the graph resets to exactly the two pinned nodes with no leftover edges/nodes from before.
9. Win the game, click "New game", then start a fresh pair — confirm the graph again shows exactly two fresh pinned nodes (no stale nodes from the previous game).

If any of these fail, fix the specific gap in `static/graph.js`/`static/app.js` before committing.

- [ ] **Step 6: Commit**

```bash
git add static/graph.js static/app.js
git commit -m "feat: add drag interaction, threshold slider, and hover tooltip to chain graph"
```
