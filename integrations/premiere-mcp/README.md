# Adobe Premiere Pro MCP — production NLE integration

The production NLE for Cuts Studio is **Adobe Premiere Pro via MCP**, using:

- upstream: `https://github.com/leancoderkavy/premiere-pro-mcp`
- pinned release: `v1.15.0` / npm `premiere-pro-mcp@1.15.0`
- local transport: `stdio`
- authority: `inspect,edit,export,filesystem`
- raw scripting: **disabled** (`unsafe-script` is never enabled by the harness)

The repository is not vendored here. Cuts Studio owns only the adapter,
configuration, deterministic edit specification and safety/readback contract;
the upstream package remains independently updateable and auditable.

## Windows setup

From the repo root:

```powershell
powershell -ExecutionPolicy Bypass -File .\integrations\premiere-mcp\setup.ps1
python -m cstudio --root . nle-status
python -m cstudio --root . nle-doctor
```

`setup.ps1` also applies a small idempotent CSS compatibility fix to the
installed CEP panel so the **whole panel scrolls when docked** in a short
Premiere workspace. The upstream v1.15.0 stylesheet keeps `body` clipped and
only makes the Activity log scrollable, which can hide the lower controls.
The fix is re-applied after connector installs/updates because `--install-cep`
can replace `styles.css`. To apply only this fix to an existing installation:

```powershell
powershell -ExecutionPolicy Bypass -File .\integrations\premiere-mcp\fix-panel-scroll.ps1
```

Fully restart Premiere after applying it. Pass `-SkipPanelScrollFix` to
`setup.ps1` only if a future pinned upstream release has fixed this itself.

Restart Premiere after installing/updating the connector, open a project and an
active sequence, then use the MCP client to run `verify_premiere_connection`
read-only. `nle-doctor` only verifies local package/config readiness; it does
not claim the editor bridge is live.

## Production handoff

After the cutlist is locked:

```powershell
python -m cstudio --root . nle-export <slug>
```

The default output is:

`productions/<slug>/.studio/internal/assembly/premiere-pro/`

It contains `timeline.json`, `premiere-edit-spec.json`, `timeline.xmeml`, a
local MCP client example and a runbook. The MCP client must discover the live
server schemas (`tools/list`) at runtime and read the sequence back after
mutations. The deterministic edit spec, not the model's prose, is the
assembly authority.

## Safety boundary

The Premiere MCP can mutate the editor, but it cannot approve Cuts Studio
gates, clear rights, register a master, or publish. Do not attach it to the
normal read-only proposal runner as a way to bypass the proposal/review model.
Live NLE execution belongs after `cutlist_lock`; resulting renders re-enter the
normal master/composition gate.
