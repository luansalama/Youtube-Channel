# Claims and evidence map

Use this for real-world facts, Minecraft mechanics, quoted material, cultural references, licences, and business claims.

## Supported claims

### C-001 — Participation versus alteration in a single past

**Claim:** In a model with one past, a traveller cannot make an established past event different, but may participate in and help cause that event.

**Support:** SRC-001, Stanford Encyclopedia of Philosophy, substantive revision 22 March 2024.

**Use in project:** This distinction supports a protagonist whose decisions remain causally important even though the observed destruction cannot be rewritten.

**Boundary:** This is a philosophical account of a coherent model, not proof that backwards time travel exists.

### C-002 — Self-consistency as a proposed constraint

**Claim:** A published closed-timelike-curve model proposes that locally possible events must extend into a globally self-consistent history.

**Support:** SRC-002, Friedman et al., *Physical Review D* 42(6), 1990, DOI 10.1103/PhysRevD.42.1915.

**Use in project:** This informs the fictional rule that every portal crossing belongs to one history rather than producing a branch or reset.

**Boundary:** The paper is conditional theoretical work. It does not demonstrate a real time machine and does not validate the fictional portal mechanism.

### C-003 — See-through portals can target an exact position in another dimension

**Claim:** Immersive Portals provides see-through, seamless portals and documents a command that assigns a portal entity an exact destination dimension and position.

**Support:** SRC-003 and SRC-004.

**Use in project:** A portal mouth in one echo can be aimed at the matching cave coordinates in another registered world or dimension while showing that destination through the frame.

**Boundary:** This supports the underlying portal capability only. It does not prove compatibility with Multiworld, independent destination weather, ReplayMod, cinematic camera tools, shaders, or the selected capture settings.

### C-004 — Separate seeded overworld-like worlds can be created

**Claim:** Multiworld supports creating and teleporting to multiple worlds, and its documented create command accepts a generator and seed. Its Fabric 1.12 release lists Minecraft 1.20.1 as compatible.

**Support:** SRC-005 and SRC-006.

**Use in project:** R0–R4 can be represented as separate saved worlds with independent block histories while retaining an overworld generator.

**Boundary:** Multiworld's existence and commands do not establish interoperability with Immersive Portals. The combined stack must be tested before production lock.

### C-005 — Dimension-specific weather is available for Minecraft 1.20.1 Fabric

**Claim:** Dimensional Weather is designed to permit dimension-specific weather conditions, and release 1.1-1.20.1 supports Minecraft 1.20.1 on Fabric.

**Support:** SRC-007 and SRC-008.

**Use in project:** R0 may remain dry while rain is active in R1, including when R1 is visible through a portal.

**Boundary:** The mod's purpose and version support do not prove that rain particles, sky state, audio, lighting, and wet-side ambience will all render correctly through Immersive Portals. That specific composition remains a test requirement.

### C-006 — The same seed is the appropriate base for matching geography

**Claim:** Minecraft documentation describes a copied seed as a way to create new worlds from the same base map, and Mojang has described seeds as reliably generating the same world.

**Support:** SRC-009 and SRC-010.

**Use in project:** The echo worlds should begin from the same seed under the same Minecraft version, world generator and generation-affecting mod configuration. Different block histories can then be art-directed independently.

**Boundary:** The seed alone is not a production guarantee when versions, generators, data packs or generation mods differ. For exact shot continuity, preserve a clean master and duplicate the required chunks or world before modifying each echo.

### C-007 — Existing mods make a proof of concept reasonable

**Claim:** The documented capabilities collectively make the scripted effect technically plausible without first commissioning a custom mod: Immersive Portals supplies the visible transition, Multiworld supplies separate seeded worlds, and Dimensional Weather supplies separate weather state.

**Support:** C-003 through C-006.

**Use in project:** Proceed to a minimal R0-to-R1 proof of concept before researching or building a custom mod.

**Boundary:** This is an engineering inference from separate documented capabilities, not evidence that the three-mod stack has already been run successfully together. Production feasibility remains **provisional** until the proof of concept passes.

## Portal implementation decision

**Status:** Research candidate; not technically locked.

**Candidate baseline:**

- Minecraft Java Edition 1.20.1
- Fabric loader profile
- Immersive Portals 5.2.0 for Minecraft 1.20.1
- Multiworld 1.12 for Fabric
- Dimensional Weather 1.1-1.20.1
- Required compatible libraries resolved and pinned during installation
- One separately saved world for each echo reality
- One shared seed and identical generation configuration for matching geography
- A clean master world or copied master chunks before echo-specific art direction

**Reason for rejecting different seeds as the default:** Different seeds are intended to generate different worlds and would not reliably preserve the exact ravine, granite seam, cave silhouette and surface composition required by the script. The narrative needs separate histories, not unrelated terrain.

## Required proof-of-concept evidence

The implementation may be promoted from `research_candidate` to `validated` only after a recorded test confirms:

1. R0 and R1 exist as separately saved overworld-like worlds.
2. Their target cave coordinates match closely enough for the scripted transition.
3. The portal shows R1 from R0 with stable perspective and natural parallax.
4. The player can cross without a loading screen or visible discontinuity.
5. R0 can remain dry while R1 is raining.
6. Rain, destination lighting and destination geometry are visible through the opening.
7. A tamed wolf can cross reliably, remain owned and preserve its state.
8. The portal can remain intentionally one-way without an unwanted return mouth.
9. Save/reload preserves worlds, destinations and portal orientation.
10. The selected camera, replay, shader and capture stack remains stable at the required resolution and frame rate.

If any condition fails, record the exact mod versions, logs and reproduction steps in the build log and risk register before changing the story or commissioning custom development.

## Story facts versus factual claims

**Proposed story facts (invented, unlocked canon):**

- The portal can connect different moments or echo realities represented by separate Minecraft worlds.
- There is one self-consistent timeline rather than parallel worlds or repeated resets.
- The older protagonist physically constructs the portal before his younger self discovers it.
- The protagonist witnesses the burned future of his homestead and initially believes his wolf was lost.
- The homestead's destruction remains fixed.
- The protagonist's rescue of the wolf was always part of the observed history.
- Crying-obsidian frames automatically continue to the next echo unless keyed.
- A builder can key a completed frame towards the first threshold.
- A charged respawn anchor participates in echo-frame activation.
- A creeper blast can ignite the completed echo frame.
- These rules are speculative story canon and are not presented as vanilla Minecraft mechanics or documented mod behaviour.

**Factual claims about philosophy, physics or implementation:**

- C-001 through C-007 only, with the limitations recorded above.

**Minecraft behaviours still requiring evidence:**

- The exact reproducible mechanic that destroys the homestead.
- How the protagonist's attempted safeguard interacts with that mechanic.
- Fire spread, animal movement and capture reliability in the production build.
- Combined Immersive Portals, Multiworld and Dimensional Weather compatibility.
- Destination-weather rendering through a portal.
- Wolf transfer through a portal.
- Replay, free-camera, shader and high-resolution capture compatibility.
- The practical capture method for showing two temporal versions of one avatar.

These behaviours are not yet asserted as supported claims. They must be tested or sourced before Production approves the relevant shots.

## Conflicts and uncertainty

The philosophical sources do not conflict at the limited level used: both permit discussion of internally consistent histories. They approach the subject from different disciplines and neither establishes that backwards time travel is physically achievable.

The portal sources document complementary capabilities but do not document this exact combined stack. No source found demonstrates the complete scripted R0-to-R1 composition with separate saved worlds, independent weather, a tamed wolf and the intended cinematic capture tools. Compatibility therefore remains unresolved until tested.

A causal loop can raise a deeper authorship question even when every physical object has an ordinary origin. The story may preserve that question as thematic residue, but it must not use it to excuse an untraceable Minecraft object or a missing causal step.

## Research exclusions

- No existing film, television episode, novel, game narrative or online plot summary was used as a story template.
- No quotations or copyrighted passages will appear in the video from these sources.
- Branching-timeline and many-worlds models were excluded because they contradict the requested fixed outcome.
- Claims that time travel is scientifically proven or practically achievable were excluded.
- A custom portal mod was not scoped because existing mods justify a proof of concept first.
- Mod files are not included in the project patch. Install only from the recorded official project pages and verify licences and hashes at installation time.
