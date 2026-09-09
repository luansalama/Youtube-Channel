"""Deterministic engine: productions, gates/locks, fingerprints, validation, packaging.

Adapted from the Youtube-Channel mould architecture (mcstudio/core.py):
single active production, proposal-gated writes, sha256 evidence
fingerprints, gate approvals, deterministic validators, checksummed
packages, quarantine recovery. Rewritten for the cuts domain —
no Minecraft content copied.
"""
from __future__ import annotations
import csv
import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone

from . import timecode as _tc

SCHEMA_VERSION = 2
PLACEHOLDERS = ("TODO", "TBD", "{{", "<replace", "[write here]", "[fill", "lorem ipsum")
PROD_DIRS = ("productions", "videos")  # primary + legacy alias


class StudioError(RuntimeError):
    pass


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    label: str
    detail: str = ""
    severity: str = "error"


# ---------- small IO ----------

def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slugify(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")
    return s or "untitled"


def find_root(start: str = ".") -> str:
    cur = os.path.abspath(start)
    while True:
        if os.path.isfile(os.path.join(cur, "pyproject.toml")) and os.path.isdir(os.path.join(cur, "studio")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            raise StudioError("studio root not found (pyproject.toml + studio/ missing)")
        cur = parent


def read_json(path: str, default=None):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------- productions ----------

def _prods_dir(root: str) -> str:
    for d in PROD_DIRS:
        p = os.path.join(root, d)
        if os.path.isdir(p):
            return p
    p = os.path.join(root, "productions")
    os.makedirs(p, exist_ok=True)
    return p


def prod_path(root: str, slug: str) -> str:
    for d in PROD_DIRS:
        p = os.path.join(root, d, slug)
        if os.path.isdir(p):
            return p
    return os.path.join(_prods_dir(root), slug)


def load_project(root: str, slug: str) -> tuple[str, dict]:
    vdir = prod_path(root, slug)
    pj = os.path.join(vdir, "project.json")
    if not os.path.isfile(pj):
        raise StudioError(f"production not found: {slug}")
    return vdir, read_json(pj)


def save_project(vdir: str, project: dict) -> None:
    project["updated_at"] = utc_now()
    write_json(os.path.join(vdir, "project.json"), project)


def list_productions(root: str) -> list[dict]:
    out = []
    for d in PROD_DIRS:
        base = os.path.join(root, d)
        if not os.path.isdir(base):
            continue
        for slug in sorted(os.listdir(base)):
            pj = os.path.join(base, slug, "project.json")
            if os.path.isfile(pj):
                try:
                    out.append(read_json(pj))
                except Exception:
                    continue
    return sorted(out, key=lambda p: p.get("slug", ""))


def active_productions(root: str) -> list[dict]:
    return [p for p in list_productions(root) if p.get("state") == "active"]


def active_production(root: str):
    acts = active_productions(root)
    return acts[0] if acts else None


_HUMAN_DOCS = [
    "01-config/config.md", "02-ingest/ingest.md", "03-analysis/analysis.md",
    "04-sync/sync.md", "05-highlights/highlights.md", "06-cutlist/cutlist.md",
    "07-assembly/assembly.md", "08-graphics/graphics.md", "09-composition/composition.md",
    "10-metadata/metadata.md", "11-publish/publish.md", "12-learn/lessons.md",
]


def create_production(root: str, title: str, slug: str | None = None, source_url: str = "") -> dict:
    slug = slugify(slug or title)
    if os.path.exists(prod_path(root, slug)):
        raise StudioError(f"production exists: {slug}")
    if active_production(root) is not None:
        raise StudioError("only one production may be active — pause/abandon the current one first")
    tpl = os.path.join(root, "templates", "production")
    vdir = os.path.join(_prods_dir(root), slug)
    if os.path.isdir(tpl):
        shutil.copytree(tpl, vdir)
    else:
        os.makedirs(vdir, exist_ok=True)
    for rel in _HUMAN_DOCS:
        p = os.path.join(vdir, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        if not os.path.exists(p):
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(f"# {title}\n\nTODO: fill {rel}\n")
    now = utc_now()
    project = {
        "schema_version": SCHEMA_VERSION, "slug": slug, "title": title,
        "stage": "config", "state": "active", "created_at": now, "updated_at": now,
        "source_url": source_url, "approvals": {}, "rights": {},
        "media": {"master_file": "", "thumbnail_file": ""},
        "sync": {"offset_seconds": 0.0, "method": "", "confidence": 0.0},
        "history": [{"at": now, "event": "created", "by": "showrunner"}],
    }
    write_json(os.path.join(vdir, "project.json"), project)
    return project


def _record(vdir: str, project: dict, event: str, **kw) -> None:
    project.setdefault("history", []).append({"at": utc_now(), "event": event, **kw})
    save_project(vdir, project)


def pause_production(root, slug, by="showrunner", reason=""):
    vdir, p = load_project(root, slug)
    p["state"] = "paused"
    _record(vdir, p, "paused", by=by, reason=reason)


def resume_production(root, slug, by="showrunner"):
    vdir, p = load_project(root, slug)
    if p.get("state") == "active":
        return
    if active_production(root) is not None and p.get("state") != "active":
        raise StudioError("another production is already active")
    p["state"] = "active"
    _record(vdir, p, "resumed", by=by)


def abandon_production(root, slug, by="showrunner", reason=""):
    vdir, p = load_project(root, slug)
    p["state"] = "abandoned"
    _record(vdir, p, "abandoned", by=by, reason=reason)


# ---------- stages / gates ----------

def load_stages(root: str) -> list[dict]:
    data = read_json(os.path.join(root, "studio", "stages.json"), {})
    stages = data.get("stages", []) if isinstance(data, dict) else []
    if not stages:
        raise StudioError("studio/stages.json has no stages")
    return stages


def get_stage(root: str, stage_id: str) -> dict:
    for s in load_stages(root):
        if s["id"] == stage_id:
            return s
    raise StudioError(f"unknown stage: {stage_id}")


def stage_index(root: str, stage_id: str) -> int:
    ids = [s["id"] for s in load_stages(root)]
    return ids.index(stage_id)


def stage_evidence_hashes(vdir: str, stage: dict) -> dict:
    hashes = {}
    for req in stage.get("requires", []):
        rel = req.get("path", "")
        p = os.path.join(vdir, rel)
        if rel and os.path.isfile(p):
            hashes[rel] = sha256_file(p)
    return hashes


def _approval_integrity(vdir: str, project: dict, gate: str) -> CheckResult:
    rec = (project.get("approvals") or {}).get(gate)
    if not rec:
        return CheckResult(False, f"gate {gate}", "missing approval")
    drift = []
    for rel, old in (rec.get("evidence") or {}).items():
        p = os.path.join(vdir, rel)
        if not os.path.isfile(p):
            drift.append(f"{rel} missing")
        elif sha256_file(p) != old:
            drift.append(f"{rel} changed")
    if drift:
        return CheckResult(False, f"gate {gate}", "approved evidence changed: " + "; ".join(drift))
    return CheckResult(True, f"gate {gate}", "fingerprints match")


# ---------- validators ----------

def _check_text(vdir, req) -> CheckResult:
    rel = req["path"]
    p = os.path.join(vdir, rel)
    label = f"text {rel}"
    if not os.path.isfile(p):
        return CheckResult(False, label, "missing file")
    t = open(p, encoding="utf-8", errors="replace").read()
    if len(t.strip()) < int(req.get("min_chars", 100)):
        return CheckResult(False, label, f"too short ({len(t.strip())} chars)")
    hits = [w for w in PLACEHOLDERS if w.lower() in t.lower()]
    if hits:
        return CheckResult(False, label, f"placeholder tokens: {hits[:3]}")
    return CheckResult(True, label, f"{len(t.strip())} chars")


def _check_exists(vdir, req) -> CheckResult:
    rel = req["path"]
    ok = os.path.isfile(os.path.join(vdir, rel))
    return CheckResult(ok, f"exists {rel}", "" if ok else "missing file")


def _check_binary(vdir, req) -> CheckResult:
    rel = req["path"]
    p = os.path.join(vdir, rel)
    if not os.path.isfile(p):
        return CheckResult(False, f"binary {rel}", "missing file")
    if os.path.getsize(p) < int(req.get("min_bytes", 1024)):
        return CheckResult(False, f"binary {rel}", "file too small")
    return CheckResult(True, f"binary {rel}", f"{os.path.getsize(p)} bytes")


def _check_csv(vdir, req) -> CheckResult:
    rel = req["path"]
    p = os.path.join(vdir, rel)
    label = f"csv {rel}"
    if not os.path.isfile(p):
        return CheckResult(False, label, "missing file")
    try:
        with open(p, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
            cols = rows and list(rows[0].keys()) or []
    except Exception as exc:
        return CheckResult(False, label, f"unreadable: {exc}")
    if len(rows) < int(req.get("min_rows", 1)):
        return CheckResult(False, label, f"only {len(rows)} rows")
    missing = [c for c in req.get("required_columns", []) if c not in (cols or [])]
    if missing:
        return CheckResult(False, label, f"missing columns: {missing}")
    return CheckResult(True, label, f"{len(rows)} rows")


def _check_json(vdir, req) -> CheckResult:
    rel = req["path"]
    p = os.path.join(vdir, rel)
    label = f"json {rel}"
    if not os.path.isfile(p):
        return CheckResult(False, label, "missing file")
    try:
        data = json.load(open(p, encoding="utf-8"))
    except Exception as exc:
        return CheckResult(False, label, f"invalid JSON: {exc}")
    keys = req.get("required_keys", [])
    missing = [k for k in keys if not (isinstance(data, dict) and data.get(k))]
    if missing:
        return CheckResult(False, label, f"missing keys: {missing}")
    blob = json.dumps(data, ensure_ascii=False).lower()
    hits = [w for w in PLACEHOLDERS if w.lower() in blob]
    if hits:
        return CheckResult(False, label, f"placeholder tokens: {hits[:3]}")
    return CheckResult(True, label, "ok")


_CHECKERS = {"text": _check_text, "exists": _check_exists, "binary": _check_binary,
             "csv": _check_csv, "json": _check_json}


def _stage_requirements(root: str, stage_id: str) -> list[dict]:
    """Default deterministic requirements per stage (overridable in stages.json)."""
    R = {
        "config": [
            {"kind": "text", "path": "01-config/config.md", "min_chars": 200},
            {"kind": "json", "path": ".studio/internal/config/sources.json",
             "required_keys": ["stream_url", "rights_status"]},
        ],
        "ingest": [
            {"kind": "csv", "path": ".studio/internal/ingest/assets.csv",
             "min_rows": 1, "required_columns": ["asset_id", "kind", "path", "sha256", "rights_status"]},
            {"kind": "text", "path": "02-ingest/ingest.md", "min_chars": 200},
        ],
        "analysis": [
            {"kind": "csv", "path": ".studio/internal/analysis/moments.csv",
             "min_rows": 1, "required_columns": ["moment_id", "t_start", "t_end", "score", "rationale"]},
        ],
        "sync": [
            {"kind": "json", "path": ".studio/internal/sync/sync-report.json",
             "required_keys": ["offset_seconds", "method", "confidence"]},
        ],
        "highlights": [
            {"kind": "csv", "path": ".studio/internal/highlights/ranking.csv",
             "min_rows": 1, "required_columns": ["moment_id", "rank", "score"]},
        ],
        "cutlist": [
            {"kind": "text", "path": "06-cutlist/cutlist.md", "min_chars": 200},
            {"kind": "csv", "path": ".studio/internal/cutlist/cutlist.csv",
             "min_rows": 1, "required_columns": ["cut_id", "t_start", "t_end", "source", "rights_status"]},
        ],
        "assembly": [
            {"kind": "json", "path": ".studio/internal/assembly/timeline.json",
             "required_keys": ["fps", "events"]},
        ],
        "graphics": [
            {"kind": "text", "path": "08-graphics/graphics.md", "min_chars": 200},
            {"kind": "csv", "path": ".studio/internal/graphics/overlays.csv",
             "min_rows": 1, "required_columns": ["overlay_id", "t_start", "t_end", "kind", "text"]},
        ],
        "composition": [
            {"kind": "json", "path": ".studio/internal/composition/master.json",
             "required_keys": ["master_file", "duration_seconds", "fps"]},
        ],
        "metadata": [
            {"kind": "json", "path": ".studio/internal/release/metadata.json",
             "required_keys": ["title", "description", "tags", "category_id"]},
            {"kind": "text", "path": "10-metadata/metadata.md", "min_chars": 120},
        ],
        "publish": [
            {"kind": "text", "path": "11-publish/publish.md", "min_chars": 120},
        ],
        "learn": [
            {"kind": "text", "path": "12-learn/lessons.md", "min_chars": 120},
        ],
    }
    return R.get(stage_id, [])


def _extra_validators(root: str, vdir: str, project: dict, stage_id: str) -> list[CheckResult]:
    from . import cutlist as _cl, rights as _rights, sync as _sync
    out: list[CheckResult] = []
    if stage_id in ("cutlist", "assembly", "graphics", "composition", "metadata", "publish"):
        p = os.path.join(vdir, ".studio/internal/cutlist/cutlist.csv")
        if os.path.isfile(p):
            try:
                res = _cl.validate_cutlist_file(p)
                out.append(CheckResult(res["ok"], "cutlist validity",
                                       "; ".join(res["errors"]) if res["errors"] else f"{res['cuts']} cuts ok"))
            except Exception as exc:
                out.append(CheckResult(False, "cutlist validity", str(exc)))
    if stage_id in ("sync", "highlights", "cutlist", "assembly", "publish"):
        p = os.path.join(vdir, ".studio/internal/sync/sync-report.json")
        if os.path.isfile(p):
            try:
                rep = json.load(open(p, encoding="utf-8"))
                ok, msg = _sync.validate_sync_report(rep)
                out.append(CheckResult(ok, "sync report", msg))
            except Exception as exc:
                out.append(CheckResult(False, "sync report", str(exc)))
    if stage_id in ("metadata", "publish"):
        ok, msg = _rights.rights_gate(project, vdir)
        out.append(CheckResult(ok, "rights clearance", msg))
    if stage_id == "composition":
        master = ((project.get("media") or {}).get("master_file")) or ""
        mp = os.path.join(vdir, master) if master and not os.path.isabs(master) else master
        if not master:
            out.append(CheckResult(False, "master media", "no master_file registered"))
        elif not os.path.isfile(mp):
            out.append(CheckResult(False, "master media", f"missing: {master}"))
        elif os.path.getsize(mp) < 1024:
            out.append(CheckResult(False, "master media", "master too small"))
        else:
            out.append(CheckResult(True, "master media", f"{os.path.getsize(mp)} bytes"))
    return out


def evaluate_stage(root: str, slug: str, stage_id: str | None = None,
                   include_approval: bool = True, scope: str = "completion") -> list[CheckResult]:
    vdir, project = load_project(root, slug)
    stages = load_stages(root)
    stage = get_stage(root, stage_id or project.get("stage", "config"))
    results: list[CheckResult] = []
    reqs = stage.get("requires") or _stage_requirements(root, stage["id"])
    for req in reqs:
        if scope == "proposal" and req.get("proposal_required") is False:
            continue
        fn = _CHECKERS.get(req.get("kind", "text"), _check_text)
        results.append(fn(vdir, req))
    results.extend(_extra_validators(root, vdir, project, stage["id"]))
    if include_approval:
        idx = stage_index(root, stage["id"])
        for prev in stages[:idx + 1]:
            gate = prev.get("gate")
            if gate:
                if gate in (project.get("approvals") or {}):
                    results.append(_approval_integrity(vdir, project, gate))
                elif prev["id"] == stage["id"]:
                    results.append(CheckResult(False, f"gate {gate}", "not yet approved"))
                else:
                    results.append(CheckResult(False, f"gate {gate}", f"upstream {prev['id']} not approved"))
    return results


def gate_status(root: str, slug: str) -> list[dict]:
    vdir, project = load_project(root, slug)
    stages = load_stages(root)
    out = []
    for s in stages:
        gate = s.get("gate")
        if not gate:
            continue
        approved = gate in (project.get("approvals") or {})
        detail = ""
        if approved:
            r = _approval_integrity(vdir, project, gate)
            detail = r.detail
            approved = r.ok
        out.append({"stage": s["id"], "gate": gate, "approved": approved, "detail": detail})
    return out


def approve_gate(root: str, slug: str, gate: str, by: str = "showrunner", note: str = "") -> dict:
    vdir, project = load_project(root, slug)
    stages = load_stages(root)
    stage = next((s for s in stages if s.get("gate") == gate), None)
    if not stage:
        raise StudioError(f"unknown gate: {gate}")
    checks = evaluate_stage(root, slug, stage["id"], include_approval=False)
    failures = [c for c in checks if not c.ok]
    if failures:
        raise StudioError("cannot approve %s: %s" % (gate, "; ".join(f"{c.label}: {c.detail}" for c in failures[:4])))
    project.setdefault("approvals", {})[gate] = {
        "by": by, "at": utc_now(), "note": note,
        "evidence": stage_evidence_hashes(vdir, {**stage, "requires": stage.get("requires") or _stage_requirements(root, stage["id"])}),
    }
    _record(vdir, project, "approved", gate=gate, by=by)
    return project["approvals"][gate]


def advance_stage(root: str, slug: str, by: str = "showrunner") -> str:
    vdir, project = load_project(root, slug)
    stages = load_stages(root)
    ids = [s["id"] for s in stages]
    cur = project.get("stage", ids[0])
    checks = evaluate_stage(root, slug, cur, include_approval=True)
    failures = [c for c in checks if not c.ok]
    if failures:
        raise StudioError("blocked: " + "; ".join(f"{c.label}: {c.detail}" for c in failures[:5]))
    i = ids.index(cur)
    if i >= len(ids) - 1:
        project["state"] = "completed"
        _record(vdir, project, "completed", by=by)
        return cur
    project["stage"] = ids[i + 1]
    _record(vdir, project, "advanced", by=by, **{"from": cur, "to": ids[i + 1]})
    return project["stage"]


def reopen_stage(root: str, slug: str, to_stage: str, by: str = "showrunner", reason: str = "") -> None:
    if len(reason.strip()) < 10:
        raise StudioError("reopen reason must be >= 10 chars")
    vdir, project = load_project(root, slug)
    stages = load_stages(root)
    ids = [s["id"] for s in stages]
    if to_stage not in ids:
        raise StudioError(f"unknown stage: {to_stage}")
    cut = ids.index(to_stage)
    for s in stages[cut:]:
        project.get("approvals", {}).pop(s.get("gate", ""), None)
    project["stage"] = to_stage
    if project.get("state") == "completed":
        project["state"] = "active"
    _record(vdir, project, "reopened", by=by, to=to_stage, reason=reason)


# ---------- status / maintenance ----------

def workflow_status(root: str, slug: str) -> dict:
    vdir, project = load_project(root, slug)
    checks = evaluate_stage(root, slug, project.get("stage"), include_approval=True)
    return {
        "slug": slug, "title": project.get("title"), "stage": project.get("stage"),
        "state": project.get("state"), "gates": gate_status(root, slug),
        "checks": [{"ok": c.ok, "label": c.label, "detail": c.detail} for c in checks],
        "blocked": any(not c.ok for c in checks),
    }


def continue_workflow(root: str, slug: str | None = None) -> dict:
    slug = slug or (active_production(root) or {}).get("slug", "")
    if not slug:
        return {"action": "none", "detail": "no active production"}
    st = workflow_status(root, slug)
    if st["blocked"]:
        return {"action": "fix", "slug": slug, "stage": st["stage"], "checks": st["checks"]}
    vdir, project = load_project(root, slug)
    stages = load_stages(root)
    cur = next(s for s in stages if s["id"] == st["stage"])
    if cur.get("gate") and cur["gate"] not in (project.get("approvals") or {}):
        return {"action": "awaiting-human-approval", "slug": slug, "gate": cur["gate"]}
    nxt = advance_stage(root, slug, by="engine")
    return {"action": "advanced", "slug": slug, "to": nxt}


def maintain_repository(root: str) -> dict:
    """Quarantine incomplete productions, ensure dirs. Returns report."""
    report = {"quarantined": [], "ok": []}
    for base in PROD_DIRS:
        bdir = os.path.join(root, base)
        if not os.path.isdir(bdir):
            continue
        for slug in os.listdir(bdir):
            vdir = os.path.join(bdir, slug)
            pj = os.path.join(vdir, "project.json")
            if os.path.isdir(vdir) and not os.path.isfile(pj):
                q = os.path.join(root, "exports", "recovery", slug)
                os.makedirs(os.path.dirname(q), exist_ok=True)
                shutil.move(vdir, q)
                report["quarantined"].append(slug)
            elif os.path.isfile(pj):
                report["ok"].append(slug)
    for d in ("exports", "data", "productions", os.path.join("exports", "recovery")):
        os.makedirs(os.path.join(root, d), exist_ok=True)
    return report


def validate_repository(root: str) -> list[CheckResult]:
    out = []
    for f in ("studio/studio.json", "studio/stages.json", "studio/agent-routing.json"):
        out.append(CheckResult(os.path.isfile(os.path.join(root, f)), f"repo file {f}",
                               "" if os.path.isfile(os.path.join(root, f)) else "missing"))
    return out


# ---------- packaging ----------

def package_publish(root: str, slug: str) -> dict:
    from . import rights as _rights
    vdir, project = load_project(root, slug)
    if "publish_lock" not in (project.get("approvals") or {}):
        raise StudioError("publish blocked: publish_lock missing")
    checks = evaluate_stage(root, slug, "publish", include_approval=False)
    failures = [c for c in checks if not c.ok]
    if failures:
        raise StudioError("publish package invalid: " + "; ".join(c.detail for c in failures[:4]))
    ok, msg = _rights.rights_gate(project, vdir)
    if not ok:
        raise StudioError("publish blocked (rights): " + msg)
    master = (project.get("media") or {}).get("master_file", "")
    mp = os.path.join(vdir, master) if master and not os.path.isabs(master) else master
    if not (master and os.path.isfile(mp)):
        raise StudioError("publish blocked: no valid master")
    day = utc_now()[:10]
    outdir = os.path.join(root, "exports", slug, f"publish-{day}")
    os.makedirs(outdir, exist_ok=True)
    required = [".studio/internal/release/metadata.json",
                ".studio/internal/cutlist/cutlist.csv",
                ".studio/internal/composition/master.json"]
    files = []
    for rel in required:
        src = os.path.join(vdir, rel)
        if not os.path.isfile(src):
            raise StudioError(f"publish package missing: {rel}")
        dst = os.path.join(outdir, os.path.basename(rel))
        shutil.copy2(src, dst)
        files.append({"name": os.path.basename(rel), "sha256": sha256_file(dst),
                      "bytes": os.path.getsize(dst)})
    manifest = {"slug": slug, "title": project.get("title"), "created_at": utc_now(),
                "language": "pt-BR", "currency": "BRL", "files": files,
                "master_sha256": sha256_file(mp)}
    write_json(os.path.join(outdir, "manifest.json"), manifest)
    return {"outdir": outdir, "manifest": manifest}
