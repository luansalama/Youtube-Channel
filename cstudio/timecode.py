"""Timecode utilities. Deterministic, no dependencies."""
from __future__ import annotations
import re

_TC_RE = re.compile(r"^(\d+):([0-5]?\d):([0-5]?\d)(?:([:;])([0-9]{1,3}))?$")
_SIMPLE_RE = re.compile(r"^([0-5]?\d):([0-5]?\d)$")


def parse_timecode(tc: str, fps: float = 30.0) -> float:
    """Parse HH:MM:SS[:FF|;FF] or MM:SS or seconds number -> seconds float."""
    if tc is None:
        raise ValueError("empty timecode")
    s = str(tc).strip()
    if re.fullmatch(r"\d+(\.\d+)?", s):
        return float(s)
    m = _SIMPLE_RE.fullmatch(s)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    m = _TC_RE.fullmatch(s)
    if not m:
        raise ValueError(f"invalid timecode: {tc!r}")
    h, mi, se, _, ff = m.groups()
    base = int(h) * 3600 + int(mi) * 60 + int(se)
    if ff is not None:
        base += int(ff) / float(fps)
    return float(base)


def format_timecode(seconds: float, fps: float = 30.0) -> str:
    if seconds < 0:
        raise ValueError("negative time")
    total_frames = int(round(seconds * fps))
    fr = total_frames % int(round(fps))
    tot_s = total_frames // int(round(fps))
    h, rem = divmod(tot_s, 3600)
    mi, se = divmod(rem, 60)
    return f"{h:02d}:{mi:02d}:{se:02d}:{fr:02d}"


def format_srt_timestamp(seconds: float) -> str:
    if seconds < 0:
        raise ValueError("negative time")
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3600000)
    mi, rem = divmod(rem, 60000)
    se, ms = divmod(rem, 1000)
    return f"{h:02d}:{mi:02d}:{se:02d},{ms:03d}"


def duration(start: str, end: str, fps: float = 30.0) -> float:
    return parse_timecode(end, fps) - parse_timecode(start, fps)
