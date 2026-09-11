"""Deterministic media organization for NLE handoff.

This module never moves, copies, renames, or deletes source media. It converts the
canonical ingest registry into a small local manifest that tells an NLE integration
which files exist and which logical Premiere bins they belong to.
"""
from __future__ import annotations

import csv
import os
from pathlib import Path

from . import core as C

VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".mxf", ".mkv", ".webm", ".avi", ".m4v", ".mts", ".m2ts",
}
VIDEO_KINDS = {"video-source", "vod", "video", "master-source", "source-video"}
MANIFEST_REL = os.path.join(".studio", "internal", "assembly", "edit-media-manifest.json")


def _assets_path(vdir: str) -> str:
    return os.path.join(vdir, ".studio", "internal", "ingest", "assets.csv")


def _looks_like_video(row: dict, full_path: str) -> bool:
    kind = str(row.get("kind") or "").strip().lower()
    ext = Path(full_path).suffix.lower()
    return kind in VIDEO_KINDS or ext in VIDEO_EXTENSIONS


def _bin_for(row: dict) -> str:
    asset_id = str(row.get("asset_id") or "").lower()
    rel = str(row.get("path") or "").replace("\\", "/").lower()
    if asset_id.startswith("youtube-") or "/youtube/" in rel:
        return "Sources/YouTube Masters"
    if asset_id.startswith("twitch-") or "/twitch/" in rel:
        return "Sources/Twitch"
    return "Sources/Other"


def build_manifest(root: str, slug: str) -> dict:
    """Generate the edit-media manifest without touching source files."""
    vdir, _project = C.load_project(root, slug)
    source = _assets_path(vdir)
    rows: list[dict] = []
    if os.path.isfile(source):
        with open(source, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))

    media: list[dict] = []
    missing: list[dict] = []
    for row in rows:
        rel = str(row.get("path") or "").strip()
        if not rel:
            continue
        full = rel if os.path.isabs(rel) else os.path.abspath(os.path.join(vdir, rel))
        if not _looks_like_video(row, full):
            continue
        item = {
            "asset_id": str(row.get("asset_id") or ""),
            "kind": str(row.get("kind") or ""),
            "source_path": rel,
            "resolved_path": full,
            "bin": _bin_for(row),
            "sha256": str(row.get("sha256") or ""),
            "rights_status": str(row.get("rights_status") or ""),
            "exists": os.path.isfile(full),
        }
        (media if item["exists"] else missing).append(item)

    media.sort(key=lambda r: (r["bin"], r["asset_id"], r["source_path"]))
    missing.sort(key=lambda r: (r["bin"], r["asset_id"], r["source_path"]))
    bins: dict[str, int] = {}
    for item in media:
        bins[item["bin"]] = bins.get(item["bin"], 0) + 1

    manifest = {
        "schema_version": 1,
        "generated_at": C.utc_now(),
        "production": slug,
        "policy": {
            "source_media_mutated": False,
            "copy_media": False,
            "organization": "logical-premiere-bins",
        },
        "summary": {
            "registered_assets": len(rows),
            "media_ready": len(media),
            "media_missing": len(missing),
            "bins": bins,
        },
        "media": media,
        "missing": missing,
    }
    C.write_json(os.path.join(vdir, MANIFEST_REL), manifest)
    return manifest


def read_manifest(root: str, slug: str) -> dict | None:
    vdir, _ = C.load_project(root, slug)
    data = C.read_json(os.path.join(vdir, MANIFEST_REL), None)
    return data if isinstance(data, dict) else None
