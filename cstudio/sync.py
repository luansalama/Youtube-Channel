"""Multi-POV synchronisation (deterministic offset estimation).

Inputs are pre-computed event/clap time lists (seconds) per source —
never raw audio analysis here (that lives in integrations/). We estimate
pairwise offsets via median of nearest-neighbour deltas, which is
deterministic and robust to a few outliers.
"""
from __future__ import annotations
import statistics


def estimate_offset(events_a: list[float], events_b: list[float],
                    max_delta: float = 5.0) -> dict:
    """Estimate offset to add to B so it aligns with A. Returns report dict."""
    a = sorted(float(x) for x in events_a)
    b = sorted(float(x) for x in events_b)
    if not a or not b:
        return {"offset_seconds": 0.0, "method": "none", "confidence": 0.0,
                "pairs": 0, "note": "empty event list"}
    deltas = []
    j = 0
    for tb in b:
        while j + 1 < len(a) and abs(a[j + 1] - tb) < abs(a[j] - tb):
            j += 1
        d = a[j] - tb
        if abs(d) <= max_delta:
            deltas.append(d)
    if not deltas:
        return {"offset_seconds": 0.0, "method": "nearest-neighbour",
                "confidence": 0.0, "pairs": 0, "note": "no pairs within max_delta"}
    med = statistics.median(deltas)
    spread = statistics.pstdev(deltas) if len(deltas) > 1 else 0.0
    conf = max(0.0, min(1.0, 1.0 - spread / max_delta))
    conf *= min(1.0, len(deltas) / max(3, min(len(a), len(b))))
    return {"offset_seconds": round(med, 3), "method": "nearest-neighbour-median",
            "confidence": round(conf, 3), "pairs": len(deltas),
            "spread": round(spread, 3)}


def validate_sync_report(report: dict, min_confidence: float = 0.5,
                         max_offset: float = 600.0) -> tuple[bool, str]:
    try:
        off = float(report["offset_seconds"])
        conf = float(report.get("confidence", 0))
        method = str(report.get("method", ""))
    except (KeyError, TypeError, ValueError):
        return False, "sync-report missing offset_seconds/confidence/method"
    if not method or method == "none":
        return False, "sync method not recorded"
    if abs(off) > max_offset:
        return False, f"offset implausible: {off}s"
    if conf < min_confidence:
        return False, f"low sync confidence {conf} < {min_confidence}"
    return True, f"offset {off}s conf {conf} ({method})"


def apply_offset(t_seconds: float, offset_seconds: float) -> float:
    return round(float(t_seconds) + float(offset_seconds), 3)
