# Storyboard plan

> Text-first storyboard designed for a creator with aphantasia. No image has been generated, embedded or approved. The panel ledger contains 49 planned panels and is the literal frame authority.

## Visual grammar

### Frame and coordinates

- Delivery frame: 16:9 landscape. Keep essential evidence inside the central 80% title-safe area.
- Every panel uses a named local coordinate system. These are proposed blocking marks, not existing Minecraft coordinates.
- `X` increases towards camera-right, `Y` increases upwards and `Z` increases away from the camera along the principal view axis unless a panel states otherwise.
- A camera entry always gives its local position, height, facing direction and planned horizontal FOV. Actual in-game transforms must replace local marks only after the master set exists.
- Environment descriptions explicitly separate foreground, midground and background.
- The 3×3 grid is written as `TL/TM/TR`, `ML/MM/MR`, `BL/BM/BR` so no spatial inference is required.

### Lens and height families

- 35°–42° FOV: journal, Atlas, marker and material-ledger inserts.
- 48°–55° FOV: human-scale performance, portal hero views and exact continuity frames.
- 58°–68° FOV: environmental geography and action where route readability matters.
- Normal protagonist-height camera: 1.6–1.8 blocks.
- Raised observational camera: 2.2–3.2 blocks.
- Low Moss or floor-detail camera: 0.6–1.0 blocks.
- Omniscient Scene 13 camera is identified explicitly and never shares the protagonist’s head height or movement language after death.

### Composition and movement

- Screen direction remains consistent within an action. Movement is stated as words such as `left to right`, `towards upper centre` or `down and away`.
- Portal views preserve the frame plane, destination horizon and parallax direction. A lateral camera move right must reveal more of the destination’s left occluded edge.
- Granite-seam recognition uses silhouette and screen placement, not colour grade alone.
- Matches use numerical camera marks and reference overlays once those references genuinely exist.
- Fire, mobs and portal activation may be divided into plates. The storyboard describes the final edit, not an assertion that one continuous take is possible.

### Local set diagrams

`MATCH PATH`, looking towards the homestead:

    BG: homestead / smoke at Z+18
                  ↑ travel
    ridge path ── H ─────────────
                  ↑
             cargo mark
                  ↑
    CAM MP-C at Z-10

Portal chamber, plan view:

    destination side Z+
         granite seam and destination cave
                    |
              [ portal plane ]
                    |
    source side Z-     CAM moves X-left → X-right

Homestead shared room, plan view:

    timber wall and fire route →
    [hearth] [green rug/Moss] [timber floor]
          doorway ↓          shortest wall at camera-left
              CAM HR-C

Final chamber, elevation:

    dark ledge L ● ── falling route ↓
                              landing ● behind H
    frame [====]   H ●   stone baffle [###]
    chamber floor ─────────────────────────

Scene 13 elevation:

    R0 surface / MATCH FRAME A
    soil module
    stone module
    forked granite seam
    active R0 mouth
       ↑ audience-only camera path
    active R4 source frame

## Consistency pack for later sketch generation

### Fixed subjects

- Protagonist: one silent Minecraft avatar. Early R0 kit is simpler and cleaner; later R4 kit carries the weathered journals and final materials. Do not invent facial acting unavailable to the skin.
- Wild wolf: no collar and no name.
- Tamed unnamed wolf: collar visible, no `Moss` label.
- Named Moss: same wolf silhouette and collar, with the name visible only when required by the panel.
- Never depict a second protagonist, an older-self conversation, a Moss body, collar drop or death message.

### Fixed props and places

- Clean survey journal: stitched corner, mostly blank pages, three-line ravine symbol and arrow-shaped seven.
- Weeping Atlas: weathered version of the same journal with only the seven Script-approved inserts.
- Portal: crying-obsidian frame, directional tear particles and a transparent destination view; ordinary Nether portal remains visually distinct.
- Geography: forked lightning-shaped granite seam, same scale and placement in all echoes.
- Hearth: stone-backed open fire; moss-green rug grows one square at a time.
- Final chamber: completed frame, charged-anchor appearance, offset stone baffle and connected dark creeper ledge.

### Restrained sketch aesthetic

Transform a real Minecraft or Blender greybox reference into a practical storyboard drawing: graphite construction lines, sparse black-ink contour, one flat grey shadow value and a single muted purple annotation only where the portal plane must be identified. Preserve block geometry, camera angle and subject marks. Do not add cinematic fog, costume detail, dramatic anatomy, extra props, textural decoration or lighting not present in the reference.

Negative constraints: no photorealism; no painterly fantasy portal; no extra characters; no wolf breed change; no curved non-Minecraft architecture; no altered frame asymmetry; no shifted granite seam; no readable text invented by the model; no body or remains; no post-death protagonist viewpoint.

### Reference-first workflow

1. Build or greybox the panel using the panel’s local marks.
2. Capture the actual camera view after the relevant technical test passes.
3. Supply that screenshot as the primary composition reference.
4. Supply the approved protagonist, Moss, portal, journal and location references only when visible.
5. Request transformation rather than independent scene invention.
6. Compare the result with the source using an overlay and a written continuity checklist.
7. Retain prompt, model identity, source provenance and human decision only after generation actually occurs.

## Scene panels

The CSV ledger contains every required field. The descriptions below identify the intended reading order and spatial problem each panel solves.

### Scene 1 — panels P01-01 to P01-02

- P01-01: the protagonist crests the R4 ridge; smoke sits behind the path line and purple cargo is physically visible before it is dropped.
- P01-02: locked `MATCH PATH`; the protagonist runs away from camera towards the homestead. The same motion line cuts to P02-01.

### Scene 2 — panels P02-01 to P02-06

- P02-01 repeats P01-02’s camera exactly in untouched morning R0, but the protagonist walks rather than runs and arrives alone.
- P02-02 establishes the overlook, water, birches and the choice to stop.
- P02-03 makes the skeleton-to-wild-wolf intervention readable without showing a collar.
- P02-04 holds bones between protagonist and wolf; hearts and collar belong only after the offered-bones action.
- P02-05 shows the anvil, `MOSS` name tag and application after the fishing cause.
- P02-06 is `MATCH FRAME A`: named Moss beside the packed protagonist before both descend.

### Scene 3 — panels P03-01 to P03-04

- P03-01 puts the granite seam and exposed iron on one continuous route.
- P03-02 reveals the crying frame only after the turn.
- P03-03 is the lateral parallax proof: dry source foreground, rainy destination background.
- P03-04 holds protagonist and Moss crossing together with audio changing at the plane.

Portal blocking:

    dry R0 source: H ●  M ●  →  [frame]  →  rain R1
    camera track: X-2 ─────────────→ X+2

### Scene 4 — panels P04-01 to P04-03

- P04-01 completes the crossing beside the same seam and visible waterfall.
- P04-02 frames the recognisable surface without shelter, crops or cow pen.
- P04-03 shows the single cobblestone block against the left frame foot before entry into the dry view.

### Scene 5 — panels P05-01 to P05-03

- P05-01 exactly repeats the frame-foot insert with the R1 block absent.
- P05-02 makes the R2 two-block L and outer torch unambiguous.
- P05-03 repeats the bare foot in R3, then presents the coordinate/marker comparison and `ECHOES` consequence.

Marker plan:

    R1: [left frame foot][one cobble]
    R2: [left frame foot][cobble]
                         [cobble+torch]
    R3: [left frame foot][bare floor]

### Scene 6 — panels P06-01 to P06-04

- P06-01 shows familiar torch and storage habits before the journal reveal.
- P06-02 aligns the clean and weathered stitched corners.
- P06-03 gives the seven Atlas instructions readable, separate holds rather than one overloaded frame.
- P06-04 places blocked gravel behind the protagonist while the contracting portal remains the only open route.

### Scene 7 — panels P07-01 to P07-02

- P07-01 completes arrival in habitable R4 while projected upper blocks fade.
- P07-02 shows ordinary fire failing at the incomplete mouth, then the surface marker and first roof as a causal sequence.

### Scene 8 — panels P08-01 to P08-04

- P08-01 repeats one exterior composition through build milestones.
- P08-02 shows Moss occupying the exact block needed and the protagonist choosing to wait.
- P08-03 repeats the same shared-room frame for bare floor, initial rug and final rug.
- P08-04 links the desk ledger, conventional portal returns and measured dead mouth without implying haste.

### Scene 9 — panels P09-01 to P09-03

- P09-01 identifies the final two ledger entries.
- P09-02 shows feed, return to rug, second sit gesture and the source bark performance.
- P09-03 holds after departure until fire catches the nearest green square and travels out of frame towards timber.

### Scene 10 — panels P10-01 to P10-05

- P10-01 resumes the exact Scene 1 path movement.
- P10-02 keeps the empty doorway, water stream, steam and falling timber in one readable axis.
- P10-03 reveals the breached shortest wall, absent rug and charred fan without any Moss evidence.
- P10-04 maps the search route from crops to ridge, ravine, portal shelter and covered hollow.
- P10-05 shows dropped cargo, weathered Atlas, wolf figure and closing of the unfinished safety page.

### Scene 11 — panels P11-01 to P11-04

- P11-01 places the muted green edge at the extreme screen side and shows its connected dark ledge.
- P11-02 matches the R4 frame’s asymmetry to the R0 mouth through labour stages.
- P11-03 separates charged-anchor appearance from the keyed/unkeyed Atlas insert.
- P11-04 makes baffle, reach, journals, protagonist and creeper landing route spatially legible.

Final chamber plan:

    frame F at Z0
          H ignition mark at Z-3
    baffle B offset X-3, Z-4
    camera C at X-6, Z-8
    ledge L at X+1, Y+5, Z-4
          ↓ connected fall
    landing at X+1, Z-3.5 behind H

### Scene 12 — panels P12-01 to P12-05

- P12-01 holds the hand on the Atlas wolf figure while the reused bark is subjective.
- P12-02 shows the raised flint and steel, landing position and creeper hiss before any ignition.
- P12-03 is a literal black frame for the explosion sound and death interval.
- P12-04 is a locked protagonist-free aftermath plate with restrained scattered items.
- P12-05 stages flash, first particles and gradual R0 destination view in that order.

### Scene 13 — panels P13-01 to P13-04

- P13-01 begins outside the frame in the protagonist-free R4 aftermath.
- P13-02 crosses into R0 and passes the granite seam as audience access.
- P13-03 rises through modular stone and soil into `MATCH FRAME A`.
- P13-04 repeats the exact Scene 2 image and narration, then cuts to the waiting R0 mouth showing R1 rain.

## Review and generation gate

### Text-board review

A human reviewer should be able to answer, without imagining missing space:

- where the camera is;
- where every subject stands and faces;
- which direction movement follows;
- what is foreground, midground and background;
- where light originates;
- what changes at the cut;
- which continuity anchor must match;
- why the shot is being captured.

Any ambiguous answer returns the panel to text revision before greyboxing.

### Five-panel model consistency test

Use actual greybox screenshots for these five cases:

1. P02-05 — protagonist/Moss identity and readable prop relationship.
2. P03-03 — portal-frame geometry, parallax and rainy destination preservation.
3. P02-03 — hostile-mob action with three clear marks and no premature collar.
4. P02-06 paired with P13-04 — exact match-frame preservation across two uses.
5. P10-03 — fireplace, missing rug and burn-fan geometry without invented Moss evidence.

First candidate: ChatGPT Images 2.0, based on the supplied official-source summary for instruction following, editing and continuity. Comparison candidate: FLUX.2 Pro for multi-reference editing and explicit composition/pose control. Midjourney’s Style and Omni Reference systems may be tested for aesthetic exploration but are not the first camera-faithful choice.

Approval requires all five outputs to preserve aspect ratio, camera geometry, block layout, protagonist silhouette, Moss state, visible props, seam/frame asymmetry and the restrained graphite-and-ink language. Reject any model that invents story evidence or shifts essential marks. Permit at most two prompt revisions per failed panel before returning to the text/greybox board or comparing the alternative. No bulk generation follows without human approval.

Panel IDs, not invented image filenames, identify this phase. If images are later generated, naming and provenance are recorded only after the files exist.