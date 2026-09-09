# Production plan — The Portal That Nobody Made

> This is the practical plan for building, recording, and handing material to the edit. Internal shot, asset, location, capture, and risk registers are maintained for you.

## Portal implementation — research candidate

The portal effect is technically plausible with existing mods, but the combined stack is not yet production-validated. Do not treat this section as a mod lock until the proof of concept passes and its exact versions are recorded.

### Candidate baseline

- Minecraft Java Edition 1.20.1
- Fabric loader profile dedicated to this production
- Immersive Portals 5.2.0 for Minecraft 1.20.1
- Multiworld 1.12 for Fabric
- Dimensional Weather 1.1-1.20.1
- Compatible Fabric API and iCommon API builds pinned after the clean-profile launch test

No mod jar is stored in the project. Download from the official pages recorded in `.studio/internal/research/source-ledger.csv`, then record the filenames, versions and file hashes in the asset register and build log.

### Echo-world architecture

Create R0, R1, R2, R3 and R4 as separate saved overworld-like worlds. Use:

- the same seed;
- the same Minecraft version;
- the same generator;
- the same generation-affecting mods and data packs;
- the same target coordinates for the hero ravine and portal mouth.

Different seeds are not the default because the script requires the same ravine profile, lightning-shaped granite seam, cave silhouette and surface composition. The story requires different histories, not unrelated geography.

For exact continuity, generate and verify one clean master location before art direction. Back it up, then duplicate the world or required region files for each echo. Apply vegetation, water, ash, archive structures, homestead construction and destruction only after the copies exist.

### Portal topology

Use an Immersive Portals portal entity inside each crying-obsidian frame. Point it to the matching coordinates in the next echo world. The intended route is:

```text
R0 → R1 → R2 → R3 → R4
```

Keep each normal crossing one-way unless a shot explicitly requires a return pair. Do not depend on a naturally generated Nether-style portal link. The crying-obsidian frame, particles, sound, keyed behaviour, anchor activation and creeper-triggered ignition remain scripted production effects rather than documented vanilla or mod mechanics.

### Weather design

Use dimension-specific weather so R0 can be dry while R1 is raining. The proof of concept must confirm that the following are visible and stable through the opening:

- rain particles;
- destination sky and light level;
- waterfall and wet-side geometry;
- destination ambience or a controllable post-production substitute;
- correct dry-side weather around the camera.

### Proof-of-concept gate: R0 to R1

Run this before building the complete echo chain:

1. Create a clean, isolated Minecraft 1.20.1 Fabric profile.
2. Install only the candidate stack and its required libraries.
3. Record every jar filename and version.
4. Create two overworld-like worlds from the same seed.
5. Verify the hero coordinates in both worlds.
6. Set R0 dry and R1 raining.
7. Build one temporary portal and assign R1's matching coordinates as its destination.
8. Record a static view, lateral parallax move and continuous player crossing.
9. Test a tamed wolf crossing in both follow and sit/release states.
10. Save, exit, reload and repeat the view and crossing.
11. Add the intended camera, replay, shader and capture tools one at a time.
12. Record results, logs, screenshots and capture filenames in the build log.

### Acceptance criteria

The portal implementation may be locked only when:

- the destination renders clearly through the frame;
- perspective and parallax remain convincing;
- the crossing has no loading screen or visible teleport cut;
- separate dry and rainy weather states coexist;
- the wolf crosses without ownership or AI corruption;
- the portal remains intentionally one-way;
- save/reload preserves worlds and portal destinations;
- the selected capture stack does not crash or corrupt the world;
- performance is sufficient for the intended recording workflow;
- a backup can restore the last known-good state.

### Fallback ladder

Use the least invasive fallback that preserves the scene:

1. Disable shaders or incompatible visual mods during portal plates.
2. Capture clean dry-side and wet-side plates separately and composite the portal interior in post.
3. Use duplicated matched sets rather than live independently generated chunks.
4. Transfer Moss in a separate controlled plate and hide the join with blocking or sound.
5. Replace the live one-way chain with manually configured portals for each shot.
6. Research a custom compatibility or portal-controller mod only after the recorded proof of concept identifies a specific unsolved failure.

## Minimal production design

TODO: List the hero location, modular/reusable elements, lighting states, characters, props, and how scale will be implied rather than built.

## Build plan

TODO: Define build order, completion criteria, reuse strategy, and what will be simplified or cut if time expands.

## Capture plan

TODO: Describe the shot strategy, camera paths, performances, narration, ambience, pickups, file naming, and backup process.

## Required assets and licences

The candidate portal software is registered in `.studio/internal/production/asset-register.csv`. Do not promote an entry to `installed` or `approved` until the exact downloaded file and licence have been verified.

TODO: Identify every additional authored, owned, commissioned, or licensed asset and its status.

## Technical and production risks

The portal-specific blockers and fallbacks are maintained in `.studio/internal/production/risk-register.md`. The largest unresolved risk is combined-mod and capture-tool compatibility, not the absence of a plausible implementation route.

TODO: Record any additional risks capable of stopping production and the fallback for each.

## Completion record

TODO: Summarise what was actually built and captured, what was selected, and any missing pickup.
