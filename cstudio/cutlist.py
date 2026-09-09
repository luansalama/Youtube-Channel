"""Cutlist model + deterministic validation (Twitch multi-POV aware)."""
from __future__ import annotations
import csv
import os

from .core import StudioError
from .timecode import duration, parse_timecode

REQUIRED_COLUMNS = ["cut_id", "t_start", "t_end", "source", "rights_status"]
BLOCKED_RIGHTS = "sem_autorizacao_confirmada"


def read_cutlist_file(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise StudioError("cutlist CSV has no header")
        missing = [c for c in REQUIRED_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise StudioError(f"cutlist missing columns: {missing}")
        return list(reader)


def validate_cutlist_file(path: str, fps: float = 30.0, min_dur: float = 3.0,
                          max_dur: float = 180.0) -> dict:
    cuts = read_cutlist_file(path)
    errors: list[str] = []
    seen: set[str] = set()
    spans: list[tuple[float, float, str]] = []
    for i, row in enumerate(cuts, 2):  # 1-based + header
        cid = (row.get("cut_id") or "").strip()
        if not cid:
            errors.append(f"line {i}: empty cut_id")
        elif cid in seen:
            errors.append(f"line {i}: duplicate cut_id {cid}")
        seen.add(cid)
        try:
            s = parse_timecode(row.get("t_start", ""), fps)
            e = parse_timecode(row.get("t_end", ""), fps)
        except ValueError as exc:
            errors.append(f"line {i} ({cid}): {exc}")
            continue
        if e <= s:
            errors.append(f"line {i} ({cid}): t_end <= t_start")
            continue
        d = e - s
        if d < min_dur:
            errors.append(f"line {i} ({cid}): too short ({d:.1f}s < {min_dur}s)")
        if d > max_dur:
            errors.append(f"line {i} ({cid}): too long ({d:.1f}s > {max_dur}s)")
        spans.append((s, e, cid))
    spans.sort()
    for (s1, e1, c1), (s2, e2, c2) in zip(spans, spans[1:]):
        if s2 < e1:
            errors.append(f"overlap: {c1} [{s1:.2f}-{e1:.2f}] x {c2} [{s2:.2f}-{e2:.2f}]")
    total = sum(e - s for s, e, _ in spans)
    return {"ok": not errors, "errors": errors, "cuts": len(cuts),
            "total_seconds": round(total, 3)}


def total_runtime(path: str, fps: float = 30.0) -> float:
    return validate_cutlist_file(path, fps)["total_seconds"]


def build_timeline(cuts: list[dict], fps: float = 30.0, target: str = "youtube-1080p30") -> dict:
    events = []
    cursor = 0.0
    for row in cuts:
        d = duration(row["t_start"], row["t_end"], fps)
        events.append({"cut_id": row["cut_id"], "source": row.get("source", ""),
                       "source_in": row["t_start"], "source_out": row["t_end"],
                       "timeline_in": round(cursor, 3), "timeline_out": round(cursor + d, 3),
                       "duration": round(d, 3)})
        cursor += d
    return {"fps": fps, "target": target, "events": events,
            "total_seconds": round(cursor, 3)}
