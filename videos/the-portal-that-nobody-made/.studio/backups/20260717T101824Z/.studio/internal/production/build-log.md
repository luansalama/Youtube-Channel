# Build log

## Build baseline

**Portal implementation status:** Research candidate; no Minecraft proof of concept has been recorded yet.

**Candidate baseline:** Minecraft Java Edition 1.20.1 Fabric with Immersive Portals, Multiworld and Dimensional Weather. Exact loader and dependency versions remain unpinned until the clean-profile test.

**World strategy:** One clean master generated from a single seed, then separate R0–R4 copies or copied region data. Echo worlds must not be built from unrelated seeds.

## Session log

### 2026-07-15

- Changes: Initial production placeholders created.
- Evidence/screenshots: None recorded.
- Performance notes: Not measured.
- Deviations from location plan: None recorded.
- Next action: Research the portal implementation.

### 2026-07-16 — portal feasibility research handoff

- Changes: Added a candidate existing-mod implementation for see-through travel between separately saved echo worlds; added same-seed world strategy, independent-weather candidate, proof-of-concept gate, risks and fallbacks.
- Evidence/screenshots: Research sources SRC-003 through SRC-011 in `.studio/internal/research/source-ledger.csv`. No in-game evidence yet.
- Performance notes: Not measured. No claim of combined-mod compatibility or capture stability.
- Deviations from location plan: None. The recommendation preserves the script's matching ravine and weather contrast.
- Decision: Do not research or commission a custom mod until the minimum R0-to-R1 proof of concept identifies a specific unresolved capability.
- Next action: Create a clean test profile and complete the proof-of-concept record below.

## Portal proof-of-concept record

Duplicate this subsection for each test run. Never replace an earlier result.

### Test POC-001 — TODO

- Date:
- Operator: Luan
- Minecraft version: 1.20.1
- Java version:
- Fabric Loader version:
- Fabric API filename/version/hash:
- iCommon API filename/version/hash:
- Immersive Portals filename/version/hash:
- Multiworld filename/version/hash:
- Dimensional Weather filename/version/hash:
- Other installed mods: None for baseline
- Test world seed:
- R0 world ID:
- R1 world ID:
- Portal source coordinates/orientation:
- Portal destination coordinates/orientation:
- R0 weather:
- R1 weather:
- Test resolution and frame-rate target:
- GPU/driver:

#### Results

| Check | Result | Evidence | Notes |
|---|---|---|---|
| Clean profile launches | TODO | TODO | TODO |
| R0 and R1 are separately saved | TODO | TODO | TODO |
| Same-coordinate terrain matches | TODO | TODO | TODO |
| R1 renders through the portal | TODO | TODO | TODO |
| Lateral movement produces correct parallax | TODO | TODO | TODO |
| Player crossing is seamless | TODO | TODO | TODO |
| R0 dry / R1 raining | TODO | TODO | TODO |
| Rain and destination lighting visible from R0 | TODO | TODO | TODO |
| Moss crosses and remains tamed | TODO | TODO | TODO |
| Portal remains one-way | TODO | TODO | TODO |
| Save/reload preserves setup | TODO | TODO | TODO |
| Camera/replay tool compatibility | TODO | TODO | TODO |
| Shader compatibility | TODO | TODO | TODO |
| Stable capture performance | TODO | TODO | TODO |

#### Failure evidence

- Crash report or log:
- Reproduction steps:
- Suspected component:
- Version change attempted:
- Result after change:

#### Outcome

- Status: `not_run`
- Approved stack:
- Rejected components:
- Required fallback:
- Next action:

## Set-lock review

**Status:** Not ready.

Portal sets, final world duplication and echo-specific art direction remain blocked until POC-001 either passes or produces a documented fallback plan approved for capture.
