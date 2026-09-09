"""Explicit rights/provenance registry. Never presume authorization."""
from __future__ import annotations
import csv
import os

from .core import StudioError, load_project, save_project

BLOCKED = "sem_autorizacao_confirmada"
ALLOWED = ("uso_proprio_confirmado", "licenca_confirmada", "autorizacao_terceiros_confirmada")


def set_asset_rights(root: str, slug: str, asset_id: str, rights_status: str,
                     authorizer: str = "", scope: str = "", evidence: str = "") -> dict:
    if rights_status not in (BLOCKED, *ALLOWED):
        raise StudioError(f"unknown rights_status: {rights_status}")
    if rights_status != BLOCKED and not authorizer:
        raise StudioError("clearance requires an authorizer name")
    vdir, project = load_project(root, slug)
    rights = project.setdefault("rights", {})
    rights[asset_id] = {"rights_status": rights_status, "authorizer": authorizer,
                        "scope": scope, "evidence": evidence}
    save_project(vdir, project)
    return rights[asset_id]


def rights_gate(project: dict, vdir: str) -> tuple[bool, str]:
    """Fail if ANY publish-relevant asset is blocked or unregistered."""
    problems: list[str] = []
    registered = project.get("rights") or {}
    # 1. project-level rights registry
    for asset_id, rec in registered.items():
        if (rec or {}).get("rights_status", BLOCKED) == BLOCKED:
            problems.append(f"{asset_id}: sem_autorizacao_confirmada")
    # 2. cutlist rows carry their own rights_status
    cl = os.path.join(vdir, ".studio/internal/cutlist/cutlist.csv")
    if os.path.isfile(cl):
        with open(cl, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if (row.get("rights_status") or BLOCKED).strip() == BLOCKED:
                    problems.append(f"cut {row.get('cut_id')}: sem_autorizacao_confirmada")
    # 3. ingest assets
    ing = os.path.join(vdir, ".studio/internal/ingest/assets.csv")
    if os.path.isfile(ing):
        with open(ing, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                st = (row.get("rights_status") or BLOCKED).strip()
                if st == BLOCKED:
                    problems.append(f"asset {row.get('asset_id')}: sem_autorizacao_confirmada")
                elif st not in ALLOWED:
                    problems.append(f"asset {row.get('asset_id')}: unknown status {st}")
    if problems:
        return False, "blocked: " + "; ".join(problems[:6])
    return True, "all publish assets cleared"
