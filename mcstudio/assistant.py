from __future__ import annotations

import csv
import io
import json
import os
import re
import secrets
import shutil
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .core import StudioError, evaluate_stage, get_stage, load_project, load_stages, read_json, save_project, utc_now, write_json
from .workspace import read_text_file, safe_video_file, write_text_file
from .runners import execute_runner, quick_runner_statuses


SCENE_CARD_PATH = ".studio/internal/story/scene-cards.csv"
SCENE_CARD_COLUMNS = [
    "scene_id",
    "sequence_id",
    "location",
    "time",
    "pov",
    "scene_purpose",
    "entry_state",
    "objective",
    "reason_objective_matters",
    "obstacle",
    "opposing_agent",
    "tactics",
    "information_revealed",
    "information_withheld",
    "emotional_progression",
    "visual_event",
    "turn",
    "outcome",
    "exit_state",
    "new_question",
    "setup_or_payoff",
    "story_value",
    "production_requirements",
]

REASONING_LEVELS: dict[str, dict[str, str]] = {
    "low": {
        "label": "Low",
        "description": "Fast responses with lighter reasoning.",
    },
    "medium": {
        "label": "Medium",
        "description": "Balances speed and reasoning depth for everyday tasks.",
    },
    "high": {
        "label": "High",
        "description": "Greater reasoning depth for complex problems.",
    },
    "xhigh": {
        "label": "Extra high",
        "description": "Extra high reasoning depth for complex problems.",
    },
    "max": {
        "label": "Max",
        "description": "Maximum reasoning depth. Consumes usage limits faster.",
    },
    "ultra": {
        "label": "Ultra",
        "description": "Highest available reasoning depth. Consumes usage limits fastest.",
    },
}

MODEL_REASONING_PROFILES: dict[str, dict[str, Any]] = {
    "gpt-5.6-sol": {
        "default": "low",
        "levels": ["low", "medium", "high", "xhigh", "max", "ultra"],
        "more_reasoning": ["max", "ultra"],
    },
    "gpt-5.6-terra": {
        "default": "medium",
        "levels": ["low", "medium", "high", "xhigh", "max", "ultra"],
        "more_reasoning": ["max", "ultra"],
    },
    "gpt-5.6-luna": {
        "default": "medium",
        "levels": ["low", "medium", "high", "xhigh", "max"],
        "more_reasoning": ["max"],
    },
    "gpt-5.5": {
        "default": "medium",
        "levels": ["low", "medium", "high", "xhigh"],
        "more_reasoning": [],
    },
    "gpt-5.4": {
        "default": "medium",
        "levels": ["low", "medium", "high", "xhigh"],
        "more_reasoning": [],
    },
    "gpt-5.4-mini": {
        "default": "medium",
        "levels": ["low", "medium", "high", "xhigh"],
        "more_reasoning": [],
    },
}

LEGACY_MODEL_ALIASES = {
    "gpt-5.6": "gpt-5.6-luna",
}

GENERIC_REASONING_PROFILE: dict[str, Any] = {
    "default": "medium",
    "levels": ["low", "medium", "high", "xhigh"],
    "more_reasoning": [],
}


def normalise_model(model: str) -> str:
    value = str(model or "").strip()
    return LEGACY_MODEL_ALIASES.get(value, value)


def reasoning_profile(model: str) -> dict[str, Any]:
    return MODEL_REASONING_PROFILES.get(normalise_model(model), GENERIC_REASONING_PROFILE)


def normalise_reasoning_effort(model: str, effort: str) -> str:
    profile = reasoning_profile(model)
    value = str(effort or "").strip().lower()
    return value if value in profile["levels"] else str(profile["default"])


DEFAULT_SETTINGS = {
    "provider": "runner_manager",
    "routing_mode": "automatic",
    "fixed_runner": "codex",
    "fallback_enabled": True,
    "fallback_order": ["codex", "opencode", "openai"],
    "routes": {
        "creative": "codex",
        "production": "opencode",
        "audit": "opencode",
    },
    "web_search_default": False,
    "visible_runner_terminal": True,
    "runner_terminal_host": "windows_terminal",
    "codex_full_output": True,
    "runners": {
        "codex": {
            "enabled": True,
            "command": "codex",
            "model": "gpt-5.6-luna",
            "reasoning_effort": "medium",
            "timeout_seconds": 3600,
        },
        "opencode": {
            "enabled": True,
            "command": "opencode",
            "model": "",
            "variant": "",
            "agent": "studio-assistant",
            "timeout_seconds": 3600,
        },
        "openai": {
            "enabled": True,
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-5.6-luna",
            "reasoning_effort": "medium",
            "api_key": "",
            "remember_api_key": True,
            "timeout_seconds": 600,
        },
    },
    # Legacy mirrors retained so v0.3.2 settings and external scripts still load.
    "base_url": "https://api.openai.com/v1",
    "model": "gpt-5.6-luna",
    "reasoning_effort": "medium",
    "api_key": "",
    "remember_api_key": True,
    "apps": {
        "minecraft": {"label": "Minecraft", "command": "", "working_directory": ""},
        "blender": {"label": "Blender", "command": "", "working_directory": ""},
        "video_editor": {"label": "Video editor", "command": "", "working_directory": ""},
        "audio_editor": {"label": "Audio editor", "command": "", "working_directory": ""},
    },
}

PHASE_EXTRA_FILES: dict[str, list[str]] = {
    "direction": [
        ".studio/internal/direction/idea-score.json",
        ".studio/internal/research/inspiration-analysis.md",
        ".studio/internal/research/source-ledger.csv",
        ".studio/internal/research/claims.md",
    ],
    "story": [
        ".studio/internal/story/story-model.json",
        ".studio/internal/story/causal-spine.csv",
        ".studio/internal/story/sequence-outline.csv",
        ".studio/internal/story/beat-sheet.csv",
        ".studio/internal/story/scene-cards.csv",
        ".studio/internal/story/information-map.csv",
        ".studio/internal/story/setup-payoff-ledger.csv",
        ".studio/internal/story/relationships.csv",
        ".studio/internal/story/continuity-bible.md",
    ],
    "script": [
        ".studio/internal/script/revision-pass-status.json",
        ".studio/internal/script/table-read-notes.md",
        ".studio/internal/script/pronunciation-guide.md",
        ".studio/internal/script/script-qc.md",
    ],
    "production": [
        ".studio/internal/production/storyboard-plan.md",
        ".studio/internal/research/source-ledger.csv",
        ".studio/internal/research/claims.md",
        ".studio/internal/production/technical-research.md",
        ".studio/internal/production/toolchain-matrix.csv",
        ".studio/internal/production/scene-implementation-matrix.csv",
        ".studio/internal/production/test-matrix.csv",
        ".studio/internal/production/storyboard-panels.csv",
        ".studio/internal/production/shot-list.csv",
        ".studio/internal/production/camera-paths.csv",
        ".studio/internal/production/asset-register.csv",
        ".studio/internal/production/location-cards.csv",
        ".studio/internal/production/location-plan.md",
        ".studio/internal/production/seed-scouting-log.csv",
        ".studio/internal/production/world-state-register.csv",
        ".studio/internal/production/installed-profile-inventory.csv",
        ".studio/internal/production/build-budget.md",
        ".studio/internal/production/risk-register.md",
        ".studio/internal/production/build-log.md",
    ],
    "edit": [
        ".studio/internal/edit/sound-plan.md",
        ".studio/internal/edit/export-qc.md",
        ".studio/internal/edit/final-qc.md",
        ".studio/internal/edit/captions-en-GB.srt",
    ],
    "release": [
        ".studio/internal/release/metadata.json",
        ".studio/internal/release/description.md",
        ".studio/internal/release/pinned-comment.md",
        ".studio/internal/release/thumbnail-brief.md",
        ".studio/internal/release/thumbnail-concepts.json",
        ".studio/internal/release/social-pack.md",
        ".studio/internal/release/promise-alignment.md",
        ".studio/internal/release/publish-checklist.md",
        ".studio/internal/release/release-record.json",
    ],
    "learn": [
        ".studio/internal/learn/postmortem.md",
        ".studio/internal/learn/retention-analysis.md",
        ".studio/internal/learn/lessons.csv",
    ],
}

PRODUCTION_DEEP_DIVE = """
Production is a research-first design phase, not only a shot-list phase. When the user requests a complete plan:
- Treat the locked Script as authority and cover every scripted scene and causal beat without changing canon.
- Compare plausible Minecraft Java, loader, API and mod-version intersections. Prefer official project pages, documentation, source repositories and exact release pages. Record URLs, publishers, publication/update dates when available, access date, licence, dependency chain and evidence tier in the research ledger.
- Never infer that a combined stack works merely because each component lists the same Minecraft version. Label this as documented individual support until an integrated proof-of-concept is actually run.
- Build a scene-by-scene implementation matrix: preferred live method, deterministic controls, camera method, VFX/composite method, fallback and test ID.
- Under solo-creator constraints, prefer scouting existing seeds/worlds and adapting the closest camera-feasible location over constructing terrain from scratch. The selected and corrected location may be R0 itself. Permit documented terrain/structure imports, duplicate R0 only after shared camera-visible geography is stable, derive close variants such as R4 directly from R0, and plan custom-dimension consolidation only for the final filming master.
- Maintain a seed/location shortlist, an installed-profile inventory and a world-state register. Distinguish separate authoring saves from final dimension IDs, record transfer scope and entity/POI policy, and never imply that copied chunks or custom-dimension generation have been tested when they have not.
- Design a resettable take-control system before proposing a custom mod. Evaluate vanilla commands, datapack functions, entity tags/NBT, scoreboard state, structure or region resets, fixed weather/time, spawn suppression, Carpet/Scarpet, replay/camera tools and actor/NPC tools. Specify setup, arm, action, reset and cleanup procedures. Do not claim they were tested.
- Create a storyboard optimised for a creator with aphantasia. It must be literal and spatial rather than evocative: panel frame description, 3x3 composition, camera height/FOV or lens, subject coordinates or screen position, facing, eyeline, foreground/midground/background, movement arrows in words, lighting direction, continuity anchors, transition, audio cue and capture purpose. Include compact text-only overhead/elevation diagrams where they reduce ambiguity.
- Do not generate, embed or claim any storyboard image. The plan may recommend and compare current image-generation models and define a later consistency test. Prefer reference-driven screenshot-to-sketch transformation over independent text-to-image generation.
- Preserve a minimum of two storyboard panels per scripted scene, increasing coverage for complex action or match cuts.
- Separate researched facts, provisional recommendations, planned tests and verified results. Unknowns remain explicit blockers or test tasks rather than confident prose.
"""


NON_FABRICATION = {
    "direction": "Do not invent external sources. If research is needed and web search is unavailable, mark research evidence as incomplete.",
    "story": "You may design the story, but do not claim audience testing or production validation occurred.",
    "script": "Do not claim a table read, performance test, or spoken pass occurred unless the supplied context records it. You may prepare notes as pending.",
    "production": "Research and plan the technical stack, deterministic staging, scene implementation, tests, storyboard, shots, assets, locations, budget and risks. Never invent captured takes, completed builds, installed versions, combined compatibility, licences, file names, test results, generated storyboard images, or technical success. Do not write capture-log.csv or audio-capture-log.csv.",
    "edit": "Do not claim a master was watched, audio measured, captions timed, or export verified unless evidence is supplied. Keep unverified checks explicitly pending.",
    "release": "Prepare packaging and metadata, but never claim publication, approval, rights clearance, or upload occurred.",
    "learn": "Separate observations from hypotheses. Never invent analytics, comments, retention behaviour, or causal explanations.",
}


def settings_path(root: Path) -> Path:
    return root / "studio" / "local-settings.json"


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def _checked(payload: dict[str, Any], key: str, default: bool = False) -> bool:
    if key not in payload:
        return default
    return str(payload.get(key, "")).lower() in {"1", "true", "yes", "on"}


def load_settings(root: Path, include_secret: bool = True) -> dict[str, Any]:
    settings = json.loads(json.dumps(DEFAULT_SETTINGS))
    path = settings_path(root)
    stored: dict[str, Any] = {}
    if path.is_file():
        try:
            stored = read_json(path)
            if isinstance(stored, dict):
                _deep_merge(settings, stored)
        except StudioError:
            stored = {}

    # Migrate the v0.3.2 direct-API layout into the OpenAI fallback runner.
    openai = settings.setdefault("runners", {}).setdefault("openai", {})
    if "runners" not in stored:
        for key in ("base_url", "model", "reasoning_effort", "api_key", "remember_api_key"):
            if key in stored:
                openai[key] = stored[key]
    env_key = os.environ.get("OPENAI_API_KEY", "")
    if env_key:
        openai["api_key"] = env_key
        settings["api_key_source"] = "environment"
    else:
        settings["api_key_source"] = "local" if openai.get("api_key") else "missing"

    for runner_name in ("codex", "openai"):
        runner = settings["runners"][runner_name]
        runner["model"] = normalise_model(str(runner.get("model") or DEFAULT_SETTINGS["runners"][runner_name]["model"]))
        runner["reasoning_effort"] = normalise_reasoning_effort(
            runner["model"], str(runner.get("reasoning_effort") or "")
        )

    # Older dashboard/provider UIs could save a display label rather than the
    # exact OpenCode provider/model identifier. Treat that as automatic instead
    # of repeatedly sending an invalid --model value.
    opencode = settings["runners"].setdefault("opencode", {})
    opencode_model = str(opencode.get("model") or "").strip()
    if opencode_model and not re.fullmatch(r"[^\s/]+/[^\s]+", opencode_model):
        opencode["model"] = ""

    # Keep the legacy fields coherent for upgrades and the direct API helper.
    settings["base_url"] = openai.get("base_url", DEFAULT_SETTINGS["base_url"])
    settings["model"] = openai.get("model", DEFAULT_SETTINGS["model"])
    settings["reasoning_effort"] = openai.get("reasoning_effort", DEFAULT_SETTINGS["reasoning_effort"])
    settings["api_key"] = openai.get("api_key", "")
    settings["remember_api_key"] = bool(openai.get("remember_api_key", True))

    if not include_secret:
        settings["has_api_key"] = bool(openai.get("api_key"))
        settings["api_key"] = ""
        settings["runners"]["openai"]["has_api_key"] = bool(openai.get("api_key"))
        settings["runners"]["openai"]["api_key"] = ""
        settings["runner_status"] = quick_runner_statuses(settings)
    return settings


def save_settings(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    current = load_settings(root, include_secret=True)
    current["provider"] = "runner_manager"
    current["routing_mode"] = str(payload.get("routing_mode") or current.get("routing_mode") or "automatic")
    current["fixed_runner"] = str(payload.get("fixed_runner") or current.get("fixed_runner") or "codex")
    current["fallback_enabled"] = _checked(payload, "fallback_enabled")
    order = [item.strip() for item in str(payload.get("fallback_order") or "codex,opencode,openai").split(",")]
    current["fallback_order"] = [item for item in order if item in {"codex", "opencode", "openai"}]
    routes = current.setdefault("routes", {})
    for group, fallback in (("creative", "codex"), ("production", "opencode"), ("audit", "opencode")):
        value = str(payload.get(f"route_{group}") or routes.get(group) or fallback)
        routes[group] = value if value in {"codex", "opencode", "openai"} else fallback
    current["web_search_default"] = _checked(payload, "web_search_default")
    current["visible_runner_terminal"] = _checked(payload, "visible_runner_terminal", True)
    terminal_host = str(
        payload.get("runner_terminal_host")
        or current.get("runner_terminal_host")
        or "windows_terminal"
    ).strip().lower()
    current["runner_terminal_host"] = (
        terminal_host if terminal_host in {"windows_terminal", "powershell"} else "windows_terminal"
    )
    current["codex_full_output"] = _checked(payload, "codex_full_output", True)

    runners = current.setdefault("runners", {})
    codex = runners.setdefault("codex", {})
    codex.update({
        "enabled": _checked(payload, "runner_codex_enabled"),
        "command": str(payload.get("runner_codex_command") or "codex").strip(),
        "model": normalise_model(str(payload.get("runner_codex_model") or codex.get("model") or "gpt-5.6-luna")),
        "timeout_seconds": max(300, min(14400, int(payload.get("runner_codex_timeout") or codex.get("timeout_seconds") or 3600))),
    })
    codex["reasoning_effort"] = normalise_reasoning_effort(
        codex["model"], str(payload.get("runner_codex_reasoning") or codex.get("reasoning_effort") or "")
    )

    opencode = runners.setdefault("opencode", {})
    opencode_model = str(payload.get("runner_opencode_model") or "").strip()
    if opencode_model and not re.fullmatch(r"[^\s/]+/[^\s]+", opencode_model):
        opencode_model = ""
    opencode.update({
        "enabled": _checked(payload, "runner_opencode_enabled"),
        "command": str(payload.get("runner_opencode_command") or "opencode").strip(),
        "model": opencode_model,
        "variant": str(payload.get("runner_opencode_variant") or "").strip(),
        "agent": str(payload.get("runner_opencode_agent") or "studio-assistant").strip(),
        "timeout_seconds": max(300, min(14400, int(payload.get("runner_opencode_timeout") or opencode.get("timeout_seconds") or 3600))),
    })

    openai = runners.setdefault("openai", {})
    openai.update({
        "enabled": _checked(payload, "runner_openai_enabled"),
        "base_url": str(payload.get("runner_openai_base_url") or openai.get("base_url") or "https://api.openai.com/v1").strip().rstrip("/"),
        "model": normalise_model(str(payload.get("runner_openai_model") or openai.get("model") or "gpt-5.6-luna")),
        "remember_api_key": _checked(payload, "remember_api_key"),
        "timeout_seconds": int(payload.get("runner_openai_timeout") or openai.get("timeout_seconds") or 600),
    })
    openai["reasoning_effort"] = normalise_reasoning_effort(
        openai["model"], str(payload.get("runner_openai_reasoning") or openai.get("reasoning_effort") or "")
    )
    supplied_key = str(payload.get("api_key") or "").strip()
    if supplied_key:
        openai["api_key"] = supplied_key if openai["remember_api_key"] else ""
        os.environ["OPENAI_API_KEY"] = supplied_key
    elif _checked(payload, "clear_api_key"):
        openai["api_key"] = ""
        os.environ.pop("OPENAI_API_KEY", None)

    current["base_url"] = openai["base_url"]
    current["model"] = openai["model"]
    current["reasoning_effort"] = openai["reasoning_effort"]
    current["api_key"] = openai.get("api_key", "")
    current["remember_api_key"] = openai["remember_api_key"]

    apps = current.setdefault("apps", {})
    for app_id in DEFAULT_SETTINGS["apps"]:
        apps.setdefault(app_id, {}).update({
            "label": DEFAULT_SETTINGS["apps"][app_id]["label"],
            "command": str(payload.get(f"app_{app_id}_command") or "").strip(),
            "working_directory": str(payload.get(f"app_{app_id}_cwd") or "").strip(),
        })
    serialisable = {key: value for key, value in current.items() if key not in {"api_key_source", "runner_status", "has_api_key"}}
    settings_path(root).parent.mkdir(parents=True, exist_ok=True)
    write_json(settings_path(root), serialisable)
    return load_settings(root, include_secret=False)


def _document_context(root: Path, slug: str) -> str:
    video_dir, project = load_project(root, slug)
    stages = load_stages(root)
    current_index = [item["name"] for item in stages].index(project["stage"])
    chunks = []
    for stage in stages[: current_index + 1]:
        rel = stage.get("user_document")
        if not rel:
            continue
        path = video_dir / rel
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            chunks.append(f"\n===== {stage['label']} document: {rel} =====\n{text[:30000]}")
    return "".join(chunks)


def _template_examples(root: Path, slug: str, paths: list[str]) -> str:
    video_dir, _ = load_project(root, slug)
    chunks = []
    for rel in paths:
        path = video_dir / rel
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            chunks.append(f"\n--- Required file {rel}; preserve its schema/columns ---\n{text[:10000]}")
    return "".join(chunks)


def build_prompt(root: Path, slug: str, user_request: str, mode: str = "develop") -> tuple[str, str, list[str]]:
    video_dir, project = load_project(root, slug)
    stage = get_stage(root, project["stage"])
    document_path = stage["user_document"]
    allowed = list(dict.fromkeys(PHASE_EXTRA_FILES.get(project["stage"], [])))
    doctrine = (root / "studio" / "writing-doctrine.json").read_text(encoding="utf-8", errors="replace")
    source_policy = (root / "studio" / "source-policy.json").read_text(encoding="utf-8", errors="replace")
    automation = (root / "studio" / "automation-policy.json").read_text(encoding="utf-8", errors="replace")
    context = _document_context(root, slug)
    examples = _template_examples(root, slug, allowed)
    checks = evaluate_stage(root, slug, include_approval=False)
    check_text = "\n".join(f"- {'PASS' if item.ok else 'BLOCKER'} · {item.label}: {item.detail}" for item in checks)
    instruction = f"""You are the Studio Assistant inside Minecraft Narrative Studio v0.3.6.
Work on exactly one video and its current phase. Use British English for public-facing writing. BRL is the business currency.
Respect the supplied writing doctrine, source policy, automation policy, established canon and previous approved decisions.
Never use rigid storytelling formulae as mandatory rules. Prefer causality, audience promise, character agency, visual storytelling and feasible Minecraft production.
This is a focused proposal-generation task. The complete project context, schemas and deterministic findings are supplied below. Do not inspect the repository, read AGENTS.md or skills, run shell commands, invoke mcstudio, use Git, browse files, modify files, or perform independent maintenance/audits. Produce the requested final JSON directly from the supplied context. The dashboard—not the model—runs deterministic checks and applies files after human review.
{NON_FABRICATION.get(project['stage'], '')}
{PRODUCTION_DEEP_DIVE if project['stage'] == 'production' else ''}
Return STRICT JSON only, with no Markdown fences and this exact top-level shape:
{{
  "summary": "concise explanation of what you changed and any unresolved issue",
  "document": "complete replacement Markdown for {document_path}",
  "files": {{"allowed/auxiliary/path": "complete file content"}},
  "questions": ["only genuinely blocking questions"],
  "warnings": ["uncertainties or evidence still needed"]
}}
The top-level document field is the complete replacement for {document_path}. Do not repeat {document_path} inside files. Only use auxiliary paths from the allowed auxiliary list. Include every auxiliary file that can be completed honestly. Preserve required JSON schemas and CSV headers exactly. CSV values must be valid RFC-style CSV text. Do not include project.json. Do not write capture-log.csv, upload records, approvals, or claims of actions not evidenced.
"""
    request = f"""VIDEO
Title: {project['title']}
Slug: {slug}
Current phase: {stage['label']}
Mode: {mode}

USER REQUEST
{user_request.strip() or 'Develop the strongest honest version of the current phase from the available context. Fill what can be determined, make uncertainty explicit, and avoid unnecessary questions.'}

MAIN DOCUMENT
- {document_path} — return this only in the top-level document field

ALLOWED AUXILIARY FILES
""" + ("".join(f"- {path}\n" for path in allowed) or "- None\n") + f"""

WRITING DOCTRINE
{doctrine[:30000]}

SOURCE POLICY
{source_policy[:12000]}

AUTOMATION POLICY
{automation[:12000]}

DETERMINISTIC PHASE CHECKS
{check_text}

PROJECT CONTEXT
{context}

CURRENT INTERNAL FILE SCHEMAS/TEMPLATES
{examples}
"""
    return instruction, request, allowed


def _responses_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    return base if base.endswith("/responses") else base + "/responses"


def _extract_output_text(payload: dict[str, Any]) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct
    texts: list[str] = []
    for item in payload.get("output", []) if isinstance(payload.get("output"), list) else []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for part in item.get("content", []) if isinstance(item.get("content"), list) else []:
            if isinstance(part, dict) and part.get("type") == "output_text" and isinstance(part.get("text"), str):
                texts.append(part["text"])
    if texts:
        return "\n".join(texts)
    raise StudioError("The AI response did not contain text output.")


def _parse_json_text(text: str) -> dict[str, Any]:
    stripped = text.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", stripped, re.DOTALL | re.IGNORECASE)
    if fenced:
        stripped = fenced.group(1).strip()
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            try:
                value = json.loads(stripped[start:end + 1])
            except json.JSONDecodeError as exc:
                raise StudioError(f"AI returned invalid JSON: {exc}") from exc
        else:
            raise StudioError("AI returned text instead of the required JSON object.")
    if not isinstance(value, dict):
        raise StudioError("AI response must be a JSON object.")
    return value


def call_openai(root: Path, instructions: str, input_text: str, use_web_search: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    settings = load_settings(root, include_secret=True)
    api_key = str(settings.get("api_key") or "").strip()
    if not api_key:
        raise StudioError("Configure an OpenAI API key in Dashboard → Settings, or import a proposal manually.")
    payload: dict[str, Any] = {
        "model": settings.get("model") or DEFAULT_SETTINGS["model"],
        "instructions": instructions,
        "input": input_text,
        "max_output_tokens": 30000,
    }
    effort = settings.get("reasoning_effort")
    if effort and effort != "none":
        payload["reasoning"] = {"effort": effort}
    if use_web_search:
        payload["tools"] = [{"type": "web_search"}]
    request = urllib.request.Request(
        _responses_url(str(settings.get("base_url") or DEFAULT_SETTINGS["base_url"])),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(body).get("error", {}).get("message", body)
        except json.JSONDecodeError:
            detail = body
        raise StudioError(f"OpenAI API error {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise StudioError(f"Could not reach the AI service: {exc.reason}") from exc
    text = _extract_output_text(raw)
    return _parse_json_text(text), raw


def proposal_dir(root: Path, slug: str) -> Path:
    video_dir, _ = load_project(root, slug)
    path = video_dir / ".studio" / "proposals"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _looks_like_setup_payoff_refs(value: str) -> bool:
    parts = [item.strip() for item in re.split(r"[;|]", value) if item.strip()]
    if not parts:
        return False
    return all(re.fullmatch(r"(?:SP|PAY|OPEN)-[A-Za-z0-9_-]+", item) for item in parts)


def _normalise_scene_card_csv(content: str) -> tuple[str, list[str]]:
    """Repair the known one-column scene-card shift without inventing story content.

    Codex occasionally omits ``exit_state`` while still returning every field
    after it. ``csv.DictReader`` then silently shifts ``new_question`` through
    ``production_requirements`` one column left. The scene outcome already
    records the post-scene state, so copying it into ``exit_state`` is a safe
    schema repair that preserves every generated value and restores the
    intended trailing columns.
    """

    try:
        reader = csv.reader(io.StringIO(content))
        header = next(reader)
    except (StopIteration, csv.Error):
        return content, []

    if header != SCENE_CARD_COLUMNS:
        return content, []

    repaired_rows: list[list[str]] = [header]
    repaired_ids: list[str] = []
    exit_index = header.index("exit_state")
    outcome_index = header.index("outcome")
    setup_index_after_shift = header.index("setup_or_payoff") - 1

    for row in reader:
        if len(row) == len(header):
            repaired_rows.append(row)
            continue

        likely_missing_exit_state = (
            len(row) == len(header) - 1
            and len(row) > setup_index_after_shift
            and _looks_like_setup_payoff_refs(row[setup_index_after_shift])
            and bool(row[outcome_index].strip())
        )
        if not likely_missing_exit_state:
            repaired_rows.append(row)
            continue

        scene_id = row[0].strip() if row else f"row-{len(repaired_rows)}"
        row = list(row)
        row.insert(exit_index, row[outcome_index])
        repaired_rows.append(row)
        repaired_ids.append(scene_id)

    if not repaired_ids:
        return content, []

    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerows(repaired_rows)
    return output.getvalue(), repaired_ids


def validate_proposal(root: Path, slug: str, proposal: dict[str, Any]) -> dict[str, Any]:
    _, project = load_project(root, slug)
    stage = get_stage(root, project["stage"])
    allowed = set(PHASE_EXTRA_FILES.get(project["stage"], []))
    document = proposal.get("document")
    if not isinstance(document, str) or len(document.strip()) < 40:
        raise StudioError("Proposal is missing a substantive document.")
    files = proposal.get("files", {})
    if isinstance(files, list):
        mapped: dict[str, str] = {}
        for index, item in enumerate(files, start=1):
            if not isinstance(item, dict):
                raise StudioError(f"Proposal file entry {index} is not an object.")
            rel = item.get("path")
            content = item.get("content")
            if not isinstance(rel, str) or not rel.strip() or not isinstance(content, str):
                raise StudioError(f"Proposal file entry {index} requires string path and content fields.")
            if rel in mapped:
                raise StudioError(f"Proposal returned the same file more than once: {rel}")
            mapped[rel] = content
        files = mapped
    if not isinstance(files, dict):
        raise StudioError("Proposal files must be an object map or path/content entries.")
    cleaned: dict[str, str] = {}
    normalisation_warnings: list[str] = []
    document_path = stage["user_document"]
    normalised_document = document.replace("\r\n", "\n").strip()
    for rel, content in files.items():
        if not isinstance(rel, str) or not rel.strip():
            raise StudioError("Proposal file paths must be non-empty strings.")
        if not isinstance(content, str):
            raise StudioError(f"Proposal content for {rel} must be text.")
        if rel == document_path:
            # Codex structured output may repeat the main phase document in
            # files even though it already exists in the top-level document
            # field. Accept an exact semantic duplicate and discard it so the
            # document is applied once. Conflicting copies remain an error.
            normalised_copy = content.replace("\r\n", "\n").strip()
            if normalised_copy != normalised_document:
                raise StudioError(
                    f"Proposal returned conflicting content for the main document: {document_path}"
                )
            continue
        if rel not in allowed:
            raise StudioError(f"Proposal attempted to write an unapproved path: {rel}")
        if rel == SCENE_CARD_PATH:
            content, repaired_ids = _normalise_scene_card_csv(content)
            if repaired_ids:
                normalisation_warnings.append(
                    "Dashboard repaired a scene-card CSV column shift by copying each affected "
                    "scene outcome into its missing exit_state field: " + ", ".join(repaired_ids)
                )
        cleaned[rel] = content
    warnings = [str(item) for item in proposal.get("warnings", []) if str(item).strip()]
    warnings.extend(normalisation_warnings)
    return {
        "summary": str(proposal.get("summary") or "Assistant proposal"),
        "document": document,
        "files": cleaned,
        "questions": [str(item) for item in proposal.get("questions", []) if str(item).strip()],
        "warnings": warnings,
        "stage": project["stage"],
        "document_path": stage["user_document"],
    }


def _copy_validation_context(root: Path, slug: str, destination: Path) -> None:
    """Create a small deterministic-check workspace without copying media or backups."""
    source_video, _ = load_project(root, slug)
    target_studio = destination / "studio"
    target_studio.mkdir(parents=True, exist_ok=True)
    for name in ("studio.json", "stages.json", "writing-doctrine.json", "source-policy.json", "automation-policy.json"):
        source = root / "studio" / name
        if source.is_file():
            shutil.copy2(source, target_studio / name)
    target_video = destination / "videos" / slug
    target_video.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_video / "project.json", target_video / "project.json")

    for child in source_video.iterdir():
        if child.is_dir() and re.match(r"^\d{2}-", child.name):
            shutil.copytree(child, target_video / child.name)

    internal = source_video / ".studio" / "internal"
    if internal.is_dir():
        shutil.copytree(internal, target_video / ".studio" / "internal")


def _proposal_stage_blockers(root: Path, slug: str, proposal: dict[str, Any]) -> list[str]:
    """Run the current phase's deterministic validators against an isolated proposal overlay."""
    _, project = load_project(root, slug)
    stage = get_stage(root, project["stage"])
    with tempfile.TemporaryDirectory(prefix="mcstudio-proposal-check-") as temp:
        check_root = Path(temp)
        _copy_validation_context(root, slug, check_root)
        video_dir = check_root / "videos" / slug

        document_path = video_dir / stage["user_document"]
        document_path.parent.mkdir(parents=True, exist_ok=True)
        document_path.write_text(proposal["document"], encoding="utf-8", newline="\n")
        for rel, content in proposal.get("files", {}).items():
            target = video_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")

        findings = evaluate_stage(
            check_root, slug, include_approval=False, validation_scope="proposal"
        )
    return [f"{item.label}: {item.detail}" for item in findings if not item.ok]


def _repair_request(input_text: str, proposal: dict[str, Any], blockers: list[str]) -> str:
    blocker_text = "\n".join(f"- {item}" for item in blockers)
    candidate = {
        "summary": proposal.get("summary", ""),
        "document": proposal.get("document", ""),
        "files": proposal.get("files", {}),
        "questions": proposal.get("questions", []),
        "warnings": proposal.get("warnings", []),
    }
    return f"""{input_text}

BOUNDED VALIDATION REPAIR
The candidate below failed deterministic checks. Return one complete corrected replacement in the same strict JSON shape. Fix only the listed failures and any directly dependent references. Do not inspect files, run commands, or discuss the repair.

FAILURES
{blocker_text}

CANDIDATE TO REPAIR
{json.dumps(candidate, ensure_ascii=False)}
"""


def create_proposal(root: Path, slug: str, user_request: str, mode: str = "develop", use_web_search: bool = False) -> dict[str, Any]:
    instructions, input_text, _ = build_prompt(root, slug, user_request, mode)
    settings = load_settings(root, include_secret=True)
    _, project = load_project(root, slug)

    result, metadata = execute_runner(
        root,
        settings,
        instructions,
        input_text,
        stage=project["stage"],
        mode=mode,
        use_web_search=use_web_search,
    )
    proposal = validate_proposal(root, slug, result)
    blockers = _proposal_stage_blockers(root, slug, proposal)
    repair_metadata: dict[str, Any] = {}

    if blockers:
        runner_name = str(metadata.get("runner") or "")
        if not runner_name:
            raise StudioError("Proposal failed deterministic validation and no runner was available for repair: " + "; ".join(blockers[:8]))
        repair_result, repair_metadata = execute_runner(
            root,
            settings,
            instructions + "\nThis is the single allowed deterministic repair pass. Return the corrected final JSON immediately.",
            _repair_request(input_text, proposal, blockers),
            stage=project["stage"],
            mode="repair",
            use_web_search=False,
            force_runner=runner_name,
        )
        proposal = validate_proposal(root, slug, repair_result)
        remaining = _proposal_stage_blockers(root, slug, proposal)
        if remaining:
            raise StudioError(
                "The assistant proposal still failed deterministic validation after one repair pass: "
                + "; ".join(remaining[:12])
            )

    attempts = list(metadata.get("attempts", []))
    if repair_metadata:
        attempts.append({
            "runner": str(repair_metadata.get("runner") or metadata.get("runner") or ""),
            "status": "repair_success",
            "error": "",
        })

    proposal.update({
        "id": secrets.token_hex(6),
        "created_at": utc_now(),
        "status": "pending",
        "mode": mode,
        "user_request": user_request,
        "runner": metadata.get("runner", ""),
        "model": metadata.get("model", ""),
        "reasoning_effort": metadata.get("reasoning_effort", ""),
        "response_id": metadata.get("response_id", ""),
        "runner_attempts": attempts,
        "deterministic_validation": "passed",
        "repair_pass_used": bool(repair_metadata),
    })
    write_json(proposal_dir(root, slug) / f"{proposal['id']}.json", proposal)
    return proposal


def import_proposal(root: Path, slug: str, text: str) -> dict[str, Any]:
    proposal = validate_proposal(root, slug, _parse_json_text(text))
    proposal.update({
        "id": secrets.token_hex(6),
        "created_at": utc_now(),
        "status": "pending",
        "mode": "imported",
        "user_request": "Imported through dashboard",
        "model": "external",
        "response_id": "",
    })
    write_json(proposal_dir(root, slug) / f"{proposal['id']}.json", proposal)
    return proposal


def recover_latest_runner_proposal(root: Path, slug: str) -> dict[str, Any]:
    """Import the newest completed archived runner result for this video."""
    archive_root = root / "exports" / "runner-runs"
    slug_marker = f"Slug: {slug}"
    candidates: list[Path] = []
    if archive_root.is_dir():
        for filename in ("final-proposal.json", "recovered-proposal.json"):
            for path in archive_root.glob(f"*/{filename}"):
                prompt_path = path.parent / "prompt.txt"
                if not prompt_path.is_file():
                    continue
                prompt = prompt_path.read_text(encoding="utf-8", errors="replace")
                if slug_marker in prompt:
                    candidates.append(path)
    if not candidates:
        raise StudioError(
            "No completed archived runner proposal was found for this video under exports/runner-runs."
        )
    source = max(candidates, key=lambda item: item.stat().st_mtime)
    relative_archive = str(source.parent.relative_to(root)).replace("\\", "/")

    for existing in list_proposals(root, slug):
        if existing.get("source_run_archive") == relative_archive:
            return existing

    proposal = validate_proposal(root, slug, _parse_json_text(source.read_text(encoding="utf-8", errors="replace")))
    metadata_path = source.parent / "metadata.json"
    metadata: dict[str, Any] = {}
    if metadata_path.is_file():
        try:
            loaded = read_json(metadata_path)
            if isinstance(loaded, dict):
                metadata = loaded
        except StudioError:
            metadata = {}
    proposal.update({
        "id": secrets.token_hex(6),
        "created_at": utc_now(),
        "status": "pending",
        "mode": "recovered",
        "user_request": f"Recovered from {relative_archive}",
        "runner": str(metadata.get("runner") or "codex"),
        "model": str(metadata.get("model") or ""),
        "reasoning_effort": str(metadata.get("reasoning_effort") or ""),
        "response_id": str(metadata.get("session_id") or ""),
        "source_run_archive": relative_archive,
        "source_result_file": source.name,
    })
    write_json(proposal_dir(root, slug) / f"{proposal['id']}.json", proposal)
    return proposal


def list_proposals(root: Path, slug: str) -> list[dict[str, Any]]:
    rows = []
    for path in proposal_dir(root, slug).glob("*.json"):
        try:
            value = read_json(path)
        except StudioError:
            continue
        value["_path"] = str(path)
        rows.append(value)
    rows.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return rows


def get_proposal(root: Path, slug: str, proposal_id: str) -> tuple[Path, dict[str, Any]]:
    path = proposal_dir(root, slug) / f"{proposal_id}.json"
    if not path.is_file():
        raise StudioError("Proposal not found.")
    return path, read_json(path)


def update_proposal_document(root: Path, slug: str, proposal_id: str, document: str) -> dict[str, Any]:
    """Save a human-edited main document while keeping the proposal pending."""
    path, proposal = get_proposal(root, slug, proposal_id)
    _, project = load_project(root, slug)
    if proposal.get("status") != "pending":
        raise StudioError("Only a pending proposal can be edited.")
    if proposal.get("stage") != project.get("stage"):
        raise StudioError("This proposal belongs to an earlier phase and can no longer be edited here.")
    if not isinstance(document, str) or len(document.strip()) < 40:
        raise StudioError("The edited proposal must contain a substantive main document.")

    revisions = proposal_dir(root, slug) / "revisions" / proposal_id
    revisions.mkdir(parents=True, exist_ok=True)
    stamp = utc_now().replace(":", "").replace("-", "")
    write_json(revisions / f"{stamp}-{secrets.token_hex(3)}.json", proposal)

    proposal["document"] = document
    proposal["edited_at"] = utc_now()
    proposal["edited_by"] = "Luan"
    proposal["manual_edit_count"] = int(proposal.get("manual_edit_count") or 0) + 1
    write_json(path, proposal)
    return proposal


def apply_edited_proposal(root: Path, slug: str, proposal_id: str, document: str) -> dict[str, Any]:
    """Save the dashboard edits and immediately apply that exact version."""
    update_proposal_document(root, slug, proposal_id, document)
    return apply_proposal(root, slug, proposal_id)


def apply_proposal(root: Path, slug: str, proposal_id: str) -> dict[str, Any]:
    path, proposal = get_proposal(root, slug, proposal_id)
    _, project = load_project(root, slug)
    if proposal.get("status") != "pending":
        raise StudioError("Only a pending proposal can be applied.")
    if proposal.get("stage") != project.get("stage"):
        raise StudioError("This proposal belongs to an earlier phase. Re-run the assistant for the current phase.")
    write_text_file(root, slug, proposal["document_path"], proposal["document"], record_event=False)
    for rel, content in proposal.get("files", {}).items():
        write_text_file(root, slug, rel, content, record_event=False)
    proposal["status"] = "applied"
    proposal["applied_at"] = utc_now()
    write_json(path, proposal)
    video_dir, project = load_project(root, slug)
    project.setdefault("history", []).append({
        "at": utc_now(), "event": "assistant_proposal_applied", "proposal_id": proposal_id,
        "phase": project["stage"], "files": [proposal["document_path"], *proposal.get("files", {}).keys()],
    })
    save_project(video_dir, project)
    return proposal


def discard_proposal(root: Path, slug: str, proposal_id: str) -> None:
    path, proposal = get_proposal(root, slug, proposal_id)
    proposal["status"] = "discarded"
    proposal["discarded_at"] = utc_now()
    write_json(path, proposal)
