from __future__ import annotations

import csv
import io
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .core import StudioError, load_project, read_json, save_project, utc_now, write_json

TEXT_EXTENSIONS = {".md", ".txt", ".json", ".csv", ".srt", ".vtt", ".yaml", ".yml"}
UPLOAD_BUCKETS = {
    "master": "assets/master",
    "thumbnail": "assets/thumbnail",
    "capture": "assets/capture",
    "audio": "assets/audio",
    "project": "assets/project-files",
    "reference": "assets/references",
    "youtube": "secrets",
    "analytics": "imports/analytics",
}


def safe_relative_path(value: str) -> Path:
    value = value.replace("\\", "/").strip().lstrip("/")
    path = Path(value)
    if not value or path.is_absolute() or ".." in path.parts:
        raise StudioError("Invalid project-relative path.")
    return path


def safe_video_file(root: Path, slug: str, relative: str, allow_internal: bool = True) -> Path:
    video_dir, _ = load_project(root, slug)
    rel = safe_relative_path(relative)
    if not allow_internal and ".studio" in rel.parts:
        raise StudioError("Internal files are not available in this view.")
    target = (video_dir / rel).resolve()
    try:
        target.relative_to(video_dir.resolve())
    except ValueError as exc:
        raise StudioError("Path is outside the video project.") from exc
    return target


def backup_file(root: Path, slug: str, target: Path) -> Path | None:
    if not target.is_file():
        return None
    video_dir, _ = load_project(root, slug)
    rel = target.relative_to(video_dir)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = video_dir / ".studio" / "backups" / stamp / rel
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target, backup)
    return backup


def read_text_file(root: Path, slug: str, relative: str) -> str:
    target = safe_video_file(root, slug, relative)
    if not target.is_file():
        raise StudioError(f"File not found: {relative}")
    if target.suffix.lower() not in TEXT_EXTENSIONS:
        raise StudioError("This file is not editable as text.")
    return target.read_text(encoding="utf-8", errors="replace")


def write_text_file(root: Path, slug: str, relative: str, content: str, record_event: bool = True) -> Path:
    target = safe_video_file(root, slug, relative)
    if target.suffix.lower() not in TEXT_EXTENSIONS:
        raise StudioError("This file type cannot be saved in the text editor.")
    backup_file(root, slug, target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content.replace("\r\n", "\n"), encoding="utf-8", newline="\n")
    if record_event:
        video_dir, project = load_project(root, slug)
        project.setdefault("history", []).append({"at": utc_now(), "event": "file_saved", "path": relative})
        save_project(video_dir, project)
    return target


def list_project_files(root: Path, slug: str, include_internal: bool = True) -> list[dict[str, Any]]:
    video_dir, _ = load_project(root, slug)
    rows: list[dict[str, Any]] = []
    for path in sorted(video_dir.rglob("*")):
        if not path.is_file() or path.name == "project.json":
            continue
        rel = path.relative_to(video_dir)
        if not include_internal and ".studio" in rel.parts:
            continue
        rows.append({
            "path": rel.as_posix(),
            "bytes": path.stat().st_size,
            "editable": path.suffix.lower() in TEXT_EXTENSIONS,
            "internal": ".studio" in rel.parts,
            "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
        })
    return rows


def upload_bytes(root: Path, slug: str, bucket: str, filename: str, data: bytes) -> Path:
    if bucket not in UPLOAD_BUCKETS:
        raise StudioError("Unknown upload destination.")
    clean_name = Path(filename).name.strip()
    if not clean_name:
        raise StudioError("Uploaded file has no filename.")
    if len(data) == 0:
        raise StudioError("Uploaded file is empty.")
    video_dir, project = load_project(root, slug)
    target_dir = video_dir / UPLOAD_BUCKETS[bucket]
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / clean_name
    backup_file(root, slug, target)
    target.write_bytes(data)
    rel = target.relative_to(video_dir).as_posix()
    media = project.setdefault("media", {})
    if bucket == "master":
        media["master_file"] = rel
    elif bucket == "thumbnail":
        media["thumbnail_file"] = rel
    elif bucket == "youtube" and clean_name.lower().endswith(".json"):
        media["youtube_client_secrets"] = rel
    project.setdefault("history", []).append({"at": utc_now(), "event": "file_uploaded", "bucket": bucket, "path": rel, "bytes": len(data)})
    save_project(video_dir, project)
    return target


def delete_project_file(root: Path, slug: str, relative: str) -> None:
    target = safe_video_file(root, slug, relative)
    if not target.is_file():
        raise StudioError("File not found.")
    if target.name == "project.json":
        raise StudioError("Project metadata cannot be deleted.")
    backup_file(root, slug, target)
    target.unlink()
    video_dir, project = load_project(root, slug)
    media = project.setdefault("media", {})
    for key, value in list(media.items()):
        if value == relative:
            media.pop(key, None)
    project.setdefault("history", []).append({"at": utc_now(), "event": "file_deleted", "path": relative})
    save_project(video_dir, project)


def append_capture_log(root: Path, slug: str, payload: dict[str, str]) -> None:
    video_dir, project = load_project(root, slug)
    path = video_dir / ".studio" / "internal" / "production" / "capture-log.csv"
    fieldnames = ["shot_id", "take", "file", "captured_at", "technical_ok", "performance_ok", "selected", "notes"]
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.is_file() and path.stat().st_size > 0
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        writer.writerow({key: payload.get(key, "") for key in fieldnames})
    project.setdefault("history", []).append({"at": utc_now(), "event": "capture_logged", "shot_id": payload.get("shot_id", ""), "take": payload.get("take", "")})
    save_project(video_dir, project)


def replace_csv_rows(root: Path, slug: str, relative: str, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    target = safe_video_file(root, slug, relative)
    backup_file(root, slug, target)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def open_path(path: Path) -> None:
    path = path.resolve()
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def launch_application(command: str, working_directory: str = "") -> None:
    command = command.strip()
    if not command:
        raise StudioError("No application path or command is configured.")
    cwd = Path(working_directory).expanduser().resolve() if working_directory.strip() else None
    if sys.platform.startswith("win"):
        subprocess.Popen(command, cwd=str(cwd) if cwd else None, shell=True)
    else:
        import shlex
        subprocess.Popen(shlex.split(command), cwd=str(cwd) if cwd else None)




ROOT_EDITABLE_FILES = {
    "channel/channel-strategy.md",
    "channel/brand-voice.md",
    "channel/series-bible.md",
    "business/monthly-review-template.md",
}

def safe_root_text_file(root: Path, relative: str) -> Path:
    rel = safe_relative_path(relative).as_posix()
    if rel not in ROOT_EDITABLE_FILES:
        raise StudioError("This studio file is not editable from the dashboard.")
    return root / rel

def read_root_text(root: Path, relative: str) -> str:
    path = safe_root_text_file(root, relative)
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""

def write_root_text(root: Path, relative: str, content: str) -> Path:
    path = safe_root_text_file(root, relative)
    if path.is_file():
        backup = root / "exports" / "backups" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") / relative
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.replace("\r\n", "\n"), encoding="utf-8", newline="\n")
    return path

def select_local_file(root: Path, slug: str, bucket: str) -> Path | None:
    if bucket not in UPLOAD_BUCKETS:
        raise StudioError("Unknown file purpose.")
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError as exc:
        raise StudioError("The native file picker is unavailable in this Python installation.") from exc
    window = tk.Tk()
    window.withdraw()
    window.attributes("-topmost", True)
    selected = filedialog.askopenfilename(title=f"Select {bucket} file")
    window.destroy()
    if not selected:
        return None
    source = Path(selected).resolve()
    if not source.is_file():
        raise StudioError("Selected file does not exist.")
    video_dir, project = load_project(root, slug)
    media = project.setdefault("media", {})
    if bucket == "master":
        media["master_file"] = str(source)
    elif bucket == "thumbnail":
        media["thumbnail_file"] = str(source)
    elif bucket == "youtube":
        media["youtube_client_secrets"] = str(source)
    else:
        target_dir = video_dir / UPLOAD_BUCKETS[bucket]
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / source.name
        if source != target:
            shutil.copy2(source, target)
        source = target
    project.setdefault("history", []).append({"at": utc_now(), "event": "local_file_selected", "bucket": bucket, "path": str(source)})
    save_project(video_dir, project)
    return source

def media_status(root: Path, slug: str) -> dict[str, Any]:
    video_dir, project = load_project(root, slug)
    result: dict[str, Any] = {}
    for key in ["master_file", "thumbnail_file", "youtube_client_secrets"]:
        rel = project.get("media", {}).get(key, "")
        raw = Path(rel).expanduser() if rel else None
        path = raw if raw and raw.is_absolute() else (video_dir / raw if raw else None)
        result[key] = {
            "relative": rel,
            "exists": bool(path and path.is_file()),
            "bytes": path.stat().st_size if path and path.is_file() else 0,
            "absolute": str(path.resolve()) if path and path.exists() else "",
        }
    return result
