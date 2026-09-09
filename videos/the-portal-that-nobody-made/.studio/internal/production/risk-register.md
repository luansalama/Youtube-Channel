# Risk register

| Risk | Probability | Impact | Trigger | Mitigation | Fallback | Owner |
|---|---:|---:|---|---|---|---|
| Unnecessary migration research consumes production time | Medium | Medium | Work pauses for a 1.21.1 comparison without a specific 1.20.1 blocker | Keep VER-121 deferred and tie migration to a retained failure | Remain on the current 1.20.1 profile | Luan |
| Current profile boundary is not reproducible | Medium | Blocker | Java/Fabric Loader, duplicate jars or hashes are unknown when a proof fails | Complete VER-120 from the copied PollyMC profile | Reduce to the minimum exact bridge stack | Luan |
| Portal, custom dimensions, weather and replay do not operate together | Medium–High | Blocker | Launch failure, missing dimension, invalid destination, weather corruption or replay defect | Add the selected bridge layers one at a time in a copied profile and reload after each | Composite destination and use shot-specific portal states | Luan |
| Registered dimensions do not persist or accept transferred terrain | Medium–High | Blocker | Dimension disappears, regenerates or ignores copied chunks after reload | Run POC-002 with unmistakable block/container markers before dressing realities | Static dimension definitions, full-folder replacement or composites | Luan |
| Asymmetric R4→R0 view and R0→R1 entry cannot coexist live | High | Blocker | R0 entry returns to R4 or another unintended destination | Record all faces/directions in POC-005 | Use shot-specific portal configurations or composites | Luan |
| R1 weather is absent or incorrect through R0 opening | Medium | High | Rain, light or waterfall differs before and after crossing | Test without shaders with fixed states | Composite rainy R1 plate and rebuild audio | Luan |
| Dimension-specific weather fails or conflicts with fixed time | Medium | High | R0/R1 weather is shared, corrupted or wrong through the portal | Keep one fixed common time; test Dimensional Weather alone before adding any alternative | Use controlled weather plates or local visual dressing | Luan |
| Portal state changes after save/reload | Medium | High | Destination, shape or orientation changes | Record commands, orientation and IDs; repeat after reload | Rebuild shot portals from recorded setup or composite | Luan |
| Portal performance is unstable | Medium–High | High | Frame spikes, chunk stalls or clipping occur | Preload required chunks, reduce recursion/distance and establish no-shader baseline | Capture foreground/destination separately | Luan |
| Replay Mod fails to record portal or cross-world entities | High | High | Interior disappears, Moss is missing or replay corrupts | Test installed Replay Mod 2.6.23 after the no-camera portal baseline; add an alternative only for a retained failure | Locked gameplay, spectator paths or matched plates | Luan |
| Shaders obscure clues or destabilise capture | Medium | Medium–High | Seam, marker, rain or frame interior becomes unreadable | Test last and review at delivery size | Remove shaders; use vanilla lighting/post grade | Luan |
| Recording tool, codec or hardware cannot hold usable pacing | Medium | High | Dropped/duplicated frames or corrupted output | Select settings through PERF-001 and inspect actual files | Lower settings, offline render or layered plates | Luan |
| Datapack reset affects the wrong world or entities | Low–Medium | Blocker | Cleanup selector reaches persistent Moss or protected build | Require namespace plus take tag and display world/region before changes | Restore verified milestone and revise selector | Luan |
| Structure restoration does not preserve portal or wolf state | Medium | High | Portal entities, owner data or block entities drift | Keep those systems outside untested structure assumptions | World/region milestone copies and explicit entity validation | Luan |
| Approved R0 source or sole milestone is contaminated | Medium | Blocker | Work is copied in the wrong direction or destructive capture reaches source | `R0_SOURCE` naming discipline, read-only backup and verified independent copies | Restore the last verified R0-derived copy | Luan |
| Echo geography drifts | Low if controlled | High | Seam, cave or surface profile differs | Derive every working save from approved R0 and keep zero-offset transfers | Re-transfer the affected chunks or build a matched hero shell | Luan |
| Scouted location creates more work than expected | Medium | High | Camera access, portal column or missing terrain proves expensive after selection | Score candidates by shot coverage and edit distance before approval | Reject candidate or import only the missing hero geography | Luan |
| Imported ravine/terrain has visible seams or broken lighting/water | Medium | High | Chunk/biome borders, floating blocks, light errors or water discontinuities appear | Preserve pre-import backup; blend and inspect from every hero camera | Re-import a smaller section or sculpt a bounded ravine locally | Luan |
| Authored downloaded map/schematic lacks publication rights | Medium | Blocker | A third-party world file is used without source or permission | Record provenance and terms before import | Use only a seed reference or create/import original geometry | Luan |
| Unexplored custom-dimension chunks generate differently | High if visible | High | Portal or Replay camera loads terrain beyond the transferred footprint | Pregenerate all camera-visible R0 chunks plus a buffer before duplication | Expand R0, pregenerate and retransfer affected regions | Luan |
| Save folders are copied while Minecraft is open | Low–Medium | Blocker | session lock, partial write or corrupted region appears | Close game/launcher process and verify backup before every transfer | Restore the pre-transfer filming master | Luan |
| Entity or POI transfer creates duplicates or deletes portals | Medium | High | UUID warnings, missing entities, villager state loss or portal disappearance | Transfer `region` first; test `entities` and `poi` separately; create portals last | Restage actors/props in filming master and omit optional folders | Luan |
| R4 drifts too far from R0 | Medium | Medium–High | New terrain work makes the final reality feel unrelated | Enforce `R4 = R0 + Home + minor differences` in location/state review | Revert shared geography and keep the distinction local/seasonal | Luan |
| MATCH PATH drifts | Medium | High | Camera, FOV, light or path direction differs | Use one numerical camera and reference overlay | Rebuild visible dressing around one source plate | Luan |
| MATCH FRAME A cannot be repeated | Medium | Blocker | Moss, kit, journal, light or pack timing differs | Protect the R0 established-pair state and one narration master | Reuse the Scene 2 source image/continuation where feasible | Luan |
| Repeated narration is recorded twice | Low | High | Timing, inflection or room sound differs | Record once and place the same asset twice | Replace both placements from one approved master | Luan |
| Granite seam becomes obscure or symbolic | Medium | Medium–High | Dressing hides the natural fork or narration overstates it | Preserve silhouette and stable screen position | Add a short neutral orientation insert | Luan |
| Wild-wolf and skeleton action is unclear | Medium–High | High | Paths collide, targeting fails or collar appears early | Use marks and separate controlled plates | Join threat, intervention and taming editorially | Luan |
| Fishing capture depends on uncontrolled luck | High | Medium | Schedule stalls or catch is unreadable | Plan controlled catch/pick-up insert while retaining fishing cause | Inventory insert joined to genuine fishing action | Luan |
| Moss’s name, collar or owner state is wrong | Medium | High | Incorrect continuity state enters shot | Maintain separate wild, tamed-unnamed and named checks | Replace plate from correct protected state | Luan |
| Moss fails portal crossing or reload | Medium–High | High | Duplication, loss, pose or owner change | Run MEC-003 before hero capture | Destination-side Moss plate with concealed handoff | Luan |
| Fire does not follow the rug-to-timber route | High | Blocker | Spread stalls, accelerates or destroys evidence | Repeat tests from exact backed-up room | Progressive states with tested origin and approved burn fan | Luan |
| Destructive capture destroys the only lived homestead | Medium | Blocker | Fire, wall break or blast begins without restore proof | Verify independent pre-fire and burned copies | Restore latest verified milestone | Luan |
| Edit resolves Moss’s fate | Medium | High | Body, collar-like drop, death text or locating sound appears | Run EDIT-002 on every relevant plate and stem | Remove or replace offending evidence | Luan |
| Creeper route is invisible or too obvious | Medium | Medium–High | Edge cannot be found on rewatch or acts as a reveal | Review sub-second plant at delivery size without sting | Adjust duration/contrast within Script restraint | Luan |
| Creeper fall and hiss cannot hit timing | Medium–High | High | It misses, lands early or fails to ignite | Test route and cues separately with tagged actor | Separate glimpse, fall, landing, hiss and reaction plates | Luan |
| Blast fails to kill protagonist or destroys all readable geometry | High | Blocker | Damage is insufficient or frame disappears | Test sacrificial chamber with recorded settings | Black fatal cut plus art-directed aftermath | Luan |
| Aftermath items imply false evidence | Medium | High | Items include a tag, collar-like object or impossible inventory | Approve a restrained list and fixed marks | Remove items and use a simpler plate | Luan |
| Delayed activation is mistaken for vanilla behaviour | Medium | High | Production/publication wording presents it as factual | Label it invented canon in every plan and review | Revise VFX and release language | Luan |
| Atlas pages retain superseded direct-discharge wording | Medium | High | Page says the protagonist must discharge the anchor | Build pages from the seven Script labels only | Replace insert before picture lock | Luan |
| Portal sound attracts R0 protagonist from surface | Medium | High | Hum appears in Scene 2 or Scene 13 surface audio | Keep isolated stems and full-sequence audio review | Rebuild underground-only sound in post | Luan |
| Scene 13 suggests post-death consciousness | Medium | High | Camera begins at eye height or carries personal sound | Start on an external protagonist-free plate and use environmental movement | Shorter environmental dissolves | Luan |
| Storyboard generation changes geometry or canon | High if unconstrained | Medium | Model invents props, characters, Moss evidence or camera angle | Reference-first five-panel test and overlays | Keep text/greybox boards only | Luan |
| Third-party rights remain unclear | Medium | Blocker | Skin, font, sound, music, mod or plug-in enters use without evidence | Record exact source, owner, licence and permitted use | Replace with original or verified alternative | Luan |
| Scope exceeds solo capacity | Medium–High | High | Full-world dressing, custom code or redundant coverage delays causal scenes | Enforce budget cut line and proof gates | Reduce cosmetic coverage and use modular plates | Luan |
| Storage failure removes a world state or capture | Medium | Blocker | Sole copy corrupts or is overwritten | Verify working and independent backup copies before destructive work | Restore latest verified state and recapture | Luan |
| A take is selected without evidence | Low | Blocker | Selection is recorded without an existing playable capture and review | Require actual file, technical inspection and human decision | Leave capture/selection records untouched | Luan |

## Scope tripwires

- Do not build all five echoes before POC-003 and POC-004 pass or yield an approved composite recipe.
- Do not spend time on 1.21.1 unless a retained 1.20.1 blocker triggers VER-121.
- Do not commission or build a custom mod before an existing-tool test isolates a precise missing capability.
- Imported raw geography may come from another seed, but all final realities must derive from the assembled and approved R0 source.
- Do not add shaders before the no-shader baseline is stable.
- Do not capture direct anchor discharge as story action.
- Do not add a surface portal hum in R0.
- Do not burn, break or explode the only copy of a set state.
- Do not use paid or uncleared assets without human approval; quote costs in BRL.
- Stop after unexplained world, entity or portal corruption and preserve logs before changing versions.

## Rights and recovery controls

1. Obtain software only from recorded official project or release pages.
2. Record exact artefact, version, source, licence and hash before use.
3. Keep original configs, datapacks, graphics and builds separate from third-party binaries.
4. Preserve the copied proof profile, approved R0 source, filming master and verified milestones.
5. Retain crash reports, logs, screenshots and concise reproduction notes for each blocker.
6. Test changes on copies, never the sole production state.