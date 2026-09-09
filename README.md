# Minecraft Narrative Studio v0.3.6

A local, dashboard-controlled harness for producing **one scripted Minecraft video at a time**, from first idea to post-release learning.

## Start without a terminal

On Windows, extract the ZIP and double-click:

```text
START-STUDIO.vbs
```

The launcher runs invisibly and opens the local dashboard. Use **Close Studio** in the sidebar when finished. `START-STUDIO.bat` remains available only for visible troubleshooting.

## First use

1. Double-click `START-STUDIO.vbs`.
2. Open **Settings**.
3. Under **Runner Manager**, install or locate Codex and OpenCode.
4. Use **Sign in with Codex** and/or **Open provider setup** for OpenCode.
5. Use each **Test** button and inspect the task result in Diagnostics.
6. Optionally configure the OpenAI API as the final fallback.
7. Configure application paths for Minecraft, Blender, your video editor, and audio editor.
8. Return to **Production**, enter a working title, and continue entirely from the dashboard.

## Runner Manager

The dashboard sends Studio Assistant work to a configured runner and always receives a **reviewable proposal**. The runner operates read-only. You can edit the proposed main document, save it as a pending draft, or accept the exact edited version before project files change.

Default automatic routing:

| Work | Preferred runner |
|---|---|
| Direction, story, script | Codex CLI |
| Production, edit, release, learning | OpenCode CLI |
| Audit and repair | OpenCode CLI |
| Final fallback | OpenAI API |

You can change each route, force one runner for all work, disable runners, or reorder fallbacks from Settings.

On Windows, visible Codex and OpenCode jobs run inside **PowerShell 7.6.3 or newer as Administrator**. Approve the Windows UAC prompt. The actual CLI—not merely a log viewer—runs elevated. Closing the terminal before completion marks the dashboard task as failed; after completion, the terminal stays open until you press Enter or close it.

### Codex CLI

The harness invokes `codex exec` in a read-only sandbox and requests a structured proposal. Its model and reasoning level are configured in the dashboard.

How Codex usage is charged depends on how Codex itself is authenticated:

- ChatGPT/Codex sign-in uses the usage limits attached to that eligible ChatGPT plan.
- API-key authentication uses the separate API account and billing.

### OpenCode CLI

The harness invokes `opencode run` with the bundled read-only `studio-assistant` agent. OpenCode uses whichever provider and model you connect in its setup interface. Therefore, its limits and charges come from that provider—not from the harness.

### OpenAI API

The direct API adapter remains available as an optional fallback. API billing is separate from ChatGPT subscriptions. The key is stored in `studio/local-settings.json` only when **Remember key locally** is enabled; that file is excluded from Git and the release manifest. `OPENAI_API_KEY` is also supported.

## Everything is controlled from the dashboard

The dashboard provides:

- creation, pausing, resuming, abandoning, reopening, approvals, and advancement;
- in-browser editing of all human documents and structured internal evidence;
- runner installation, authentication/setup, connection tests, routing, fallbacks, models, and reasoning levels;
- directly editable AI proposals with save-before-apply and automatic revision backups;
- manual proposal import as a provider-independent fallback;
- browser and native file selection for footage, audio, project files, masters, thumbnails, OAuth credentials, and analytics;
- capture logging and deterministic phase checks;
- launch buttons for Minecraft, Blender, video editor, and audio editor;
- release metadata, wireframes, checksummed packaging, YouTube dry runs, approved uploads, captions, thumbnails, privacy, and scheduling;
- ideas, calendar, social queue, creator-hours, BRL finances, deals, reusable assets, analytics, channel strategy, canon, maintenance, logs, backups, diagnostics, and recovery.

## Pipeline

```text
Direction → Story → Script → Production → Edit → Release → Learn
```

Five decisions require your approval:

```text
Direction · Story · Script · Final master · Publication
```

Safe administrative transitions advance automatically after their deterministic evidence passes.

## Safety and privacy

- The dashboard binds to `127.0.0.1` and is local to the computer by default.
- Codex and OpenCode are invoked in read-only proposal workflows.
- No proposal applies itself.
- Approved evidence is fingerprinted; later drift is detected.
- Reopening a locked phase invalidates affected downstream approvals.
- Real YouTube publication is blocked server-side until Publication approval exists.
- AI cannot fabricate captured work, analytics, approvals, rights clearance, or commercial commitments.
- British English controls public writing; BRL is the default business currency.
- Only one production may be active.

## Recovery

Unexpected failures appear in the dashboard and are logged to:

```text
exports/studio-server.log
exports/launcher.log
```

Incomplete project folders are quarantined under `exports/recovery/` rather than silently deleted.

See `docs/DASHBOARD-GUIDE.md` for the screen-by-screen workflow and `docs/INTEGRATIONS.md` for runner setup details.
