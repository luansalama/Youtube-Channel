# Production technical research — The Portal That Nobody Made

> Evidence snapshot supplied through 17 July 2026. This document separates official-source findings, recommendations, planned tests and verified results. No stack, build, capture or storyboard image has been created or tested.

## Decision

Test **Minecraft Java 1.20.1 + Fabric** first. It has the strongest exact-version evidence intersection in the supplied source set. This is a provisional baseline, not a technical lock.

Do not spend production time building a 1.21.1 comparison profile unless a required capability fails reproducibly on 1.20.1. VER-121 is therefore deferred and must be triggered by a specific retained blocker, not by general uncertainty.

## Exact-version comparison

| Function | Current 1.20.1 evidence | Dependency or boundary | Decision |
|---|---|---|---|
| Game/profile | PollyMC instance targeting Java Edition 1.20.1 | Java runtime and Fabric Loader unrecorded | Current production baseline |
| Shared API | Fabric API `0.92.11+1.20.1` present | Integrated launch still unverified | Record hash; retain |
| Portal and dimension management | Immersive Portals `5.2.0` present | Bundled `/dims` capability is documented; persistence must be tested | First bridge candidate |
| Authoring worlds | Separate duplicated save folders | Ordinary file workflow, not a mod | Selected R0–R4 authoring method |
| Final echo dimensions | Registered custom dimensions plus copied/imported chunks | Dimension IDs and transfer procedure untested in this save | Selected filming-master method |
| Weather | Dimensional Weather `1.1-1.20.1` present | Requires weather-capable dimension types; portal view untested | First weather candidate |
| Pregeneration | Chunky `1.3.146` present | Radius/footprint must be chosen from shots | Pregenerate R0 before duplication |
| World generation | Tectonic `3.0.17`, WWOO `2.0.0`, Ecologics `2.2.7`, Lithostitched `1.4.11` present | Exact configs and unexplored custom-dimension behaviour unverified | Freeze configuration; transfer all visible chunks |
| Season difference | Fabric Seasons `2.4.2 BETA` and Extras `1.3.2 BETA` present | R4 use is optional; persistence/portal/replay untested | Minor R4 difference only |
| Replay camera | Replay Mod `2.6.23` present | Cross-dimensional portal recording untested | First camera path |
| Rendering | Sodium `0.5.13`, Indium `1.0.36`, Iris `1.7.6` present | No-shader baseline first | Add after transfer proof |
| Terrain transfer/edit | MCA Selector and WorldEdit candidates | Exact acquired artefacts absent | Pin only when needed |
| Recording | OBS isolated-pass method selected in production context | Exact version/encoder/settings unrecorded | Test actual outputs |
| Blender/compositing | Blender available as a creator skill/tool category | Exact version and Replay export bridge unresolved | Conditional fallback |
| 1.21.1 | No installed comparison profile | No migration need exists | Deferred |

### Why this changes the earlier recommendation

The earlier plan optimised for a theoretically clean world stack and made Multiworld the first candidate. The actual production constraint is different: the creator will scout for a near-match and cannot afford to construct five environments. The correct optimisation target is therefore the smallest edit distance from a strong existing location, followed by exact duplication and final assembly.

### Migration condition

Research or test 1.21.1 only if a required 1.20.1 capability has a reproducible version-specific failure and no controlled plate, transfer or composite fallback is acceptable.

## Candidate dependency chain

| Component | Exact current evidence | Role | Unresolved item |
|---|---|---|---|
| Fabric profile | Minecraft 1.20.1; Fabric API `0.92.11+1.20.1` | Base profile | Java, Fabric Loader and hashes |
| Immersive Portals | `5.2.0` enabled | See-through portal, exact destination and dimension registration candidate | Persistence, routing, replay and shader intersection |
| Dimensional Weather | `1.1-1.20.1` enabled | Separate dry/rain states | Dimension-type suitability and portal rendering |
| Chunky | `1.3.146` enabled | Pregenerate the production footprint | Exact centre/radius per approved R0 |
| Replay Mod | `2.6.23` enabled | Performance replay and camera paths | Portal/dimension recording and render output |
| Sodium / Indium / Iris | `0.5.13` / `1.0.36` / `1.7.6` enabled | Rendering baseline and optional shader path | Combined stability and chosen shader |
| Tectonic / WWOO / Ecologics | `3.0.17` / `2.0.0` / `2.2.7` enabled | Scouting and R0 generation character | Config freeze and custom-dimension unexplored chunks |
| Fabric Seasons / Extras | `2.4.2 BETA` / `1.3.2 BETA` enabled | Optional minor R4 distinction | State control and continuity |
| MCA Selector | Exact artefact not acquired | Selective chunk import/export and inspection | Version, Java requirement and operational proof |
| WorldEdit | 7.2.15 is an official 1.20/1.20.1 Fabric candidate | Ravine/forest import, blending, schematics and brushes | Not installed; exact artefact/hash and stack impact |
| Datapack `tpnm_take` | Not created | Take control and optional static dimension definitions | Implementation and validation |

Multiworld/iCommon are retained only as historical researched alternatives. They are not dependencies of the selected architecture.

## Implementation options

### Option A — R0 working saves consolidated as custom dimensions

1. Scout and approve the closest camera-feasible location.
2. Adapt it into R0, including imported ravine/forest/mountain/structure sections where necessary.
3. Pregenerate every camera-visible chunk plus a buffer.
4. Preserve `TPNM_R0_SOURCE` and duplicate it into R0–R4 working saves.
5. Edit the realities independently; keep R4 closest to R0.
6. Create a filming master from R0.
7. Register R1–R4 dimensions, close Minecraft and transfer generated terrain at zero offset.
8. Validate save/reload, then create portal entities and stage important actors.

Advantages: minimum landscape creation, exact shared coordinates, safe independent editing and one seamless recording save.

Unknowns: dynamic-dimension persistence, copied chunk lighting/block entities, unexplored custom-dimension generation, weather, replay visibility, entity UUIDs and portal routing.

Decision: selected architecture, still untested.

### Option B — full-folder replacement versus selective MCA import

Use full `region` replacement for the first proof and for compact working saves. It removes stale destination terrain and is simple to audit. Add `entities` or `poi` only for a documented requirement.

Use MCA Selector when the working save contains irrelevant explored areas, when only a production footprint should move, or when a later revision must replace selected chunks. Keep X/Z offsets at zero. Always back up source and destination.

Decision: full-folder terrain replacement first; selective import as an efficiency tool.

### Option C — shot-specific portal routing or matched plates

If simultaneous R4→R0 and R0→R1 routing fails, rebuild the portal destinations for separate capture windows or composite matched destination plates. This remains valid because the story requires editorial continuity, not one public technical demonstration of the topology.

### Option D — custom mod

Do not begin. A custom mod is justified only by a narrow retained failure after the selected world-transfer, portal, weather and composite routes have been tested.

## Portal and world-transfer tests

The minimum proof uses a disposable R0/R1 pair rather than a full production build:

1. Create a small R0 test world in a copied profile.
2. Duplicate it as `R1_TEST_WORK` and place unmistakable block/container changes at known coordinates.
3. In an R0-based filming test save, register `mns:r1_test` through the available dimension method and enter it once.
4. Close Minecraft completely and back up both saves.
5. Replace/import the R1 generated `region` data at zero offset. Omit `entities` and `poi` for the first pass.
6. Reopen, teleport to `mns:r1_test` and verify terrain, blocks, containers, lighting and coordinates.
7. Save, exit and repeat the verification twice.
8. Add one portal; capture a static view, a four-block lateral move and player crossing.
9. Add rain separation, then Replay Mod, then rendering additions.
10. Preserve logs, artefact hashes, world backups and a destination table.

A second controlled pass may test `entities` and `poi` separately. Duplicate UUID warnings, missing paintings/item frames, lost villagers or portal deletion are failures, not reasons to transfer every folder by default.

Do not build R2–R4 before this produces either a live pass or a documented composite/shot-specific recipe.

## Independent time, weather and season

Use a fixed common time first. Set time, disable daylight cycling and disable weather cycling in every required dimension. Dimensional Weather is the first visual weather method: R0 remains clear while R1 rains. Acceptance requires the states to persist through save/reload and remain correct while viewed through the portal.

Do not require independent dimension time for the baseline. If a scene needs a different light state, capture it in a separate controlled window or rebuild the light in post.

Fabric Seasons may provide a small R4 distinction from R0, but it is optional. Test the exact season state after duplication, custom-dimension transfer, portal viewing and Replay recording. If control is cumbersome, use local vegetation/block dressing and colour/lighting continuity rather than a full seasonal simulation.

Audio is recorded as isolated OBS passes. Visual weather success does not require live cross-dimensional audio to be accepted.

## Deterministic take-controller specification

### Namespace and state

Use datapack namespace `tpnm_take`. Proposed objectives:

- `tpnm_take`: numeric take identifier;
- `tpnm_phase`: 0 idle, 1 setup, 2 armed, 3 action, 4 reset;
- `tpnm_tick`: action-relative tick;
- `tpnm_cue`: synchronisation cue number.

Use namespaced storage for non-score state only after syntax is verified. Every temporary entity receives `tpnm.temp` and a take-specific tag. Persistent story entities receive continuity tags but are never removed by broad cleanup selectors.

Marker entities define:

- `tpnm.mark.camera`;
- `tpnm.mark.hero`;
- `tpnm.mark.wolf`;
- `tpnm.mark.skeleton`;
- `tpnm.mark.creeper_ledge`;
- `tpnm.mark.creeper_land`;
- `tpnm.mark.eyeline`;
- prop and item positions.

### Function lifecycle

#### `setup/<take_id>`

- Confirm the active world-state ID through a human-readable title or actionbar.
- Set recorded difficulty, time and weather.
- Disable daylight/weather cycles and natural mob spawning.
- Clear only entities tagged for this take.
- Restore the set from a verified structure/region copy or switch to the correct world milestone.
- Clear take-specific fire, projectiles and dropped items.
- Create or validate markers.
- Summon temporary actors with persistence and AI held, or validate the persistent Moss continuity state.
- Set the phase to setup and tick to zero.

#### `arm/<take_id>`

- Teleport the player/camera and actors to their marks.
- Apply the required facing and eyeline.
- Set sit, health, name visibility and equipment states.
- Hold actors through `NoAI`, barriers, sit state or a Scarpet controller, depending on the validated method.
- Preload required chunks if the selected tools support a documented method.
- Display `ARMED <take_id>` and emit a guide-only synchronisation cue.
- Set phase to armed.

#### `action/<take_id>`

- Set phase to action and tick to zero.
- Increment `tpnm_tick` from a central tick function.
- Release only scheduled actors at named ticks.
- Change structures, fire blocks, portal effects or audio guide cues only through the take function.
- Record a visible or audible guide cue that can be removed in the final edit.

#### `reset/<take_id>`

- Stop scheduled actions.
- Remove only take-tagged temporary actors, items, projectiles and fire.
- Restore the known source structure or reload/switch to the protected milestone for destructive scenes.
- Revalidate persistent Moss rather than recreating it silently.
- Reset scores and call `arm/<take_id>` only after the restored state passes a quick identity check.

#### `cleanup/<take_id>`

- Remove take-only tags and marker entities.
- Restore every game rule changed by setup.
- Remove guide cues and temporary objectives only when no other take needs them.
- Never delete the approved R0 source, persistent Moss, journals, protected set states or untagged entities.

### Entity handling

#### Wild wolf

Use a dedicated Scene 2 state with no collar, name or owner. Arm at a fixed mark. Release on a scheduled cue or capture its intervention separately. Natural target selection is not an acceptance criterion.

#### Tamed unnamed wolf

Create this state through a rehearsed taming transition or a verified snapshot. The collar may appear; `Moss` must not. Owner data must be inspected after reload. Do not assume direct NBT editing preserves valid ownership.

#### Named Moss

Apply the name tag visibly in the story beat, then protect the named continuity state. Log owner, collar colour, name, health, sit/follow state and coordinates during real tests. Portal transfer and save/reload each require inspection.

#### Skeleton

Use a take-tagged skeleton at a fixed mark with controlled equipment, health and release tick. Separate skeleton threat, wolf response and taming plates if paths are inconsistent. Remove arrows/projectiles on reset.

#### Creeper

Use one take-tagged creeper and connected ledge/landing marks. Test a genuine fall separately. For deterministic editorial plates, Scarpet or tick-based waypoint motion may control the visible descent, followed by a separately cued hiss. Do not claim that scripted motion is natural AI. Blast tests occur only in a sacrificial chamber copy.

#### Fire

Keep `doFireTick` disabled during setup and arm. Restore the pre-fire room, place the initial fire at the defined rug edge on the action cue and enable spread only for mechanics tests. Because spread can vary, the preferred production result is a set of progressive states that preserve the tested causal origin and final burn fan. Reset by restoring the region, not by trying to reverse individual random changes.

#### Dropped items

Clear only take-tagged items during setup. For aftermath plates, place a restrained approved set at fixed marks after studying any real blast test. Exclude name tags, collars, wolf food arrangements or any item that could resolve Moss’s fate. Record natural scatter only as reference until reviewed.

### Spawn suppression and safety

- Disable natural mob spawning throughout controlled takes.
- Keep working routes lit and barriers outside camera where practical.
- Use a sacrificial copy for fire, wall breaking, explosions and portal-state experiments.
- Never run destructive reset functions against the approved R0 source.
- Include a dry-run mode that displays target region and take ID without changing blocks.
- Make cleanup selectors require both namespace and take tags.

### Synchronisation

Use a visible actionbar count and a guide-only sound or particle cue at tick zero. Record portal, bark, creeper hiss, explosion and narration as isolated stems. The Scene 9 bark source is reused exactly in Scene 12; it is not regenerated or re-performed.

### Controller escalation order

1. Vanilla commands, functions, tags, marker entities, scoreboards and structure/region restoration.
2. Carpet/Scarpet for tick timing or actor motion a documented vanilla test cannot hold.
3. CinematicTools or another sourced actor tool for a precise failed performance requirement.
4. Composite plates and hidden cuts.
5. Custom mod only after all preceding routes produce documented inadequacy.

## World scouting, editing, transfer and reset

### Candidate scouting

Record each seed/world in `seed-scouting-log.csv`. A useful candidate minimises total production work and supports the hero shots; it does not need to contain every scripted feature naturally. Record source URL/provenance, version/generator stack, coordinates, matching features, missing features, possible imports, camera access and edit distance.

### R0 adaptation

R0 is the approved scouted location after corrections. Use MCA Selector or WorldEdit to import missing ravine, cave, forest, mountain or structure geometry when that is faster than manual construction. Blend borders, repair water/lighting, inspect biome transitions and preserve a pre-import source.

Duplicate only after the shared terrain, portal chamber, surface column and camera corridors are stable. Later common corrections should be propagated with schematics or controlled chunk replacement rather than rebuilt manually.

### Pregeneration boundary

Use Chunky to generate every chunk that may appear through a portal, landscape shot, protagonist route or Replay Mod camera, plus a safety buffer. Do this before duplication. Do not depend on Tectonic/WWOO/Ecologics reproducing unexplored terrain under custom dimension IDs.

### Transfer policy

- `region`: default terrain/build dataset; required for the selected production area.
- `entities`: default omit; add only for tested decorative or mechanical entities.
- `poi`: default omit; add only for villager/bed/workstation or other POI needs.
- close Minecraft before any save-folder operation;
- back up the filming master before each dimension replacement;
- delete/replace stale destination folders rather than casually merging them;
- keep zero coordinate offset;
- create portal entities after all terrain/entity/POI transfers.

### State protection

Protect `TPNM_R0_SOURCE`, all R0/R4 milestones and the filming master before destructive work. Use structure templates or WorldEdit schematics for bounded common modules, world/region copies for fire/blast states and explicit naming to prevent copying in the wrong direction. Never run destructive reset functions against the approved R0 source.

## Camera and replay comparison

### Replay Mod

Strength: recorded performance can be viewed through a later cinematic camera path.

Current artefact: Replay Mod `2.6.23` is present. Unknowns: portal interior rendering, custom-dimension recording, wolf state, weather, audio, Fabric API and performance-mod intersection.

### CinematicTools 1.2.0+1.20.1

Strength: exact 1.20.1 candidate and authored camera/actor purpose.

Unknowns: exact dependencies, licence, portal rendering, save/reload stability and whether it solves requirements beyond Replay Mod.

### Vanilla/spectator and locked transforms

Strength: minimum dependency path for static plates and simple tracks.

Unknowns: path interpolation and repeatable first-person action.

Decision: prove static and lateral portal plates first, then test the already-installed Replay Mod 2.6.23. CinematicTools remains an optional alternative only if Replay Mod fails a specific shot requirement.

## Performance, shaders and recording

Establish a no-shader baseline first. Record portal recursion settings, render distance, simulation distance, destination chunk state, resolution, frame-rate target, encoder, GPU, driver and frame-time evidence only when selected.

Add Sodium or Iris only from exact official releases compatible with the pinned profile. The supplied Immersive Portals note mentions compatibility but supplies no exact versions. Shaders are optional and first on the scope cut line.

Recording software and codec are unselected. A candidate such as OBS or a tool-integrated renderer requires official-source, exact-version and licence review before use. Acceptance is a playable file with stable frame pacing, correct portal rendering and synchronisation—not a nominal frame-rate setting.

## Blender and compositing fallback

Blender is a provisional category for:

- recreating the numerical camera and portal plane;
- projecting destination footage onto a card or simple depth shell;
- creating foreground occlusion masks;
- greyboxing the Scene 13 vertical route;
- transforming modular stone/soil plates through matched dissolves.

No exact Blender version, plug-in or successful workflow is claimed. If selected, record the official release, licence, colour-management settings, frame rate and render pipeline. A conventional editor/compositor may perform the same tasks if it preserves geometry more efficiently.

## Storyboard image-model comparison

| Candidate | Supplied official evidence | Composition preservation | Multi-reference support | Character/location consistency | Decision |
|---|---|---|---|---|---|
| ChatGPT Images 2.0 | Instruction following, editing, style handling and multi-scene continuity described | Promising but untested on project greyboxes | Supplied summary supports edits; exact project limit untested | Promising but unverified | First five-panel test |
| FLUX.2 Pro | Multi-reference editing and explicit composition/pose controls documented | Strong test candidate | Explicitly documented | Must be measured across five panels | Comparison candidate |
| Midjourney | Omni Reference and Style Reference documented | No supplied proof of exact camera preservation | Reference systems documented | Useful for subject/style exploration | Reserve, not first camera-faithful choice |

The workflow must transform actual Minecraft or Blender greyboxes, not invent independent scenes. The five panels test relationship, portal parallax, action, exact match and burned-room continuity. No image generation occurs in this phase.

## Test order

1. VER-120 record Java, Fabric Loader, hashes and the current enabled boundary.
2. POC-001 copied-profile launch and reload.
3. LOC-001 shortlist and approve a camera-feasible R0 candidate.
4. POC-002 R0 duplicate, custom-dimension registration and terrain transfer.
5. POC-003 portal view, parallax and player crossing.
6. POC-004 common fixed time with independent dry/rain weather.
7. CAM-001 Replay Mod 2.6.23 portal/dimension recording.
8. PERF-001 no-shader baseline, then Sodium/Indium/Iris and optional shader.
9. POC-005 asymmetric topology.
10. ACT-001 datapack lifecycle.
11. MEC-003 Moss crossing/state.
12. Composite, fire, creeper, aftermath and Scene 13 tests.

## Verified results

None. All technical statuses remain `not_run`, `research_candidate`, `evidence_gap` or `planned`.