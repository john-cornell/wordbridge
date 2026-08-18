# Chain Graph View — Spec

A force-directed graph visualization of the in-progress chain, replacing the current plain word list. Builds on Wordbridge v1 (see `SPEC.md`) as one of the "explore more functionality" follow-ups.

## Problem

The current chain UI (`#chain-list`) is a plain ordered list of words with similarity numbers next to each. It doesn't visually communicate which words are actually "close" to each other in word2vec-space — a graph where connected words cluster and unrelated words drift apart would make relatedness visible and explorable at a glance, rather than requiring the player to read raw numbers.

## Goals

- Replace the current `<ol>` chain list with a force-directed node/edge graph.
- Draw an edge between two **consecutive** chain words only when their `neighbor_similarity` exceeds a player-adjustable threshold; otherwise the two words render with no edge between them, floating apart under generic repulsion.
- A live slider lets the player drag the threshold and watch edges appear/disappear in real time, using similarity data already returned by the API — no new network round-trip per threshold change.
- Pin the start word and target word at fixed anchor positions so the graph has a stable spatial frame of reference; every added chain word is a free-floating, draggable node.
- Edge visual weight (thickness/opacity) scales with the underlying similarity value.
- Digression words render in a distinct node color, carrying forward today's ⚠ signal.
- Exact neighbor/target similarity numbers remain available via hover/click on a node, not shown by default.

## Non-Goals

- No full pairwise graph — only consecutive chain words (word[i]/word[i+1]) are ever candidate edges. This reuses the existing `neighbor_similarity` per step; it does not compute similarity between every pair of words in the chain.
- No changes to scoring, win condition, or digression detection in `wordbridge/game.py` — this is a pure frontend/visualization feature layered on data the API already returns.
- No history-view graph — applies only to the live, in-progress chain.
- No external JS libraries or build step — consistent with the project's existing vanilla-JS-only constraint (`SPEC.md`).

## Requirements

- Replace `#chain-list` in `static/index.html` with an SVG- or `<canvas>`-based graph, driven from `static/app.js`.
- Force simulation: a small hand-rolled physics loop — spring attraction along above-threshold edges, generic repulsion between all node pairs, simple velocity/position integration via `requestAnimationFrame`. No external graph/physics library.
- Nodes: one per chain entry (start word, each added word, target word). Draggable via mouse/touch.
- Anchors: start word and target word have fixed x/y positions (e.g. left and right edges of the canvas). They do not participate in the free-floating physics themselves, though they still repel other nodes normally.
- Edges: created/removed reactively as the threshold slider moves — an edge exists between two adjacent chain words iff their already-known `neighbor_similarity` ≥ the current slider value.
- Threshold slider: an `<input type="range">` (or equivalent) with a visible current-value label. Default starting value proposed at **0.15** — real observed word2vec neighbor-similarities run much lower than the 0.7 win-threshold (e.g. 0.23, 0.06 seen in actual play), so a higher default would likely show no edges at all. This is a first guess, flagged for live tuning once played, same as the win threshold in `SPEC.md`.
- Digression coloring: any node whose step was flagged `is_digression: true` by the API renders in a distinct color (e.g. orange), independent of whether it has an edge.
- Hover/click tooltip on a node shows the word plus its exact `neighbor_similarity` and `target_similarity` values.
- Score, win/status messages, and the Restart/New game controls remain unchanged and continue to work exactly as today — only the `#chain-list` region is replaced.

## Constraints

- Vanilla JS/HTML/CSS only, no build step, no external libraries (matches `SPEC.md`'s existing constraint).
- Must not require any change to `wordbridge/game.py`, `wordbridge/routes.py`, or the JSON API contract — `neighbor_similarity`, `target_similarity`, and `is_digression` per word are already returned by `POST /api/game/word`.
- Should perform acceptably for chains up to the existing soft cap (~15 words) plus some slack beyond it, since chains are allowed to keep growing past the cap.

## Edge Cases

- A freshly started game (start/target set, zero added words): graph shows just the two pinned anchor nodes, no edges, nothing floating.
- Threshold slider at 0: every consecutive pair connects (all similarities are ≥ 0). Threshold at 1: essentially nothing ever connects (two distinct words reaching neighbor_similarity = 1.0 is effectively impossible) — both are valid, non-error states.
- A word that is both a digression *and* connected to its neighbor (similarity above threshold despite being a "backward" step relative to the target): digression coloring and edge-drawing are independent signals and can coexist on the same node/edge.
- Restarting or starting a new game must fully reset the graph — remove all prior nodes/edges, re-pin new start/target anchors.

## Open Questions

- Exact default threshold value (0.15 proposed) will likely need live tuning once you're actually dragging the slider during play — same caveat as the existing win-threshold tuning note in `SPEC.md`.
- Node sizing, exact color palette, and precise physics constants (spring stiffness, repulsion strength, damping) are implementation details to settle during a quick prototyping pass, not spec-blocking.

## Acceptance Criteria

- [ ] `#chain-list` is replaced by a graph rendering of the current chain.
- [ ] Start word and target word render at fixed, stable positions; other chain words float freely and are draggable.
- [ ] An edge renders between two consecutive chain words iff their neighbor_similarity is ≥ the current threshold slider value.
- [ ] Moving the threshold slider updates edges live, with no additional network request.
- [ ] Edge thickness/opacity visibly scales with the underlying similarity value.
- [ ] A digression word renders in a visually distinct color from non-digression words.
- [ ] Hovering or clicking a node reveals its exact neighbor_similarity/target_similarity values.
- [ ] Restart and New game both correctly reset the graph to just the two anchor nodes.
- [ ] No changes required to any Python file for this feature to work.
