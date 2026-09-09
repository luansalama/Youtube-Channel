"""Safe workspace file operations (sandboxed to one production)."""
from __future__ import annotations
import os
import shutil
from datetime import datetime, timezone

from .core import StudioError, load_project, save_project

TEXT_EXTENSIONS = {".md", ".txt", ".json", ".csv", ".srt", ".vtt", ".yaml", ".yml"}


def safe_relative_path(rel: str) -> str:
    if not rel or os.path.isabs(rel) or ".." in rel.replace("\\", "/").split("/"):
        raise StudioError(f"unsafe path: {rel!r}")
    return rel.replace("\\", "/")


def safe_prod_file(root: str, slug: str, rel: str, allow_internal: bool = False) -> str:
    from .core import prod_path
    rel = safe_relative_path(rel)
    if rel.startswith(".studio/") and not allow_internal:
        raise StudioError("internal files are engine-managed")
    vdir = prod_path(root, slug)
    full = os.path.abspath(os.path.join(vdir, rel))
    if os.path.commonpath([full, os.path.abspath(vdir)]) != os.path.abspath(vdir):
        raise StudioError(f"path escapes production: {rel!r}")
    return full


def backup_file(root: str, slug: str, rel: str) -> str | None:
    from .core import prod_path
    from .core import utc_now
    vdir = prod_path(root, slug)
    src = os.path.join(vdir, rel)
    if not os.path.isfile(src):
        return None
    stamp = utc_now().replace(":", "").replace("-", "")
    dst = os.path.join(vdir, ".studio", "backups", stamp, rel)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    return dst


def read_text_file(root: str, slug: str, rel: str) -> str:
    p = safe_prod_file(root, slug, rel)
    with open(p, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def write_text_file(root: str, slug: str, rel: str, content: str, by: str = "engine") -> None:
    from .core import prod_path
    if os.path.splitext(rel)[1].lower() not in TEXT_EXTENSIONS:
        raise StudioError(f"not editable as text: {rel}")
    p = safe_prod_file(root, slug, rel)
    backup_file(root, slug, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content.replace("\r\n", "\n"))
    vdir, project = load_project(root, slug)
    project.setdefault("history", []).append(
        {"at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
         "event": "file_saved", "file": rel, "by": by})
    save_project(vdir, project)
