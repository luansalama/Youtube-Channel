# Production proposal validation hotfix

## Problem fixed

The Production Studio Assistant was required to pass capture-completion checks while also being forbidden from inventing or writing capture evidence. On the first Production planning run, this caused an otherwise valid proposal to fail and triggered an impossible repair pass.

## Behaviour after this patch

- Studio Assistant Production proposals validate only the planning files the assistant is allowed to create.
- `capture-log.csv`, a selected take, and technical usability are not required merely to generate and review a Production proposal.
- The normal Production phase check is unchanged.
- Advancing from Production to Edit still requires real capture-log evidence, at least one selected take, and that selected take marked technically usable.

## Files replaced

```text
mcstudio/core.py
mcstudio/assistant.py
studio/stages.json
tests/test_integrations.py
```

## Apply on Windows

1. Close the Minecraft Narrative Studio browser tab.
2. Close its launcher/dashboard terminal and any Codex or OpenCode runner terminals.
3. Back up the four files listed above, or back up the entire harness folder.
4. Extract this zip into the Minecraft Narrative Studio root: the folder containing `START-STUDIO.ps1`, `mcstudio`, `studio`, and `videos`.
5. Allow Windows to replace the four existing files.
6. Start the dashboard normally with `START-STUDIO.bat`, `START-STUDIO.vbs`, or `START-STUDIO.ps1`.

## Continue the failed Production run

Recommended method, without paying for another generation:

1. Open the active video's **Production** workspace.
2. Expand **Import or recover assistant work**.
3. Click **Recover latest completed run**.
4. Review the recovered proposal carefully.
5. Click **Accept edited version** after making any desired changes.

The latest archived run is the deterministic repair response. It still contains the complete Production document and the permitted production planning files, but explicitly leaves capture evidence unresolved.

Alternatively, run Studio Assistant again in **Develop phase** mode with the same Production prompt. After this patch it should finish after one generation and create a normal reviewable proposal.

## What happens next

After accepting the Production plan, the phase checks should still show capture blockers. That is correct. Record real takes through **Record a captured take** as you produce the footage. Before advancing to Edit, at least one capture row must have:

```text
Selected: yes
Technical: yes
```

Do not add a fake row to clear the gate.

## Verification

The patched repository passes the complete automated test suite:

```text
45 tests, 0 failures
```
