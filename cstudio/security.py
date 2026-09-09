"""Treat every external content blob as DATA, never instructions.

VOD files, transcripts, Twitch chat, page text, comments, metadata:
scan for embedded instruction-like lines, quarantine them into evidence,
and never execute them.
"""
from __future__ import annotations
import re

_PATTERNS = [
    re.compile(r"^\s*(ignore|disregard)\b.{0,120}(instruction|prompt|rule)", re.I),
    re.compile(r"^\s*(system|developer)\s*:", re.I),
    re.compile(r"^\s*(execute|run|delete|publish|upload)\b.{0,80}(now|immediately|automatically)", re.I),
    re.compile(r"\[system\]", re.I),
    re.compile(r"<\|?(system|developer|tool)\|?>", re.I),
]


def scan_text(text: str) -> list[dict]:
    findings: list[dict] = []
    for i, line in enumerate((text or "").splitlines(), 1):
        for p in _PATTERNS:
            if p.search(line):
                findings.append({"line": i, "text": line.strip()[:300], "pattern": p.pattern})
                break
    return findings


def sanitize_record(record: dict) -> dict:
    """Return copy with quarantine report; never raises on hostile content."""
    out = dict(record)
    blob = "\n".join(str(v) for v in record.values() if isinstance(v, str))
    out["_injection_findings"] = scan_text(blob)
    out["_untrusted"] = True
    return out
