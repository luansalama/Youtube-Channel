"""Local dashboard server (binds 127.0.0.1 by default)."""
from __future__ import annotations
import html
import json
import urllib.parse as _up
from http.server import BaseHTTPRequestHandler, HTTPServer

from . import core as C
from . import dashboard as D
from . import proposals as P


def _parse_body(handler: BaseHTTPRequestHandler, raw: bytes):
    """Return (payload dict, is_form). Supports JSON + urlencoded forms (stdlib only)."""
    ctype = handler.headers.get("Content-Type", "") or ""
    if "application/x-www-form-urlencoded" in ctype:
        parsed = _up.parse_qs(raw.decode("utf-8", errors="replace"), keep_blank_values=True)
        return ({k: v[0] if len(v) == 1 else v for k, v in parsed.items()}, True)
    try:
        text = raw.decode("utf-8") if raw else "{}"
        if not text.strip():
            return ({}, False)
        # form fallback: plain key=value&... without proper content-type (alguns navegadores/proxies)
        if "=" in text and text.strip().startswith(("slug=", "gate=", "id=", "title=", "source_url=", "confirmo=", "by=", "reason=", "note=")) and "{" not in text:
            parsed = _up.parse_qs(text, keep_blank_values=True)
            return ({k: v[0] if len(v) == 1 else v for k, v in parsed.items()}, True)
        data = json.loads(text)
        return (data if isinstance(data, dict) else {}, False)
    except Exception:
        return ({}, False)


class Handler(BaseHTTPRequestHandler):
    root: str = "."

    def log_message(self, *a):  # quieter logs
        pass

    def _send(self, body: str, ctype="text/html; charset=utf-8", code=200):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, location: str):
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _form_result(self, ok: bool, slug: str, page: str, message: str):
        back = f"/?page={_up.quote(page)}&slug={_up.quote(slug)}" if slug else f"/?page={_up.quote(page)}"
        cls = "ok" if ok else "bad"
        title = "Ação concluída" if ok else "Falha na ação"
        body = (f"<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>"
                f"<title>{title}</title></head><body style='background:#333333;color:#FFFFFF;"
                f"font-family:Inter,system-ui,sans-serif;max-width:640px;margin:40px auto;padding:0 16px'>"
                f"<h1>{title}</h1><p class='{cls}'>{html.escape(message)}</p>"
                f"<p><a style='color:#0A84FF' href='{html.escape(back)}'>Voltar ao painel</a></p>"
                f"<script>setTimeout(function(){{location.href={json.dumps(back)}}},1500)</script>"
                f"</body></html>")
        self._send(body, code=200 if ok else 400)

    def do_GET(self):
        u = _up.urlparse(self.path)
        q = _up.parse_qs(u.query)
        page = (q.get("page", ["production"])[0])
        slug = (q.get("slug", [""])[0])
        if u.path == "/health":
            return self._send("ok", "text/plain")
        if u.path == "/api/status":
            try:
                st = C.workflow_status(self.root, slug) if slug else {"productions": C.list_productions(self.root)}
                return self._send(json.dumps(st, ensure_ascii=False), "application/json")
            except Exception as exc:
                return self._send(json.dumps({"error": str(exc)}), "application/json", 400)
        if u.path in ("/", "/index.html"):
            try:
                return self._send(D.render(self.root, page, slug))
            except Exception as exc:
                return self._send(f"<h1>Error</h1><pre>{exc}</pre>", code=500)
        return self._send("not found", "text/plain", 404)

    def do_POST(self):
        u = _up.urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        payload, is_form = _parse_body(self, raw)
        try:
            if u.path == "/action/approve":
                rec = C.approve_gate(self.root, payload["slug"], payload["gate"],
                                     by=payload.get("by", "showrunner") or "showrunner",
                                     note=payload.get("note", "") or "")
                if is_form:
                    dest = f"/?page=gates&slug={_up.quote(str(payload.get('slug', '')))}"
                    return self._redirect(dest)
                return self._send(json.dumps({"ok": True, "approval": rec}), "application/json")
            if u.path == "/action/advance":
                nxt = C.advance_stage(self.root, payload["slug"])
                if is_form:
                    dest = f"/?page=gates&slug={_up.quote(str(payload.get('slug', '')))}"
                    return self._redirect(dest)
                return self._send(json.dumps({"ok": True, "stage": nxt}), "application/json")
            if u.path == "/action/apply-proposal":
                rec = P.apply_proposal(self.root, payload["slug"], payload["id"],
                                       by=payload.get("by", "showrunner") or "showrunner")
                if is_form:
                    dest = f"/?page=proposals&slug={_up.quote(str(payload.get('slug', '')))}"
                    return self._redirect(dest)
                return self._send(json.dumps({"ok": True, "proposal": rec["id"]}), "application/json")
            if u.path == "/action/discard-proposal":
                rec = P.discard_proposal(self.root, payload["slug"], payload["id"],
                                         by=payload.get("by", "showrunner") or "showrunner")
                if is_form:
                    dest = f"/?page=proposals&slug={_up.quote(str(payload.get('slug', '')))}"
                    return self._redirect(dest)
                return self._send(json.dumps({"ok": True, "proposal": rec["id"]}), "application/json")
            if u.path == "/action/new":
                title = str(payload.get("title", "") or "").strip()
                if not title:
                    raise ValueError("title is required")
                slug_raw = str(payload.get("slug", "") or "").strip()
                slug_arg = slug_raw or None
                source_url = str(payload.get("source_url", "") or "")
                proj = C.create_production(self.root, title, slug_arg, source_url)
                new_slug = str(proj.get("slug", "") or slug_raw)
                if is_form:
                    dest = f"/?page=gates&slug={_up.quote(new_slug)}"
                    return self._redirect(dest)
                return self._send(json.dumps({"ok": True, "slug": new_slug, "project": proj}, ensure_ascii=False), "application/json")
            if u.path == "/action/pause":
                slug = str(payload.get("slug", "") or "")
                if not slug:
                    raise ValueError("slug is required")
                C.pause_production(self.root, slug,
                                   by=str(payload.get("by", "showrunner") or "showrunner"),
                                   reason=str(payload.get("reason", "") or ""))
                if is_form:
                    dest = f"/?page=production&slug={_up.quote(slug)}"
                    return self._redirect(dest)
                return self._send(json.dumps({"ok": True, "slug": slug, "state": "paused"}), "application/json")
            if u.path == "/action/resume":
                slug = str(payload.get("slug", "") or "")
                if not slug:
                    raise ValueError("slug is required")
                C.resume_production(self.root, slug,
                                    by=str(payload.get("by", "showrunner") or "showrunner"))
                if is_form:
                    dest = f"/?page=production&slug={_up.quote(slug)}"
                    return self._redirect(dest)
                return self._send(json.dumps({"ok": True, "slug": slug, "state": "active"}), "application/json")
            if u.path == "/action/abandon":
                slug = str(payload.get("slug", "") or "")
                if not slug:
                    raise ValueError("slug is required")
                if is_form and not payload.get("confirmo"):
                    raise ValueError("confirme o abandono marcando 'confirmo'")
                C.abandon_production(self.root, slug,
                                     by=str(payload.get("by", "showrunner") or "showrunner"),
                                     reason=str(payload.get("reason", "") or ""))
                if is_form:
                    dest = f"/?page=production&slug={_up.quote(slug)}"
                    return self._redirect(dest)
                return self._send(json.dumps({"ok": True, "slug": slug, "state": "abandoned"}), "application/json")
            if u.path == "/action/maintain":
                report = C.maintain_repository(self.root)
                if is_form:
                    slug = str(payload.get("slug", "") or "")
                    dest = f"/?page=production&slug={_up.quote(slug)}" if slug else "/?page=production"
                    return self._redirect(dest)
                return self._send(json.dumps({"ok": True, "report": report}, ensure_ascii=False), "application/json")
            if is_form:
                return self._form_result(False, str(payload.get("slug", "")), "production",
                                         "ação desconhecida")
            return self._send(json.dumps({"error": "unknown action"}), "application/json", 404)
        except Exception as exc:
            if is_form:
                if "proposal" in u.path or "discard" in u.path:
                    page = "proposals"
                elif u.path in ("/action/new", "/action/pause", "/action/resume", "/action/abandon", "/action/maintain"):
                    page = "production"
                else:
                    page = "gates"
                return self._form_result(False, str(payload.get("slug", "")), page, str(exc))
            return self._send(json.dumps({"ok": False, "error": str(exc)}), "application/json", 400)


def run(root: str, host: str = "127.0.0.1", port: int = 8765, open_browser: bool = False) -> None:
    Handler.root = root
    srv = HTTPServer((host, port), Handler)
    print(f"Cuts Studio dashboard at http://{host}:{port}/ (root={root})")
    if open_browser:
        import webbrowser
        webbrowser.open(f"http://{host}:{port}/")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
