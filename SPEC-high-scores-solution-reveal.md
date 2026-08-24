# High Scores: Solution Reveal + Player Filter — Spec

## Revision history

**2026-08-24 (later): full search now shows real non-bridge connections,
threshold displayed, hints marked, clear gated by password.** The first
correction (below) still only drew the winning bridge's own edges in
"Full search" - every other tried word floated disconnected, because the
replay graph never got `setThreshold()` called on it (stuck at the
default 0.7, hiding real sub-threshold-looking-but-actually-fine edges).
Fixed: the endpoint now returns the game's actual `threshold`, the
frontend applies it via `ChainGraph.setThreshold()` before rendering, and
displays it as text in the modal. Words obtained via a hint are now
tracked per-step (`Step.is_hint`, threaded through `chain_json`,
`Chain.to_dict()`, and the replay endpoint) and get a distinct dashed
purple border (`.node-hint` in `graph.js`/`style.css`) plus a tooltip
suffix. Separately (not part of this feature, but done alongside it):
"Clear high scores" now requires a password (hardcoded `"deleteme"` for
now - a friction gate for an amateur site shared with friends, not real
auth), and the misleading "Shortest path found" in-game message was
renamed to "Shortest path I found... (maybe you can do better!)" since
the solver's route is a greedy heuristic, not guaranteed-optimal.

**2026-08-24: corrected after initial misimplementation.** The first version
of this feature showed the AI solver's own pathfinding (`_compute_solution_route`'s
best-effort route, plus a full "candidates considered per hop" search trace)
instead of what the player actually did. That's the wrong data entirely —
"Direct path" and "Full search" are about the player's game, not the AI's
internal search. Corrected below; the solver-trace mechanism (`find_route(trace=...)`,
`Chain.solution_trace`, `solution_route_json`/`solution_trace_json` DB
columns) was fully reverted, along with a session-cookie-overflow bug it
caused along the way (see `deploy/AIREADME.md`'s "the session is a
client-side cookie" gotcha — moot now that this feature no longer stores
anything trace-shaped, but worth remembering for future session state).

## Problem

The high scores page (`/scores`) lists past attempts but gives no way to see
*how* a winning game actually went, and no way to focus on one player's
results among everyone else's.

## Goals

- A "Show solution" reveal per high-score row, on the (already separate)
  `/scores` page, so it never interrupts a game in progress.
  - **Direct path**: the actual winning bridge the player made — the
    connected chain of played words (plus start/target) that satisfied the
    win condition, exactly as shown in-game via `winning_connection`.
  - **Full search**: every word the player actually tried during that game,
    in order, including digressions that weren't part of the final bridge.
- A dropdown to filter the high scores list down to one player.

## Non-Goals

- Nothing about the AI solver's own pathfinding (`_compute_solution_route`)
  is part of this reveal. That mechanism still exists and is unchanged —
  it's used for par (the score baseline) and the in-game give-up reveal —
  but it is not what "show solution" on the high-scores page shows.
- No backfill for attempts saved before this ships — older rows (no stored
  `threshold`) simply have no reveal available. Not backwards compatible,
  by design.
- The player filter does not change what counts as "high scores" (still
  top 50 by score, overall) — it only hides rows client-side. A player
  whose best attempt didn't crack the top 50 shows nothing when selected.
- No change to `vocab_limit` / word count. Measured empirically against
  the real cached model file: the entire word2vec-google-news-300 vocab
  only contains ~155,060 valid lowercase-alpha words no matter how much of
  the file is loaded. 200k was never reachable from this word list.
  Decision: leave `vocab_limit` at its current value.

## Requirements

### Data model

- `attempts` gains one nullable column, `threshold REAL`, added via the
  same idempotent `ALTER TABLE ... ADD COLUMN` + catch-`OperationalError`
  pattern already used for `player_name`. This is the win threshold the
  game was actually played at — needed to correctly replay the win
  condition later (a different threshold could produce a different, or no,
  connection). `chain_json` (already stored — every word the player
  played, in order) doubles as the "full search" data; no new column
  needed for that part.
- `save_attempt` writes `chain.threshold` (always a real float — every
  chain has one).
- `list_high_scores` returns `has_solution: bool` per row (`threshold IS
  NOT NULL`) so the frontend can grey out the "Solution" button without a
  separate fetch per row.

### Replay, not re-search

`GET /api/high_scores/<id>/solution` reconstructs a fresh `Chain` from the
stored primitives (`start_word`, `target_word`, `threshold`) and replays
every stored word through `chain.add_word(word)`, in order. This
regenerates the exact same `Step` data (similarities, digression flags)
the player saw live, and lets `chain.winning_connection()` produce the
real bridge — using the existing, already-tested `Chain` methods rather
than inventing a new code path. If replay raises (a word no longer exists
in a since-changed vocabulary), the endpoint reports the reveal as
unavailable rather than erroring.

Response shape:
```json
{
  "available": true,
  "start_word": "...", "target_word": "...", "start_target_similarity": 0.0,
  "steps": [{"word": "...", "neighbor_similarity": 0.0, "target_similarity": 0.0, "is_digression": false, "similarities": [...]}],
  "winning_connection": [{"a": "...", "b": "...", "similarity": 0.0}]
}
```
or `{"available": false}` (threshold missing, or replay failed). 404 if
the id doesn't exist at all.

### Frontend (`/scores`)

- Each row gets a "Solution" button, disabled when `has_solution` is
  false.
- Clicking it opens a modal with a "Direct path" / "Full search" toggle:
  - **Direct path** reuses the existing `ChainGraph.reset()` +
    `showSuggestedRoute(path)` — `path` is derived from
    `winning_connection` (`[start_word, ...winning_connection.map(l => l.b)]`).
    Same call the in-game give-up reveal already makes; no new `graph.js`
    code.
  - **Full search** reuses the existing `ChainGraph.addStep(step)` for
    every entry in `steps`, in order — exactly the same call live gameplay
    already makes per move (so digressions render with the same
    `.node-digression` styling players already recognize from playing),
    then calls `highlightWinningConnection(winning_connection)` on top so
    the actual bridge is still visually distinguishable within the full
    graph. Zero new `graph.js` code needed for this feature at all — it's
    entirely composed from the two rendering primitives that already
    exist for live gameplay.
- A `<select id="player-filter">` above the table, populated from distinct
  `player_name` values in the currently loaded rows. Client-side filter,
  no new endpoint.

## Constraints

- Must not retroactively backfill `threshold` for existing rows — going
  forward only.
- Replay must use the same `Chain.add_word` validation path real gameplay
  uses — no parallel/simplified reimplementation that could drift from
  actual game rules.

## Edge Cases

- Attempt predates this feature (`threshold IS NULL`): `has_solution` is
  `false`, endpoint returns `{"available": false}`.
- Vocabulary changed since the game was played (a stored word no longer
  exists): replay's `add_word` raises `ValueError`, caught, same
  `{"available": false}` response rather than a 500.
- Player filter selected with zero matching rows in the top 50: table
  shows a filter-scoped empty state, distinct from "no high scores exist
  at all."
- Clicking "Solution" on a row whose attempt was deleted between page load
  and click: the detail fetch 404s; modal shows a plain error state.

## Acceptance Criteria

- [x] `attempts` gains `threshold`, added via idempotent migration;
      existing rows unaffected (`NULL`).
- [x] Winning a game persists the threshold it was played at.
- [x] `GET /api/high_scores/<id>/solution` replays the stored words and
      returns the real winning connection + full step list, or
      `{"available": false}` for attempts predating this feature.
- [x] `/scores` shows a "Solution" button per row, disabled when
      unavailable.
- [x] Clicking it shows the actual winning bridge, with a working toggle
      to see every word tried (including digressions).
- [x] A player-filter dropdown on `/scores` hides non-matching rows.
- [x] All existing tests pass; new tests cover the threshold migration,
      `save_attempt`/`list_high_scores` changes, and the replay endpoint
      (including the two-word-bridge and predates-feature cases).
