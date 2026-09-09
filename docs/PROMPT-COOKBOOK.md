# Studio Assistant prompt cookbook

The normal agent should follow `AGENTS.md` and work on the single active video. These prompts are diagnostic fallbacks, not commands the showrunner must manage.

## Continue the active production

> Run `python -m mcstudio --root . maintain` and `python -m mcstudio --root . continue`. Read the active phase’s numbered human document. Complete every safe drafting, research, organisation, internal-ledger, and validation task available in the current phase. Keep machine evidence under `.studio/internal/`. Stop only for the showrunner’s creative judgement, a physical production task, a consequential external action, or a genuine ambiguity.

## Direction review

> Test the viewer promise, premise, hook, Minecraft causality, ending, originality, and smallest worthwhile scope. Decide whether research mode should be none, light, or full. Update `01-direction/direction.md` and the internal direction scorecard, but do not record `direction_lock`.

## Story review

> Read the approved Direction and `02-story/story-plan.md`. Test chronological logic, causal plot, audience presentation, character decisions, opposition, clue fairness, setup/payoff obligations, ending, continuity, and solo production feasibility. Maintain the hidden structured story records and run `python -m mcstudio --root . story-audit <slug> --scope outline`. Do not record `story_lock`.

## Script review

> Revise `03-script/script.md` in British English. Complete the six core passes and activate optional passes only where relevant. Update hidden script QC, spoken-pass notes, pronunciation guidance, and adaptive revision status. Run `python -m mcstudio --root . story-audit <slug> --scope script`. Do not record `script_lock`.

## Production planning

> Run a research-first Production deepening pass from the locked Script. Update the production plan, technical research, source/claims ledgers, exact-version toolchain matrix, scene implementation matrix, test matrix, deterministic take-control design, text-first storyboard and panel ledger, camera paths, locations, assets, budget and risks. Cover all thirteen scenes. Use official sources and label combined compatibility untested until a real spike. Optimise every storyboard panel for aphantasia with literal spatial blocking and text-only diagrams. Recommend a later reference-driven sketch model test but do not generate images. Clearly separate planned work from evidence Luan must physically create.

## Final-master review

> Read `05-edit/edit-review.md` and inspect available evidence. Audit picture, pacing, information flow, sound, captions, continuity, rights, credits, exports, and opening-to-promise alignment. Record timestamped findings and completed fixes. Do not record `master_lock`.

## Release review

> Prepare `06-release/release-plan.md` and hidden metadata, thumbnail concepts, description, credits, checklist, and package evidence. Keep curiosity honest. Use en-GB and BRL. Publishing remains dry-run and requires `publish_lock` plus explicit execution.

## Learning review

> Use production notes and available analytics to update `07-learn/lessons.md`. Separate observations from uncertain explanations. Carry forward only a few concrete decisions and reusable assets.
