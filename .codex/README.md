# Codex setup

Run Codex from the repository root so it can discover `AGENTS.md`, `.codex/config.toml`, and `.agents/skills`.

The main agent may delegate at most four bounded tasks. Review-oriented subagents are read-only. No role is authorised to approve a gate, publish, spend, or speak externally for Luan.

Use natural-language requests from `docs/PROMPT-COOKBOOK.md`; Codex does not need custom slash commands for this repository.
