# Give Up Button — Spec

## Problem

A player who's stuck has no clean way to end an unwinnable-feeling attempt other than Restart (which silently discards the chain) or abandoning the page entirely. There's no feedback on how close they actually got.

## Goals

- A "Give up" button ends the current attempt.
- Giving up locks the chain (read-only, same lock as a win — no more words can be added) and shows the player's best (highest) `target_similarity` reached among all words they added, plus which word achieved it.
- Given-up attempts are NOT persisted to history — same as Restart/abandoned attempts, consistent with the existing "only completed (won) attempts are persisted" rule.

## Non-Goals

- No change to scoring formula or win threshold.
- No hints about what word to try next, no reveal of any "correct path."
- No new persistence/schema for "given up" attempts as a distinct history category (could be explored later — out of scope now).

## Requirements

- Backend: new endpoint `POST /api/game/give_up` — loads the current session chain, marks it `completed = True` (reusing the existing terminal-state flag from the win-fix work) WITHOUT calling `save_attempt`, and returns the best `target_similarity` reached and the word that achieved it.
- "Best" is `max(step.target_similarity for step in chain.steps)`.
- Frontend: a "Give up" button alongside Restart/New game. Clicking it calls the endpoint, disables word-input/add-word-btn (same lock as a win), and shows a status message like "You gave up. Your best was '&lt;word&gt;' at 0.34 similarity to the target."
- After giving up, Restart and New game both still work normally (Restart clears `completed`, same as after a win, allowing a fresh attempt on the same pair).

## Constraints

- Must reuse the existing `Chain.completed` terminal-state mechanism rather than inventing a parallel one.
- Must never call `save_attempt` for a given-up chain, under any circumstance.

## Edge Cases

- Giving up with zero words added (fresh game, immediate give-up): no steps exist, so there's no "best word." Response should indicate this cleanly (e.g. `best_word: null, best_similarity: null`), not error. Frontend shows a neutral message like "You gave up without trying any words."
- Giving up on an already-completed (won) chain: rejected the same way `add_word` already rejects further input on a completed chain (400 error), not silently allowed.
- Giving up, then Restart: must produce a genuinely fresh, playable chain on the same pair, same as restarting after a win already does.

## Open Questions

- Exact wording of the give-up status message — cosmetic, decide at implementation time.
- Whether "best" should be judged by `target_similarity` specifically vs. some other metric (e.g. score) — proposing `target_similarity` since it's the most intuitive "how close did you get" signal.

## Acceptance Criteria

- [ ] A "Give up" button exists in the game UI.
- [ ] Clicking it ends the attempt: locks input, does not persist to history.
- [ ] The UI shows the best `target_similarity` reached and which word achieved it (or a graceful message if zero words were added).
- [ ] Giving up on an already-completed chain is rejected with a clear error, consistent with how `add_word` already behaves post-completion.
- [ ] Restart after giving up produces a fresh, playable chain on the same word pair.
