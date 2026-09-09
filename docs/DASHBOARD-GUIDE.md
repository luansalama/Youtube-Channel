# Dashboard guide — v0.3.6

## Initial runner setup

Open **Settings** before the first AI-assisted production.

1. Keep **Automatic by task** unless you deliberately want one fixed runner.
2. Install or locate Codex and OpenCode.
3. Sign into Codex from its dashboard button.
4. Launch OpenCode provider setup, connect a provider, and return to the Studio.
5. Test both runners.
6. Optionally configure the OpenAI API as a fallback.
7. Save the routing settings.

Background setup and test tasks appear in **Diagnostics**. Normal production does not require a terminal.

## Production

This is the control room. It shows the one active video, phase, progress, blockers, next action, configured application launchers, and project controls.

You can start, enter, approve, continue, pause, resume, abandon, reopen, or open the project folder from here.

## Workspace

The current human-facing phase document is editable directly in the browser.

The Studio Assistant can:

- develop the phase from rough notes;
- revise current work;
- audit and repair blockers;
- use web research when enabled.

The Runner Manager chooses Codex, OpenCode, or the API according to Settings. The selected runner reads project context and returns a proposal. Review its complete document, internal-file changes, questions, warnings, runner metadata, and fallback attempts. Nothing changes until you accept the proposal. A pending proposal’s main document can be edited directly. Use **Save edits** to keep working without applying it, or **Accept edited version** to save and apply the exact text shown.

Manual editing and JSON proposal import remain available when no runner is connected.

## Files & media

Use the native picker for large files without duplicating them. Browser upload copies smaller files into the video project. Text changes create backups, and deletion backs up first.

## Release

Release combines metadata, thumbnail planning, captions, package generation, YouTube dependency installation, dry runs, privacy, scheduling, and an explicitly approved real upload. The server verifies Publication approval independently.

## Operations and Channel

Operations contains ideas, creator-hours, BRL finances, milestones, social queue, commercial opportunities, assets, and analytics. Channel contains strategy, voice, series bible, and canon.

## Settings

Configure:

- automatic or fixed runner routing;
- preferred runner by task group;
- fallback order;
- Codex executable, model, reasoning, and timeout;
- OpenCode executable, provider/model identifier, variant, agent, and timeout;
- optional OpenAI API fallback;
- default web-research permission;
- production application commands.

## Diagnostics

Diagnostics shows environment information, installed runner state, repository validation, setup/test tasks, maintenance controls, and server logs.

## Closing and reopening

Use **Close Studio** in the sidebar. Restart by double-clicking `START-STUDIO.vbs`.

## Live runner terminal

By default, every Codex or OpenCode Studio Assistant task opens a PowerShell window showing the runner's live output. The dashboard continues to collect the structured proposal. When the task finishes, the terminal remains open until you close it. Disable this only from Settings by clearing **Open a live runner terminal and keep it open after completion**.
