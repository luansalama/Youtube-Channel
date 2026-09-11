# DaVinci Resolve driver — retired

DaVinci Resolve is no longer the production NLE driver for this harness.
Production assembly now targets Adobe Premiere Pro through the MCP integration
documented in [`PREMIERE-MCP.md`](PREMIERE-MCP.md).

Historical Resolve exports are not deleted, but new `nle-export` runs default to
`premiere-pro` and no Resolve Python/Lua scripts are generated.
