# Full Pairwise Similarity Graph — Spec

Extends the just-built chain graph view (`SPEC-graph-view.md`) to connect every word to every other word, not just consecutive chain words. Fixes the target-connectivity gap discovered in play: today's graph never draws an edge from the last-typed word to the target unless it's an exact string match.

## Problem

The current graph only connects consecutive typed words via `neighbor_similarity`. The target node (and any non-adjacent pair) never gets an edge unless it exactly matches — confirmed live: typing "burst" toward target "bursts" leaves them disconnected even at threshold 0, because there's no edge model connecting the tail of the chain to the target at all, only an exact-string-match special case. The graph should instead reflect true pairwise relatedness between every word currently in play.

## Goals

- Every word currently in the graph (start, target, all added chain words) gets a candidate edge to every OTHER word, based on their direct pairwise similarity — not just to its immediate chain neighbor.
- This fully replaces the "only consecutive words" edge model from the original chain-graph-view feature.
- New pairwise data reaches the frontend incrementally: whenever a word is added, the API response includes that word's similarity to every other word currently in the chain — not a full matrix recomputed from scratch each time.
- The target-connectivity gap is resolved as a natural side effect, since the target is just another node subject to the same all-pairs rule.

## Non-Goals

- No change to scoring, win condition, or digression detection — `neighbor_similarity`/`target_similarity`/`is_digression` per step remain exactly as they are for game-logic purposes. This is purely about what the graph renders, layered on top of a new pairwise-similarities field.
- No persistence of pairwise similarity data to SQLite — history storage (chain of words, digression count, score) is unchanged.
- No changes to `wordbridge/game.py`'s scoring formula.

## Requirements

- Backend: for the newly added word, compute its similarity to every OTHER word currently tracked in the chain (start word, target word, every previously added word) using `WordVectorModel.similarity(a, b)`, which is already fully generic — not limited to neighbor/target pairs.
- API: `POST /api/game/word`'s response gains a new field — e.g. `"similarities": [{"word": "<other word>", "similarity": <float>}, ...]` — one entry per other word currently in the chain (excluding the word itself), for the just-added word only. Existing fields (`neighbor_similarity`, `target_similarity`, `is_digression`, `score`, `won`, `over_soft_cap`) are unchanged.
- Frontend: `ChainGraph` maintains one edge per PAIR of nodes ever compared, each with its own similarity value. Adding the Nth word creates N-1 edges (one per every already-existing node), not just one.
- Edge visibility/rendering rule is unchanged conceptually: edge shown iff `similarity >= threshold`; thickness/opacity still scale with similarity.
- The Task-1 win special case (typing the literal target word connects into the pinned target rather than duplicating it) becomes redundant under this general model — a typed word equal to the target will naturally show ~1.0 similarity to the target node like any other pairing. Remove/simplify that special-case branch rather than leaving it as dead or duplicated logic.

## Constraints

- Must not touch scoring/win/digression logic — those still only ever look at `neighbor_similarity`/`target_similarity` as already defined.
- Backend cost: O(current chain length) additional `similarity()` calls per added word — trivial given chain lengths are soft-capped around 15-20 words.
- Vanilla JS, no build step, no external graph library — consistent with the rest of the project.

## Edge Cases

- First word added: only 2 "other words" exist (start, target), so its `similarities` list has exactly 2 entries.
- A win (typed word exactly matches target): naturally produces a ~1.0 similarity entry to the target — no special-casing needed in the API; the frontend renders it like any other edge.
- Two added (non-anchor) words happening to be identical strings — still just computes `similarity(word, word) = 1.0` like any pair, not a special error case.

## Open Questions

- Should the hover tooltip show a live "similarity to every other node" for the hovered word (not just the old neighbor/target pair), now that "neighbor" is no longer the most meaningful figure? Proposing to keep the existing tooltip format as a safe default for v1 and revisit once this is in play — not spec-blocking.
- Exact response field naming (`similarities` vs. something else) is a naming detail, not spec-blocking.

## Acceptance Criteria

- [ ] Every pair of words currently in the chain (including start/target) has a candidate edge based on direct pairwise similarity, not just consecutive pairs.
- [ ] The target node connects to any sufficiently-similar word regardless of whether it's the literal last word typed or an exact string match.
- [ ] `POST /api/game/word`'s response includes the added word's similarity to every other current word.
- [ ] No change to score/win/digression computation.
- [ ] Threshold slider still works exactly as before, now governing visibility of the full set of pairwise edges instead of just N-1 sequential ones.
