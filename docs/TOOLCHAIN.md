# Production toolchain decision guide

This harness does not force one Minecraft version or mod stack. Pin every project's game, loader, API, mod, shader, resource-pack, Java, Blender, exporter and capture versions in the toolchain matrix and build log.

## Decision hierarchy

1. Start from locked scene requirements, not a favourite mod.
2. Find the strongest exact-version intersection using official release pages and documentation.
3. Distinguish **documented individual support** from **integrated tested compatibility**.
4. Install one component at a time in an isolated instance; save, exit and reload after each addition.
5. Keep the least complex stack that produces the locked shot. Composite or Blender plates are valid fallbacks.

## Candidate roles

- **Immersive Portals**: see-through portal geometry, crossing and custom portal commands/datapacks. Story-specific asymmetric routing still requires a spike.
- **Multiworld or a custom-dimension method**: isolated echo states and seeds. Do not assume compatibility with a portal renderer.
- **Dimensional Weather**: first candidate for dimension-specific vanilla weather where the chosen dimension type supports it. Keep one fixed common time unless a specific production requirement justifies another tool.
- **Replay Mod**: record/replay sessions, entity spectating, keyframed camera paths and rendering.
- **CinematicTools**: authored cinematics and actor/player presentation; compare against Replay Mod rather than automatically stacking both.
- **Carpet/Scarpet**: technical timing, scripted setup and programmable take control before a custom mod is considered.
- **Axiom / WorldEdit**: fast, reversible world and region editing. Keep untouched masters.
- **Blender + Mineways/MCprep**: controlled inserts, impossible transitions, VFX and composite plates after a small scale/material test.

## Deterministic take controller

Every complex take should have documented `setup`, `arm`, `action`, `reset` and `cleanup` procedures. Prefer vanilla commands/datapack functions, entity tags/NBT, scoreboards, fixed time/weather, spawn suppression, structure/region resets and Carpet/Scarpet. Use actor/NPC tools only where they solve a defined gap. Commission a custom mod only after the test matrix proves that these layers cannot deliver the required performance.

## Storyboard workflow

The storyboard is text-first and accessible without mental imagery. Every panel records camera, composition, blocking, depth layers, movement, lighting, continuity, transition and audio. Later sketches should begin from real Minecraft/Blender greybox screenshots and use reference-driven image editing to preserve geometry. Run a five-panel model consistency test before scaling. Never treat a generated sketch as proof of in-game feasibility.

## Version manifest

```text
Minecraft Java:
Java runtime:
Launcher/instance:
Fabric Loader/API:
Mods, exact files and hashes:
Dependencies:
Shaders/resource packs:
World/seed/generator:
Capture resolution/FPS:
Replay/camera tool:
Datapack/Scarpet revision:
Export/Blender bridge:
Blender/renderer:
Editing application:
Audio tools:
```

## Primary reference starting points

- Immersive Portals: https://modrinth.com/mod/immersiveportals
- Replay Mod documentation: https://www.replaymod.com/docs/
- Carpet: https://modrinth.com/mod/carpet
- Axiom documentation: https://axiomdocs.moulberry.com/
- CinematicTools: https://modrinth.com/mod/cinematictools
- Multiworld: https://modrinth.com/project/fgvoNDL1
- Dimension Level Data: https://modrinth.com/project/bkJ2cuX0
- Dimensional Weather: https://modrinth.com/project/Z8Eq3K2Z
- WorldPainter: https://www.worldpainter.net/
- Mineways: https://www.realtimerendering.com/erich/minecraft/public/mineways/
- MCprep: https://theduckcow.com/dev/blender/mcprep/
