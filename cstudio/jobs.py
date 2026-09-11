"""Small persistent job runner for dashboard operations.

Long-running agent and Premiere preparation work runs outside the HTTP request and
survives dashboard restarts. Only a closed set of semantic job types is accepted.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import uuid
from typing import Any

from . import core as C

ALLOWED_TYPES = {
    "agent-proposal", "video-proposal", "video-proposal-refine",
    "source-download-twitch", "source-batch-download-twitch", "source-download-audio", "source-audio-transcribe",
    "source-batch-audio-transcribe", "source-transcribe", "source-prepare-vods",
    "video-candidate-precision",
    "premiere-doctor", "premiere-export",
}


def _base(root: str, slug: str) -> str:
    vdir, _ = C.load_project(root, slug)
    path = os.path.join(vdir, ".studio", "jobs")
    os.makedirs(os.path.join(path, "logs"), exist_ok=True)
    return path


def _job_path(root: str, slug: str, job_id: str) -> str:
    return os.path.join(_base(root, slug), f"{job_id}.json")


def _log_path(root: str, slug: str, job_id: str) -> str:
    return os.path.join(_base(root, slug), "logs", f"{job_id}.log")


def _write(root: str, slug: str, rec: dict) -> None:
    C.write_json(_job_path(root, slug, rec["id"]), rec)


def read_job(root: str, slug: str, job_id: str) -> dict | None:
    return C.read_json(_job_path(root, slug, job_id), None)


def list_jobs(root: str, slug: str, limit: int = 20) -> list[dict]:
    d = _base(root, slug)
    rows: list[dict] = []
    for name in os.listdir(d):
        if not name.endswith(".json"):
            continue
        item = C.read_json(os.path.join(d, name), None)
        if isinstance(item, dict):
            rows.append(item)
    rows.sort(key=lambda r: str(r.get("started_at") or r.get("created_at") or ""), reverse=True)
    return rows[:max(1, int(limit))]


def latest_job(root: str, slug: str, job_type: str = "") -> dict | None:
    for item in list_jobs(root, slug, 50):
        if not job_type or item.get("type") == job_type:
            return item
    return None


def tail_log(root: str, slug: str, job_id: str | None = None, max_chars: int = 12000) -> str:
    rec = read_job(root, slug, job_id) if job_id else latest_job(root, slug)
    if not rec:
        return ""
    path = str(rec.get("log_path") or "")
    if not path or not os.path.isfile(path):
        return ""
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    return text[-max(1000, int(max_chars)):]


def _job_session_id(rec: dict) -> str:
    """Recover a runner session from durable job metadata or its log.

    v2.2.5 and older jobs did not persist the Agy init conversation ID on a
    failed attempt, but the live stream log did.  Reading it here makes those
    attempts resumable after upgrading without guessing a global/latest Agy
    conversation.
    """
    session = rec.get("runner_session") if isinstance(rec.get("runner_session"), dict) else {}
    sid = str(session.get("session_id") or "").strip()
    if sid:
        return sid
    result = rec.get("result_summary") if isinstance(rec.get("result_summary"), dict) else {}
    sid = str(result.get("session_id") or "").strip()
    if sid:
        return sid
    path = str(rec.get("log_path") or "")
    if not path or not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()[-200000:]
    except OSError:
        return ""
    matches = re.findall(r"Agy stream started(?:\s*·)?\s*conversation=([^\s]+)", text, re.I)
    if matches:
        return str(matches[-1]).strip()
    matches = re.findall(r"session\s+id\s*:\s*([0-9A-Za-z_-]{8,})", text, re.I)
    return str(matches[-1]).strip() if matches else ""


def video_resume_candidate(root: str, slug: str, part: str, proposal_id: str = "", job_id: str = "") -> dict | None:
    """Return the latest failed same-part attempt that has an exact session ID.

    Part 1 is identified by the latest `video-proposal` job.  Part 2 is scoped
    to one proposal id.  A newer completed/running attempt suppresses an older
    failed session so the UI never resurrects stale work accidentally.
    """
    part = str(part or "").strip().lower()
    expected_type = "video-proposal" if part == "part1" else "video-proposal-refine" if part == "part2" else ""
    if not expected_type:
        raise C.StudioError(f"unknown video proposal part: {part}")
    proposal_id = str(proposal_id or "").strip()
    for rec in list_jobs(root, slug, 100):
        if rec.get("type") != expected_type:
            continue
        params = rec.get("params") if isinstance(rec.get("params"), dict) else {}
        if part == "part2" and str(params.get("proposal_id") or "") != proposal_id:
            continue
        if job_id and str(rec.get("id") or "") != str(job_id):
            # The first relevant row is the newest one. Never allow a stale
            # hidden resume_job_id to skip past a newer attempt.
            return None
        # Only the newest relevant attempt is eligible. If it is not failed, an
        # older session is stale by definition.
        if str(rec.get("status") or "") != "failed":
            return None
        sid = _job_session_id(rec)
        if not sid:
            return None
        if part == "part2":
            try:
                from . import video_plans as VP
                proposal = VP.get_video_proposal(root, slug, proposal_id)
                answers_updated = str(proposal.get("answers_updated_at") or "")
                started_at = str(rec.get("started_at") or rec.get("created_at") or "")
                if answers_updated and started_at and answers_updated > started_at:
                    return None
            except C.StudioError:
                return None
        session = rec.get("runner_session") if isinstance(rec.get("runner_session"), dict) else {}
        return {
            "job_id": str(rec.get("id") or ""),
            "part": part,
            "proposal_id": proposal_id,
            "session_id": sid,
            "runner": str(session.get("runner") or params.get("runner") or ""),
            "model": str(session.get("model") or params.get("model") or ""),
            "reasoning_effort": str(session.get("reasoning_effort") or params.get("reasoning_effort") or ""),
            "request": str(params.get("request") or ""),
            "source_asset_ids": list(params.get("source_asset_ids") or []),
            "started_at": str(rec.get("started_at") or ""),
        }
    return None


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
        try:
            import ctypes
            from ctypes import wintypes
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel32.OpenProcess.restype = wintypes.HANDLE
            kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            kernel32.GetExitCodeProcess.restype = wintypes.BOOL
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle.restype = wintypes.BOOL
            handle = kernel32.OpenProcess(0x1000, False, value)
            if not handle:
                return ctypes.get_last_error() == 5
            try:
                code = wintypes.DWORD()
                return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(code)) and code.value == 259)
            finally:
                kernel32.CloseHandle(handle)
        except Exception:
            return False
    try:
        os.kill(value, 0)
        return True
    except PermissionError:
        return True
    except (ProcessLookupError, OSError):
        return False


def mark_stale_failed(root: str, slug: str) -> int:
    fixed = 0
    for rec in list_jobs(root, slug, 100):
        if rec.get("status") == "running" and not _pid_alive(rec.get("worker_pid")):
            rec["status"] = "failed"
            rec["ended_at"] = C.utc_now()
            rec["return_code"] = 1
            rec["error"] = "worker process ended before job completion"
            _write(root, slug, rec)
            fixed += 1
    return fixed


def _new_record(root: str, slug: str, job_type: str, params: dict) -> dict:
    jid = C.utc_now().replace("-", "").replace(":", "").replace("T", "-").replace("Z", "") + "-" + uuid.uuid4().hex[:6]
    return {
        "id": jid,
        "type": job_type,
        "status": "running",
        "slug": slug,
        "created_at": C.utc_now(),
        "started_at": C.utc_now(),
        "ended_at": "",
        "return_code": None,
        "error": "",
        "worker_pid": 0,
        "log_path": _log_path(root, slug, jid),
        "params": params,
        "result_summary": {},
    }


def _worker_command(root: str, slug: str, job_id: str) -> list[str]:
    return [sys.executable, "-m", "cstudio", "--root", os.path.abspath(root), "job-worker", slug, "--job-id", job_id]


def _spawn(root: str, slug: str, job_id: str) -> subprocess.Popen:
    # Keep worker bootstrap errors observable.  The first implementation sent
    # stdout/stderr to DEVNULL, which made a Windows launch/import failure look
    # like the dashboard simply stopped doing anything.  The persisted job log
    # is safe to share with the actual worker because both writers append only.
    log_path = _log_path(root, slug, job_id)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    bootstrap_log = open(log_path, "ab", buffering=0)
    kwargs: dict[str, Any] = {
        "cwd": os.path.abspath(root),
        "stdin": subprocess.DEVNULL,
        "stdout": bootstrap_log,
        "stderr": subprocess.STDOUT,
        "close_fds": True,
    }
    if os.name == "nt":
        # CREATE_NO_WINDOW is sufficient for a silent background worker.
        # CREATE_NEW_PROCESS_GROUP is intentionally avoided here: it adds no
        # value for these one-shot workers and has caused inconsistent launch
        # behaviour across Windows/Python combinations.
        kwargs["creationflags"] = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
    else:
        kwargs["start_new_session"] = True
    try:
        return subprocess.Popen(_worker_command(root, slug, job_id), **kwargs)
    finally:
        # Popen duplicates/owns the child handle; the dashboard must not keep a
        # second writer open for the lifetime of the server.
        bootstrap_log.close()


def start_job(root: str, slug: str, job_type: str, **params) -> dict:
    if job_type not in ALLOWED_TYPES:
        raise C.StudioError(f"unsupported dashboard job: {job_type}")
    C.load_project(root, slug)
    mark_stale_failed(root, slug)
    running = [j for j in list_jobs(root, slug, 100) if j.get("status") == "running" and _pid_alive(j.get("worker_pid"))]
    if running:
        raise C.StudioError("another production job is already running; wait for it to finish before starting a new one")
    rec = _new_record(root, slug, job_type, {k: v for k, v in params.items()})
    _write(root, slug, rec)
    try:
        proc = _spawn(root, slug, rec["id"])
    except Exception as exc:
        rec["status"] = "failed"
        rec["ended_at"] = C.utc_now()
        rec["return_code"] = 1
        rec["error"] = f"could not start worker: {exc}"
        _write(root, slug, rec)
        raise C.StudioError(rec["error"]) from exc
    current = read_job(root, slug, rec["id"]) or rec
    if current.get("status") == "running":
        current["worker_pid"] = proc.pid
        _write(root, slug, current)
    return current


def _run_agent(root: str, slug: str, params: dict, log) -> dict:
    from . import runners as R
    request = str(params.get("request") or "").strip()
    if len(request) < 12:
        raise C.StudioError("describe the agent objective with at least 12 characters")
    expected_stage = str(params.get("stage") or "")
    log.write(
        f"Stage: {expected_stage or 'current'}\n"
        f"Runner: {params.get('runner') or 'auto'}\n"
        f"Model: {params.get('model') or 'runner default'}\n"
        f"Reasoning: {params.get('reasoning_effort') or 'runner default'}\n\n"
    )
    log.flush()
    result = R.execute_runner(
        root,
        slug,
        request,
        force_runner=str(params.get("runner") or ""),
        model=str(params.get("model") or ""),
        reasoning_effort=str(params.get("reasoning_effort") or ""),
        timeout=int(params.get("timeout") or 1200),
        expected_stage=expected_stage,
        log=log,
    )
    proposal = result.get("proposal") or {}
    return {
        "runner": result.get("runner"),
        "model": result.get("model") or str(params.get("model") or ""),
        "reasoning_effort": result.get("reasoning_effort") or str(params.get("reasoning_effort") or ""),
        "proposal_id": proposal.get("id"),
        "summary": proposal.get("summary", ""),
    }


def _run_video_proposal(root: str, slug: str, params: dict, log, refine: bool = False, session_callback=None) -> dict:
    from . import runners as R
    request = str(params.get("request") or "").strip()
    source_ids = params.get("source_asset_ids") or []
    if isinstance(source_ids, str):
        source_ids = [x for x in source_ids.split(",") if x]
    proposal_id = str(params.get("proposal_id") or "") if refine else ""
    continue_attempt = bool(params.get("continue_attempt"))
    resume_job_id = str(params.get("resume_job_id") or "").strip()
    resume_session_id = ""

    if continue_attempt:
        candidate = video_resume_candidate(
            root, slug, "part2" if refine else "part1",
            proposal_id=proposal_id, job_id=resume_job_id,
        )
        if not candidate:
            raise C.StudioError("the selected same-part attempt is no longer resumable")
        resume_session_id = str(candidate.get("session_id") or "")
        # Continuation is bound to the exact runner settings and original part
        # inputs. The model receives only `Continue.`; these values are retained
        # for validation and durable proposal metadata, not resent as context.
        params["runner"] = str(candidate.get("runner") or "")
        params["model"] = str(candidate.get("model") or "")
        params["reasoning_effort"] = str(candidate.get("reasoning_effort") or "")
        request = str(candidate.get("request") or request)
        if not refine:
            source_ids = list(candidate.get("source_asset_ids") or [])

    if len(request) < 12:
        raise C.StudioError("describe the video objective/refinement with at least 12 characters")

    log.write(
        f"Video proposal: {'refine' if refine else 'create'}\n"
        f"Runner: {params.get('runner') or 'auto'}\n"
        f"Model: {params.get('model') or 'runner default'}\n"
        f"Reasoning: {params.get('reasoning_effort') or 'runner default'}\n"
        f"Sources: {len(source_ids)}\n"
        f"Continue previous attempt: {'yes' if continue_attempt else 'no'}"
        + (f" · prior_job={resume_job_id} · session={resume_session_id}" if continue_attempt else "")
        + "\n\n"
    )
    log.flush()
    result = R.execute_video_runner(
        root, slug, request, list(source_ids),
        force_runner=str(params.get("runner") or ""),
        model=str(params.get("model") or ""),
        reasoning_effort=str(params.get("reasoning_effort") or ""),
        timeout=int(params.get("timeout") or 1200),
        proposal_id=proposal_id,
        resume_session_id=resume_session_id,
        continue_attempt=continue_attempt,
        session_callback=session_callback,
        log=log,
    )
    proposal = result.get("proposal") or {}
    return {
        "runner": result.get("runner"), "model": result.get("model"),
        "reasoning_effort": result.get("reasoning_effort"),
        "session_id": result.get("session_id") or resume_session_id,
        "continued": continue_attempt,
        "video_proposal_id": proposal.get("id"), "revision": proposal.get("revision"),
        "summary": proposal.get("summary", ""), "usage": result.get("usage") or {},
    }

def _run_source_download_twitch(root: str, slug: str, params: dict, log) -> dict:
    from . import source_media as SM
    vod_id = str(params.get("vod_id") or "").strip()
    if not vod_id:
        raise C.StudioError("vod_id is required")
    result = SM.download_twitch_vod(root, slug, vod_id, force=bool(params.get("force")), log=log)
    return {
        "vod_id": vod_id,
        "asset_id": result.get("asset_id"),
        "path": result.get("path"),
        "bytes": result.get("bytes"),
        "status": result.get("status"),
    }


def _run_source_batch_download_twitch(root: str, slug: str, params: dict, log) -> dict:
    from . import source_media as SM
    vod_ids = params.get("vod_ids") or []
    if isinstance(vod_ids, str):
        vod_ids = [x for x in vod_ids.split(",") if x]
    ids = list(dict.fromkeys(str(x).strip() for x in vod_ids if str(x).strip()))
    if not ids:
        raise C.StudioError("select at least one Twitch VOD")
    items = []
    for index, vod_id in enumerate(ids, 1):
        log.write(f"\n=== Full source download {index}/{len(ids)}: Twitch {vod_id} ===\n")
        log.flush()
        rec = SM.download_twitch_vod(root, slug, vod_id, force=bool(params.get("force")), log=log)
        items.append({"vod_id": vod_id, "asset_id": rec.get("asset_id"), "bytes": rec.get("bytes")})
    return {"vods_requested": len(ids), "vods_downloaded": len(items), "items": items}


def _run_source_download_audio(root: str, slug: str, params: dict, log) -> dict:
    from . import source_media as SM
    vod_id = str(params.get("vod_id") or "").strip()
    if not vod_id:
        raise C.StudioError("vod_id is required")
    result = SM.download_twitch_audio(root, slug, vod_id, force=bool(params.get("force")), log=log)
    return {
        "vod_id": vod_id,
        "temp_path": result.get("temp_path"),
        "bytes": result.get("bytes"),
        "status": result.get("status"),
        "temporary": True,
    }


def _run_source_audio_transcribe(root: str, slug: str, params: dict, log) -> dict:
    from . import source_media as SM
    vod_id = str(params.get("vod_id") or "").strip()
    if not vod_id:
        raise C.StudioError("vod_id is required")
    result = SM.transcribe_twitch_audio(
        root, slug, vod_id,
        download_if_missing=bool(params.get("download_if_missing", True)),
        cleanup_after=bool(params.get("cleanup_after", True)),
        force=bool(params.get("force")), log=log,
    )
    return {
        "vod_id": vod_id,
        "asset_id": f"twitch-video-{vod_id}",
        "segment_count": result.get("segment_count"),
        "word_count": result.get("word_count"),
        "timestamp_mode": result.get("timestamp_mode"),
        "source_mode": result.get("source_mode"),
        "temporary_audio_cleaned": bool(params.get("cleanup_after", True)),
    }


def _run_source_batch_audio_transcribe(root: str, slug: str, params: dict, log) -> dict:
    from . import source_media as SM
    vod_ids = params.get("vod_ids") or []
    if isinstance(vod_ids, str):
        vod_ids = [x for x in vod_ids.split(",") if x]
    ids = list(dict.fromkeys(str(x).strip() for x in vod_ids if str(x).strip()))
    if not ids:
        raise C.StudioError("select at least one Twitch VOD")
    completed = []
    failed = []
    for index, vod_id in enumerate(ids, 1):
        log.write(f"\n=== Audio discovery {index}/{len(ids)}: Twitch {vod_id} ===\n")
        log.flush()
        try:
            tr = SM.transcribe_twitch_audio(
                root, slug, vod_id, download_if_missing=True, cleanup_after=True,
                force=bool(params.get("force")), log=log,
            )
            completed.append({"vod_id": vod_id, "segments": tr.get("segment_count"), "timestamp_mode": tr.get("timestamp_mode")})
        except Exception as exc:
            failed.append({"vod_id": vod_id, "error": str(exc)[:1200]})
            log.write(f"FAILED VOD {vod_id}: {exc}\n")
            log.flush()
    if failed:
        summary = "; ".join(f"{x['vod_id']}: {x['error']}" for x in failed[:4])
        raise C.StudioError(f"audio discovery completed {len(completed)}/{len(ids)} VODs; failures: {summary}")
    return {"vods_requested": len(ids), "vods_transcribed": len(completed), "items": completed}


def _run_source_transcribe(root: str, slug: str, params: dict, log) -> dict:
    from . import source_media as SM
    asset_id = str(params.get("asset_id") or "").strip()
    if not asset_id:
        raise C.StudioError("asset_id is required")
    result = SM.transcribe_asset(root, slug, asset_id, force=bool(params.get("force")), log=log)
    return {
        "asset_id": asset_id,
        "segment_count": result.get("segment_count"),
        "word_count": result.get("word_count"),
        "duration_seconds": result.get("duration_seconds"),
        "model": result.get("model"),
        "language": result.get("language"),
    }


def _run_source_prepare_vods(root: str, slug: str, params: dict, log) -> dict:
    from . import source_media as SM
    vod_ids = params.get("vod_ids") or []
    if isinstance(vod_ids, str):
        vod_ids = [x for x in vod_ids.split(",") if x]
    result = SM.prepare_vods(
        root, slug, list(vod_ids), include_masters=bool(params.get("include_masters", True)), log=log
    )
    return {
        "vods_requested": result.get("vods_requested"),
        "vods_prepared": result.get("vods_prepared"),
        "include_masters": result.get("include_masters"),
    }


def _run_video_candidate_precision(root: str, slug: str, params: dict, log) -> dict:
    from . import source_media as SM
    video_id = str(params.get("video_id") or "").strip()
    if not video_id:
        raise C.StudioError("video_id is required")
    result = SM.generate_candidate_word_timestamps(
        root, slug, video_id,
        padding_seconds=float(params.get("padding_seconds") or 3.0),
        force=bool(params.get("force")), log=log,
    )
    return {
        "video_id": video_id,
        "candidate_count": result.get("candidate_count"),
        "word_count": result.get("word_count"),
        "timestamp_mode": result.get("timestamp_mode"),
    }


def _run_premiere_doctor(root: str, params: dict, log) -> dict:
    from . import nle as NLE
    driver = NLE.get_driver(str(params.get("driver") or ""), root=root)
    result = driver.doctor(timeout=int(params.get("timeout") or 60))
    log.write(str(result.get("doctor_output") or "No doctor output") + "\n")
    return {k: result.get(k) for k in ("driver", "available", "doctor_ok", "doctor_exit_code", "live_connection_verified")}


def _run_premiere_export(root: str, slug: str, params: dict, log) -> dict:
    from . import nle as NLE
    vdir, project = C.load_project(root, slug)
    timeline_path = os.path.join(vdir, ".studio", "internal", "assembly", "timeline.json")
    if not os.path.isfile(timeline_path):
        raise C.StudioError("timeline.json not found; finish the assembly artifact before preparing Premiere handoff")
    with open(timeline_path, encoding="utf-8") as fh:
        timeline = json.load(fh)
    if not isinstance(timeline, dict) or not list(timeline.get("events") or []):
        raise C.StudioError("timeline.json is still empty; finish assembly before preparing the Premiere handoff")
    driver = NLE.get_driver(str(params.get("driver") or ""), root=root)
    outdir = os.path.join(vdir, ".studio", "internal", "assembly", driver.name)
    result = driver.export(timeline, outdir, str(project.get("title") or slug))
    log.write("Prepared Premiere handoff:\n")
    for item in result.get("files", []):
        log.write(f" - {item}\n")
    return {"driver": result.get("driver"), "outdir": result.get("outdir"), "files": result.get("files", [])}


def run_persisted_job(root: str, slug: str, job_id: str) -> dict:
    rec = read_job(root, slug, job_id)
    if not isinstance(rec, dict):
        raise C.StudioError(f"job not found: {job_id}")
    if rec.get("status") != "running":
        return rec
    rec["worker_pid"] = os.getpid()
    _write(root, slug, rec)
    params = dict(rec.get("params") or {})

    def persist_runner_session(session: dict) -> None:
        if not isinstance(session, dict) or not str(session.get("session_id") or "").strip():
            return
        rec["runner_session"] = dict(session)
        rec["runner_session"]["captured_at"] = C.utc_now()
        _write(root, slug, rec)

    try:
        with open(rec["log_path"], "a", encoding="utf-8", errors="replace") as log:
            log.write(f"[{C.utc_now()}] Cuts Studio job {rec['type']} pid={os.getpid()}\n")
            log.flush()
            if rec["type"] == "agent-proposal":
                result = _run_agent(root, slug, params, log)
            elif rec["type"] == "video-proposal":
                result = _run_video_proposal(root, slug, params, log, refine=False, session_callback=persist_runner_session)
            elif rec["type"] == "video-proposal-refine":
                result = _run_video_proposal(root, slug, params, log, refine=True, session_callback=persist_runner_session)
            elif rec["type"] == "source-download-twitch":
                result = _run_source_download_twitch(root, slug, params, log)
            elif rec["type"] == "source-batch-download-twitch":
                result = _run_source_batch_download_twitch(root, slug, params, log)
            elif rec["type"] == "source-download-audio":
                result = _run_source_download_audio(root, slug, params, log)
            elif rec["type"] == "source-audio-transcribe":
                result = _run_source_audio_transcribe(root, slug, params, log)
            elif rec["type"] == "source-batch-audio-transcribe":
                result = _run_source_batch_audio_transcribe(root, slug, params, log)
            elif rec["type"] == "source-transcribe":
                result = _run_source_transcribe(root, slug, params, log)
            elif rec["type"] == "source-prepare-vods":
                result = _run_source_prepare_vods(root, slug, params, log)
            elif rec["type"] == "video-candidate-precision":
                result = _run_video_candidate_precision(root, slug, params, log)
            elif rec["type"] == "premiere-doctor":
                result = _run_premiere_doctor(root, params, log)
            elif rec["type"] == "premiere-export":
                result = _run_premiere_export(root, slug, params, log)
            else:
                raise C.StudioError(f"unsupported job type: {rec['type']}")
            rec["result_summary"] = result
            rec["status"] = "completed"
            rec["return_code"] = 0
            rec["error"] = ""
    except Exception as exc:
        rec["status"] = "failed"
        rec["return_code"] = 1
        rec["error"] = str(exc)
        try:
            with open(rec["log_path"], "a", encoding="utf-8", errors="replace") as log:
                log.write(f"\nERROR: {exc}\n")
        except Exception:
            pass
    rec["ended_at"] = C.utc_now()
    _write(root, slug, rec)
    return rec
