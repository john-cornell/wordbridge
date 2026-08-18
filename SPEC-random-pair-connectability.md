# Random-Pair Connectability — Spec

## Problem

`WordVectorModel.random_pair()` currently samples two completely unrelated words from the filtered vocabulary with no check that they're actually bridgeable within a reasonable number of hops. Real observed similarity values run surprisingly low even for related-feeling words (e.g. 0.05, 0.12 seen in actual play), so some random pairs could be frustratingly close to unsolvable within the game's soft cap.

## Goals

- Before offering a randomly-generated pair to the player, verify a plausible path exists between the two words — a greedy nearest-neighbor search (using gensim's built-in `most_similar`) from the start word, bounded by a max hop count and a per-hop candidate budget, checking whether the target becomes reachable.
- If no path is found within the bounds, resample a new pair and repeat (with an overall retry cap, to avoid pathological infinite loops).

## Non-Goals

- No change to actual gameplay rules (win threshold, scoring, digression, soft cap) — this only affects which pairs get offered for random mode.
- No change to manual mode — the player can still manually enter any two words regardless of provable connectability; that's an explicit, opt-in choice.
- Not attempting a perfect/exhaustive proof of connectability — a bounded, best-effort greedy search, not a full graph search over the entire 3M-word vocabulary.

## Requirements

- New method `WordVectorModel.is_connectable(word_a, word_b, max_hops=6, neighbors_per_hop=20, win_threshold=0.7) -> bool`: a greedy/BFS search starting from `word_a`. At each hop, look at the frontier's top-N nearest neighbors via `self._kv.most_similar(word, topn=neighbors_per_hop)`; check if `word_b` is among them, or if any candidate's similarity to `word_b` already clears `win_threshold`. Expand the frontier for up to `max_hops`.
- `random_pair()` samples a candidate pair, checks `is_connectable`, and resamples (up to a retry cap, e.g. 20 attempts) if not connectable, before returning.
- If the retry cap is exhausted, fall back to returning the last sampled pair anyway — never hang indefinitely. This is a rare degenerate case, not a hard failure.

## Constraints

- No new dependency — `most_similar` is already part of gensim's `KeyedVectors` API, already a project dependency.
- Should stay fast enough for interactive use — a player clicking "Random pair" shouldn't wait more than ~1-2 seconds. Exact hop-count/neighbor-budget tuning is an implementation-time judgment call, to be checked against real timing once running against the actual 3M-word model.
- Automated tests must still use the small synthetic `KeyedVectors` fixture, never the real model — `is_connectable`'s logic must be testable against a tiny hand-built neighbor structure, same as the rest of `WordVectorModel`.

## Edge Cases

- The two randomly sampled words happen to be identical — should never happen given `rng.sample` already guarantees distinct elements, but worth a defensive thought if this logic is reused elsewhere.
- A word with very few or degenerate nearest-neighbors in the tiny test fixture (fewer neighbors available than `neighbors_per_hop`) — `most_similar(topn=N)` naturally returns fewer results if the vocab is smaller than N; must not error.
- Retry cap exhausted (extremely rare in the real 3M-word model, but must be handled gracefully per Requirements, not left as an infinite loop).

## Open Questions

- Exact values for `max_hops`/`neighbors_per_hop`/retry cap are best tuned empirically against the real model once running (proposed defaults: 6 hops, 20 neighbors/hop, 20 retries) — flagged as needing live tuning, same as the win-threshold and graph-connection-threshold were already flagged in earlier specs.
- Should search performance be measured/logged anywhere for future tuning? Proposing not, for v1 of this feature, to avoid scope creep — "make it work, refine later."

## Acceptance Criteria

- [ ] `WordVectorModel.is_connectable(word_a, word_b, ...)` exists and is unit-testable against the small synthetic fixture.
- [ ] `random_pair()` only returns pairs that pass `is_connectable` (or the documented retry-cap fallback).
- [ ] Manual mode is completely unaffected — no connectability check applied there.
- [ ] No change to scoring, win condition, digression, or soft-cap logic.
- [ ] Automated tests cover: a connectable pair found within a few hops, an unconnectable pair correctly detected as such (in the tiny fixture), and the retry-cap fallback path.
