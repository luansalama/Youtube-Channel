---
name: scriptwriting-en-gb
description: Draft or revise an en-GB production script from locked story architecture using controlled scene design and specialised revision passes.
---

# Scriptwriting En Gb

## Required inputs

Locked outline evidence, stable scene IDs, continuity bible, production constraints, and `studio/writing-doctrine.json`.

## Outputs

`03-script/script.md`, `script-qc.md`, `revision-pass-status.json`, `table-read-notes.md`, and `pronunciation-guide.md`.

## Method

Preserve scene IDs and approved causal order. For each scene distinguish entry state, purpose/story value, objective/pressure/tactic when useful, visual action, narration, dialogue/in-world audio, subtext/power shift, information revealed or withheld, sound intent, turn/outcome/exit state, and production note.

Write what can be seen, heard, performed, staged, animated, edited, or deliberately withheld. Convert internal information into behaviour, voice-over, visual design, dialogue, or intentional ambiguity. Remove narration that merely describes clear visuals. Use exposition when necessary, motivated, timely, and action-changing.

Perform a recorded solo spoken pass, table read, storyboard read, or animatic review and capture the resulting changes in `table-read-notes.md`. Read prose aloud. Prefer concrete verbs, controlled sentence length, natural rhythm, intentional silence, and British spelling without manufacturing a British persona or accent.

## Revision passes

Complete separately: promise; causality; character agency; escalation; theme/change; information; scene necessity; dialogue/subtext; visual storytelling; production feasibility; continuity/canon; audience-results plan. Record evidence and decisions in both QC and `revision-pass-status.json`.

`not_applicable` requires a real rationale. `blocked` cannot reach script lock.

## QC

Run `python -m mcstudio --root . story-audit <slug> --scope script`. Verify originality, factual support, pronunciation, runtime, and production feasibility. Flag every line that requires an unplanned shot, asset, world rule, or canon change.
