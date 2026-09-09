# Sound plan — The Portal That Nobody Made

> Production revision: 17 July 2026  
> Minecraft profile: Java Edition 1.20.1, Fabric  
> Confirmed capture decision: Replay Mod for picture and timing; OBS Studio for isolated real-time Minecraft audio passes.

## 1. Locked production decision

The final game-audio workflow is **OBS isolated Minecraft passes**.

- Replay Mod `1.20.1-2.6.23` supplies the saved performance, camera path and high-quality picture render.
- OBS captures the Minecraft application audio while the same Replay Mod camera path is played at normal speed.
- Each OBS recording contains one deliberately isolated sound layer or cue group.
- Sound Controller presets and Minecraft category levels create the isolation.
- Sound Physics Perfected remains active when the selected pass needs final in-world occlusion, directionality and reverberation.
- Story-critical cues are isolated more narrowly than ordinary Minecraft sound categories.
- Narration, music and editorially designed effects remain separate post-production assets.

ReplayMod Audio Render is **not part of the approved final workflow**. Keep its jar only for optional comparison tests. Disable it in the production sound-capture clone so it cannot introduce an unnecessary render hook or configuration variable.

Recommended disabled filename:

```text
replaymodaudiorender-0.1.0+1.19.3.jar.disabled
```

This decision does not claim that ReplayMod Audio Render is incompatible. It removes an unused component from the controlled production profile.

## 2. Current installed sound-relevant stack

### Approved for testing in the sound-capture clone

| Installed artefact | Production role | Current decision |
|---|---|---|
| `replaymod-1.20.1-2.6.23.jar` | Saved performance, replay timeline and camera path | Retain |
| `sound_physics_perfected-1.17.3+1.20.1-fabric.jar` | Occlusion, reverberation, directionality and material response | Retain provisionally; tune conservatively |
| `PresenceFootsteps-1.10.1+1.20.1.jar` | Material-aware player movement and tactile surface identity | Retain provisionally |
| `soundcontroller-1.2.3-mc1.20.jar` | Per-sound identification, muting, volume control and capture presets | Retain; required production utility |
| `Drip Sounds-0.5.2+1.20.4-Fabric.jar` | Restrained cave drip detail | Retain provisionally; the release supports 1.20–1.20.4 |
| `cloth-config-11.1.136-fabric.jar` | Configuration dependency | Retain |
| `yet_another_config_lib_v3-3.6.6+1.20.1-fabric.jar` | Configuration dependency | Retain |
| `fabric-api-0.92.11+1.20.1.jar` | Fabric dependency | Retain |
| `modmenu-7.2.2.jar` | Configuration access | Retain |

### Installed artefacts requiring an audio contribution audit

| Installed artefact | Audit question |
|---|---|
| `physics-mod-3.0.20-mc-1.20.1-fabric.jar` | Does any enabled destruction, debris or entity physics feature create, suppress or retime sound? |
| `cosmetica-fabric-2.0.1-1.20.1.jar` | Does any cosmetic currently selected emit a sound? |
| Animation, skin and model mods | Do any animation events trigger extra client-side audio or change action timing enough to affect synchronisation? |

Do not assume these mods are silent merely from their filenames. Audit representative events once, then record the result.

### Resource-pack audit status

The installed packs are primarily animation, entity-model and expression packs:

```text
Creatures-animated-ADDON-1.0.1.zip
Creatures+3.0.zip
FA+All_Extensions-v1.8.1.zip
FA+Classic_Horses-v1.5.zip
FA+Player-v1.1.zip
Fresh Patch - More Mob Variants.zip
FreshAnimations_v1.10.4.zip
JustExpressions_v1.2.1.zip
```

Their filenames do not prove the absence of audio. Before toolchain lock, inspect each archive for:

```text
assets/<namespace>/sounds.json
assets/<namespace>/sounds/*.ogg
```

`-1.21.2 Fresh Moves v3.1 (With Animated Eyes).zip.disabled` remains disabled and is outside the 1.20.1 production profile.

## 3. Sound architecture

Sound is divided into three controlled layers.

### A. Physical acoustics

These affect how an existing sound occupies a location:

- Sound Physics Perfected;
- Presence Footsteps where its generated movement belongs to the selected pass;
- distance, obstruction and room/cave response.

This layer may remain broadly active, but settings must be archived and kept restrained.

### B. Environmental texture

These create non-critical world detail:

- rain;
- drips;
- fire;
- wind;
- leaves;
- waterfalls;
- furnace and work sounds;
- room tone.

Environmental texture is captured per scene. It must not reveal Moss, danger, weather or the portal before the script allows it.

### C. Authored narrative cues

These communicate plot and must be deterministic:

- echo-portal body, texture and instability;
- portal-layer dropout;
- quiet portal collapse;
- delayed return after the fatal blast;
- Scene 9 Moss bark master;
- exact Scene 12 memory reuse;
- creeper landing, hiss and explosion;
- exact repeated R0 ambience in Scene 13.

Narrative cues are never delegated to random ambience generation.

## 4. OBS recording architecture

Create one OBS scene collection named:

```text
TPNM — Replay Audio Capture
```

### Sources

1. **Game Capture — Replay Reference Picture**
   - captures the Replay Viewer window for synchronisation and QC;
   - this is only a lightweight reference picture, not the final image render.

2. **Application Audio Capture — Minecraft**
   - targets the active PollyMC Minecraft Java process;
   - contains vanilla, resource-pack and mod-produced audio emitted by that process.

3. **Optional microphone slate**
   - disabled for normal passes;
   - used only when a spoken take note is useful;
   - assigned to a separate OBS track.

### Global OBS rules

- OBS sample rate: **48 kHz**.
- Channels: **stereo**.
- Recording container: **MKV**.
- Audio encoder: a lossless option available in the installed OBS build, preferably PCM or FLAC.
- Desktop Audio: **disabled**, preventing duplicate Minecraft capture.
- Minecraft Application Audio source: monitored only when required; never routed back into Desktop Audio.
- No noise suppression, compressor, limiter, gate, loudness filter or automatic gain on the Minecraft source.
- Record reference picture and audio together so every isolated pass carries its own visual synchronisation evidence.
- Remux or extract lossless WAV files after recording; preserve the original MKV.

OBS multi-track recording separates independent OBS sources, not Minecraft’s internal categories. Minecraft-category separation therefore comes from one repeated, isolated pass per stem.

## 5. Synchronisation system

Every audio pass must use:

- the same replay file;
- the same saved camera path;
- the same playback speed, normally `1.0×`;
- the same start timestamp;
- the same end timestamp;
- the same field of view and listener perspective;
- at least two seconds of pre-roll;
- at least five seconds of post-roll when a reverberation tail, fire bed, rain or explosion needs decay time.

### Preferred slate

Place a synchronisation event outside the final scene range during original capture:

1. one visually unambiguous frame event, such as a lamp flash or arm swing;
2. one short, dry sound event on the same game tick;
3. two seconds of clean lead-in after the slate before the scene begins.

The slate is removed in edit. It must not share the same sound identity as a story cue.

### Fallback synchronisation

When the replay lacks a slate:

- record the Replay Viewer reference picture in OBS;
- align the OBS reference frame to the identical frame in the final Replay Mod render;
- verify alignment again at a second visible impact or animation near the end of the shot;
- reject the pass if drift becomes audible or frame alignment changes materially.

## 6. Capture-pass system

The capture unit is one scene or one continuous camera shot. Do not record a single global stem for the entire film unless the same replay and camera path genuinely cover it.

### Core passes

| Pass ID | Contents | Isolation method |
|---|---|---|
| `FULL_REF` | Complete in-game reference mix | All approved scene sounds enabled |
| `ROOMTONE` | Stable location bed only | Disable actions, mobs, UI, music and story cues |
| `PLAYER_FOLEY` | Player movement, clothing-equivalent movement and Presence Footsteps | Players category plus exact required sound IDs |
| `BLOCKS_PROPS` | Mining, placement, doors, furnace, crops, item and environmental interactions | Blocks category with per-sound exclusions |
| `WEATHER` | Rain and thunder only | Weather category plus exact weather IDs |
| `AMBIENCE` | Cave tone, wind, leaves, waterfall and Drip Sounds | Ambient/Environment plus exact mod IDs |
| `MOSS` | Only approved Moss breathing, paws or vocal performance | Exact wolf sound IDs; other friendly creatures muted |
| `HOSTILE` | Creeper or other approved hostile action | Exact hostile sound IDs; unrelated hostile mobs muted |
| `PORTAL` | Conventional or echo-portal source elements | Exact portal IDs or project-owned custom IDs |
| `FIRE` | Close, middle or distant fire perspectives | Exact fire IDs; unrelated block sounds muted |
| `CLEAN` | No intentional game sound | Used to expose noise, duplicate capture or unexpected mod events |

### Why categories alone are insufficient

Minecraft’s broad categories combine unrelated sources. For example, Friendly Creatures can include Moss, sheep, chickens and other animals. Sound Controller must therefore apply a second level of isolation by exact sound ID.

Use this priority:

```text
Exact sound-ID preset
→ Minecraft category level
→ master level
```

### Required Sound Controller presets

Create and archive these presets after the first sound-ID discovery session:

```text
TPNM_00_FULL_REF
TPNM_01_CLEAN
TPNM_02_ROOMTONE
TPNM_03_PLAYER_FOLEY
TPNM_04_BLOCKS_PROPS
TPNM_05_WEATHER
TPNM_06_AMBIENCE
TPNM_07_MOSS
TPNM_08_HOSTILE_CREEPER
TPNM_09_PORTAL_CONVENTIONAL
TPNM_10_PORTAL_ECHO
TPNM_11_FIRE
TPNM_12_SC12_FATAL_CHAIN
```

Every selected pass records the preset name and a hash or archived copy of the relevant configuration.

## 7. Replay-audio compatibility gate

Do not assume every client-generated mod sound will reproduce inside Replay Viewer merely because it was audible during original gameplay.

Run `AUD-POC-001` before principal audio capture.

| Test event | Required result |
|---|---|
| Vanilla footstep | Present at the correct visible step |
| Presence Footsteps surface change | Present and materially correct |
| Drip Sounds event | Present when the recorded/replayed drip occurs |
| Sound Physics room transition | Listener follows Replay Mod camera; occlusion and reverb remain credible |
| Physics Mod representative event | Any audio contribution is identified and repeatable |
| Resource-pack replacement | Correct OGG/event is heard in Replay Viewer |
| Sound Controller mute | Target event is removed without suppressing required events |
| Five-minute drift test | Start and end visual/audio synchronisation remain acceptable |

### Failure route

When a sound is missing or inconsistent in Replay Viewer:

1. do not abandon the entire OBS workflow;
2. classify the sound as `ORIGINAL_TAKE_ONLY` or `AUTHORED_POST`;
3. capture it during the original gameplay performance or in a deterministic dedicated staging pass;
4. preserve a dry version and, where useful, a Sound Physics-treated version;
5. align it editorially using the same replay-visible action.

Random client ambience is never allowed to carry a plot-critical cue.

## 8. Scene-by-scene capture map

| Scene | Required game-audio passes | Story-owned/editorial passes | Forbidden or muted |
|---|---|---|---|
| 1 — R4 chase/fire | `FULL_REF`, `PLAYER_FOLEY`, `FIRE`, dry wind/room tone | selective impacts if needed | portal, music, birds, wolves and locating cues |
| 2 — R0 home/day | `FULL_REF`, `ROOMTONE`, `PLAYER_FOLEY`, `BLOCKS_PROPS`, restrained ambience | narration and exact repeat master | portal lure and dramatic ambience |
| 3 — cave/threshold | `FULL_REF`, `PLAYER_FOLEY`, `BLOCKS_PROPS`, `AMBIENCE`, destination rain perspective | echo-portal layers | horror stingers and portal audio before visual discovery |
| 4 — R1 | `FULL_REF`, `WEATHER`, waterfall/ambience, footsteps | controlled portal bed | duplicate rain or thunder beds |
| 5 — dry echoes | `FULL_REF`, `ROOMTONE`, `PLAYER_FOLEY`, dry ambience | optional restrained musical pulse after marker absence | lush wildlife and generic danger cues |
| 6 — archive | `FULL_REF`, `ROOMTONE`, `BLOCKS_PROPS`, `PORTAL` | portal dropout and failure negative space | generic shutdown sting |
| 7 — home echo | `FULL_REF`, `ROOMTONE`, controlled birds | quiet portal collapse | random mobs and uncontrolled ambience events |
| 8 — domestic montage | `FULL_REF`, `PLAYER_FOLEY`, `BLOCKS_PROPS`, `MOSS`, `WEATHER` | score and selected thunder placement | UI sounds and uncontrolled weather |
| 9 — shared room/gate | `FULL_REF`, `ROOMTONE`, hearth/fire, restrained Moss movement | isolated Scene 9 bark master | random wolf barks and score after closure |
| 10 — burned-home search | `FULL_REF`, `PLAYER_FOLEY`, `FIRE`, Scene 1 wind vocabulary | dawn birds at exact cue | Moss locator, body/death cues and early birds |
| 11 — ledge/build | `FULL_REF`, `PLAYER_FOLEY`, `BLOCKS_PROPS`, dry room tone | faint portal-memory music | active portal locator |
| 12 — fatal sequence | isolated `MOSS`, landing, hiss and blast passes; `CLEAN` safety | exact bark reuse, negative space and delayed portal response | score, extra mobs, ambience events and thunder |
| 13 — omniscient return | exact R0 master, controlled portal transition | narration reuse and final mix transition | surface lure, approximate replacement ambience |

## 9. Narrative sound rules

### Conventional Nether portal

Retain a recognisable vanilla identity. It may use ordinary travel language, but its hum is controlled per pass. It must remain sonically distinct from an echo portal.

### Echo portal

Build from independently controllable layers:

1. **body** — low architectural pressure;
2. **texture** — fragile air, stone or granular movement;
3. **instability** — a narrow uneasy layer that can disappear at failure.

Rules:

- no echo-portal audio before the frame is visually discovered underground;
- destination rain may transmit only when the opening exists and perspective supports it;
- Scene 6 failure removes a layer rather than adding a generic power-down sting;
- Scene 7 collapse is quiet;
- Scene 12 response follows bark, landing, hiss, blast and an authored delay;
- Scene 13 transitions into the exact approved R0 ambience;
- the surface never emits a lure that would have drawn the protagonist earlier.

### Moss

- Random wolf vocalisations remain muted during controlled story passes.
- Record one clean Scene 9 gate bark as the protected master.
- Reuse the exact same source file in Scene 12.
- Perspective processing may change, but performance identity may not.
- R4 post-fire scenes contain no bark, whine, collar or locating cue that resolves Moss’s fate.

### Creeper interruption

The Scene 12 order is fixed:

1. remembered Moss bark;
2. creeper landing;
3. close hiss;
4. fatal explosion;
5. short air-loss or negative-space treatment;
6. delayed portal return.

Capture landing, hiss and explosion independently even when a full live sequence is also recorded.

### Repetition

- Scene 2’s approved R0 ambience becomes the Scene 13 source master.
- Scene 9’s approved bark becomes the Scene 12 source master.
- Scenes 1 and 10 share a recognisable wind, step and distant-fire vocabulary.
- Meaning changes through level, filtering and perspective—not by silently substituting a different performance.

## 10. Standard operating procedure

### Before a capture session

1. Launch the dedicated sound-capture clone.
2. Confirm ReplayMod Audio Render is disabled.
3. Confirm exact mod and resource-pack order.
4. Confirm Sound Physics Perfected configuration.
5. Confirm the selected Sound Controller preset.
6. Confirm Minecraft music and UI sounds are disabled unless explicitly required.
7. Confirm OBS Desktop Audio is disabled.
8. Confirm the Minecraft Application Audio source meters correctly.
9. Record ten seconds of `CLEAN` and check for duplicate or unintended audio.
10. Load the exact replay and camera path recorded in the shot ledger.

### For each shot

1. Record `FULL_REF` first.
2. Review it before recording isolated passes.
3. Record only the passes required by the scene map.
4. Preserve the same replay range, camera path and handles.
5. Announce the pass in the filename and metadata, not through an audible slate inside the final range.
6. Check the beginning and end for synchronisation.
7. Check for missing client-side mod sounds.
8. Record a safety pass with optional texture mods disabled when a mod is not fully deterministic.
9. Stop immediately after a crash, listener jump, duplicate audio path or unexplained sound event.
10. Preserve the OBS log and Minecraft log for failed but diagnostically useful runs.

### After a capture session

1. Preserve the original MKV.
2. Extract or remux the lossless audio without resampling.
3. Name the extracted file with the same stem as the MKV.
4. Import the low-resolution reference picture and audio into the edit.
5. Align to the final Replay Mod render.
6. Verify a second synchronisation point near the end.
7. Record QC notes in `audio-capture-log.csv`.
8. Mark one take selected only after human review.
9. Never overwrite the selected master.

## 11. File naming

Use:

```text
TPNM_SC-<scene>_SH-<shot>_AUD-<pass>_TK-<take>_<YYYYMMDD>.mkv
TPNM_SC-<scene>_SH-<shot>_AUD-<pass>_TK-<take>_<YYYYMMDD>.wav
```

Examples:

```text
TPNM_SC-03_SH-04_AUD-AMBIENCE_TK-01_20260717.mkv
TPNM_SC-09_SH-02_AUD-MOSS-BARK_TK-03_20260717.wav
TPNM_SC-12_SH-05_AUD-CREEPER-HISS_TK-02_20260717.wav
```

## 12. Audio capture log fields

The harness audio log should record:

```text
audio_id
scene_id
shot_id
replay_file
camera_path
pass_id
sound_preset
obs_file
audio_file
take
selected
sync_start
sync_end
mod_profile
resource_pack_profile
spp_config
noise_notes
processing_notes
qc_status
```

Do not populate the log before a real file exists.

## 13. Music and silence

Music is added in post and remains separate from all game-audio passes.

### No-music zones

- Scene 1;
- ordinary setup before portal discovery;
- Scene 9 after the conventional portal closes;
- Scene 12 in full;
- immediate post-death negative space and delayed portal response.

### Authored silence

Silence means controlled room tone or deliberate air removal, not accidental missing audio.

Key events:

- portal-layer dropout in Scene 6;
- room tone, hearth and Moss only after Scene 9 closure;
- no Moss-locating sound in Scene 10;
- negative space after the Scene 12 blast;
- quiet holds during domestic routine.

## 14. Mix hierarchy and QC

Priority order:

1. narration and intelligible story information;
2. plot-critical bark, hiss, portal dropout and delayed return;
3. character and action foley;
4. location ambience;
5. music;
6. decorative micro-detail.

Minimum QC:

- no clipping, crackle, missing samples or unintended gating;
- no duplicate application/desktop capture;
- no audible synchronisation drift;
- narration remains intelligible on headphones, speakers and a small phone speaker;
- critical cues survive mono playback;
- ambience never reveals information early;
- no duplicate rain, thunder, footsteps, portal, fire or wildlife layer;
- conventional and echo portals are distinguishable without picture;
- exact repeated assets are verified by file identity;
- selected takes reference the exact mod, resource-pack and configuration profile.

## 15. Immediate evidence-producing tests

Run in this order:

1. `AUD-POC-001` — OBS application capture receives Minecraft once, with no duplication.
2. `AUD-POC-002` — Replay Viewer reproduces vanilla, Presence Footsteps and Drip Sounds events.
3. `AUD-POC-003` — Sound Physics listener follows the Replay Mod camera through open field, wooden room and cave.
4. `AUD-POC-004` — Sound Controller cleanly isolates one vanilla and one modded sound ID.
5. `AUD-POC-005` — five-minute replay pass remains synchronised at both ends.
6. `AUD-POC-006` — Scene 9 bark can be captured alone and reused exactly.
7. `AUD-POC-007` — Scene 12 landing, hiss and blast can be captured as independent files.
8. `AUD-POC-008` — R0/R1 threshold rain can be isolated without duplicate weather beds.

Production audio remains unapproved until these tests produce retained evidence and human review.
