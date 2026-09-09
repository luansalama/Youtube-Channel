# Harness roadmap

## Included in v0.3.4

- provider-agnostic Runner Manager;
- Codex CLI adapter using structured `codex exec` proposals in a read-only sandbox;
- OpenCode CLI adapter using a bundled read-only agent and session-export recovery;
- direct OpenAI API fallback;
- automatic task routing, fixed-runner mode, configurable fallback order, models, reasoning, variants, and timeouts;
- dashboard installation, setup, testing, status, and diagnostics for runners;
- runner and fallback-attempt metadata stored with proposals;
- all v0.3.2 dashboard orchestration, release, operations, safety, recovery, and no-terminal controls.

## Add only after real production use proves the need

1. per-task cost and usage estimates where providers expose reliable data;
2. richer side-by-side runner comparison for the same proposal;
3. adapters for exact NLE, Blender, Minecraft, render, and export conventions;
4. transcript-to-caption alignment and caption editing;
5. direct YouTube Analytics snapshots after CSV import is proven;
6. approved social-network connectors;
7. richer visual diffs between proposals and approved versions.

## Deliberately excluded

- autonomous approval or public publishing;
- runner write access to the repository;
- automatic sponsorship acceptance or outreach;
- invented production evidence or analytics;
- multiple simultaneous active productions;
- a distributed service before local files become insufficient.
