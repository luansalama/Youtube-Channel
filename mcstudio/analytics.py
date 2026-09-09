from __future__ import annotations

import csv
import re
from datetime import date
from pathlib import Path
from typing import Any

from .core import StudioError, append_csv, read_csv_rows

FIELD_ALIASES = {
    "video_id": ["video id", "content", "video"],
    "title": ["video title", "title"],
    "views": ["views"],
    "watch_hours": ["watch time (hours)", "watch time hours", "watch time"],
    "impressions": ["impressions"],
    "ctr_percent": ["impressions click-through rate (%)", "impressions click through rate", "ctr"],
    "average_view_duration": ["average view duration", "avg view duration"],
    "subscribers_gained": ["subscribers", "subscribers gained"],
}


def normalise(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def find_column(fieldnames: list[str], aliases: list[str]) -> str | None:
    mapping = {normalise(name): name for name in fieldnames}
    for alias in aliases:
        if normalise(alias) in mapping:
            return mapping[normalise(alias)]
    return None


def parse_number(value: str | None) -> str:
    if value is None:
        return ""
    clean = value.strip().replace("%", "").replace(",", "")
    return clean


def import_youtube_csv(root: Path, csv_path: Path, slug: str, video_id: str | None = None) -> dict[str, Any]:
    if not csv_path.is_file():
        raise StudioError(f"CSV not found: {csv_path}")
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        columns = {target: find_column(fieldnames, aliases) for target, aliases in FIELD_ALIASES.items()}
        rows = list(reader)
    if not rows:
        raise StudioError("Analytics CSV contains no data rows.")
    selected = None
    if video_id and columns["video_id"]:
        selected = next((row for row in rows if (row.get(columns["video_id"] or "") or "").strip() == video_id), None)
    if selected is None:
        selected = rows[0]
    standard = {
        "snapshot_date": date.today().isoformat(),
        "slug": slug,
        "video_id": video_id or (selected.get(columns["video_id"] or "") if columns["video_id"] else ""),
        "title": selected.get(columns["title"] or "", "") if columns["title"] else "",
        "views": parse_number(selected.get(columns["views"] or "")) if columns["views"] else "",
        "watch_hours": parse_number(selected.get(columns["watch_hours"] or "")) if columns["watch_hours"] else "",
        "impressions": parse_number(selected.get(columns["impressions"] or "")) if columns["impressions"] else "",
        "ctr_percent": parse_number(selected.get(columns["ctr_percent"] or "")) if columns["ctr_percent"] else "",
        "average_view_duration": selected.get(columns["average_view_duration"] or "", "") if columns["average_view_duration"] else "",
        "subscribers_gained": parse_number(selected.get(columns["subscribers_gained"] or "")) if columns["subscribers_gained"] else "",
        "source_file": str(csv_path),
    }
    fields = ["snapshot_date", "slug", "video_id", "title", "views", "watch_hours", "impressions", "ctr_percent", "average_view_duration", "subscribers_gained", "source_file"]
    append_csv(root / "data" / "analytics" / "video_snapshots.csv", fields, standard)
    return standard


def report_for_slug(root: Path, slug: str) -> dict[str, Any]:
    rows = [row for row in read_csv_rows(root / "data" / "analytics" / "video_snapshots.csv") if row.get("slug") == slug]
    if not rows:
        raise StudioError(f"No analytics snapshots found for {slug}.")
    latest = rows[-1]
    report: dict[str, Any] = {"latest": latest, "snapshots": len(rows), "deltas": {}}
    if len(rows) >= 2:
        previous = rows[-2]
        for field in ["views", "watch_hours", "impressions", "subscribers_gained"]:
            try:
                report["deltas"][field] = float(latest.get(field) or 0) - float(previous.get(field) or 0)
            except ValueError:
                report["deltas"][field] = None
    return report
