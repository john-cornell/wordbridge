# Wordbridge — Backlog

Not yet spec'd/planned — ideas captured for a future round, not to be implemented until explicitly requested.

## Graph UI: clarify display-threshold vs. win-threshold

Prompted by real confusion in play: the graph's connection threshold (default 0.15, purely
cosmetic/display) and the actual win threshold (fixed at 0.7, checked only against the last
word's direct similarity to the target) are unrelated numbers, and nothing in the UI makes
that distinction obvious. A "connected-looking" chain of low-threshold hops gives no signal
about whether any single word is actually close to winning.

Three concrete ideas from the user, not yet spec'd:

1. **Color-code edges by win-relevance, keep thickness for magnitude.** Edges below the 0.7
   win threshold render red; edges at/above it render green — layered on top of the existing
   thickness/opacity-by-similarity encoding, not replacing it.
2. **A "win threshold" notch on the slider itself**, at 0.7, with a bit of drag resistance
   near it — so sliding past the point where you'd only be looking at winning-strength
   connections has some tactile/visual feedback, distinct from casual exploration of the rest
   of the range.
3. **Reword the slider's label** — currently "Connection threshold," which reads as if it
   might affect scoring/gameplay. Something like "Display Connection Threshold" makes it
   clearer that this control only affects what's drawn, not the game itself.

Needs a proper `SPEC-*.md` + plan before implementation (interview if anything above is
ambiguous — e.g. exact green/red color values, exact slider snap behavior).
