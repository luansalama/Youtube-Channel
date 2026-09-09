# Build log

## Build baseline

**Evidence status:** Planning and supplied-source research only. No Minecraft profile, proof of concept, datapack, world, location, graphic, audio file, capture or storyboard image is evidenced.

**Portal implementation status:** Immersive Portals 5.2.0 and Dimensional Weather 1.1 are present in the user-reported profile. Multiworld is not installed or selected. Custom-dimension registration, R0-derived terrain transfer, portal routing and replay remain untested.

**Provisional baseline:** Existing Minecraft Java Edition 1.20.1 Fabric profile. Fabric API 0.92.11, Replay Mod 2.6.23, Chunky 1.3.146, Sodium 0.5.13, Indium 1.0.36 and Iris 1.7.6 are user-reported present; Java, Fabric Loader and hashes remain unrecorded.

**1.21.1 comparison:** Deferred. It is not a production prerequisite and will reopen only after a reproducible 1.20.1 blocker.

**World strategy:** Scout for the closest usable seed/world, adapt it directly into R0, allow bounded terrain imports such as a ravine, pregenerate the camera footprint, preserve `TPNM_R0_SOURCE`, duplicate R0–R4 working saves and consolidate them as dimensions in one filming master. R4 remains the closest R0 derivative and adds Home plus minor differences. No final seed or coordinate has been selected.

**Script authority:** Production follows all thirteen scenes of `draft-03`. The protagonist does not ignite or directly discharge the final system; the creeper explodes first. Delayed activation is invented canon. R4 Moss’s fate remains unresolved.

## Session log

### 2026-07-15

- Changes: Initial production planning files created.
- Evidence/screenshots: None recorded.
- Performance notes: Not measured.
- Deviations: None implemented.
- Next action: Research portal implementation.

### 2026-07-16 — portal feasibility research handoff

- Changes: Recorded supplied candidates for see-through portal travel, separate echo states, same-seed geography and independent weather; defined a proof gate and composite fallback.
- Evidence/screenshots: Source records only. No in-game evidence.
- Performance notes: Not measured.
- Deviations: None implemented.
- Decision: Do not commission a custom mod before a precise existing-tool failure is retained.
- Next action: Resolve exact dependencies and run the minimum proof.

### 2026-07-16 — Script-led production development

- Changes: Planned thirteen scenes and established `MATCH PATH`, `MATCH FRAME A`, granite-seam, fire, creeper-route and delayed-activation controls.
- Evidence/screenshots: None created.
- Performance notes: Not measured.
- Deviations: None implemented.
- Decision: Script `draft-03` supersedes conflicting Story and Direction material.
- Next action: Run the isolated R0-to-R1 baseline before full echo construction.

### 2026-07-17 — research-first deepening proposal

- Changes: Reorganised the supplied primary-source findings into an exact-version comparison; selected 1.20.1 as a provisional evidence-led baseline; recorded the absent 1.21.1 intersection; designed the datapack-first take controller; completed planning matrices, 49 text storyboard panels, camera paths, modular locations, budget and expanded risks.
- Evidence/screenshots: No new external research, installation, test, build, capture or generated image is claimed. This entry records synthesis from supplied context only.
- Performance notes: Not measured.
- Deviations: None implemented.
- Decision: Test one world, weather and camera method at a time. Keep live and composite portal routes available. Defer custom development.
- Next action: Record the current 1.20.1 runtime/profile metadata, then run the smallest isolated portal baseline. The 1.21.1 comparison remains deferred unless a specific blocker appears.


### 2026-07-18 — R0-first scouting and dimension-consolidation decision

- User constraint: insufficient time/resources to create five environments or a neutral base from scratch.
- Decision: scout existing in-game/online seeds and locations, choose the strongest near-match as R0, import missing terrain such as a ravine when efficient, then duplicate R0 into R1–R4 working saves.
- R4 rule: direct R0 derivative with Home and minor seasonal/state differences.
- Final assembly: R0 remains the filming-master overworld; R1–R4 are registered dimensions populated by zero-offset terrain transfer. Multiworld/iCommon are removed from the preferred path.
- Evidence added: exact user-reported mods-directory inventory; no launch, hash, transfer, weather, portal, replay or capture success is claimed.
- Next action: fill the seed shortlist while running the smallest disposable R0/R1 dimension-transfer proof.

## Planned take-controller record

**Status:** Designed, not implemented.

Planned lifecycle: `setup`, `arm`, `action`, `reset`, `cleanup`.

Planned controls: namespaced temporary tags; marker entities; `tpnm_take`, `tpnm_phase`, `tpnm_tick` and `tpnm_cue` objectives; fixed time/weather; disabled natural spawning; protected world/region restoration; explicit wild, tamed-unnamed and named Moss states; separate skeleton, fire and creeper plates.

No datapack file, command execution, state inspection or reset result exists.

## Version research queue

| Test | Requirement | Status | Next evidence |
|---|---|---|---|
| VER-120 | Record Java, Fabric Loader and hashes for the current 1.20.1 proof profile | `not_run` | Launcher metadata and local artefact hashes |
| VER-121 | Conditional 1.21.1 migration comparison after a specific blocker | `deferred` | Retained 1.20.1 failure plus official replacement releases |

## Portal proof-of-concept record

Retain every completed run as a new subsection. Never replace earlier evidence.

### Test POC-001 — not run

- Date: Not run
- Operator: Luan
- Minecraft version: 1.20.1 candidate
- Java version: Not recorded
- Fabric Loader version: Not recorded
- Fabric API artefact/version/hash: Not recorded
- Immersive Portals artefact/version/hash: Not recorded
- Other installed mods: None recorded
- Test world seed: Not selected
- World ID: Not created
- Portal coordinates/orientation: Not selected
- Resolution/frame-rate target: Not selected
- GPU/driver: Not recorded

| Check | Result | Evidence | Notes |
|---|---|---|---|
| Clean profile launches | Not run | None | Minimum stack only |
| Portal can be created | Not run | None | Record exact command/configuration |
| Save and reload preserve portal | Not run | None | Repeat twice |
| Static destination view renders | Not run | None | Inspect clipping |
| Lateral parallax is correct | Not run | None | Four-block planned move |
| Player crossing is usable | Not run | None | Inspect discontinuity |

#### Outcome

- Status: `not_run`
- Approved stack: None
- Rejected components: None
- Fallback selected: None
- Next action: Record the current proof-profile boundary, then run dimension registration and R0/R1 terrain transfer.

### Tests POC-002 through POC-005 — not run

No world IDs, seeds, destinations, weather states, Moss crossings, asymmetric routes, save/reload results, logs or recordings exist. Procedures and criteria are in the test matrix.

## Mechanics, continuity and effects queue

| Test ID | Requirement | Status |
|---|---|---|
| ACT-001 | Repeatable setup–arm–action–reset–cleanup lifecycle | `not_run` |
| MEC-001 | Skeleton threat, wild-wolf intervention and taming | `not_run` |
| MEC-002 | Fishing, name tag, anvil and MOSS application | `not_run` |
| MEC-003 | Moss states, routines and portal crossing | `not_run` |
| MEC-004 | Rug-origin fire route and reset | `not_run` |
| MEC-005 | Connected creeper route, fall and hiss | `not_run` |
| MEC-006 | Fatal blast and readable aftermath | `not_run` |
| VFX-001 | Portal failure and quiet collapse | `not_run` |
| VFX-002 | Delayed flash, particles and destination view | `not_run` |
| VFX-003 | Smoke, water, steam and fire continuity | `not_run` |
| CONT-001 | MATCH PATH and MATCH FRAME A | `not_run` |
| CONT-002 | Marker-foot and granite-seam continuity | `not_run` |
| CONT-003 | Final-frame asymmetry and creeper geography | `not_run` |
| AUD-001 | Exact narration/bark reuse and audio boundaries | `not_run` |
| GFX-001 | Journal, Atlas, ledger and title readability | `not_run` |
| EDIT-001 | Scene 13 omniscient reading | `not_run` |
| EDIT-002 | Moss fate remains unresolved | `not_run` |
| STB-001 | Five-panel image-model consistency comparison | `not_run` |

## Set-lock review

**Status:** Not ready.

Portal method, dependency pins, world duplication, weather, controller, camera path, Moss transfer, destructive resets and composite fallbacks have not produced evidence. Full echo dressing and destructive R4 construction remain gated.

## Completion evidence

- Completed locations: None evidenced.
- Completed builds: None evidenced.
- Implemented controller: None.
- Recorded mechanics tests: None.
- Generated storyboard images: None.
- Recorded captures: None.
- Recorded audio: None.
- Selected takes: None.
- Technically usable selected takes: None.
- Pickups: Undetermined.

Capture-log and audio-capture-log remain untouched. No capture or take-selection entry may be created until a genuine file exists and receives technical and human review.