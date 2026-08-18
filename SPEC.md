# Wordbridge (working title) — v1 Spec

A local, single-player web app inspired by [Linxicon](https://linxicon.com/): connect two words with a chain of intermediate words, using `word2vec-google-news-300` embeddings for similarity. Built as a v1 base to explore further game mechanics on top of.

## Problem

You want a local sandbox for playing with semantic word-chain gameplay (à la Linxicon), backed by real word2vec embeddings, that you can extend with new mechanics over time rather than a fixed one-shot game.

## Goals

- Free-play sandbox: pick/generate a word pair, build a chain from the start word to the target word, get scored on it.
- Real word2vec similarity (`word2vec-google-news-300` via gensim) drives both gameplay (win condition) and scoring.
- Simple local web UI (Python backend + plain HTML/JS), no accounts, runs on localhost.
- Persist completed attempts locally so history/scores survive restarts.
- Structured cleanly enough to bolt on new mechanics later (daily puzzle mode, hints, alternate scoring, etc.) without a rewrite.

## Non-Goals (v1)

- No daily-puzzle mode, no timers, no multiplayer/leaderboards, no accounts/auth.
- No exact replication of Linxicon's actual scoring/algorithm — this is a similarity-driven reinterpretation.
- No mobile-specific UI polish; desktop browser only for v1.

## Requirements

**Word pair selection**
- Two entry modes: (a) random pair generated from a filtered word2vec vocab, (b) manual entry of both words.
- Random filtering excludes multi-word phrases (tokens with `_`), non-alphabetic tokens, and restricts to a reasonably common-word slice of the vocab (e.g. top N most-frequent single-word tokens) so pairs aren't obscure garbage.
- Manual entry validates both words exist in the model vocab; reject with a clear error if not.

**Chain building**
- Append-only: no undo/edit of individual words once added (per your answer). A **Restart** action clears the whole in-progress chain and starts a fresh empty attempt on the same pair; the abandoned attempt is not persisted, just dropped from the session.
- Any vocab word can be appended — no minimum-similarity gate blocking a move. The game shows the impact of a bad move via scoring, not by disallowing the input.
- Soft cap on chain length (proposed: 15 words) — past the cap, show a warning but allow continuing; score keeps degrading as documented below.

**Similarity & scoring**
- For each word added to the chain, compute and display:
  - similarity to the previous word in the chain ("neighbor similarity")
  - similarity to the target word ("target similarity")
- A step is a **digression** if its target-similarity is lower than the previous step's target-similarity (i.e. you moved further from the goal).
- Score formula (default, tunable later):
  ```
  score = 100 - (10 × chain_length) - (5 × num_digressions)
  ```
- **Win condition**: the chain is complete once the last word's similarity to the target meets/exceeds a threshold (proposed default: cosine similarity ≥ 0.7 — needs a bit of live tuning once real embeddings are in front of you, since word2vec similarity distributions are lumpier than intuition suggests).

**Persistence**
- Simple local store (proposed: SQLite file in the project dir). On a **completed** (won) attempt, persist: word pair, full chain with per-step similarities, digression count, final score, timestamp.
- Abandoned/restarted attempts are not persisted (per your answer) — only completed attempts build history.
- No "best score per pair" tracking required for v1 (not requested), but the schema shouldn't actively prevent adding it later.

## Constraints

- `word2vec-google-news-300` is a ~3.6GB in-memory model (~1.6GB compressed download via `gensim.downloader`); expect a real chunk of RAM (4GB+ free recommended) and a noticeable one-time load delay on app startup. Worth loading once at process start and keeping resident, not per-request.
- Local-only, single-user — no auth, no need to handle concurrent multi-user state.
- New project, lives at `~/Code/wordbridge`, fully separate from the billing repo.

## Edge Cases

- Manually entered word not in vocab → reject with a clear message, chain unaffected.
- Word pair where start and target are already extremely similar (e.g. synonyms) → should still work, just a very short/high-scoring chain; not specifically excluded by the random-pair filter.
- Chain that never reaches the similarity threshold, growing indefinitely past the soft cap → allowed to continue (no hard stop for v1), score just keeps falling.
- Restarting immediately with an empty chain (no words added yet) → should be a no-op, not an error.

## Open Questions

- Exact win-threshold value (0.7 proposed) and random-pair vocab frequency cutoff will likely need live tuning once you can actually play with real embeddings — flagged as "tune after first playable version," not blocking v1 build.
- Any preference on Flask vs FastAPI for the backend, or should that be picked at implementation time?
- Project name "Wordbridge" is a placeholder — rename anytime before it matters (e.g. before a git remote/README references it).

## Acceptance Criteria

- [ ] App runs locally (`localhost`) with a Python backend serving `word2vec-google-news-300` loaded once at startup.
- [ ] Can start a new attempt via either a random filtered word pair or manually entered pair.
- [ ] Can append words one at a time (append-only) and see neighbor-similarity + target-similarity for each step.
- [ ] Digressions are detected and reflected in the live score using the formula above.
- [ ] Chain auto-completes as a win once target-similarity crosses the threshold.
- [ ] Soft cap warning appears past 15 words but doesn't block further play.
- [ ] Restart clears the current in-progress chain without saving it.
- [ ] Completed (won) attempts are saved to a local SQLite store and visible/queryable after an app restart.
