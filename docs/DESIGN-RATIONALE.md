# Design rationale — v0.3.6

v0.3.6 adds a human-editable proposal checkpoint while retaining the provider-independent runner architecture introduced in v0.3.4. The dashboard now treats Codex, OpenCode, and the direct API as interchangeable proposal runners behind one stable Studio Assistant interface.

## Product decisions

- Normal use requires no terminal.
- Every runner can be installed, configured, tested, routed, and diagnosed from the browser.
- Codex is the default creative runner because it is suited to long repository-aware reasoning.
- OpenCode is a first-class dashboard runner, not a secondary manual tool.
- OpenCode defaults to production support and audit work, but any route can be reassigned.
- The OpenAI API remains an optional fallback rather than a requirement.
- Runner failures may trigger configured fallbacks without losing the task.
- Every runner returns the same structured proposal and cannot apply it.
- Codex and OpenCode receive read-only permissions for dashboard work.
- Manual editing and proposal import remain complete when no runner is available.
- One active video and one next action remain the organising principle.
- Irreversible actions continue to require deterministic server-side approval checks.

The retained safeguards are local files, deterministic checks, approval fingerprints, deliberate reopening, backups, dry-run publication, non-fabrication rules, explicit external actions, and human review before AI-generated changes are applied.
