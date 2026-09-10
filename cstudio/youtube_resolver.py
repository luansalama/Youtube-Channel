"""YouTube Mirror Resolver.

Discovers official/allowed YouTube mirrors for Twitch VODs already ingested by a
Cuts Studio production.  It is intentionally an ingest subsystem: it may index,
compare, verify, download and register source media, but it never clears rights,
approves a gate, advances a stage or publishes.

The implementation is stdlib-first. yt-dlp/FFmpeg are external executables and
are invoked with argv lists only (never shell=True). YouTube/Twitch text is
untrusted data and is scanned before persistence/display.
"""
from __future__ import annotations

import csv
import difflib
import html
import json
import math
import os
import re
import shutil
import statistics
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import urllib.parse
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from . import core as C
from . import pipeline as PL
from .security import scan_text


def _hidden_subprocess_kwargs() -> dict[str, Any]:
    """Return Windows flags that keep console executables completely silent.

    The resolver worker itself runs without a console.  Without explicitly
    propagating CREATE_NO_WINDOW to child console applications, Windows may
    create a new Terminal/conhost window for yt-dlp, ffmpeg, ffprobe, fpcalc or
    Python helper processes.  STARTUPINFO/SW_HIDE is included as a belt-and-
    suspenders fallback for executables that honour the window hint.
    """
    if os.name != "nt":
        return {}
    kwargs: dict[str, Any] = {
        "creationflags": int(getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)),
    }
    startup_cls = getattr(subprocess, "STARTUPINFO", None)
    if startup_cls is not None:
        startup = startup_cls()
        startup.dwFlags |= int(getattr(subprocess, "STARTF_USESHOWWINDOW", 0x00000001))
        startup.wShowWindow = int(getattr(subprocess, "SW_HIDE", 0))
        kwargs["startupinfo"] = startup
    return kwargs


def _merge_hidden_subprocess_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Merge hidden-window defaults without clobbering caller process flags."""
    if os.name != "nt":
        return kwargs
    merged = dict(kwargs)
    hidden = _hidden_subprocess_kwargs()
    merged["creationflags"] = int(merged.get("creationflags", 0)) | int(hidden.get("creationflags", 0))
    if hidden.get("startupinfo") is not None and merged.get("startupinfo") is None:
        merged["startupinfo"] = hidden["startupinfo"]
    return merged


def _run_hidden(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
    return subprocess.run(*args, **_merge_hidden_subprocess_kwargs(kwargs))


def _popen_hidden(*args: Any, **kwargs: Any) -> subprocess.Popen:
    return subprocess.Popen(*args, **_merge_hidden_subprocess_kwargs(kwargs))

try:  # Optional fast path; resolver remains functional without NumPy.
    import numpy as _np  # type: ignore
except Exception:  # pragma: no cover - exercised on minimal installs
    _np = None

SCHEMA_VERSION = 2
MATCH_STATES = ("unmatched", "candidate", "likely", "verified", "rejected", "ambiguous")
STREAMER_RE = re.compile(r"^[A-Za-z0-9_]{1,40}$")
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,32}$")
CHANNEL_ID_RE = re.compile(r"^UC[A-Za-z0-9_-]{20,30}$")
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be"}

# Conservative defaults. Metadata gets a candidate into the expensive verifier;
# it never directly establishes verified state.
CANDIDATE_WEIGHTS = {
    # Channel membership is a hard gate when an immutable channel ID is known;
    # it should not add a constant bonus to every row in an already scoped index.
    "channel": 0.00,
    "date": 0.30,
    "duration": 0.22,
    "title": 0.28,
    "chapters": 0.20,
}
LIKELY_THRESHOLD = 0.70
VERIFY_ANCHORS = 4
ANCHOR_SECONDS = 28.0
ANCHOR_SIMILARITY_MIN = 0.82
VERIFY_MEDIAN_MIN = 0.85
FRAME_SECONDS = 0.50
PCM_RATE = 8000

# Audio-first verifier. Metadata only decides what is worth analysing; the
# established audiovisual anchors decide VERIFIED. Whisper is localized and
# on-demand only for borderline matches and never weakens the audio policy.
TRANSCRIPT_PROVIDER = "openai-whisper-turbo-segment-v3"  # backwards-compatible cache/provider id
TRANSCRIPT_PROVIDER_FASTER = "faster-whisper-1.2-batched-segment-v1"
TRANSCRIPT_PROVIDERS = {TRANSCRIPT_PROVIDER, TRANSCRIPT_PROVIDER_FASTER}
TRANSCRIPT_SCHEMA_VERSION = 2
TRANSCRIPT_DECODING_PROFILE = "matching-independent-segments-v1"
TRANSCRIPT_QUALITY_PROFILE = "matching-quality-v1"
TRANSCRIPT_ALIGNMENT_PROVIDER = "whisper-token-alignment-v1"
TRANSCRIPT_MIN_SIMILARITY = 0.72
TRANSCRIPT_VERIFY_MIN_SCORE = 0.54
TRANSCRIPT_VERIFY_PER_VOD = 4
TRANSCRIPT_ANCHORS = 7
TRANSCRIPT_QUERY_WORDS = 12
AUDIO_CONFIRM_SECONDS = 18.0
AUDIO_CONFIRM_RADIUS = 5.0
# Full-source Whisper is intentionally not part of the default resolver path.
# The old audiovisual verifier runs first; only borderline audio matches may
# request a few short transcript clips around already-localized audio anchors.
LOCALIZED_TRANSCRIPT_SECONDS = 48.0
LOCALIZED_TRANSCRIPT_MAX_ANCHORS = 4
LOCALIZED_TRANSCRIPT_MIN_AUDIO_SIMILARITY = 0.74
LOCALIZED_TRANSCRIPT_MIN_TEXT_SIMILARITY = 0.74
LOCALIZED_TRANSCRIPT_PROVIDER = "whisper-localized-anchor-v2"
DEFAULT_CONCURRENT_FRAGMENTS = 8
DEFAULT_FASTER_WHISPER_BATCH_SIZE = 8
DEFAULT_FASTER_WHISPER_COMPUTE_TYPE = "float16"
DEFAULT_STREAMER_LANGUAGES = {"alanzoka": "pt"}
METADATA_CACHE_SECONDS = 7 * 24 * 60 * 60
CAPTION_CACHE_SECONDS = 7 * 24 * 60 * 60
AUDIO_SEARCH_BACKTRACK_SECONDS = 120.0
AUDIO_SEARCH_FORWARD_SECONDS = 15 * 60.0
OFFSET_BACKTRACK_TOLERANCE_SECONDS = 20.0
OFFSET_CONTINUITY_TOLERANCE_SECONDS = 30.0
PEAK_EXCLUSION_SECONDS = 45.0
DEFAULT_ANALYSIS_AUDIO_CACHE_GB = 4.0
CHROMAPRINT_SAMPLE_STRIDE = 4
AUDIO_FINGERPRINT_PROVIDER = "ffmpeg-temporal-features-v1"
AUDIO_VERIFIER_PROVIDER = "ffmpeg-temporal-features-v3-piecewise-offset"
VERIFICATION_POLICY_VERSION = "global-source-assignment-v1"
DEEP_RESOLUTION_POLICY_VERSION = "localized-global-tiebreak-v1"
GLOBAL_DISCOVERY_MIN_SCORE = 0.45
GLOBAL_DISCOVERY_MIN_CHAPTER_SHARED = 2
GLOBAL_DISCOVERY_MAX_VIDEOS = 64
# Flat YouTube tab indexes frequently omit upload dates and may expose temporary
# titles such as "guns5".  Metadata similarity therefore cannot be a hard gate
# for recent uploads.  Resolve lazily enriches a bounded recent frontier and
# admits every video whose exact publish timestamp can overlap the production
# window, irrespective of title/chapter tokens.
GLOBAL_DISCOVERY_PRE_ROLL_DAYS = 2.0
GLOBAL_DISCOVERY_UPLOAD_LAG_DAYS = 21.0
GLOBAL_DISCOVERY_METADATA_SCAN_LIMIT = 40
GLOBAL_DISCOVERY_OLD_BOUNDARY_STREAK = 3
DEEP_RESOLUTION_MAX_VODS = 3
DEEP_RESOLUTION_MIN_AUDIO_ANCHORS = 2
DEEP_RESOLUTION_AUDIO_MEDIAN_MIN = 0.75

_LOCK = threading.RLock()
_RUNNING: dict[tuple[str, str], Any] = {}
# Avoid re-downloading the same large source repeatedly when an external Whisper
# invocation fails during one server lifetime. Restart/--force retries it.
_TRANSCRIPT_FAILURES: dict[tuple[str, ...], str] = {}
# Runtime probe cache keyed by the external Whisper Python interpreter.
_WHISPER_PREFLIGHTS: dict[str, dict[str, Any]] = {}
_FASTER_WHISPER_PREFLIGHTS: dict[str, dict[str, Any]] = {}
_FASTER_WHISPER_FAILURES: dict[str, str] = {}
_DENO_STATUS: dict[str, tuple[str, bool]] = {}


class _TranscriptContentError(C.StudioError):
    """Transcript decoded successfully but is unusable as matching evidence."""


def _abs_root(root: str) -> str:
    return os.path.abspath(root)


def youtube_dir(root: str, slug: str) -> str:
    vdir, _ = C.load_project(root, slug)
    return os.path.join(vdir, ".studio", "internal", "ingest", "youtube")


def _ensure_layout(root: str, slug: str) -> str:
    base = youtube_dir(root, slug)
    for rel in ("index", "fingerprints", "matches", "assignments", "jobs", "logs", "media", "tmp", "metadata", "captions", "analysis-audio",
                os.path.join("transcripts", "twitch"), os.path.join("transcripts", "youtube")):
        os.makedirs(os.path.join(base, rel), exist_ok=True)
    return base


def config_path(root: str) -> str:
    return os.path.join(root, "studio", "youtube-mirrors.json")


def default_config() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "auto_download_verified": False,
        "transcription": {
            "enabled": True,
            "provider": "faster-whisper",
            # ``backend`` is the runtime selector. Existing configs that predate
            # faster-whisper inherit ``auto`` without rewriting user settings.
            "backend": "auto",
            "whisper_home": "",
            "executable": "",
            "model": "",
            "faster_model": "",
            "device": "",
            "compute_type": DEFAULT_FASTER_WHISPER_COMPUTE_TYPE,
            "batch_size": DEFAULT_FASTER_WHISPER_BATCH_SIZE,
            "language": "",
            "language_by_streamer": dict(DEFAULT_STREAMER_LANGUAGES),
        },
        "streamers": {},
    }


def load_config(root: str) -> dict[str, Any]:
    data = C.read_json(config_path(root), None)
    if not isinstance(data, dict):
        return default_config()
    out = default_config()
    out.update({k: v for k, v in data.items() if k in out})
    if not isinstance(out.get("streamers"), dict):
        out["streamers"] = {}
    tdefaults = default_config()["transcription"]
    traw = out.get("transcription") if isinstance(out.get("transcription"), dict) else {}
    out["transcription"] = {**tdefaults, **traw}
    lang_defaults = dict(tdefaults.get("language_by_streamer") or {})
    lang_raw = traw.get("language_by_streamer") if isinstance(traw.get("language_by_streamer"), dict) else {}
    out["transcription"]["language_by_streamer"] = {**lang_defaults, **lang_raw}
    out["schema_version"] = SCHEMA_VERSION
    backend_hint = str(out["transcription"].get("backend") or "auto").strip().lower()
    out["transcription"]["provider"] = "faster-whisper" if backend_hint in {"", "auto", "faster-whisper"} else "openai-whisper"
    return out


def _validate_streamer(streamer: str) -> str:
    value = str(streamer or "").strip().lower()
    if not STREAMER_RE.fullmatch(value):
        raise C.StudioError("invalid Twitch streamer; use letters, numbers or underscore")
    return value


def normalize_youtube_url(url: str) -> str:
    value = str(url or "").strip()
    if not value:
        raise C.StudioError("YouTube channel URL is required")
    if not re.match(r"^https?://", value, re.I):
        value = "https://" + value.lstrip("/")
    try:
        parsed = urllib.parse.urlparse(value)
    except Exception as exc:
        raise C.StudioError(f"invalid YouTube URL: {exc}") from exc
    host = (parsed.hostname or "").lower()
    if host not in YOUTUBE_HOSTS:
        raise C.StudioError("channel URL must point to youtube.com")
    if host.endswith("youtu.be"):
        raise C.StudioError("use a YouTube channel URL, not a youtu.be video URL")
    path = parsed.path.rstrip("/")
    if not path or path == "/":
        raise C.StudioError("channel URL is missing a channel path")
    first = path.strip("/").split("/", 1)[0].lower()
    if first in {"watch", "shorts", "playlist", "live", "results", "feed", "embed"}:
        raise C.StudioError("use a YouTube channel URL, not a video/playlist/feed URL")
    # Canonicalise to /videos; yt-dlp accepts handles, /channel/UC..., /c/... and /user/...
    if path.endswith("/videos"):
        videos_path = path
    else:
        videos_path = path + "/videos"
    return urllib.parse.urlunparse(("https", "www.youtube.com", videos_path, "", "", ""))


def set_channel(root: str, streamer: str, *, name: str, url: str, channel_id: str = "",
                enabled: bool = True, language: str = "") -> dict[str, Any]:
    streamer = _validate_streamer(streamer)
    canonical = normalize_youtube_url(url)
    name = str(name or "").strip() or streamer
    channel_id = str(channel_id or "").strip()
    if channel_id and not CHANNEL_ID_RE.fullmatch(channel_id):
        raise C.StudioError("invalid YouTube channel_id; expected a UC... channel identifier")
    cfg = load_config(root)
    entry = cfg.setdefault("streamers", {}).setdefault(streamer, {"youtube_channels": []})
    lang = str(language or "").strip().lower()
    if lang:
        if lang != "auto" and not re.fullmatch(r"[a-z]{2,3}(?:-[a-z0-9]{2,8})?", lang):
            raise C.StudioError("invalid Whisper language; use pt/en/es or auto")
        entry["transcription_language"] = lang
    channels = list(entry.get("youtube_channels") or [])
    key = channel_id or canonical.lower()
    new = {
        "name": name[:160],
        "channel_id": channel_id[:128],
        "url": canonical,
        "enabled": bool(enabled),
        "updated_at": C.utc_now(),
    }
    replaced = False
    for i, row in enumerate(channels):
        row_key = str(row.get("channel_id") or row.get("url") or "").lower()
        if row_key == key.lower():
            channels[i] = new
            replaced = True
            break
    if not replaced:
        channels.append(new)
    entry["youtube_channels"] = channels
    C.write_json(config_path(root), cfg)
    return new


def set_channel_enabled(root: str, streamer: str, channel_key: str, enabled: bool) -> dict[str, Any]:
    streamer = _validate_streamer(streamer)
    key = str(channel_key or "").strip()
    cfg = load_config(root)
    channels = list(((cfg.get("streamers") or {}).get(streamer) or {}).get("youtube_channels") or [])
    for row in channels:
        if key in {str(row.get("channel_id") or ""), str(row.get("url") or "")}:
            row["enabled"] = bool(enabled)
            row["updated_at"] = C.utc_now()
            C.write_json(config_path(root), cfg)
            return row
    raise C.StudioError("configured YouTube channel not found")


def set_auto_download(root: str, enabled: bool) -> dict[str, Any]:
    cfg = load_config(root)
    cfg["auto_download_verified"] = bool(enabled)
    C.write_json(config_path(root), cfg)
    return cfg


def configured_channels(root: str, streamer: str = "", *, enabled_only: bool = False) -> list[dict[str, Any]]:
    cfg = load_config(root)
    rows: list[dict[str, Any]] = []
    selected = [_validate_streamer(streamer)] if streamer else sorted((cfg.get("streamers") or {}).keys())
    for st in selected:
        entry = ((cfg.get("streamers") or {}).get(st) or {})
        language = whisper_language(root, st)
        for ch in list(entry.get("youtube_channels") or []):
            if enabled_only and not ch.get("enabled", True):
                continue
            rows.append({"streamer": st, "transcription_language": language, **dict(ch)})
    return rows


def _configured_channel_ids(root: str, streamer: str) -> set[str]:
    return {
        str(row.get("channel_id") or "")
        for row in configured_channels(root, streamer, enabled_only=True)
        if CHANNEL_ID_RE.fullmatch(str(row.get("channel_id") or ""))
    }


def _channel_allowed_for_video(root: str, streamer: str, video: dict[str, Any]) -> bool:
    allowed = _configured_channel_ids(root, streamer)
    actual = str(video.get("channel_id") or "")
    # Until an immutable ID has been learned/configured we preserve the existing
    # URL-scoped behavior. Once IDs are available, mismatches fail closed.
    if not allowed or not CHANNEL_ID_RE.fullmatch(actual):
        return True
    return actual in allowed


def _remember_channel_id(root: str, streamer: str, configured_url: str, observed_channel_id: str) -> None:
    observed_channel_id = str(observed_channel_id or "")
    if not CHANNEL_ID_RE.fullmatch(observed_channel_id):
        return
    cfg = load_config(root)
    entry = ((cfg.get("streamers") or {}).get(streamer) or {})
    changed = False
    for row in list(entry.get("youtube_channels") or []):
        if normalize_youtube_url(str(row.get("url") or "")) != normalize_youtube_url(configured_url):
            continue
        current = str(row.get("channel_id") or "")
        if current and current != observed_channel_id:
            return
        if not current:
            row["channel_id"] = observed_channel_id
            row["updated_at"] = C.utc_now()
            changed = True
        break
    if changed:
        cfg["schema_version"] = SCHEMA_VERSION
        C.write_json(config_path(root), cfg)


def _resolve_tool(env_name: str, executable: str, *, required: bool = True) -> str:
    override = str(os.environ.get(env_name, "") or "").strip()
    if override:
        if os.path.isfile(override) or shutil.which(override):
            return override
        if required:
            raise C.StudioError(f"{env_name} not found: {override}")
        return ""
    found = shutil.which(executable) or ""
    if required and not found:
        raise C.StudioError(f"{executable} is required ({env_name} may override its path)")
    return found


def resolve_ytdlp(required: bool = True) -> str:
    return _resolve_tool("CSTUDIO_YTDLP", "yt-dlp", required=required)


def resolve_ffmpeg(required: bool = True) -> str:
    return _resolve_tool("CSTUDIO_FFMPEG", "ffmpeg", required=required)


def resolve_ffprobe(required: bool = True) -> str:
    return _resolve_tool("CSTUDIO_FFPROBE", "ffprobe", required=required)


def resolve_fpcalc(required: bool = False) -> str:
    return _resolve_tool("CSTUDIO_FPCALC", "fpcalc", required=required)


def resolve_deno(required: bool = False) -> str:
    return _resolve_tool("CSTUDIO_DENO", "deno", required=required)


def _tool_version(executable: str, *args: str) -> str:
    if not executable:
        return ""
    try:
        proc = _run_hidden(
            [executable, *args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", timeout=8, check=False,
        )
    except Exception:
        return ""
    return (proc.stdout or "").splitlines()[0].strip()[:200]


def _deno_status(executable: str) -> tuple[str, bool]:
    if not executable:
        return "", False
    with _LOCK:
        cached = _DENO_STATUS.get(executable)
    if cached is not None:
        return cached
    text = _tool_version(executable, "--version")
    match = re.search(r"(?:deno\s+)?(\d+)\.(\d+)(?:\.(\d+))?", text, re.I)
    version = (0, 0, 0) if not match else (int(match.group(1)), int(match.group(2)), int(match.group(3) or 0))
    result = (text, version >= (2, 3, 0))
    with _LOCK:
        _DENO_STATUS[executable] = result
    return result


def _deno_supported(executable: str) -> bool:
    return _deno_status(executable)[1]


def _yt_dlp_runtime_args() -> list[str]:
    """Use yt-dlp's recommended Deno EJS runtime when available.

    yt-dlp can still execute without this flag on versions/environments that do
    not require challenge solving, so absence remains a health degradation rather
    than a hard failure. This keeps offline/unit workflows portable while making
    production extraction explicit and diagnosable.
    """
    deno = resolve_deno(False)
    return ["--js-runtimes", f"deno:{deno}"] if deno and _deno_supported(deno) else []


def _yt_dlp_youtube_metadata_args() -> list[str]:
    # Metadata-only calls do not need HLS/DASH manifests; avoiding them saves
    # round-trips and reduces exposure to extractor changes.
    return ["--extractor-args", "youtube:skip=hls,dash"]


def _candidate_whisper_homes(root: str = "") -> list[str]:
    """Return portable discovery candidates; no absolute machine path is hardcoded."""
    rows: list[str] = []
    explicit = str(os.environ.get("CSTUDIO_WHISPER_HOME", "") or "").strip()
    if explicit:
        rows.append(explicit)
    if root:
        cfg = load_config(root)
        configured = str((cfg.get("transcription") or {}).get("whisper_home") or "").strip()
        if configured:
            rows.append(configured)
        # User's local layout is Applications/Youtube-Channel beside Applications/LLMS/Whisper.
        # This is a relative heuristic only; it safely no-ops elsewhere.
        rows.append(os.path.join(os.path.dirname(_abs_root(root)), "LLMS", "Whisper"))
    seen: set[str] = set()
    out: list[str] = []
    for value in rows:
        if not value:
            continue
        absolute = os.path.abspath(value)
        if absolute in seen:
            continue
        seen.add(absolute)
        out.append(absolute)
    return out


def resolve_whisper(root: str = "", required: bool = False) -> str:
    override = str(os.environ.get("CSTUDIO_WHISPER", "") or "").strip()
    if override:
        if os.path.isfile(override) or shutil.which(override):
            return override
        if required:
            raise C.StudioError(f"CSTUDIO_WHISPER not found: {override}")
        return ""
    if root:
        configured = str((load_config(root).get("transcription") or {}).get("executable") or "").strip()
        if configured:
            if os.path.isfile(configured) or shutil.which(configured):
                return configured
            if required:
                raise C.StudioError(f"configured Whisper executable not found: {configured}")
    exe_names = [os.path.join(".venv", "Scripts", "whisper.exe"), os.path.join(".venv", "bin", "whisper")]
    for home in _candidate_whisper_homes(root):
        for rel in exe_names:
            candidate = os.path.join(home, rel)
            if os.path.isfile(candidate):
                return candidate
    found = shutil.which("whisper") or ""
    if found:
        return found
    if required:
        raise C.StudioError("Whisper is required (set CSTUDIO_WHISPER or CSTUDIO_WHISPER_HOME)")
    return ""


def resolve_whisper_model(root: str = "") -> str:
    override = str(os.environ.get("CSTUDIO_WHISPER_MODEL", "") or "").strip()
    if override:
        return override
    if root:
        configured = str((load_config(root).get("transcription") or {}).get("model") or "").strip()
        if configured:
            return configured
    for home in _candidate_whisper_homes(root):
        checkpoint = os.path.join(home, "large-v3-turbo.pt")
        if os.path.isfile(checkpoint):
            return checkpoint
    return "turbo"



def resolve_faster_whisper_model(root: str = "", required: bool = False) -> str:
    """Resolve a local CTranslate2-converted Whisper model directory."""
    override = str(os.environ.get("CSTUDIO_FASTER_WHISPER_MODEL", "") or "").strip()
    candidates: list[str] = []
    if override:
        candidates.append(override)
    if root:
        configured = str((load_config(root).get("transcription") or {}).get("faster_model") or "").strip()
        if configured:
            candidates.append(configured)
    for home in _candidate_whisper_homes(root):
        candidates.extend([
            os.path.join(home, "faster-whisper-large-v3-turbo"),
            os.path.join(home, "faster-whisper-turbo"),
        ])
    for candidate in candidates:
        if candidate and os.path.isdir(candidate) and os.path.isfile(os.path.join(candidate, "model.bin")):
            return os.path.abspath(candidate)
    if required:
        requested = override or "faster-whisper-large-v3-turbo"
        raise C.StudioError(f"faster-whisper model not found: {requested}")
    return ""


def faster_whisper_compute_type(root: str = "") -> str:
    value = str(os.environ.get("CSTUDIO_FASTER_WHISPER_COMPUTE_TYPE", "") or "").strip()
    if not value and root:
        value = str((load_config(root).get("transcription") or {}).get("compute_type") or "").strip()
    return value or DEFAULT_FASTER_WHISPER_COMPUTE_TYPE


def faster_whisper_batch_size(root: str = "") -> int:
    raw = str(os.environ.get("CSTUDIO_FASTER_WHISPER_BATCH_SIZE", "") or "").strip()
    if not raw and root:
        raw = str((load_config(root).get("transcription") or {}).get("batch_size") or "")
    try:
        value = int(raw or DEFAULT_FASTER_WHISPER_BATCH_SIZE)
    except ValueError:
        value = DEFAULT_FASTER_WHISPER_BATCH_SIZE
    return max(1, min(32, value))


def _faster_failure_key(root: str = "") -> str:
    return "|".join([
        resolve_whisper_python(root, required=False),
        resolve_faster_whisper_model(root, required=False),
        whisper_device(root) or "auto",
        faster_whisper_compute_type(root),
    ])


def transcription_backend(root: str = "") -> str:
    """Select faster-whisper when installed, while retaining OpenAI fallback.

    ``auto`` is deliberately separate from the historical ``provider`` setting so
    old youtube-mirrors.json files can adopt the faster runtime without a config
    rewrite. Set CSTUDIO_TRANSCRIPTION_BACKEND=openai-whisper to pin the old path.
    """
    requested = str(os.environ.get("CSTUDIO_TRANSCRIPTION_BACKEND", "") or "").strip().lower()
    if not requested and root:
        requested = str((load_config(root).get("transcription") or {}).get("backend") or "auto").strip().lower()
    requested = requested or "auto"
    aliases = {
        "faster": "faster-whisper",
        "faster_whisper": "faster-whisper",
        "openai": "openai-whisper",
        "whisper": "openai-whisper",
    }
    requested = aliases.get(requested, requested)
    if requested == "faster-whisper":
        return "faster-whisper" if resolve_faster_whisper_model(root, False) and resolve_whisper_python(root, False) else ""
    if requested == "openai-whisper":
        return "openai-whisper" if resolve_whisper(root, False) else ""
    if requested not in {"auto", ""}:
        return ""
    faster_ready = bool(resolve_faster_whisper_model(root, False) and resolve_whisper_python(root, False))
    if faster_ready:
        with _LOCK:
            failed = bool(_FASTER_WHISPER_FAILURES.get(_faster_failure_key(root)))
        if not failed:
            return "faster-whisper"
    if resolve_whisper(root, False):
        return "openai-whisper"
    return ""


def _faster_whisper_subprocess_env(root: str) -> dict[str, str]:
    """Expose CUDA DLLs commonly bundled with the dedicated Whisper venv."""
    env = _media_subprocess_env()
    python = resolve_whisper_python(root, required=False)
    if not python:
        return env
    scripts = Path(python).resolve().parent
    venv = scripts.parent
    candidates = [
        venv / "Lib" / "site-packages" / "ctranslate2",
        venv / "lib" / "site-packages" / "ctranslate2",
        venv / "Lib" / "site-packages" / "torch" / "lib",
        venv / "lib" / "site-packages" / "torch" / "lib",
        venv / "Lib" / "site-packages" / "nvidia" / "cublas" / "bin",
        venv / "Lib" / "site-packages" / "nvidia" / "cudnn" / "bin",
    ]
    prepend = [str(path) for path in candidates if path.is_dir()]
    if prepend:
        env["PATH"] = os.pathsep.join(prepend + [env.get("PATH", "")])
    return env


def _faster_whisper_preflight(root: str, log=None) -> dict[str, Any]:
    python = resolve_whisper_python(root, required=True)
    model = resolve_faster_whisper_model(root, required=True)
    key = "|".join([python, model, whisper_device(root) or "auto", faster_whisper_compute_type(root)])
    with _LOCK:
        cached = _FASTER_WHISPER_PREFLIGHTS.get(key)
    if cached:
        return dict(cached)
    probe = (
        "import json,ctranslate2,faster_whisper; "
        "print(json.dumps({'faster_whisper':getattr(faster_whisper,'__version__','unknown'),"
        "'ctranslate2':getattr(ctranslate2,'__version__','unknown'),"
        "'cuda_devices':int(ctranslate2.get_cuda_device_count())}))"
    )
    proc = _run_hidden(
        [python, "-c", probe], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", env=_faster_whisper_subprocess_env(root), timeout=30,
    )
    output = (proc.stdout or "").strip()
    if proc.returncode != 0:
        raise C.StudioError(f"faster-whisper runtime preflight failed with code {proc.returncode}: {output[-1200:]}")
    try:
        data = json.loads(output.splitlines()[-1])
    except Exception as exc:
        raise C.StudioError(f"faster-whisper preflight returned invalid output: {output[-1200:]}") from exc
    configured = whisper_device(root)
    effective_device = configured or ("cuda" if int(data.get("cuda_devices") or 0) > 0 else "cpu")
    if effective_device == "cuda" and int(data.get("cuda_devices") or 0) < 1:
        raise C.StudioError("faster-whisper requested CUDA but CTranslate2 reports no CUDA device")
    data.update({
        "backend": "faster-whisper",
        "model": model,
        "effective_device": effective_device,
        "compute_type": faster_whisper_compute_type(root) if effective_device == "cuda" else "int8",
        "batch_size": faster_whisper_batch_size(root),
    })
    with _LOCK:
        _FASTER_WHISPER_PREFLIGHTS[key] = dict(data)
    if log:
        log.write(
            "faster-whisper preflight: "
            f"python={python} faster_whisper={data.get('faster_whisper')} ctranslate2={data.get('ctranslate2')} "
            f"cuda_devices={data.get('cuda_devices')} device={effective_device} "
            f"compute={data.get('compute_type')} batch={data.get('batch_size')} "
            f"model={os.path.basename(model)}\n"
        )
        log.flush()
    return data


def _transcription_preflight(root: str, log=None) -> dict[str, Any]:
    backend = transcription_backend(root)
    if backend == "faster-whisper":
        try:
            return _faster_whisper_preflight(root, log=log)
        except Exception as exc:
            with _LOCK:
                _FASTER_WHISPER_FAILURES[_faster_failure_key(root)] = str(exc)[:1600]
            if resolve_whisper(root, False):
                if log:
                    log.write(f"faster-whisper preflight failed; OpenAI Whisper fallback available: {exc}\n")
                    log.flush()
                data = _whisper_preflight(root, log=log)
                return {"backend": "openai-whisper", **data}
            raise
    if backend == "openai-whisper":
        data = _whisper_preflight(root, log=log)
        return {"backend": "openai-whisper", **data}
    raise C.StudioError("no transcription runtime available")


def whisper_device(root: str = "") -> str:
    value = str(os.environ.get("CSTUDIO_WHISPER_DEVICE", "") or "").strip()
    if value:
        return value
    if root:
        return str((load_config(root).get("transcription") or {}).get("device") or "").strip()
    return ""


def whisper_language(root: str = "", streamer: str = "") -> str:
    """Resolve the Whisper language hint with per-streamer precedence.

    Empty return means Whisper auto-detect. The literal ``auto`` is accepted as
    an explicit opt-out from defaults. V2.3 ships a conservative default hint
    for Alanzoka (pt) because long VODs can begin with English game audio and
    otherwise poison global auto-detection.
    """
    def _value(raw: Any) -> tuple[bool, str]:
        text = str(raw or "").strip().lower()
        if not text:
            return False, ""
        return True, "" if text == "auto" else text

    present, value = _value(os.environ.get("CSTUDIO_WHISPER_LANGUAGE", ""))
    if present:
        return value
    st = str(streamer or "").strip().lower()
    if st:
        env_key = "CSTUDIO_WHISPER_LANGUAGE_" + re.sub(r"[^A-Z0-9]", "_", st.upper())
        present, value = _value(os.environ.get(env_key, ""))
        if present:
            return value
    if root:
        cfg = load_config(root)
        if st:
            entry = ((cfg.get("streamers") or {}).get(st) or {})
            present, value = _value(entry.get("transcription_language"))
            if present:
                return value
            by_streamer = (cfg.get("transcription") or {}).get("language_by_streamer") or {}
            if isinstance(by_streamer, dict):
                present, value = _value(by_streamer.get(st))
                if present:
                    return value
        present, value = _value((cfg.get("transcription") or {}).get("language"))
        if present:
            return value
        return ""
    if st:
        return str(DEFAULT_STREAMER_LANGUAGES.get(st) or "").strip().lower()
    return ""


def configured_streamer_languages(root: str) -> dict[str, str]:
    cfg = load_config(root)
    streamers = set((cfg.get("streamers") or {}).keys()) | set(DEFAULT_STREAMER_LANGUAGES.keys())
    return {st: lang for st in sorted(streamers) if (lang := whisper_language(root, st))}


def transcript_enabled(root: str) -> bool:
    raw = str(os.environ.get("CSTUDIO_WHISPER_ENABLED", "") or "").strip().lower()
    if raw:
        return raw not in {"0", "false", "no", "off"}
    return bool((load_config(root).get("transcription") or {}).get("enabled", True))


def concurrent_fragments() -> int:
    raw = str(os.environ.get("CSTUDIO_YTDLP_FRAGMENTS", DEFAULT_CONCURRENT_FRAGMENTS) or DEFAULT_CONCURRENT_FRAGMENTS)
    try:
        value = int(raw)
    except ValueError:
        value = DEFAULT_CONCURRENT_FRAGMENTS
    return max(1, min(32, value))


def health(root: str = "") -> dict[str, Any]:
    whisper = resolve_whisper(root, False) if root else resolve_whisper("", False)
    model = resolve_whisper_model(root) if root else str(os.environ.get("CSTUDIO_WHISPER_MODEL") or "turbo")
    faster_model = resolve_faster_whisper_model(root, False) if root else str(os.environ.get("CSTUDIO_FASTER_WHISPER_MODEL") or "")
    backend = transcription_backend(root) if root else ("faster-whisper" if faster_model else ("openai-whisper" if whisper else ""))
    deno = resolve_deno(False)
    deno_version, deno_supported = _deno_status(deno)
    return {
        "yt_dlp": resolve_ytdlp(False),
        "ffmpeg": resolve_ffmpeg(False),
        "ffprobe": resolve_ffprobe(False),
        "fpcalc": resolve_fpcalc(False),
        "deno": deno,
        "deno_version": deno_version,
        "deno_supported": deno_supported,
        "deno_minimum": "2.3.0",
        "whisper": whisper,
        "whisper_model": model,
        "whisper_device": whisper_device(root),
        "whisper_languages": configured_streamer_languages(root) if root else dict(DEFAULT_STREAMER_LANGUAGES),
        "faster_whisper_model": faster_model,
        "faster_whisper_available": bool(faster_model and (resolve_whisper_python(root, False) if root else True)),
        "faster_whisper_batch_size": faster_whisper_batch_size(root) if root else DEFAULT_FASTER_WHISPER_BATCH_SIZE,
        "faster_whisper_compute_type": faster_whisper_compute_type(root) if root else DEFAULT_FASTER_WHISPER_COMPUTE_TYPE,
        "transcription_backend": backend,
        "yt_dlp_available": bool(resolve_ytdlp(False)),
        "ffmpeg_available": bool(resolve_ffmpeg(False)),
        "ffprobe_available": bool(resolve_ffprobe(False)),
        "fpcalc_available": bool(resolve_fpcalc(False)),
        "deno_available": bool(deno),
        "youtube_js_runtime_status": "ready" if deno_supported else "degraded",
        "whisper_available": bool(whisper or faster_model),
        "transcript_enabled": transcript_enabled(root) if root else True,
        "concurrent_fragments": concurrent_fragments(),
        "analysis_audio_cache_gb": round(_analysis_audio_cache_limit_bytes() / (1024**3), 2),
        "numpy_acceleration": bool(_np is not None),
        "matcher_engine": "numpy-exact" if _np is not None else "unavailable (NumPy required)",
        "verification_policy": VERIFICATION_POLICY_VERSION,
        "verification_provider": "global all-VOD audio assignment + piecewise offsets + localized text fallback",
        "transcript_provider": TRANSCRIPT_PROVIDER_FASTER if backend == "faster-whisper" else TRANSCRIPT_PROVIDER,
    }

def _display_cmd(cmd: Iterable[str]) -> str:
    parts = []
    for item in cmd:
        s = str(item)
        parts.append(f'"{s}"' if any(c.isspace() for c in s) else s)
    return " ".join(parts)


def _ffmpeg_location_args() -> list[str]:
    """Tell yt-dlp where the resolver-discovered FFmpeg toolchain lives."""
    ffmpeg = resolve_ffmpeg(False)
    if not ffmpeg:
        return []
    location = os.path.dirname(ffmpeg) if os.path.isfile(ffmpeg) else ffmpeg
    return ["--ffmpeg-location", location] if location else []


def _media_subprocess_env() -> dict[str, str]:
    """Expose resolver-discovered FFmpeg/ffprobe to child CLIs such as Whisper.

    OpenAI Whisper invokes the literal command ``ffmpeg`` internally, so merely
    knowing CSTUDIO_FFMPEG inside Cuts Studio is insufficient on Windows.
    """
    env = os.environ.copy()
    # Keep Windows console encodings from crashing Whisper/argparse or hiding
    # subprocess diagnostics when the host code page is cp1252.
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    dirs: list[str] = []
    for tool in (resolve_ffmpeg(False), resolve_ffprobe(False)):
        if not tool:
            continue
        directory = os.path.dirname(tool) if os.path.isfile(tool) else tool
        if directory and directory not in dirs:
            dirs.append(directory)
    if dirs:
        current = env.get("PATH", "")
        env["PATH"] = os.pathsep.join(dirs + ([current] if current else []))
    return env


def build_index_command(channel_url: str, *, playlist_end: int = 120) -> list[str]:
    ytdlp = resolve_ytdlp()
    url = normalize_youtube_url(channel_url)
    return [
        ytdlp, "--flat-playlist", "--dump-json", "--skip-download", "--ignore-errors",
        *_yt_dlp_runtime_args(),
        "--extractor-args", "youtubetab:approximate_date",
        "--playlist-end", str(max(1, int(playlist_end))), url,
    ]


def _safe_text(value: Any, max_len: int = 12000) -> str:
    text = str(value or "")[:max_len]
    return text


def normalize_ytdlp_entry(raw: dict[str, Any], fallback_channel: dict[str, Any] | None = None) -> dict[str, Any]:
    fallback_channel = fallback_channel or {}
    video_id = str(raw.get("id") or raw.get("url") or "").strip()
    if not VIDEO_ID_RE.fullmatch(video_id):
        webpage = str(raw.get("webpage_url") or "")
        match = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{6,32})", webpage)
        if match:
            video_id = match.group(1)
    if not VIDEO_ID_RE.fullmatch(video_id):
        raise ValueError("invalid YouTube video id")
    title = _safe_text(raw.get("title"), 1000)
    description = _safe_text(raw.get("description"), 12000)
    findings = scan_text(title + "\n" + description)
    timestamp = raw.get("timestamp") or raw.get("release_timestamp")
    upload_date = str(raw.get("upload_date") or raw.get("release_date") or "")
    duration = raw.get("duration")
    try:
        duration = float(duration) if duration is not None else None
    except (TypeError, ValueError):
        duration = None
    channel_id = str(raw.get("channel_id") or raw.get("uploader_id") or fallback_channel.get("channel_id") or "")
    channel_name = _safe_text(raw.get("channel") or raw.get("uploader") or fallback_channel.get("name"), 300)
    webpage_url = str(raw.get("webpage_url") or f"https://www.youtube.com/watch?v={video_id}")
    thumbs = raw.get("thumbnails") if isinstance(raw.get("thumbnails"), list) else []
    return {
        "schema_version": SCHEMA_VERSION,
        "video_id": video_id,
        "url": webpage_url,
        "channel_id": channel_id,
        "channel_name": channel_name,
        "title": title,
        "description": description,
        "upload_date": upload_date,
        "timestamp": timestamp,
        "duration": duration,
        "availability": raw.get("availability"),
        "live_status": raw.get("live_status"),
        "thumbnail": raw.get("thumbnail") or (thumbs[-1].get("url") if thumbs else None),
        "thumbnails": thumbs[-4:],
        "view_count": raw.get("view_count"),
        "playlist_index": raw.get("playlist_index"),
        "playlist_autonumber": raw.get("playlist_autonumber"),
        "chapters": raw.get("chapters") if isinstance(raw.get("chapters"), list) else [],
        "formats_summary": _formats_summary(raw.get("formats")),
        "indexed_at": C.utc_now(),
        "untrusted": True,
        "injection_findings": findings,
    }


def _formats_summary(formats: Any) -> dict[str, Any]:
    if not isinstance(formats, list):
        return {}
    heights = sorted({int(f.get("height")) for f in formats if isinstance(f, dict) and f.get("height")})
    fps = sorted({float(f.get("fps")) for f in formats if isinstance(f, dict) and f.get("fps")})
    return {
        "max_height": max(heights) if heights else None,
        "max_fps": max(fps) if fps else None,
        "heights": heights[-8:],
    }


def _index_file(root: str, slug: str, streamer: str) -> str:
    return os.path.join(_ensure_layout(root, slug), "index", f"{_validate_streamer(streamer)}.json")


def load_index(root: str, slug: str, streamer: str = "") -> list[dict[str, Any]]:
    base = os.path.join(_ensure_layout(root, slug), "index")
    files = [_index_file(root, slug, streamer)] if streamer else [os.path.join(base, n) for n in sorted(os.listdir(base)) if n.endswith(".json")]
    rows: list[dict[str, Any]] = []
    for path in files:
        data = C.read_json(path, {})
        if isinstance(data, dict):
            rows.extend([dict(x) for x in data.get("videos", []) if isinstance(x, dict)])
    return rows


def index_status(root: str, slug: str) -> dict[str, Any]:
    base = os.path.join(_ensure_layout(root, slug), "index")
    by_streamer = []
    total = 0
    last = ""
    for name in sorted(os.listdir(base)):
        if not name.endswith(".json"):
            continue
        data = C.read_json(os.path.join(base, name), {}) or {}
        count = len(data.get("videos") or [])
        total += count
        last = max(last, str(data.get("updated_at") or ""))
        by_streamer.append({"streamer": name[:-5], "videos": count, "updated_at": data.get("updated_at", "")})
    return {"videos": total, "last_indexed_at": last, "streamers": by_streamer}


def index_streamer(root: str, slug: str, streamer: str, *, force: bool = False,
                   playlist_end: int = 120, log=None) -> dict[str, Any]:
    streamer = _validate_streamer(streamer)
    C.load_project(root, slug)
    channels = configured_channels(root, streamer, enabled_only=True)
    if not channels:
        raise C.StudioError(f"no enabled YouTube channels configured for {streamer}")
    path = _index_file(root, slug, streamer)
    existing_doc = C.read_json(path, {}) or {}
    existing = {str(v.get("video_id")): dict(v) for v in existing_doc.get("videos", []) if isinstance(v, dict)}
    seen = set()
    indexed_channels = []
    for channel in channels:
        cmd = build_index_command(channel["url"], playlist_end=playlist_end)
        if log:
            log.write(f"index {streamer}/{channel.get('name')}: {_display_cmd(cmd)}\n")
            log.flush()
        proc = _run_hidden(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", check=False)
        if proc.returncode != 0 and not proc.stdout.strip():
            raise C.StudioError(f"yt-dlp index failed for {channel.get('name')}: {proc.stderr[-600:]}")
        channel_count = 0
        observed_channel_id = ""
        for line in proc.stdout.splitlines():
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
                row = normalize_ytdlp_entry(raw, channel)
            except Exception:
                continue
            row["streamer"] = streamer
            row["configured_channel_url"] = channel["url"]
            row["configured_channel_name"] = channel.get("name", "")
            if not observed_channel_id and CHANNEL_ID_RE.fullmatch(str(row.get("channel_id") or "")):
                observed_channel_id = str(row["channel_id"])
            existing[row["video_id"]] = {**existing.get(row["video_id"], {}), **row}
            seen.add(row["video_id"])
            channel_count += 1
        if observed_channel_id:
            _remember_channel_id(root, streamer, str(channel["url"]), observed_channel_id)
        indexed_channels.append({"name": channel.get("name"), "url": channel.get("url"), "seen": channel_count})
    videos = sorted(existing.values(), key=_video_sort_key, reverse=True)
    doc = {
        "schema_version": SCHEMA_VERSION,
        "streamer": streamer,
        "updated_at": C.utc_now(),
        "refresh_mode": "forced" if force else "incremental_recent_window",
        "playlist_end": int(playlist_end),
        "channels": indexed_channels,
        "seen_this_run": len(seen),
        "videos": videos,
    }
    C.write_json(path, doc)
    return {"streamer": streamer, "videos": len(videos), "seen_this_run": len(seen), "path": path, "channels": indexed_channels}


def index_all(root: str, slug: str, *, streamer: str = "", force: bool = False,
              playlist_end: int = 120, log=None) -> dict[str, Any]:
    streamers = [_validate_streamer(streamer)] if streamer else sorted({r["streamer"] for r in configured_channels(root, enabled_only=True)})
    if not streamers:
        raise C.StudioError("no enabled YouTube mirror channels configured")
    results = [index_streamer(root, slug, st, force=force, playlist_end=playlist_end, log=log) for st in streamers]
    return {"indexed": results, "status": index_status(root, slug)}


def _video_sort_key(row: dict[str, Any]) -> tuple[int, float, float]:
    """Sort newest first while preserving flat-playlist recency when dates are absent."""
    published = _video_publish_time(row)
    if published is not None:
        return 1, published.timestamp(), 0.0
    try:
        playlist_index = float(row.get("playlist_index"))
        if playlist_index > 0:
            # YouTube channel tabs enumerate from newest (1) to oldest.
            return 0, 0.0, -playlist_index
    except (TypeError, ValueError):
        pass
    # Unknown legacy entries should trail current flat-index rows rather than
    # accidentally becoming the "recent frontier" merely because date=0.
    return 0, 0.0, -1_000_000_000.0


def _walk(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from _walk(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _walk(value)


def parse_twitch_discovery(path: str, streamer: str = "") -> dict[str, Any]:
    data = C.read_json(path, {}) or {}
    vod_id = str(data.get("vod_id") or "")
    candidates = []
    chapters = []
    for obj in _walk(data):
        if str(obj.get("id") or "") == vod_id:
            candidates.append(obj)
        # Chapter-ish structures in Twitch captures commonly expose position/duration + game/title.
        if any(k in obj for k in ("positionMilliseconds", "positionSeconds", "durationMilliseconds")):
            game_obj = obj.get("game") if isinstance(obj.get("game"), dict) else {}
            details = obj.get("details") if isinstance(obj.get("details"), dict) else {}
            details_game = details.get("game") if isinstance(details.get("game"), dict) else {}
            title = (obj.get("description") or obj.get("title") or game_obj.get("displayName") or
                     game_obj.get("name") or details_game.get("displayName") or details_game.get("name"))
            start = obj.get("positionSeconds")
            if start is None and obj.get("positionMilliseconds") is not None:
                try: start = float(obj.get("positionMilliseconds")) / 1000.0
                except Exception: start = None
            dur = obj.get("durationSeconds")
            if dur is None and obj.get("durationMilliseconds") is not None:
                try: dur = float(obj.get("durationMilliseconds")) / 1000.0
                except Exception: dur = None
            if title and start is not None:
                chapters.append({"title": _safe_text(title, 500), "start": float(start), "duration": float(dur) if dur is not None else None})
    best = max(candidates, key=lambda o: len(o.keys()), default={})
    title = _safe_text(best.get("title") or best.get("broadcastSettings", {}).get("title") if isinstance(best.get("broadcastSettings"), dict) else best.get("title"), 1000)
    game_obj = best.get("game") if isinstance(best.get("game"), dict) else {}
    game = _safe_text(game_obj.get("displayName") or game_obj.get("name"), 300)
    created = best.get("createdAt") or best.get("publishedAt") or best.get("recordedAt")
    duration = best.get("lengthSeconds") or best.get("durationSeconds") or best.get("duration")
    try: duration = float(duration) if duration is not None else None
    except Exception: duration = None
    # Chat timestamps are a useful fallback for approximate VOD start date.
    if not created:
        dates = []
        for obj in _walk(data.get("important_operations", {})):
            value = obj.get("createdAt")
            if isinstance(value, str) and value:
                dates.append(value)
        created = min(dates) if dates else ""
    return {
        "vod_id": vod_id,
        "streamer": streamer,
        "title": title,
        "game": game,
        "created_at": created or "",
        "duration": duration,
        "chapters": _dedupe_chapters(chapters),
        "path": path,
        "source_url": f"https://www.twitch.tv/videos/{vod_id}" if vod_id else "",
        "untrusted": True,
        "injection_findings": scan_text(title + "\n" + game),
    }


def _dedupe_chapters(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set(); out = []
    for row in sorted(rows, key=lambda r: float(r.get("start") or 0)):
        key = (round(float(row.get("start") or 0), 1), str(row.get("title") or "").lower())
        if key in seen: continue
        seen.add(key); out.append(row)
    return out[:200]


def list_twitch_vods(root: str, slug: str, streamer: str = "") -> list[dict[str, Any]]:
    vdir, _ = C.load_project(root, slug)
    base = os.path.join(vdir, ".studio", "internal", "ingest", "twitch")
    if not os.path.isdir(base):
        return []
    rows = []
    for st in sorted(os.listdir(base)):
        if st == "runs" or (streamer and st.lower() != streamer.lower()):
            continue
        discovery = os.path.join(base, st, "discovery")
        if not os.path.isdir(discovery):
            continue
        for name in sorted(os.listdir(discovery)):
            if re.fullmatch(r"\d+\.json", name):
                rows.append(parse_twitch_discovery(os.path.join(discovery, name), st.lower()))
    return rows


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]{3,}", (text or "").lower())
    stop = {"the","and","com","para","uma","das","dos","que","live","vod","parte","final","jogo","game","stream"}
    return {w for w in words if w not in stop}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b: return 0.0
    return len(a & b) / len(a | b)


def _parse_date(value: Any) -> datetime | None:
    if value is None or value == "": return None
    if isinstance(value, (int, float)):
        try: return datetime.fromtimestamp(float(value), timezone.utc)
        except Exception: return None
    text = str(value)
    if re.fullmatch(r"\d{8}", text):
        try: return datetime.strptime(text, "%Y%m%d").replace(tzinfo=timezone.utc)
        except Exception: return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _date_score(vod: dict[str, Any], video: dict[str, Any]) -> tuple[float | None, str]:
    a = _parse_date(vod.get("created_at")); b = _parse_date(video.get("timestamp") or video.get("upload_date"))
    if not a or not b: return None, "date unavailable on one side"
    days = (b - a).total_seconds() / 86400.0
    if days < -2: return 0.0, f"YouTube predates Twitch by {abs(days):.1f}d"
    # Uploads between same-day and two weeks later are normal; decay beyond that.
    score = math.exp(-max(0.0, days) / 12.0)
    if -2 <= days < 0: score *= 0.65
    return max(0.0, min(1.0, score)), f"upload delay {days:+.1f}d"


def _duration_score(vod: dict[str, Any], video: dict[str, Any]) -> tuple[float | None, str]:
    try: tv = float(vod.get("duration") or 0); yv = float(video.get("duration") or 0)
    except Exception: return None, "duration unavailable"
    if tv <= 0 or yv <= 0: return None, "duration unavailable"
    ratio = yv / tv
    # Mirrors may be a subset of a VOD. Longer-than-VOD is suspicious; short subsets remain plausible.
    if ratio > 1.15: return max(0.0, 1.0 - (ratio - 1.15) * 2.5), f"YouTube/Twitch duration ratio {ratio:.2f}"
    if ratio >= 0.25: return min(1.0, 0.65 + 0.35 * min(1.0, ratio / 0.9)), f"subset-compatible ratio {ratio:.2f}"
    return max(0.15, ratio / 0.25 * 0.65), f"short subset ratio {ratio:.2f}"


def _chapter_score(vod: dict[str, Any], video: dict[str, Any]) -> tuple[float, str]:
    vt = _tokens(str(video.get("title") or "") + " " + str(video.get("description") or ""))
    pieces = [str(vod.get("game") or ""), str(vod.get("title") or "")]
    pieces += [str(c.get("title") or "") for c in vod.get("chapters") or []]
    tt = _tokens(" ".join(pieces))
    score = _jaccard(vt, tt)
    if vt and tt and vt & tt:
        score = min(1.0, 0.4 + 1.4 * score)
    return score, f"shared tokens: {', '.join(sorted(vt & tt)[:8]) or 'none'}"


def score_candidate(vod: dict[str, Any], video: dict[str, Any], configured_channel: bool = True) -> dict[str, Any]:
    title_tokens = _tokens(str(video.get("title") or ""))
    vod_title_tokens = _tokens(str(vod.get("title") or "") + " " + str(vod.get("game") or ""))
    title_score: float | None = _jaccard(vod_title_tokens, title_tokens) if title_tokens and vod_title_tokens else None
    if title_score is not None and title_score > 0:
        title_score = min(1.0, 0.3 + 1.4 * title_score)
    date_score, date_detail = _date_score(vod, video)
    duration_score, duration_detail = _duration_score(vod, video)
    chapter_score, chapter_detail = _chapter_score(vod, video)
    if not (_tokens(str(video.get("title") or "") + " " + str(video.get("description") or ""))):
        chapter_score = None
        chapter_detail = "title/description unavailable"

    raw = {
        "channel": (1.0 if configured_channel else 0.0, "configured mirror channel" if configured_channel else "channel mismatch"),
        "date": (date_score, date_detail),
        "duration": (duration_score, duration_detail),
        "title": (title_score, "token similarity" if title_score is not None else "title unavailable"),
        "chapters": (chapter_score, chapter_detail),
    }
    available_weight = sum(
        CANDIDATE_WEIGHTS[key] for key, (value, _detail) in raw.items()
        if value is not None and CANDIDATE_WEIGHTS[key] > 0
    )
    signals: dict[str, dict[str, Any]] = {}
    contributions: dict[str, float] = {}
    for key, (value, detail) in raw.items():
        base_weight = CANDIDATE_WEIGHTS[key]
        effective_weight = (base_weight / available_weight) if value is not None and available_weight > 0 and base_weight > 0 else 0.0
        signals[key] = {
            "score": round(float(value), 4) if value is not None else None,
            "available": value is not None,
            "weight": base_weight,
            "effective_weight": round(effective_weight, 6),
            "detail": detail,
        }
        contributions[key] = round((float(value) if value is not None else 0.0) * effective_weight, 4)
    score = round(sum(contributions.values()), 4)
    return {"candidate_score": score, "signals": signals, "contributions": contributions}


def _candidate_file(root: str, slug: str, vod_id: str, video_id: str) -> str:
    safe_vod = re.sub(r"[^0-9]", "", str(vod_id))
    safe_video = re.sub(r"[^A-Za-z0-9_-]", "", str(video_id))
    return os.path.join(_ensure_layout(root, slug), "matches", safe_vod, f"{safe_video}.json")


def save_match(root: str, slug: str, manifest: dict[str, Any]) -> str:
    path = _candidate_file(root, slug, str(manifest.get("twitch_vod_ids", [""])[0]), str(manifest.get("youtube_video_id") or ""))
    manifest["schema_version"] = SCHEMA_VERSION
    manifest["updated_at"] = C.utc_now()
    C.write_json(path, manifest)
    return path


def load_match(root: str, slug: str, vod_id: str, video_id: str) -> dict[str, Any] | None:
    return C.read_json(_candidate_file(root, slug, vod_id, video_id), None)


def list_matches(root: str, slug: str, vod_id: str = "") -> list[dict[str, Any]]:
    base = os.path.join(_ensure_layout(root, slug), "matches")
    rows = []
    dirs = [str(vod_id)] if vod_id else sorted(os.listdir(base))
    for vd in dirs:
        d = os.path.join(base, vd)
        if not os.path.isdir(d): continue
        for name in os.listdir(d):
            if not name.endswith(".json"): continue
            rec = C.read_json(os.path.join(d, name), None)
            if isinstance(rec, dict): rows.append(rec)
    return sorted(rows, key=lambda r: (str((r.get("twitch_vod_ids") or [""])[0]), -float(r.get("candidate_score") or 0)))


def _assignment_file(root: str, slug: str, video_id: str) -> str:
    safe_video = re.sub(r"[^A-Za-z0-9_-]", "", str(video_id))
    return os.path.join(_ensure_layout(root, slug), "assignments", f"{safe_video}.json")


def load_assignment(root: str, slug: str, video_id: str) -> dict[str, Any] | None:
    return C.read_json(_assignment_file(root, slug, video_id), None)


def save_assignment(root: str, slug: str, assignment: dict[str, Any]) -> str:
    assignment["schema_version"] = SCHEMA_VERSION
    assignment["policy_version"] = VERIFICATION_POLICY_VERSION
    assignment["updated_at"] = C.utc_now()
    path = _assignment_file(root, slug, str(assignment.get("youtube_video_id") or ""))
    C.write_json(path, assignment)
    return path


def list_assignments(root: str, slug: str) -> list[dict[str, Any]]:
    base = os.path.join(_ensure_layout(root, slug), "assignments")
    rows: list[dict[str, Any]] = []
    for name in os.listdir(base):
        if not name.endswith(".json"):
            continue
        rec = C.read_json(os.path.join(base, name), None)
        if isinstance(rec, dict):
            rows.append(rec)
    rows.sort(key=lambda r: (str(r.get("streamer") or ""), str(r.get("youtube_video_id") or "")))
    return rows


def _fingerprint_signature(fp: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(fp, dict):
        return {}
    return {
        "provider": str(fp.get("provider") or ""),
        "frames": len(fp.get("features") or []),
        "duration_seconds": round(float(fp.get("duration_seconds") or 0.0), 3),
    }


def _current_matcher_engine() -> str:
    return "numpy-exact" if _np is not None else "stdlib-coarse"


def _pair_result_reusable(result: dict[str, Any] | None) -> bool:
    """Return whether an existing pair checkpoint is valid for this runtime.

    Chronology-only exclusions do not depend on the acoustic matcher and can be
    reused forever under the same verification policy. Audio results, however,
    must record the matcher engine. This intentionally invalidates legacy
    stdlib-coarse/engine-less checkpoints once the exact NumPy matcher is active,
    without throwing away the expensive source fingerprints themselves.
    """
    if not isinstance(result, dict):
        return False
    if str(result.get("policy_version") or "") != VERIFICATION_POLICY_VERSION:
        return False
    if str(result.get("state") or "") == "rejected":
        return True
    assessment = ((result.get("audio") or {}).get("assessment") or {})
    audio_state = str(assessment.get("state") or "")
    if audio_state in {"", "not_run"}:
        reason = str(result.get("reason") or assessment.get("reason") or "")
        return reason == "known upload date predates this Twitch VOD"
    return str(result.get("matcher_engine") or "") == _current_matcher_engine()


def _assignment_resolution_terminal(assignment: dict[str, Any] | None) -> bool:
    if not isinstance(assignment, dict):
        return False
    if str(assignment.get("state") or "") == "verified":
        return True
    deep = assignment.get("deep_resolution") or {}
    return (
        isinstance(deep, dict)
        and str(deep.get("policy_version") or "") == DEEP_RESOLUTION_POLICY_VERSION
        and str(deep.get("status") or "") == "completed"
    )


def _assignment_complete_for_vods(assignment: dict[str, Any] | None, vod_ids: Iterable[str]) -> bool:
    if not isinstance(assignment, dict):
        return False
    if str(assignment.get("policy_version") or "") != VERIFICATION_POLICY_VERSION:
        return False
    if str(assignment.get("status") or "") != "completed":
        return False
    if str(assignment.get("matcher_engine") or "") != _current_matcher_engine():
        return False
    evaluated = {str(x) for x in (assignment.get("evaluated_vod_ids") or [])}
    if not set(map(str, vod_ids)).issubset(evaluated):
        return False
    # "Compared every VOD" is not the same as "resolved". Old assignments used
    # status=completed for unmatched/likely rows and therefore got frozen forever.
    # Only a verified result, or a completed deep-resolution pass, is terminal.
    return _assignment_resolution_terminal(assignment)


def generate_candidates(root: str, slug: str, *, streamer: str = "", vod_id: str = "",
                        max_candidates: int = 8, log=None) -> dict[str, Any]:
    vods = list_twitch_vods(root, slug, streamer)
    if vod_id:
        vods = [v for v in vods if v.get("vod_id") == str(vod_id)]
        if not vods: raise C.StudioError(f"Twitch VOD not found in production: {vod_id}")
    created = []
    for vod in vods:
        videos = [v for v in load_index(root, slug, vod["streamer"]) if str(v.get("streamer") or vod["streamer"]) == vod["streamer"]]
        scored = []
        for video in videos:
            if not _channel_allowed_for_video(root, vod["streamer"], video):
                if log:
                    log.write(
                        f"candidate hard gate: skip youtube={video.get('video_id')} "
                        f"channel_id={video.get('channel_id') or 'unknown'} not in configured channel IDs\n"
                    )
                continue
            ds, _ = _date_score(vod, video)
            # Cheap prefilter: only a known and clearly impossible date rejects.
            # Missing date remains neutral and is resolved by later metadata.
            if ds is not None and ds <= 0.02:
                continue
            rec = score_candidate(vod, video, configured_channel=True)
            scored.append((rec["candidate_score"], video, rec))
        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:max(1, int(max_candidates))]
        ambiguous_top = len(top) >= 2 and top[0][0] >= LIKELY_THRESHOLD and top[1][0] >= LIKELY_THRESHOLD and abs(top[0][0] - top[1][0]) <= 0.04
        for rank, (score, video, evidence) in enumerate(top, 1):
            prior = load_match(root, slug, vod["vod_id"], video["video_id"]) or {}
            prior_state = str(prior.get("state") or "")
            prior_global_current = (
                bool(prior.get("global_assignment"))
                and str((prior.get("verification") or {}).get("policy_version") or "") == VERIFICATION_POLICY_VERSION
                and prior_state in MATCH_STATES
            )
            if prior_state in {"verified", "rejected"}:
                state = prior_state
            elif prior_global_current:
                state = prior_state
            elif rank <= 2 and ambiguous_top:
                state = "ambiguous"
            else:
                state = "likely" if score >= LIKELY_THRESHOLD else "candidate"
            if prior_global_current:
                # Candidate generation runs before global assignment on every
                # resolve. Do not replace enriched/date-aware global evidence with
                # the cheaper index snapshot while an assignment is resuming.
                manifest_video = {**video, **dict(prior.get("youtube") or {})}
                manifest_score = float(prior.get("candidate_score") or score)
                manifest_evidence = prior.get("candidate_evidence") or evidence
            else:
                manifest_video = video
                manifest_score = score
                manifest_evidence = evidence
            manifest = {
                **prior,
                "schema_version": SCHEMA_VERSION,
                "youtube_video_id": video["video_id"],
                "youtube": manifest_video,
                "twitch_vod_ids": [vod["vod_id"]],
                "twitch": vod,
                "streamer": vod["streamer"],
                "state": state,
                "candidate_score": manifest_score,
                "candidate_evidence": manifest_evidence,
                "verification": prior.get("verification") or {"mode": "pending", "providers": {"metadata": "complete", "audio": "pending", "transcript": "pending"}, "transcript": {"method": TRANSCRIPT_ALIGNMENT_PROVIDER, "anchors": []}, "audio": {"method": AUDIO_VERIFIER_PROVIDER, "anchors": []}},
                "timeline_segments": prior.get("timeline_segments") or [],
                "download": prior.get("download") or {"status": "not_downloaded", "path": ""},
                "rights_status": "sem_autorizacao_confirmada",
            }
            save_match(root, slug, manifest)
            created.append(manifest)
            if log:
                log.write(f"candidate vod={vod['vod_id']} youtube={video['video_id']} score={score:.3f} state={state}\n")
    return {"vods": len(vods), "candidates": len(created), "matches": created}


def enrich_video_metadata(video: dict[str, Any], *, log=None) -> dict[str, Any]:
    ytdlp = resolve_ytdlp()
    url = str(video.get("url") or f"https://www.youtube.com/watch?v={video.get('video_id','')}")
    cmd = [
        ytdlp, "--dump-single-json", "--skip-download", "--no-playlist",
        *_yt_dlp_runtime_args(), *_yt_dlp_youtube_metadata_args(), *_ffmpeg_location_args(), url,
    ]
    if log: log.write(f"metadata: {_display_cmd(cmd)}\n"); log.flush()
    proc = _run_hidden(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", check=False)
    if proc.returncode != 0:
        raise C.StudioError(f"yt-dlp metadata failed: {proc.stderr[-700:]}")
    try: raw = json.loads(proc.stdout)
    except Exception as exc: raise C.StudioError("yt-dlp returned invalid metadata JSON") from exc
    return {**video, **normalize_ytdlp_entry(raw, {"name": video.get("channel_name"), "channel_id": video.get("channel_id")})}


def _metadata_cache_file(root: str, slug: str, video_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]", "", str(video_id))
    return os.path.join(_ensure_layout(root, slug), "metadata", f"{safe}.json")


def _cache_age_seconds(record: dict[str, Any]) -> float:
    stamp = _parse_date(record.get("fetched_at") or record.get("created_at") or record.get("indexed_at"))
    if not stamp:
        return float("inf")
    return max(0.0, (datetime.now(timezone.utc) - stamp).total_seconds())


def enrich_video_metadata_cached(root: str, slug: str, video: dict[str, Any], *, force: bool = False, log=None) -> dict[str, Any]:
    video_id = str(video.get("video_id") or "")
    if not VIDEO_ID_RE.fullmatch(video_id):
        return enrich_video_metadata(video, log=log)
    path = _metadata_cache_file(root, slug, video_id)
    cached = C.read_json(path, None) if os.path.isfile(path) and not force else None
    if isinstance(cached, dict) and isinstance(cached.get("video"), dict) and _cache_age_seconds(cached) <= METADATA_CACHE_SECONDS:
        merged = {**video, **dict(cached["video"])}
        streamer = str(merged.get("streamer") or "").strip().lower()
        configured_url = str(merged.get("configured_channel_url") or "")
        if streamer and configured_url and CHANNEL_ID_RE.fullmatch(str(merged.get("channel_id") or "")):
            _remember_channel_id(root, streamer, configured_url, str(merged["channel_id"]))
        if log:
            log.write(f"metadata cache hit: youtube/{video_id} age={_cache_age_seconds(cached):.0f}s\n")
            log.flush()
        return merged
    enriched = enrich_video_metadata(video, log=log)
    streamer = str(enriched.get("streamer") or video.get("streamer") or "").strip().lower()
    configured_url = str(enriched.get("configured_channel_url") or video.get("configured_channel_url") or "")
    if streamer and configured_url and CHANNEL_ID_RE.fullmatch(str(enriched.get("channel_id") or "")):
        _remember_channel_id(root, streamer, configured_url, str(enriched["channel_id"]))
    C.write_json(path, {
        "schema_version": SCHEMA_VERSION,
        "provider": "yt-dlp-metadata-v2",
        "video_id": video_id,
        "fetched_at": C.utc_now(),
        "video": enriched,
    })
    return enriched


def _audio_cache_file(root: str, slug: str, vod_id: str) -> str:
    return os.path.join(_ensure_layout(root, slug), "fingerprints", f"twitch-{vod_id}.features.json")


def _analysis_audio_cached(root: str, slug: str, source_kind: str, source_id: str) -> str:
    base = Path(_ensure_layout(root, slug)) / "analysis-audio"
    safe = re.sub(r"[^A-Za-z0-9_-]", "", str(source_id))
    prefix = f"{source_kind}-{safe}."
    rows = [
        str(p) for p in base.iterdir()
        if p.is_file() and p.name.startswith(prefix) and not p.name.endswith((".part", ".ytdl", ".json"))
    ] if base.is_dir() else []
    if not rows:
        return ""
    chosen = max(rows, key=os.path.getmtime)
    try:
        os.utime(chosen, None)  # true LRU: successful reuse refreshes recency
    except OSError:
        pass
    return chosen


def _is_analysis_audio_path(root: str, slug: str, path: str) -> bool:
    if not path:
        return False
    try:
        base = os.path.abspath(os.path.join(_ensure_layout(root, slug), "analysis-audio"))
        candidate = os.path.abspath(path)
        return os.path.commonpath([base, candidate]) == base
    except (ValueError, OSError):
        return False


def _analysis_audio_cache_limit_bytes() -> int:
    raw = str(os.environ.get("CSTUDIO_YOUTUBE_ANALYSIS_CACHE_GB", DEFAULT_ANALYSIS_AUDIO_CACHE_GB) or DEFAULT_ANALYSIS_AUDIO_CACHE_GB)
    try:
        gb = max(0.25, min(100.0, float(raw)))
    except ValueError:
        gb = DEFAULT_ANALYSIS_AUDIO_CACHE_GB
    return int(gb * 1024 * 1024 * 1024)


def _prune_analysis_audio_cache(root: str, slug: str, *, keep: str = "", log=None) -> None:
    base = Path(_ensure_layout(root, slug)) / "analysis-audio"
    if not base.is_dir():
        return
    rows = [p for p in base.iterdir() if p.is_file() and not p.name.endswith((".part", ".ytdl", ".json"))]
    total = sum(p.stat().st_size for p in rows)
    limit = _analysis_audio_cache_limit_bytes()
    keep_abs = os.path.abspath(keep) if keep else ""
    for path in sorted(rows, key=lambda p: p.stat().st_mtime):
        if total <= limit:
            break
        if keep_abs and os.path.abspath(str(path)) == keep_abs:
            continue
        try:
            size = path.stat().st_size
            path.unlink()
            total -= size
            if log:
                log.write(f"analysis audio cache prune: removed={path.name} bytes={size}\n")
                log.flush()
        except OSError:
            continue


def _persist_youtube_analysis_audio(root: str, slug: str, video_id: str, audio_path: str, *, log=None) -> str:
    """Keep the already-downloaded YouTube bestaudio for cheap local clipping.

    Twitch HLS range fetches are already fast in the observed workload, while
    YouTube section seeks were the dominant localized-transcript cost. Persisting
    only YouTube analysis audio avoids a multi-GB Twitch cache and adds no second
    transcode/decode pass. The cache is technical evidence only, never a master.
    """
    if not audio_path or not os.path.isfile(audio_path):
        return ""
    base = Path(_ensure_layout(root, slug)) / "analysis-audio"
    base.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_-]", "", str(video_id))
    suffix = Path(audio_path).suffix or ".audio"
    dest = base / f"youtube-{safe}{suffix}"
    if os.path.abspath(audio_path) != os.path.abspath(str(dest)):
        for old in base.glob(f"youtube-{safe}.*"):
            if old == dest:
                continue
            try:
                old.unlink()
            except OSError:
                pass
        try:
            os.replace(audio_path, dest)
        except OSError:
            shutil.copy2(audio_path, dest)
            try:
                os.remove(audio_path)
            except OSError:
                pass
    if log:
        log.write(f"analysis audio cached: youtube/{video_id} path={dest.name}\n")
        log.flush()
    _prune_analysis_audio_cache(root, slug, keep=str(dest), log=log)
    return str(dest)


def _download_audio(url: str, out_template: str, *, section: tuple[float, float] | None = None, log=None,
                    force_keyframes_at_cuts: bool = True) -> str:
    """Fetch best audio with real-time progress and parallel HLS/DASH fragments.

    Sections remain supported for localized fallback. Full-source audio is used
    for persistent fingerprints; transcript clips may fetch only short ranges.
    """
    ytdlp = resolve_ytdlp()
    cmd = [
        ytdlp, "--no-playlist", "--no-write-info-json", "--no-write-thumbnail",
        "--concurrent-fragments", str(concurrent_fragments()),
        "--newline", "--progress", "--progress-delta", "1",
        "--progress-template",
        "download:[download] %(info.id)s %(progress._percent_str)s %(progress._speed_str)s ETA %(progress._eta_str)s frag %(progress.fragment_index)s/%(progress.fragment_count)s",
        *_yt_dlp_runtime_args(), *_ffmpeg_location_args(),
        "-f", "ba", "-o", out_template,
    ]
    if section:
        start, end = section
        cmd += ["--download-sections", f"*{max(0.0,start):.3f}-{max(start,end):.3f}"]
        if force_keyframes_at_cuts:
            cmd.append("--force-keyframes-at-cuts")
    cmd.append(url)
    if log:
        log.write(f"audio fetch (-N {concurrent_fragments()}): {_display_cmd(cmd)}\n")
        log.flush()
    proc = _popen_hidden(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        encoding="utf-8", errors="replace", bufsize=1,
    )
    tail: list[str] = []
    if proc.stdout is not None:
        for line in proc.stdout:
            clean = line.rstrip("\r\n")
            if not clean:
                continue
            tail.append(clean)
            if len(tail) > 80:
                tail = tail[-80:]
            if log:
                log.write(clean + "\n")
                log.flush()
    rc = proc.wait()
    output_tail = "\n".join(tail)
    if rc != 0:
        raise C.StudioError(f"yt-dlp audio fetch failed with code {rc}: {output_tail[-900:]}")
    prefix = out_template.split("%(", 1)[0]
    parent = os.path.dirname(prefix) or "."
    base = os.path.basename(prefix)
    candidates = []
    for name in os.listdir(parent):
        if name.startswith(base) and not name.endswith((".part", ".ytdl", ".json")):
            candidates.append(os.path.join(parent, name))
    if not candidates:
        raise C.StudioError("yt-dlp completed but no audio file was found")
    return max(candidates, key=os.path.getmtime)

def _frame_feature(samples: tuple[int, ...]) -> list[float]:
    n = len(samples)
    if n < 8: return [0.0, 0.0, 0.0]
    sq = sum(float(s) * float(s) for s in samples) / n
    rms = math.log1p(math.sqrt(sq))
    zero = sum(1 for a, b in zip(samples, samples[1:]) if (a < 0 <= b) or (a >= 0 > b)) / max(1, n - 1)
    lag = 8
    dsq = sum(float(samples[i] - samples[i-lag]) ** 2 for i in range(lag, n)) / max(1, n-lag)
    diff = math.log1p(math.sqrt(dsq))
    return [rms, zero, diff]


def _frame_feature_numpy(data: bytes) -> list[float]:
    """Vectorized equivalent of ``_frame_feature`` for decoded s16le PCM."""
    if _np is None:
        count = len(data) // 2
        return _frame_feature(struct.unpack("<" + "h" * count, data[:count * 2]))
    samples = _np.frombuffer(data, dtype="<i2").astype(_np.float64, copy=False)
    n = int(samples.size)
    if n < 8:
        return [0.0, 0.0, 0.0]
    rms = math.log1p(math.sqrt(float(_np.mean(samples * samples))))
    signs = samples >= 0
    zero = float(_np.count_nonzero(signs[1:] != signs[:-1])) / max(1, n - 1)
    lag = 8
    delta = samples[lag:] - samples[:-lag]
    diff = math.log1p(math.sqrt(float(_np.mean(delta * delta))))
    return [rms, zero, diff]


def extract_audio_features(media_path: str, *, start: float = 0.0, duration: float | None = None) -> list[list[float]]:
    ffmpeg = resolve_ffmpeg()
    cmd = [ffmpeg, "-v", "error"]
    if start > 0: cmd += ["-ss", f"{float(start):.3f}"]
    cmd += ["-i", media_path]
    if duration is not None: cmd += ["-t", f"{float(duration):.3f}"]
    cmd += ["-vn", "-ac", "1", "-ar", str(PCM_RATE), "-f", "s16le", "pipe:1"]
    proc = _popen_hidden(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdout is not None
    bytes_per_frame = int(PCM_RATE * FRAME_SECONDS) * 2
    features = []
    while True:
        data = proc.stdout.read(bytes_per_frame)
        if not data: break
        if len(data) < bytes_per_frame // 2: break
        count = len(data) // 2
        raw = data[:count * 2]
        if _np is not None:
            features.append(_frame_feature_numpy(raw))
        else:
            samples = struct.unpack("<" + "h" * count, raw)
            features.append(_frame_feature(samples))
    stderr = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
    rc = proc.wait()
    if rc != 0:
        raise C.StudioError(f"ffmpeg feature extraction failed: {stderr[-700:]}")
    return features


def _znorm(values: list[float]) -> list[float]:
    if not values: return []
    mean = sum(values) / len(values)
    var = sum((x-mean)**2 for x in values) / len(values)
    sd = math.sqrt(var)
    if sd < 1e-9: return [0.0 for _ in values]
    return [(x-mean)/sd for x in values]


def feature_similarity(query: list[list[float]], target: list[list[float]]) -> float:
    n = min(len(query), len(target))
    if n < 8: return 0.0
    q = query[:n]; t = target[:n]
    sims = []
    for col in range(3):
        qa = _znorm([row[col] for row in q]); ta = _znorm([row[col] for row in t])
        if not qa or not ta: continue
        corr = sum(a*b for a,b in zip(qa,ta)) / len(qa)
        sims.append(max(-1.0, min(1.0, corr)))
    if not sims: return 0.0
    # RMS dynamics carry most temporal identity; zcr/diff add codec-tolerant texture evidence.
    raw = (sims[0] * 0.62 + sims[1] * 0.16 + sims[2] * 0.22)
    return round(max(0.0, min(1.0, (raw + 1.0) / 2.0)), 4)


def _match_feature_window_details_numpy(query: list[list[float]], target: list[list[float]], *,
                                        min_start: int = 0, max_start: int | None = None) -> dict[str, Any]:
    """Exact normalized cross-correlation for all candidate frames.

    The legacy matcher sampled every N frames and refined only around the coarse
    winner. Narrow true peaks could therefore be skipped entirely. NumPy lets us
    evaluate every 0.5 s frame much faster while preserving the same three-feature
    weighted correlation semantics.
    """
    assert _np is not None
    qn = len(query)
    if qn < 8 or len(target) < qn:
        return {"start_frame": 0, "similarity": 0.0, "second_best": 0.0, "peak_margin": 0.0,
                "evaluated": 0, "engine": "numpy-exact"}
    max_valid = len(target) - qn
    lo = max(0, int(min_start))
    hi = max_valid if max_start is None else min(int(max_start), max_valid)
    if hi < lo:
        return {"start_frame": lo, "similarity": 0.0, "second_best": 0.0, "peak_margin": 0.0,
                "evaluated": 0, "engine": "numpy-exact"}

    q = _np.asarray(query, dtype=_np.float32)
    # Include qn-1 look-ahead samples so mode='valid' yields one score per
    # candidate start in [lo, hi].
    t = _np.asarray(target[lo:hi + qn], dtype=_np.float32)
    scores_raw = _np.zeros(hi - lo + 1, dtype=_np.float32)
    weights = (0.62, 0.16, 0.22)
    for col, weight in enumerate(weights):
        qc = q[:, col]
        qmean = float(qc.mean())
        qstd = float(qc.std())
        if qstd < 1e-9:
            continue
        qnorm = (qc - qmean) / qstd
        tc = t[:, col]
        csum = _np.concatenate((_np.array([0.0], dtype=_np.float64), _np.cumsum(tc, dtype=_np.float64)))
        csum2 = _np.concatenate((_np.array([0.0], dtype=_np.float64), _np.cumsum(tc * tc, dtype=_np.float64)))
        sums = csum[qn:] - csum[:-qn]
        sums2 = csum2[qn:] - csum2[:-qn]
        means = sums / qn
        variances = _np.maximum(0.0, sums2 / qn - means * means)
        stds = _np.sqrt(variances)
        dots = _np.correlate(tc, qnorm, mode="valid")
        corr = _np.divide(
            dots,
            qn * stds,
            out=_np.zeros_like(dots, dtype=_np.float64),
            where=stds > 1e-9,
        )
        scores_raw += float(weight) * _np.clip(corr, -1.0, 1.0).astype(_np.float32)

    similarities = _np.clip((scores_raw + 1.0) / 2.0, 0.0, 1.0)
    best_local = int(_np.argmax(similarities))
    best = float(similarities[best_local])
    exclusion = max(1, int(PEAK_EXCLUSION_SECONDS / FRAME_SECONDS))
    mask = _np.ones(similarities.shape[0], dtype=bool)
    mask[max(0, best_local - exclusion + 1):min(len(mask), best_local + exclusion)] = False
    second = float(similarities[mask].max()) if bool(mask.any()) else 0.0
    best = max(0.0, round(best, 4))
    second = max(0.0, round(second, 4))
    return {
        "start_frame": lo + best_local,
        "similarity": best,
        "second_best": second,
        "peak_margin": round(max(0.0, best - second), 4),
        "evaluated": int(similarities.size),
        "engine": "numpy-exact",
    }


def match_feature_window_details(query: list[list[float]], target: list[list[float]], *, step_frames: int = 2,
                                 min_start: int = 0, max_start: int | None = None) -> dict[str, Any]:
    if _np is not None:
        return _match_feature_window_details_numpy(
            query, target, min_start=min_start, max_start=max_start,
        )
    qn = len(query)
    if qn < 8 or len(target) < qn:
        return {"start_frame": 0, "similarity": 0.0, "second_best": 0.0, "peak_margin": 0.0, "evaluated": 0}
    hi = len(target) - qn if max_start is None else min(int(max_start), len(target)-qn)
    lo = max(0, int(min_start))
    if hi < lo:
        return {"start_frame": lo, "similarity": 0.0, "second_best": 0.0, "peak_margin": 0.0, "evaluated": 0}
    step = max(1, int(step_frames))
    scored: list[tuple[float, int]] = []
    best_i = lo; best = -1.0
    for i in range(lo, hi + 1, step):
        score = feature_similarity(query, target[i:i+qn])
        scored.append((score, i))
        if score > best:
            best_i, best = i, score
    # Refine around the coarse winner frame-by-frame.
    lo2 = max(lo, best_i - max(2, step*2)); hi2 = min(hi, best_i + max(2, step*2))
    for i in range(lo2, hi2 + 1):
        score = feature_similarity(query, target[i:i+qn])
        scored.append((score, i))
        if score > best:
            best_i, best = i, score
    exclusion = max(1, int(PEAK_EXCLUSION_SECONDS / FRAME_SECONDS))
    second = max((score for score, frame in scored if abs(frame-best_i) >= exclusion), default=0.0)
    best = max(0.0, round(best, 4))
    second = max(0.0, round(second, 4))
    return {
        "start_frame": best_i, "similarity": best, "second_best": second,
        "peak_margin": round(max(0.0, best-second), 4), "evaluated": len(scored),
        "engine": "stdlib-coarse",
    }


def match_feature_window(query: list[list[float]], target: list[list[float]], *, step_frames: int = 2,
                         min_start: int = 0, max_start: int | None = None) -> tuple[int, float]:
    details = match_feature_window_details(
        query, target, step_frames=step_frames, min_start=min_start, max_start=max_start,
    )
    return int(details["start_frame"]), float(details["similarity"])




def _youtube_audio_cache_file(root: str, slug: str, video_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]", "", str(video_id))
    return os.path.join(_ensure_layout(root, slug), "fingerprints", f"youtube-{safe}.features.json")


def _chromaprint_cache_file(root: str, slug: str, source_kind: str, source_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]", "", str(source_id))
    return os.path.join(_ensure_layout(root, slug), "fingerprints", f"{source_kind}-{safe}.chromaprint.json")


def _normalize_chromaprint_values(value: Any) -> list[int]:
    if isinstance(value, list):
        rows = value
    elif isinstance(value, str):
        rows = [x.strip() for x in value.strip().strip("[]").split(",") if x.strip()]
    else:
        rows = []
    out: list[int] = []
    for item in rows:
        try:
            out.append(int(item) & 0xFFFFFFFF)
        except (TypeError, ValueError):
            continue
    return out


def _build_chromaprint(media_path: str, source_kind: str, source_id: str, *, log=None) -> dict[str, Any] | None:
    fpcalc = resolve_fpcalc(False)
    if not fpcalc or not media_path or not os.path.isfile(media_path):
        return None
    cmd = [fpcalc, "-json", "-raw", media_path]
    if log:
        log.write(f"chromaprint shadow: {_display_cmd(cmd)}\n")
        log.flush()
    proc = _run_hidden(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    if proc.returncode != 0:
        if log:
            log.write(f"chromaprint shadow unavailable: {(proc.stderr or '')[-500:]}\n")
            log.flush()
        return None
    try:
        raw = json.loads(proc.stdout)
    except Exception:
        return None
    values = _normalize_chromaprint_values(raw.get("fingerprint"))
    if not values:
        return None
    try:
        duration = float(raw.get("duration") or 0.0)
    except (TypeError, ValueError):
        duration = 0.0
    frame_seconds = (duration / len(values)) if duration > 0 else 0.1238
    return {
        "schema_version": SCHEMA_VERSION,
        "provider": "chromaprint-fpcalc-shadow-v1",
        "source_kind": source_kind,
        "source_id": str(source_id),
        "created_at": C.utc_now(),
        "duration_seconds": round(duration, 3),
        "frame_seconds": round(frame_seconds, 8),
        "fingerprint": values,
    }


def _ensure_chromaprint(root: str, slug: str, source_kind: str, source_id: str, media_path: str = "", *, force: bool = False, log=None) -> dict[str, Any] | None:
    path = _chromaprint_cache_file(root, slug, source_kind, source_id)
    cached = C.read_json(path, None) if os.path.isfile(path) and not force else None
    if isinstance(cached, dict) and cached.get("provider") == "chromaprint-fpcalc-shadow-v1" and cached.get("fingerprint"):
        return cached
    built = _build_chromaprint(media_path, source_kind, source_id, log=log)
    if built:
        C.write_json(path, built)
    return built


def _chromaprint_similarity(query: list[int], target: list[int], *, stride: int = CHROMAPRINT_SAMPLE_STRIDE) -> float:
    n = min(len(query), len(target))
    if n < 12:
        return 0.0
    step = max(1, int(stride))
    bits = 0
    count = 0
    for i in range(0, n, step):
        bits += ((int(query[i]) ^ int(target[i])) & 0xFFFFFFFF).bit_count()
        count += 1
    if not count:
        return 0.0
    return round(max(0.0, min(1.0, 1.0 - bits / (32.0 * count))), 4)


def _match_chromaprint_window(query: list[int], target: list[int], *, min_start: int = 0, max_start: int | None = None) -> tuple[int, float]:
    qn = len(query)
    if qn < 12 or len(target) < qn:
        return 0, 0.0
    lo = max(0, int(min_start))
    hi = len(target)-qn if max_start is None else min(len(target)-qn, int(max_start))
    if hi < lo:
        return lo, 0.0
    coarse = max(2, CHROMAPRINT_SAMPLE_STRIDE * 2)
    best_i = lo
    best = -1.0
    for i in range(lo, hi+1, coarse):
        score = _chromaprint_similarity(query, target[i:i+qn])
        if score > best:
            best_i, best = i, score
    for i in range(max(lo, best_i-coarse), min(hi, best_i+coarse)+1):
        score = _chromaprint_similarity(query, target[i:i+qn], stride=2)
        if score > best:
            best_i, best = i, score
    return best_i, max(0.0, round(best, 4))


def _chromaprint_shadow_anchors(duration: float, youtube_cp: dict[str, Any] | None, twitch_cp: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(youtube_cp, dict) or not isinstance(twitch_cp, dict):
        return {"provider": "chromaprint-fpcalc-shadow-v1", "status": "unavailable", "anchors": []}
    yf = _normalize_chromaprint_values(youtube_cp.get("fingerprint"))
    tf = _normalize_chromaprint_values(twitch_cp.get("fingerprint"))
    try:
        ystep = float(youtube_cp.get("frame_seconds") or 0.1238)
        tstep = float(twitch_cp.get("frame_seconds") or 0.1238)
    except (TypeError, ValueError):
        return {"provider": "chromaprint-fpcalc-shadow-v1", "status": "invalid", "anchors": []}
    if not yf or not tf or ystep <= 0 or tstep <= 0:
        return {"provider": "chromaprint-fpcalc-shadow-v1", "status": "unavailable", "anchors": []}
    anchors: list[dict[str, Any]] = []
    last_twitch = 0
    for idx, yt_start in enumerate(_anchor_times(duration)):
        y0 = max(0, int(yt_start/ystep))
        qn = max(12, int(ANCHOR_SECONDS/ystep))
        query = yf[y0:y0+qn]
        if len(query) < 12:
            continue
        if idx == 0 or not anchors:
            frame, score = _match_chromaprint_window(query, tf)
        else:
            delta = yt_start - float(anchors[-1]["youtube_time"])
            predicted = last_twitch + int(max(0.0, delta)/tstep)
            lo = max(0, predicted-int(AUDIO_SEARCH_BACKTRACK_SECONDS/tstep))
            hi = min(max(0, len(tf)-len(query)), predicted+int(AUDIO_SEARCH_FORWARD_SECONDS/tstep))
            frame, score = _match_chromaprint_window(query, tf, min_start=lo, max_start=hi)
            if score < 0.70:
                frame, score = _match_chromaprint_window(query, tf, min_start=max(0, last_twitch))
        last_twitch = frame
        anchors.append({
            "youtube_time": round(yt_start, 3),
            "twitch_time": round(frame*tstep, 3),
            "similarity": score,
        })
    scores = [float(a.get("similarity") or 0.0) for a in anchors]
    return {
        "provider": "chromaprint-fpcalc-shadow-v1",
        "status": "complete" if anchors else "unavailable",
        "anchors": anchors,
        "median_similarity": round(statistics.median(scores), 4) if scores else 0.0,
        "authority": False,
    }


def _transcript_file(root: str, slug: str, source_kind: str, source_id: str) -> str:
    if source_kind not in {"twitch", "youtube"}:
        raise C.StudioError("invalid transcript source kind")
    safe = re.sub(r"[^A-Za-z0-9_-]", "", str(source_id))
    return os.path.join(_ensure_layout(root, slug), "transcripts", source_kind, f"{safe}.json")


def _caption_cache_file(root: str, slug: str, video_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]", "", str(video_id))
    return os.path.join(_ensure_layout(root, slug), "captions", f"{safe}.captions.json")


def _parse_vtt_time(value: str) -> float:
    text = str(value or "").strip().split()[0]
    parts = text.replace(",", ".").split(":")
    try:
        if len(parts) == 3:
            h, m, sec = parts
            return float(h) * 3600 + float(m) * 60 + float(sec)
        if len(parts) == 2:
            m, sec = parts
            return float(m) * 60 + float(sec)
    except ValueError:
        return 0.0
    return 0.0


def _parse_webvtt(path: str, *, video_id: str, language: str = "") -> dict[str, Any]:
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    segments: list[dict[str, Any]] = []
    i = 0
    previous_full = ""
    while i < len(lines):
        line = lines[i].strip()
        if "-->" not in line:
            i += 1
            continue
        left, right = line.split("-->", 1)
        start = _parse_vtt_time(left)
        end = _parse_vtt_time(right)
        i += 1
        text_lines: list[str] = []
        while i < len(lines) and lines[i].strip():
            text_lines.append(lines[i].strip())
            i += 1
        raw_text = " ".join(text_lines)
        clean_full = html.unescape(re.sub(r"<[^>]+>", "", raw_text))
        clean_full = re.sub(r"\s+", " ", clean_full).strip()
        if not clean_full or clean_full == previous_full or end <= start:
            continue
        # YouTube auto-captions may emit cumulative cues. Compare against the
        # previous *full* cue, not the previously emitted suffix, otherwise the
        # third and later cumulative cues can duplicate text.
        clean = clean_full
        if previous_full and clean_full.startswith(previous_full) and len(clean_full) > len(previous_full):
            clean = clean_full[len(previous_full):].strip() or clean_full
        previous_full = clean_full
        segments.append({"start": round(start, 3), "end": round(end, 3), "text": clean, "words": []})
    full_text = " ".join(str(x.get("text") or "") for x in segments).strip()
    return {
        "schema_version": TRANSCRIPT_SCHEMA_VERSION,
        "provider": "yt-dlp-youtube-captions-v1",
        "source_kind": "youtube",
        "source_id": str(video_id),
        "language": language or "unknown",
        "timestamp_mode": "segment",
        "scope": "full",
        "created_at": C.utc_now(),
        "duration_seconds": max((float(x.get("end") or 0) for x in segments), default=0.0),
        "segment_count": len(segments),
        "text": full_text,
        "segments": segments,
        "word_count": len(full_text.split()),
        "untrusted": True,
        "injection_findings": scan_text(full_text[:20000]),
    }


def _youtube_caption_transcript(root: str, slug: str, video_id: str, url: str, *, streamer: str = "", log=None, force: bool = False) -> dict[str, Any] | None:
    """Return cached YouTube captions, preferring them over audio transcription.

    A negative result is cached as well so borderline candidates do not repeatedly
    query the same video. This is evidence only; it never clears rights or creates
    VERIFIED without the acoustic policy.
    """
    cache_path = _caption_cache_file(root, slug, video_id)
    cached = C.read_json(cache_path, None) if os.path.isfile(cache_path) and not force else None
    if isinstance(cached, dict) and _cache_age_seconds(cached) <= CAPTION_CACHE_SECONDS:
        transcript = cached.get("transcript")
        if log:
            log.write(
                f"caption cache hit: youtube/{video_id} status={cached.get('status') or 'unknown'} "
                f"age={_cache_age_seconds(cached):.0f}s\n"
            )
            log.flush()
        return dict(transcript) if isinstance(transcript, dict) and transcript.get("segments") else None

    language = whisper_language(root, streamer) or "auto"
    # With no language hint we cannot reliably choose among YouTube's original,
    # translated and auto-generated tracks. Skip this optimization rather than
    # compare text in the wrong language; Whisper auto-detection remains fallback.
    if language == "auto":
        record = {
            "schema_version": SCHEMA_VERSION,
            "provider": "yt-dlp-youtube-captions-v1",
            "video_id": video_id,
            "fetched_at": C.utc_now(),
            "status": "skipped_auto_language",
            "language_requested": "auto",
            "return_code": None,
            "error": "caption lookup skipped because transcription language is auto",
            "transcript": None,
        }
        C.write_json(cache_path, record)
        return None
    ytdlp = resolve_ytdlp()
    sub_pattern = f"{language}.*, {language}".replace(" ", "")
    base = os.path.join(_ensure_layout(root, slug), "captions")
    safe = re.sub(r"[^A-Za-z0-9_-]", "", str(video_id))
    out_template = os.path.join(base, f"{safe}.%(ext)s")
    # Clear stale temporary subtitle files while preserving the normalized cache.
    for stale in Path(base).glob(f"{safe}.*.vtt"):
        try:
            stale.unlink()
        except OSError:
            pass
    cmd = [
        ytdlp, "--skip-download", "--no-playlist", "--ignore-errors",
        "--write-subs", "--write-auto-subs", "--sub-langs", sub_pattern, "--sub-format", "vtt",
        "--no-write-info-json", *_yt_dlp_runtime_args(), *_yt_dlp_youtube_metadata_args(),
        "-o", out_template, url,
    ]
    if log:
        log.write(f"youtube captions: {_display_cmd(cmd)}\n")
        log.flush()
    proc = _run_hidden(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    files = sorted(Path(base).glob(f"{safe}.*.vtt"), key=lambda x: (f".{language}.vtt" not in x.name, len(x.name)))
    transcript: dict[str, Any] | None = None
    if files:
        chosen = files[0]
        lang_match = re.match(re.escape(safe) + r"\.(.+)\.vtt$", chosen.name)
        detected_language = lang_match.group(1) if lang_match else language
        try:
            parsed = _parse_webvtt(str(chosen), video_id=video_id, language=detected_language)
            if parsed.get("segments"):
                transcript = parsed
        finally:
            for item in files:
                try:
                    item.unlink()
                except OSError:
                    pass
    record = {
        "schema_version": SCHEMA_VERSION,
        "provider": "yt-dlp-youtube-captions-v1",
        "video_id": video_id,
        "fetched_at": C.utc_now(),
        "status": "available" if transcript else "unavailable",
        "language_requested": language,
        "return_code": proc.returncode,
        "error": (proc.stderr or "")[-900:] if proc.returncode else "",
        "transcript": transcript,
    }
    C.write_json(cache_path, record)
    if log:
        log.write(
            f"youtube captions result: video={video_id} status={record['status']} "
            f"segments={len((transcript or {}).get('segments') or [])}\n"
        )
        log.flush()
    return transcript


def resolve_whisper_python(root: str = "", required: bool = False) -> str:
    """Resolve the Python interpreter belonging to the discovered Whisper venv.

    Calling ``python -m whisper`` is more diagnosable on Windows than the tiny
    console-script launcher and guarantees we use the packages/CUDA runtime from
    the user's Whisper environment.
    """
    explicit = str(os.environ.get("CSTUDIO_WHISPER_PYTHON") or "").strip()
    if explicit:
        if os.path.isfile(explicit):
            return explicit
        if required:
            raise C.StudioError(f"Whisper Python not found: {explicit}")
        return ""
    whisper = resolve_whisper(root, False)
    candidates: list[str] = []
    if whisper:
        parent = os.path.dirname(whisper)
        candidates.extend([os.path.join(parent, "python.exe"), os.path.join(parent, "python")])
    for home in _candidate_whisper_homes(root):
        candidates.extend([
            os.path.join(home, ".venv", "Scripts", "python.exe"),
            os.path.join(home, ".venv", "bin", "python"),
        ])
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    if required:
        raise C.StudioError("Whisper Python runtime not found")
    return ""


def _whisper_model_cli(root: str) -> tuple[str, str]:
    """Return (model_arg, model_dir) while preserving official alignment metadata.

    A local official ``large-v3-turbo.pt`` should be addressed as model ``turbo``
    with its parent directory as ``--model_dir``. OpenAI Whisper then reuses the
    local checkpoint and recognizes it as the official model instead of treating
    it as an anonymous custom checkpoint.
    """
    model = resolve_whisper_model(root)
    if os.path.isfile(model):
        base = os.path.basename(model).lower()
        aliases = {
            "large-v3-turbo.pt": "turbo",
            "large-v3.pt": "large-v3",
            "large-v2.pt": "large-v2",
            "large-v1.pt": "large-v1",
        }
        if base in aliases:
            return aliases[base], os.path.dirname(model)
    return model, ""


def _whisper_preflight(root: str, log=None) -> dict[str, Any]:
    python = resolve_whisper_python(root, required=True)
    with _LOCK:
        cached = _WHISPER_PREFLIGHTS.get(python)
    if cached:
        return dict(cached)
    probe = (
        "import json,torch,whisper; "
        "print(json.dumps({'torch':torch.__version__,'whisper':getattr(whisper,'__version__','unknown'),"
        "'cuda_available':bool(torch.cuda.is_available()),"
        "'cuda_device':(torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')}))"
    )
    proc = _run_hidden(
        [python, "-c", probe], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", env=_media_subprocess_env(), timeout=30,
    )
    output = (proc.stdout or "").strip()
    if proc.returncode != 0:
        raise C.StudioError(f"Whisper runtime preflight failed with code {proc.returncode}: {output[-1200:]}")
    try:
        data = json.loads(output.splitlines()[-1])
    except Exception as exc:
        raise C.StudioError(f"Whisper runtime preflight returned invalid output: {output[-1200:]}") from exc
    configured = whisper_device(root)
    data["effective_device"] = configured or ("cuda" if data.get("cuda_available") else "cpu")
    with _LOCK:
        _WHISPER_PREFLIGHTS[python] = dict(data)
    if log:
        log.write(
            "whisper preflight: "
            f"python={python} torch={data.get('torch')} whisper={data.get('whisper')} "
            f"cuda={data.get('cuda_available')} gpu={data.get('cuda_device') or 'none'} "
            f"device={data.get('effective_device')}\n"
        )
        log.flush()
    return data


def build_whisper_command(root: str, media_path: str | list[str], output_dir: str, *, device: str = "", streamer: str = "",
                          clip_timestamps: list[tuple[float, float]] | None = None) -> list[str]:
    python = resolve_whisper_python(root, required=False)
    whisper = resolve_whisper(root, required=True)
    model, model_dir = _whisper_model_cli(root)
    media_paths = [str(media_path)] if isinstance(media_path, (str, os.PathLike)) else [str(x) for x in media_path]
    cmd = ([python, "-m", "whisper"] if python else [whisper]) + media_paths + [
        "--model", model,
        "--output_dir", output_dir,
        "--output_format", "json",
        "--verbose", "False",
        "--task", "transcribe",
        # Matching benefits from independent windows more than editorial prose
        # continuity. Whisper defaults this to True, which can propagate a bad
        # decode across a long VOD and get stuck in repetition loops.
        "--condition_on_previous_text", "False",
        # Do not enable word_timestamps for full multi-hour sources. Segment
        # timestamps are enough to locate text anchors, while word-level DTW can
        # fall back to very slow kernels when Triton/CUDA tooling is unavailable.
    ]
    if clip_timestamps:
        points: list[str] = []
        for start, end in clip_timestamps:
            points.extend([f"{max(0.0, float(start)):.3f}", f"{max(float(start), float(end)):.3f}"])
        cmd += ["--clip_timestamps", ",".join(points)]
    if model_dir:
        cmd += ["--model_dir", model_dir]
    effective_device = device or whisper_device(root)
    language = whisper_language(root, streamer)
    if effective_device:
        cmd += ["--device", effective_device]
    if language:
        cmd += ["--language", language]
    return cmd


def _quality_text(text: Any) -> str:
    value = unicodedata.normalize("NFKC", str(text or "")).casefold()
    value = re.sub(r"[^\w']+", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


def assess_transcript_quality(transcript: Any) -> dict[str, Any]:
    """Assess whether a transcript is useful/safe as a matching reference.

    This gate is intentionally conservative: a transcript rejected here simply
    falls back to the existing audiovisual verifier. It is not a judgement of
    editorial transcript quality and sparse/silent material is only rejected
    when it is too weak to provide reliable text anchors.
    """
    segments = list(transcript.get("segments") or []) if isinstance(transcript, dict) else []
    normalized: list[str] = []
    max_end = 0.0
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        normalized.append(_quality_text(seg.get("text")))
        try:
            max_end = max(max_end, float(seg.get("end") or 0))
        except (TypeError, ValueError):
            pass

    segment_count = len(normalized)
    nonempty = [text for text in normalized if text]
    nonempty_count = len(nonempty)
    counts = Counter(nonempty)
    dominant_text, dominant_count = counts.most_common(1)[0] if counts else ("", 0)
    dominant_ratio = (dominant_count / nonempty_count) if nonempty_count else 0.0
    unique_count = len(counts)
    unique_ratio = (unique_count / nonempty_count) if nonempty_count else 0.0
    nonempty_ratio = (nonempty_count / segment_count) if segment_count else 0.0
    empty_ratio = 1.0 - nonempty_ratio if segment_count else 1.0

    repeat_pairs = sum(1 for prev, cur in zip(nonempty, nonempty[1:]) if prev == cur)
    consecutive_repeat_ratio = repeat_pairs / max(1, nonempty_count - 1)
    tokens = re.findall(r"\w+", " ".join(nonempty), flags=re.UNICODE)
    lexical_diversity = (len(set(tokens)) / len(tokens)) if tokens else 0.0
    useful_chars = sum(len(text) for text in nonempty)
    try:
        processed_duration = float(transcript.get("processed_duration_seconds") or 0) if isinstance(transcript, dict) else 0.0
    except (TypeError, ValueError):
        processed_duration = 0.0
    try:
        declared_duration = float(transcript.get("duration_seconds") or 0) if isinstance(transcript, dict) else 0.0
    except (TypeError, ValueError):
        declared_duration = 0.0
    # Localized transcripts retain absolute source timestamps, so max_end can be
    # hours into the source even though only a few minutes were actually decoded.
    duration_seconds = processed_duration if processed_duration > 0 else max(max_end, declared_duration)
    useful_chars_per_hour = useful_chars * 3600.0 / duration_seconds if duration_seconds > 0 else float(useful_chars)

    metrics = {
        "segment_count": segment_count,
        "nonempty_segments": nonempty_count,
        "nonempty_ratio": round(nonempty_ratio, 4),
        "empty_ratio": round(empty_ratio, 4),
        "unique_normalized_segments": unique_count,
        "unique_ratio": round(unique_ratio, 4),
        "dominant_text": dominant_text[:160],
        "dominant_text_count": dominant_count,
        "dominant_text_ratio": round(dominant_ratio, 4),
        "consecutive_repeat_ratio": round(consecutive_repeat_ratio, 4),
        "lexical_diversity": round(lexical_diversity, 4),
        "useful_chars": useful_chars,
        "useful_chars_per_hour": round(useful_chars_per_hour, 1),
        "duration_seconds": round(duration_seconds, 3),
    }

    reasons: list[str] = []
    classification = "usable"
    dominant_is_short = len(dominant_text) <= 80 and len(dominant_text.split()) <= 12
    if nonempty_count == 0:
        reasons.append("no_usable_text")
        classification = "insufficient_text"
    if nonempty_count >= 20 and dominant_is_short and dominant_ratio >= 0.70:
        reasons.append("short_segment_dominates_transcript")
        classification = "hallucination_loop"
    if nonempty_count >= 40 and consecutive_repeat_ratio >= 0.60 and unique_ratio <= 0.15:
        reasons.append("consecutive_repetition_collapse")
        classification = "hallucination_loop"
    if duration_seconds >= 1800 and nonempty_count >= 50 and lexical_diversity <= 0.02 and unique_ratio <= 0.10:
        reasons.append("lexical_diversity_collapse")
        classification = "hallucination_loop"
    if duration_seconds >= 3600 and useful_chars_per_hour < 80 and nonempty_ratio < 0.05:
        reasons.append("too_little_text_for_matching_duration")
        if classification == "usable":
            classification = "insufficient_text"
    if segment_count >= 100 and empty_ratio >= 0.95 and useful_chars_per_hour < 300:
        reasons.append("excessive_empty_segments")
        if classification == "usable":
            classification = "insufficient_text"

    return {
        "profile": TRANSCRIPT_QUALITY_PROFILE,
        "state": "invalid" if reasons else "valid",
        "classification": classification,
        "reasons": reasons,
        "metrics": metrics,
    }


def _run_openai_whisper(root: str, media_path: str, *, source_kind: str, source_id: str, streamer: str = "", log=None,
                        clip_timestamps: list[tuple[float, float]] | None = None) -> dict[str, Any]:
    if not transcript_enabled(root):
        raise C.StudioError("transcription provider is disabled")
    if not resolve_whisper(root, False):
        raise C.StudioError("Whisper runtime not found")
    temp_out = tempfile.mkdtemp(prefix="cstudio-whisper-")
    # A system temp directory avoids filename collisions and is deleted immediately.
    try:
        preflight = _whisper_preflight(root, log=log)
        cmd = build_whisper_command(
            root, media_path, temp_out, device=str(preflight.get("effective_device") or ""),
            streamer=streamer, clip_timestamps=clip_timestamps,
        )
        if log:
            log.write(
                f"whisper profile: streamer={streamer or 'unknown'} "
                f"language={whisper_language(root, streamer) or 'auto'} timestamps=segment "
                f"condition_on_previous_text=false profile={TRANSCRIPT_DECODING_PROFILE} "
                f"scope={'localized' if clip_timestamps else 'full'} "
                f"processed_seconds={sum(max(0.0, end-start) for start, end in (clip_timestamps or [])):.1f} "
                f"model={_whisper_model_cli(root)[0]} device={preflight.get('effective_device') or 'auto'}\n"
            )
            log.write(f"transcribe {source_kind}/{source_id}: {_display_cmd(cmd)}\n")
            log.flush()
        child_env = _media_subprocess_env()
        if log:
            log.write(
                f"whisper media tools: ffmpeg={resolve_ffmpeg(False) or 'missing'} "
                f"ffprobe={resolve_ffprobe(False) or 'missing (not required by Whisper)'}\n"
            )
            log.flush()
        proc = _popen_hidden(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding="utf-8", errors="replace", bufsize=1, env=child_env,
        )
        tail: list[str] = []
        if proc.stdout is not None:
            for line in proc.stdout:
                clean = line.rstrip("\r\n")
                if not clean:
                    continue
                tail.append(clean)
                if len(tail) > 100:
                    tail = tail[-100:]
                if log:
                    log.write("[whisper] " + clean + "\n")
                    log.flush()
        rc = proc.wait()
        if rc != 0:
            raise C.StudioError(f"Whisper transcription failed with code {rc}: {' | '.join(tail[-8:])}")
        files = sorted(Path(temp_out).glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
        if not files:
            raise C.StudioError("Whisper completed but produced no JSON transcript")
        raw = json.loads(files[0].read_text(encoding="utf-8"))
    finally:
        shutil.rmtree(temp_out, ignore_errors=True)
    transcript = _normalize_whisper_transcript(
        raw, source_kind=source_kind, source_id=source_id, root=root, streamer=streamer,
        processed_duration_seconds=(sum(max(0.0, end-start) for start, end in clip_timestamps) if clip_timestamps else None),
        scope=("localized" if clip_timestamps else "full"),
    )
    quality = transcript.get("quality") or {}
    if log:
        metrics = quality.get("metrics") or {}
        log.write(
            f"transcript quality: state={quality.get('state')} classification={quality.get('classification')} "
            f"segments={metrics.get('segment_count', 0)} unique_ratio={metrics.get('unique_ratio', 0)} "
            f"dominant_ratio={metrics.get('dominant_text_ratio', 0)} "
            f"repeat_ratio={metrics.get('consecutive_repeat_ratio', 0)} "
            f"chars_per_hour={metrics.get('useful_chars_per_hour', 0)}\n"
        )
        log.flush()
    if quality.get("state") != "valid":
        reason = quality.get("classification") or "invalid"
        details = ", ".join(quality.get("reasons") or []) or "quality gate failed"
        raise _TranscriptContentError(f"Whisper transcript rejected by quality gate ({reason}): {details}")
    return transcript



def _run_faster_whisper_inputs(root: str, inputs: list[dict[str, Any]], *, source_kind: str, source_id: str,
                               streamer: str = "", log=None, scope: str = "localized") -> dict[str, Any]:
    """Run one isolated CTranslate2 model load across one or more input clips."""
    if not transcript_enabled(root):
        raise C.StudioError("transcription provider is disabled")
    preflight = _faster_whisper_preflight(root, log=log)
    python = resolve_whisper_python(root, required=True)
    runner = str(Path(__file__).with_name("faster_whisper_runner.py"))
    if not os.path.isfile(runner):
        raise C.StudioError(f"faster-whisper runner missing: {runner}")

    normalized_inputs: list[dict[str, Any]] = []
    processed_seconds = 0.0
    for item in inputs:
        path = str(item.get("path") or "")
        if not path or not os.path.isfile(path):
            raise C.StudioError(f"faster-whisper input missing: {path or '<empty>'}")
        ranges = [(float(a), float(b)) for a, b in list(item.get("ranges") or []) if float(b) > float(a)]
        duration = max(0.0, float(item.get("duration") or 0.0))
        if ranges:
            processed_seconds += sum(max(0.0, b - a) for a, b in ranges)
        else:
            processed_seconds += duration
        normalized_inputs.append({
            "path": path,
            "offset": float(item.get("offset") or 0.0),
            "duration": duration,
            "ranges": [[round(a, 3), round(b, 3)] for a, b in ranges],
        })

    temp_out = tempfile.mkdtemp(prefix="cstudio-faster-whisper-")
    spec_path = os.path.join(temp_out, "spec.json")
    output_path = os.path.join(temp_out, "transcript.json")
    spec = {
        "model": str(preflight.get("model") or resolve_faster_whisper_model(root, required=True)),
        "device": str(preflight.get("effective_device") or "cuda"),
        "compute_type": str(preflight.get("compute_type") or faster_whisper_compute_type(root)),
        "batch_size": int(preflight.get("batch_size") or faster_whisper_batch_size(root)),
        "beam_size": 5,
        "language": whisper_language(root, streamer),
        "inputs": normalized_inputs,
    }
    C.write_json(spec_path, spec)
    cmd = [python, runner, "--spec", spec_path, "--output", output_path]
    try:
        if log:
            log.write(
                f"faster-whisper profile: streamer={streamer or 'unknown'} "
                f"language={whisper_language(root, streamer) or 'auto'} timestamps=segment "
                f"condition_on_previous_text=false scope={scope} processed_seconds={processed_seconds:.1f} "
                f"model={os.path.basename(spec['model'])} device={spec['device']} compute={spec['compute_type']} "
                f"batch={spec['batch_size']} beam={spec['beam_size']} vad={'on' if not any(x['ranges'] for x in normalized_inputs) else 'clip-ranges'}\n"
            )
            log.write(f"transcribe {source_kind}/{source_id}: {_display_cmd(cmd)}\n")
            log.flush()
        proc = _popen_hidden(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding="utf-8", errors="replace", bufsize=1, env=_faster_whisper_subprocess_env(root),
        )
        tail: list[str] = []
        if proc.stdout is not None:
            for line in proc.stdout:
                clean = line.rstrip("\r\n")
                if not clean:
                    continue
                tail.append(clean)
                if len(tail) > 120:
                    tail = tail[-120:]
                if log:
                    log.write("[faster-whisper] " + clean + "\n")
                    log.flush()
        rc = proc.wait()
        if rc != 0:
            error = f"faster-whisper transcription failed with code {rc}: {' | '.join(tail[-10:])}"
            with _LOCK:
                _FASTER_WHISPER_FAILURES[_faster_failure_key(root)] = error[:1600]
            raise C.StudioError(error)
        if not os.path.isfile(output_path):
            raise C.StudioError("faster-whisper completed but produced no transcript JSON")
        raw = json.loads(Path(output_path).read_text(encoding="utf-8"))
        backend = dict(raw.get("backend") or {})
        transcript = _normalize_whisper_transcript(
            raw, source_kind=source_kind, source_id=source_id, root=root, streamer=streamer,
            processed_duration_seconds=(float(raw.get("processed_duration_seconds") or processed_seconds) or None),
            scope=scope, provider=TRANSCRIPT_PROVIDER_FASTER, model_override=spec["model"],
            decoding_profile_extra={
                "backend": "faster-whisper",
                "faster_whisper": backend.get("faster_whisper") or preflight.get("faster_whisper") or "unknown",
                "ctranslate2": backend.get("ctranslate2") or preflight.get("ctranslate2") or "unknown",
                "compute_type": spec["compute_type"],
                "batch_size": spec["batch_size"],
                "beam_size": spec["beam_size"],
                "vad_filter": not any(x["ranges"] for x in normalized_inputs),
                "without_timestamps": True,
            },
        )
        quality = transcript.get("quality") or {}
        if log:
            metrics = quality.get("metrics") or {}
            log.write(
                f"transcript quality: backend=faster-whisper state={quality.get('state')} "
                f"classification={quality.get('classification')} segments={metrics.get('segment_count', 0)} "
                f"unique_ratio={metrics.get('unique_ratio', 0)} dominant_ratio={metrics.get('dominant_text_ratio', 0)} "
                f"repeat_ratio={metrics.get('consecutive_repeat_ratio', 0)} chars_per_hour={metrics.get('useful_chars_per_hour', 0)}\n"
            )
            log.flush()
        if quality.get("state") != "valid":
            reason = quality.get("classification") or "invalid"
            details = ", ".join(quality.get("reasons") or []) or "quality gate failed"
            raise _TranscriptContentError(f"faster-whisper transcript rejected by quality gate ({reason}): {details}")
        with _LOCK:
            _FASTER_WHISPER_FAILURES.pop(_faster_failure_key(root), None)
        return transcript
    finally:
        shutil.rmtree(temp_out, ignore_errors=True)


def _run_faster_whisper(root: str, media_path: str, *, source_kind: str, source_id: str, streamer: str = "", log=None,
                        clip_timestamps: list[tuple[float, float]] | None = None) -> dict[str, Any]:
    return _run_faster_whisper_inputs(
        root,
        [{"path": media_path, "ranges": list(clip_timestamps or [])}],
        source_kind=source_kind, source_id=source_id, streamer=streamer, log=log,
        scope=("localized" if clip_timestamps else "full"),
    )


def _run_whisper(root: str, media_path: str, *, source_kind: str, source_id: str, streamer: str = "", log=None,
                 clip_timestamps: list[tuple[float, float]] | None = None) -> dict[str, Any]:
    """Dispatch to faster-whisper first in auto mode, with OpenAI as fallback."""
    backend = transcription_backend(root)
    if backend == "faster-whisper":
        try:
            return _run_faster_whisper(
                root, media_path, source_kind=source_kind, source_id=source_id,
                streamer=streamer, log=log, clip_timestamps=clip_timestamps,
            )
        except _TranscriptContentError:
            raise
        except Exception as exc:
            with _LOCK:
                _FASTER_WHISPER_FAILURES[_faster_failure_key(root)] = str(exc)[:1600]
            if resolve_whisper(root, False):
                if log:
                    log.write(f"faster-whisper failed; falling back to OpenAI Whisper for this source: {exc}\n")
                    log.flush()
                return _run_openai_whisper(
                    root, media_path, source_kind=source_kind, source_id=source_id,
                    streamer=streamer, log=log, clip_timestamps=clip_timestamps,
                )
            raise
    if backend == "openai-whisper":
        return _run_openai_whisper(
            root, media_path, source_kind=source_kind, source_id=source_id,
            streamer=streamer, log=log, clip_timestamps=clip_timestamps,
        )
    raise C.StudioError("no transcription runtime available")


def _normalize_whisper_transcript(raw: dict[str, Any], *, source_kind: str, source_id: str, root: str, streamer: str = "",
                                  processed_duration_seconds: float | None = None, scope: str = "full",
                                  provider: str = TRANSCRIPT_PROVIDER, model_override: str = "",
                                  decoding_profile_extra: dict[str, Any] | None = None) -> dict[str, Any]:
    segments = []
    word_count = 0
    for seg in list(raw.get("segments") or []):
        if not isinstance(seg, dict):
            continue
        words = []
        for word in list(seg.get("words") or []):
            if not isinstance(word, dict):
                continue
            token = str(word.get("word") or "")
            try:
                start = float(word.get("start"))
                end = float(word.get("end"))
            except (TypeError, ValueError):
                continue
            words.append({
                "word": token,
                "start": round(start, 3),
                "end": round(end, 3),
                "probability": round(float(word.get("probability") or 0), 4),
            })
        text = _safe_text(seg.get("text"), 4000)
        try:
            start = float(seg.get("start") or 0)
            end = float(seg.get("end") or start)
        except (TypeError, ValueError):
            start = 0.0; end = 0.0
        segments.append({"start": round(start, 3), "end": round(end, 3), "text": text, "words": words})
        word_count += len(words) if words else len(text.split())
    full_text = _safe_text(raw.get("text"), 2_000_000)
    findings = scan_text(full_text[:20000])
    duration_seconds = max((float(seg.get("end") or 0) for seg in segments), default=0.0)
    record = {
        "schema_version": TRANSCRIPT_SCHEMA_VERSION,
        "provider": provider,
        "source_kind": source_kind,
        "source_id": str(source_id),
        "model": model_override or resolve_whisper_model(root),
        "device": whisper_device(root) or "auto",
        "language": str(raw.get("language") or whisper_language(root, streamer) or "auto"),
        "language_requested": whisper_language(root, streamer) or "auto",
        "streamer": str(streamer or ""),
        "timestamp_mode": "segment",
        "scope": scope,
        "processed_duration_seconds": round(float(processed_duration_seconds if processed_duration_seconds is not None else duration_seconds), 3),
        "decoding_profile": {
            "name": TRANSCRIPT_DECODING_PROFILE,
            "condition_on_previous_text": False,
            "word_timestamps": False,
            **(decoding_profile_extra or {}),
        },
        "created_at": C.utc_now(),
        "duration_seconds": round(duration_seconds, 3),
        "segment_count": len(segments),
        "text": full_text,
        "segments": segments,
        "word_count": word_count,
        "untrusted": True,
        "injection_findings": findings,
    }
    record["quality"] = assess_transcript_quality(record)
    record["quality_state"] = record["quality"]["state"]
    return record




def _transcript_cache_status(transcript: Any, root: str, streamer: str = "") -> tuple[bool, str]:
    if not isinstance(transcript, dict) or not transcript.get("segments"):
        return False, "missing transcript segments"
    computed_quality = assess_transcript_quality(transcript)
    if computed_quality.get("state") != "valid":
        metrics = computed_quality.get("metrics") or {}
        return False, (
            f"quality={computed_quality.get('state')}/{computed_quality.get('classification')} "
            f"dominant_ratio={metrics.get('dominant_text_ratio')} "
            f"unique_ratio={metrics.get('unique_ratio')}"
        )
    if int(transcript.get("schema_version") or 0) != TRANSCRIPT_SCHEMA_VERSION:
        return False, f"schema={transcript.get('schema_version') or 'legacy'}"
    if str(transcript.get("provider") or "") not in TRANSCRIPT_PROVIDERS:
        return False, f"provider={transcript.get('provider') or 'legacy'}"
    if str(transcript.get("timestamp_mode") or "") != "segment":
        return False, f"timestamp_mode={transcript.get('timestamp_mode') or 'legacy'}"
    profile = transcript.get("decoding_profile") or {}
    if not isinstance(profile, dict) or str(profile.get("name") or "") != TRANSCRIPT_DECODING_PROFILE:
        return False, f"decoding_profile={profile.get('name') if isinstance(profile, dict) else 'legacy'}"
    if profile.get("condition_on_previous_text") is not False:
        return False, "condition_on_previous_text must be false"
    cached_quality = transcript.get("quality") or {}
    if not isinstance(cached_quality, dict) or cached_quality.get("profile") != TRANSCRIPT_QUALITY_PROFILE or cached_quality.get("state") != "valid":
        return False, "quality metadata missing/stale"
    requested = whisper_language(root, streamer) or "auto"
    if str(transcript.get("language_requested") or "auto").lower() != requested.lower():
        return False, f"language={transcript.get('language_requested') or 'auto'} -> {requested}"
    return True, "compatible"


def _transcript_cache_compatible(transcript: Any, root: str, streamer: str = "") -> bool:
    return _transcript_cache_status(transcript, root, streamer)[0]

def _fingerprint_record(source_kind: str, source_id: str, features: list[list[float]]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "provider": AUDIO_FINGERPRINT_PROVIDER,
        "source_kind": source_kind,
        "source_id": str(source_id),
        "frame_seconds": FRAME_SECONDS,
        "duration_seconds": round(len(features) * FRAME_SECONDS, 3),
        "created_at": C.utc_now(),
        "features": features,
    }


def _ensure_media_analysis(root: str, slug: str, *, source_kind: str, source_id: str,
                           source_url: str, streamer: str = "", force: bool = False, log=None,
                           want_transcript: bool = True, keep_media: bool = False) -> dict[str, Any]:
    """Ensure cached audio features and, only when requested, a full transcript.

    The resolver now calls this with ``want_transcript=False`` for its first
    verification phase. That preserves the proven audiovisual verifier without
    paying multi-hour Whisper cost. ``keep_media`` lets a newly-downloaded audio
    file survive briefly so a borderline match can reuse it for localized clips.
    """
    transcript_path = _transcript_file(root, slug, source_kind, source_id)
    fp_path = _audio_cache_file(root, slug, source_id) if source_kind == "twitch" else _youtube_audio_cache_file(root, slug, source_id)
    transcript = C.read_json(transcript_path, None) if os.path.isfile(transcript_path) and not force else None
    cache_ok, cache_reason = _transcript_cache_status(transcript, root, streamer) if transcript is not None else (False, "missing")
    if transcript is not None and not cache_ok:
        if log:
            action = "regenerating if transcript is needed" if want_transcript else "ignored during audio-first phase"
            log.write(
                f"transcript cache stale: {source_kind}/{source_id} "
                f"reason={cache_reason}; {action}\n"
            )
            log.flush()
        transcript = None
    fp = C.read_json(fp_path, None) if os.path.isfile(fp_path) and not force else None
    cached_analysis_audio = _analysis_audio_cached(root, slug, source_kind, source_id) if source_kind == "youtube" and not force else ""
    chromaprint_path = _chromaprint_cache_file(root, slug, source_kind, source_id)
    chromaprint = C.read_json(chromaprint_path, None) if os.path.isfile(chromaprint_path) and not force else None
    if not isinstance(chromaprint, dict) and cached_analysis_audio and resolve_fpcalc(False):
        chromaprint = _ensure_chromaprint(
            root, slug, source_kind, source_id, cached_analysis_audio, force=force, log=log,
        )
    failure_key = (
        _abs_root(root), str(slug), str(source_kind), str(source_id), str(streamer or ""),
        whisper_language(root, streamer) or "auto",
    )
    if force:
        with _LOCK:
            _TRANSCRIPT_FAILURES.pop(failure_key, None)
    with _LOCK:
        prior_transcript_failure = _TRANSCRIPT_FAILURES.get(failure_key, "")
    need_transcript = (
        want_transcript
        and transcript_enabled(root)
        and bool(transcription_backend(root))
        and not prior_transcript_failure
        and not (isinstance(transcript, dict) and transcript.get("segments"))
    )
    need_fp = not (isinstance(fp, dict) and fp.get("features"))
    if need_transcript:
        try:
            _transcription_preflight(root, log=log)
        except Exception as exc:
            error = str(exc) or exc.__class__.__name__
            with _LOCK:
                _TRANSCRIPT_FAILURES[failure_key] = error[:1200]
            prior_transcript_failure = error
            need_transcript = False
            if log:
                log.write(
                    f"transcript runtime unavailable for {source_kind}/{source_id}; "
                    f"audio fallback remains available and retry is suppressed until restart/--force: {error}\n"
                )
                log.flush()
    if not need_transcript and not need_fp:
        if prior_transcript_failure and log:
            log.write(
                f"transcript retry suppressed for {source_kind}/{source_id} in this server lifetime; "
                f"reusing cached audio fingerprint\n"
            )
            log.flush()
        return {
            "transcript": transcript, "fingerprint": fp, "chromaprint": chromaprint, "cache_hit": True,
            "transcript_failure": prior_transcript_failure,
            "media_path": cached_analysis_audio if keep_media and cached_analysis_audio else "",
        }

    base = _ensure_layout(root, slug)
    tmpdir = os.path.join(base, "tmp")
    os.makedirs(tmpdir, exist_ok=True)
    template = os.path.join(tmpdir, f"{source_kind}-{source_id}.%(ext)s")
    audio = cached_analysis_audio if cached_analysis_audio and os.path.isfile(cached_analysis_audio) else _download_audio(source_url, template, log=log)
    persistent_audio = bool(cached_analysis_audio and os.path.abspath(audio) == os.path.abspath(cached_analysis_audio))
    try:
        if need_transcript:
            try:
                transcript = _run_whisper(root, audio, source_kind=source_kind, source_id=source_id, streamer=streamer, log=log)
                C.write_json(transcript_path, transcript)
                with _LOCK:
                    _TRANSCRIPT_FAILURES.pop(failure_key, None)
                if log:
                    log.write(f"transcript cached: {source_kind}/{source_id} words={transcript.get('word_count', 0)}\n")
                    log.flush()
            except Exception as exc:
                error = str(exc) or exc.__class__.__name__
                with _LOCK:
                    _TRANSCRIPT_FAILURES[failure_key] = error[:1200]
                if log:
                    log.write(
                        f"transcript unavailable for {source_kind}/{source_id}; "
                        f"audio fallback remains available and transcript retry is suppressed until restart/--force: {error}\n"
                    )
                    log.flush()
        if need_fp:
            features = extract_audio_features(audio)
            fp = _fingerprint_record(source_kind, source_id, features)
            if source_kind == "twitch":
                fp["vod_id"] = str(source_id)  # backwards-compatible field
            else:
                fp["video_id"] = str(source_id)
            C.write_json(fp_path, fp)
            if log:
                log.write(f"audio fingerprint cached: {source_kind}/{source_id} frames={len(features)}\n")
                log.flush()
        if not isinstance(chromaprint, dict) and resolve_fpcalc(False):
            chromaprint = _ensure_chromaprint(
                root, slug, source_kind, source_id, audio, force=force, log=log,
            )
        if source_kind == "youtube" and not persistent_audio and os.path.isfile(audio):
            audio = _persist_youtube_analysis_audio(root, slug, source_id, audio, log=log) or audio
            persistent_audio = _analysis_audio_cached(root, slug, source_kind, source_id) == audio
    finally:
        if not keep_media and not persistent_audio:
            try:
                os.remove(audio)
            except OSError:
                pass
    return {
        "transcript": transcript, "fingerprint": fp, "chromaprint": chromaprint, "cache_hit": False,
        "media_path": audio if keep_media and os.path.isfile(audio) else "",
    }


def _fingerprint_twitch_vod(root: str, slug: str, vod: dict[str, Any], *, force: bool = False, log=None) -> dict[str, Any]:
    result = _ensure_media_analysis(
        root, slug, source_kind="twitch", source_id=str(vod["vod_id"]),
        source_url=str(vod["source_url"]), streamer=str(vod.get("streamer") or ""), force=force, log=log,
        want_transcript=False,
    )
    fp = result.get("fingerprint")
    if not isinstance(fp, dict) or not fp.get("features"):
        raise C.StudioError("Twitch audio fingerprint unavailable")
    return fp


def _norm_token(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text or "").lower())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^a-z0-9]+", "", value)
    return value


def _transcript_words(transcript: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(transcript, dict):
        return []
    rows: list[dict[str, Any]] = []
    for seg in list(transcript.get("segments") or []):
        if not isinstance(seg, dict):
            continue
        words = list(seg.get("words") or [])
        if words:
            for w in words:
                if not isinstance(w, dict):
                    continue
                token = _norm_token(w.get("word"))
                if not token:
                    continue
                try:
                    start = float(w.get("start")); end = float(w.get("end"))
                except (TypeError, ValueError):
                    continue
                rows.append({"token": token, "start": start, "end": end, "word": str(w.get("word") or "")})
            continue
        text_words = [x for x in re.findall(r"[\wÀ-ÿ']+", str(seg.get("text") or ""), flags=re.UNICODE) if _norm_token(x)]
        if not text_words:
            continue
        try:
            start = float(seg.get("start") or 0); end = float(seg.get("end") or start)
        except (TypeError, ValueError):
            start = 0.0; end = start
        span = max(0.001, end - start)
        for i, word in enumerate(text_words):
            ws = start + span * (i / len(text_words))
            we = start + span * ((i + 1) / len(text_words))
            rows.append({"token": _norm_token(word), "start": ws, "end": we, "word": word})
    return rows


def _ngram_index(words: list[dict[str, Any]], n: int) -> dict[tuple[str, ...], list[int]]:
    index: dict[tuple[str, ...], list[int]] = {}
    tokens = [w["token"] for w in words]
    for i in range(0, max(0, len(tokens) - n + 1)):
        key = tuple(tokens[i:i+n])
        index.setdefault(key, []).append(i)
    return index


def _best_text_window(query_tokens: list[str], target_words: list[dict[str, Any]], indexes: dict[int, dict[tuple[str, ...], list[int]]]) -> tuple[int, float]:
    candidates: set[int] = set()
    for n in (4, 3, 2):
        if len(query_tokens) < n:
            continue
        idx = indexes[n]
        seeds = []
        for offset in range(0, len(query_tokens)-n+1):
            key = tuple(query_tokens[offset:offset+n])
            hits = idx.get(key) or []
            if hits:
                seeds.append((len(hits), offset, hits))
        for _, offset, hits in sorted(seeds, key=lambda x: x[0])[:8]:
            for pos in hits[:40]:
                start = pos - offset
                if 0 <= start <= len(target_words) - len(query_tokens):
                    candidates.add(start)
        if candidates:
            break
    if not candidates:
        return 0, 0.0
    target_tokens = [w["token"] for w in target_words]
    best_start = 0; best = 0.0
    for start in list(candidates)[:400]:
        for shift in (-2, -1, 0, 1, 2):
            pos = start + shift
            if pos < 0 or pos + len(query_tokens) > len(target_tokens):
                continue
            ratio = difflib.SequenceMatcher(None, query_tokens, target_tokens[pos:pos+len(query_tokens)], autojunk=False).ratio()
            if ratio > best:
                best_start, best = pos, ratio
    return best_start, round(best, 4)


def align_transcripts(youtube_transcript: dict[str, Any], twitch_transcript: dict[str, Any]) -> dict[str, Any]:
    yw = _transcript_words(youtube_transcript)
    tw = _transcript_words(twitch_transcript)
    if len(yw) < TRANSCRIPT_QUERY_WORDS * 2 or len(tw) < TRANSCRIPT_QUERY_WORDS * 2:
        return {"method": TRANSCRIPT_ALIGNMENT_PROVIDER, "anchors": [], "assessment": {"state": "insufficient", "good_anchors": 0, "timeline_consistency": "insufficient"}}
    indexes = {n: _ngram_index(tw, n) for n in (2, 3, 4)}
    fractions = (0.07, 0.20, 0.34, 0.49, 0.64, 0.79, 0.92)[:TRANSCRIPT_ANCHORS]
    anchors = []
    qn = TRANSCRIPT_QUERY_WORDS
    for fraction in fractions:
        center = int((len(yw) - 1) * fraction)
        start = max(0, min(len(yw) - qn, center - qn // 2))
        query = yw[start:start+qn]
        query_tokens = [w["token"] for w in query]
        target_start, similarity = _best_text_window(query_tokens, tw, indexes)
        if similarity <= 0:
            continue
        center_offset = min(qn - 1, qn // 2)
        yt_word = query[center_offset]
        tw_word = tw[min(len(tw)-1, target_start + center_offset)]
        anchors.append({
            "youtube_time": round((float(yt_word["start"]) + float(yt_word["end"])) / 2, 3),
            "twitch_time": round((float(tw_word["start"]) + float(tw_word["end"])) / 2, 3),
            "similarity": similarity,
            "method": TRANSCRIPT_ALIGNMENT_PROVIDER,
            "query": " ".join(w["word"].strip() for w in query)[:320],
        })
    assessment = assess_transcript_alignment(anchors)
    return {"method": TRANSCRIPT_ALIGNMENT_PROVIDER, "anchors": anchors, "assessment": assessment}


def assess_transcript_alignment(anchors: list[dict[str, Any]]) -> dict[str, Any]:
    good = sorted([a for a in anchors if float(a.get("similarity") or 0) >= TRANSCRIPT_MIN_SIMILARITY], key=lambda a: float(a.get("youtube_time") or 0))
    ordered = len(good) >= 2 and all(float(b["twitch_time"]) > float(a["twitch_time"]) for a, b in zip(good, good[1:]))
    slopes = []
    for a, b in zip(good, good[1:]):
        yd = float(b["youtube_time"]) - float(a["youtube_time"])
        td = float(b["twitch_time"]) - float(a["twitch_time"])
        if yd > 0:
            slopes.append(td / yd)
    consistent = bool(slopes) and sum(1 for s in slopes if 0.70 <= s <= 4.0) >= max(1, math.ceil(len(slopes) * 0.70))
    median = statistics.median([float(a["similarity"]) for a in good]) if good else 0.0
    if len(good) >= 3 and ordered and consistent and median >= TRANSCRIPT_MIN_SIMILARITY:
        state = "strong"
    elif len(good) >= 2 and ordered:
        state = "likely"
    elif len(good) >= 2:
        state = "ambiguous"
    else:
        state = "insufficient"
    return {
        "state": state,
        "good_anchors": len(good),
        "total_anchors": len(anchors),
        "median_similarity": round(median, 4),
        "ordered": ordered,
        "timeline_consistency": "strong" if consistent and ordered else ("weak" if len(good) >= 2 else "insufficient"),
        "slopes": [round(x, 4) for x in slopes],
    }


def _feature_slice(features: list[list[float]], center_time: float, duration: float) -> tuple[list[list[float]], float]:
    half = duration / 2
    start_time = max(0.0, float(center_time) - half)
    start_frame = int(start_time / FRAME_SECONDS)
    frames = max(2, int(duration / FRAME_SECONDS))
    return features[start_frame:start_frame+frames], start_time


def confirm_transcript_anchors_audio(transcript_anchors: list[dict[str, Any]], youtube_fp: dict[str, Any], twitch_fp: dict[str, Any]) -> list[dict[str, Any]]:
    yf = list(youtube_fp.get("features") or [])
    tf = list(twitch_fp.get("features") or [])
    out = []
    for anchor in transcript_anchors:
        if float(anchor.get("similarity") or 0) < TRANSCRIPT_MIN_SIMILARITY:
            continue
        query, yt_start = _feature_slice(yf, float(anchor["youtube_time"]), AUDIO_CONFIRM_SECONDS)
        if len(query) < 4:
            continue
        predicted_start = max(0.0, float(anchor["twitch_time"]) - AUDIO_CONFIRM_SECONDS / 2)
        lo = max(0, int((predicted_start - AUDIO_CONFIRM_RADIUS) / FRAME_SECONDS))
        hi = min(max(0, len(tf) - len(query)), int((predicted_start + AUDIO_CONFIRM_RADIUS) / FRAME_SECONDS))
        frame, sim = match_feature_window(query, tf, step_frames=1, min_start=lo, max_start=hi)
        twitch_center = frame * FRAME_SECONDS + AUDIO_CONFIRM_SECONDS / 2
        out.append({
            "youtube_time": round(float(anchor["youtube_time"]), 3),
            "twitch_time": round(twitch_center, 3),
            "predicted_twitch_time": round(float(anchor["twitch_time"]), 3),
            "similarity": sim,
            "transcript_similarity": float(anchor.get("similarity") or 0),
            "method": "ffmpeg-temporal-features-localized-v2",
            "duration": AUDIO_CONFIRM_SECONDS,
        })
    return out


def _audio_only_anchors_from_caches(duration: float, youtube_fp: dict[str, Any], twitch_fp: dict[str, Any], *, log=None) -> list[dict[str, Any]]:
    yf = list(youtube_fp.get("features") or [])
    tf = list(twitch_fp.get("features") or [])
    anchors: list[dict[str, Any]] = []
    last_twitch_frame = 0
    for idx, yt_start in enumerate(_anchor_times(duration)):
        start_frame = int(yt_start / FRAME_SECONDS)
        count = max(2, int(ANCHOR_SECONDS / FRAME_SECONDS))
        query = yf[start_frame:start_frame+count]
        if not query:
            continue
        search_mode = "global"
        if idx == 0 or not anchors:
            details = match_feature_window_details(query, tf, step_frames=4, min_start=0)
        else:
            delta_seconds = max(0.0, yt_start - float(anchors[-1]["youtube_time"]))
            predicted = last_twitch_frame + int(delta_seconds / FRAME_SECONDS)
            lo = max(0, predicted - int(AUDIO_SEARCH_BACKTRACK_SECONDS / FRAME_SECONDS))
            hi = min(
                max(0, len(tf)-len(query)),
                predicted + int(AUDIO_SEARCH_FORWARD_SECONDS / FRAME_SECONDS),
            )
            details = match_feature_window_details(query, tf, step_frames=3, min_start=lo, max_start=hi)
            search_mode = "predicted-window"
            # A weak local maximum may simply mean a long removed Twitch interval.
            # Fall back to the old broad forward search rather than losing recall.
            if float(details.get("similarity") or 0.0) < max(0.76, ANCHOR_SIMILARITY_MIN - 0.04):
                broad_min = max(0, last_twitch_frame + int(delta_seconds / FRAME_SECONDS * 0.5))
                broad = match_feature_window_details(query, tf, step_frames=3, min_start=broad_min)
                if float(broad.get("similarity") or 0.0) >= float(details.get("similarity") or 0.0):
                    details = broad
                    search_mode = "forward-fallback"
        frame = int(details.get("start_frame") or 0)
        sim = float(details.get("similarity") or 0.0)
        last_twitch_frame = frame
        anchor = {
            "youtube_time": round(yt_start, 3),
            "twitch_time": round(frame * FRAME_SECONDS, 3),
            "similarity": sim,
            "second_best_similarity": float(details.get("second_best") or 0.0),
            "peak_margin": float(details.get("peak_margin") or 0.0),
            "search_mode": search_mode,
            "evaluated_windows": int(details.get("evaluated") or 0),
            "method": AUDIO_VERIFIER_PROVIDER,
            "duration": ANCHOR_SECONDS,
        }
        anchors.append(anchor)
        if log:
            log.write(
                f"audio fallback anchor {idx+1}: yt={yt_start:.1f}s twitch={anchor['twitch_time']:.1f}s "
                f"similarity={sim:.4f} second={anchor['second_best_similarity']:.4f} "
                f"margin={anchor['peak_margin']:.4f} search={search_mode}\n"
            )
            log.flush()
    return anchors

def _anchor_times(duration: float) -> list[float]:
    if duration <= ANCHOR_SECONDS * 2:
        return [max(0.0, duration/2 - ANCHOR_SECONDS/2)]
    fractions = (0.10, 0.36, 0.64, 0.88)
    out = []
    for f in fractions[:VERIFY_ANCHORS]:
        start = duration * f - ANCHOR_SECONDS/2
        out.append(max(2.0, min(duration - ANCHOR_SECONDS - 2.0, start)))
    return sorted(set(round(x, 3) for x in out))


def _piecewise_segments(anchors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    good = sorted([a for a in anchors if float(a.get("similarity") or 0) >= ANCHOR_SIMILARITY_MIN], key=lambda a: float(a["youtube_time"]))
    segments = []
    for a, b in zip(good, good[1:]):
        yd = float(b["youtube_time"]) - float(a["youtube_time"])
        td = float(b["twitch_time"]) - float(a["twitch_time"])
        if yd <= 1 or td <= 0: continue
        slope = td / yd
        # Huge jumps indicate a removed section; preserve piecewise mapping but do not bridge absurd matches.
        if slope > 4.0 or slope < 0.75: continue
        conf = min(float(a["similarity"]), float(b["similarity"]))
        offset_start = float(a["twitch_time"]) - float(a["youtube_time"])
        offset_end = float(b["twitch_time"]) - float(b["youtube_time"])
        segments.append({
            "youtube_start": float(a["youtube_time"]), "youtube_end": float(b["youtube_time"]),
            "twitch_start": float(a["twitch_time"]), "twitch_end": float(b["twitch_time"]),
            "slope": round(slope, 5), "confidence": round(conf, 4),
            "offset_start": round(offset_start, 3), "offset_end": round(offset_end, 3),
            "offset_delta": round(offset_end-offset_start, 3),
            "kind": "cut-gap" if offset_end-offset_start > OFFSET_CONTINUITY_TOLERANCE_SECONDS else "continuous",
        })
    return segments


def assess_verification(anchors: list[dict[str, Any]]) -> dict[str, Any]:
    good = [a for a in anchors if float(a.get("similarity") or 0) >= ANCHOR_SIMILARITY_MIN]
    similarities = [float(a.get("similarity") or 0) for a in good]
    ordered_good = sorted(good, key=lambda x: float(x["youtube_time"]))
    ordered = (
        len(ordered_good) > 1 and
        all(float(b["twitch_time"]) > float(a["twitch_time"]) for a,b in zip(ordered_good, ordered_good[1:]))
    )
    slopes: list[float] = []
    offsets = [float(a["twitch_time"]) - float(a["youtube_time"]) for a in ordered_good]
    offset_deltas = [b-a for a,b in zip(offsets, offsets[1:])]
    for a,b in zip(ordered_good, ordered_good[1:]):
        yd=float(b["youtube_time"])-float(a["youtube_time"]); td=float(b["twitch_time"])-float(a["twitch_time"])
        if yd > 0:
            slopes.append(td/yd)
    # For raw/near-raw uploads the mapping is naturally piecewise offset: within
    # a contiguous region TW-YT stays stable; removed Twitch material makes the
    # offset jump forward. Large backwards jumps are much stronger evidence of a
    # false peak than accepting arbitrary slopes up to 3x.
    backwards = [delta for delta in offset_deltas if delta < -OFFSET_BACKTRACK_TOLERANCE_SECONDS]
    continuous = [delta for delta in offset_deltas if abs(delta) <= OFFSET_CONTINUITY_TOLERANCE_SECONDS]
    forward_cuts = [delta for delta in offset_deltas if delta > OFFSET_CONTINUITY_TOLERANCE_SECONDS]
    consistent = bool(offset_deltas) and not backwards and ordered
    median = statistics.median(similarities) if similarities else 0.0
    margins = [float(a.get("peak_margin") or 0.0) for a in good if "peak_margin" in a]
    median_margin = statistics.median(margins) if margins else None
    # A raw/near-raw mirror should contain at least one adjacent anchor pair
    # with a stable offset. Positive jumps between other pairs are allowed as
    # removed Twitch material, but three unrelated forward peaks must not become
    # VERIFIED merely because they happen to be ordered.
    if len(good) >= 3 and median >= VERIFY_MEDIAN_MIN and ordered and consistent and continuous:
        state = "verified"
    elif len(good) >= 2 and ordered:
        state = "likely"
    elif len(good) >= 2 and not ordered:
        state = "ambiguous"
    else:
        state = "candidate"
    return {
        "state": state, "good_anchors": len(good), "total_anchors": len(anchors),
        "median_similarity": round(median, 4), "ordered": ordered,
        "timeline_consistency": "strong" if consistent else ("weak" if len(good) >= 2 else "insufficient"),
        "slopes": [round(x, 4) for x in slopes],
        "offsets": [round(x, 3) for x in offsets],
        "offset_deltas": [round(x, 3) for x in offset_deltas],
        "backwards_offset_jumps": [round(x, 3) for x in backwards],
        "continuous_offset_pairs": len(continuous),
        "forward_cut_gaps": [round(x, 3) for x in forward_cuts],
        "median_peak_margin": round(median_margin, 4) if median_margin is not None else None,
        "consistency_model": "piecewise-offset-v1",
    }



def _localized_range(anchor: dict[str, Any], key: str, source_duration: float = 0.0) -> tuple[float, float]:
    anchor_start = float(anchor.get(key) or 0.0)
    anchor_duration = float(anchor.get("duration") or ANCHOR_SECONDS)
    center = anchor_start + anchor_duration / 2.0
    half = LOCALIZED_TRANSCRIPT_SECONDS / 2.0
    start = max(0.0, center - half)
    end = center + half
    if source_duration > 0:
        end = min(source_duration, end)
        start = max(0.0, end - LOCALIZED_TRANSCRIPT_SECONDS)
    return round(start, 3), round(max(start + 1.0, end), 3)


def _transcript_text_in_range(transcript: dict[str, Any] | None, start: float, end: float) -> str:
    if not isinstance(transcript, dict):
        return ""
    parts: list[str] = []
    for seg in list(transcript.get("segments") or []):
        if not isinstance(seg, dict):
            continue
        try:
            seg_start = float(seg.get("start") or 0.0)
            seg_end = float(seg.get("end") or seg_start)
        except (TypeError, ValueError):
            continue
        if seg_end < start or seg_start > end:
            continue
        text = str(seg.get("text") or "").strip()
        if text:
            parts.append(text)
    return " ".join(parts)


def _localized_text_similarity(a: str, b: str) -> tuple[float, int, int]:
    at = [_norm_token(x) for x in re.findall(r"[\wÀ-ÿ']+", a or "", flags=re.UNICODE)]
    bt = [_norm_token(x) for x in re.findall(r"[\wÀ-ÿ']+", b or "", flags=re.UNICODE)]
    at = [x for x in at if x]
    bt = [x for x in bt if x]
    if len(at) < 8 or len(bt) < 8:
        return 0.0, len(at), len(bt)
    ratio = difflib.SequenceMatcher(None, at, bt, autojunk=False).ratio()
    return round(ratio, 4), len(at), len(bt)


def assess_localized_transcript_alignment(anchors: list[dict[str, Any]]) -> dict[str, Any]:
    good = [a for a in anchors if float(a.get("similarity") or 0) >= LOCALIZED_TRANSCRIPT_MIN_TEXT_SIMILARITY]
    sims = [float(a.get("similarity") or 0) for a in good]
    median = statistics.median(sims) if sims else 0.0
    if len(good) >= 3 and median >= 0.78:
        state = "strong"
    elif len(good) >= 2:
        state = "likely"
    else:
        state = "insufficient"
    return {
        "state": state,
        "good_anchors": len(good),
        "total_anchors": len(anchors),
        "median_similarity": round(median, 4),
        "timeline_consistency": "strong" if len(good) >= 2 else "insufficient",
    }


def _offset_raw_transcript(raw: dict[str, Any], offset: float) -> dict[str, Any]:
    out = {"text": str(raw.get("text") or ""), "language": raw.get("language"), "segments": []}
    for seg in list(raw.get("segments") or []):
        if not isinstance(seg, dict):
            continue
        item = dict(seg)
        try:
            item["start"] = float(item.get("start") or 0.0) + offset
            item["end"] = float(item.get("end") or item["start"] - offset) + offset
        except (TypeError, ValueError):
            continue
        words = []
        for word in list(item.get("words") or []):
            if not isinstance(word, dict):
                continue
            w = dict(word)
            try:
                w["start"] = float(w.get("start") or 0.0) + offset
                w["end"] = float(w.get("end") or w["start"] - offset) + offset
            except (TypeError, ValueError):
                continue
            words.append(w)
        if words:
            item["words"] = words
        out["segments"].append(item)
    return out


def _run_whisper_clip_files(root: str, clips: list[tuple[str, float, float]], *, source_kind: str,
                            source_id: str, streamer: str = "", log=None) -> dict[str, Any]:
    """Transcribe several downloaded clip files with one model load."""
    if not clips:
        raise C.StudioError("no localized clips to transcribe")
    if transcription_backend(root) == "faster-whisper":
        try:
            return _run_faster_whisper_inputs(
                root,
                [
                    {"path": path, "offset": start, "duration": max(0.0, end - start)}
                    for path, start, end in clips
                ],
                source_kind=source_kind, source_id=source_id, streamer=streamer,
                log=log, scope="localized",
            )
        except _TranscriptContentError:
            raise
        except Exception as exc:
            with _LOCK:
                _FASTER_WHISPER_FAILURES[_faster_failure_key(root)] = str(exc)[:1600]
            if not resolve_whisper(root, False):
                raise
            if log:
                log.write(f"faster-whisper localized batch failed; falling back to OpenAI Whisper: {exc}\n")
                log.flush()
    temp_out = tempfile.mkdtemp(prefix="cstudio-whisper-clips-")
    try:
        preflight = _whisper_preflight(root, log=log)
        paths = [path for path, _, _ in clips]
        cmd = build_whisper_command(
            root, paths, temp_out, device=str(preflight.get("effective_device") or ""), streamer=streamer,
        )
        if log:
            processed = sum(max(0.0, end-start) for _, start, end in clips)
            log.write(
                f"whisper localized batch: source={source_kind}/{source_id} clips={len(clips)} "
                f"processed_seconds={processed:.1f} model_loads=1\n"
            )
            log.write(f"transcribe localized {source_kind}/{source_id}: {_display_cmd(cmd)}\n")
            log.flush()
        proc = _popen_hidden(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding="utf-8", errors="replace", bufsize=1, env=_media_subprocess_env(),
        )
        tail: list[str] = []
        if proc.stdout is not None:
            for line in proc.stdout:
                clean = line.rstrip("\r\n")
                if not clean:
                    continue
                tail.append(clean)
                if len(tail) > 100:
                    tail = tail[-100:]
                if log:
                    log.write("[whisper] " + clean + "\n")
                    log.flush()
        rc = proc.wait()
        if rc != 0:
            raise C.StudioError(f"Whisper localized transcription failed with code {rc}: {' | '.join(tail[-8:])}")

        merged = {"text": "", "language": whisper_language(root, streamer) or "", "segments": []}
        texts: list[str] = []
        for path, start, _end in clips:
            expected = Path(temp_out) / (Path(path).stem + ".json")
            if not expected.is_file():
                matches = list(Path(temp_out).glob(Path(path).stem + "*.json"))
                if not matches:
                    raise C.StudioError(f"Whisper localized output missing for {os.path.basename(path)}")
                expected = matches[0]
            raw = json.loads(expected.read_text(encoding="utf-8"))
            shifted = _offset_raw_transcript(raw, start)
            if shifted.get("language") and not merged.get("language"):
                merged["language"] = shifted["language"]
            merged["segments"].extend(shifted.get("segments") or [])
            texts.append(str(shifted.get("text") or ""))
        merged["text"] = " ".join(x for x in texts if x)
        processed = sum(max(0.0, end-start) for _, start, end in clips)
        transcript = _normalize_whisper_transcript(
            merged, source_kind=source_kind, source_id=source_id, root=root, streamer=streamer,
            processed_duration_seconds=processed, scope="localized",
        )
        quality = transcript.get("quality") or {}
        if quality.get("state") != "valid":
            raise C.StudioError(
                f"localized transcript rejected by quality gate ({quality.get('classification') or 'invalid'})"
            )
        return transcript
    finally:
        shutil.rmtree(temp_out, ignore_errors=True)


def _download_localized_clips(root: str, slug: str, *, source_kind: str, source_id: str, source_url: str,
                              ranges: list[tuple[float, float]], log=None) -> list[tuple[str, float, float]]:
    base = _ensure_layout(root, slug)
    tmpdir = os.path.join(base, "tmp")
    os.makedirs(tmpdir, exist_ok=True)
    token = uuid.uuid4().hex[:6]
    clips: list[tuple[str, float, float]] = []
    try:
        for idx, (start, end) in enumerate(ranges, 1):
            template = os.path.join(tmpdir, f"localized-{source_kind}-{source_id}-{token}-{idx}.%(ext)s")
            path = _download_audio(
                source_url, template, section=(start, end), log=log, force_keyframes_at_cuts=False,
            )
            clips.append((path, start, end))
        return clips
    except Exception:
        for path, _, _ in clips:
            try:
                os.remove(path)
            except OSError:
                pass
        raise


def _localized_transcript_for_source(root: str, slug: str, *, source_kind: str, source_id: str,
                                     source_url: str, streamer: str, ranges: list[tuple[float, float]],
                                     existing_media: str = "", log=None) -> dict[str, Any]:
    if source_kind == "youtube":
        captions = _youtube_caption_transcript(
            root, slug, str(source_id), source_url, streamer=streamer, log=log,
        )
        if isinstance(captions, dict) and captions.get("segments"):
            if log:
                log.write(
                    f"localized transcript: using YouTube captions for {source_id}; "
                    f"Whisper/audio clip download skipped\n"
                )
                log.flush()
            return captions

        # Old fingerprint caches predate analysis-audio persistence. For two or
        # more localized anchors, repeatedly seeking three/four tiny YouTube
        # sections is commonly much slower than fetching bestaudio once. Migrate
        # that candidate lazily into the bounded local analysis cache; if the full
        # fetch fails, retain the previous range-download fallback below.
        if not (existing_media and os.path.isfile(existing_media)) and len(ranges) >= 2:
            existing_media = _analysis_audio_cached(root, slug, "youtube", str(source_id))
            if not existing_media:
                base = _ensure_layout(root, slug)
                template = os.path.join(base, "tmp", f"localized-full-youtube-{source_id}.%(ext)s")
                try:
                    if log:
                        log.write(
                            f"localized transcript: warming full YouTube analysis audio for {source_id}; "
                            f"clips={len(ranges)}\n"
                        )
                        log.flush()
                    fetched = _download_audio(source_url, template, log=log)
                    existing_media = _persist_youtube_analysis_audio(
                        root, slug, str(source_id), fetched, log=log,
                    ) or fetched
                except Exception as exc:
                    existing_media = ""
                    if log:
                        log.write(
                            f"localized transcript: full YouTube audio warmup failed; "
                            f"falling back to section downloads: {exc}\n"
                        )
                        log.flush()

    if existing_media and os.path.isfile(existing_media):
        if log:
            log.write(
                f"localized transcript: reuse downloaded {source_kind}/{source_id}; "
                f"clips={len(ranges)} seconds={sum(end-start for start, end in ranges):.1f}\n"
            )
            log.flush()
        return _run_whisper(
            root, existing_media, source_kind=source_kind, source_id=source_id, streamer=streamer,
            log=log, clip_timestamps=ranges,
        )

    clips = _download_localized_clips(
        root, slug, source_kind=source_kind, source_id=source_id, source_url=source_url,
        ranges=ranges, log=log,
    )
    try:
        return _run_whisper_clip_files(
            root, clips, source_kind=source_kind, source_id=source_id, streamer=streamer, log=log,
        )
    finally:
        for path, _, _ in clips:
            try:
                os.remove(path)
            except OSError:
                pass


def confirm_audio_anchors_with_localized_transcripts(root: str, slug: str, *, vod_id: str, video_id: str,
                                                      streamer: str, twitch_url: str, youtube_url: str,
                                                      anchors: list[dict[str, Any]], twitch_fp: dict[str, Any],
                                                      youtube_fp: dict[str, Any], twitch_media: str = "",
                                                      youtube_media: str = "", log=None) -> dict[str, Any]:
    selected = [
        a for a in sorted(anchors, key=lambda x: float(x.get("youtube_time") or 0.0))
        if float(a.get("similarity") or 0.0) >= LOCALIZED_TRANSCRIPT_MIN_AUDIO_SIMILARITY
    ][:LOCALIZED_TRANSCRIPT_MAX_ANCHORS]
    if len(selected) < 2:
        return {
            "method": LOCALIZED_TRANSCRIPT_PROVIDER,
            "anchors": [],
            "assessment": {"state": "insufficient", "good_anchors": 0, "total_anchors": 0,
                           "timeline_consistency": "insufficient", "reason": "not enough audio-localized anchors"},
        }

    yt_duration = float(youtube_fp.get("duration_seconds") or 0.0)
    tw_duration = float(twitch_fp.get("duration_seconds") or 0.0)
    yt_ranges = [_localized_range(a, "youtube_time", yt_duration) for a in selected]
    tw_ranges = [_localized_range(a, "twitch_time", tw_duration) for a in selected]

    yt_transcript = _localized_transcript_for_source(
        root, slug, source_kind="youtube", source_id=video_id, source_url=youtube_url,
        streamer=streamer, ranges=yt_ranges, existing_media=youtube_media, log=log,
    )
    tw_transcript = _localized_transcript_for_source(
        root, slug, source_kind="twitch", source_id=vod_id, source_url=twitch_url,
        streamer=streamer, ranges=tw_ranges, existing_media=twitch_media, log=log,
    )

    out: list[dict[str, Any]] = []
    for anchor, yr, tr in zip(selected, yt_ranges, tw_ranges):
        yt_text = _transcript_text_in_range(yt_transcript, *yr)
        tw_text = _transcript_text_in_range(tw_transcript, *tr)
        similarity, yt_tokens, tw_tokens = _localized_text_similarity(yt_text, tw_text)
        row = {
            "youtube_time": round(float(anchor.get("youtube_time") or 0.0), 3),
            "twitch_time": round(float(anchor.get("twitch_time") or 0.0), 3),
            "audio_similarity": round(float(anchor.get("similarity") or 0.0), 4),
            "similarity": similarity,
            "youtube_tokens": yt_tokens,
            "twitch_tokens": tw_tokens,
            "youtube_text": yt_text[:320],
            "twitch_text": tw_text[:320],
            "method": LOCALIZED_TRANSCRIPT_PROVIDER,
        }
        out.append(row)
        if log:
            log.write(
                f"localized transcript anchor: yt={row['youtube_time']:.1f}s tw={row['twitch_time']:.1f}s "
                f"audio={row['audio_similarity']:.4f} text={similarity:.4f} "
                f"tokens={yt_tokens}/{tw_tokens}\n"
            )
            log.flush()
    return {"method": LOCALIZED_TRANSCRIPT_PROVIDER, "anchors": out, "assessment": assess_localized_transcript_alignment(out)}

def verify_match(root: str, slug: str, vod_id: str, video_id: str, *, force: bool = False, log=None) -> dict[str, Any]:
    manifest = load_match(root, slug, vod_id, video_id)
    if not manifest:
        raise C.StudioError("candidate match not found; run youtube-resolve first")
    if manifest.get("state") == "rejected" and not force:
        raise C.StudioError("candidate was rejected; use --force to verify it again")

    video = enrich_video_metadata_cached(root, slug, dict(manifest.get("youtube") or {}), force=force, log=log)
    manifest["youtube"] = video
    manifest_streamer = str((manifest.get("twitch") or {}).get("streamer") or manifest.get("streamer") or video.get("streamer") or "").strip().lower()
    if manifest_streamer and not _channel_allowed_for_video(root, manifest_streamer, video):
        manifest["state"] = "candidate"
        manifest["verification"] = {
            "mode": "metadata-rejected-before-media",
            "providers": {"metadata": "complete", "transcript": "not_run", "audio": "not_run"},
            "reason": "YouTube channel ID does not match configured mirror channel",
        }
        save_match(root, slug, manifest)
        return manifest
    duration = float(video.get("duration") or 0)
    if duration <= 0:
        raise C.StudioError("YouTube duration unavailable; cannot verify candidate")
    vod = dict(manifest.get("twitch") or {})
    if not vod.get("source_url"):
        raise C.StudioError("Twitch source URL unavailable")
    streamer = str(vod.get("streamer") or manifest.get("streamer") or "").strip().lower()

    refined = score_candidate(vod, video, configured_channel=True)
    prior_score = float(manifest.get("candidate_score") or 0)
    manifest["candidate_score_initial"] = prior_score
    manifest["candidate_score"] = refined["candidate_score"]
    manifest["candidate_evidence"] = refined
    manifest["metadata_enriched_at"] = C.utc_now()
    date_signal = (refined.get("signals") or {}).get("date", {})
    date_score = float(date_signal.get("score")) if date_signal.get("available") and date_signal.get("score") is not None else None
    if not force and ((date_score is not None and date_score <= 0.02) or float(refined["candidate_score"]) < 0.40):
        manifest["state"] = "candidate"
        manifest["verification"] = {
            "mode": "metadata-rejected-before-media",
            "providers": {"metadata": "complete", "transcript": "not_run", "audio": "not_run"},
            "transcript": {"method": LOCALIZED_TRANSCRIPT_PROVIDER, "anchors": [], "assessment": {"state": "not_run"}},
            "audio": {"method": AUDIO_VERIFIER_PROVIDER, "anchors": [], "assessment": {"state": "not_run"}},
            "reason": "enriched metadata fell below verification gate",
        }
        save_match(root, slug, manifest)
        if log:
            date_label = f"{date_score:.3f}" if date_score is not None else "unknown"
            log.write(f"metadata gate: skip media vod={vod_id} youtube={video_id} score={float(refined['candidate_score']):.3f} date={date_label}\n")
            log.flush()
        return manifest

    # Phase 1: proven audiovisual verifier first. Full-source Whisper is never
    # started here. Newly downloaded audio is kept only until this verification
    # finishes so a borderline match can reuse it for short localized clips.
    twitch_analysis = _ensure_media_analysis(
        root, slug, source_kind="twitch", source_id=str(vod_id),
        source_url=str(vod["source_url"]), streamer=streamer, force=force, log=log,
        want_transcript=False, keep_media=True,
    )
    youtube_url = str(video.get("url") or f"https://www.youtube.com/watch?v={video_id}")
    youtube_analysis = _ensure_media_analysis(
        root, slug, source_kind="youtube", source_id=str(video_id),
        source_url=youtube_url, streamer=streamer, force=force, log=log,
        want_transcript=False, keep_media=True,
    )
    kept_media = [str(twitch_analysis.get("media_path") or ""), str(youtube_analysis.get("media_path") or "")]
    try:
        twitch_fp = twitch_analysis.get("fingerprint") or {}
        youtube_fp = youtube_analysis.get("fingerprint") or {}
        if not twitch_fp.get("features") or not youtube_fp.get("features"):
            raise C.StudioError("audio fingerprint cache unavailable after media analysis")

        audio_anchors = _audio_only_anchors_from_caches(duration, youtube_fp, twitch_fp, log=log)
        audio_assessment = assess_verification(audio_anchors)
        chromaprint_shadow = _chromaprint_shadow_anchors(
            duration, youtube_analysis.get("chromaprint"), twitch_analysis.get("chromaprint"),
        )
        if log and chromaprint_shadow.get("status") == "complete":
            log.write(
                f"chromaprint shadow assessment: anchors={len(chromaprint_shadow.get('anchors') or [])} "
                f"median={float(chromaprint_shadow.get('median_similarity') or 0):.4f} authority=false\n"
            )
            log.flush()
        audio_state = str(audio_assessment.get("state") or "candidate")
        mode = "audio-first"
        state = audio_state
        transcript_provider_state = "not_needed" if audio_state == "verified" else "not_run"
        transcript_evidence: dict[str, Any] = {
            "method": LOCALIZED_TRANSCRIPT_PROVIDER,
            "anchors": [],
            "assessment": {
                "state": "not_needed" if audio_state == "verified" else "not_run",
                "good_anchors": 0,
                "timeline_consistency": "not_needed" if audio_state == "verified" else "not_run",
                "reason": "audio verifier already satisfied VERIFIED policy" if audio_state == "verified" else "localized transcript not required yet",
            },
        }

        if log:
            log.write(
                f"audio-first assessment: state={audio_state} good={audio_assessment.get('good_anchors', 0)}/"
                f"{audio_assessment.get('total_anchors', 0)} median={float(audio_assessment.get('median_similarity') or 0):.4f} "
                f"consistency={audio_assessment.get('timeline_consistency')}\n"
            )
            if audio_state == "verified":
                log.write("Whisper skipped: audiovisual verifier already reached VERIFIED.\n")
            log.flush()

        # Compatible full transcripts from an earlier run can still contribute at
        # zero inference cost, but the resolver does not create new full transcripts.
        twitch_transcript = twitch_analysis.get("transcript")
        youtube_transcript = youtube_analysis.get("transcript")
        if audio_state != "verified" and isinstance(twitch_transcript, dict) and isinstance(youtube_transcript, dict):
            cached_evidence = align_transcripts(youtube_transcript, twitch_transcript)
            transcript_evidence = cached_evidence
            transcript_provider_state = "cache_complete"
            mode = "audio-first+cached-transcript"
            cached_state = str((cached_evidence.get("assessment") or {}).get("state") or "insufficient")
            # Cached text may make a borderline result more conservative, but never
            # promotes beyond the existing audiovisual VERIFIED threshold.
            if audio_state == "likely" and cached_state not in {"strong", "likely"}:
                state = "candidate" if cached_state == "insufficient" else "ambiguous"

        # Only a near-match gets new text work. We transcribe at most four 48-second
        # regions around audio-localized anchors. If the full media is no longer
        # present, yt-dlp fetches only those sections and Whisper loads the model once.
        elif (
            audio_state == "likely"
            and transcript_enabled(root)
            and bool(transcription_backend(root))
        ):
            try:
                transcript_evidence = confirm_audio_anchors_with_localized_transcripts(
                    root, slug, vod_id=str(vod_id), video_id=str(video_id), streamer=streamer,
                    twitch_url=str(vod["source_url"]), youtube_url=youtube_url,
                    anchors=audio_anchors, twitch_fp=twitch_fp, youtube_fp=youtube_fp,
                    twitch_media=str(twitch_analysis.get("media_path") or ""),
                    youtube_media=str(youtube_analysis.get("media_path") or ""), log=log,
                )
                transcript_provider_state = "localized_complete"
                mode = "audio-first+localized-transcript"
                text_state = str((transcript_evidence.get("assessment") or {}).get("state") or "insufficient")
                # Text is a conservative secondary gate only. It cannot create
                # VERIFIED unless audio independently already met VERIFIED (handled above).
                if text_state not in {"strong", "likely"}:
                    state = "candidate"
            except Exception as exc:
                transcript_provider_state = "localized_failed"
                transcript_evidence = {
                    "method": LOCALIZED_TRANSCRIPT_PROVIDER,
                    "anchors": [],
                    "assessment": {"state": "unavailable", "good_anchors": 0, "timeline_consistency": "unavailable", "reason": str(exc)[:1200]},
                }
                if log:
                    log.write(f"localized transcript unavailable; preserving audio result {audio_state}: {exc}\n")
                    log.flush()
                state = audio_state

        segments = _piecewise_segments(audio_anchors)
        manifest["state"] = state
        manifest["verification"] = {
            "mode": mode,
            "providers": {
                "metadata": "complete",
                "transcript": transcript_provider_state,
                "audio": "complete",
            },
            "transcript": {
                **transcript_evidence,
                "strategy": "localized-on-demand",
                "full_source_whisper": False,
                "twitch_cache": os.path.relpath(_transcript_file(root, slug, "twitch", vod_id), C.prod_path(root, slug)).replace(os.sep, "/") if isinstance(twitch_transcript, dict) else "",
                "youtube_cache": os.path.relpath(_transcript_file(root, slug, "youtube", video_id), C.prod_path(root, slug)).replace(os.sep, "/") if isinstance(youtube_transcript, dict) else "",
            },
            "audio": {
                "method": AUDIO_VERIFIER_PROVIDER,
                "anchors": audio_anchors,
                "assessment": audio_assessment,
                "chromaprint_shadow": chromaprint_shadow,
                "twitch_fingerprint_cache": os.path.relpath(_audio_cache_file(root, slug, vod_id), C.prod_path(root, slug)).replace(os.sep, "/"),
                "youtube_fingerprint_cache": os.path.relpath(_youtube_audio_cache_file(root, slug, video_id), C.prod_path(root, slug)).replace(os.sep, "/"),
            },
        }
        manifest["timeline_segments"] = segments
        save_match(root, slug, manifest)
        return manifest
    finally:
        for media in kept_media:
            if media and not _is_analysis_audio_path(root, slug, media):
                try:
                    os.remove(media)
                except OSError:
                    pass

def map_youtube_to_twitch(manifest: dict[str, Any], youtube_time: float) -> float | None:
    t = float(youtube_time)
    for seg in manifest.get("timeline_segments") or []:
        a=float(seg["youtube_start"]); b=float(seg["youtube_end"])
        if a <= t <= b and b > a:
            ratio=(t-a)/(b-a); return float(seg["twitch_start"]) + ratio*(float(seg["twitch_end"])-float(seg["twitch_start"]))
    return None


def map_twitch_to_youtube(manifest: dict[str, Any], twitch_time: float) -> float | None:
    t = float(twitch_time)
    for seg in manifest.get("timeline_segments") or []:
        a=float(seg["twitch_start"]); b=float(seg["twitch_end"])
        if a <= t <= b and b > a:
            ratio=(t-a)/(b-a); return float(seg["youtube_start"]) + ratio*(float(seg["youtube_end"])-float(seg["youtube_start"]))
    return None


def reject_match(root: str, slug: str, vod_id: str, video_id: str, reason: str = "manual rejection") -> dict[str, Any]:
    rec = load_match(root, slug, vod_id, video_id)
    if not rec: raise C.StudioError("candidate match not found")
    rec["state"] = "rejected"
    rec["rejection"] = {"at": C.utc_now(), "reason": str(reason or "manual rejection")[:1000]}
    save_match(root, slug, rec)
    assignment = load_assignment(root, slug, video_id)
    if isinstance(assignment, dict):
        pair_results = dict(assignment.get("pair_results") or {})
        prior_pair = dict(pair_results.get(str(vod_id)) or {})
        prior_pair.update({"vod_id": str(vod_id), "state": "rejected", "reason": rec["rejection"]["reason"]})
        pair_results[str(vod_id)] = prior_pair
        assignment["pair_results"] = pair_results
        assignment["status"] = "partial"
        assignment["state"] = "pending"
        assignment["primary_vod_id"] = ""
        save_assignment(root, slug, assignment)
    return rec


def build_download_command(url: str, output_template: str, *, info_json: bool = True) -> list[str]:
    ytdlp = resolve_ytdlp()
    ffmpeg = resolve_ffmpeg()
    ffmpeg_dir = os.path.dirname(ffmpeg) if os.path.isfile(ffmpeg) else ffmpeg
    cmd = [ytdlp, "--no-playlist", *_yt_dlp_runtime_args(), "-f", "bv*+ba/b", "--merge-output-format", "mkv"]
    if ffmpeg_dir: cmd += ["--ffmpeg-location", ffmpeg_dir]
    if info_json: cmd += ["--write-info-json"]
    cmd += ["-o", output_template, url]
    return cmd


def _probe_media(path: str) -> dict[str, Any]:
    ffprobe = resolve_ffprobe()
    cmd = [ffprobe, "-v", "error", "-print_format", "json", "-show_streams", "-show_format", path]
    proc = _run_hidden(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", check=False)
    if proc.returncode != 0: return {"error": proc.stderr[-500:]}
    try: data=json.loads(proc.stdout)
    except Exception: return {}
    videos=[s for s in data.get("streams",[]) if s.get("codec_type")=="video"]
    audios=[s for s in data.get("streams",[]) if s.get("codec_type")=="audio"]
    v=videos[0] if videos else {}; a=audios[0] if audios else {}
    fps = None
    rate=str(v.get("avg_frame_rate") or "")
    if "/" in rate:
        try:
            n,d=rate.split("/",1); fps=float(n)/float(d) if float(d) else None
        except Exception: pass
    return {"height": v.get("height"), "width": v.get("width"), "fps": fps, "video_codec": v.get("codec_name"), "audio_codec": a.get("codec_name"), "duration": (data.get("format") or {}).get("duration")}


def _verified_relationships_for_video(root: str, slug: str, video_id: str) -> list[dict[str, Any]]:
    """Return every verified pair manifest for one YouTube source.

    Pair manifests remain stored by Twitch VOD so N Twitch VODs -> 1 YouTube video
    does not collapse independent piecewise timeline maps into one ambiguous file.
    """
    rows = []
    for rec in list_matches(root, slug):
        if rec.get("youtube_video_id") == video_id and rec.get("state") == "verified":
            rows.append(rec)
    return rows


def download_verified(root: str, slug: str, vod_id: str, video_id: str, *, force: bool = False, log=None) -> dict[str, Any]:
    manifest = load_match(root, slug, vod_id, video_id)
    if not manifest: raise C.StudioError("candidate match not found")
    if manifest.get("state") != "verified" and not force:
        raise C.StudioError("automatic master download is allowed only for VERIFIED matches; use --force for explicit manual override")
    streamer = _validate_streamer(str(manifest.get("streamer") or "unknown"))
    media_dir = os.path.join(_ensure_layout(root, slug), "media", streamer, video_id)
    os.makedirs(media_dir, exist_ok=True)
    output_template = os.path.join(media_dir, f"{video_id}.%(ext)s")
    cmd = build_download_command(str((manifest.get("youtube") or {}).get("url") or f"https://www.youtube.com/watch?v={video_id}"), output_template)
    if log: log.write(f"download master: {_display_cmd(cmd)}\n"); log.flush()
    proc = _run_hidden(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", check=False)
    if log: log.write(proc.stdout[-8000:] + "\n"); log.flush()
    if proc.returncode != 0:
        manifest["download"] = {"status": "failed", "path": "", "returncode": proc.returncode, "error": proc.stdout[-1000:]}
        save_match(root, slug, manifest)
        raise C.StudioError(f"yt-dlp download failed with code {proc.returncode}")
    candidates=[]
    for name in os.listdir(media_dir):
        if name.endswith((".info.json", ".part", ".ytdl", ".json")): continue
        full=os.path.join(media_dir,name)
        if os.path.isfile(full): candidates.append(full)
    if not candidates: raise C.StudioError("download completed but master file was not found")
    master=max(candidates,key=os.path.getsize)
    quality=_probe_media(master)
    vdir=C.prod_path(root,slug)
    rel=os.path.relpath(master,vdir).replace(os.sep,"/")
    manifest_rel=os.path.relpath(_candidate_file(root,slug,vod_id,video_id),vdir).replace(os.sep,"/")
    relationships = _verified_relationships_for_video(root, slug, video_id)
    verified_vods = sorted({str(v) for rec in relationships for v in (rec.get("twitch_vod_ids") or []) if v})
    relationship_manifests = sorted({
        os.path.relpath(_candidate_file(root, slug, str((rec.get("twitch_vod_ids") or [""])[0]), video_id), vdir).replace(os.sep, "/")
        for rec in relationships if rec.get("twitch_vod_ids")
    })
    manifest["download"]={"status":"completed","path":rel,"completed_at":C.utc_now(),**quality}
    manifest["asset"]={
        "asset_id":f"youtube-{video_id}","kind":"video-source","platform":"youtube",
        "youtube_video_id": video_id, "channel": (manifest.get("youtube") or {}).get("channel_name", ""),
        "source_url": (manifest.get("youtube") or {}).get("url", ""), "quality": quality,
        "corresponding_twitch_vod_ids": verified_vods or [str(vod_id)],
        "verified_match_manifests": relationship_manifests or [manifest_rel],
        "metadata_manifest":manifest_rel,"resolver_state": manifest.get("state"),
        "rights_status":"sem_autorizacao_confirmada"
    }
    save_match(root,slug,manifest)
    asset=PL.register_asset(root,slug,f"youtube-{video_id}","video-source",rel,"sem_autorizacao_confirmada")
    manifest["asset"].update(asset)
    save_match(root,slug,manifest)
    return manifest


def _chapter_shared_token_count(vod: dict[str, Any], video: dict[str, Any]) -> int:
    vt = _tokens(str(video.get("title") or "") + " " + str(video.get("description") or ""))
    if not vt:
        return 0
    return max(
        [len(vt & _tokens(str(ch.get("title") or ""))) for ch in (vod.get("chapters") or []) if isinstance(ch, dict)]
        or [0]
    )


def _global_discovery_time_window(vods: list[dict[str, Any]]) -> tuple[datetime | None, datetime | None]:
    """Return the safe YouTube publish window for a production's Twitch VODs."""
    starts: list[datetime] = []
    ends: list[datetime] = []
    for vod in vods:
        created = _parse_date(vod.get("created_at"))
        if not created:
            continue
        starts.append(created)
        try:
            duration = max(0.0, float(vod.get("duration") or 0.0))
        except (TypeError, ValueError):
            duration = 0.0
        ends.append(created + timedelta(seconds=duration))
    if not starts:
        return None, None
    earliest = min(starts) - timedelta(days=GLOBAL_DISCOVERY_PRE_ROLL_DAYS)
    latest = max(ends or starts) + timedelta(days=GLOBAL_DISCOVERY_UPLOAD_LAG_DAYS)
    return earliest, latest


def _video_publish_time(video: dict[str, Any]) -> datetime | None:
    return _parse_date(video.get("timestamp") or video.get("upload_date") or video.get("release_timestamp"))


def _discover_global_video_pool(root: str, slug: str, *, streamer: str = "", vod_id: str = "", log=None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return YouTube sources that can plausibly belong to the production.

    Metadata similarity is useful for prioritisation, not completeness. YouTube
    flat-tab entries often omit dates and sometimes carry temporary titles
    (e.g. ``guns5``), so a strict title/chapter gate can permanently hide a true
    mirror. We therefore lazily enrich a bounded recent frontier and include
    every upload whose exact publish time overlaps the Twitch production window.
    Older historical rows still use the cheap metadata/cached-fingerprint rules.
    """
    vods = list_twitch_vods(root, slug, streamer)
    if vod_id:
        vods = [v for v in vods if str(v.get("vod_id") or "") == str(vod_id)]
        if not vods:
            raise C.StudioError(f"Twitch VOD not found in production: {vod_id}")
    by_streamer: dict[str, list[dict[str, Any]]] = {}
    for vod in vods:
        by_streamer.setdefault(str(vod.get("streamer") or "").lower(), []).append(vod)

    prior_video_ids = {
        str(rec.get("youtube_video_id") or "")
        for rec in list_matches(root, slug)
        if str(rec.get("state") or "") in {"likely", "verified", "ambiguous"}
    }
    selected: dict[str, dict[str, Any]] = {}
    for st, streamer_vods in by_streamer.items():
        indexed = [dict(v) for v in load_index(root, slug, st) if isinstance(v, dict)]
        earliest_publish, latest_publish = _global_discovery_time_window(streamer_vods)
        metadata_scanned = 0
        older_streak = 0

        for position, original_video in enumerate(indexed, 1):
            video = dict(original_video)
            video_id = str(video.get("video_id") or "")
            if not video_id or not _channel_allowed_for_video(root, st, video):
                continue

            publish_time = _video_publish_time(video)
            # Channel-tab flat indexes are newest-first. Enrich only the recent
            # frontier until exact dates prove we are safely older than the
            # production. Cached metadata makes later runs essentially free.
            should_enrich_frontier = (
                publish_time is None
                and earliest_publish is not None
                and metadata_scanned < GLOBAL_DISCOVERY_METADATA_SCAN_LIMIT
                and older_streak < GLOBAL_DISCOVERY_OLD_BOUNDARY_STREAK
            )
            if should_enrich_frontier:
                try:
                    video = enrich_video_metadata_cached(root, slug, video, force=False, log=log)
                    metadata_scanned += 1
                    publish_time = _video_publish_time(video)
                except Exception as exc:
                    metadata_scanned += 1
                    if log:
                        log.write(f"global discovery metadata unavailable: youtube={video_id} position={position}: {exc}\n")
                        log.flush()

            if publish_time is not None and earliest_publish is not None:
                if publish_time < earliest_publish:
                    older_streak += 1
                else:
                    older_streak = 0

            scores = [(score_candidate(vod, video, configured_channel=True), vod) for vod in streamer_vods]
            if not scores:
                continue
            best_evidence, best_vod = max(scores, key=lambda row: float(row[0].get("candidate_score") or 0.0))
            best_score = float(best_evidence.get("candidate_score") or 0.0)
            shared = max(_chapter_shared_token_count(vod, video) for vod in streamer_vods)
            cached_fp = os.path.isfile(_youtube_audio_cache_file(root, slug, video_id))
            in_time_window = bool(
                publish_time is not None
                and earliest_publish is not None
                and latest_publish is not None
                and earliest_publish <= publish_time <= latest_publish
            )
            unknown_recent_frontier = bool(
                publish_time is None
                and earliest_publish is not None
                and position <= GLOBAL_DISCOVERY_METADATA_SCAN_LIMIT
                and older_streak < GLOBAL_DISCOVERY_OLD_BOUNDARY_STREAK
            )
            metadata_selected = best_score >= GLOBAL_DISCOVERY_MIN_SCORE or shared >= GLOBAL_DISCOVERY_MIN_CHAPTER_SHARED
            historical_selected = cached_fp or video_id in prior_video_ids

            if not (in_time_window or unknown_recent_frontier or metadata_selected or historical_selected):
                continue

            reasons: list[str] = []
            if in_time_window:
                reasons.append("production-time-window")
            if unknown_recent_frontier:
                reasons.append("recent-date-unknown")
            if metadata_selected:
                reasons.append("metadata")
            if historical_selected:
                reasons.append("checkpoint")
            selected[video_id] = {
                "video": dict(video),
                "best_candidate_score": round(best_score, 4),
                "best_candidate_vod_id": str(best_vod.get("vod_id") or ""),
                "best_chapter_shared_tokens": int(shared),
                "streamer": st,
                "discovery_reasons": reasons,
                "index_position": position,
                "publish_time": publish_time.isoformat() if publish_time else "",
            }

        if log:
            time_rows = sum(1 for r in selected.values() if r.get("streamer") == st and "production-time-window" in (r.get("discovery_reasons") or []))
            unknown_rows = sum(1 for r in selected.values() if r.get("streamer") == st and "recent-date-unknown" in (r.get("discovery_reasons") or []))
            log.write(
                f"global discovery coverage: streamer={st} indexed={len(indexed)} metadata_scanned={metadata_scanned} "
                f"time_window={time_rows} unknown_recent={unknown_rows} selected={sum(1 for r in selected.values() if r.get('streamer') == st)}\n"
            )
            log.flush()

    rows = sorted(
        selected.values(),
        key=lambda row: (
            0 if "production-time-window" in (row.get("discovery_reasons") or []) else 1,
            int(row.get("index_position") or 10**9),
            -float(row.get("best_candidate_score") or 0.0),
            -int(row.get("best_chapter_shared_tokens") or 0),
            str((row.get("video") or {}).get("video_id") or ""),
        ),
    )
    if len(rows) > GLOBAL_DISCOVERY_MAX_VIDEOS:
        if log:
            log.write(
                f"global discovery safety cap: selected={len(rows)} cap={GLOBAL_DISCOVERY_MAX_VIDEOS}; "
                "increase GLOBAL_DISCOVERY_MAX_VIDEOS only for unusually large productions\n"
            )
            log.flush()
        rows = rows[:GLOBAL_DISCOVERY_MAX_VIDEOS]
    return vods, rows


def _pair_result_rank(result: dict[str, Any]) -> tuple[int, int, float, int, float]:
    assessment = ((result.get("audio") or {}).get("assessment") or {})
    state_rank = {"verified": 4, "likely": 3, "ambiguous": 2, "candidate": 1, "rejected": 0}.get(str(result.get("state") or ""), 0)
    return (
        state_rank,
        int(assessment.get("good_anchors") or 0),
        float(assessment.get("median_similarity") or 0.0),
        int(assessment.get("continuous_offset_pairs") or 0),
        float(result.get("candidate_score") or 0.0),
    )


def _deep_audio_stats(result: dict[str, Any]) -> tuple[int, float]:
    anchors = list((result.get("audio") or {}).get("anchors") or [])
    similarities = [
        float(a.get("similarity") or 0.0)
        for a in anchors
        if float(a.get("similarity") or 0.0) >= LOCALIZED_TRANSCRIPT_MIN_AUDIO_SIMILARITY
    ]
    return len(similarities), (statistics.median(similarities) if similarities else 0.0)


def _deep_resolution_candidates(pair_results: dict[str, Any]) -> list[dict[str, Any]]:
    """Return a bounded set of unresolved pairs worth paying text cost for.

    The acoustic verifier remains authoritative for direct VERIFIED. This list is
    intentionally broader: two independently localized, moderately similar audio
    anchors are enough to justify a short captions/Whisper tiebreak, not enough to
    verify on their own.
    """
    rows: list[dict[str, Any]] = []
    for result in pair_results.values():
        if not isinstance(result, dict):
            continue
        if str(result.get("state") or "") in {"verified", "rejected"}:
            continue
        assessment = ((result.get("audio") or {}).get("assessment") or {})
        if str(assessment.get("state") or "") in {"", "not_run"}:
            continue
        count, median = _deep_audio_stats(result)
        if count < DEEP_RESOLUTION_MIN_AUDIO_ANCHORS or median < DEEP_RESOLUTION_AUDIO_MEDIAN_MIN:
            continue
        row = dict(result)
        row["deep_audio_anchor_count"] = count
        row["deep_audio_median_similarity"] = round(median, 4)
        rows.append(row)
    rows.sort(
        key=lambda r: (
            _pair_result_rank(r),
            int(r.get("deep_audio_anchor_count") or 0),
            float(r.get("deep_audio_median_similarity") or 0.0),
            float(r.get("candidate_score") or 0.0),
        ),
        reverse=True,
    )
    return rows[:DEEP_RESOLUTION_MAX_VODS]


def _evaluate_global_audio_pair(vod: dict[str, Any], video: dict[str, Any], youtube_fp: dict[str, Any], twitch_fp: dict[str, Any], *, log=None) -> dict[str, Any]:
    evidence = score_candidate(vod, video, configured_channel=True)
    date_signal = (evidence.get("signals") or {}).get("date") or {}
    date_score = float(date_signal.get("score")) if date_signal.get("available") and date_signal.get("score") is not None else None
    result: dict[str, Any] = {
        "vod_id": str(vod.get("vod_id") or ""),
        "state": "candidate",
        "candidate_score": float(evidence.get("candidate_score") or 0.0),
        "candidate_evidence": evidence,
        "evaluated_at": C.utc_now(),
        "policy_version": VERIFICATION_POLICY_VERSION,
        "matcher_engine": "not_run",
        "timeline_segments": [],
        "audio": {"method": AUDIO_VERIFIER_PROVIDER, "anchors": [], "assessment": {"state": "not_run"}},
    }
    # Exact upload metadata may cheaply exclude a later VOD. Unknown dates stay
    # eligible; audio is the authority for every plausible source.
    if date_score is not None and date_score <= 0.02:
        result["reason"] = "known upload date predates this Twitch VOD"
        result["audio"]["assessment"] = {"state": "not_run", "reason": result["reason"]}
        return result
    duration = float(video.get("duration") or youtube_fp.get("duration_seconds") or 0.0)
    if duration <= 0:
        result["reason"] = "YouTube duration unavailable"
        result["audio"]["assessment"] = {"state": "not_run", "reason": result["reason"]}
        return result
    anchors = _audio_only_anchors_from_caches(duration, youtube_fp, twitch_fp, log=log)
    assessment = assess_verification(anchors)
    result["state"] = str(assessment.get("state") or "candidate")
    result["matcher_engine"] = _current_matcher_engine()
    result["audio"] = {"method": AUDIO_VERIFIER_PROVIDER, "anchors": anchors, "assessment": assessment}
    result["timeline_segments"] = _piecewise_segments(anchors)
    return result


def _persist_global_pair_result(root: str, slug: str, vod: dict[str, Any], video: dict[str, Any], result: dict[str, Any], *, force: bool = False, create_candidate: bool = False) -> dict[str, Any] | None:
    vod_id = str(vod.get("vod_id") or "")
    video_id = str(video.get("video_id") or "")
    prior = load_match(root, slug, vod_id, video_id) or {}
    if prior.get("state") == "rejected" and not force:
        return prior
    state = str(result.get("state") or "candidate")
    if not prior and state == "candidate" and not create_candidate:
        return None
    transcript_evidence = result.get("transcript") if isinstance(result.get("transcript"), dict) else None
    audio_assessment = ((result.get("audio") or {}).get("assessment") or {})
    audio_ran = str(audio_assessment.get("state") or "") != "not_run"
    verification = {
        "status": "complete",
        "policy_version": VERIFICATION_POLICY_VERSION,
        "matcher_engine": str(result.get("matcher_engine") or "not_run"),
        "completed_at": C.utc_now(),
        "mode": "global-audio+localized-text" if transcript_evidence else "global-audio-assignment",
        "providers": {"metadata": "complete", "audio": "complete" if audio_ran else "not_run", "transcript": "localized_complete" if transcript_evidence else "not_run"},
        "transcript": ({
            **transcript_evidence,
            "strategy": "bounded-global-localized-tiebreak",
            "full_source_whisper": False,
        } if transcript_evidence else {
            "method": LOCALIZED_TRANSCRIPT_PROVIDER, "anchors": [], "assessment": {"state": "not_run"},
            "strategy": "bounded-global-localized-tiebreak", "full_source_whisper": False,
        }),
        "audio": result.get("audio") or {},
    }
    manifest = {
        **prior,
        "schema_version": SCHEMA_VERSION,
        "youtube_video_id": video_id,
        "youtube": dict(video),
        "twitch_vod_ids": [vod_id],
        "twitch": dict(vod),
        "streamer": str(vod.get("streamer") or video.get("streamer") or ""),
        "state": state,
        "candidate_score": float(result.get("candidate_score") or 0.0),
        "candidate_evidence": result.get("candidate_evidence") or {},
        "verification": verification,
        "timeline_segments": list(result.get("timeline_segments") or []),
        "download": prior.get("download") or {"status": "not_downloaded", "path": ""},
        "rights_status": "sem_autorizacao_confirmada",
        "global_assignment": True,
    }
    save_match(root, slug, manifest)
    return manifest


def _maybe_localized_confirm_global_pair(root: str, slug: str, *, vod: dict[str, Any], video: dict[str, Any],
                                         pair_result: dict[str, Any], youtube_analysis: dict[str, Any],
                                         twitch_analysis: dict[str, Any], log=None) -> dict[str, Any]:
    """Use captions/Whisper only for the best unresolved global assignment."""
    if str(pair_result.get("state") or "") not in {"likely", "ambiguous", "candidate"}:
        return pair_result
    audio_count, audio_median = _deep_audio_stats(pair_result)
    if audio_count < DEEP_RESOLUTION_MIN_AUDIO_ANCHORS:
        return pair_result
    if audio_median < DEEP_RESOLUTION_AUDIO_MEDIAN_MIN:
        return pair_result
    if not transcript_enabled(root) or not transcription_backend(root):
        return pair_result
    try:
        evidence = confirm_audio_anchors_with_localized_transcripts(
            root, slug,
            vod_id=str(vod.get("vod_id") or ""),
            video_id=str(video.get("video_id") or ""),
            streamer=str(vod.get("streamer") or ""),
            twitch_url=str(vod.get("source_url") or ""),
            youtube_url=str(video.get("url") or f"https://www.youtube.com/watch?v={video.get('video_id','')}"),
            anchors=list((pair_result.get("audio") or {}).get("anchors") or []),
            twitch_fp=twitch_analysis.get("fingerprint") or {},
            youtube_fp=youtube_analysis.get("fingerprint") or {},
            twitch_media=str(twitch_analysis.get("media_path") or ""),
            youtube_media=str(youtube_analysis.get("media_path") or ""),
            log=log,
        )
    except Exception as exc:
        if log:
            log.write(f"global localized confirmation unavailable: {exc}\n")
            log.flush()
        return pair_result
    pair_result = dict(pair_result)
    pair_result["transcript"] = evidence
    pair_result["deep_audio_anchor_count"] = audio_count
    pair_result["deep_audio_median_similarity"] = round(audio_median, 4)
    text_assessment = evidence.get("assessment") or {}
    if str(text_assessment.get("state") or "") in {"strong", "likely"} and int(text_assessment.get("good_anchors") or 0) >= 2:
        # Two independent acoustic anchors plus two localized text confirmations
        # are sufficient only after global all-VOD competition has reduced the
        # risk of a local false peak.
        pair_result["state"] = "verified"
        pair_result["verification_basis"] = "global-audio+localized-text"
    return pair_result


def _resolve_global_assignments(root: str, slug: str, *, streamer: str = "", vod_id: str = "",
                                download: bool = False, no_download: bool = False, force: bool = False, log=None) -> dict[str, Any]:
    if _np is None:
        raise C.StudioError(
            "NumPy is required for global YouTube mirror assignment. "
            "Run `python -m pip install -e .` in the same Python environment that starts the dashboard, then restart it."
        )
    vods, pool = _discover_global_video_pool(root, slug, streamer=streamer, vod_id=vod_id, log=log)
    vods_by_streamer: dict[str, list[dict[str, Any]]] = {}
    for vod in vods:
        vods_by_streamer.setdefault(str(vod.get("streamer") or "").lower(), []).append(vod)
    for rows in vods_by_streamer.values():
        rows.sort(key=lambda v: str(v.get("created_at") or ""))

    errors: list[dict[str, Any]] = []
    completed: list[dict[str, Any]] = []
    resumed = 0
    evaluated_pairs = 0
    skipped_pairs = 0
    deepened_pairs = 0
    twitch_analysis_cache: dict[str, dict[str, Any]] = {}
    total = len(pool)
    if log:
        log.write(
            f"global source assignment: videos={total} vods={len(vods)} matcher={'numpy-exact' if _np is not None else 'stdlib-coarse'} "
            f"policy={VERIFICATION_POLICY_VERSION}\n"
        )
        log.flush()

    for number, item in enumerate(pool, 1):
        video = dict(item.get("video") or {})
        video_id = str(video.get("video_id") or "")
        st = str(item.get("streamer") or video.get("streamer") or "").lower()
        eligible_vods = vods_by_streamer.get(st, [])
        eligible_ids = [str(v.get("vod_id") or "") for v in eligible_vods]
        if not video_id or not eligible_ids:
            continue
        assignment = load_assignment(root, slug, video_id)
        if not force and _assignment_complete_for_vods(assignment, eligible_ids):
            resumed += 1
            completed.append(dict(assignment or {}))
            if not no_download and str((assignment or {}).get("state") or "") == "verified":
                cfg = load_config(root)
                if download or cfg.get("auto_download_verified"):
                    primary_vod_id = str((assignment or {}).get("primary_vod_id") or "")
                    manifest = load_match(root, slug, primary_vod_id, video_id) if primary_vod_id else None
                    if manifest and str((manifest.get("download") or {}).get("status") or "") != "completed":
                        download_verified(root, slug, primary_vod_id, video_id, log=log)
            if log:
                log.write(f"assignment {number}/{total}: youtube={video_id} resume=completed -> skip all {len(eligible_ids)} VODs\n")
                log.flush()
            continue
        if not isinstance(assignment, dict) or force or str(assignment.get("policy_version") or "") != VERIFICATION_POLICY_VERSION:
            assignment = {
                "youtube_video_id": video_id,
                "streamer": st,
                "status": "running",
                "created_at": C.utc_now(),
                "evaluated_vod_ids": [],
                "pair_results": {},
            }
        else:
            if str(assignment.get("matcher_engine") or "") != _current_matcher_engine():
                # Deep text decisions are tied to the acoustic locations they
                # confirmed. When migrating an old coarse matcher checkpoint,
                # preserve fingerprints/pair metadata but rebuild deep evidence.
                assignment.pop("deep_resolution", None)
            assignment["status"] = "running"
        assignment["matcher_engine"] = _current_matcher_engine()
        assignment["youtube"] = video
        assignment["candidate_discovery"] = {
            "best_candidate_score": item.get("best_candidate_score"),
            "best_candidate_vod_id": item.get("best_candidate_vod_id"),
            "best_chapter_shared_tokens": item.get("best_chapter_shared_tokens"),
            "reasons": list(item.get("discovery_reasons") or []),
            "index_position": item.get("index_position"),
            "publish_time": item.get("publish_time"),
        }
        save_assignment(root, slug, assignment)
        if log:
            already = len(set(map(str, assignment.get("evaluated_vod_ids") or [])) & set(eligible_ids))
            log.write(f"assignment {number}/{total}: youtube={video_id} evaluated={already}/{len(eligible_ids)}\n")
            log.flush()
        try:
            try:
                video = enrich_video_metadata_cached(root, slug, video, force=force, log=log)
            except Exception as exc:
                if log:
                    log.write(f"metadata enrichment unavailable for youtube={video_id}; continuing with index metadata: {exc}\n")
                    log.flush()
            youtube_analysis = _ensure_media_analysis(
                root, slug, source_kind="youtube", source_id=video_id,
                source_url=str(video.get("url") or f"https://www.youtube.com/watch?v={video_id}"),
                streamer=st, force=force, log=log, want_transcript=False, keep_media=False,
            )
            youtube_fp = youtube_analysis.get("fingerprint") or {}
            if not youtube_fp.get("features"):
                raise C.StudioError("YouTube audio fingerprint unavailable")
            assignment["youtube"] = video
            assignment["youtube_fingerprint"] = _fingerprint_signature(youtube_fp)
            pair_results = dict(assignment.get("pair_results") or {})
            evaluated_ids = {str(x) for x in (assignment.get("evaluated_vod_ids") or [])}

            for vod in eligible_vods:
                current_vod_id = str(vod.get("vod_id") or "")
                existing_pair = pair_results.get(current_vod_id)
                if not force and current_vod_id in evaluated_ids and _pair_result_reusable(existing_pair):
                    skipped_pairs += 1
                    continue
                if not force and current_vod_id in evaluated_ids and isinstance(existing_pair, dict) and log:
                    log.write(
                        f"pair checkpoint replay: youtube={video_id} vod={current_vod_id} "
                        f"old_matcher={existing_pair.get('matcher_engine') or 'legacy'} "
                        f"new_matcher={_current_matcher_engine()}\n"
                    )
                    log.flush()
                prior = load_match(root, slug, current_vod_id, video_id)
                if prior and prior.get("state") == "rejected" and not force:
                    pair_result = {
                        "vod_id": current_vod_id, "state": "rejected", "candidate_score": float(prior.get("candidate_score") or 0.0),
                        "reason": "manual rejection preserved", "evaluated_at": C.utc_now(), "policy_version": VERIFICATION_POLICY_VERSION,
                        "matcher_engine": "not_run",
                    }
                else:
                    # Cheap date scoring can avoid preparing a Twitch fingerprint
                    # for a pair that is chronologically impossible.
                    evidence = score_candidate(vod, video, configured_channel=True)
                    date_signal = (evidence.get("signals") or {}).get("date") or {}
                    date_score = float(date_signal.get("score")) if date_signal.get("available") and date_signal.get("score") is not None else None
                    if date_score is not None and date_score <= 0.02:
                        pair_result = {
                            "vod_id": current_vod_id, "state": "candidate", "candidate_score": float(evidence.get("candidate_score") or 0.0),
                            "candidate_evidence": evidence, "reason": "known upload date predates this Twitch VOD",
                            "evaluated_at": C.utc_now(), "policy_version": VERIFICATION_POLICY_VERSION,
                            "matcher_engine": "not_run",
                            "timeline_segments": [], "audio": {"method": AUDIO_VERIFIER_PROVIDER, "anchors": [], "assessment": {"state": "not_run"}},
                        }
                    else:
                        twitch_analysis = twitch_analysis_cache.get(current_vod_id)
                        if twitch_analysis is None:
                            twitch_analysis = _ensure_media_analysis(
                                root, slug, source_kind="twitch", source_id=current_vod_id,
                                source_url=str(vod.get("source_url") or ""), streamer=st,
                                force=force, log=log, want_transcript=False, keep_media=False,
                            )
                            twitch_analysis_cache[current_vod_id] = twitch_analysis
                        twitch_fp = twitch_analysis.get("fingerprint") or {}
                        if not twitch_fp.get("features"):
                            raise C.StudioError(f"Twitch audio fingerprint unavailable: {current_vod_id}")
                        pair_result = _evaluate_global_audio_pair(vod, video, youtube_fp, twitch_fp, log=log)
                        pair_result["twitch_fingerprint"] = _fingerprint_signature(twitch_fp)
                    evaluated_pairs += 1

                pair_results[current_vod_id] = pair_result
                evaluated_ids.add(current_vod_id)
                assignment["pair_results"] = pair_results
                assignment["evaluated_vod_ids"] = sorted(evaluated_ids)
                save_assignment(root, slug, assignment)
                _persist_global_pair_result(root, slug, vod, video, pair_result, force=force)

            ranked = sorted(
                [r for r in pair_results.values() if isinstance(r, dict) and str(r.get("state") or "") != "rejected"],
                key=_pair_result_rank,
                reverse=True,
            )

            # Stage 2: bounded deep tiebreak. Pair checkpoints above remain cheap
            # and reusable. Only unresolved pairs with >=2 moderately strong
            # localized acoustic anchors can spend captions/Whisper work, and the
            # attempt list is checkpointed separately so restarts continue here.
            verified_before_deep = any(str(r.get("state") or "") == "verified" for r in ranked)
            deep = assignment.get("deep_resolution") if isinstance(assignment.get("deep_resolution"), dict) else {}
            if str(deep.get("policy_version") or "") != DEEP_RESOLUTION_POLICY_VERSION:
                deep = {
                    "policy_version": DEEP_RESOLUTION_POLICY_VERSION,
                    "status": "pending",
                    "attempted_vod_ids": [],
                    "candidate_vod_ids": [],
                    "attempts": {},
                }
            if verified_before_deep:
                deep.update({
                    "status": "completed",
                    "reason": "direct acoustic verification",
                    "completed_at": C.utc_now(),
                })
            else:
                deep_candidates = _deep_resolution_candidates(pair_results)
                candidate_ids = [str(r.get("vod_id") or "") for r in deep_candidates]
                deep["candidate_vod_ids"] = candidate_ids
                attempted_ids = {str(x) for x in (deep.get("attempted_vod_ids") or [])}
                attempts = dict(deep.get("attempts") or {})

                if not deep_candidates:
                    deep.update({
                        "status": "completed",
                        "reason": "no unresolved pair has enough localized acoustic evidence for text tiebreak",
                        "completed_at": C.utc_now(),
                    })
                elif not transcript_enabled(root) or not transcription_backend(root):
                    deep.update({
                        "status": "blocked",
                        "reason": "localized transcript backend unavailable",
                    })
                else:
                    deep["status"] = "running"
                    for candidate in deep_candidates:
                        deep_vod_id = str(candidate.get("vod_id") or "")
                        if not deep_vod_id or deep_vod_id in attempted_ids:
                            continue
                        deep_vod = next((v for v in eligible_vods if str(v.get("vod_id") or "") == deep_vod_id), None)
                        if not deep_vod:
                            continue
                        deep_twitch = twitch_analysis_cache.get(deep_vod_id)
                        if deep_twitch is None:
                            deep_twitch = _ensure_media_analysis(
                                root, slug, source_kind="twitch", source_id=deep_vod_id,
                                source_url=str(deep_vod.get("source_url") or ""), streamer=st,
                                force=False, log=log, want_transcript=False, keep_media=False,
                            )
                            twitch_analysis_cache[deep_vod_id] = deep_twitch
                        confirmed = _maybe_localized_confirm_global_pair(
                            root, slug, vod=deep_vod, video=video, pair_result=candidate,
                            youtube_analysis=youtube_analysis, twitch_analysis=deep_twitch, log=log,
                        )
                        transcript_evidence = confirmed.get("transcript") if isinstance(confirmed, dict) else None
                        if not isinstance(transcript_evidence, dict):
                            # The helper intentionally leaves transient download /
                            # transcription failures retryable on the next run.
                            deep["status"] = "partial"
                            deep["reason"] = f"localized confirmation unavailable for VOD {deep_vod_id}; retryable"
                            break
                        deepened_pairs += 1
                        attempted_ids.add(deep_vod_id)
                        attempts[deep_vod_id] = {
                            "state": str(confirmed.get("state") or "candidate"),
                            "assessment": transcript_evidence.get("assessment") or {},
                            "attempted_at": C.utc_now(),
                        }
                        pair_results[deep_vod_id] = confirmed
                        _persist_global_pair_result(
                            root, slug, deep_vod, video, confirmed,
                            force=force, create_candidate=True,
                        )
                        assignment["pair_results"] = pair_results
                        deep["attempted_vod_ids"] = sorted(attempted_ids)
                        deep["attempts"] = attempts
                        assignment["deep_resolution"] = deep
                        save_assignment(root, slug, assignment)
                        if str(confirmed.get("state") or "") == "verified":
                            deep.update({
                                "status": "completed",
                                "reason": f"localized text verified VOD {deep_vod_id}",
                                "completed_at": C.utc_now(),
                            })
                            break
                    else:
                        if set(candidate_ids).issubset(attempted_ids):
                            deep.update({
                                "status": "completed",
                                "reason": "all bounded deep-resolution candidates exhausted",
                                "completed_at": C.utc_now(),
                            })
                        else:
                            deep["status"] = "partial"
                            deep["reason"] = "deep-resolution candidates remain"

                    deep["attempted_vod_ids"] = sorted(attempted_ids)
                    deep["attempts"] = attempts
            assignment["deep_resolution"] = deep

            ranked = sorted(
                [r for r in pair_results.values() if isinstance(r, dict) and str(r.get("state") or "") != "rejected"],
                key=_pair_result_rank,
                reverse=True,
            )
            top = ranked[0] if ranked else None
            verified_rows = [r for r in ranked if str(r.get("state") or "") == "verified"]
            if verified_rows:
                primary = verified_rows[0]
                assignment_state = "verified"
                assigned_ids = [str(r.get("vod_id") or "") for r in verified_rows]
            elif top and str(top.get("state") or "") == "likely":
                primary = top
                assignment_state = "likely"
                assigned_ids = [str(top.get("vod_id") or "")]
            elif top and str(top.get("state") or "") == "ambiguous":
                primary = top
                assignment_state = "ambiguous"
                assigned_ids = []
            else:
                primary = top
                assignment_state = "unmatched"
                assigned_ids = []
            assignment.update({
                "status": "completed",
                "state": assignment_state,
                "primary_vod_id": str(primary.get("vod_id") or "") if primary else "",
                "assigned_vod_ids": assigned_ids,
                "pair_results": pair_results,
                "evaluated_vod_ids": sorted(evaluated_ids),
                "matcher_engine": _current_matcher_engine(),
                "completed_at": C.utc_now(),
            })
            save_assignment(root, slug, assignment)
            completed.append(dict(assignment))
            if primary and assignment_state in {"verified", "likely"}:
                primary_vod = next((v for v in eligible_vods if str(v.get("vod_id") or "") == str(primary.get("vod_id") or "")), None)
                if primary_vod:
                    manifest = _persist_global_pair_result(
                        root, slug, primary_vod, video, primary, force=force, create_candidate=True,
                    )
                    if manifest and assignment_state == "verified" and not no_download:
                        cfg = load_config(root)
                        if download or cfg.get("auto_download_verified"):
                            if str((manifest.get("download") or {}).get("status") or "") != "completed":
                                download_verified(root, slug, str(primary.get("vod_id") or ""), video_id, log=log)
            if log:
                log.write(
                    f"assignment result: youtube={video_id} state={assignment_state} "
                    f"primary_vod={assignment.get('primary_vod_id') or '-'} assigned={','.join(assigned_ids) or '-'}\n"
                )
                log.flush()
        except Exception as exc:
            assignment["status"] = "partial"
            assignment["error"] = str(exc)[:1500]
            save_assignment(root, slug, assignment)
            errors.append({"video_id": video_id, "error": str(exc)})
            if log:
                log.write(f"assignment failed/partial youtube={video_id}: {exc}\n")
                log.flush()

    return {
        "videos": total,
        "completed": len(completed),
        "resumed": resumed,
        "evaluated_pairs": evaluated_pairs,
        "skipped_pairs": skipped_pairs,
        "deepened_pairs": deepened_pairs,
        "verified": sum(1 for a in completed if str(a.get("state") or "") == "verified"),
        "likely": sum(1 for a in completed if str(a.get("state") or "") == "likely"),
        "errors": errors,
        "assignments": completed,
    }


def resolve(root: str, slug: str, *, streamer: str = "", vod_id: str = "", refresh_index: bool = False,
            download: bool = False, no_download: bool = False, force: bool = False, verify_likely: bool = True, log=None) -> dict[str, Any]:
    if refresh_index:
        index_all(root, slug, streamer=streamer, force=force, log=log)
    candidates = generate_candidates(root, slug, streamer=streamer, vod_id=vod_id, log=log)
    verified=[]; errors=[]
    if verify_likely:
        global_result = _resolve_global_assignments(
            root, slug, streamer=streamer, vod_id=vod_id,
            download=download, no_download=no_download, force=force, log=log,
        )
        errors.extend(global_result.get("errors") or [])
        return {
            "candidates": candidates["candidates"],
            "verified": int(global_result.get("verified") or 0),
            "likely": int(global_result.get("likely") or 0),
            "errors": errors,
            "resume": {
                "videos": int(global_result.get("videos") or 0),
                "completed": int(global_result.get("completed") or 0),
                "resumed": int(global_result.get("resumed") or 0),
                "evaluated_pairs": int(global_result.get("evaluated_pairs") or 0),
                "skipped_pairs": int(global_result.get("skipped_pairs") or 0),
                "deepened_pairs": int(global_result.get("deepened_pairs") or 0),
            },
            "assignments": global_result.get("assignments") or [],
            "matches": list_matches(root,slug,vod_id),
        }
    return {"candidates": candidates["candidates"], "verified": len(verified), "errors": errors, "matches": list_matches(root,slug,vod_id)}

def _job_path(root: str, slug: str, job_id: str) -> str:
    return os.path.join(_ensure_layout(root, slug), "jobs", f"{job_id}.json")


def _job_log_path(root: str, slug: str, job_id: str) -> str:
    return os.path.join(_ensure_layout(root, slug), "logs", f"{job_id}.log")


def _write_job(root: str, slug: str, rec: dict[str, Any]) -> None:
    C.write_json(_job_path(root,slug,rec["id"]),rec)


def read_job(root: str, slug: str, job_id: str) -> dict[str, Any] | None:
    return C.read_json(_job_path(root,slug,job_id),None)


def list_jobs(root: str, slug: str, limit: int = 20) -> list[dict[str, Any]]:
    d=os.path.join(_ensure_layout(root,slug),"jobs")
    rows=[]
    for name in os.listdir(d):
        if name.endswith(".json"):
            r=C.read_json(os.path.join(d,name),None)
            if isinstance(r,dict): rows.append(r)
    rows.sort(key=lambda r:str(r.get("started_at") or r.get("created_at") or ""),reverse=True)
    return rows[:max(1,int(limit))]


def latest_job(root: str, slug: str) -> dict[str, Any] | None:
    rows=list_jobs(root,slug,1); return rows[0] if rows else None


def tail_job_log(root: str, slug: str, job_id: str | None = None, max_chars: int | None = 12000) -> str:
    rec=read_job(root,slug,job_id) if job_id else latest_job(root,slug)
    if not rec: return ""
    path=str(rec.get("log_path") or "")
    if not path or not os.path.isfile(path): return ""
    with open(path,"r",encoding="utf-8",errors="replace") as fh: text=fh.read()
    if max_chars is None:
        return text
    return text[-max(1000,int(max_chars)):]


def _job_worker(root: str, slug: str, rec: dict[str, Any], params: dict[str, Any]) -> None:
    key=(_abs_root(root),slug)
    log_path=rec["log_path"]
    rec["worker_pid"] = os.getpid()
    rec["worker_mode"] = str(rec.get("worker_mode") or "process")
    _write_job(root, slug, rec)
    try:
        with open(log_path,"a",encoding="utf-8",errors="replace") as log:
            log.write(f"[{C.utc_now()}] YouTube Mirror Resolver job {rec['type']} pid={os.getpid()}\n")
            typ=rec["type"]
            if typ=="index": result=index_all(root,slug,streamer=params.get("streamer","") or "",force=bool(params.get("force")),log=log)
            elif typ=="resolve": result=resolve(root,slug,streamer=params.get("streamer","") or "",vod_id=params.get("vod_id","") or "",refresh_index=bool(params.get("refresh_index")),download=bool(params.get("download")),no_download=bool(params.get("no_download")),force=bool(params.get("force")),verify_likely=bool(params.get("verify",True)),log=log)
            elif typ=="verify": result=verify_match(root,slug,str(params["vod_id"]),str(params["video_id"]),force=bool(params.get("force")),log=log)
            elif typ=="download": result=download_verified(root,slug,str(params["vod_id"]),str(params["video_id"]),force=bool(params.get("force")),log=log)
            else: raise C.StudioError(f"unknown YouTube resolver job type: {typ}")
            rec["result_summary"] = _compact_result(result)
            rec["status"]="completed"; rec["return_code"]=0; rec["error"]=""
    except Exception as exc:
        rec["status"]="failed"; rec["return_code"]=1; rec["error"]=str(exc)
        try:
            with open(log_path,"a",encoding="utf-8",errors="replace") as log: log.write(f"\nERROR: {exc}\n")
        except Exception: pass
    finally:
        rec["ended_at"]=C.utc_now(); _write_job(root,slug,rec)
        with _LOCK: _RUNNING.pop(key,None)


def _compact_result(result: Any) -> Any:
    if not isinstance(result,dict): return str(result)[:1000]
    keep={}
    for k,v in result.items():
        if k in {"matches","assignments","youtube","twitch","features"}: continue
        keep[k]=v
    return keep


def _new_job_record(root: str, slug: str, job_type: str, params: dict[str, Any]) -> dict[str, Any]:
    job_id=C.utc_now().replace("-","").replace(":","").replace("T","-").replace("Z","")+"-"+uuid.uuid4().hex[:6]
    return {
        "id":job_id,"type":job_type,"status":"running","slug":slug,
        "streamer":str(params.get("streamer") or ""),"vod_id":str(params.get("vod_id") or ""),
        "candidate_video_id":str(params.get("video_id") or ""),"created_at":C.utc_now(),
        "started_at":C.utc_now(),"ended_at":"","command":str(params.get("command") or job_type),
        "return_code":None,"error":"","artifacts":[],"log_path":_job_log_path(root,slug,job_id),
        "params":{k:v for k,v in params.items() if k!="command"},"worker_pid":0,"worker_mode":"process",
    }


def _handle_alive(handle: Any) -> bool:
    if handle is None:
        return False
    poll = getattr(handle, "poll", None)
    if callable(poll):
        try:
            return poll() is None
        except Exception:
            return False
    alive = getattr(handle, "is_alive", None)
    if callable(alive):
        try:
            return bool(alive())
        except Exception:
            return False
    return False


def _pid_alive_windows(pid: int) -> bool:
    """Check a Windows PID without sending it a signal.

    ``os.kill(pid, 0)`` is the conventional POSIX liveness probe, but on
    Windows non-console signals are implemented with TerminateProcess.  Use the
    native process handle API so a dashboard health check can never terminate
    its own detached resolver worker.
    """
    try:
        import ctypes
        from ctypes import wintypes

        process_query_limited_information = 0x1000
        still_active = 259
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(process_query_limited_information, False, int(pid))
        if not handle:
            # ERROR_ACCESS_DENIED still proves that a process owns this PID.
            return ctypes.get_last_error() == 5
        try:
            code = wintypes.DWORD()
            return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(code)) and code.value == still_active)
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return False


def _pid_alive(pid: Any) -> bool:
    try:
        value = int(pid or 0)
    except (TypeError, ValueError):
        return False
    if value <= 0:
        return False
    if value == os.getpid():
        return True
    if os.name == "nt":
        return _pid_alive_windows(value)
    try:
        os.kill(value, 0)
        return True
    except PermissionError:
        return True
    except (ProcessLookupError, OSError):
        return False


def _worker_command(root: str, slug: str, job_id: str) -> list[str]:
    return [
        sys.executable, "-m", "cstudio", "--root", _abs_root(root),
        "youtube-job-worker", slug, "--job-id", job_id,
    ]


def _spawn_job_process(root: str, slug: str, job_id: str) -> subprocess.Popen:
    kwargs: dict[str, Any] = {
        "cwd": _abs_root(root),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
        "env": _media_subprocess_env(),
    }
    if os.name == "nt":
        # Windows processes are independent of their parent by default; a new
        # process group is enough for lifecycle isolation.  Do not use
        # DETACHED_PROCESS here because it conflicts with CREATE_NO_WINDOW and
        # can cause child console tools to surface Terminal windows.
        kwargs["creationflags"] = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    else:
        kwargs["start_new_session"] = True
    return _popen_hidden(_worker_command(root, slug, job_id), **kwargs)


def run_persisted_job(root: str, slug: str, job_id: str) -> dict[str, Any]:
    """Entrypoint used by the detached worker process."""
    rec = read_job(root, slug, job_id)
    if not isinstance(rec, dict):
        raise C.StudioError(f"YouTube resolver job not found: {job_id}")
    if rec.get("status") != "running":
        return rec
    params = dict(rec.get("params") or {})
    rec["worker_pid"] = os.getpid()
    rec["worker_mode"] = "process"
    _write_job(root, slug, rec)
    _job_worker(root, slug, rec, params)
    return read_job(root, slug, job_id) or rec


def start_job(root: str, slug: str, job_type: str, **params: Any) -> dict[str, Any]:
    """Start a dashboard job in a detached process that survives server restarts."""
    C.load_project(root,slug); _ensure_layout(root,slug)
    if job_type not in {"index","resolve","verify","download"}: raise C.StudioError("invalid YouTube resolver job type")
    mark_stale_jobs_failed(root, slug)
    key=(_abs_root(root),slug)
    with _LOCK:
        existing=_RUNNING.get(key)
        if _handle_alive(existing): raise C.StudioError("a YouTube resolver job is already running for this production")
        disk_running=[j for j in list_jobs(root,slug,100) if j.get("status")=="running" and _pid_alive(j.get("worker_pid"))]
        if disk_running: raise C.StudioError("a YouTube resolver job is already running for this production")
        rec=_new_job_record(root, slug, job_type, params)
        _write_job(root,slug,rec)
        try:
            proc=_spawn_job_process(root, slug, rec["id"])
        except Exception as exc:
            rec["status"]="failed"; rec["ended_at"]=C.utc_now(); rec["return_code"]=1
            rec["error"]=f"could not start resolver worker: {exc}"
            _write_job(root,slug,rec)
            raise C.StudioError(rec["error"]) from exc
        _RUNNING[key]=proc
        # Merge only the PID into the latest on-disk record so a very fast worker
        # cannot be overwritten back to RUNNING by the launcher.
        current=read_job(root,slug,rec["id"]) or rec
        if current.get("status")=="running":
            current["worker_pid"]=proc.pid
            current["worker_mode"]="process"
            _write_job(root,slug,current)
        returned=dict(current)
        returned["worker_pid"]=int(returned.get("worker_pid") or proc.pid)
        return returned


def run_job(root: str, slug: str, job_type: str, **params: Any) -> dict[str, Any]:
    """Synchronous CLI path; records the same job schema without forking twice."""
    C.load_project(root,slug); _ensure_layout(root,slug)
    if job_type not in {"index","resolve","verify","download"}: raise C.StudioError("invalid YouTube resolver job type")
    mark_stale_jobs_failed(root, slug)
    running=[j for j in list_jobs(root,slug,100) if j.get("status")=="running" and _pid_alive(j.get("worker_pid"))]
    if running:
        raise C.StudioError("a YouTube resolver job is already running for this production")
    rec=_new_job_record(root,slug,job_type,params)
    rec["worker_mode"]="inline-cli"; rec["worker_pid"]=os.getpid()
    _write_job(root,slug,rec)
    _job_worker(root,slug,rec,dict(rec.get("params") or {}))
    return read_job(root,slug,rec["id"]) or rec


def mark_stale_jobs_failed(root: str, slug: str) -> int:
    """Fail only jobs whose persisted worker process is actually gone."""
    fixed=0
    key=(_abs_root(root),slug)
    with _LOCK:
        live=_RUNNING.get(key)
        if _handle_alive(live):
            return 0
        if live is not None:
            _RUNNING.pop(key,None)
    for rec in list_jobs(root,slug,100):
        if rec.get("status")!="running":
            continue
        if _pid_alive(rec.get("worker_pid")):
            continue
        rec["status"]="failed"; rec["ended_at"]=C.utc_now(); rec["return_code"]=1
        rec["error"]="resolver worker process is no longer running before job completion"
        _write_job(root,slug,rec); fixed+=1
    return fixed


def dashboard_state(root: str, slug: str) -> dict[str, Any]:
    mark_stale_jobs_failed(root,slug)
    return {
        "health": health(root),
        "config": load_config(root),
        "channels": configured_channels(root),
        "index": index_status(root,slug),
        "vods": list_twitch_vods(root,slug),
        "matches": list_matches(root,slug),
        "assignments": list_assignments(root,slug),
        "jobs": list_jobs(root,slug,10),
        "latest_job": latest_job(root,slug),
    }


def shutdown_jobs(timeout: float = 1.0) -> None:
    # Detached YouTube workers intentionally survive dashboard shutdown. Dropping
    # local Popen handles is enough; persisted PID/status lets the next server
    # instance reattach logically without killing useful work.
    with _LOCK:
        _RUNNING.clear()
