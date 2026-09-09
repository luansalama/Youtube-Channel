# Integrations — v0.3.6

All normal integration controls are exposed in the dashboard.

## Runner Manager

Open **Settings** to configure automatic task routing, fallback order, individual runners, models, reasoning levels, timeouts, and web-research permission.

Every runner must return the same proposal contract:

```json
{
  "summary": "...",
  "document": "...",
  "files": {},
  "questions": [],
  "warnings": []
}
```

The proposal is stored under the active video and remains unapplied until you review it.

### Codex

Use **Install / update Codex**, **Sign in with Codex**, then **Test Codex**. The adapter runs `codex exec` with:

- the studio root as its working directory;
- a read-only sandbox;
- an explicit structured-output schema;
- the selected model and reasoning level;
- optional web search only when authorised.

The harness does not store Codex credentials. Codex manages its own authentication.

### OpenCode

Use **Install / update OpenCode**, then **Open provider setup**. This starts OpenCode Web locally so you can connect the provider and model you prefer. Return to Studio Settings and select **Test OpenCode**.

The adapter runs `opencode run` with the bundled `.opencode/agents/studio-assistant.md` agent. That agent allows reading and searching but denies writing, shell commands, task delegation, and external modification. Output is captured as JSON; when streaming output is incomplete, the adapter can recover the final proposal from the OpenCode session export.

### OpenAI API fallback

The direct Responses API adapter is optional. Configure its key, base URL, model, reasoning level, and timeout under Settings. API usage is billed by the API account and is separate from ChatGPT or Codex subscription usage.

### Routing and failure handling

Default routes are:

- creative development → Codex;
- production support → OpenCode;
- audit and repair → OpenCode;
- fallback order → Codex, OpenCode, OpenAI API.

The preferred runner is attempted first. If it fails and fallback is enabled, the next enabled runner is tried. The final proposal records the successful runner and the failed attempts for diagnosis.

## Production applications

Settings provides configurable launchers for Minecraft, Blender, video editor, and audio editor. Commands run only when their dashboard buttons are clicked.

## YouTube

Use **Files & media** for master, thumbnail, OAuth client JSON, and captions. Use **Release** to install support, dry-run, configure privacy or scheduling, and execute an approved upload.

## Analytics

Export a CSV from YouTube Studio and import it from **Operations**. The harness preserves snapshots for comparison and does not invent causal explanations.

## Windows visible runner terminal

When live-terminal mode is enabled, the dashboard requests Windows Administrator permission and starts the actual Codex/OpenCode CLI inside PowerShell 7.6.3 or newer. The dashboard watches started, exit, and completion marker files. Cancelling UAC or closing the terminal early produces a failed task instead of a permanent Running state. The terminal waits for Enter after completion.
