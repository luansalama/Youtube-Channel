"""Twitch scraper integration for Cuts Studio.

The bundled scraper is treated as an ingest tool: it writes immutable-ish raw
artifacts under the selected production, then this module registers the primary
VOD metadata/chat outputs in the normal ingest asset registry. It never advances
a stage, approves a gate, or changes rights clearance.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Any

from . import core as C
from . import pipeline as PL

_ALLOWED_THREADS = (1, 2, 4, 8)
_STREAMER_RE = re.compile(r"^[A-Za-z0-9_]{1,25}$")
_VOD_RE = re.compile(r"^https?://(?:www\.)?twitch\.tv/videos/\d{7,}(?:[/?#].*)?$", re.I)
_RUNNING: dict[tuple[str, str], threading.Thread] = {}
_RUNNING_PROCS: dict[tuple[str, str], subprocess.Popen] = {}
_LOCK = threading.RLock()


def scraper_dir(root: str) -> str:
    return os.path.join(os.path.abspath(root), "integrations", "twitch-scraper")


def output_dir(root: str, slug: str, streamer: str) -> str:
    vdir, _ = C.load_project(root, slug)
    return os.path.join(vdir, ".studio", "internal", "ingest", "twitch", streamer.lower())


def _runs_dir(root: str, slug: str) -> str:
    vdir, _ = C.load_project(root, slug)
    return os.path.join(vdir, ".studio", "internal", "ingest", "twitch", "runs")


def _run_path(root: str, slug: str, run_id: str) -> str:
    return os.path.join(_runs_dir(root, slug), f"{run_id}.json")


def _log_path(root: str, slug: str, run_id: str) -> str:
    return os.path.join(_runs_dir(root, slug), f"{run_id}.log")


def _write_run(root: str, slug: str, record: dict[str, Any]) -> None:
    C.write_json(_run_path(root, slug, record["id"]), record)


def _validate(streamer: str, target: str, threads: int) -> tuple[str, str, int]:
    streamer = str(streamer or "").strip()
    target = str(target or "").strip()
    if not _STREAMER_RE.fullmatch(streamer):
        raise C.StudioError("invalid Twitch channel (letters, numbers and underscore only)")
    if not target:
        target = "3"
    if target.isdigit():
        if int(target) <= 0:
            raise C.StudioError("latest-VOD count must be greater than zero")
    elif not _VOD_RE.fullmatch(target):
        raise C.StudioError("target must be a latest-VOD count, Twitch VOD id, or twitch.tv/videos URL")
    try:
        threads = int(threads)
    except (TypeError, ValueError):
        raise C.StudioError("threads must be one of 1, 2, 4, 8") from None
    if threads not in _ALLOWED_THREADS:
        raise C.StudioError("threads must be one of 1, 2, 4, 8")
    return streamer, target, threads


def resolve_bun() -> str:
    configured = os.environ.get("CSTUDIO_BUN", "").strip()
    if configured:
        if os.path.isfile(configured) or shutil.which(configured):
            return configured
        raise C.StudioError(f"CSTUDIO_BUN not found: {configured}")
    bun = shutil.which("bun")
    if not bun:
        raise C.StudioError("Bun is required for the Twitch scraper (bun executable not found in PATH)")
    return bun


def build_command(root: str, slug: str, streamer: str, target: str = "3", *,
                  threads: int = 4, force: bool = False, resume: bool = True,
                  sequential: bool = False) -> dict[str, Any]:
    streamer, target, threads = _validate(streamer, target, threads)
    C.load_project(root, slug)  # fail early if the production does not exist
    sdir = scraper_dir(root)
    script = os.path.join(sdir, "scrape.mjs")
    if not os.path.isfile(script):
        raise C.StudioError(f"bundled Twitch scraper not found: {script}")
    bun = resolve_bun()
    effective_threads = 1 if sequential else threads
    cmd = [bun, "run", "scrape.mjs", streamer, target]
    if sequential:
        cmd.append("--sequential")
    else:
        cmd.extend(["--threads", str(threads)])
    if force:
        cmd.append("--force")
    if not resume:
        cmd.append("--no-resume")
    return {
        "cmd": cmd,
        "cwd": sdir,
        "output_dir": output_dir(root, slug, streamer),
        "streamer": streamer,
        "target": target,
        "threads": threads,
        "effective_threads": effective_threads,
        "force": bool(force),
        "resume": bool(resume),
        "sequential": bool(sequential),
    }


def scraper_health(root: str) -> dict[str, Any]:
    sdir = scraper_dir(root)
    bun = os.environ.get("CSTUDIO_BUN", "").strip() or shutil.which("bun") or ""
    return {
        "scraper_dir": sdir,
        "script_present": os.path.isfile(os.path.join(sdir, "scrape.mjs")),
        "bun": bun,
        "bun_available": bool(bun and (os.path.isfile(bun) or shutil.which(bun))),
        "dependencies_present": os.path.isdir(os.path.join(sdir, "node_modules", "playwright")),
        "allowed_threads": list(_ALLOWED_THREADS),
    }


def _append_history(root: str, slug: str, event: str, **extra: Any) -> None:
    with _LOCK:
        vdir, project = C.load_project(root, slug)
        project.setdefault("history", []).append({"at": C.utc_now(), "event": event, **extra})
        C.save_project(vdir, project)


def _read_json(path: str, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def _vod_ids_from_output(out: str) -> list[str]:
    ids: set[str] = set()
    history = _read_json(os.path.join(out, "history.json"), {})
    videos = history.get("videos", history) if isinstance(history, dict) else []
    if isinstance(videos, list):
        for row in videos:
            if isinstance(row, dict) and str(row.get("id", "")).isdigit():
                ids.add(str(row["id"]))
    elif isinstance(videos, dict):
        for key, row in videos.items():
            candidate = str((row or {}).get("id", key)) if isinstance(row, dict) else str(key)
            if candidate.isdigit():
                ids.add(candidate)
    for sub in ("chat", "discovery", "raw"):
        d = os.path.join(out, sub)
        if not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            match = re.fullmatch(r"(\d+)\.json", name)
            if match:
                ids.add(match.group(1))
    return sorted(ids, key=int)


def import_outputs(root: str, slug: str, out: str) -> list[dict[str, Any]]:
    """Register primary scraper artifacts in the normal ingest registry.

    Raw capture, diagnostics and stats remain available under the Twitch ingest
    directory, but only the VOD discovery document and chat are registered as
    rights-relevant assets. Everything starts blocked by the existing rights rule.
    """
    vdir, _ = C.load_project(root, slug)
    imported: list[dict[str, Any]] = []
    for vod_id in _vod_ids_from_output(out):
        candidates = (
            (f"twitch-vod-{vod_id}", "vod-metadata", os.path.join(out, "discovery", f"{vod_id}.json")),
            (f"twitch-chat-{vod_id}", "chat", os.path.join(out, "chat", f"{vod_id}.json")),
        )
        for asset_id, kind, full in candidates:
            if not os.path.isfile(full):
                continue
            rel = os.path.relpath(full, vdir).replace(os.sep, "/")
            rec = PL.register_asset(root, slug, asset_id, kind, rel, "sem_autorizacao_confirmada")
            imported.append({"asset_id": asset_id, "kind": kind, "path": rel, **rec})
    return imported


def _command_display(cmd: list[str]) -> str:
    def q(part: str) -> str:
        return f'"{part}"' if any(c.isspace() for c in part) else part
    return " ".join(q(str(x)) for x in cmd)


def _run_worker(root: str, slug: str, record: dict[str, Any], spec: dict[str, Any]) -> None:
    key = (os.path.abspath(root), slug)
    log_path = record["log_file"]
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    os.makedirs(spec["output_dir"], exist_ok=True)
    env = os.environ.copy()
    env["CSTUDIO_TWITCH_OUT"] = spec["output_dir"]
    returncode = 1
    try:
        with open(log_path, "a", encoding="utf-8", errors="replace") as log:
            log.write(f"[{C.utc_now()}] Cuts Studio Twitch ingest\n")
            log.write(f"output: {spec['output_dir']}\n")
            deps = os.path.join(spec["cwd"], "node_modules", "playwright")
            if not os.path.isdir(deps):
                log.write("dependencies: missing; running bun install --frozen-lockfile\n")
                log.flush()
                setup = subprocess.run(
                    [spec["cmd"][0], "install", "--frozen-lockfile"],
                    cwd=spec["cwd"], env=env, stdout=log, stderr=subprocess.STDOUT,
                    text=True, check=False,
                )
                if setup.returncode != 0:
                    raise C.StudioError(f"bun install failed with exit code {setup.returncode}")
                log.write("browser: ensuring Playwright Chromium is installed\n")
                log.flush()
                browser_setup = subprocess.run(
                    [spec["cmd"][0], "x", "playwright", "install", "chromium"],
                    cwd=spec["cwd"], env=env, stdout=log, stderr=subprocess.STDOUT,
                    text=True, check=False,
                )
                if browser_setup.returncode != 0:
                    raise C.StudioError(
                        f"Playwright Chromium install failed with exit code {browser_setup.returncode}"
                    )
            log.write(f"command: {_command_display(spec['cmd'])}\n\n")
            log.flush()
            proc = subprocess.Popen(
                spec["cmd"], cwd=spec["cwd"], env=env,
                stdout=log, stderr=subprocess.STDOUT, text=True,
            )
            with _LOCK:
                _RUNNING_PROCS[key] = proc
            record["pid"] = proc.pid
            _write_run(root, slug, record)
            returncode = proc.wait()
        record["returncode"] = returncode
        record["finished_at"] = C.utc_now()
        if returncode == 0:
            record["imported_assets"] = import_outputs(root, slug, spec["output_dir"])
            record["status"] = "completed"
            _append_history(root, slug, "twitch_scrape_completed", run_id=record["id"],
                            streamer=record["streamer"], target=record["target"],
                            assets=len(record["imported_assets"]))
        else:
            record["status"] = "failed"
            record["error"] = f"scraper exited with code {returncode}"
            _append_history(root, slug, "twitch_scrape_failed", run_id=record["id"],
                            streamer=record["streamer"], target=record["target"],
                            returncode=returncode)
    except Exception as exc:
        record["status"] = "failed"
        record["returncode"] = returncode
        record["finished_at"] = C.utc_now()
        record["error"] = str(exc)
        try:
            with open(log_path, "a", encoding="utf-8", errors="replace") as log:
                log.write(f"\nERROR: {exc}\n")
        except Exception:
            pass
        try:
            _append_history(root, slug, "twitch_scrape_failed", run_id=record["id"],
                            streamer=record["streamer"], target=record["target"], error=str(exc))
        except Exception:
            pass
    finally:
        _write_run(root, slug, record)
        with _LOCK:
            _RUNNING.pop(key, None)
            _RUNNING_PROCS.pop(key, None)


def start_scrape(root: str, slug: str, streamer: str, target: str = "3", *,
                 threads: int = 4, force: bool = False, resume: bool = True,
                 sequential: bool = False) -> dict[str, Any]:
    spec = build_command(root, slug, streamer, target, threads=threads, force=force,
                         resume=resume, sequential=sequential)
    key = (os.path.abspath(root), slug)
    with _LOCK:
        existing = _RUNNING.get(key)
        if existing and existing.is_alive():
            raise C.StudioError("a Twitch scrape is already running for this production")
        run_id = C.utc_now().replace("-", "").replace(":", "").replace("T", "-").replace("Z", "") + "-" + uuid.uuid4().hex[:6]
        record: dict[str, Any] = {
            "id": run_id,
            "status": "running",
            "created_at": C.utc_now(),
            "started_at": C.utc_now(),
            "finished_at": "",
            "slug": slug,
            "streamer": spec["streamer"],
            "target": spec["target"],
            "threads": spec["threads"],
            "effective_threads": spec["effective_threads"],
            "force": spec["force"],
            "resume": spec["resume"],
            "sequential": spec["sequential"],
            "output_dir": spec["output_dir"],
            "command": _command_display(spec["cmd"]),
            "log_file": _log_path(root, slug, run_id),
            "pid": None,
            "returncode": None,
            "error": "",
            "imported_assets": [],
        }
        _write_run(root, slug, record)
        _append_history(root, slug, "twitch_scrape_started", run_id=run_id,
                        streamer=record["streamer"], target=record["target"],
                        threads=record["effective_threads"])
        thread = threading.Thread(target=_run_worker, args=(root, slug, record, spec),
                                  name=f"twitch-scrape-{slug}", daemon=True)
        _RUNNING[key] = thread
        thread.start()
        return dict(record)


def run_scrape(root: str, slug: str, streamer: str, target: str = "3", *,
               threads: int = 4, force: bool = False, resume: bool = True,
               sequential: bool = False) -> dict[str, Any]:
    """Synchronous CLI helper using the same persistent run contract as the dashboard."""
    record = start_scrape(root, slug, streamer, target, threads=threads, force=force,
                          resume=resume, sequential=sequential)
    key = (os.path.abspath(root), slug)
    with _LOCK:
        thread = _RUNNING.get(key)
    if thread:
        thread.join()
    return read_run(root, slug, record["id"]) or record


def read_run(root: str, slug: str, run_id: str) -> dict[str, Any] | None:
    path = _run_path(root, slug, run_id)
    return _read_json(path, None) if os.path.isfile(path) else None


def list_runs(root: str, slug: str, limit: int = 20) -> list[dict[str, Any]]:
    d = _runs_dir(root, slug)
    if not os.path.isdir(d):
        return []
    rows = []
    for name in os.listdir(d):
        if not name.endswith(".json"):
            continue
        row = _read_json(os.path.join(d, name), None)
        if isinstance(row, dict):
            rows.append(row)
    rows.sort(key=lambda r: str(r.get("started_at", "")), reverse=True)
    return rows[:max(1, int(limit))]


def latest_run(root: str, slug: str) -> dict[str, Any] | None:
    rows = list_runs(root, slug, 1)
    return rows[0] if rows else None


def tail_log(root: str, slug: str, run_id: str | None = None, max_chars: int = 12000) -> str:
    run = read_run(root, slug, run_id) if run_id else latest_run(root, slug)
    if not run:
        return ""
    path = str(run.get("log_file", "") or "")
    if not path or not os.path.isfile(path):
        return ""
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    return text[-max(1000, int(max_chars)):]


def shutdown_jobs(timeout: float = 3.0) -> None:
    """Best-effort cleanup for scraper subprocesses when the dashboard exits."""
    with _LOCK:
        procs = list(_RUNNING_PROCS.values())
    for proc in procs:
        if proc.poll() is not None:
            continue
        try:
            proc.terminate()
            proc.wait(timeout=timeout)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def status_summary(root: str, slug: str) -> dict[str, Any]:
    return {
        "health": scraper_health(root),
        "latest": latest_run(root, slug),
        "runs": list_runs(root, slug, 8),
    }
