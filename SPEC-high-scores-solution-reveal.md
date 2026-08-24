# High Scores: Solution Reveal + Player Filter — Spec

## Problem

The high scores page (`/scores`) lists past attempts but gives no way to see
*how* a winning chain was actually connectable, and no way to focus on one
player's results among everyone else's. Separately, there's no record of
the solver's actual search process for a puzzle — only the final route,
and only live in the current session (via the give-up reveal), never
persisted.

## Goals

- A "Show solution" reveal per high-score row, on the (already separate)
  `/scores` page, so it never interrupts a game in progress.
  - (a) The direct path: the shortest real route the model found between
    start and target at the puzzle's threshold.
  - (b) The full search: every word the solver actually considered while
    finding that route, not just the winning hops.
- A dropdown to filter the high scores list down to one player.

## Non-Goals

- No backfill of solution data for attempts saved before this ships —
  older rows simply have no reveal available. Not backwards compatible,
  by design.
- The trace does not include hints used during actual play, or rerolled
  random pairs that were discarded before the puzzle was chosen — only the
  solver's search for the pair that became the actual puzzle.
- The player filter does not change what counts as "high scores" (still
  top 50 by score, overall) — it only hides rows client-side. A player
  whose best attempt didn't crack the top 50 shows nothing when selected.
- No change to `vocab_limit` / word count. Measured empirically against
  the real cached model file: the entire word2vec-google-news-300 vocab
  only contains ~155,060 valid lowercase-alpha words no matter how much of
  the file is loaded (140,284 at the current 1.7M-entry raw load; 155,060
  even loading all 3,000,000 raw entries). 200k was never reachable from
  this word list. Decision: leave `vocab_limit` at its current value
  (140k reachable in practice); revisit only if the model source changes.

## Requirements

### Data model

- `attempts` table gains two nullable columns, added via the same
  idempotent `ALTER TABLE ... ADD COLUMN` + catch-`OperationalError` pattern
  already used for `player_name` in `db.py`'s `init_db`:
  - `solution_route_json TEXT` — the direct path, `[start_word, ..., target_word]`.
  - `solution_trace_json TEXT` — the full search trace (see below).
- `save_attempt` writes both when the chain has them (`chain.solution_route`,
  `chain.solution_trace`), `NULL` otherwise.
- `list_high_scores` additionally returns `has_solution: bool` per row
  (`solution_route_json IS NOT NULL`) so the frontend can grey out the
  "Show solution" button without a separate fetch per row.

### Solver trace capture

- `Chain` gains a `solution_trace` field, alongside the existing
  `solution_route`, both set together by `_compute_solution_route` and
  carried through `Chain.to_dict()` / `Chain.from_dict()` exactly like
  `solution_route` already is — so it survives threshold changes
  (`/api/game/threshold` already recomputes `solution_route`; it now
  recomputes `solution_trace` at the same time) and session round-trips.
- `WordVectorModel.find_route` gains an optional `trace=None` parameter.
  When the caller passes a list, each hop of the search appends one entry:
  ```python
  {
      "from": current,                  # word the search was standing on
      "current_similarity": ...,        # current -> to_word similarity
      "candidates": [
          {
              "word": w,
              "similarity_to_current": ...,
              "similarity_to_target": ...,
              "passed_threshold": bool,  # cleared win_threshold from `current`
          }
          for w in <neighbors_per_hop candidates returned by most_similar>
      ],
      "chosen": <word or None>,         # the candidate the search moved to, if any
  }
  ```
  Existing callers (`_find_hint_word`'s bridge/continuation/fresh searches)
  do not pass `trace`, so hint searches during play are untouched and pay
  no extra cost.
- `_compute_solution_route` passes a trace list to its primary search
  (`_PAR_SEARCH_PARAMS`). If that fails and the fallback
  (`_PAR_FALLBACK_SEARCH_PARAMS`) has to run, the fallback's hops are
  appended to the same list — so a reveal for a puzzle that needed the
  fallback shows the full attempt, including the primary search's
  unsuccessful hops.

### API

- `GET /api/high_scores/<id>/solution` → `{"solution_route": [...] | null, "solution_trace": [...] | null}`.
  404 if `id` doesn't exist at all; `null` fields (200) if it exists but
  predates this feature or the puzzle had no findable route.

### Frontend (`/scores`)

- Each row gets a "Show solution" button, disabled (with a tooltip-style
  title, e.g. "No solution recorded for this attempt") when
  `has_solution` is false.
- Clicking it opens a modal containing:
  - An `<svg>` + tooltip `<div>`, same shape as the in-game ones in
    `index.html`, loading the existing `graph.js`.
  - A "Direct path" / "Full search" toggle, defaulting to "Direct path".
  - **Direct path** reuses the existing `ChainGraph.reset(start, target, similarity)`
    + `ChainGraph.showSuggestedRoute(route)` — the same call the in-game
    give-up reveal already makes. No new `graph.js` code needed for this
    part.
  - **Full search** calls one new `ChainGraph` method,
    `renderSearchTrace(startWord, targetWord, trace)`: resets the graph,
    then for each hop adds a node per candidate word (reusing existing
    nodes where a word repeats across hops) with an edge from `hop.from`
    to each candidate — dimmed/thin for `passed_threshold: false`,
    normal weight for `passed_threshold: true`, and the `chosen` edge
    drawn the same way `highlightWinningConnection` already highlights
    edges. This is additive: it doesn't touch `addStep`,
    `highlightWinningConnection`, or any other live-gameplay method.
- A `<select id="player-filter">` above the table, populated from the
  distinct `player_name` values present in the currently loaded rows
  (`"All players"` default). Selecting a name hides non-matching `<tr>`s
  client-side; no new endpoint.

## Constraints

- Must not change the return shape of `find_route` for existing callers —
  `trace` is opt-in via an extra parameter, default `None` means "don't
  bother building trace data."
- Must not retroactively compute or backfill `solution_route`/`solution_trace`
  for existing rows — this is a going-forward feature only.
- The "Full search" graph must remain readable at the trace sizes actually
  produced (up to `max_hops` hops × up to `neighbors_per_hop` candidates
  each, bounded by the existing `_PAR_SEARCH_PARAMS`/`_PAR_FALLBACK_SEARCH_PARAMS`
  constants — no new size limits introduced by this feature).

## Edge Cases

- Puzzle where no solution route could be found at all (`par_length is None`):
  `solution_route`/`solution_trace` are both `None`; `has_solution` is
  `False`; "Show solution" stays disabled for that row.
- Player filter selected with zero matching rows in the top 50 (their best
  attempt didn't crack it): table shows empty with the existing
  "No high scores yet" state, scoped to being empty *for that filter* —
  copy may need a small tweak so it doesn't imply zero scores exist at all
  (decide exact wording at implementation time).
- Clicking "Show solution" on a row whose attempt was deleted between page
  load and click (via "Clear high scores" in another tab): the detail
  fetch 404s; modal shows a plain error state instead of crashing.

## Open Questions

- Exact modal styling/copy — cosmetic, decide at implementation time,
  consistent with the existing `.card`/`.btn` classes in `style.css`.

## Acceptance Criteria

- [ ] `attempts` gains `solution_route_json`/`solution_trace_json`, added
      via idempotent migration; existing rows unaffected (`NULL`).
- [ ] Winning a game (random or manual mode) persists both fields for that
      attempt whenever the puzzle had a findable solution route.
- [ ] `GET /api/high_scores/<id>/solution` returns the stored route/trace,
      or `null`/`null` for attempts predating this feature.
- [ ] `/scores` shows a "Show solution" button per row, disabled when
      unavailable.
- [ ] Clicking it shows the direct path via the existing graph component,
      with a working toggle to the full search trace view.
- [ ] A player-filter dropdown on `/scores` hides non-matching rows.
- [ ] All existing tests still pass; new tests cover the trace-building
      logic in `find_route`, the migration, `save_attempt`/`list_high_scores`
      changes, and the new endpoint.
