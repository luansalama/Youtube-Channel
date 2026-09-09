"""Proposal contract: read-only runners -> structured JSON -> human review -> apply.

Contract (identical for codex/opencode/openai/manual):
  {summary, document, files, questions, warnings}
files may be {path: content} or [{path, content}].
"""
from __future__ import annotations
import json
import os
import re
import secrets

from .core import StudioError, get_stage, load_project, read_json, utc_now, write_json
from .workspace import write_text_file

REQUIRED_KEYS = ("summary", "document", "files", "questions", "warnings")


def normalise_proposal(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise StudioError("proposal must be a JSON object")
    missing = [k for k in REQUIRED_KEYS if k not in raw]
    if missing:
        raise StudioError(f"proposal missing keys: {missing}")
    files = raw["files"]
    if isinstance(files, list):
        norm: dict[str, str] = {}
        for item in files:
            if not isinstance(item, dict) or not isinstance(item.get("path"), str) \
                    or not isinstance(item.get("content"), str):
                raise StudioError("proposal.files entries must be {path, content} strings")
            if item["path"] in norm:
                raise StudioError(f"duplicate proposal file: {item['path']}")
            norm[item["path"]] = item["content"]
        files = norm
    if not isinstance(files, dict):
        raise StudioError("proposal.files must be object or list")
    for k, v in files.items():
        if not isinstance(k, str) or not isinstance(v, str):
            raise StudioError("proposal file paths/contents must be strings")
    for k in ("questions", "warnings"):
        if not isinstance(raw[k], list) or any(not isinstance(x, str) for x in raw[k]):
            raise StudioError(f"proposal.{k} must be list[str]")
    doc = str(raw["document"])
    if len(doc.strip()) < 40:
        raise StudioError("proposal.document too short (<40 chars)")
    return {"summary": str(raw["summary"]), "document": doc, "files": dict(files),
            "questions": list(raw["questions"]), "warnings": list(raw["warnings"])}


def parse_json_text(text: str) -> dict:
    """Extract strict JSON object from runner stdout (fenced or bare)."""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidate = m.group(1) if m else text
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass
    # fallback: largest {...} span
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start >= 0 and end > start:
        return json.loads(candidate[start:end + 1])
    raise StudioError("no JSON proposal found in runner output")


def _proposals_dir(vdir: str) -> str:
    p = os.path.join(vdir, ".studio", "proposals")
    os.makedirs(p, exist_ok=True)
    return p


def _allowed_paths(root: str, stage_id: str) -> set[str]:
    """Human doc + internal evidence files for this stage are writable via proposal."""
    from .core import _stage_requirements
    stage = get_stage(root, stage_id)
    reqs = stage.get("requires") or _stage_requirements(root, stage_id)
    paths = {stage["doc"]}
    for r in reqs:
        paths.add(r["path"])
    return paths


def validate_proposal(root: str, slug: str, proposal: dict, stage_id: str | None = None) -> dict:
    vdir, project = load_project(root, slug)
    stage_id = stage_id or project.get("stage", "config")
    stage = get_stage(root, stage_id)
    norm = normalise_proposal(proposal)
    allowed = _allowed_paths(root, stage_id)
    cleaned = {}
    for rel, content in norm["files"].items():
        if ".." in rel or rel.startswith("/") or "\\" in rel:
            raise StudioError(f"proposal path rejected: {rel}")
        if rel == stage["doc"] and content.strip() == norm["document"].strip():
            continue  # duplicate of main document is fine
        if rel not in allowed:
            raise StudioError(f"unapproved proposal path for stage {stage_id}: {rel}")
        cleaned[rel] = content
    return {"summary": norm["summary"], "document": norm["document"], "files": cleaned,
            "questions": norm["questions"], "warnings": norm["warnings"],
            "stage": stage_id, "document_path": stage["doc"]}


def create_proposal(root: str, slug: str, proposal: dict, runner: str = "manual",
                    stage_id: str | None = None, user_request: str = "") -> dict:
    from .core import evaluate_stage
    vdir, project = load_project(root, slug)
    validated = validate_proposal(root, slug, proposal, stage_id)
    # deterministic pre-check: overlay onto temp copies is heavy; run scope=proposal
    # against current tree + overlay in-memory where feasible via file write to temp dir
    import shutil
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tv = os.path.join(tmp, "v")
        shutil.copytree(vdir, tv, ignore=shutil.ignore_patterns(".studio/backups"))
        os.makedirs(os.path.join(tv, os.path.dirname(validated["document_path"])), exist_ok=True)
        with open(os.path.join(tv, validated["document_path"]), "w", encoding="utf-8") as fh:
            fh.write(validated["document"])
        for rel, content in validated["files"].items():
            dest = os.path.join(tv, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(content)
        # evaluate using copied tree by monkey-root: temporarily evaluate manually
        from . import core as _core
        real_prod = _core.prod_path
        try:
            _core.prod_path = lambda _r, _s, _tv=tv: _tv  # noqa: E731
            checks = _core.evaluate_stage(root, slug, validated["stage"], include_approval=False, scope="proposal")
        finally:
            _core.prod_path = real_prod
    failures = [c for c in checks if not c.ok]
    pid = secrets.token_hex(6)
    record = {**validated, "id": pid, "created_at": utc_now(), "status": "pending",
              "runner": runner, "user_request": user_request,
              "deterministic_validation": "passed" if not failures else "failed",
              "blockers": [{"label": c.label, "detail": c.detail} for c in failures]}
    write_json(os.path.join(_proposals_dir(vdir), f"{pid}.json"), record)
    return record


def list_proposals(root: str, slug: str) -> list[dict]:
    vdir, _ = load_project(root, slug)
    d = os.path.join(vdir, ".studio", "proposals")
    if not os.path.isdir(d):
        return []
    out = []
    for fn in sorted(os.listdir(d)):
        if fn.endswith(".json"):
            try:
                out.append(read_json(os.path.join(d, fn)))
            except Exception:
                continue
    return out


def get_proposal(root: str, slug: str, pid: str) -> dict:
    vdir, _ = load_project(root, slug)
    p = os.path.join(vdir, ".studio", "proposals", f"{pid}.json")
    if not os.path.isfile(p):
        raise StudioError(f"proposal not found: {pid}")
    return read_json(p)


def update_proposal_document(root: str, slug: str, pid: str, document: str) -> dict:
    vdir, _ = load_project(root, slug)
    rec = get_proposal(root, slug, pid)
    if rec.get("status") != "pending":
        raise StudioError("only pending proposals can be edited")
    if len(document.strip()) < 40:
        raise StudioError("edited document too short")
    revdir = os.path.join(vdir, ".studio", "proposals", "revisions", pid)
    os.makedirs(revdir, exist_ok=True)
    write_json(os.path.join(revdir, f"{utc_now().replace(':','')}-edit.json"), {"document": rec["document"]})
    rec["document"] = document
    write_json(os.path.join(vdir, ".studio", "proposals", f"{pid}.json"), rec)
    return rec


def apply_proposal(root: str, slug: str, pid: str, by: str = "showrunner", edited_document: str | None = None) -> dict:
    """Human-triggered deterministic apply. Runner output never applies itself."""
    vdir, project = load_project(root, slug)
    rec = get_proposal(root, slug, pid)
    if rec.get("status") != "pending":
        raise StudioError("proposal already decided")
    doc = edited_document if edited_document is not None else rec["document"]
    if len(doc.strip()) < 40:
        raise StudioError("document too short")
    write_text_file(root, slug, rec["document_path"], doc, by=f"{by}:proposal:{pid}")
    for rel, content in rec["files"].items():
        dest = os.path.join(vdir, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content)
    rec["status"] = "applied"
    rec["applied_at"] = utc_now()
    rec["applied_by"] = by
    write_json(os.path.join(vdir, ".studio", "proposals", f"{pid}.json"), rec)
    vdir2, project2 = load_project(root, slug)
    project2.setdefault("history", []).append(
        {"at": utc_now(), "event": "assistant_proposal_applied", "proposal_id": pid, "by": by})
    from .core import save_project
    save_project(vdir2, project2)
    return rec


def discard_proposal(root: str, slug: str, pid: str, by: str = "showrunner") -> dict:
    vdir, _ = load_project(root, slug)
    rec = get_proposal(root, slug, pid)
    rec["status"] = "discarded"
    rec["decided_by"] = by
    write_json(os.path.join(vdir, ".studio", "proposals", f"{pid}.json"), rec)
    return rec
