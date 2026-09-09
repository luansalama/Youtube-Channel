from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

PLACEHOLDER_TOKENS = ("TODO", "TBD", "{{", "<replace", "[write here]", "[fill")


class StudioError(RuntimeError):
    pass


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    label: str
    detail: str
    severity: str = "error"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    if not value:
        raise StudioError("Could not derive a slug from the supplied title.")
    return value[:80]


def find_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "studio" / "studio.json").is_file():
            return candidate
    raise StudioError("Not inside a Minecraft Narrative Studio repository.")


def read_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        if default is not None:
            return default
        raise StudioError(f"Missing JSON file: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StudioError(f"Invalid JSON in {path}: {exc}") from exc


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def ensure_csv(path: Path, fieldnames: list[str]) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        csv.DictWriter(handle, fieldnames=fieldnames).writeheader()


def append_csv(path: Path, fieldnames: list[str], row: dict[str, Any]) -> None:
    ensure_csv(path, fieldnames)
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writerow({key: row.get(key, "") for key in fieldnames})


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def text_is_substantive(path: Path, min_chars: int = 1) -> tuple[bool, str]:
    if not path.is_file():
        return False, "file is missing"
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if len(text) < min_chars:
        return False, f"only {len(text)} characters; requires {min_chars}"
    lowered = text.lower()
    hits = [token for token in PLACEHOLDER_TOKENS if token.lower() in lowered]
    if hits:
        return False, f"contains placeholder token(s): {', '.join(hits)}"
    return True, f"{len(text)} characters"


def json_placeholder_paths(value: Any, prefix: str = "$") -> list[str]:
    hits: list[str] = []
    if isinstance(value, str):
        lowered = value.lower()
        if any(token.lower() in lowered for token in PLACEHOLDER_TOKENS):
            hits.append(prefix)
    elif isinstance(value, dict):
        for key, child in value.items():
            hits.extend(json_placeholder_paths(child, f"{prefix}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            hits.extend(json_placeholder_paths(child, f"{prefix}[{index}]"))
    return hits


def _check_requirement(video_dir: Path, requirement: dict[str, Any]) -> CheckResult:
    rel = requirement["path"]
    path = video_dir / rel
    label = requirement.get("label", rel)
    kind = requirement.get("kind", "text")

    if kind == "text":
        ok, detail = text_is_substantive(path, int(requirement.get("min_chars", 1)))
        return CheckResult(ok, label, detail)

    if kind == "exists":
        ok = path.exists()
        return CheckResult(ok, label, "present" if ok else "missing")

    if kind == "binary":
        if not path.is_file():
            return CheckResult(False, label, "file is missing")
        minimum = int(requirement.get("min_bytes", 1))
        size = path.stat().st_size
        return CheckResult(size >= minimum, label, f"{size} bytes" if size >= minimum else f"{size} bytes; requires {minimum}")

    if kind == "csv":
        if not path.is_file():
            return CheckResult(False, label, "file is missing")
        rows = read_csv_rows(path)
        nonempty_rows = [row for row in rows if any((value or "").strip() for value in row.values())]
        minimum = int(requirement.get("min_rows", 1))
        if len(nonempty_rows) < minimum:
            return CheckResult(False, label, f"{len(nonempty_rows)} populated row(s); requires {minimum}")
        required_columns = requirement.get("required_columns", [])
        missing_columns = [column for column in required_columns if column not in (rows[0].keys() if rows else [])]
        if missing_columns:
            return CheckResult(False, label, f"missing column(s): {', '.join(missing_columns)}")
        return CheckResult(True, label, f"{len(nonempty_rows)} populated row(s)")

    if kind == "json":
        if not path.is_file():
            return CheckResult(False, label, "file is missing")
        try:
            payload = read_json(path)
        except StudioError as exc:
            return CheckResult(False, label, str(exc))
        if not isinstance(payload, dict):
            return CheckResult(False, label, "JSON root must be an object")
        missing = [key for key in requirement.get("required_keys", []) if payload.get(key) in (None, "", [], {})]
        if missing:
            return CheckResult(False, label, f"empty required key(s): {', '.join(missing)}")
        placeholders = json_placeholder_paths(payload)
        if placeholders:
            shown = ", ".join(placeholders[:5])
            suffix = "..." if len(placeholders) > 5 else ""
            return CheckResult(False, label, f"contains placeholder value(s) at {shown}{suffix}")
        return CheckResult(True, label, "required keys populated; no placeholders")

    raise StudioError(f"Unknown requirement kind: {kind}")


def load_stages(root: Path) -> list[dict[str, Any]]:
    stages = read_json(root / "studio" / "stages.json")
    if not isinstance(stages, list) or not stages:
        raise StudioError("studio/stages.json must contain a non-empty list.")
    return stages


def get_stage(root: Path, stage_name: str) -> dict[str, Any]:
    for stage in load_stages(root):
        if stage["name"] == stage_name:
            return stage
    raise StudioError(f"Unknown stage: {stage_name}")


def video_path(root: Path, slug: str) -> Path:
    path = root / "videos" / slug
    if not (path / "project.json").is_file():
        raise StudioError(f"Unknown video project: {slug}")
    return path


def load_project(root: Path, slug: str) -> tuple[Path, dict[str, Any]]:
    path = video_path(root, slug)
    return path, read_json(path / "project.json")


def save_project(path: Path, project: dict[str, Any]) -> None:
    project["updated_at"] = utc_now()
    write_json(path / "project.json", project)


def initialise_repository(root: Path) -> None:
    for rel, headers in {
        "data/business/ledger.csv": ["date", "type", "amount", "currency", "category", "video", "counterparty", "note"],
        "data/business/deals.csv": ["created_at", "brand", "contact", "status", "value", "currency", "deliverables", "next_action", "next_action_date", "notes"],
        "data/analytics/video_snapshots.csv": ["snapshot_date", "slug", "video_id", "title", "views", "watch_hours", "impressions", "ctr_percent", "average_view_duration", "subscribers_gained", "source_file"],
        "data/ideas.csv": ["created_at", "slug", "title", "premise", "hook", "format", "scope", "clarity", "hook_strength", "visual_potential", "feasibility", "originality", "series_potential", "score", "status", "notes"],
        "data/business/time_log.csv": ["date", "hours", "area", "video", "task", "tool", "notes"],
        "data/channel/content_calendar.csv": ["created_at", "video_slug", "working_title", "format", "pillar", "status", "target_publish", "priority", "dependency", "notes"],
        "data/channel/social_queue.csv": ["created_at", "platform", "video_slug", "target_publish", "status", "copy_file", "asset", "approved_by", "notes"],
        "data/library/assets.csv": ["created_at", "asset_id", "name", "type", "path_or_url", "owner", "licence", "version", "reuse_status", "used_in", "notes"],
    }.items():
        ensure_csv(root / rel, headers)


def render_template(text: str, context: dict[str, str]) -> str:
    for key, value in context.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def active_projects(root: Path) -> list[dict[str, Any]]:
    return [project for project in list_projects(root) if project.get("state", "active") == "active"]


def active_project(root: Path) -> dict[str, Any] | None:
    projects = active_projects(root)
    if len(projects) > 1:
        raise StudioError("More than one active video exists. Pause all but one in Diagnostics before continuing.")
    return projects[0] if projects else None


def create_video(root: Path, title: str, slug: str | None = None) -> Path:
    maintain_repository(root)
    current = active_project(root)
    if current:
        raise StudioError(
            f"'{current['title']}' is already active. Finish, pause, or abandon it before starting another video."
        )
    slug = slugify(slug or title)
    destination = root / "videos" / slug
    if destination.exists():
        raise StudioError(f"Video project already exists: {slug}")
    template_dir = root / "templates" / "video"
    if not template_dir.is_dir():
        raise StudioError("Missing templates/video directory.")
    videos_dir = root / "videos"
    videos_dir.mkdir(parents=True, exist_ok=True)
    working = Path(tempfile.mkdtemp(prefix=f".creating-{slug}-", dir=videos_dir))
    try:
        shutil.copytree(template_dir, working, dirs_exist_ok=True)
        context = {
            "VIDEO_TITLE": title.strip(),
            "VIDEO_SLUG": slug,
            "CREATED_DATE": date.today().isoformat(),
        }
        for path in working.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".md", ".json", ".csv", ".txt", ".srt"}:
                rendered = render_template(path.read_text(encoding="utf-8"), context)
                path.write_text(rendered, encoding="utf-8", newline="\n")
        project = {
            "schema_version": 2,
            "slug": slug,
            "title": title.strip(),
            "stage": "direction",
            "state": "active",
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "approvals": {},
            "history": [{"at": utc_now(), "event": "created", "stage": "direction"}],
            "youtube": {"video_id": "", "published_at": "", "upload_status": "not_started"},
            "media": {"master_file": "", "thumbnail_file": "", "youtube_client_secrets": ""},
        }
        write_json(working / "project.json", project)
        os.replace(working, destination)
    except Exception:
        shutil.rmtree(working, ignore_errors=True)
        raise
    return destination


def stage_evidence_hashes(video_dir: Path, stage: dict[str, Any]) -> dict[str, str]:
    evidence: dict[str, str] = {}
    for requirement in stage.get("requirements", []):
        rel = requirement["path"]
        path = video_dir / rel
        if path.is_file():
            evidence[rel] = sha256_file(path)
    return evidence


def _approval_integrity(video_dir: Path, stage: dict[str, Any], approval: dict[str, Any] | None) -> CheckResult:
    gate = stage.get("approval_gate")
    if not gate:
        return CheckResult(True, f"approval:{stage['name']}", "no approval required")
    if not approval:
        return CheckResult(False, f"approval:{gate}", "not approved")
    recorded = approval.get("evidence")
    if not isinstance(recorded, dict):
        return CheckResult(False, f"approval:{gate}", "approval has no evidence fingerprints; reopen and approve again")
    current = stage_evidence_hashes(video_dir, stage)
    changed = sorted(path for path in set(recorded) | set(current) if recorded.get(path) != current.get(path))
    if changed:
        return CheckResult(False, f"approval:{gate}", f"approved evidence changed: {', '.join(changed)}")
    return CheckResult(True, f"approval:{gate}", f"approved by {approval.get('by')} at {approval.get('at')}; evidence unchanged")


def _conditional_research(video_dir: Path) -> list[CheckResult]:
    score_path = video_dir / ".studio" / "internal" / "direction" / "idea-score.json"
    if not score_path.is_file():
        return [CheckResult(False, "research decision", "internal direction scorecard is missing")]
    try:
        payload = read_json(score_path)
    except StudioError as exc:
        return [CheckResult(False, "research decision", str(exc))]
    mode = str(payload.get("research_mode") or "").strip().lower()
    reason = str(payload.get("research_reason") or "").strip()
    if mode not in {"none", "light", "full"}:
        return [CheckResult(False, "research decision", "research_mode must be none, light, or full")]
    if len(reason) < 20:
        return [CheckResult(False, "research decision", "research_reason must explain the choice")]
    if mode == "none":
        return [CheckResult(True, "research decision", "no external research required; rationale recorded")]

    research_dir = video_dir / ".studio" / "internal" / "research"
    results: list[CheckResult] = []
    inspiration = research_dir / "inspiration-analysis.md"
    ok, detail = text_is_substantive(inspiration, 350)
    results.append(CheckResult(ok, "inspiration/originality review", detail))
    if mode == "full":
        ledger = _check_requirement(video_dir, {
            "path": ".studio/internal/research/source-ledger.csv",
            "kind": "csv",
            "min_rows": 2,
            "required_columns": ["source_id", "claim", "url", "publisher", "published_date", "accessed_date", "source_type", "reliability", "status", "notes"],
            "label": "research source ledger",
        })
        claims = _check_requirement(video_dir, {
            "path": ".studio/internal/research/claims.md", "kind": "text", "min_chars": 450,
            "label": "claims and evidence map",
        })
        results.extend([ledger, claims])
    results.append(CheckResult(True, "research mode", f"{mode} research selected"))
    return results


def _media_validator(video_dir: Path, project: dict[str, Any], key: str, label: str, minimum: int = 1) -> CheckResult:
    rel = str(project.get("media", {}).get(key) or "").strip()
    if not rel:
        return CheckResult(False, label, "not selected or uploaded")
    raw = Path(rel).expanduser()
    path = raw.resolve() if raw.is_absolute() else (video_dir / raw).resolve()
    if not path.is_file():
        return CheckResult(False, label, f"missing: {rel}")
    size = path.stat().st_size
    if size < minimum:
        return CheckResult(False, label, f"{size} bytes; requires at least {minimum}")
    return CheckResult(True, label, f"{rel} ({size} bytes)")


def _capture_evidence(video_dir: Path) -> list[CheckResult]:
    path = video_dir / ".studio" / "internal" / "production" / "capture-log.csv"
    rows = read_csv_rows(path)
    selected = [row for row in rows if str(row.get("selected", "")).strip().lower() in {"yes", "true", "1", "selected"}]
    technically_ok = [row for row in selected if str(row.get("technical_ok", "")).strip().lower() in {"yes", "true", "1", "ok"}]
    return [CheckResult(bool(selected), "selected captured take", f"{len(selected)} selected take(s)" if selected else "no selected take recorded"),
            CheckResult(bool(technically_ok), "technically usable selected take", f"{len(technically_ok)} usable selected take(s)" if technically_ok else "no selected take marked technically usable")]


def _required_for_validation_scope(item: dict[str, Any], validation_scope: str) -> bool:
    """Return whether a configured check belongs to the requested validation scope."""
    if validation_scope == "completion":
        return True
    if validation_scope == "proposal":
        return bool(item.get("proposal_required", True))
    raise StudioError(f"Unknown validation scope: {validation_scope}")


def _run_stage_validators(
    root: Path,
    video_dir: Path,
    stage: dict[str, Any],
    validation_scope: str = "completion",
) -> list[CheckResult]:
    validators = stage.get("validators", [])
    if not validators:
        return []
    from .story import audit_outline, audit_script

    project = read_json(video_dir / "project.json")
    results: list[CheckResult] = []
    for validator in validators:
        config = validator if isinstance(validator, dict) else {"name": validator}
        if not _required_for_validation_scope(config, validation_scope):
            continue
        name = config.get("name")
        if name == "story_outline":
            findings = audit_outline(root, video_dir)
            results.extend(CheckResult(item.ok, item.label, item.detail, item.severity) for item in findings)
        elif name == "story_script":
            findings = audit_script(root, video_dir)
            results.extend(CheckResult(item.ok, item.label, item.detail, item.severity) for item in findings)
        elif name == "conditional_research":
            results.extend(_conditional_research(video_dir))
        elif name == "capture_evidence":
            results.extend(_capture_evidence(video_dir))
        elif name == "master_media":
            results.append(_media_validator(video_dir, project, "master_file", "final master", 1024))
        elif name == "thumbnail_media":
            results.append(_media_validator(video_dir, project, "thumbnail_file", "final thumbnail", 128))
        else:
            raise StudioError(f"Unknown stage validator: {name}")
    return results


def evaluate_stage(
    root: Path,
    slug: str,
    stage_name: str | None = None,
    include_approval: bool = True,
    validation_scope: str = "completion",
) -> list[CheckResult]:
    video_dir, project = load_project(root, slug)
    stages = load_stages(root)
    target_name = stage_name or project["stage"]
    stage = get_stage(root, target_name)
    requirements = [
        req for req in stage.get("requirements", [])
        if _required_for_validation_scope(req, validation_scope)
    ]
    results = [_check_requirement(video_dir, req) for req in requirements]
    results.extend(_run_stage_validators(root, video_dir, stage, validation_scope))
    if include_approval:
        names = [item["name"] for item in stages]
        if target_name not in names:
            raise StudioError(f"Unknown stage: {target_name}")
        target_index = names.index(target_name)
        # When auditing a historical/future named stage, only require its own lock. For the active
        # stage, verify every upstream lock so post-approval drift cannot remain hidden.
        approval_stages = stages[: target_index + 1] if target_name == project["stage"] else [stage]
        for approval_stage in approval_stages:
            gate = approval_stage.get("approval_gate")
            if gate:
                approval = project.get("approvals", {}).get(gate)
                results.append(_approval_integrity(video_dir, approval_stage, approval))
    return results


def approve_gate(root: Path, slug: str, gate: str, approved_by: str, note: str = "") -> None:
    if not approved_by.strip():
        raise StudioError("Approver name cannot be empty.")
    video_dir, project = load_project(root, slug)
    if project.get("state", "active") != "active":
        raise StudioError("Only the active video can receive an approval.")
    current = get_stage(root, project["stage"])
    expected = current.get("approval_gate")
    if expected != gate:
        raise StudioError(f"Current stage '{project['stage']}' expects gate '{expected}', not '{gate}'.")
    blockers = [result for result in evaluate_stage(root, slug, include_approval=False) if not result.ok]
    if blockers:
        message = "; ".join(f"{item.label}: {item.detail}" for item in blockers)
        raise StudioError(f"Cannot approve incomplete stage: {message}")
    project.setdefault("approvals", {})[gate] = {
        "by": approved_by.strip(),
        "at": utc_now(),
        "note": note.strip(),
        "evidence": stage_evidence_hashes(video_dir, current),
    }
    project.setdefault("history", []).append({"at": utc_now(), "event": "approved", "gate": gate, "by": approved_by.strip()})
    save_project(video_dir, project)


def advance_stage(root: Path, slug: str) -> str:
    video_dir, project = load_project(root, slug)
    stages = load_stages(root)
    names = [stage["name"] for stage in stages]
    current = project["stage"]
    if current not in names:
        raise StudioError(f"Project has invalid current phase: {current}")
    blockers = [result for result in evaluate_stage(root, slug) if not result.ok]
    if blockers:
        message = "\n".join(f"- {item.label}: {item.detail}" for item in blockers)
        raise StudioError(f"Phase check failed for '{current}':\n{message}")
    index = names.index(current)
    if index == len(names) - 1:
        project["state"] = "completed"
        project.setdefault("history", []).append({"at": utc_now(), "event": "completed", "phase": current})
        save_project(video_dir, project)
        return "completed"
    next_stage = names[index + 1]
    project["stage"] = next_stage
    project.setdefault("history", []).append({"at": utc_now(), "event": "advanced", "from": current, "to": next_stage})
    save_project(video_dir, project)
    return next_stage


def reopen_stage(root: Path, slug: str, to_stage: str, reopened_by: str, reason: str) -> None:
    if not reopened_by.strip():
        raise StudioError("Reopened-by name cannot be empty.")
    if len(reason.strip()) < 10:
        raise StudioError("Reopen reason must explain the change in at least 10 characters.")
    video_dir, project = load_project(root, slug)
    stages = load_stages(root)
    names = [stage["name"] for stage in stages]
    if to_stage not in names:
        raise StudioError(f"Unknown stage: {to_stage}")
    current = project["stage"]
    if names.index(to_stage) > names.index(current):
        raise StudioError("Reopen may only move to the current or an earlier stage.")
    target_index = names.index(to_stage)
    removed: list[str] = []
    approvals = project.setdefault("approvals", {})
    for stage in stages[target_index:]:
        gate = stage.get("approval_gate")
        if gate and gate in approvals:
            approvals.pop(gate, None)
            removed.append(gate)
    project["stage"] = to_stage
    project.setdefault("history", []).append({
        "at": utc_now(), "event": "reopened", "from": current, "to": to_stage,
        "by": reopened_by.strip(), "reason": reason.strip(), "invalidated_approvals": removed,
    })
    save_project(video_dir, project)


def list_projects(root: Path) -> list[dict[str, Any]]:
    projects: list[dict[str, Any]] = []
    for path in sorted((root / "videos").glob("*/project.json")):
        try:
            project = read_json(path)
        except StudioError:
            continue
        project.setdefault("state", "active")
        project.setdefault("schema_version", 1)
        projects.append(project)
    projects.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
    return projects


def pause_video(root: Path, slug: str, by: str = "Luan", reason: str = "Paused to focus elsewhere") -> None:
    video_dir, project = load_project(root, slug)
    if project.get("state", "active") != "active":
        raise StudioError("Only the active video can be paused.")
    project["state"] = "paused"
    project.setdefault("history", []).append({"at": utc_now(), "event": "paused", "by": by, "reason": reason})
    save_project(video_dir, project)


def resume_video(root: Path, slug: str, by: str = "Luan") -> None:
    if active_project(root):
        raise StudioError("Another video is already active. Pause or finish it first.")
    video_dir, project = load_project(root, slug)
    if project.get("state") not in {"paused"}:
        raise StudioError("Only a paused video can be resumed.")
    project["state"] = "active"
    project.setdefault("history", []).append({"at": utc_now(), "event": "resumed", "by": by})
    save_project(video_dir, project)


def abandon_video(root: Path, slug: str, by: str = "Luan", reason: str = "Project abandoned") -> None:
    video_dir, project = load_project(root, slug)
    if project.get("state", "active") not in {"active", "paused"}:
        raise StudioError("Only an active or paused video can be abandoned.")
    project["state"] = "abandoned"
    project.setdefault("history", []).append({"at": utc_now(), "event": "abandoned", "by": by, "reason": reason})
    save_project(video_dir, project)


def phase_progress(root: Path, project: dict[str, Any]) -> dict[str, Any]:
    stages = load_stages(root)
    names = [item["name"] for item in stages]
    stage_name = project.get("stage", names[0])
    index = names.index(stage_name) if stage_name in names else 0
    state = project.get("state", "active")
    percent = 100 if state == "completed" else round(index / max(1, len(names) - 1) * 100)
    return {"index": index, "total": len(names), "percent": percent, "phase": stage_name}


def workflow_status(root: Path, slug: str | None = None) -> dict[str, Any]:
    project = None
    if slug:
        _, project = load_project(root, slug)
    else:
        project = active_project(root)
    if not project:
        return {
            "status": "no_active_video",
            "headline": "Start one video",
            "next_action": "Create a video project from the dashboard.",
            "can_continue": False,
        }
    stages = load_stages(root)
    stage = get_stage(root, project["stage"])
    checks = evaluate_stage(root, project["slug"], include_approval=False)
    current_index = [item["name"] for item in stages].index(project["stage"])
    for prior_stage in stages[: current_index + 1]:
        prior_gate = prior_stage.get("approval_gate")
        prior_approval = project.get("approvals", {}).get(prior_gate) if prior_gate else None
        if prior_gate and (prior_stage["name"] != project["stage"] or prior_approval):
            checks.append(_approval_integrity(root / "videos" / project["slug"], prior_stage, prior_approval))
    blockers = [item for item in checks if not item.ok]
    gate = stage.get("approval_gate")
    approval = project.get("approvals", {}).get(gate) if gate else None
    if blockers:
        first = blockers[0]
        status = "work_needed"
        headline = f"Complete {stage['label']}"
        next_action = f"{first.label}: {first.detail}"
        can_continue = False
    elif gate and not approval:
        status = "approval_needed"
        headline = f"Review and approve {stage['label']}"
        next_action = stage.get("human_focus", f"Approve {stage['label']}.")
        can_continue = False
    else:
        status = "ready_to_advance"
        headline = f"{stage['label']} is ready"
        next_action = "Continue production; the harness will advance safely."
        can_continue = True
    return {
        "status": status,
        "headline": headline,
        "next_action": next_action,
        "can_continue": can_continue,
        "project": project,
        "stage": stage,
        "checks": checks,
        "blockers": blockers,
        "progress": phase_progress(root, project),
        "user_document": stage.get("user_document", ""),
        "assistant_focus": stage.get("assistant_focus", ""),
        "human_focus": stage.get("human_focus", ""),
        "approval_gate": gate,
    }


def continue_workflow(root: Path, slug: str | None = None) -> dict[str, Any]:
    maintain_repository(root)
    project = None
    if slug:
        _, project = load_project(root, slug)
    else:
        project = active_project(root)
    if not project:
        return workflow_status(root)
    if project.get("state", "active") != "active":
        raise StudioError("Continue works only on the active video.")

    advanced: list[str] = []
    while True:
        status = workflow_status(root, project["slug"])
        if status["status"] != "ready_to_advance":
            status["advanced"] = advanced
            return status
        result = advance_stage(root, project["slug"])
        advanced.append(result)
        if result == "completed":
            return {
                "status": "completed",
                "headline": "Video completed",
                "next_action": "Start the next video when you are ready.",
                "can_continue": False,
                "project": read_json((root / "videos" / project["slug"] / "project.json")),
                "advanced": advanced,
                "progress": {"percent": 100, "phase": "learn", "index": 6, "total": 7},
            }
        _, project = load_project(root, project["slug"])


def _migrate_v02_video_layout(root: Path, video_dir: Path) -> None:
    """Create the v0.3 workspace while preserving a readable backup of a v0.2 project."""
    template_dir = root / "templates" / "video"
    for source in template_dir.rglob("*"):
        relative = source.relative_to(template_dir)
        destination = video_dir / relative
        if source.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        elif not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

    old_dirs = [
        "00-admin", "01-concept", "02-research", "03-outline", "04-script", "05-preproduction",
        "06-build", "07-capture", "08-edit", "09-review", "10-publish", "11-postmortem",
    ]
    backup = video_dir / ".studio" / "migration-backup-v0.2"
    backup.mkdir(parents=True, exist_ok=True)
    for name in old_dirs:
        source = video_dir / name
        if source.exists() and not (backup / name).exists():
            shutil.copytree(source, backup / name)

    def copy_file(old_rel: str, new_rel: str) -> None:
        source = video_dir / old_rel
        destination = video_dir / new_rel
        if source.is_file():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

    # Human-facing documents.
    copy_file("01-concept/concept.md", "01-direction/direction.md")
    if (video_dir / "03-outline/story-outline.md").is_file():
        copy_file("03-outline/story-outline.md", "02-story/story-plan.md")
    else:
        copy_file("03-outline/treatment.md", "02-story/story-plan.md")
    copy_file("04-script/script.md", "03-script/script.md")

    combined_sources = {
        "04-production/production-plan.md": ["05-preproduction/location-plan.md", "05-preproduction/risk-register.md", "06-build/build-log.md", "07-capture/README.md"],
        "05-edit/edit-review.md": ["08-edit/edit-plan.md", "08-edit/edit-review.md", "08-edit/export-qc.md", "09-review/final-qc.md"],
        "06-release/release-plan.md": ["10-publish/promise-alignment.md", "10-publish/thumbnail-brief.md", "10-publish/publish-checklist.md"],
        "07-learn/lessons.md": ["11-postmortem/postmortem.md", "11-postmortem/retention-analysis.md"],
    }
    for destination_rel, source_rels in combined_sources.items():
        chunks: list[str] = []
        for source_rel in source_rels:
            source = video_dir / source_rel
            if source.is_file():
                chunks.append(
                    "\n\n---\n\n## Migrated from `" + source_rel + "`\n\n"
                    + source.read_text(encoding="utf-8", errors="replace")
                )
        if chunks:
            destination = video_dir / destination_rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(
                "# Migrated v0.3 document\n" + "".join(chunks) + "\n",
                encoding="utf-8",
                newline="\n",
            )

    internal_groups = {
        "01-concept": ".studio/internal/direction",
        "02-research": ".studio/internal/research",
        "03-outline": ".studio/internal/story",
        "04-script": ".studio/internal/script",
        "05-preproduction": ".studio/internal/production",
        "06-build": ".studio/internal/production",
        "07-capture": ".studio/internal/production",
        "08-edit": ".studio/internal/edit",
        "09-review": ".studio/internal/edit",
        "10-publish": ".studio/internal/release",
        "11-postmortem": ".studio/internal/learn",
    }
    excluded = {"01-concept/concept.md", "04-script/script.md"}
    for old_dir, new_dir in internal_groups.items():
        source_dir = video_dir / old_dir
        if not source_dir.is_dir():
            continue
        for source in source_dir.iterdir():
            old_rel = f"{old_dir}/{source.name}"
            if source.is_file() and old_rel not in excluded:
                destination = video_dir / new_dir / source.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)

def maintain_repository(root: Path) -> list[CheckResult]:
    initialise_repository(root)
    results: list[CheckResult] = []

    # A v0.3.0 project-creation failure could leave a directory without
    # project.json. Quarantine it instead of allowing it to block the title
    # forever or deleting potentially useful files.
    videos_dir = root / "videos"
    videos_dir.mkdir(parents=True, exist_ok=True)
    recovery_root = root / "exports" / "recovery" / "incomplete-video-projects"
    for candidate in sorted(videos_dir.iterdir()):
        if not candidate.is_dir() or (candidate / "project.json").is_file():
            continue
        recovery_root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        target = recovery_root / f"{candidate.name}-{stamp}"
        counter = 2
        while target.exists():
            target = recovery_root / f"{candidate.name}-{stamp}-{counter}"
            counter += 1
        shutil.move(str(candidate), str(target))
        results.append(CheckResult(
            True,
            "incomplete project recovered",
            f"moved videos/{candidate.name} to {target.relative_to(root)}",
            "warning",
        ))

    studio_path = root / "studio" / "studio.json"
    studio = read_json(studio_path)
    changed = False
    if studio.get("schema_version", 0) < 3:
        studio["schema_version"] = 3
        changed = True
    business = studio.setdefault("business", {})
    if business.get("base_currency") != "BRL":
        business["base_currency"] = "BRL"
        changed = True
    if business.get("commercial_currency") != "BRL":
        business["commercial_currency"] = "BRL"
        changed = True
    if changed:
        write_json(studio_path, studio)
    results.append(CheckResult(True, "studio maintenance", "configuration and ledgers are current"))

    for project in list_projects(root):
        path = root / "videos" / project["slug"]
        migrated = False
        if project.get("schema_version", 0) < 2:
            old_stage = project.get("stage", "concept")
            _migrate_v02_video_layout(root, path)
            mapping = {
                "concept": "direction", "research": "direction", "outline": "story", "script": "script",
                "preproduction": "production", "build": "production", "capture": "production",
                "edit": "edit", "review": "edit", "package": "release", "scheduled": "release",
                "published": "learn", "archived": "learn",
            }
            project["stage"] = mapping.get(old_stage, "direction")
            project["schema_version"] = 2
            project["state"] = "completed" if old_stage == "archived" else "paused"
            project["approvals"] = {}
            project.setdefault("history", []).append({"at": utc_now(), "event": "migrated", "from_schema": 1, "to_schema": 2, "approvals_invalidated": True})
            migrated = True
        if "state" not in project:
            project["state"] = "active"
            migrated = True
        if migrated:
            save_project(path, project)
    active_count = len(active_projects(root))
    results.append(CheckResult(active_count <= 1, "single active video", f"{active_count} active video(s)"))
    return results


def deterministic_idea_score(values: dict[str, int]) -> float:
    weights = {
        "clarity": 1.0,
        "hook_strength": 1.5,
        "visual_potential": 1.25,
        "feasibility": 1.5,
        "originality": 1.25,
        "series_potential": 1.0,
    }
    total_weight = sum(weights.values())
    score = sum(max(1, min(5, int(values[key]))) * weight for key, weight in weights.items()) / total_weight
    return round(score * 20, 1)


def add_idea(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    fields = ["clarity", "hook_strength", "visual_potential", "feasibility", "originality", "series_potential"]
    for field in fields:
        value = int(payload[field])
        if not 1 <= value <= 5:
            raise StudioError(f"{field} must be between 1 and 5.")
        payload[field] = value
    payload["score"] = deterministic_idea_score(payload)
    payload["created_at"] = utc_now()
    payload["slug"] = slugify(payload["title"])
    payload.setdefault("status", "backlog")
    payload.setdefault("notes", "")
    fieldnames = ["created_at", "slug", "title", "premise", "hook", "format", "scope", *fields, "score", "status", "notes"]
    append_csv(root / "data" / "ideas.csv", fieldnames, payload)
    return payload


def business_entry(root: Path, payload: dict[str, Any]) -> None:
    if payload["type"] not in {"expense", "revenue"}:
        raise StudioError("Business entry type must be expense or revenue.")
    try:
        amount = float(payload["amount"])
    except (TypeError, ValueError) as exc:
        raise StudioError("Amount must be numeric.") from exc
    if amount < 0:
        raise StudioError("Amount must be positive; use type to distinguish expense and revenue.")
    payload["amount"] = f"{amount:.2f}"
    fields = ["date", "type", "amount", "currency", "category", "video", "counterparty", "note"]
    append_csv(root / "data" / "business" / "ledger.csv", fields, payload)


def business_summary(root: Path) -> dict[str, dict[str, float]]:
    summary: dict[str, dict[str, float]] = {}
    for row in read_csv_rows(root / "data" / "business" / "ledger.csv"):
        currency = (row.get("currency") or "UNKNOWN").upper()
        bucket = summary.setdefault(currency, {"revenue": 0.0, "expense": 0.0, "profit": 0.0})
        try:
            amount = float(row.get("amount") or 0)
        except ValueError:
            continue
        entry_type = row.get("type")
        if entry_type in {"revenue", "expense"}:
            bucket[entry_type] += amount
    for bucket in summary.values():
        bucket["profit"] = bucket["revenue"] - bucket["expense"]
    return summary


def add_deal(root: Path, payload: dict[str, Any]) -> None:
    fields = ["created_at", "brand", "contact", "status", "value", "currency", "deliverables", "next_action", "next_action_date", "notes"]
    payload["created_at"] = utc_now()
    append_csv(root / "data" / "business" / "deals.csv", fields, payload)



def add_time_entry(root: Path, payload: dict[str, Any]) -> None:
    try:
        hours = float(payload["hours"])
    except (TypeError, ValueError) as exc:
        raise StudioError("Hours must be numeric.") from exc
    if hours <= 0 or hours > 24:
        raise StudioError("Hours must be greater than 0 and no more than 24 per entry.")
    payload["hours"] = f"{hours:.2f}"
    fields = ["date", "hours", "area", "video", "task", "tool", "notes"]
    append_csv(root / "data" / "business" / "time_log.csv", fields, payload)


def time_summary(root: Path) -> dict[str, Any]:
    rows = read_csv_rows(root / "data" / "business" / "time_log.csv")
    total = 0.0
    by_area: dict[str, float] = {}
    by_video: dict[str, float] = {}
    for row in rows:
        try:
            hours = float(row.get("hours") or 0)
        except ValueError:
            continue
        total += hours
        area = row.get("area") or "uncategorised"
        video = row.get("video") or "channel/general"
        by_area[area] = by_area.get(area, 0.0) + hours
        by_video[video] = by_video.get(video, 0.0) + hours
    return {"total_hours": round(total, 2), "by_area": by_area, "by_video": by_video}


def add_calendar_item(root: Path, payload: dict[str, Any]) -> None:
    payload["created_at"] = utc_now()
    fields = ["created_at", "video_slug", "working_title", "format", "pillar", "status", "target_publish", "priority", "dependency", "notes"]
    append_csv(root / "data" / "channel" / "content_calendar.csv", fields, payload)


def add_social_item(root: Path, payload: dict[str, Any]) -> None:
    payload["created_at"] = utc_now()
    fields = ["created_at", "platform", "video_slug", "target_publish", "status", "copy_file", "asset", "approved_by", "notes"]
    append_csv(root / "data" / "channel" / "social_queue.csv", fields, payload)


def add_library_asset(root: Path, payload: dict[str, Any]) -> None:
    payload["created_at"] = utc_now()
    if not payload.get("asset_id"):
        payload["asset_id"] = slugify(payload["name"])
    fields = ["created_at", "asset_id", "name", "type", "path_or_url", "owner", "licence", "version", "reuse_status", "used_in", "notes"]
    rows = read_csv_rows(root / "data" / "library" / "assets.csv")
    if any(row.get("asset_id") == payload["asset_id"] for row in rows):
        raise StudioError(f"Asset ID already exists: {payload['asset_id']}")
    append_csv(root / "data" / "library" / "assets.csv", fields, payload)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_publish(root: Path, slug: str) -> Path:
    video_dir, project = load_project(root, slug)
    approval = project.get("approvals", {}).get("publish_lock")
    if not approval:
        raise StudioError("Cannot package before the showrunner approves publication.")
    package_checks = evaluate_stage(root, slug, "release", include_approval=False)
    blockers = [item for item in package_checks if not item.ok]
    if blockers:
        message = "; ".join(f"{item.label}: {item.detail}" for item in blockers)
        raise StudioError(f"Cannot package incomplete release material: {message}")
    release_dir = video_dir / ".studio" / "internal" / "release"
    required = [
        release_dir / "metadata.json",
        release_dir / "description.md",
        release_dir / "pinned-comment.md",
        release_dir / "thumbnail-brief.md",
        release_dir / "promise-alignment.md",
    ]
    missing = [str(path.relative_to(video_dir)) for path in required if not path.is_file()]
    if missing:
        raise StudioError(f"Cannot package; missing: {', '.join(missing)}")
    export_dir = root / "exports" / slug / f"publish-{date.today().isoformat()}"
    if export_dir.exists():
        shutil.rmtree(export_dir)
    export_dir.mkdir(parents=True)
    for source in required:
        shutil.copy2(source, export_dir / source.name)
    optional = [
        release_dir / "social-pack.md",
        release_dir / "thumbnail.png",
        video_dir / ".studio" / "internal" / "edit" / "captions-en-GB.srt",
        video_dir / ".studio" / "internal" / "edit" / "captions-en-GB.vtt",
        video_dir / "06-release" / "release-plan.md",
    ]
    for source in optional:
        if source.is_file():
            shutil.copy2(source, export_dir / source.name)
    manifest = {
        "slug": slug,
        "title": project["title"],
        "created_at": utc_now(),
        "currency": "BRL",
        "language": "en-GB",
        "files": [],
    }
    for file in sorted(export_dir.iterdir()):
        if file.is_file():
            manifest["files"].append({"name": file.name, "sha256": sha256_file(file), "bytes": file.stat().st_size})
    write_json(export_dir / "manifest.json", manifest)
    return export_dir


def validate_repository(root: Path) -> list[CheckResult]:
    checks: list[CheckResult] = []
    for rel in ["AGENTS.md", "studio/studio.json", "studio/stages.json", "studio/writing-doctrine.json", "templates/video", ".agents/skills", ".codex/config.toml", "opencode.json"]:
        path = root / rel
        checks.append(CheckResult(path.exists(), rel, "present" if path.exists() else "missing"))
    try:
        stages = load_stages(root)
        names = [stage["name"] for stage in stages]
        checks.append(CheckResult(len(names) == len(set(names)), "stage names unique", ", ".join(names)))
    except StudioError as exc:
        checks.append(CheckResult(False, "stage configuration", str(exc)))
    try:
        from .story import validate_writing_doctrine
        checks.extend(CheckResult(item.ok, item.label, item.detail, item.severity) for item in validate_writing_doctrine(root))
    except (OSError, ValueError) as exc:
        checks.append(CheckResult(False, "writing doctrine", str(exc)))
    for project in list_projects(root):
        slug = project.get("slug", "unknown")
        try:
            results = evaluate_stage(root, slug)
            failed = [r for r in results if not r.ok]
            checks.append(CheckResult(not failed, f"video:{slug}:{project.get('stage')}", "ready" if not failed else f"{len(failed)} blocker(s)"))
        except StudioError as exc:
            checks.append(CheckResult(False, f"video:{slug}", str(exc)))
    return checks


def table(rows: Iterable[Iterable[Any]], headers: Iterable[str]) -> str:
    rows_list = [[str(value) for value in row] for row in rows]
    headers_list = [str(value) for value in headers]
    widths = [len(header) for header in headers_list]
    for row in rows_list:
        for index, value in enumerate(row):
            if index >= len(widths):
                widths.append(len(value))
            else:
                widths[index] = max(widths[index], len(value))
    def format_row(row: list[str]) -> str:
        return "  ".join(value.ljust(widths[index]) for index, value in enumerate(row))
    output = [format_row(headers_list), format_row(["-" * width for width in widths])]
    output.extend(format_row(row) for row in rows_list)
    return "\n".join(output)
