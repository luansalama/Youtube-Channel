---
name: automation-safety
description: Design or review any new automation, integration, model delegation, scheduled action, or credentialed workflow.
---

# Automation Safety

## Risk test
Classify data sensitivity, external side effects, reversibility, blast radius, model reliability, prompt-injection exposure, and required evidence.

## Defaults
Read/draft/test is allowed; send/publish/spend/delete/accept is gated. Use dry-run, least privilege, explicit target, idempotency, logs, checksums, rollback, and human approval immediately before the consequential action.

## Model routing
Use free/secondary models only for bounded reversible tasks. Never give them secrets or unsupervised external authority.
