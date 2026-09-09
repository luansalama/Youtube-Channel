---
name: qa-gates
description: Run objective, doctrine-aware, and adversarial reviews before human approval without confusing structural checks with artistic judgement.
---

# QA Gates

## Method

Read `project.json`, `studio/stages.json`, `studio/writing-doctrine.json`, approved upstream evidence, current artefacts, and relevant skills. Run `python -m mcstudio --root . gate <slug>`. For outline or script, also run `python -m mcstudio --root . story-audit <slug>`.

Inspect evidence quality, not only file presence. Test causality, references, audience knowledge states, setup/payoff obligations, canon integrity, Minecraft-specific causality, promise alignment, production feasibility, and downstream dependency risk.

## Report order

1. deterministic failures;
2. factual, rights, safety, or canon blockers;
3. causal or production blockers requiring human judgement;
4. advisory warnings from flexible conventions or thresholds;
5. non-blocking creative recommendations;
6. exact human decision required.

## Rule

Never approve or advance. A passing mechanical gate and story audit mean the required evidence is present and internally coherent enough for human review; they do not prove the story is good.
