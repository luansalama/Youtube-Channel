# Build report — Minecraft Narrative Studio v0.3.6

## Delivered

- Elevated PowerShell 7.6.3+ runner terminals with UAC, completion markers, closure detection, UTF-8 output, and terminal persistence.
- Editable proposal review with save-before-apply and automatic revision backups.
- Complete dashboard-controlled, video-at-a-time pipeline.
- Provider-agnostic Runner Manager with automatic task routing and fallback.
- Codex CLI adapter with read-only sandbox and structured output schema.
- OpenCode CLI adapter with bundled read-only agent and JSON/session-export recovery.
- Optional direct OpenAI Responses API fallback.
- Dashboard installation, authentication/setup, testing, model, reasoning, variant, timeout, status, and diagnostics controls.
- Review/apply isolation: runners cannot modify or approve project work directly.
- Seven phases, five human approvals, deterministic checks, fingerprints, reopening, backups, maintenance, and recovery.
- Browser editing, media management, application launchers, release packaging, YouTube controls, operations, analytics, channel documents, and BRL defaults.

## Verification target

```text
30 automated tests pass
Codex mock CLI structured proposal passes
OpenCode mock CLI structured proposal passes
cross-runner fallback passes
repository validation passes
all dashboard pages render
HTTP project creation remains reachable
ZIP integrity and manifest verification pass
```
