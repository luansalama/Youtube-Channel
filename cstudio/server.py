"""Local Cuts Studio dashboard server.

The server intentionally stays in the Python stdlib and binds to loopback by default.
Browser enhancements never bypass the same deterministic domain functions used by CLI.
"""
from __future__ import annotations

import html
import json
import secrets
import urllib.parse as _up
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources

from . import core as C
from . import dashboard as D
from . import proposals as P


STATIC_FILES = {
    "/static/dashboard.css": ("dashboard.css", "text/css; charset=utf-8"),
    "/static/dashboard.js": ("dashboard.js", "text/javascript; charset=utf-8"),
}


def _parse_body(handler: BaseHTTPRequestHandler, raw: bytes):
    """Return ``(payload, is_form)`` for JSON and urlencoded browser forms."""
    ctype = handler.headers.get("Content-Type", "") or ""
    if "application/x-www-form-urlencoded" in ctype:
        parsed = _up.parse_qs(raw.decode("utf-8", errors="replace"), keep_blank_values=True)
        return ({k: v[0] if len(v) == 1 else v for k, v in parsed.items()}, True)
    try:
        text = raw.decode("utf-8") if raw else "{}"
        if not text.strip():
            return ({}, False)
        # Compatibility with simple clients that forgot the form content type.
        prefixes = ("slug=", "gate=", "id=", "title=", "source_url=", "confirmo=", "by=", "reason=", "note=", "streamer=")
        if "=" in text and text.strip().startswith(prefixes) and "{" not in text:
            parsed = _up.parse_qs(text, keep_blank_values=True)
            return ({k: v[0] if len(v) == 1 else v for k, v in parsed.items()}, True)
        data = json.loads(text)
        return (data if isinstance(data, dict) else {}, False)
    except Exception:
        return ({}, False)


class Handler(BaseHTTPRequestHandler):
    root: str = "."
    csrf_token: str = ""

    def log_message(self, *args):  # quieter local server
        pass

    def _base_headers(self, cache: str = "no-store") -> None:
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'; object-src 'none'",
        )

    def _send_bytes(self, data: bytes, ctype: str, code: int = 200, cache: str = "no-store"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self._base_headers(cache)
        self.end_headers()
        self.wfile.write(data)

    def _send(self, body: str, ctype: str = "text/html; charset=utf-8", code: int = 200, cache: str = "no-store"):
        self._send_bytes(body.encode("utf-8"), ctype, code, cache)

    def _redirect(self, location: str):
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self._base_headers("no-store")
        self.end_headers()

    def _form_result(self, ok: bool, slug: str, page: str, message: str):
        back = f"/?page={_up.quote(page)}&slug={_up.quote(slug)}" if slug else f"/?page={_up.quote(page)}"
        title = "Ação concluída" if ok else "Falha na ação"
        tone = "message-ok" if ok else "message-error"
        body = (
            "<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{html.escape(title)}</title><link rel='stylesheet' href='/static/dashboard.css?v=2'></head>"
            f"<body class='message-page'><main class='message-card {tone}'><span class='eyebrow'>Cuts Studio</span>"
            f"<h1>{html.escape(title)}</h1><p>{html.escape(message)}</p>"
            f"<a class='button button-primary' href='{html.escape(back)}'>Voltar ao painel</a></main></body></html>"
        )
        self._send(body, code=200 if ok else 400)

    def _static(self, path: str):
        spec = STATIC_FILES.get(path)
        if not spec:
            return self._send("not found", "text/plain; charset=utf-8", 404)
        filename, ctype = spec
        try:
            data = resources.files("cstudio").joinpath("static", filename).read_bytes()
        except Exception:
            return self._send("static asset unavailable", "text/plain; charset=utf-8", 404)
        return self._send_bytes(data, ctype, 200, "public, max-age=3600")

    def _validate_browser_post(self, payload: dict, is_form: bool) -> None:
        # Fetch Metadata blocks obvious cross-site browser submissions before token checks.
        fetch_site = (self.headers.get("Sec-Fetch-Site", "") or "").lower()
        if fetch_site == "cross-site":
            raise PermissionError("cross-site POST rejected")
        if not is_form or not self.csrf_token:
            return
        token = str(payload.get("csrf_token", "") or "")
        if not token or not secrets.compare_digest(token, self.csrf_token):
            raise PermissionError("CSRF token inválido; recarregue o dashboard e tente novamente")

    def do_GET(self):
        u = _up.urlparse(self.path)
        q = _up.parse_qs(u.query)
        page = q.get("page", ["production"])[0]
        slug = q.get("slug", [""])[0]

        if u.path in STATIC_FILES:
            return self._static(u.path)
        if u.path == "/health":
            return self._send("ok", "text/plain; charset=utf-8")
        if u.path == "/api/status":
            try:
                state = C.workflow_status(self.root, slug) if slug else {"productions": C.list_productions(self.root)}
                return self._send(json.dumps(state, ensure_ascii=False), "application/json; charset=utf-8")
            except Exception as exc:
                return self._send(json.dumps({"error": str(exc)}), "application/json; charset=utf-8", 400)
        if u.path == "/api/twitch-status":
            try:
                if not slug:
                    raise ValueError("slug is required")
                from . import twitch as TW
                data = TW.status_summary(self.root, slug)
                latest = data.get("latest") or {}
                data["log_tail"] = TW.tail_log(self.root, slug, latest.get("id")) if latest else ""
                return self._send(json.dumps(data, ensure_ascii=False), "application/json; charset=utf-8")
            except Exception as exc:
                return self._send(json.dumps({"error": str(exc)}), "application/json; charset=utf-8", 400)
        if u.path == "/ui/twitch-run":
            try:
                if not slug:
                    raise ValueError("slug is required")
                return self._send(D.render_twitch_run(self.root, slug))
            except Exception as exc:
                return self._send(
                    '<div class="notice notice-danger"><div><strong>Falha ao atualizar</strong><span>'
                    + html.escape(str(exc)) + "</span></div></div>",
                    code=400,
                )
        if u.path in ("/", "/index.html"):
            try:
                return self._send(D.render(self.root, page, slug, csrf_token=self.csrf_token))
            except Exception as exc:
                return self._send(
                    "<!doctype html><html><head><meta charset='utf-8'><link rel='stylesheet' href='/static/dashboard.css?v=2'>"
                    f"</head><body class='message-page'><main class='message-card message-error'><h1>Erro</h1><p>{html.escape(str(exc))}</p></main></body></html>",
                    code=500,
                )
        return self._send("not found", "text/plain; charset=utf-8", 404)

    def do_POST(self):
        u = _up.urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        if length > 1_000_000:
            return self._send(json.dumps({"ok": False, "error": "request too large"}), "application/json; charset=utf-8", 413)
        raw = self.rfile.read(length) if length else b""
        payload, is_form = _parse_body(self, raw)
        try:
            self._validate_browser_post(payload, is_form)
            if u.path == "/action/approve":
                rec = C.approve_gate(
                    self.root, payload["slug"], payload["gate"],
                    by=payload.get("by", "showrunner") or "showrunner",
                    note=payload.get("note", "") or "",
                )
                if is_form:
                    return self._redirect(f"/?page=gates&slug={_up.quote(str(payload.get('slug', '')))}")
                return self._send(json.dumps({"ok": True, "approval": rec}), "application/json; charset=utf-8")
            if u.path == "/action/advance":
                nxt = C.advance_stage(self.root, payload["slug"])
                if is_form:
                    return self._redirect(f"/?page=gates&slug={_up.quote(str(payload.get('slug', '')))}")
                return self._send(json.dumps({"ok": True, "stage": nxt}), "application/json; charset=utf-8")
            if u.path == "/action/apply-proposal":
                rec = P.apply_proposal(
                    self.root, payload["slug"], payload["id"],
                    by=payload.get("by", "showrunner") or "showrunner",
                )
                if is_form:
                    return self._redirect(f"/?page=proposals&slug={_up.quote(str(payload.get('slug', '')))}")
                return self._send(json.dumps({"ok": True, "proposal": rec["id"]}), "application/json; charset=utf-8")
            if u.path == "/action/discard-proposal":
                rec = P.discard_proposal(
                    self.root, payload["slug"], payload["id"],
                    by=payload.get("by", "showrunner") or "showrunner",
                )
                if is_form:
                    return self._redirect(f"/?page=proposals&slug={_up.quote(str(payload.get('slug', '')))}")
                return self._send(json.dumps({"ok": True, "proposal": rec["id"]}), "application/json; charset=utf-8")
            if u.path == "/action/new":
                title = str(payload.get("title", "") or "").strip()
                if not title:
                    raise ValueError("title is required")
                slug_raw = str(payload.get("slug", "") or "").strip()
                project = C.create_production(
                    self.root, title, slug_raw or None,
                    str(payload.get("source_url", "") or ""),
                )
                new_slug = str(project.get("slug", "") or slug_raw)
                if is_form:
                    return self._redirect(f"/?page=production&slug={_up.quote(new_slug)}")
                return self._send(json.dumps({"ok": True, "slug": new_slug, "project": project}, ensure_ascii=False), "application/json; charset=utf-8")
            if u.path == "/action/pause":
                slug = str(payload.get("slug", "") or "")
                if not slug:
                    raise ValueError("slug is required")
                C.pause_production(
                    self.root, slug,
                    by=str(payload.get("by", "showrunner") or "showrunner"),
                    reason=str(payload.get("reason", "") or ""),
                )
                if is_form:
                    return self._redirect(f"/?page=production&slug={_up.quote(slug)}")
                return self._send(json.dumps({"ok": True, "slug": slug, "state": "paused"}), "application/json; charset=utf-8")
            if u.path == "/action/resume":
                slug = str(payload.get("slug", "") or "")
                if not slug:
                    raise ValueError("slug is required")
                C.resume_production(self.root, slug, by=str(payload.get("by", "showrunner") or "showrunner"))
                if is_form:
                    return self._redirect(f"/?page=production&slug={_up.quote(slug)}")
                return self._send(json.dumps({"ok": True, "slug": slug, "state": "active"}), "application/json; charset=utf-8")
            if u.path == "/action/abandon":
                slug = str(payload.get("slug", "") or "")
                if not slug:
                    raise ValueError("slug is required")
                if is_form and not payload.get("confirmo"):
                    raise ValueError("confirme o abandono")
                C.abandon_production(
                    self.root, slug,
                    by=str(payload.get("by", "showrunner") or "showrunner"),
                    reason=str(payload.get("reason", "") or ""),
                )
                if is_form:
                    return self._redirect(f"/?page=production&slug={_up.quote(slug)}")
                return self._send(json.dumps({"ok": True, "slug": slug, "state": "abandoned"}), "application/json; charset=utf-8")
            if u.path == "/action/twitch-scrape":
                slug = str(payload.get("slug", "") or "").strip()
                if not slug:
                    raise ValueError("slug is required")
                from . import twitch as TW
                rec = TW.start_scrape(
                    self.root, slug,
                    str(payload.get("streamer", "") or ""),
                    str(payload.get("target", "3") or "3"),
                    threads=int(payload.get("threads", 4) or 4),
                    force=bool(payload.get("force")),
                    resume=not bool(payload.get("no_resume")),
                    sequential=bool(payload.get("sequential")),
                )
                if is_form:
                    return self._redirect(f"/?page=twitch&slug={_up.quote(slug)}")
                return self._send(json.dumps({"ok": True, "run": rec}, ensure_ascii=False), "application/json; charset=utf-8")
            if u.path == "/action/maintain":
                report = C.maintain_repository(self.root)
                if is_form:
                    slug = str(payload.get("slug", "") or "")
                    dest = f"/?page=production&slug={_up.quote(slug)}" if slug else "/?page=production"
                    return self._redirect(dest)
                return self._send(json.dumps({"ok": True, "report": report}, ensure_ascii=False), "application/json; charset=utf-8")
            if is_form:
                return self._form_result(False, str(payload.get("slug", "")), "production", "ação desconhecida")
            return self._send(json.dumps({"error": "unknown action"}), "application/json; charset=utf-8", 404)
        except Exception as exc:
            if is_form:
                if "proposal" in u.path or "discard" in u.path:
                    page = "proposals"
                elif u.path == "/action/twitch-scrape":
                    page = "twitch"
                elif u.path in ("/action/new", "/action/pause", "/action/resume", "/action/abandon", "/action/maintain"):
                    page = "production"
                else:
                    page = "gates"
                return self._form_result(False, str(payload.get("slug", "")), page, str(exc))
            return self._send(json.dumps({"ok": False, "error": str(exc)}), "application/json; charset=utf-8", 400)


def run(root: str, host: str = "127.0.0.1", port: int = 8765, open_browser: bool = False) -> None:
    Handler.root = root
    Handler.csrf_token = secrets.token_urlsafe(32)
    srv = ThreadingHTTPServer((host, port), Handler)
    srv.daemon_threads = True
    print(f"Cuts Studio dashboard at http://{host}:{port}/ (root={root})")
    if open_browser:
        import webbrowser
        webbrowser.open(f"http://{host}:{port}/")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
        try:
            from . import twitch as TW
            TW.shutdown_jobs()
        except Exception:
            pass
