# Production plan — The Portal That Nobody Made

> Research-first Production proposal for authoritative Script `draft-03`. Everything below is planned work. It does not evidence installation, interoperability, testing, completed builds, generated storyboard images, capture, selected takes, technical success, rights clearance or creative approval.

## Authority and scope

- This plan covers exactly one video, `The Portal That Nobody Made`, in Production.
- `03-script/script.md`, draft `draft-03`, controls all thirteen scenes, chronology, causality, continuity, narration meaning, portal topology and Moss’s unresolved R4 fate.
- Direction and Story material is informative only where it agrees with the Script. Superseded fixed-timeline, older-self-builder and wolf-rescue material must not enter Production.
- The editorial guide remains 20:38. Individual timings guide coverage and do not impose a formula.
- Public-facing language uses British English. All business figures use BRL.

## Evidence vocabulary

| Label | Meaning |
|---|---|
| Researched fact | Supported by an official or primary source recorded in the source ledger |
| Documented individual support | A release page lists the stated game version or capability; no combined-stack conclusion follows |
| Provisional recommendation | A preferred next test based on available evidence, not an approved toolchain |
| Planned test | Procedure and acceptance criteria exist, but no result exists |
| Verified result | Requires retained logs, exact artefacts, settings and review evidence; none exists yet |

All candidate stacks remain **untested**. Shared Minecraft-version labels are not evidence of interoperability.

## Script-over-context decisions

| Conflict | Production decision |
|---|---|
| Earlier material starts with Moss already present | Follow Scene 2: the protagonist arrives alone, survives, meets a wild wolf, tames it, later obtains a name tag by fishing and finally names it `MOSS`. |
| Earlier material uses a surface portal hum | Follow Scenes 2–3: ordinary mining and exposed iron cause discovery; echo-portal audio begins only after the frame is visible underground. |
| Earlier material repeats arrival at the ending | Follow Scene 13: repeat `MATCH FRAME A`, after Moss is tamed and named, as the pair begin the mining descent. |
| Earlier material requires direct anchor discharge | Follow Scenes 11–12: the protagonist prepares but never ignites the frame; the falling creeper explodes first. |
| Earlier material explains a fixed timeline and older builder | Exclude it. `draft-03` uses stable echo realities and one R4 source frame projecting the R0 receiving mouth. |
| Earlier material resolves Moss’s fate | Exclude it. R4 Moss remains absent and unseen; show no body, collar drop, death message or locating sound. |

## Provisional technical decision

Use the existing **Minecraft Java Edition 1.20.1 Fabric profile** as the production baseline, but prove the world-assembly bridge in a copied profile before committing the selected location.

The user-reported mod directory on 18 July 2026 establishes that the profile currently contains these central artefacts:

- Fabric API `0.92.11+1.20.1`;
- Immersive Portals `5.2.0` enabled, with an older `3.4.0` artefact disabled;
- Dimensional Weather `1.1-1.20.1`;
- Chunky `1.3.146`;
- Replay Mod `2.6.23`;
- Sodium `0.5.13`, Sodium Extra `0.5.9`, Indium `1.0.36` and Iris `1.7.6`;
- Tectonic `3.0.17`, WWOO `2.0.0`, Ecologics `2.2.7`, Lithostitched `1.4.11`, Fabric Seasons `2.4.2 BETA` and Seasons Extras `1.3.2 BETA`;
- the wider visual, animation, wildlife, particle and sound stack recorded in `installed-profile-inventory.csv`.

Presence in the directory is **not** evidence that the complete stack launches, records or interoperates. Disabled files remain excluded. The exact Fabric Loader and Java runtime are still unrecorded.

### World-method decision

Multiworld and iCommon are no longer the preferred architecture and are not present in the supplied profile. The selected method is:

1. scout existing seeds/worlds for the closest usable location;
2. adapt the chosen location into R0, importing missing geography when efficient;
3. preserve the approved R0 source and duplicate it into R0–R4 working saves;
4. register R1–R4 as dimensions inside one filming master;
5. copy or import the generated production chunks at zero coordinate offset;
6. create Immersive Portals only after terrain transfer and reload validation.

Immersive Portals documents `/dims clone_dimension` through its bundled dimension utility and exact destination commands, but persistence and interaction with this world-generation stack remain planned tests rather than verified results.

### 1.20.1 versus 1.21.1

| Capability | Current 1.20.1 evidence | 1.21.1 evidence | Decision |
|---|---|---|---|
| Existing production profile | Exact user-reported 1.20.1 artefact filenames | No equivalent installed profile | Remain on 1.20.1 |
| See-through portal | Immersive Portals 5.2.0 present | Not relevant to the current build | Test current artefact |
| Echo realities | Separate R0–R4 authoring saves plus custom dimensions and copied chunks | Not researched | Use the R0-first hybrid method |
| Independent weather | Dimensional Weather 1.1 present | Not researched | Test one shared fixed time and dimension-specific weather |
| World generation | Tectonic, WWOO, Ecologics and supporting libraries present | Not researched | Freeze the exact generation profile before final R0 selection |
| World editing | MCA Selector/WorldEdit workflow; exact tools still to be acquired or pinned | Not researched | Use only as needed for imports and transfers |
| Replay/camera | Replay Mod 2.6.23 present | Not relevant to current production | Test after dimension transfer |
| Performance/shaders | Sodium/Indium/Iris exact files present | Not relevant to current production | Test last; shaders remain optional |

A 1.21.1 comparison is deferred. It is not a prerequisite for scouting, R0 adaptation or the 1.20.1 proof. Reopen it only after a reproducible 1.20.1 blocker.

### Candidate proof order

1. Duplicate the current PollyMC instance as a disposable proof profile.
2. Record Java, Fabric Loader and hashes for the central enabled artefacts.
3. With the smallest workable stack, register one `mns:r1_test` dimension and verify save/reload.
4. Duplicate a tiny R0 test world, make unmistakable R1 changes and transfer the generated terrain at zero offset.
5. Add Dimensional Weather and prove common fixed time with dry R0/rainy R1.
6. Add Replay Mod 2.6.23 and record one portal view, lateral move and crossing.
7. Add Sodium, Indium and Iris in the current order; add a shader only after the no-shader pass.
8. Restore wildlife, seasons, particles, animations and sound layers in groups, preserving the first failing boundary.

No custom mod is recommended. MCA Selector, WorldEdit and any custom/static dimension definition remain unpinned workflow components until exact artefacts or files exist.

## Implementation architecture

### World and geography layer

#### R0-first authoring decision

R0 is not a separate abstract world that must be built from scratch. It is the best scouted location after the minimum story corrections.

Search both in game and through documented seed/location sources. Score each candidate against:

- ridge, clearing and homestead approach;
- ravine/descent potential;
- recognisable granite seam or a place where one can be added;
- portal chamber and corresponding surface column;
- fishing bank and survival montage access;
- `MATCH PATH`, `MATCH FRAME A` and portal-parallax camera corridors;
- how much terrain must be hidden, blended or imported;
- how much camera-visible world already exists.

A candidate does not need to contain every required feature. If the strongest landscape lacks a ravine, import a suitable ravine or cave section from another seed with MCA Selector or WorldEdit, preserve a pre-import backup and blend terrain, biome, lighting and water boundaries. Imported geography becomes part of R0 before duplication.

After the expensive shared geography is stable, preserve an approved source and create:

```text
TPNM_R0_SOURCE
├── TPNM_R0_WORK
├── TPNM_R1_WORK
├── TPNM_R2_WORK
├── TPNM_R3_WORK
└── TPNM_R4_WORK
```

`TPNM_R4_WORK` is the closest derivative: **R4 = R0 + Home + minor seasonal/state differences**. Do not rebuild the ridge, ravine or portal geography for R4.

The selected R0 source must contain every camera-visible shared feature and a pregenerated buffer around portal sightlines, landscape shots, movement routes and Replay Mod cameras. Unrelated seeds may supply imported raw geography, but the final realities must all derive from the assembled R0 source rather than being independently generated.

#### Filming-master assembly

Create `TPNM_FILMING_MASTER` from a verified R0 working copy. Register:

```text
minecraft:overworld
mns:r1_rain
mns:r2_ash
mns:r3_archive
mns:r4_home
```

For each target dimension: create/visit it once, close Minecraft completely, back up the filming master, then replace or import the approved generated terrain at zero X/Z offset. `region` is the default required dataset. Transfer `entities` only for a specific tested need, and `poi` only when villager beds/workstations or other POI behaviour matters. Stage Moss, hostile actors and portal entities in the filming master after terrain transfer wherever practical.

Whole-folder replacement is the simplest first method when a working save contains only the production area. MCA Selector becomes preferable when irrelevant exploration must be excluded or a controlled subset must be updated. Never merge live save folders casually while Minecraft is open.

### Portal layer

Preferred test path: Immersive Portals provides the live view and crossing while an independently registered world or dimension represents each echo. Exact destination commands and portal orientation must be recorded during the proof of concept.

Required topology:

`R0 unkeyed entry → R1 → R2 → R3 → R4`

`R4 completed source view → R0 cave`

`R0 entry must still continue → R1`

This asymmetric condition is a blocker-level test. If it cannot coexist live, use shot-specific portal configurations or matched destination composites. The invented keying, creeper-triggered activation, particles and delayed portal response remain VFX/story canon, not claims about vanilla Minecraft or a mod.

### Weather and time layer

Use one fixed common time across all realities unless a later isolated test proves independent time safely. Disable daylight and weather cycling for repeatable plates. Dimensional Weather is the selected first method for dry R0 and rainy R1; the custom dimensions must retain overworld-like weather capability.

R4 may differ from R0 through Fabric Seasons or controlled seasonal dressing, but this is optional and must not introduce a new full-world build. Test season persistence, portal visibility and Replay recording before relying on it. A physical dressing change or separately captured plate is the fallback.

The weather pass must show rain, destination light, waterfall and geometry through the portal from R0 and after crossing. Audio remains an isolated OBS pass even when live visual weather succeeds.

### Camera and capture layer

Locked views use numerical transforms and planned local marks. Portal-parallax shots require lateral motion; match cuts use static or exactly repeated paths. Test the already-installed Replay Mod `2.6.23` first. Add CinematicTools or another camera tool only if Replay Mod fails a specific documented shot requirement. Native or external recording software, codec, resolution and frame-rate remain unselected. A 24 fps editorial target may be used for path design, but no performance target is considered achieved.

### Composite and Blender fallback

Where live rendering fails, record separately controlled source and destination plates with identical camera geometry. Composite the destination into a tracked portal mask, preserve foreground occlusion, add restrained tear particles and keep rain/audio on destination-specific layers. Scene 13 may use modular stone-and-soil plates and matched dissolves rather than a literal continuous underground flight. Blender is a candidate for greyboxing, camera matching and depth-assisted composites; its exact version, licence record and plug-ins must be verified before use.

### Custom-development gate

No custom mod is recommended now. It becomes eligible only after:

1. an existing-tool test has a reproducible failure;
2. exact versions, logs, steps and expected versus actual behaviour are retained;
3. the composite or shot-specific configuration fallback is judged inadequate;
4. the missing behaviour is expressed as a narrow acceptance test; and
5. the human approves the added scope and any BRL cost.

## Scene synthesis

Detailed controls are in the scene implementation and test matrices.

| Scene | Preferred production route | Deterministic control | Camera/VFX route | Test gate |
|---|---|---|---|---|
| 1 | R4 night plate plus controlled smoke and dropped cargo | Fixed marks, time, weather and tagged cargo | Locked `MATCH PATH`; separate smoke if needed | CONT-001, VFX-003 |
| 2 | State-based R0 montage with separately blocked hostile-mob and wolf plates | Wild, tamed-unnamed and named states; scripted skeleton release; controlled fishing insert | Locked arrival, short montage paths, `MATCH FRAME A` | MEC-001, MEC-002, MEC-003, CONT-001 |
| 3 | Live portal discovery if proof passes | Fixed seam, iron turn, player and Moss threshold marks | Lateral parallax and threshold move; composite fallback | POC-003, MEC-003 |
| 4 | R1 copy with fixed rain and marker state | Independent weather, one-block marker and journal state | Matched arrival and R1 surface plate | POC-004, CONT-002 |
| 5 | Separate R2 and R3 states | Bare foot, L marker, block-count and journal inserts | Exact frame-foot close-ups | CONT-002, GFX-001 |
| 6 | Compact archive set and controlled portal-failure plates | Atlas page order, gravel state and Moss exit mark | Locked inserts; contracted destination composite if required | GFX-001, VFX-001 |
| 7 | Fresh R4 copy with staged mouth collapse | Incomplete-frame structure, failed ordinary-fire beat and surface marker | Matched arrival plus soft fade | POC-003, VFX-001 |
| 8 | Milestone copies of the homestead | Rug states, Moss marks, fixed weather and build modules | Repeated locked montage compositions | MEC-003, MEC-004 |
| 9 | Controlled Moss routine and separate fire-origin plate | Feed, sit, second gesture, isolated bark cue, fixed first fire block | Locked shared-room wide | AUD-001, MEC-004 |
| 10 | Same R4 fire continuity window as Scene 1 where practical | Resettable doorway, water, falling timber, removable wall and search marks | Controlled fire/steam plates and burned-state hold | MEC-004, VFX-003, CONT-001 |
| 11 | State-based final-frame construction in sacrificial chamber copy | Tagged creeper plant, exact ledge, frame states, anchor appearance and baffle marks | Brief first-person plant; locked construction fragments | MEC-005, MEC-006, CONT-003 |
| 12 | Separate choice, fall, hiss, blast, aftermath and activation plates | Scripted creeper path, fixed cue ticks, protected aftermath state and curated items | Black-frame fatal cut and delayed composite activation | MEC-005, MEC-006, VFX-002 |
| 13 | Omniscient frame approach, modular vertical transition and exact R0 repeat | Protected R0 established-pair state and one reused narration asset | Portal composite, stylised layers, `MATCH FRAME A` | CONT-001, EDIT-001, AUD-001 |

## Resettable take controller

Create the project datapack namespace `tpnm_take` before complex rehearsals. Each take exposes five functions:

1. `setup/<take_id>` restores the correct region or structure, sets game rules, establishes time/weather, removes only tagged temporary entities and creates marks.
2. `arm/<take_id>` teleports performers to marks, freezes or holds them, resets objectives, places the camera and displays a ready cue.
3. `action/<take_id>` starts a tick counter, releases only required actors and emits a synchronisation cue.
4. `reset/<take_id>` clears tagged fire, items, projectiles and temporary actors, restores the source state and returns to `arm`.
5. `cleanup/<take_id>` removes take-only marks, tags and objectives without touching persistent Moss, protected builds or the approved R0 source.

Planned objectives are `tpnm_take`, `tpnm_phase`, `tpnm_tick` and `tpnm_cue`. All temporary entities receive both a broad `tpnm.temp` tag and a take-specific tag. Marker entities identify actor, camera, landing, prop and eyeline positions.

Global take controls include fixed time/weather, `doDaylightCycle false`, `doWeatherCycle false`, `doMobSpawning false`, a recorded difficulty, and restoration of every changed game rule during cleanup. Syntax and dimension scope must be verified in the selected build.

Safety rules:

- A wild wolf, tamed unnamed wolf and named Moss are distinct continuity states. Do not silently substitute one persistent entity for another.
- Ownership, collar, name, health and sit state must be inspected after save/reload and portal crossing.
- Skeleton action is released from fixed marks; separate threat and intervention plates are preferred over natural targeting RNG.
- Fishing remains the story cause, but the production insert must not depend on waiting for an uncontrolled random catch.
- Fire uses a fixed ignition mark and backed-up room. Exact burn-fan continuity should use progressive state copies if spread is not repeatable.
- The creeper follows a connected, visible ledge-to-landing route. Fall, hiss, blast and aftermath may be separate plates.
- Dropped items are tagged or art-directed from test evidence, then checked to exclude Moss-related or continuity-breaking items.

The complete controller specification is in technical research. It is designed but not implemented or tested.

## Continuity locks

### MATCH PATH

Scenes 1, 2 and 10 use one planned camera transform, height, FOV, path centreline and travel direction. R0 morning and R4 fire-night are different set states around that invariant. Scenes 1 and 10 should be captured within one restorable R4 fire window when feasible.

### MATCH FRAME A

Create only after Moss has helped against the skeleton, been tamed, received the name tag `MOSS` and joined established routines. Preserve camera, sun direction, weather, equipment, journal condition, pack action, protagonist mark, Moss mark and action timing. Record the line once and reuse the same audio in Scene 13:

`Below the hill was only another day's work. They went together.`

### Granite seam

The seam remains natural geography. Its fork, scale and screen position identify matching coordinates in all echoes. R0’s iron vein continues beyond it and causes the turn towards the portal.

### Moss

No collar or name before its scripted beat. No R4 post-fire shot or sound may resolve Moss’s fate. The Scene 12 bark is the exact Scene 9 performance filtered as memory, not a bark located in the ravine.

### Creeper route

The Scene 11 dark ledge must physically connect to the Scene 12 landing mark. The green edge is sub-second, peripheral and unstressed. The protagonist raises flint and steel but does not ignite the frame before the blast.

## Storyboard and camera design

The text-first storyboard contains 49 planned panels, at least two for every scene, with extra coverage for portals, match frames, hostile-mob action, fire, the creeper route and Scene 13. Each ledger entry provides:

- a literal frame and 3×3 grid;
- a planned local camera position, height and FOV;
- foreground, midground and background;
- subject marks, facing and eyeline;
- movement stated as directions in words;
- lighting direction;
- environment, audio and transition;
- continuity anchor and capture purpose.

Local coordinates are design marks, not claims about an existing world. Actual Minecraft coordinates may be recorded only after the master location exists.

No storyboard image has been generated. For a later optional sketch pass, use actual Minecraft or Blender greybox screenshots as composition-locked references. The provisional first model test is ChatGPT Images 2.0, with FLUX.2 Pro as the multi-reference comparison and Midjourney as a style exploration reserve. Run only the defined five-panel consistency test before scaling.

## Location and build strategy

Scout and adapt rather than construct five landscapes. The chosen R0 location carries the expensive geography. Use imported terrain only where it closes a clear shot requirement faster than sculpting. Build only camera-safe directions and pregenerate only the production footprint plus a safety buffer.

The derivation strategy is:

| Reality | Source | Main changes |
|---|---|---|
| R0 | Scouted and corrected hero location | Survival states, Moss progression, portal receiving mouth and match frames |
| R1 | Direct R0 duplicate | Rain, waterfall/opening, denser vegetation, absent home and first marker |
| R2 | Direct R0 duplicate | Ash/scorch, exposed shelf, marker tests and reduced vegetation |
| R3 | Direct R0 duplicate | Compact archive recess, historical props, gravel and failing portal states |
| R4 | Direct R0 duplicate | Home, domestic milestones, optional minor season difference, fire/search/final-frame states |

R4 uses separately restorable milestones:

- fresh R0-like arrival;
- first roof;
- growing home;
- lived room with each rug stage;
- pre-fire room;
- burning doorway;
- breached and burned room;
- final-frame chamber;
- protagonist-free aftermath.

Do not wait for a naturally perfect seed. Do not expand a candidate merely because unused terrain exists. Do not dress all five realities before the R0/R1 transfer, weather and Replay proof has either passed or produced an approved composite recipe.

## Evidence-producing order

1. Record the current profile inventory, Java/Fabric Loader and central hashes; do not spend time on 1.21.1 unless 1.20.1 blocks production.
2. Run the smallest R0/R1 custom-dimension and chunk-transfer proof in a copied profile.
3. Add Dimensional Weather and prove dry R0 viewing rainy R1 at one fixed time.
4. Add Replay Mod 2.6.23; test portal view, crossing, reload and one rendered/captured result.
5. Scout and shortlist candidate seeds/worlds while the technical proof is still small.
6. Approve the best camera-feasible candidate and adapt it into R0; import only missing hero geography.
7. Mark the complete camera-visible footprint and pregenerate it with Chunky before duplication.
8. Preserve `TPNM_R0_SOURCE`, then duplicate R0 into R0–R4 working saves.
9. Dress R1–R3 minimally; derive R4 directly from R0 and add Home plus minor differences.
10. Assemble `TPNM_FILMING_MASTER`; transfer terrain first, validate reload, then stage actors and portals.
11. Implement the smallest datapack controller and repeat one setup–action–reset cycle twice after reload.
12. Test player and Moss crossing, then asymmetric R4→R0/R0→R1 routing.
13. Establish the no-shader performance baseline; restore optional rendering, wildlife and sound layers last.
14. Build/capture non-destructive R0 and R4 milestones before fire, blast and aftermath copies.
15. Build a text-and-greybox animatic before final narration and principal capture.

## Capture and post-production policy

- No capture filename, take, selected take or usability result exists.
- Record actual filenames only after files exist, using the approved slug/scene/shot/setup/take/date convention.
- Preserve exact world states and two independent backups where available before destructive work.
- Inspect picture, sound, UI, entity states, portal geometry and forbidden Moss evidence before a take can be considered usable.
- Live portals are conditional. Composite plates are an authored fallback, not a failed imitation.
- No narration follows the protagonist’s death.
- Keep conventional-portal, echo-portal, rain, fire, bark and synchronisation stems isolated.
- Final narration changes may improve clarity but may not add a surface hum, change causes, resolve Moss or imply survival.

## Budget and cut line

No cash spend is authorised. The planning budget records labour hours and `BRL 0 authorised` for every package until an exact quote or purchase receives human approval.

The minimum viable version retains all thirteen causal scenes, the skeleton-to-bones-to-taming chain, fishing-to-name-tag cause, both marker absences, Atlas evidence, R4 domestic life, rug growth, fire path, unresolved absence, connected creeper route, fatal interruption, delayed portal activation and `MATCH FRAME A` ending.

Cut in this order if capacity is exceeded:

1. shaders and cosmetic rendering mods;
2. generated sketch conversion after the text/greybox board;
3. extra background dressing and wide echo coverage;
4. redundant montage angles;
5. a literal continuous Scene 13 ascent, replacing it with matched modular dissolves.

Do not cut a causal scene, Moss-state transition, portal rule, match frame or creeper-route evidence.

## Rights and business controls

Exact source, publisher, licence, version, artefact name and hash must be recorded before software or third-party media enters Production. No skin, font, sound, music, plug-in or external asset is approved by this plan. Original work requires an authorship record once created. No purchase, commission or external message is authorised. Any future cost must be quoted in BRL and approved before commitment.

## Completion record

| Item | Status | Evidence |
|---|---|---|
| Production synthesis | Deepened proposal | This document and auxiliary planning registers |
| Current 1.20.1 profile | User-reported inventory recorded | Exact mod filenames are catalogued; Java, Fabric Loader, hashes and integrated behaviour remain unverified |
| 1.21.1 comparison | Deferred | Not required unless a reproducible 1.20.1 blocker appears |
| Combined stack | Untested | No launch, log, save or reload evidence |
| Take controller | Designed only | No datapack or run evidence |
| Master world and locations | Not created | Cards and modules are plans |
| Storyboard | Text-first plan complete | 49 planned ledger panels; no image generated |
| Mechanics and VFX tests | Not run | Test matrix only |
| Narration and bark | Not recorded | Reuse requirements only |
| Captures | None recorded | Capture and audio-capture logs remain untouched |
| Selected take | None | Human selection cannot occur without capture evidence |
| Technical usability | Not assessed | No captured take exists |

Production remains open. The next evidence-producing actions are a seed/location shortlist and the isolated R0/R1 custom-dimension transfer, weather and Replay proof in a copied 1.20.1 profile. Capture-log and selected-take checks must remain blocked until genuine captures exist and receive human review.