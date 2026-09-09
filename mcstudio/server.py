from __future__ import annotations

import html
import importlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import traceback
import uuid
import webbrowser
from datetime import datetime, timezone
from email.parser import BytesParser
from email.policy import default as email_policy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse

from .analytics import import_youtube_csv
from .assistant import (
    apply_edited_proposal,
    apply_proposal,
    create_proposal,
    discard_proposal,
    import_proposal,
    recover_latest_runner_proposal,
    load_settings,
    save_settings,
    update_proposal_document,
)
from .core import (
    StudioError,
    abandon_video,
    add_calendar_item,
    add_deal,
    add_idea,
    add_library_asset,
    add_social_item,
    add_time_entry,
    approve_gate,
    business_entry,
    continue_workflow,
    create_video,
    load_project,
    maintain_repository,
    package_publish,
    pause_video,
    reopen_stage,
    resume_video,
    save_project,
    utc_now,
    workflow_status,
)
from .dashboard import render_page
from .runners import RUNNER_LABELS, install_runner, launch_runner_setup, test_runner
from .workspace import (
    append_capture_log,
    delete_project_file,
    launch_application,
    open_path,
    safe_video_file,
    select_local_file,
    upload_bytes,
    write_root_text,
    write_text_file,
)
from .svg import generate_thumbnail_wireframes
from .youtube import upload as youtube_upload


class StudioHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, handler, root: Path):
        super().__init__(address, handler)
        self.root = root
        self.error_log = root / "exports" / "studio-server.log"
        self.jobs: dict[str, dict[str, Any]] = {}
        self.jobs_lock = threading.Lock()

    def record_error(self, context: str) -> None:
        self.error_log.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        with self.error_log.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(f"\n[{timestamp}] {context}\n")
            handle.write(traceback.format_exc())

    def handle_error(self, request, client_address) -> None:
        # Request-thread failures must never terminate the local dashboard.
        self.record_error(f"Unhandled request failure from {client_address[0]}:{client_address[1]}")

    def list_jobs(self) -> list[dict[str, Any]]:
        with self.jobs_lock:
            rows = [dict(value) for value in self.jobs.values()]
        rows.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return rows

    def start_job(self, label: str, function: Callable[[], Any], dedupe_key: str = "") -> str:
        with self.jobs_lock:
            if dedupe_key:
                for existing in self.jobs.values():
                    if existing.get("dedupe_key") == dedupe_key and existing.get("status") == "running":
                        return str(existing["id"])
            job_id = uuid.uuid4().hex[:12]
            job = {
                "id": job_id,
                "label": label,
                "status": "running",
                "message": "Focused generation is running. The runner terminal shows live Codex events; keep it open until completion.",
                "error": "",
                "dedupe_key": dedupe_key,
                "created_at": utc_now(),
                "updated_at": utc_now(),
            }
            self.jobs[job_id] = job

        def runner() -> None:
            try:
                result = function()
                message = result.get("message", "Complete") if isinstance(result, dict) else str(result or "Complete")
                with self.jobs_lock:
                    job.update({"status": "complete", "message": message, "updated_at": utc_now()})
            except Exception as exc:  # background failures must be visible and logged
                try:
                    raise
                except Exception:
                    self.record_error(f"Background job failed: {label}")
                with self.jobs_lock:
                    job.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}", "updated_at": utc_now()})

        threading.Thread(target=runner, daemon=True, name=f"mcstudio-{job_id}").start()
        return job_id


class StudioHandler(BaseHTTPRequestHandler):
    server: StudioHTTPServer

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _send(self, body: str | bytes, status: int = 200, content_type: str = "text/html; charset=utf-8", filename: str = "") -> None:
        payload = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename.replace(chr(34), "")}"')
        try:
            self.end_headers()
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            # Normal when the browser navigates or reloads before a response is
            # fully written. It must not be treated as a Studio crash.
            return

    def _render(self, page: str = "home", message: str = "", error: bool = False, params: dict[str, str] | None = None, status: int = 200) -> None:
        self._send(render_page(self.server.root, page, params=params, message=message, error=error, jobs=self.server.list_jobs()), status=status)

    def _redirect(self, page: str, message: str = "", error: bool = False, **params: str) -> None:
        query = {"page": page, **{key: value for key, value in params.items() if value}}
        if message:
            query["message"] = message
        if error:
            query["error"] = "1"
        location = "/?" + urlencode(query)
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        try:
            self.end_headers()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return

    def _request_data(self) -> tuple[dict[str, str], dict[str, tuple[str, bytes]]]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        content_type = self.headers.get("Content-Type", "")
        if length > 2 * 1024 * 1024 * 1024:
            raise StudioError("Browser upload exceeds 2 GB. Use the native file picker instead.")
        body = self.rfile.read(length)
        fields: dict[str, str] = {}
        files: dict[str, tuple[str, bytes]] = {}
        if content_type.startswith("multipart/form-data"):
            raw = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + body
            message = BytesParser(policy=email_policy).parsebytes(raw)
            for part in message.iter_parts():
                name = part.get_param("name", header="content-disposition")
                if not name:
                    continue
                filename = part.get_filename()
                payload = part.get_payload(decode=True) or b""
                if filename is not None:
                    files[str(name)] = (Path(filename).name, payload)
                else:
                    charset = part.get_content_charset() or "utf-8"
                    fields[str(name)] = payload.decode(charset, errors="replace")
        else:
            parsed = parse_qs(body.decode("utf-8", errors="replace"), keep_blank_values=True)
            fields = {key: values[-1] if values else "" for key, values in parsed.items()}
        return fields, files

    def do_GET(self) -> None:  # noqa: N802
        try:
            parsed = urlparse(self.path)
            params = {key: values[-1] for key, values in parse_qs(parsed.query).items() if values}
            if parsed.path == "/":
                self._render(
                    params.get("page", "home"),
                    message=params.get("message", ""),
                    error=params.get("error") == "1",
                    params=params,
                )
                return
            if parsed.path == "/health":
                self._send("ok", content_type="text/plain; charset=utf-8")
                return
            if parsed.path == "/api/jobs":
                self._send(json.dumps(self.server.list_jobs(), ensure_ascii=False), content_type="application/json; charset=utf-8")
                return
            if parsed.path.startswith("/download/"):
                parts = [unquote(item) for item in parsed.path[len("/download/"):].split("/") if item]
                if len(parts) < 2:
                    self._send("Not found", 404, "text/plain; charset=utf-8")
                    return
                slug, relative = parts[0], "/".join(parts[1:])
                try:
                    target = safe_video_file(self.server.root, slug, relative, allow_internal=False)
                    if not target.is_file():
                        raise StudioError("File not found.")
                    self._send(target.read_bytes(), content_type="application/octet-stream", filename=target.name)
                except StudioError as exc:
                    self._send(str(exc), 404, "text/plain; charset=utf-8")
                return
            if parsed.path == "/closed":
                self._send("<!doctype html><title>Studio closed</title><style>body{background:#10140f;color:#f0ead8;font:18px Segoe UI;padding:40px}</style><h1>Minecraft Narrative Studio is closed.</h1><p>You may close this tab. Double-click START-STUDIO.vbs to open it again.</p>")
                return
            self._send("Not found", 404, "text/plain; charset=utf-8")
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return
        except Exception as exc:
            self.server.record_error(f"Unexpected failure during GET {self.path}")
            try:
                self._send(
                    f"<!doctype html><title>Studio page error</title><style>body{{background:#10140f;color:#f0ead8;font:18px Segoe UI;padding:40px}}a{{color:#c7db88}}</style><h1>This page could not be rendered.</h1><p>{html.escape(type(exc).__name__ + ': ' + str(exc))}</p><p>The Studio server is still running. <a href='/?page=diagnostics'>Open Diagnostics</a>.</p>",
                    status=500,
                )
            except Exception:
                return

    def _media_path(self, video_dir: Path, stored: str) -> Path:
        raw = Path(stored).expanduser()
        return raw.resolve() if raw.is_absolute() else (video_dir / raw).resolve()

    def do_POST(self) -> None:  # noqa: N802
        page = "home"
        try:
            data, files = self._request_data()
            path = urlparse(self.path).path
            slug = data.get("slug", "")

            if path == "/action/new":
                title = data.get("title", "").strip()
                if not title:
                    raise StudioError("Enter a working title.")
                project_path = create_video(self.server.root, title)
                self._render("workspace", f"Started {project_path.name}. Add your rough idea or run the Studio Assistant.")
                return

            if path in {"/action/save-document", "/action/save-file"}:
                page = "workspace" if path.endswith("document") else ("release" if data.get("path", "").endswith("metadata.json") else "file")
                write_text_file(self.server.root, slug, data.get("path", ""), data.get("content", ""))
                params = {"path": data.get("path", "")} if page == "file" else None
                self._render(page, "Saved.", params=params)
                return

            if path == "/action/save-root-file":
                page = "channel"
                write_root_text(self.server.root, data.get("path", ""), data.get("content", ""))
                self._render(page, "Channel document saved.")
                return

            if path == "/action/assistant":
                page = "workspace"
                request_text = data.get("request", "")
                mode = data.get("mode", "develop")
                use_web = data.get("use_web") == "yes"
                job_id = self.server.start_job(
                    f"Studio Assistant · {mode}",
                    lambda: {
                        "message": f"Proposal {create_proposal(self.server.root, slug, request_text, mode, use_web)['id']} is ready for review."
                    },
                    dedupe_key=f"assistant:{slug}:{mode}",
                )
                self._redirect("diagnostics", f"Studio Assistant started as task {job_id}. Status will refresh safely without resubmitting the action.")
                return

            if path == "/action/import-proposal":
                page = "workspace"
                proposal = import_proposal(self.server.root, slug, data.get("proposal", ""))
                self._render("proposal", "Proposal imported. Review it before applying.", params={"id": proposal["id"]})
                return

            if path == "/action/recover-runner-proposal":
                page = "workspace"
                proposal = recover_latest_runner_proposal(self.server.root, slug)
                self._render(
                    "proposal",
                    "Recovered the latest completed runner proposal. Review it before applying.",
                    params={"id": proposal["id"]},
                )
                return

            if path == "/action/save-proposal":
                page = "workspace"
                proposal_id = data.get("proposal_id", "")
                update_proposal_document(self.server.root, slug, proposal_id, data.get("document", ""))
                self._render("proposal", "Proposal edits saved. It is still pending.", params={"id": proposal_id})
                return

            if path == "/action/apply-edited-proposal":
                page = "workspace"
                proposal = apply_edited_proposal(
                    self.server.root, slug, data.get("proposal_id", ""), data.get("document", "")
                )
                self._render(page, f"Accepted edited proposal {proposal['id']}. Run phase checks next.")
                return

            if path == "/action/apply-proposal":
                page = "workspace"
                proposal = apply_proposal(self.server.root, slug, data.get("proposal_id", ""))
                self._render(page, f"Applied proposal {proposal['id']}. Run phase checks next.")
                return

            if path == "/action/discard-proposal":
                page = "workspace"
                discard_proposal(self.server.root, slug, data.get("proposal_id", ""))
                self._render(page, "Proposal discarded.")
                return

            if path == "/action/check":
                page = "workspace"
                status = workflow_status(self.server.root, slug)
                message = "All phase checks pass." if not status.get("blockers") else f"Found {len(status['blockers'])} blocker(s)."
                self._render(page, message)
                return

            if path == "/action/approve":
                page = "workspace"
                approve_gate(self.server.root, slug, data.get("gate", ""), "Luan", "Approved from dashboard")
                result = continue_workflow(self.server.root, slug)
                self._render(page, f"Approved. {result.get('headline', 'Production advanced')}.")
                return

            if path == "/action/continue":
                page = "workspace"
                result = continue_workflow(self.server.root, slug or None)
                advanced = ", ".join(result.get("advanced", []))
                self._render(page if result.get("status") != "completed" else "home", f"{result.get('headline', 'Workflow checked')}." + (f" Advanced: {advanced}." if advanced else ""))
                return

            if path == "/action/capture":
                page = "workspace"
                append_capture_log(self.server.root, slug, data)
                self._render(page, "Captured take added to the production record.")
                return

            if path == "/action/upload":
                page = "media"
                filename, payload = files.get("file", ("", b""))
                target = upload_bytes(self.server.root, slug, data.get("bucket", ""), filename, payload)
                self._render(page, f"Uploaded {target.name}.")
                return

            if path == "/action/select-file":
                page = "media"
                selected = select_local_file(self.server.root, slug, data.get("bucket", ""))
                self._render(page, f"Selected {selected}." if selected else "File selection cancelled.")
                return

            if path == "/action/delete-file":
                page = "media"
                delete_project_file(self.server.root, slug, data.get("path", ""))
                self._render(page, "File removed; a backup was retained.")
                return

            if path == "/action/open-project":
                page = "home"
                video_dir, _ = load_project(self.server.root, slug)
                open_path(video_dir)
                self._render(page, "Opened the project folder.")
                return

            if path == "/action/open-root":
                open_path(self.server.root)
                self._render("home", "Opened the studio folder.")
                return

            if path == "/action/open-path":
                candidate = Path(data.get("path", "")).resolve()
                try:
                    candidate.relative_to(self.server.root.resolve())
                except ValueError as exc:
                    raise StudioError("Only studio paths can be opened.") from exc
                open_path(candidate)
                self._render("release", "Opened the package folder.")
                return

            if path == "/action/pause":
                pause_video(self.server.root, slug, "Luan")
                self._render("home", "Video paused. You can resume it later.")
                return

            if path == "/action/resume":
                resume_video(self.server.root, slug, "Luan")
                self._render("workspace", "Video resumed as the active production.")
                return

            if path == "/action/abandon":
                abandon_video(self.server.root, slug, "Luan", "Abandoned from dashboard")
                self._render("home", "Video abandoned. All files were retained.")
                return

            if path == "/action/reopen":
                page = "workspace"
                reopen_stage(self.server.root, slug, data.get("to_stage", ""), "Luan", data.get("reason", ""))
                self._render(page, f"Reopened {data.get('to_stage', '')}. Affected approvals were invalidated.")
                return

            if path == "/action/settings":
                page = "settings"
                save_settings(self.server.root, data)
                self._render(page, "Runner routing and settings saved.")
                return

            if path == "/action/runner-install":
                page = "settings"
                runner = data.get("runner", "")
                settings = load_settings(self.server.root, include_secret=True)
                job_id = self.server.start_job(
                    f"Install {RUNNER_LABELS.get(runner, runner)}",
                    lambda runner=runner, settings=settings: install_runner(self.server.root, settings, runner),
                    dedupe_key=f"runner-install:{runner}",
                )
                self._redirect("diagnostics", f"Installation started as task {job_id}.")
                return

            if path == "/action/runner-setup":
                page = "settings"
                runner = data.get("runner", "")
                settings = load_settings(self.server.root, include_secret=True)
                job_id = self.server.start_job(
                    f"Set up {RUNNER_LABELS.get(runner, runner)}",
                    lambda runner=runner, settings=settings: launch_runner_setup(self.server.root, settings, runner),
                    dedupe_key=f"runner-setup:{runner}",
                )
                self._redirect("diagnostics", f"Setup started as task {job_id}. Follow the browser sign-in window if one opens.")
                return

            if path == "/action/runner-test":
                page = "settings"
                runner = data.get("runner", "")
                settings = load_settings(self.server.root, include_secret=True)
                job_id = self.server.start_job(
                    f"Test {RUNNER_LABELS.get(runner, runner)}",
                    lambda runner=runner, settings=settings: test_runner(self.server.root, settings, runner),
                    dedupe_key=f"runner-test:{runner}",
                )
                self._redirect("diagnostics", f"Connection test started as task {job_id}.")
                return

            if path == "/action/launch":
                page = "home"
                settings = load_settings(self.server.root, include_secret=False)
                app = settings.get("apps", {}).get(data.get("app_id", ""), {})
                launch_application(app.get("command", ""), app.get("working_directory", ""))
                self._render(page, f"Launched {app.get('label', 'application')}.")
                return

            if path == "/action/package":
                page = "release"
                package = package_publish(self.server.root, slug)
                self._render(page, f"Publish package created: {package.name}")
                return

            if path == "/action/wireframes":
                page = "release"
                outputs = generate_thumbnail_wireframes(self.server.root, slug)
                self._render(page, f"Generated {len(outputs)} thumbnail wireframe(s).")
                return

            if path == "/action/install-youtube":
                page = "release"
                packages = ["google-api-python-client>=2.0", "google-auth-oauthlib>=1.0", "google-auth-httplib2>=0.2"]
                def install_youtube_support() -> dict[str, str]:
                    result = subprocess.run(
                        [sys.executable, "-m", "pip", "install", *packages],
                        cwd=self.server.root,
                        capture_output=True,
                        text=True,
                        timeout=1800,
                    )
                    if result.returncode != 0:
                        detail = (result.stderr or result.stdout or "pip returned no diagnostic output").strip()
                        raise StudioError(f"YouTube dependency installation failed: {detail[-4000:]}")
                    importlib.invalidate_caches()
                    return {"message": "YouTube support installed and ready."}

                job_id = self.server.start_job("Install YouTube support", install_youtube_support, dedupe_key="youtube-install")
                self._redirect("diagnostics", f"Installation started as task {job_id}.")
                return

            if path == "/action/youtube":
                page = "release"
                video_dir, project = load_project(self.server.root, slug)
                media = project.get("media", {})
                master = self._media_path(video_dir, media.get("master_file", ""))
                client = self._media_path(video_dir, media.get("youtube_client_secrets", ""))
                metadata = video_dir / ".studio" / "internal" / "release" / "metadata.json"
                token = self.server.root / "secrets" / "youtube-token.json"
                execute = data.get("execute") == "yes"
                if execute and not project.get("approvals", {}).get("publish_lock"):
                    raise StudioError("Real upload requires Publication approval. Dry run remains available before approval.")
                if execute and importlib.util.find_spec("googleapiclient") is None:
                    raise StudioError("Install YouTube support from the Release page before a real upload.")
                privacy = data.get("privacy", "private")
                publish_at = data.get("publish_at", "").strip() or None
                notify_subscribers = data.get("notify_subscribers") == "yes"
                thumbnail_stored = media.get("thumbnail_file", "")
                thumbnail = self._media_path(video_dir, thumbnail_stored) if thumbnail_stored else None
                captions = video_dir / ".studio" / "internal" / "edit" / "captions-en-GB.srt"

                def run_upload() -> dict[str, str]:
                    result = youtube_upload(master, metadata, client, token, privacy, publish_at, execute, thumbnail, captions, notify_subscribers)
                    video_dir2, project2 = load_project(self.server.root, slug)
                    youtube = project2.setdefault("youtube", {})
                    youtube["upload_status"] = "uploaded" if execute else "dry_run_complete"
                    youtube["last_plan"] = result.get("request_body", {})
                    response = result.get("response", {}) if isinstance(result, dict) else {}
                    if isinstance(response, dict) and response.get("id"):
                        youtube["video_id"] = response["id"]
                        youtube["published_at"] = utc_now()
                    project2.setdefault("history", []).append({"at": utc_now(), "event": "youtube_upload" if execute else "youtube_dry_run", "privacy": privacy, "publish_at": publish_at or ""})
                    save_project(video_dir2, project2)
                    return {"message": "YouTube upload complete." if execute else "YouTube dry-run plan complete."}

                job_id = self.server.start_job(
                    "YouTube upload" if execute else "YouTube dry run",
                    run_upload,
                    dedupe_key=f"youtube:{slug}:{'execute' if execute else 'dry-run'}",
                )
                self._redirect("diagnostics", f"Uploader started as task {job_id}.")
                return

            if path == "/action/idea":
                page = "operations"
                payload = dict(data)
                payload.setdefault("status", "backlog")
                payload.setdefault("notes", "")
                add_idea(self.server.root, payload)
                self._render(page, "Idea added and scored.")
                return

            if path == "/action/time":
                page = "operations"
                add_time_entry(self.server.root, data)
                self._render(page, "Time entry added.")
                return

            if path == "/action/money":
                page = "operations"
                business_entry(self.server.root, data)
                self._render(page, "Money entry added in its original currency.")
                return

            if path == "/action/calendar":
                page = "operations"
                add_calendar_item(self.server.root, data)
                self._render(page, "Calendar milestone added.")
                return

            if path == "/action/social":
                page = "operations"
                add_social_item(self.server.root, data)
                self._render(page, "Social item added.")
                return

            if path == "/action/deal":
                page = "operations"
                payload = dict(data)
                payload["currency"] = (payload.get("currency") or "BRL").upper()
                add_deal(self.server.root, payload)
                self._render(page, "Commercial opportunity added.")
                return

            if path == "/action/asset":
                page = "operations"
                add_library_asset(self.server.root, data)
                self._render(page, "Reusable asset added.")
                return

            if path == "/action/upload-analytics":
                page = "operations"
                filename, payload = files.get("file", ("analytics.csv", b""))
                if not payload:
                    raise StudioError("Choose a YouTube Studio CSV file.")
                with tempfile.NamedTemporaryFile(prefix="mcstudio-analytics-", suffix=".csv", delete=False) as handle:
                    handle.write(payload)
                    temp_path = Path(handle.name)
                try:
                    result = import_youtube_csv(self.server.root, temp_path, slug, data.get("video_id", ""))
                finally:
                    temp_path.unlink(missing_ok=True)
                self._render(page, f"Analytics snapshot imported for {slug}.")
                return

            if path == "/action/maintain":
                page = "diagnostics"
                checks = maintain_repository(self.server.root)
                failed = [item for item in checks if not item.ok]
                self._render(page, "Maintenance completed." if not failed else f"Maintenance found {len(failed)} issue(s).", error=bool(failed))
                return

            if path == "/action/shutdown":
                self._send("<!doctype html><style>body{background:#10140f;color:#f0ead8;font:18px Segoe UI;padding:40px}</style><h1>Minecraft Narrative Studio is closed.</h1><p>You may close this tab. Double-click START-STUDIO.vbs to open it again.</p>")
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return

            raise StudioError("Unknown dashboard action.")

        except (StudioError, OSError, ValueError, json.JSONDecodeError) as exc:
            self._render(page, f"Could not complete action: {exc}", error=True, status=400)
        except Exception as exc:
            self.server.record_error(f"Unexpected failure during {self.command} {self.path}")
            self._render(page, f"Unexpected error: {type(exc).__name__}: {exc}. Details were saved to Diagnostics.", error=True, status=500)


def run_studio(root: Path, host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    maintain_repository(root)
    server = StudioHTTPServer((host, port), StudioHandler, root)
    actual_port = server.server_address[1]
    url = f"http://{host}:{actual_port}/"
    print(f"Minecraft Narrative Studio: {url}", flush=True)
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
