---
name: story-architecture
description: Build or audit a causal, character-driven Minecraft story architecture without imposing a universal plot formula.
---

# Story Architecture

## Required inputs

Approved concept and research, `studio/writing-doctrine.json`, relevant postmortems, and current production constraints.

## Outputs

`.studio/internal/story/story-model.json`, `causal-spine.csv`, `sequence-outline.csv`, `beat-sheet.csv`, `scene-cards.csv`, `relationships.csv`, `information-map.csv`, `setup-payoff-ledger.csv`, `story-outline.md`, `treatment.md`, and `continuity-bible.md`.

## Method

1. Separate chronological story, causal plot, and audience presentation.
2. Reconfirm the audience promise and thematic conflict from approved concept evidence. Propose changes explicitly; do not silently rewrite them.
3. Build the character system around want, need, fear, belief, limitation, strategy, contradiction, boundary, pressure point, relationship function, and agency.
4. Design active opposition, layered stakes, final choice, climax mechanism, final state, and final image before filling the middle.
5. Create the minimum causal spine. For every major event record causes, actor, goal, decision, consequence, state change, information effect, later dependencies, counterfactual result, deletion impact, and production note.
6. Expand into sequences and beats. Each sequence records a temporary objective, strategy, location, complications, reversal/outcome, and resulting story state. Each beat states who acts, what they attempt, what interferes, what changes, and why the next beat follows.
7. Track audience knowledge, questions, expectations, emotional orientation, and character knowledge in the information map.
8. Register every major setup and its planned payoff, reinterpretation, cut status, or intentionally open serial reason.
9. Record relationship dynamics when more than one principal character exists, then build scene cards. Require purpose, entry/exit states, earned story value, and production requirements. Treat objective, obstacle, turn, and outcome as useful but flexible diagnostics.
10. Choose and justify the architecture that fits the material. Three acts, a midpoint, a protagonist arc, sequence counts, and opening/closing-image symmetry are optional.
11. Write an emotion-driven treatment without changing the approved graph, then make Minecraft mechanics, geography, inventory, construction, travel, and world rules alter choices, strategy, conflict, or climax.
12. Run `python -m mcstudio --root . story-audit <slug> --scope outline`, then separate failures, warnings, and creative recommendations.

## Gate test

Major events form a valid causal graph; references resolve; audience information is controlled; setup obligations are accounted for; the climax follows from earlier choices and rules; Minecraft is causally necessary; continuity can be filmed; and human judgement—not a formula—has selected the structure.
