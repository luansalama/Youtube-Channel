"""Pipeline helpers: ingest/analysis/graphics/composition/metadata/publish/learn."""
from __future__ import annotations
import csv
import hashlib
import json
import os

from .core import StudioError, load_project, save_project, sha256_file
from .security import sanitize_record


# ---- ingest ----

def register_asset(root: str, slug: str, asset_id: str, kind: str, path: str,
                   rights_status: str = "sem_autorizacao_confirmada") -> dict:
    from .core import prod_path
    vdir, _ = load_project(root, slug)
    full = path if os.path.isabs(path) else os.path.join(vdir, path)
    digest = sha256_file(full) if os.path.isfile(full) else "missing-file"
    csv_path = os.path.join(vdir, ".studio/internal/ingest/assets.csv")
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    exists = os.path.isfile(csv_path)
    rows = []
    if exists:
        with open(csv_path, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
    rows = [r for r in rows if r.get("asset_id") != asset_id]
    rows.append({"asset_id": asset_id, "kind": kind, "path": path,
                 "sha256": digest, "rights_status": rights_status})
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["asset_id", "kind", "path", "sha256", "rights_status"])
        w.writeheader()
        w.writerows(rows)
    return {"asset_id": asset_id, "sha256": digest}


def import_untrusted_rows(rows: list[dict]) -> list[dict]:
    """Mark chat/transcript/comment rows as DATA + quarantine injections."""
    return [sanitize_record(r) for r in rows]


# ---- analysis / highlights ----

def score_moments(signals: list[dict], w_chat=0.4, w_audio=0.3, w_game=0.3) -> list[dict]:
    """Deterministic weighted score in [0,1]. Pure function, fully testable."""
    out = []
    for s in signals:
        score = (float(s.get("chat_rate", 0)) * w_chat + float(s.get("audio_peak", 0)) * w_audio
                 + float(s.get("game_event", 0)) * w_game)
        out.append({**s, "score": round(max(0.0, min(1.0, score)), 4)})
    return sorted(out, key=lambda r: r["score"], reverse=True)


# ---- graphics ----

GRAPHICS_KINDS = ("lower-third", "title-card", "highlight-tag", "subscribe-cta", "censor-blur")


def validate_overlays(path: str, cutlist_path: str = "", fps: float = 30.0) -> dict:
    from .timecode import parse_timecode
    errors: list[str] = []
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for i, r in enumerate(rows, 2):
        if r.get("kind") not in GRAPHICS_KINDS:
            errors.append(f"line {i}: unknown kind {r.get('kind')!r}")
        try:
            s = parse_timecode(r.get("t_start", ""), fps)
            e = parse_timecode(r.get("t_end", ""), fps)
            if e <= s:
                errors.append(f"line {i}: t_end <= t_start")
        except ValueError as exc:
            errors.append(f"line {i}: {exc}")
        if not (r.get("text") or "").strip() and r.get("kind") != "censor-blur":
            errors.append(f"line {i}: empty text")
    return {"ok": not errors, "errors": errors, "overlays": len(rows)}


# ---- composition / master ----

def register_master(root: str, slug: str, master_file: str, duration_seconds: float,
                    fps: float = 30.0) -> dict:
    from .core import prod_path
    vdir, project = load_project(root, slug)
    full = master_file if os.path.isabs(master_file) else os.path.join(vdir, master_file)
    if not os.path.isfile(full):
        raise StudioError(f"master not found: {master_file}")
    if os.path.getsize(full) < 1024:
        raise StudioError("master file too small (<1KB)")
    rec = {"master_file": master_file, "duration_seconds": float(duration_seconds),
           "fps": float(fps), "sha256": sha256_file(full)}
    os.makedirs(os.path.join(vdir, ".studio/internal/composition"), exist_ok=True)
    with open(os.path.join(vdir, ".studio/internal/composition/master.json"), "w", encoding="utf-8") as fh:
        json.dump(rec, fh, ensure_ascii=False, indent=2)
    project.setdefault("media", {})["master_file"] = master_file
    save_project(vdir, project)
    return rec


# ---- metadata ----

def write_metadata(root: str, slug: str, title: str, description: str, tags: list[str],
                   category_id: str = "20", language: str = "pt-BR") -> dict:
    from .core import prod_path
    if len(title.strip()) < 5:
        raise StudioError("title too short")
    if len(description.strip()) < 50:
        raise StudioError("description too short (<50 chars)")
    if not tags:
        raise StudioError("at least one tag required")
    vdir, _ = load_project(root, slug)
    meta = {"title": title, "description": description, "tags": tags,
            "category_id": category_id, "default_language": language,
            "made_for_kids": False, "contains_synthetic_media": False}
    os.makedirs(os.path.join(vdir, ".studio/internal/release"), exist_ok=True)
    with open(os.path.join(vdir, ".studio/internal/release/metadata.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2)
    return meta


# ---- publish (dry-run default, real blocked) ----

def publish_dry_run(root: str, slug: str) -> dict:
    from . import core as _core
    from . import rights as _rights
    vdir, project = load_project(root, slug)
    checks = _core.evaluate_stage(root, slug, "publish", include_approval=True)
    ok_rights, rights_msg = _rights.rights_gate(project, vdir)
    blockers = [f"{c.label}: {c.detail}" for c in checks if not c.ok]
    if not ok_rights:
        blockers.append("rights: " + rights_msg)
    pkg = None
    if not blockers:
        try:
            pkg = _core.package_publish(root, slug)
        except StudioError as exc:
            blockers.append(str(exc))
    return {"mode": "dry-run", "would_publish": not blockers, "blockers": blockers,
            "package": (pkg or {}).get("outdir", "")}


def publish_execute(root: str, slug: str) -> dict:
    """Real upload stays blocked until gates pass AND credentials exist.

    Even with gates passing, without configured YouTube credentials this
    returns blocked=False-executed rather than faking an upload.
    """
    dry = publish_dry_run(root, slug)
    if dry["blockers"]:
        raise StudioError("publish blocked: " + "; ".join(dry["blockers"][:5]))
    creds = os.environ.get("YOUTUBE_CLIENT_SECRETS", "")
    if not creds or not os.path.isfile(creds):
        return {"executed": False, "reason": "youtube credentials not configured; package ready at " + dry["package"]}
    return {"executed": False,
            "reason": "uploader not wired in this build; use package + YouTube Studio (see docs/PUBLISH.md)"}


# ---- learn ----

def append_lesson(root: str, slug: str, lesson: str) -> None:
    from .core import prod_path
    vdir, _ = load_project(root, slug)
    p = os.path.join(vdir, "12-learn/lessons.md")
    with open(p, "a", encoding="utf-8") as fh:
        fh.write(f"\n- {lesson.strip()}\n")
