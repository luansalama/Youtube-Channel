"""Proposal contract: read-only runners -> structured JSON -> human review -> apply.

Contract (identical for codex/opencode/agy and legacy openai/manual):
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
PARSE_REQUIRED_KEYS = ("summary", "files", "questions", "warnings")


class ProposalFormatError(StudioError):
    """The runner answered, but its proposal payload does not satisfy the contract."""


def normalise_proposal(raw: dict, target_document_path: str = "") -> dict:
    if not isinstance(raw, dict):
        raise ProposalFormatError("proposal must be a JSON object")
    required = REQUIRED_KEYS if not target_document_path else tuple(k for k in REQUIRED_KEYS if k != "document")
    missing = [k for k in required if k not in raw]
    if missing:
        raise ProposalFormatError(f"proposal missing keys: {missing}")
    files = raw["files"]
    if isinstance(files, list):
        norm: dict[str, str] = {}
        for item in files:
            if not isinstance(item, dict) or not isinstance(item.get("path"), str) \
                    or not isinstance(item.get("content"), str):
                raise ProposalFormatError("proposal.files entries must be {path, content} strings")
            if item["path"] in norm:
                raise ProposalFormatError(f"duplicate proposal file: {item['path']}")
            norm[item["path"]] = item["content"]
        files = norm
    if not isinstance(files, dict):
        raise ProposalFormatError("proposal.files must be object or list")
    for k, v in files.items():
        if not isinstance(k, str) or not isinstance(v, str):
            raise ProposalFormatError("proposal file paths/contents must be strings")
    for k in ("questions", "warnings"):
        if not isinstance(raw[k], list) or any(not isinstance(x, str) for x in raw[k]):
            raise ProposalFormatError(f"proposal.{k} must be list[str]")

    raw_doc = raw.get("document", "")
    if isinstance(raw_doc, dict) and isinstance(raw_doc.get("content"), str):
        raw_doc = raw_doc["content"]
    doc = str(raw_doc or "")

    # Some runners put the full target document in files[target] and leave
    # `document` empty/short. That is semantically recoverable and should not
    # trigger another paid model call. Promote it to the canonical field.
    if target_document_path and target_document_path in files:
        target_copy = files[target_document_path]
        if len(doc.strip()) < 40 and len(target_copy.strip()) >= 40:
            doc = target_copy
            files = dict(files)
            files.pop(target_document_path, None)
        elif doc.strip() == target_copy.strip():
            files = dict(files)
            files.pop(target_document_path, None)
        elif len(doc.strip()) >= 40:
            raise ProposalFormatError(
                f"proposal contains two different versions of target document {target_document_path}"
            )

    if len(doc.strip()) < 40:
        raise ProposalFormatError(
            "target document content is too short (<40 chars); put the full target document in `document` "
            "or in files[target_document]"
        )
    return {"summary": str(raw["summary"]), "document": doc, "files": dict(files),
            "questions": list(raw["questions"]), "warnings": list(raw["warnings"])}


def parse_json_text(text: str) -> dict:
    """Extract a proposal JSON object from noisy or multi-object runner output."""
    decoder = json.JSONDecoder()
    candidates: list[dict] = []
    # Prefer fenced payloads, then scan every object start. This handles CLIs
    # that print diagnostics/events or even a duplicate JSON object.
    chunks = [m.group(1) for m in re.finditer(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)]
    chunks.append(text)
    for chunk in chunks:
        for match in re.finditer(r"\{", chunk):
            try:
                obj, _end = decoder.raw_decode(chunk[match.start():])
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                if all(key in obj for key in PARSE_REQUIRED_KEYS):
                    return obj
                candidates.append(obj)
    if candidates:
        # Give envelope-style runners one final chance.
        for obj in candidates:
            structured = obj.get("structured_output")
            if isinstance(structured, dict) and all(k in structured for k in PARSE_REQUIRED_KEYS):
                return structured
            response = obj.get("response")
            if isinstance(response, str) and response != text:
                try:
                    return parse_json_text(response)
                except StudioError:
                    pass
    raise ProposalFormatError("no JSON proposal found in runner output")


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
    norm = normalise_proposal(proposal, target_document_path=str(stage["doc"]))
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
                    stage_id: str | None = None, user_request: str = "",
                    model: str = "", reasoning_effort: str = "") -> dict:
    from .core import evaluate_stage
    vdir, project = load_project(root, slug)
    validated = validate_proposal(root, slug, proposal, stage_id)
    # Deterministic pre-check without duplicating large VOD/master files. The
    # temporary tree lives under the repository (same filesystem), so unchanged
    # files can be hard-linked. Files that the proposal will overwrite are real
    # copies, preventing writes through a hard link into production state.
    import shutil
    import tempfile
    tmp_root = os.path.join(root, ".studio", "tmp", "proposals")
    os.makedirs(tmp_root, exist_ok=True)
    overlay_paths = {validated["document_path"], *validated["files"].keys()}

    def _cheap_copy(src: str, dst: str):
        rel = os.path.relpath(src, vdir).replace("\\", "/")
        if rel in overlay_paths:
            return shutil.copy2(src, dst)
        try:
            os.link(src, dst)
            return dst
        except OSError:
            # If hard links are unavailable, never byte-copy a multi-GB media file
            # just to validate a text proposal. A sparse placeholder preserves the
            # existence/size checks used by proposal validation.
            try:
                size = os.path.getsize(src)
            except OSError:
                size = 0
            if size > 16 * 1024 * 1024:
                with open(dst, "wb") as fh:
                    fh.truncate(size)
                return dst
            return shutil.copy2(src, dst)

    with tempfile.TemporaryDirectory(dir=tmp_root) as tmp:
        tv = os.path.join(tmp, "v")
        shutil.copytree(vdir, tv, ignore=shutil.ignore_patterns("backups", "Auto-Save"), copy_function=_cheap_copy)
        doc_dest = os.path.join(tv, validated["document_path"])
        os.makedirs(os.path.dirname(doc_dest), exist_ok=True)
        # Replace instead of truncating in place in case a target was linked by an
        # older proposal implementation.
        if os.path.exists(doc_dest):
            os.remove(doc_dest)
        with open(doc_dest, "w", encoding="utf-8") as fh:
            fh.write(validated["document"])
        for rel, content in validated["files"].items():
            dest = os.path.join(tv, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            if os.path.exists(dest):
                os.remove(dest)
            with open(dest, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(content)
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
              "model": str(model or ""), "reasoning_effort": str(reasoning_effort or ""),
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
