# Premiere Pro MCP

Cuts Studio uses Adobe Premiere Pro as its production NLE through the
open-source `leancoderkavy/premiere-pro-mcp` server. Configuration is in
`studio/nle.json`; workstation setup lives in `integrations/premiere-mcp/`.

## Architecture

```text
Cuts Studio timeline.json
        ↓ deterministic export
premiere-edit-spec.json + timeline.xmeml recovery
        ↓
MCP-capable editor agent/client
        ↓ local stdio
premiere-pro-mcp (pinned release)
        ↓
UXP when authenticated / CEP compatibility bridge
        ↓
Adobe Premiere Pro
        ↓ mandatory timeline readback
Cuts Studio master/composition flow
```

The harness deliberately does not implement a fake Premiere API. `nle-status`
means only that the local MCP executable was found. `nle-doctor` runs the
upstream local diagnostic. A real editor connection is established only when
the MCP client successfully runs `verify_premiere_connection` against an open
Premiere project/sequence.

## Determinism and gates

`premiere-edit-spec.json` carries exact source in/out ranges, record positions,
track intent, expected event count and total runtime. Live tool schemas are
always discovered at runtime because the upstream MCP evolves independently.
A structural edit is not considered successful until sequence readback matches
the spec within one frame and no unexpected gaps appear.

No MCP operation may approve `cutlist_lock`, `graphics_lock`, `master_lock`,
`rights_lock` or `publish_lock`. `execute_extendscript` and
`evaluate_expression` are forbidden because they cross the raw-code execution
boundary; the configured MCP authority excludes `unsafe-script`.

## Why the old Resolve driver was removed

The previous driver generated Resolve Python/Lua scripts and explicitly did not
provide a live integration. Premiere's current ecosystem provides a much
broader MCP tool surface plus documented UXP timeline actions, so Premiere MCP
is now the production backend. FCP7 XML remains only as a deterministic
recovery/interchange fallback, not as the primary control path.
