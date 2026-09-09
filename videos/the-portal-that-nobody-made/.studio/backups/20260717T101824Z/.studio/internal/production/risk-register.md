# Risk register

| Risk | Probability | Impact | Trigger | Mitigation | Fallback | Owner |
|---|---:|---:|---|---|---|---|
| Immersive Portals, Multiworld and Dimensional Weather do not operate together | Medium | Blocker | Launch failure, crash, missing destination world, or portal cannot target a Multiworld world | Test only the three candidate mods and required libraries in a clean 1.20.1 Fabric profile; pin exact versions; add other mods one at a time | Replace Multiworld with another registered-dimension method, or research a narrow compatibility/custom controller mod after logging the failure | Luan |
| Destination weather is not visible or is visually incorrect through the portal | Medium | High | R1 is raining after crossing but the R0 portal view is dry, incomplete, incorrectly lit or unstable | Verify weather state before adding shaders; test rain particles, sky, lighting and audio separately | Composite a separately captured rainy R1 plate into the portal surface | Luan |
| Portal view or crossing fails after save/reload | Low–Medium | High | Destination, orientation, portal shape or one-way state changes after reopening the world | Export commands/configuration, record NBT or setup steps, and make a known-good backup after each stable milestone | Rebuild portals from the recorded setup before each capture session | Luan |
| Tamed wolf transfer loses ownership, name, pose or AI state | Medium | High | Moss does not cross, duplicates, becomes untamed, teleports late, stands after a sit command, or becomes unsafe | Run isolated follow, sit/release, lead and repeated-crossing tests; capture safety takes | Capture Moss in a controlled destination-side plate and conceal the handoff with framing, occlusion or sound | Luan |
| Replay, free-camera, shader or capture tools conflict with portal rendering | High | High | Crash, missing portal interior, clipping, broken particles, incorrect camera transform or corrupted replay | Establish a vanilla-render baseline; add one capture tool at a time; retain logs and a compatibility matrix | Record portal plates without the conflicting tool, use live camera paths, or composite clean plates | Luan |
| Portal rendering performance is too low for stable capture | Medium | High | Frame-time spikes, chunk-loading stalls or inconsistent motion at target settings | Reduce portal render distance/recursion, pre-load destination chunks, remove shaders and close background tools | Capture portal interior and foreground as separate locked plates | Luan |
| Echo terrain does not match closely enough | Low if controlled | High | Ravine, granite seam, cave silhouette or surface frame differs between R0–R4 | Use one seed and identical generator configuration; verify coordinates before building; duplicate a clean master world or region files | Build matched hero-location sets manually and use them only for portal/cave shots | Luan |
| Art direction contaminates the clean master or another echo | Medium | High | R0 changes appear in R1–R4, files are copied in the wrong direction, or a destructive edit reaches the master | Make the master read-only where practical; use explicit world names; back up before every copy or destructive operation | Restore the affected echo from the last verified master-derived backup | Luan |
| An unintended return portal breaks the story's one-way chain | Medium | Medium–High | Crossing creates or exposes a reverse mouth, or the player can immediately return | Use controlled portal entities and remove connected portals; test both faces and both directions | Block or hide the reverse side for capture; use shot-specific portal setup | Luan |
| A candidate mod update changes behaviour mid-production | Medium | High | Launcher updates a jar, a config resets, or an existing world opens under a new build | Disable automatic updates; archive exact jar filenames, hashes, configs and loader version after validation | Restore the locked profile and known-good world backup | Luan |
| Invented activation mechanics are mistaken for vanilla or documented mod behaviour | Low | Medium | Script, description or production notes present keyed frames, anchor activation or creeper ignition as factual mechanics | Keep them labelled as invented canon in research, script and release checks | Reword narration/description and use controlled effects or compositing | Luan |

## Scope tripwires

- Do not commission or build a custom mod before the R0-to-R1 proof of concept identifies a specific capability gap.
- Do not switch the echoes to different seeds merely to create variation; that sacrifices the matching geography required by the script.
- Do not build all five echo worlds before the two-world portal, weather, wolf and capture test passes.
- Do not add shaders, ReplayMod or unrelated content mods until the minimum stack works and is backed up.
- Do not claim that crying obsidian, anchors, builder keys or creeper ignition are vanilla or provided by the candidate mods.
- Stop production and restore a backup after any unexplained world, entity or portal-state corruption.

## Rights and provenance risks

- Install mods only from the official project or release pages recorded in the source ledger.
- Record each exact file, version, source URL, licence and hash before production use.
- Do not redistribute mod jars inside the project or a downloadable production package unless the relevant licence and distribution terms have been reviewed.
- Keep any modified configs, commands and original production assets separate from third-party binaries.

## Technical failure recovery

1. Preserve a clean Minecraft profile containing only the validated portal stack.
2. Preserve an untouched master world and dated backups of each echo.
3. Record portal commands, coordinates, orientation, destination world IDs and weather commands.
4. Keep crash reports, `latest.log`, screenshots and a short reproduction note for every blocker.
5. Restore the last known-good profile and world before attempting a version change.
6. Test version changes on copies, never on the only production world.
