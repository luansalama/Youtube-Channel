# Changelog
## Production research and storyboard hotfix — 2026-07-17

- separates the main Production plan from technical research, scene implementation, proof-of-concept tests and an aphantasia-accessible storyboard
- adds exact-version toolchain, scene, test and storyboard-panel validators
- adds a deterministic take-controller design requirement before custom mod development
- exposes research and storyboard files in the Production dashboard
- prioritises Codex/OpenAI when web research is explicitly enabled
- keeps real capture evidence mandatory only for phase completion and never permits the assistant to fabricate it
- includes the user's fuller Production plan and a sourced provisional 1.20.1/Fabric research baseline for the active video


## 0.3.6

- Runs visible Codex and OpenCode processes inside PowerShell 7.6.3+ as Administrator.
- Uses completion markers so the dashboard finishes while the terminal remains open.
- Detects UAC cancellation or a terminal closed before completion and marks the task failed.
- Enforces runner timeouts inside the elevated terminal.
- Forces UTF-8 terminal output to prevent mojibake.


## 0.3.5

- Made the proposed main document directly editable in the dashboard.
- Added **Save edits** to retain a revised proposal without applying it.
- Added **Accept edited version** to save and apply the exact dashboard text in one action.
- Preserved automatic hidden revision backups for every manual proposal save.
- Kept proposed internal evidence read-only and clearly separated from main-document edits.

## 0.3.4

- Studio Assistant runs open a live Windows terminal for Codex or OpenCode.
- Runner output streams to the terminal while the dashboard collects the proposal.
- The terminal remains open after success or failure until the user closes it.
- Visible terminal mode is enabled by default and can be disabled in Settings.
- Runner logs are retained under `exports/runner-logs/`.
- Fixed compressed Installed, Missing, Ready, and Not found status badges across dashboard pages.

## 0.3.3 — Codex and OpenCode Runner Manager

- Added a provider-agnostic Runner Manager controlled entirely from the dashboard.
- Added Codex CLI execution through `codex exec` with read-only sandboxing and structured proposal output.
- Added OpenCode CLI execution through `opencode run` with a bundled read-only Studio Assistant agent.
- Added resilient OpenCode JSON/session-export recovery.
- Added automatic task routing, fixed-runner mode, configurable fallback order, runner enablement, models, reasoning levels, variants, agents, and timeouts.
- Retained the direct OpenAI Responses API as an optional fallback.
- Added dashboard install, setup, connection-test, task-status, and diagnostics controls for runners.
- Stored runner, model, reasoning, response ID, and fallback-attempt metadata with every generated proposal.
- Added mocked end-to-end Codex, OpenCode, and cross-runner fallback tests.

## 0.3.2 — complete dashboard orchestration

- Added a hidden Windows launcher so normal use no longer opens or requires a terminal.
- Made all project controls, documents, internal evidence, checks, approvals, and phase transitions available in the dashboard.
- Added an optional built-in Studio Assistant using reviewable proposals, plus manual proposal import when no API key is configured.
- Added in-browser file editing, backups, deletion recovery, browser uploads, and native large-file selection.
- Added capture logging and configurable one-click launchers for Minecraft, Blender, video, and audio applications.
- Added complete Release controls: metadata, wireframes, packages, YouTube dependency installation, dry-run planning, approved real upload, scheduling, thumbnail, captions, and notification choice.
- Added Operations and Channel editing for ideas, time, BRL finances, milestones, social items, deals, assets, analytics, strategy, voice, and canon.
- Added dashboard settings, background jobs, diagnostics, maintenance, logs, and recovery controls.
- Enforced Publication approval server-side for real uploads while keeping dry runs available before approval.
- Added end-to-end dashboard tests for every page, browser editing, proposal import/application, and no-terminal launch assets.

## 0.3.1 — dashboard start reliability hotfix

- Removed the fragile POST/redirect/GET cycle from dashboard actions.
- Kept the dashboard server alive after unexpected action failures.
- Added local traceback logging at `exports/studio-server.log`.
- Made new-video creation atomic so failed creation cannot leave a partial project.
- Automatically quarantines incomplete v0.3.0 project folders under `exports/recovery/` so the same title can be started again safely.
- Added a `/health` endpoint and stronger Windows launcher diagnostics.
- Added an end-to-end HTTP test that starts a video and verifies the server remains reachable.

## 0.3.0 — video-at-a-time redesign

- Made the local dashboard the primary interface and added browser actions.
- Enforced one active video.
- Replaced thirteen visible stages with seven phases.
- Reduced human approvals to Direction, Story, Script, Final master, and Publication.
- Added `mcstudio continue` for safe automatic advancement.
- Reduced each video workspace to seven human-facing documents.
- Moved structured evidence into `.studio/internal/`.
- Made research conditional: none, light, or full.
- Made script revision adaptive: six core checks plus relevant optional passes.
- Set operating and commercial defaults to BRL while retaining en-GB output.
- Hid empty Operations data from the main dashboard.
- Added automatic maintenance and a v0.2 migration path with backups and invalidated old approvals.
- Added Windows dashboard launchers.
