# Architecture — v0.3.6

The harness has six layers:

1. **Hidden launcher** — starts the local Python service without a terminal.
2. **Dashboard** — the complete user interface for production, runners, files, approvals, release, operations, and diagnostics.
3. **Runner Manager** — routes Studio Assistant tasks to Codex, OpenCode, or the OpenAI API and normalises every response into one proposal schema.
4. **Human documents** — seven readable phase records.
5. **Internal evidence** — structured story, production, QC, release, proposal, backup, and analytics records.
6. **Deterministic engine** — checks, fingerprints, transitions, packaging, integrations, maintenance, and recovery.

## Trust boundary

External AI runners never become the workflow authority. They receive context and return proposals. Codex runs in a read-only sandbox; OpenCode uses a bundled read-only agent. The Python server alone applies reviewed changes, records approvals, advances stages, and performs consequential integrations.

## Adapter boundary

All providers implement the same conceptual operation:

```text
instructions + project context
→ structured proposal
→ human review
→ deterministic application
```

This keeps the pipeline independent of any single model provider and allows routing or fallback changes without redesigning project files.

The server uses Python’s standard library, binds to `127.0.0.1`, and keeps consequential actions behind explicit forms and server-side validation.
