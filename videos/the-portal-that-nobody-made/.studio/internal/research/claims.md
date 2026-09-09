# Claims and evidence map

Use this map for technical facts, licences, business decisions and explicit evidence gaps. Draft-03 story canon is separated from real-world claims.

## Supported production claims

### C-P01 — See-through portals and exact destinations are documented capabilities

**Claim:** Immersive Portals documents seamless see-through portal travel and a command-level method for assigning a destination dimension and position.

**Support:** SRC-003, SRC-004 and SRC-012.

**Use:** Justifies an isolated live-portal proof before defaulting to compositing or custom development.

**Boundary:** It does not prove custom-dimension persistence, R0-derived terrain transfer, asymmetric routing, destination weather, wolf transfer, replay visibility, shader compatibility or stable capture.

### C-P02 — Named custom dimensions can be registered without Multiworld

**Claim:** Immersive Portals documents bundled dimension-management commands, including cloning an overworld-like generator/type into a new named dimension.

**Support:** SRC-027.

**Use:** Register `mns:r1_rain` through `mns:r4_home` inside the filming master before transferring R0-derived terrain.

**Boundary:** The command clones generation configuration, not existing blocks or entities. Dimension persistence, custom worldgen behaviour and copied-region acceptance remain proof-of-concept questions. Multiworld is not selected.

### C-P03 — Dimension-specific weather has a selected first candidate

**Claim:** Dimensional Weather `1.1-1.20.1` is intended to separate vanilla weather by dimension. Dimension Level Data `0.1.0-1.20.1` remains a historically researched alternative, but it is not required by the selected baseline.

**Support:** SRC-007, SRC-008 and SRC-014.

**Use:** Test dry R0 viewing rainy R1 while all realities use one fixed common time.

**Boundary:** Portal-view rendering, persistence and integration with the final dimension method remain unverified. Add another time/weather mod only after a specific retained failure.

### C-P04 — R0 may be a scouted and assembled production location

**Claim:** Reusing one approved generated source is the correct continuity control; the source does not need to be a hand-built neutral world.

**Support:** SRC-009, SRC-010 and user production decision SRC-032.

**Use:** Scout existing seeds/worlds, adapt the strongest candidate directly into R0, import missing hero geography when efficient, then duplicate the completed shared footprint into R1-R4 working saves.

**Boundary:** Imported authored worlds or schematics require provenance and usage rights. All final realities must derive from the assembled R0 source; independently generated realities are not continuity-safe.

### C-P05 — Carpet is an existing programmable control candidate

**Claim:** Carpet `1.4.112` lists Fabric support for Minecraft 1.20/1.20.1 and includes technical control with Scarpet scripting.

**Support:** SRC-018.

**Use:** Second control layer after vanilla commands and the project datapack.

**Boundary:** No exact actor sequence, fake-player route, tick behaviour or compatibility with the proposed stack has been tested.

### C-P06 — Axiom is an existing 1.20.1 world-editing candidate

**Claim:** Axiom `5.2.1` lists Fabric support for Minecraft 1.20–1.20.1.

**Support:** SRC-019.

**Use:** Candidate for build variants and manual region repair after the master backup procedure is proven.

**Boundary:** It is not the sole reset or backup system. Exact licence, artefact and stack stability are unresolved.

### C-P07 — Replay Mod is the selected first camera route

**Claim:** The user-reported profile contains Replay Mod `2.6.23` for Minecraft 1.20.1, while CinematicTools has a researched `1.2.0+1.20.1` candidate release.

**Support:** SRC-015 through SRC-017 and installed-profile evidence SRC-032.

**Use:** Test the installed Replay Mod first for numerical paths, entity visibility and portal capture. Consider CinematicTools only if a specific shot requirement fails.

**Boundary:** The local jar hash, launch state, portal/dimension recording and render output remain unverified. CinematicTools’ dependency pins remain unresolved.

### C-P08 — The exact 1.20.1 evidence intersection is stronger than the supplied 1.21.1 evidence

**Claim:** The supplied sources contain exact 1.20.1 candidates for the central portal, world, weather, scripting, editing and one camera path, but contain no exact 1.21.1 candidate intersection.

**Support:** SRC-006, SRC-008, SRC-012, SRC-014 and SRC-017 through SRC-019; missing-evidence record SRC-024.

**Use:** Select 1.20.1 as the first proof-of-concept baseline.

**Boundary:** This is an evidence-completeness decision. It is not a claim that 1.21.1 is less capable, unsupported or incompatible.

### C-P09 — A reference-first image-editing comparison is justified

**Claim:** The supplied official summaries support testing ChatGPT Images 2.0 for instruction-following and edits, FLUX.2 Pro for multi-reference editing and Midjourney for reference/style systems.

**Support:** SRC-020 through SRC-023.

**Use:** Run a five-panel screenshot-to-graphite-board comparison after real greyboxes exist.

**Boundary:** No project image has been generated. Model consistency, exact composition preservation, terms and production suitability remain unverified.

### C-P10 — Pregenerated terrain data can be treated as dimension input

**Claim:** Official FTB implementation documentation uses `region` MCA files at minimum, with `entities` and `poi` as optional datasets, to populate custom dimensions.

**Support:** SRC-029.

**Use:** Supports a controlled R0-derived terrain-transfer proof into the final R1-R4 dimension folders.

**Boundary:** This is implementation precedent, not a verified result for the project save. Minecraft must be closed, backups retained and reload behaviour tested.

### C-P11 — Selective chunk transfer and inspection tooling exists

**Claim:** MCA Selector documents selecting/exporting Java Edition chunks and working with region, entity and POI data.

**Support:** SRC-028.

**Use:** Import a ravine or limit final transfers to camera-visible chunks while preserving coordinates.

**Boundary:** Exact local version and workflow are untested; the tool can modify or delete world data and therefore requires backups.

### C-P12 — The production footprint can be pregenerated

**Claim:** Chunky documents pregeneration based on a selected world/dimension, centre, shape and radius.

**Support:** SRC-030 and user-reported installed file in SRC-032.

**Use:** Generate every portal sightline, landscape shot, route and Replay camera buffer before R0 duplication.

**Boundary:** The final radius is a shot-design decision. Pregeneration does not prove custom-dimension terrain generation will match outside transferred chunks.

### C-P13 — An in-game 1.20.1 terrain editor is available

**Claim:** WorldEdit has an official Fabric 1.20/1.20.1 release and is designed for in-game map editing.

**Support:** SRC-031.

**Use:** Candidate for ravine/forest import, terrain blending, brushes and common schematics.

**Boundary:** It is not installed or tested in the supplied profile and must not replace source backups.

## User-locked production decisions

- R0 will be found through seed/world scouting and adapted rather than constructed as a neutral master.
- Missing geography may be copied from another seed and blended into R0.
- R1-R4 are duplicated working saves derived from the approved R0 source.
- R4 is geographically closest to R0 and adds Home plus minor seasonal/state differences.
- The final recording environment is one filming master containing R0 and imported R1-R4 dimensions.
- These are workflow decisions, not claims that the transfer has already succeeded.

## Provisional engineering inferences

### C-I01 — Existing tools should be tested before custom development

Immersive Portals, duplicated R0 working saves, registered custom dimensions, controlled terrain transfer, Dimensional Weather, vanilla commands and a project datapack collectively make an existing-tool proof reasonable.

This is an inference from separate capabilities, not evidence that the stack works together. A custom mod remains deferred until a retained test isolates a specific unmet requirement.

### C-I02 — Live and composite portal routes should be designed in parallel

The live route promises correct parallax and continuous crossing, while matched plates provide a controlled fallback for weather, topology, replay and performance failures. Designing both does not assert either has passed.

### C-I03 — Progressive fire and aftermath states are safer than relying on RNG

The Script needs a legible rug-to-timber burn fan and reproducible continuity, not a documentary record of uncontrolled fire spread. If the exact mechanism is not repeatable, state-based plates preserve the scripted cause without claiming a continuous simulation.

## Unresolved technical claims

The following must not be written as facts or successful results:

- the complete 1.20.1 stack launches or reloads;
- the user-reported mod directory launches as a stable integrated production profile;
- registered custom dimensions persist and accept the copied/imported R0-derived terrain;
- copied terrain retains required blocks, block entities, lighting and coordinates after reload;
- optional entity/POI transfer avoids duplicate UUIDs and does not delete portal entities;
- the R4→R0 view can coexist with R0→R1 entry;
- R1 rain, light and particles render correctly through an R0 portal;
- a named tamed wolf crosses while retaining owner, name, collar, pose and health;
- Replay Mod 2.6.23 records the portal and all entities correctly; an alternative camera tool has not been justified;
- Sodium, Iris, shaders or capture software operate with acceptable performance;
- vanilla fire creates the required rug-to-timber fan repeatably;
- the planned skeleton/wolf action, fishing insert or creeper route is repeatable;
- a creeper blast leaves the required frame and baffle geometry;
- an anchor flashes or an echo frame activates because of that blast;
- the Scene 13 transition reads as omniscient rather than post-death consciousness;
- a 1.21.1 migration is needed or superior for this production;
- any storyboard model preserves the project’s character and location consistency.

## Draft-03 story canon, not technical claims

- R0–R4 are stable echo realities with corresponding geography and incompatible histories. Their production assets derive from one approved R0 source, but that authoring method is not part of the fiction.
- An unkeyed crying-frame entry advances to the next mouth.
- The completed R4 source frame projects the R0 receiving mouth.
- Builder presence at ignition keys a route to `FIRST THRESHOLD`.
- The protagonist prepares the frame but a falling creeper explodes before he ignites it.
- The explosion kills the protagonist.
- The charged anchor gives a later violet flash and the portal activates too late.
- The Scene 13 camera is omniscient audience presentation.
- R4 Moss’s fate remains unresolved.

These are fictional rules or scripted events. Crying-frame travel, keying, creeper-triggered activation and the delayed frame response must never be presented as vanilla Minecraft behaviour or verified mod behaviour.

## Superseded context excluded from Production

- one fixed timeline;
- an older version of the protagonist constructing the opening portal;
- direct anchor discharge by the protagonist;
- a surviving protagonist rescuing Moss after the fire;
- a final image of the pair walking away from a burned home.

Those ideas remain historical development context and cannot override `draft-03`.

## Evidence gaps and contradictions

- The exact 1.20.1 central releases are documented individually, but there is no integrated proof. This is not a source contradiction; it is missing interoperability evidence.
- A 1.21.1 comparison remains incomplete but is intentionally deferred because the current 1.20.1 profile and workflow are selected. Missing migration research is no longer a production blocker.
- Immersive Portals release notes mention Sodium/Iris compatibility without supplying exact production pins. Those tools remain optional and last in the test order.
- Dimensional Weather is the selected first method. Use one common fixed time; do not add another time/weather mod without a specific failed requirement.
- Replay Mod 2.6.23 is already present and is the first camera route. Add an alternative only after a specific failed criterion.
- Exact recording, Blender, shader, codec, driver and operating-environment evidence is absent.

## Promotion rule

A claim may move from planned or provisional to verified only when the build log records the exact version, source, artefact name and hash; the test matrix procedure is executed; logs and visual evidence are retained; save/reload is repeated where relevant; and a human reviews the acceptance criteria. No supplied evidence meets that threshold yet.