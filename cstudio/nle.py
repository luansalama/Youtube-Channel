"""NLE abstraction + production Adobe Premiere Pro MCP driver.

The production driver is a local MCP integration for Adobe Premiere Pro.  The
harness owns a deterministic edit specification and an interchange fallback;
it does not pretend that Premiere is connected when it is not.  Live timeline
mutations are performed by an MCP-capable operator/agent on the editor machine,
with runtime tool discovery and post-mutation readback.
"""
from __future__ import annotations

import abc
import json
import os
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

from .timecode import parse_timecode


DEFAULT_DRIVER = "premiere-pro"
DEFAULT_CONFIG = {
    "schema_version": 1,
    "production_driver": DEFAULT_DRIVER,
    "premiere_pro": {
        "integration": "mcp",
        "repository": "https://github.com/leancoderkavy/premiere-pro-mcp",
        "source_ref": "v1.15.0",
        "npm_package": "premiere-pro-mcp",
        "npm_version": "1.15.0",
        "server_name": "io.github.leancoderkavy/premiere-pro",
        "transport": "stdio",
        "command": "premiere-pro-mcp",
        "capabilities": ["inspect", "edit", "export", "filesystem"],
        "tool_packs": "full",
        "unsafe_script": False,
        "production_bridge": "cep",
        "uxp_extension": "prefer-documented-actions-when-authenticated",
    },
}


class NLEDriver(abc.ABC):
    name: str = "abstract"

    def __init__(self, root: str = "") -> None:
        self.root = os.path.abspath(root) if root else ""

    @abc.abstractmethod
    def export(self, timeline: dict, outdir: str, production_title: str = "") -> dict:
        """Write deterministic NLE/MCP handoff artefacts into outdir."""

    @abc.abstractmethod
    def available(self) -> bool:
        """True only when the local driver command is present on PATH."""

    def status(self) -> dict:
        return {"driver": self.name, "available": self.available()}

    def doctor(self, timeout: int = 60) -> dict:
        raise RuntimeError(f"doctor is not supported by NLE driver {self.name}")


def load_config(root: str = "") -> dict:
    """Load studio/nle.json with safe built-in defaults for older repos."""
    data = json.loads(json.dumps(DEFAULT_CONFIG))
    if not root:
        return data
    path = os.path.join(os.path.abspath(root), "studio", "nle.json")
    if not os.path.isfile(path):
        return data
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return data
    if not isinstance(raw, dict):
        return data
    data.update({k: v for k, v in raw.items() if k != "premiere_pro"})
    if isinstance(raw.get("premiere_pro"), dict):
        data["premiere_pro"].update(raw["premiere_pro"])
    return data


def default_driver(root: str = "") -> str:
    return str(load_config(root).get("production_driver") or DEFAULT_DRIVER)


def _seconds(value, fps: float) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "0").strip()
    try:
        return float(text)
    except ValueError:
        return parse_timecode(text, fps)


def _frame(value, fps: float) -> int:
    return int(round(_seconds(value, fps) * fps))


def _rate(parent: ET.Element, fps: float) -> None:
    rate = ET.SubElement(parent, "rate")
    ET.SubElement(rate, "timebase").text = str(int(round(fps)))
    ET.SubElement(rate, "ntsc").text = "FALSE"


def _pathurl(source: str) -> str:
    """Return a conservative FCP XML path URL without inventing a path."""
    source = str(source or "")
    if not source:
        return ""
    if source.startswith(("file://", "http://", "https://")):
        return source
    try:
        p = Path(source).expanduser()
        if p.is_absolute():
            return p.as_uri()
    except (OSError, ValueError):
        pass
    return source.replace("\\", "/")


def fcp7_xml(timeline: dict, title: str = "timeline") -> str:
    """Generate a deterministic FCP7 XML rough-cut interchange fallback.

    Premiere MCP is the primary path.  This XML exists as recovery/interchange
    evidence and encodes both source trims and record/timeline positions.
    """
    fps = float(timeline.get("fps", 30) or 30)
    events = list(timeline.get("events", []))
    total_frames = max((_frame(ev.get("timeline_out", 0), fps) for ev in events), default=0)

    xmeml = ET.Element("xmeml", version="4")
    sequence = ET.SubElement(xmeml, "sequence", id="sequence-1")
    ET.SubElement(sequence, "name").text = title
    ET.SubElement(sequence, "duration").text = str(total_frames)
    _rate(sequence, fps)
    media = ET.SubElement(sequence, "media")
    video = ET.SubElement(media, "video")
    vtrack = ET.SubElement(video, "track")

    source_ids: dict[str, str] = {}
    for index, ev in enumerate(events, 1):
        cut_id = str(ev.get("cut_id") or f"cut-{index}")
        source = str(ev.get("source") or "")
        source_id = source_ids.setdefault(source, f"file-{len(source_ids) + 1}")
        source_in = _frame(ev.get("source_in", 0), fps)
        source_out = _frame(ev.get("source_out", 0), fps)
        start = _frame(ev.get("timeline_in", 0), fps)
        end = _frame(ev.get("timeline_out", 0), fps)

        ci = ET.SubElement(vtrack, "clipitem", id=f"clipitem-{index}")
        ET.SubElement(ci, "name").text = cut_id
        ET.SubElement(ci, "duration").text = str(max(0, source_out - source_in))
        _rate(ci, fps)
        ET.SubElement(ci, "start").text = str(start)
        ET.SubElement(ci, "end").text = str(end)
        ET.SubElement(ci, "in").text = str(source_in)
        ET.SubElement(ci, "out").text = str(source_out)

        file_el = ET.SubElement(ci, "file", id=source_id)
        ET.SubElement(file_el, "name").text = os.path.basename(source) or source or cut_id
        ET.SubElement(file_el, "pathurl").text = _pathurl(source)
        _rate(file_el, fps)

    return ET.tostring(xmeml, encoding="unicode")


def _premiere_config(root: str = "") -> dict:
    cfg = load_config(root).get("premiere_pro") or {}
    return cfg if isinstance(cfg, dict) else {}


def _edit_spec(timeline: dict, title: str, cfg: dict) -> dict:
    fps = float(timeline.get("fps", 30) or 30)
    events = []
    for index, ev in enumerate(timeline.get("events", []), 1):
        events.append({
            "order": index,
            "cut_id": str(ev.get("cut_id") or f"cut-{index}"),
            "source": str(ev.get("source") or ""),
            "source_in_seconds": round(_seconds(ev.get("source_in", 0), fps), 6),
            "source_out_seconds": round(_seconds(ev.get("source_out", 0), fps), 6),
            "timeline_in_seconds": round(_seconds(ev.get("timeline_in", 0), fps), 6),
            "timeline_out_seconds": round(_seconds(ev.get("timeline_out", 0), fps), 6),
            "duration_seconds": round(float(ev.get("duration") or 0), 6),
            "video_track": 0,
            "audio_track": 0,
        })
    unique_sources = list(dict.fromkeys(ev["source"] for ev in events if ev["source"]))
    return {
        "schema_version": 1,
        "kind": "cuts-studio-premiere-edit-spec",
        "driver": DEFAULT_DRIVER,
        "title": title,
        "fps": fps,
        "target": timeline.get("target", ""),
        "total_seconds": float(timeline.get("total_seconds") or 0),
        "sources": unique_sources,
        "events": events,
        "mcp": {
            "server_name": cfg.get("server_name"),
            "repository": cfg.get("repository"),
            "source_ref": cfg.get("source_ref"),
            "transport": "stdio",
            "runtime_schema_authority": "tools/list",
            "required_preflight_tools": ["get_capabilities", "verify_premiere_connection", "get_premiere_state"],
            "preferred_mutation_route": [
                "preview_edit_plan/apply_edit_plan when the live schema can express the complete rough cut",
                "documented UXP tools (manage_source_clip_uxp + edit_timeline_uxp) when authenticated",
                "CEP compatibility tools (Source Monitor in/out + insert/overwrite) otherwise",
            ],
            "required_post_readback": ["get_full_sequence_info", "get_timeline_gaps", "get_used_media_report"],
            "never_use": ["execute_extendscript", "evaluate_expression"],
        },
        "preconditions": {
            "cutlist_lock_must_be_approved_before_live_mutation": True,
            "active_project_and_sequence_required": True,
            "source_paths_must_be_operator_approved": True,
            "no_publish_or_upload": True,
        },
        "postconditions": {
            "expected_event_count": len(events),
            "expected_total_seconds": float(timeline.get("total_seconds") or 0),
            "duration_tolerance_seconds": round(1.0 / fps, 6),
            "unexpected_timeline_gaps_allowed": False,
            "readback_required_after_mutation": True,
        },
    }


def _generic_mcp_client_config(cfg: dict) -> dict:
    command = str(cfg.get("command") or "premiere-pro-mcp")
    capabilities = cfg.get("capabilities") or ["inspect", "edit", "export", "filesystem"]
    env = {
        "PREMIERE_MCP_CAPABILITIES": ",".join(str(v) for v in capabilities),
        "PREMIERE_MCP_TOOL_PACKS": str(cfg.get("tool_packs") or "full"),
    }
    return {
        "mcpServers": {
            "premiere-pro": {
                "command": command,
                "args": [],
                "env": env,
            }
        }
    }


RUNBOOK_TEMPLATE = """# Premiere Pro MCP Runbook — {title}

Cuts Studio production NLE: **Adobe Premiere Pro via MCP**.

Pinned upstream:
- repository: `{repository}`
- package: `{package}@{version}`
- server: `{server_name}`
- transport: local `stdio`

## One-time workstation setup

Requires Node.js 20.19+ and Premiere Pro on the same Windows/macOS machine.
The harness intentionally does not install editor plugins by itself.

```powershell
npm install -g {package}@{version}
premiere-pro-mcp --install-cep
premiere-pro-mcp --doctor
```

Or run `integrations/premiere-mcp/setup.ps1` from the repository root.
After restarting Premiere, open a project and an active sequence. In the
Premiere MCP panel confirm the bridge is running, then make the MCP client run
`verify_premiere_connection` **read-only** before any edit.

## Assembly handoff

- `timeline.json`: engine-owned source of truth.
- `premiere-edit-spec.json`: deterministic MCP intent + postconditions.
- `timeline.xmeml`: recovery/interchange rough-cut fallback.
- `mcp-client.example.json`: generic local stdio client configuration.

The live client MUST discover the installed server's schemas at runtime; do
not hardcode a development-branch tool schema. Prefer the server's preview / 
confirmation workflow, then documented UXP timeline actions when available;
CEP is the compatibility bridge.

Before a live mutation, `cutlist_lock` must already be approved. After every
structural mutation, read the timeline back and compare it with
`premiere-edit-spec.json`: event count, source ranges, order, gaps and total
runtime (tolerance: one frame). A tool returning success without matching
readback is a failure.

`execute_extendscript` and `evaluate_expression` are intentionally forbidden by
this harness. The MCP authority profile remains `inspect,edit,export,filesystem`
without `unsafe-script`.

This integration never approves gates, changes rights clearance, uploads or
publishes. Rendering still feeds the normal `master`/composition gate.
"""


class PremiereMCPDriver(NLEDriver):
    name = DEFAULT_DRIVER

    @property
    def config(self) -> dict:
        return _premiere_config(self.root)

    @property
    def command(self) -> str:
        return str(os.environ.get("CSTUDIO_PREMIERE_MCP") or self.config.get("command") or "premiere-pro-mcp")

    def available(self) -> bool:
        return bool(shutil.which(self.command))

    def status(self) -> dict:
        cfg = self.config
        resolved = shutil.which(self.command)
        return {
            "driver": self.name,
            "integration": "mcp",
            "available": bool(resolved),
            "command": self.command,
            "resolved_command": resolved or "",
            "repository": cfg.get("repository"),
            "source_ref": cfg.get("source_ref"),
            "package": cfg.get("npm_package"),
            "pinned_version": cfg.get("npm_version"),
            "server_name": cfg.get("server_name"),
            "transport": cfg.get("transport", "stdio"),
            "capabilities": cfg.get("capabilities", []),
            "unsafe_script": bool(cfg.get("unsafe_script", False)),
            "live_connection_verified": False,
            "note": "Executable detection does not prove a live Premiere bridge; run nle-doctor then verify_premiere_connection from the MCP client.",
        }

    def doctor(self, timeout: int = 60) -> dict:
        resolved = shutil.which(self.command)
        if not resolved:
            return {**self.status(), "doctor_ok": False, "doctor_output": "premiere-pro-mcp executable not found"}
        try:
            proc = subprocess.run(
                [resolved, "--doctor"],
                cwd=self.root or None,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {**self.status(), "doctor_ok": False, "doctor_output": str(exc)}
        output = ((proc.stdout or "") + (proc.stderr or "")).strip()
        return {
            **self.status(),
            "doctor_ok": proc.returncode == 0,
            "doctor_exit_code": proc.returncode,
            "doctor_output": output[-12000:],
            "live_connection_verified": False,
        }

    def export(self, timeline: dict, outdir: str, production_title: str = "") -> dict:
        os.makedirs(outdir, exist_ok=True)
        title = production_title or "timeline"
        cfg = self.config

        files = []
        artifacts = {
            "timeline.json": timeline,
            "premiere-edit-spec.json": _edit_spec(timeline, title, cfg),
            "mcp-client.example.json": _generic_mcp_client_config(cfg),
        }
        for filename, payload in artifacts.items():
            with open(os.path.join(outdir, filename), "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
            files.append(filename)

        with open(os.path.join(outdir, "timeline.xmeml"), "w", encoding="utf-8") as fh:
            fh.write(fcp7_xml(timeline, title))
            fh.write("\n")
        files.append("timeline.xmeml")

        with open(os.path.join(outdir, "RUNBOOK.md"), "w", encoding="utf-8") as fh:
            fh.write(RUNBOOK_TEMPLATE.format(
                title=title,
                repository=cfg.get("repository", ""),
                package=cfg.get("npm_package", "premiere-pro-mcp"),
                version=cfg.get("npm_version", ""),
                server_name=cfg.get("server_name", ""),
            ))
        files.append("RUNBOOK.md")

        return {
            "driver": self.name,
            "integration": "mcp",
            "files": files,
            "outdir": outdir,
            "mcp_available": self.available(),
            "notes": "Premiere MCP is primary; edit spec + readback policy are deterministic, xmeml is recovery fallback.",
        }


DRIVERS = {DEFAULT_DRIVER: PremiereMCPDriver}


def get_driver(name: str = "", root: str = "") -> NLEDriver:
    selected = name or default_driver(root)
    try:
        return DRIVERS[selected](root=root)
    except KeyError:
        raise ValueError(f"unknown NLE driver: {selected} (available: {sorted(DRIVERS)})")
