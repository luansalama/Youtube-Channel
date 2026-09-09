# Production technical research — The Portal That Nobody Made

> Research snapshot accessed 17 July 2026. This is discovery evidence and a provisional test decision, not proof that the combined stack installs, survives reloads or captures correctly. No image has been generated.

## Provisional baseline decision

Use **Minecraft Java 1.20.1 + Fabric** as the first isolated proof-of-concept baseline. It currently has an unusually clear documented intersection for the central portal and production candidates: Immersive Portals 5.2.0, Carpet 1.4.112, Axiom 5.2.1, CinematicTools 1.2.0, Dimensional Weather 1.1 and available Replay Mod builds. Multiworld also lists 1.20.1 as active. This is a test preference, not an approval: the complete stack must be installed incrementally and reloaded after every addition.

Do not move to 1.21.1 merely because some tools are newer there. Run a second compatibility-paper comparison only if a required 1.20.1 capability is absent or the integrated spike fails. The locked video needs reliable portal geometry, separate world states, weather, actors, resettable takes and camera paths more than it needs newer vanilla content.

## Primary candidates and boundaries

- **Immersive Portals 5.2.0** — official Modrinth release for Fabric 1.20.1, client and server, Apache-2.0. It provides see-through seamless portals and documents custom portal commands/datapack functionality. It does not by itself prove the story's asymmetric R4→R0 and R0→R1 routing.
  Source: https://modrinth.com/mod/immersiveportals/version/5.2.0
- **Multiworld** — official project page lists 1.20.1 as active and supports creating worlds with generators/seeds and teleporting by command. Treat its interaction with Immersive Portals as unverified until the integrated portal spike.
  Source: https://modrinth.com/project/fgvoNDL1
- **Dimension Level Data 0.1.0-1.20.1** — stores time and weather separately by dimension. Candidate when echoes are implemented as dimensions.
  Source: https://modrinth.com/mod/dimension-level-data/version/c2yUFutK
- **Dimensional Weather 1.1-1.20.1** — Fabric/Quilt release requiring Fabric API 0.92.2+1.20.1; supports vanilla rain, thunder and clear only in dimensions that permit weather. Candidate alternative or supplement, not automatically compatible with every custom-world method.
  Source: https://modrinth.com/mod/dimensional-weather/version/1.1-1.20.1
- **Replay Mod** — records sessions and provides cinematic camera paths and rendering. Use it for post-performance camera design, but validate exact build, Fabric API/Sodium/Iris intersection and entity visibility with the portal stack.
  Sources: https://www.replaymod.com/ and https://www.replaymod.com/docs/
- **CinematicTools 1.2.0+1.20.1** — candidate for authored camera paths and actor/player presentation. Its exact release lists Fabric API, GeckoLib and CreativeCore dependencies. Evaluate overlap with Replay Mod rather than assuming both should remain installed.
  Source: https://modrinth.com/mod/cinematictools/version/1.2.0%2B1.20.1
- **Carpet 1.4.112** — Fabric 1.20/1.20.1, MIT. Carpet provides technical game control, tick tools and Scarpet scripting. Use it as the first programmable layer for repeatable take setup before commissioning a custom mod.
  Source: https://modrinth.com/mod/carpet/version/1.4.112
- **Axiom 5.2.1** — Fabric 1.20–1.20.1 world editor. Use for non-destructive build variants and quick region repair only after the master-world backup procedure is proven.
  Source: https://modrinth.com/mod/axiom/version/5.2.1

## Deterministic take-controller design

Create a project datapack namespace such as `tpnm_take`. Every complex performance receives five explicit functions:

1. `setup/<take_id>` — disable random mob spawning, set time/weather/difficulty, restore or paste the correct set state, summon controlled entities with unique tags, set health/equipment/sit/AI state and teleport all performers to marks.
2. `arm/<take_id>` — freeze or hold actors, place the camera/player at its recorded transform, reset scoreboards and display a human-readable ready state.
3. `action/<take_id>` — release only the required AI or scripted movement, start timed scoreboards/Scarpet events and record a synchronisation cue.
4. `reset/<take_id>` — kill only tagged temporary entities, clear temporary items/fire/projectiles, restore the source structure/region and return to the arm state.
5. `cleanup/<take_id>` — remove take-only entities and objectives without touching persistent Moss, hero builds or protected masters.

Prefer deterministic commands and short controlled plates over natural RNG. Use vanilla `/summon`, entity tags, `/tp`, `/data`, `/execute`, scoreboards, fixed time/weather, `doMobSpawning false`, structure blocks or copied region states. Use Carpet/Scarpet where vanilla timing or actor sequencing is insufficient. Preserve genuine wolf states separately; never replace narrative continuity with an unlabelled duplicate.

### Scene-specific control priorities

- Scene 2 skeleton/wild-wolf intervention: separate skeleton, wolf and protagonist action plates are acceptable. Script the marks and release order; do not wait for natural targeting.
- Fishing/name-tag chain: schedule a controlled catch/pick-up insert while preserving the causal edit that fishing supplied the tag.
- Scenes 9–10 fire: restore from a dedicated pre-fire world copy or region state; use progressive fire-state copies if vanilla spread cannot repeat the required burn fan.
- Scenes 11–12 creeper: use a tagged creeper, exact ledge mark, controlled release and separate fall/hiss/blast/aftermath plates. The invented frame activation remains post/VFX unless a purpose-built effect is proven safer.
- Moss routines: use short sits, follows and teleports between hidden cuts; record owner, collar, health, sit and position before each setup.

## Storyboard model recommendation — no generation in this phase

Use **ChatGPT Images 2.0 / the current OpenAI image model** as the first model test for storyboard sketches because its official release emphasises multi-scene continuity, stylistic illustration, instruction following and edits that preserve composition and details. The production workflow should not ask it to invent each frame independently. First capture a crude Minecraft or Blender greybox frame with the actual camera and blocking, then transform that reference into a restrained graphite-and-ink storyboard while preserving geometry.

Use **FLUX.2 Pro** as the controlled alternative when several references must be combined; its official documentation supports multi-reference editing and explicit composition/pose control. Midjourney can remain a mood/style exploration tool, but it is not the first choice for camera-faithful boards despite its Style and Omni Reference systems.

Run only a five-panel comparison before scaling: one static dialogue/relationship frame, one portal parallax frame, one action frame, one exact match frame and one fire/aftermath frame. Approve a model only if character silhouette, Moss, camera geometry, prop placement, hand-drawn line language and aspect ratio remain acceptably consistent. Store prompts and source frames; never use a generated board as evidence that a Minecraft setup is feasible.

Sources:
- https://openai.com/index/introducing-chatgpt-images-2-0/
- https://docs.bfl.ai/flux_2/flux2_image_editing
- https://docs.midjourney.com/hc/en-us/articles/36285124473997-Omni-Reference
- https://docs.midjourney.com/hc/en-us/articles/32180011136653-Style-Reference

## Integrated proof-of-concept order

1. New isolated Prism/MultiMC-style instance; Java, launcher, Fabric Loader and Fabric API pinned.
2. Immersive Portals only; create and reload one portal, record logs.
3. Add one world/dimension method; test same-seed copies, coordinates, player crossing and asymmetric routing prototype.
4. Add independent weather/time method; prove dry source and rainy destination in one visible portal.
5. Add Carpet plus the minimal `tpnm_take` datapack; prove summon/mark/action/reset twice after reload.
6. Add either Replay Mod or CinematicTools first; test portal visibility, entity recording and one numerical camera path. Add the second only if it solves a documented gap.
7. Add Axiom and performance/rendering mods one at a time.
8. Save, exit and reload after each component. Archive latest.log, exact filenames, versions, hashes and a short screen recording.
9. Reject or replace only the component that introduces the failure. Never continue building the hero worlds on an unproven profile.

## Current evidence status

- Individual version support: researched candidate.
- Licences listed above: discovery evidence from official project pages; exact downloaded artefacts still require inspection.
- Combined stack: not tested.
- Asymmetric portal topology: not tested.
- Independent visible weather through portal: not tested.
- Deterministic actor controller: designed, not implemented.
- Storyboard model: recommended for a five-panel test, no images generated.
