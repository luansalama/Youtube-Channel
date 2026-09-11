"""Server-rendered dashboard for Cuts Studio.

The dashboard is deliberately stdlib-first: Python remains authoritative for domain
state/actions and the browser is only a progressively enhanced presentation layer.
CSS and JavaScript live in ``cstudio/static`` so the server can enforce a strict CSP.
"""
from __future__ import annotations

import csv
import difflib
import html
import io
import json
import os
import re
import urllib.parse as _up
from typing import Iterable

from . import core as C
from . import proposals as P


NAV_GROUPS = [
    ("Produção", [("production", "Produção"), ("sources", "Fontes"), ("videos", "Vídeos"), ("premiere", "Premiere")]),
    ("Sistema", [("diagnostics", "Diagnóstico")]),
]
NAV = [item for _group, items in NAV_GROUPS for item in items]
PAGE_LABELS = dict(NAV)
# Legacy/deep-link pages remain supported, but no longer compete in the primary nav.
PAGE_LABELS.update({
    "twitch": "Captura Twitch", "youtube": "YouTube Mirrors", "videos": "Vídeos", "reviews": "Revisões técnicas", "proposals": "Propostas", "gates": "Aprovações",
    "cutlist": "Cutlist", "sync": "Sincronização", "graphics": "Gráficos", "master": "Master", "release": "Release",
})

ARTIFACT_PAGES = {
    "cutlist": {
        "title": "Cutlist",
        "path": ".studio/internal/cutlist/cutlist.csv",
        "kind": "csv",
        "accent": "teal",
        "description": "Seleção editorial estruturada que alimenta a montagem. Revise IDs, fontes, timecodes e durações antes do lock.",
    },
    "sync": {
        "title": "Sincronização",
        "path": ".studio/internal/sync/sync-report.json",
        "kind": "json",
        "accent": "blue",
        "description": "Offsets e evidências de alinhamento entre fontes. O relatório deve explicar o que foi sincronizado e com qual confiança.",
    },
    "graphics": {
        "title": "Gráficos",
        "path": ".studio/internal/graphics/overlays.csv",
        "kind": "csv",
        "accent": "purple",
        "description": "Plano de overlays e elementos gráficos. Alterações posteriores ao graphics_lock exigem nova revisão.",
    },
    "master": {
        "title": "Master",
        "path": ".studio/internal/composition/master.json",
        "kind": "json",
        "accent": "green",
        "description": "Evidência do master de composição. Esta tela mostra readiness e o artefato produzido, sem fingir integração live com o NLE.",
    },
    "release": {
        "title": "Release",
        "path": ".studio/internal/release/metadata.json",
        "kind": "json",
        "accent": "red",
        "description": "Pacote final e metadados de release. Publicação continua fail-closed e nunca faz upload automaticamente.",
    },
}


def _e(value) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _q(value) -> str:
    return _up.quote(str(value if value is not None else ""), safe="")


def _csrf(token: str) -> str:
    if not token:
        return ""
    return f'<input type="hidden" name="csrf_token" value="{_e(token)}">'


def _icon(name: str) -> str:
    """Small, self-contained SVG icon set; no runtime icon library is required."""
    paths = {
        "production": '<rect x="2.2" y="2.2" width="11.6" height="11.6" rx="3"/><circle cx="8" cy="8" r="2.4"/>',
        "sources": '<path d="M2.2 4.2h4l1.2 1.5h6.4v6.1a1.7 1.7 0 0 1-1.7 1.7H3.9a1.7 1.7 0 0 1-1.7-1.7z"/><path d="M2.2 6h11.6"/>',
        "reviews": '<path d="M3 2.5h7.2l2.8 2.8v8.2H3z"/><path d="M10 2.8v2.8h2.8M5.3 8l1.4 1.4 3-3"/>',
        "premiere": '<rect x="2" y="2.5" width="12" height="11" rx="2.2"/><path d="M5.2 11V5h2.3a2 2 0 0 1 0 4H5.2M10.2 11V7.2M10.2 7.2h2"/>',
        "twitch": '<path d="M2.4 2.4h11.2v7.2l-3 3H8l-1.8 1.6v-1.6H3.8V4.2z"/><path d="M6.3 5.2v3.2M9.7 5.2v3.2"/>',
        "youtube": '<rect x="1.5" y="3.2" width="13" height="9.6" rx="3"/><path d="M6.5 5.8l4 2.2-4 2.2z"/>',
        "proposals": '<path d="M4 2h4.6L12 5.4V14H4z"/><path d="M8.5 2v3.5H12M6 8.5h4M6 10.8h4"/>',
        "gates": '<path d="M8 1.7l4.7 1.8v3.8c0 3.2-2.2 5.1-4.7 6.6-2.5-1.5-4.7-3.4-4.7-6.6V3.5z"/><path d="M5.9 7.9l1.4 1.4 2.9-3"/>',
        "cutlist": '<path d="M2.5 4h11M2.5 8h11M2.5 12h7"/><circle cx="11.8" cy="12" r="1.7"/>',
        "sync": '<path d="M13 8a5 5 0 1 1-1.2-3.3"/><path d="M12.6 1.8v3.3H9.3"/>',
        "graphics": '<rect x="2" y="3" width="12" height="10" rx="2"/><circle cx="5.4" cy="6.2" r="1.1"/><path d="M2.6 11.4l3.2-2.8 2.4 1.9 2-1.5 3.1 2.4"/>',
        "master": '<circle cx="8" cy="8" r="6"/><path d="M6.7 5.3l4.1 2.7-4.1 2.7z"/>',
        "release": '<path d="M8 12.5V2.7M4.7 5.9L8 2.7l3.3 3.2M2.8 14h10.4"/>',
        "diagnostics": '<path d="M1.7 8h2.7l1.4-3.7 2.9 7.4 1.5-3.7h4.1"/>',
        "menu": '<path d="M2 4.2h12M2 8h12M2 11.8h12"/>',
        "activity": '<path d="M8 2v6l3.8 2.1"/><circle cx="8" cy="8" r="6"/>',
        "check": '<path d="M3 8.2l3.1 3.1L13 4.8"/>',
        "arrow": '<path d="M3 8h10M9.5 4.5L13 8l-3.5 3.5"/>',
        "play": '<path d="M5.2 3.2l7 4.8-7 4.8z"/>',
        "pause": '<path d="M5.3 3.3v9.4M10.7 3.3v9.4"/>',
        "warning": '<path d="M8 1.9l6.1 11H1.9z"/><path d="M8 5.3v3.6M8 11.2h.01"/>',
        "external": '<path d="M9.2 2.5h4.3v4.3M13.2 2.8L7.6 8.4"/><path d="M12 8.2v4.2H3.6V4H8"/>',
    }
    p = paths.get(name, '<circle cx="8" cy="8" r="5.5"/>')
    return (
        '<svg class="icon" viewBox="0 0 16 16" width="16" height="16" fill="none" '
        'stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        f"{p}</svg>"
    )


def _badge(label: str, tone: str = "neutral") -> str:
    return f'<span class="badge badge-{_e(tone)}"><span class="badge-dot"></span>{_e(label)}</span>'


def _status_badge(status: str) -> str:
    s = str(status or "unknown")
    sl = s.lower()
    if sl in {"completed", "complete", "active", "applied", "approved", "ready"}:
        tone = "ok"
    elif sl in {"failed", "error", "blocked", "abandoned"}:
        tone = "danger"
    elif sl in {"running", "processing"}:
        tone = "info"
    elif sl in {"pending", "paused", "waiting"}:
        tone = "warn"
    else:
        tone = "neutral"
    return _badge(s, tone)


def _page_header(title: str, eyebrow: str, description: str = "", actions: str = "") -> str:
    return (
        '<header class="page-header">'
        '<div class="page-heading">'
        f'<div class="eyebrow">{_e(eyebrow)}</div><h1>{_e(title)}</h1>'
        + (f'<p>{_e(description)}</p>' if description else "")
        + '</div>'
        + (f'<div class="page-actions">{actions}</div>' if actions else "")
        + '</header>'
    )


def _metric(label: str, value: str, detail: str, tone: str = "blue", icon: str = "activity") -> str:
    return (
        f'<article class="metric metric-{_e(tone)}">'
        f'<div class="metric-top"><span>{_e(label)}</span><span class="metric-icon">{_icon(icon)}</span></div>'
        f'<strong>{_e(value)}</strong><span class="metric-detail">{_e(detail)}</span></article>'
    )


def _stage_data(root: str):
    try:
        return list(C.load_stages(root) or [])
    except Exception:
        return []


def _stage_label(root: str, stage_id: str) -> str:
    for s in _stage_data(root):
        if s.get("id") == stage_id:
            return str(s.get("label") or stage_id)
    return str(stage_id or "—")


def _pipeline(root: str, current: str) -> str:
    stages = _stage_data(root)
    if not stages:
        return '<p class="empty-state">Pipeline indisponível.</p>'
    ids = [str(s.get("id", "")) for s in stages]
    try:
        current_index = ids.index(str(current))
    except ValueError:
        current_index = 0
    items = []
    for i, stage in enumerate(stages):
        sid = str(stage.get("id", ""))
        label = str(stage.get("label") or sid)
        gate = str(stage.get("gate") or "")
        state = "done" if i < current_index else ("current" if i == current_index else "upcoming")
        marker = "✓" if i < current_index else str(i + 1)
        items.append(
            f'<li class="pipeline-step pipeline-{state}" aria-current="{"step" if state == "current" else "false"}">'
            f'<span class="pipeline-index">{_e(marker)}</span><span class="pipeline-copy"><strong>{_e(label)}</strong>'
            f'<small>{_e(sid)}{(" · gate " + _e(gate)) if gate else ""}</small></span></li>'
        )
    return f'<ol class="pipeline" aria-label="Pipeline da produção">{"".join(items)}</ol>'


def _activity_feed(history: Iterable[dict], limit: int = 8) -> str:
    rows = list(history or [])[-limit:]
    if not rows:
        return '<p class="empty-state compact">Sem atividade registrada.</p>'
    out = []
    for h in reversed(rows):
        event = str(h.get("event") or "atividade")
        at = str(h.get("at") or "")
        extra = []
        for key in ("gate", "by", "to", "from", "proposal_id", "reason"):
            if h.get(key):
                extra.append(f"{key}={h.get(key)}")
        tone = "ok" if any(k in event.lower() for k in ("approv", "aplica", "advanc", "conclu")) else (
            "danger" if any(k in event.lower() for k in ("fail", "erro", "block", "aband", "discard")) else "neutral"
        )
        out.append(
            '<li class="activity-item"><span class="activity-mark"></span><div>'
            f'<div class="activity-title">{_badge("Evento", tone)} <strong>{_e(event)}</strong></div>'
            + (f'<div class="activity-detail">{_e(" · ".join(extra))}</div>' if extra else "")
            + f'<time>{_e(at)}</time></div></li>'
        )
    return f'<ul class="activity-list">{"".join(out)}</ul>'


def _history_for(root: str, slug: str) -> list[dict]:
    if not slug:
        return []
    try:
        _dir, project = C.load_project(root, slug)
        return list((project or {}).get("history", []) or [])
    except Exception:
        return []


def _nav(page: str, slug: str) -> str:
    chunks = []
    for group, items in NAV_GROUPS:
        links = []
        for key, label in items:
            href = f'/?page={_q(key)}' + (f'&slug={_q(slug)}' if slug else "")
            links.append(
                f'<a class="nav-link{" active" if key == page else ""}" href="{href}" '
                f'aria-current="{"page" if key == page else "false"}">{_icon(key)}<span>{_e(label)}</span></a>'
            )
        chunks.append(f'<div class="nav-group"><div class="nav-label">{_e(group)}</div>{"".join(links)}</div>')
    return "".join(chunks)


def _production_switcher(productions: list[dict], page: str, slug: str) -> str:
    if not productions:
        return '<a class="button button-primary" href="/?page=production">Criar produção</a>'
    opts = []
    for p in productions:
        ps = str(p.get("slug") or "")
        title = str(p.get("title") or ps)
        opts.append(f'<option value="{_e(ps)}"{" selected" if ps == slug else ""}>{_e(title)}</option>')
    return (
        '<form class="production-switcher" method="get" action="/">'
        f'<input type="hidden" name="page" value="{_e(page)}">'
        '<label for="production-switch">Produção</label>'
        f'<select id="production-switch" name="slug">{"".join(opts)}</select>'
        '<button class="button button-ghost button-icon-only" type="submit" aria-label="Abrir produção">'
        f'{_icon("arrow")}</button></form>'
    )


def _context_panel(root: str, slug: str, status: dict | None, history: list[dict]) -> str:
    if not slug or not status:
        summary = '<p class="empty-state compact">Selecione uma produção para acompanhar contexto e atividade.</p>'
    else:
        stage = str(status.get("stage") or "—")
        state = str(status.get("state") or "—")
        blocked = bool(status.get("blocked"))
        summary = (
            '<dl class="context-facts">'
            f'<div><dt>Fase</dt><dd>{_e(_stage_label(root, stage))}</dd></div>'
            f'<div><dt>Estado</dt><dd>{_e(state)}</dd></div>'
            f'<div><dt>Readiness</dt><dd>{_badge("Bloqueado" if blocked else "Pronto", "danger" if blocked else "ok")}</dd></div>'
            '</dl>'
        )
    return (
        '<aside class="context-panel" id="context-panel" aria-label="Contexto da produção">'
        '<div class="context-head"><div><span class="eyebrow">Contexto</span><h2>Agora</h2></div>'
        '<button class="icon-button context-close" type="button" data-close-context aria-label="Fechar contexto">×</button></div>'
        f'<section class="context-card"><h3>Resumo</h3>{summary}</section>'
        f'<section class="context-card context-activity"><h3>Atividade recente</h3>{_activity_feed(history)}</section>'
        '</aside>'
    )


def layout(
    root: str,
    page: str,
    body: str,
    slug: str = "",
    productions: list[dict] | None = None,
    status: dict | None = None,
    history: list[dict] | None = None,
    csrf_token: str = "",
) -> str:
    productions = list(productions or [])
    history = list(history or [])
    page = page if page in PAGE_LABELS else "production"
    label = PAGE_LABELS.get(page, page)
    if slug and status:
        title = str(status.get("title") or slug)
        stage = str(status.get("stage") or "")
        crumb = f'<span>{_e(label)}</span><span class="crumb-sep">/</span><strong>{_e(title)}</strong>'
        stage_chip = _badge(_stage_label(root, stage), "info") if stage else ""
    else:
        crumb = f'<strong>{_e(label)}</strong>'
        stage_chip = ""
    token_meta = f'<meta name="csrf-token" content="{_e(csrf_token)}">' if csrf_token else ""
    return f'''<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark">
{token_meta}
<title>Cuts Studio · {_e(label)}</title>
<link rel="stylesheet" href="/static/dashboard.css?v=9">
<script src="/static/dashboard.js?v=9" defer></script>
</head>
<body data-page="{_e(page)}" data-slug="{_e(slug)}">
<div class="app-shell">
<div class="mobile-backdrop" data-close-sidebar></div>
<aside class="sidebar" id="sidebar" aria-label="Navegação principal">
  <a class="brand" href="/?page=production"><span class="brand-mark">C</span><span><strong>Cuts Studio</strong><small>Production cockpit</small></span></a>
  <nav class="nav">{_nav(page, slug)}</nav>
  <div class="sidebar-foot"><span class="status-light"></span><span>Local · determinístico</span></div>
</aside>
<main class="main-shell">
  <header class="topbar">
    <div class="topbar-left">
      <button class="icon-button mobile-menu" type="button" data-open-sidebar aria-label="Abrir menu">{_icon("menu")}</button>
      <nav class="breadcrumb" aria-label="Breadcrumb"><a href="/?page=production">Cuts Studio</a><span class="crumb-sep">/</span>{crumb}</nav>
      {stage_chip}
    </div>
    <div class="topbar-actions">
      {_production_switcher(productions, page, slug)}
      <button class="icon-button context-toggle" type="button" data-open-context aria-label="Abrir contexto">{_icon("activity")}</button>
    </div>
  </header>
  <div class="workspace">
    <div class="content" id="main-content">{body}</div>
    {_context_panel(root, slug, status, history)}
  </div>
</main>
</div>
<dialog class="confirm-dialog" id="confirm-dialog">
  <form method="dialog">
    <div class="dialog-icon">{_icon("warning")}</div>
    <h2>Confirmar ação</h2>
    <p id="confirm-message">Esta ação requer confirmação.</p>
    <div class="dialog-actions"><button class="button button-ghost" value="cancel">Cancelar</button><button class="button button-danger" value="confirm">Confirmar</button></div>
  </form>
</dialog>
</body>
</html>'''


def _checks_table(checks: Iterable[dict]) -> str:
    rows = []
    for c in list(checks or []):
        ok = bool(c.get("ok"))
        rows.append(
            '<tr>'
            f'<td>{_badge("OK" if ok else "Falha", "ok" if ok else "danger")}</td>'
            f'<td><strong>{_e(c.get("label", ""))}</strong></td>'
            f'<td class="muted-cell">{_e(c.get("detail", ""))}</td></tr>'
        )
    if not rows:
        return '<p class="empty-state compact">Nenhuma verificação disponível.</p>'
    return (
        '<div class="table-scroll"><table><thead><tr><th>Status</th><th>Verificação</th><th>Detalhe</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
    )


def _gates_table(gates: Iterable[dict], slug: str, csrf_token: str, current_stage: str = "") -> str:
    rows = []
    for g in list(gates or []):
        approved = bool(g.get("approved"))
        action = '<span class="table-dash">—</span>'
        if not approved and str(g.get("stage") or "") == str(current_stage or ""):
            action = (
                '<form class="inline-form" method="post" action="/action/approve">'
                f'{_csrf(csrf_token)}<input type="hidden" name="slug" value="{_e(slug)}">'
                f'<input type="hidden" name="gate" value="{_e(g.get("gate", ""))}">'
                '<button class="button button-success button-small" type="submit">Aprovar</button></form>'
            )
        elif not approved:
            action = '<span class="muted-cell">Aguarda fase</span>'
        rows.append(
            '<tr>'
            f'<td><code>{_e(g.get("gate", ""))}</code></td><td>{_e(g.get("stage", ""))}</td>'
            f'<td>{_badge("Aprovado" if approved else "Pendente", "ok" if approved else "warn")}</td>'
            f'<td class="muted-cell">{_e(g.get("detail", ""))}</td><td>{action}</td></tr>'
        )
    return (
        '<div class="table-scroll"><table><thead><tr><th>Gate</th><th>Fase</th><th>Situação</th><th>Detalhe</th><th>Ação</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
    )


def _proposal_current_text(root: str, slug: str, rel: str) -> str:
    """Read a proposal target defensively; proposal paths must stay in production."""
    rel = str(rel or "").replace("\\", "/")
    if not rel or rel.startswith("/") or ".." in rel.split("/"):
        return ""
    vdir = os.path.realpath(C.prod_path(root, slug))
    path = os.path.realpath(os.path.join(vdir, *rel.split("/")))
    try:
        if os.path.commonpath([vdir, path]) != vdir or not os.path.isfile(path):
            return ""
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except (OSError, ValueError):
        return ""


def _proposal_diff(before: str, after: str, rel: str) -> str:
    before_lines = str(before or "").splitlines()
    after_lines = str(after or "").splitlines()
    diff = list(difflib.unified_diff(
        before_lines,
        after_lines,
        fromfile=f"atual/{rel}",
        tofile=f"proposto/{rel}",
        lineterm="",
        n=3,
    ))
    if not diff:
        return '<div class="proposal-no-diff">Sem diferença textual neste artefato.</div>'
    # Keep a pathological generated file from making the review page enormous.
    clipped = diff[:1800]
    rendered = []
    for line in clipped:
        klass = "diff-line"
        if line.startswith("+++") or line.startswith("---"):
            klass += " diff-file"
        elif line.startswith("+"):
            klass += " diff-add"
        elif line.startswith("-"):
            klass += " diff-remove"
        elif line.startswith("@@"):
            klass += " diff-hunk"
        rendered.append(f'<span class="{klass}">{_e(line)}</span>')
    if len(diff) > len(clipped):
        rendered.append('<span class="diff-line diff-hunk">… diff truncado para revisão no dashboard …</span>')
    return '<pre class="proposal-diff">' + "\n".join(rendered) + '</pre>'


def _proposal_list(items: list[str], empty: str) -> str:
    if not items:
        return f'<p class="proposal-empty-copy">{_e(empty)}</p>'
    return '<ul class="proposal-note-list">' + ''.join(f'<li>{_e(item)}</li>' for item in items) + '</ul>'


def _proposal_artifact_review(root: str, slug: str, rel: str, proposed: str, *, main: bool = False) -> str:
    current = _proposal_current_text(root, slug, rel)
    label = "Documento principal" if main else "Arquivo adicional"
    current_state = "arquivo existente" if current else "novo arquivo"
    return (
        '<section class="proposal-artifact">'
        f'<div class="proposal-artifact-head"><div><span class="eyebrow">{_e(label)}</span><h4><code>{_e(rel)}</code></h4></div>'
        f'<span class="muted-cell">{_e(current_state)}</span></div>'
        '<div class="proposal-review-section"><div class="proposal-section-title"><strong>O que muda</strong><span>verde adiciona · vermelho remove</span></div>'
        f'{_proposal_diff(current, proposed, rel)}</div>'
        '<details class="proposal-full-document"><summary>Ver conteúdo proposto completo</summary>'
        f'<pre class="code-block proposal-document">{_e(proposed)}</pre></details>'
        '</section>'
    )


def _proposal_queue(root: str, props: list[dict], slug: str, csrf_token: str) -> str:
    pending = [p for p in props if str(p.get("status")) == "pending"]
    if not pending:
        return '<div class="empty-state"><strong>Fila limpa</strong><span>Não há propostas aguardando revisão humana.</span></div>'
    cards = []
    for p in pending:
        pid = str(p.get("id") or "")
        document_path = str(p.get("document_path") or "")
        document = str(p.get("document") or "")
        files = dict(p.get("files") or {})
        warnings = [str(x) for x in (p.get("warnings") or [])]
        questions = [str(x) for x in (p.get("questions") or [])]
        blockers = list(p.get("blockers") or [])
        runner = str(p.get("runner") or "manual")
        model = str(p.get("model") or "")
        effort = str(p.get("reasoning_effort") or "")
        validation_ok = str(p.get("deterministic_validation") or "") == "passed"
        artifacts = ""
        if document_path:
            artifacts += _proposal_artifact_review(root, slug, document_path, document, main=True)
        for rel, content in files.items():
            artifacts += _proposal_artifact_review(root, slug, str(rel), str(content))
        if not artifacts:
            artifacts = '<div class="notice notice-danger"><div><strong>Proposal sem artefatos revisáveis</strong><span>Não aplique esta proposal.</span></div></div>'
        blocker_html = ""
        if blockers:
            blocker_html = (
                '<div class="notice notice-danger proposal-blockers"><div><strong>Validação encontrou bloqueios</strong>'
                '<span>Aplicar não significa que a fase ficará pronta. Revise estes itens primeiro.</span>'
                + '<ul class="proposal-note-list">'
                + ''.join(f'<li><strong>{_e(b.get("label", "check"))}</strong> — {_e(b.get("detail", ""))}</li>' for b in blockers)
                + '</ul></div></div>'
            )
        runner_bits = [runner]
        if model:
            runner_bits.append(model)
        if effort:
            runner_bits.append(f"reasoning {effort}")
        cards.append(
            '<article class="review-card">'
            '<div class="review-copy">'
            f'<div class="review-meta">{_badge("Pendente", "warn")}{_badge("Validação OK" if validation_ok else "Com bloqueios", "ok" if validation_ok else "danger")}<code>{_e(pid)}</code><span>{_e(" · ".join(runner_bits))}</span></div>'
            f'<h3>{_e(p.get("summary", "Proposta sem resumo"))}</h3>'
            '<p>Abra e confira exatamente o que será alterado antes de tomar qualquer decisão.</p>'
            '</div>'
            '<details class="proposal-inspector">'
            '<summary><span>Abrir proposta</span><small>diff + conteúdo completo</small></summary>'
            '<div class="proposal-inspector-body">'
            + blocker_html
            + '<div class="proposal-overview">'
            + f'<div><span>Runner</span><strong>{_e(runner)}</strong></div>'
            + f'<div><span>Modelo</span><strong>{_e(model or "não registrado")}</strong></div>'
            + f'<div><span>Reasoning</span><strong>{_e(effort or "não registrado")}</strong></div>'
            + f'<div><span>Criada</span><strong>{_e(p.get("created_at") or "—")}</strong></div>'
            + '</div>'
            + artifacts
            + '<div class="proposal-notes-grid">'
            + '<section><span class="eyebrow">Warnings</span><h4>Atenção antes de aplicar</h4>' + _proposal_list(warnings, "Nenhum warning informado pelo agente.") + '</section>'
            + '<section><span class="eyebrow">Perguntas</span><h4>O que ainda precisa de resposta</h4>' + _proposal_list(questions, "Nenhuma pergunta pendente informada pelo agente.") + '</section>'
            + '</div>'
            + '<div class="proposal-decision-actions"><div><strong>Decisão humana</strong><span>Aplicar grava os artefatos acima. Descartar preserva o registro no histórico.</span></div><div class="review-actions">'
            + '<form method="post" action="/action/apply-proposal" data-confirm="Aplicar esta proposal exatamente como revisada acima?">'
            + f'{_csrf(csrf_token)}<input type="hidden" name="slug" value="{_e(slug)}"><input type="hidden" name="id" value="{_e(pid)}">'
            + '<button class="button button-primary" type="submit">Aplicar proposta</button></form>'
            + '<form method="post" action="/action/discard-proposal" data-confirm="Descartar esta proposta? O registro será preservado no histórico.">'
            + f'{_csrf(csrf_token)}<input type="hidden" name="slug" value="{_e(slug)}"><input type="hidden" name="id" value="{_e(pid)}">'
            + '<button class="button button-ghost" type="submit">Descartar</button></form>'
            + '</div></div></div></details></article>'
        )
    return f'<div class="review-queue">{"".join(cards)}</div>'


def _proposal_history(props: list[dict]) -> str:
    old = [p for p in props if str(p.get("status")) != "pending"]
    if not old:
        return '<p class="empty-state compact">Nenhuma proposta processada ainda.</p>'
    rows = []
    for p in old[:50]:
        status = str(p.get("status") or "")
        rows.append(
            f'<tr><td><code>{_e(p.get("id", ""))}</code></td><td>{_e(p.get("runner", ""))}</td>'
            f'<td>{_status_badge(status)}</td><td>{_e(str(p.get("summary", ""))[:160])}</td></tr>'
        )
    return '<div class="table-scroll"><table><thead><tr><th>ID</th><th>Runner</th><th>Status</th><th>Resumo</th></tr></thead>' + f'<tbody>{"".join(rows)}</tbody></table></div>'


def _readiness_summary(root: str, st: dict, pending_props: int) -> str:
    checks = list(st.get("checks", []) or [])
    failed = sum(1 for c in checks if not c.get("ok"))
    stage = str(st.get("stage") or "—")
    total_stages = len(_stage_data(root)) or 12
    ids = [str(s.get("id")) for s in _stage_data(root)]
    try:
        stage_no = ids.index(stage) + 1
    except ValueError:
        stage_no = 1
    readiness = "Pronto" if not failed else f"{failed} pendência" + ("s" if failed != 1 else "")
    return (
        '<div class="metric-grid metric-grid-3 cockpit-metrics">'
        + _metric("Fase", _stage_label(root, stage), f"{stage_no} de {total_stages}", "blue", "production")
        + _metric("Readiness", readiness, "checks determinísticos da fase", "green" if not failed else "red", "check")
        + _metric("Revisões", str(pending_props), "proposal(s) aguardando decisão", "purple" if pending_props else "teal", "reviews")
        + '</div>'
    )


def _macro_pipeline(current: str) -> str:
    from . import operations as OPS
    items = []
    for item in OPS.macro_progress(current):
        state = item["state"]
        marker = "✓" if state == "done" else ("•" if state == "current" else "")
        items.append(
            f'<li class="journey-step journey-{_e(state)}"><span class="journey-dot">{_e(marker)}</span>'
            f'<span><strong>{_e(item["label"])}</strong><small>{_e(" · ".join(item["stages"]))}</small></span></li>'
        )
    return f'<ol class="journey" aria-label="Jornada da produção">{"".join(items)}</ol>'


def _stage_details(root: str, st: dict, slug: str) -> str:
    failed = [c for c in st.get("checks", []) or [] if not c.get("ok")]
    summary = "Tudo que o harness exige nesta fase está atendido." if not failed else f"{len(failed)} verificação(ões) ainda precisam ser resolvidas."
    return (
        '<details class="technical-details"><summary><span>Detalhes da fase</span><small>' + _e(summary) + '</small></summary>'
        '<div class="technical-details-body"><div class="two-column details-grid">'
        '<section><span class="eyebrow">Checks</span><h3>O que o harness está verificando</h3>' + _checks_table(st.get("checks", [])) + '</section>'
        '<section><span class="eyebrow">Pipeline interno</span><h3>12 fases do harness</h3>' + _pipeline(root, str(st.get("stage") or "")) + '</section>'
        '</div><div class="details-links">'
        f'<a class="text-link" href="/?page=gates&slug={_q(slug)}">Abrir gates e checks {_icon("arrow")}</a>'
        '</div></div></details>'
    )


def _runner_client_config(ui: dict) -> dict:
    return {
        "models": ui.get("models") or {},
        "model_labels": ui.get("model_labels") or {},
        "efforts": ui.get("efforts") or {},
        "model_efforts": ui.get("model_efforts") or {},
        "model_default_efforts": ui.get("model_default_efforts") or {},
        "defaults": ui.get("defaults") or {},
        "effort_labels": ui.get("effort_labels") or {},
    }


def _runner_options(root: str, stage_id: str, selected_runner: str = "") -> tuple[str, dict]:
    from . import runners as R
    statuses = R.quick_runner_statuses()
    ui = R.runner_ui_config(root, stage_id)
    preferred = str(ui.get("preferred") or "codex")
    selected_runner = selected_runner if selected_runner in R.CLI_RUNNERS else preferred
    options = []
    for key in R.CLI_RUNNERS:
        item = statuses.get(key) or {}
        available = item.get("available")
        suffix = " · disponível" if available is True else (" · não detectado" if available is False else "")
        recommended = " · recomendado nesta fase" if key == preferred else ""
        selected = " selected" if key == selected_runner else ""
        options.append(f'<option value="{_e(key)}"{selected}>{_e(item.get("label") or key)}{_e(recommended + suffix)}</option>')
    return "".join(options), ui


def _runner_selection(ui: dict, runner: str, model: str = "", effort: str = "") -> tuple[str, str]:
    defaults = (ui.get("defaults") or {}).get(runner) or {}
    models = (ui.get("models") or {}).get(runner) or []
    model = str(model or defaults.get("model") or (models[0] if models else ""))
    model_efforts = ((ui.get("model_efforts") or {}).get(runner) or {}).get(model) or []
    model_default = ((ui.get("model_default_efforts") or {}).get(runner) or {}).get(model)
    effort = str(effort or model_default or defaults.get("reasoning_effort") or (model_efforts[0] if model_efforts else ""))
    if model_efforts and effort not in model_efforts:
        effort = str(model_default or model_efforts[0])
    return model, effort


def _runner_model_options(ui: dict, runner: str, selected_model: str) -> str:
    models = list((ui.get("models") or {}).get(runner) or [])
    labels = (ui.get("model_labels") or {}).get(runner) or {}
    if selected_model and selected_model not in models:
        models.insert(0, selected_model)
    out = []
    for model in models:
        label = str(labels.get(model) or model)
        if model == selected_model and model not in ((ui.get("model_labels") or {}).get(runner) or {}):
            label += " · legacy/custom"
        out.append(f'<option value="{_e(model)}"{" selected" if model == selected_model else ""}>{_e(label)}</option>')
    return "".join(out)


def _runner_effort_options(ui: dict, runner: str, model: str, selected_effort: str) -> str:
    efforts = list((((ui.get("model_efforts") or {}).get(runner) or {}).get(model) or []))
    labels = ui.get("effort_labels") or {}
    if selected_effort and selected_effort not in efforts:
        efforts.insert(0, selected_effort)
    return "".join(
        f'<option value="{_e(value)}"{" selected" if value == selected_effort else ""}>{_e(labels.get(value) or value)}</option>'
        for value in efforts
    )

def _source_job_progress(root: str, slug: str, job: dict) -> str:
    """Render durable discovery-transcription state when available."""
    from . import source_media as SM
    from . import video_plans as VP

    if str(job.get("status") or "") != "running":
        return ""
    params = dict(job.get("params") or {})
    job_kind = str(job.get("type") or "")
    candidates: list[tuple[str, str]] = []
    batch_label = ""

    if job_kind == "source-transcribe":
        asset_id = str(params.get("asset_id") or "").strip()
        if asset_id:
            candidates.append((asset_id, asset_id))
    elif job_kind == "source-audio-transcribe":
        vod_id = str(params.get("vod_id") or "").strip()
        if vod_id:
            candidates.append((f"twitch-video-{vod_id}", f"Twitch {vod_id} · áudio temporário"))
    elif job_kind in {"source-prepare-vods", "source-batch-audio-transcribe"}:
        raw_ids = params.get("vod_ids") or []
        if isinstance(raw_ids, str):
            raw_ids = [x for x in raw_ids.split(",") if x]
        vod_ids = [str(x).strip() for x in raw_ids if str(x).strip()]
        catalog = {str(x.get("vod_id") or ""): x for x in VP.source_catalog(root, slug)}
        prepared = 0
        for index, vod_id in enumerate(vod_ids, 1):
            source = catalog.get(vod_id) or {}
            twitch_media = source.get("twitch_media") if isinstance(source.get("twitch_media"), dict) else None
            aid = str((twitch_media or {}).get("asset_id") or f"twitch-video-{vod_id}")
            candidates.append((aid, f"VOD {index}/{len(vod_ids)} · Twitch {vod_id}"))
            if source.get("proposal_ready"):
                prepared += 1
            if job_kind == "source-prepare-vods" and bool(params.get("include_masters", True)):
                for media in source.get("media_sources") or []:
                    if str(media.get("platform") or "") != "youtube":
                        continue
                    aid = str(media.get("asset_id") or "")
                    if aid:
                        candidates.append((aid, f"VOD {index}/{len(vod_ids)} · YouTube master"))
        if vod_ids:
            batch_label = f"{prepared}/{len(vod_ids)} VOD(s) com transcript de descoberta concluído"

    running_rec = None
    running_label = ""
    for asset_id, label in candidates:
        status = SM.transcript_status(root, slug, asset_id)
        if str(status.get("status") or "") == "running":
            running_rec, running_label = status, label
            break

    if not running_rec:
        # During the download portion of a batch there is intentionally no fake
        # transcription percentage. The log remains visible until Whisper writes
        # its first progress.json.
        if batch_label:
            return '<div class="transcription-progress is-waiting"><div class="transcription-progress-head"><div><span class="eyebrow">Preparação em andamento</span><strong>Aguardando etapa de transcrição</strong></div><span>' + _e(batch_label) + '</span></div></div>'
        return ""

    total_chunks = max(0, int(running_rec.get("chunks_total") or 0))
    done_chunks = max(0, int(running_rec.get("chunks_completed") or 0))
    current_chunk = max(0, int(running_rec.get("current_chunk") or min(total_chunks, done_chunks + 1)))
    try:
        percent = float(running_rec.get("percent") or (done_chunks / total_chunks * 100 if total_chunks else 0.0))
    except (TypeError, ValueError, ZeroDivisionError):
        percent = 0.0
    percent = max(0.0, min(100.0, percent))
    try:
        duration = float(running_rec.get("duration_seconds") or 0.0)
        processed = float(running_rec.get("processed_seconds") or 0.0)
    except (TypeError, ValueError):
        duration, processed = 0.0, 0.0
    if processed <= 0 and done_chunks and running_rec.get("chunk_seconds"):
        try:
            processed = min(duration or float("inf"), done_chunks * float(running_rec.get("chunk_seconds") or 0))
        except (TypeError, ValueError):
            processed = 0.0
    asset_id = str(running_rec.get("asset_id") or "")
    label = running_label or asset_id
    time_copy = f"{_format_hms(processed)} / {_format_hms(duration)} de mídia" if duration > 0 else f"{_format_hms(processed)} processados"
    chunk_copy = f"{done_chunks}/{total_chunks} chunks" if total_chunks else "passagem única"
    current_copy = f"chunk atual {current_chunk}/{total_chunks}" if current_chunk and total_chunks else "segment timestamps"
    updated = str(running_rec.get("updated_at") or running_rec.get("started_at") or "")
    return (
        '<div class="transcription-progress">'
        '<div class="transcription-progress-head"><div><span class="eyebrow">Whisper Turbo · transcrevendo</span>'
        f'<strong>{_e(label)}</strong><small><code>{_e(asset_id)}</code></small></div><b>{_e(f"{percent:.1f}%")}</b></div>'
        f'<progress class="transcription-progress-bar" max="100" value="{_e(f"{percent:.1f}")}">{_e(f"{percent:.1f}%")}</progress>'
        '<div class="transcription-progress-meta">'
        f'<span><strong>{_e(chunk_copy)}</strong><small>concluídos</small></span>'
        f'<span><strong>{_e(time_copy)}</strong><small>cobertura processada</small></span>'
        f'<span><strong>{_e(current_copy)}</strong><small>em execução</small></span>'
        f'<span><strong>{_e(updated or "—")}</strong><small>última atualização</small></span>'
        '</div>'
        + (f'<div class="transcription-progress-batch">{_e(batch_label)}</div>' if batch_label else '')
        + '</div>'
    )


def render_studio_job(root: str, slug: str, job_type: str = "") -> str:
    from . import jobs as J
    J.mark_stale_failed(root, slug)
    if job_type == "video-proposals":
        jobs = [j for j in J.list_jobs(root, slug, 50) if j.get("type") in {"video-proposal", "video-proposal-refine", "video-candidate-precision"}]
        job = jobs[0] if jobs else None
    elif job_type == "sources":
        jobs = [j for j in J.list_jobs(root, slug, 50) if j.get("type") in {
            "source-download-twitch", "source-batch-download-twitch", "source-download-audio",
            "source-audio-transcribe", "source-batch-audio-transcribe", "source-transcribe", "source-prepare-vods"
        }]
        job = jobs[0] if jobs else None
    else:
        job = J.latest_job(root, slug, job_type) if job_type else J.latest_job(root, slug)
    if not job:
        return '<div class="job-empty" data-studio-job-live data-running="false"><span>Nenhuma execução recente.</span></div>'
    running = str(job.get("status") or "") == "running"
    log = J.tail_log(root, slug, str(job.get("id") or ""), 14000)
    source_progress = _source_job_progress(root, slug, job) if str(job.get("type") or "").startswith("source-") else ""
    result = job.get("result_summary") or {}
    result_copy = ""
    if result:
        if result.get("video_proposal_id"):
            result_copy = f'<div class="job-result"><strong>Proposta de vídeo pronta</strong><span>{_e(result.get("summary") or result.get("video_proposal_id"))}</span><a class="button button-primary button-small" href="/?page=videos&slug={_q(slug)}#video-proposal-{_q(result.get("video_proposal_id"))}">Abrir proposta</a></div>'
        elif result.get("proposal_id"):
            result_copy = f'<div class="job-result"><strong>Proposal técnica pronta</strong><span>{_e(result.get("summary") or result.get("proposal_id"))}</span><a class="button button-primary button-small" href="/?page=reviews&slug={_q(slug)}">Revisar proposal</a></div>'
        elif result.get("files"):
            result_copy = f'<div class="job-result"><strong>Handoff preparado</strong><span>{_e(len(result.get("files") or []))} arquivo(s) prontos para o Premiere.</span></div>'
        elif result.get("asset_id") and result.get("segment_count") is not None:
            result_copy = f'<div class="job-result"><strong>Transcrição de descoberta pronta</strong><span>{_e(result.get("asset_id"))} · {_e(result.get("segment_count"))} segmentos · {_e(result.get("timestamp_mode") or "segment")}.</span><a class="button button-primary button-small" href="/?page=videos&slug={_q(slug)}">Abrir Vídeos</a></div>'
        elif result.get("asset_id") and result.get("path"):
            result_copy = f'<div class="job-result"><strong>VOD completo baixado</strong><span>{_e(result.get("asset_id"))} está registrado no pool compartilhado.</span></div>'
        elif result.get("vods_prepared") is not None:
            result_copy = f'<div class="job-result"><strong>Fontes preparadas</strong><span>{_e(result.get("vods_prepared") or 0)}/{_e(result.get("vods_requested") or 0)} VOD(s) com original Twitch + transcrição por segmento. Masters locais também foram enriquecidos quando disponíveis.</span><a class="button button-primary button-small" href="/?page=videos&slug={_q(slug)}">Abrir Vídeos</a></div>'
        elif result.get("vods_transcribed") is not None:
            result_copy = f'<div class="job-result"><strong>Descoberta em lote pronta</strong><span>{_e(result.get("vods_transcribed") or 0)}/{_e(result.get("vods_requested") or 0)} VOD(s) transcritos; os áudios temporários foram limpos após sucesso.</span><a class="button button-primary button-small" href="/?page=videos&slug={_q(slug)}">Abrir Vídeos</a></div>'
        elif result.get("vods_downloaded") is not None:
            result_copy = f'<div class="job-result"><strong>Sources baixados</strong><span>{_e(result.get("vods_downloaded") or 0)}/{_e(result.get("vods_requested") or 0)} VOD(s) materializados sem forçar transcrição.</span></div>'
        elif result.get("video_id") and result.get("candidate_count") is not None:
            result_copy = f'<div class="job-result"><strong>Precisão dos candidates pronta</strong><span>{_e(result.get("candidate_count") or 0)} intervalo(s) · {_e(result.get("word_count") or 0)} word timestamps. O frame-level continua no Premiere.</span><a class="button button-primary button-small" href="/?page=videos&slug={_q(slug)}#planned-videos">Abrir vídeo</a></div>'
        elif "doctor_ok" in result:
            result_copy = f'<div class="job-result"><strong>{"Diagnóstico OK" if result.get("doctor_ok") else "Diagnóstico com pendências"}</strong><span>Veja o log para os detalhes do bridge local.</span></div>'
    error = f'<div class="notice notice-danger"><div><strong>Execução falhou</strong><span>{_e(job.get("error"))}</span></div></div>' if job.get("status") == "failed" else ""
    return (
        f'<div class="studio-job" data-studio-job-live data-running="{str(running).lower()}" data-job-id="{_e(job.get("id"))}">'
        '<div class="job-summary"><div>'
        f'<span class="eyebrow">Execução atual</span><h3>{_e(str(job.get("type") or "job").replace("-", " "))}</h3>'
        f'<p>{_status_badge(str(job.get("status") or "unknown"))} <span class="muted-cell">{_e(job.get("started_at") or "")}</span></p>'
        '</div>'
        f'<span class="live-dot{" is-live" if running else ""}"></span></div>{error}{result_copy}{source_progress}'
        '<div class="log-panel"><div class="log-head"><span>Log</span><button class="button button-ghost button-small" type="button" data-copy-log>Copiar</button></div>'
        f'<pre class="log-output">{_e(log or "Aguardando saída do worker…")}</pre></div></div>'
    )


def _agent_workspace(root: str, slug: str, st: dict, csrf_token: str) -> str:
    from . import operations as OPS, jobs as J
    ux = OPS.experience(root, slug, st)
    if not ux.get("agent"):
        return ""
    J.mark_stale_failed(root, slug)
    latest = J.latest_job(root, slug, "agent-proposal")
    running = bool(latest and latest.get("status") == "running")
    disabled = " disabled" if running else ""
    runner_options, runner_ui = _runner_options(root, str(st.get("stage") or ""))
    preferred = str(runner_ui.get("preferred") or "codex")
    default_model, default_effort = _runner_selection(runner_ui, preferred)
    model_options = _runner_model_options(runner_ui, preferred, default_model)
    effort_options = _runner_effort_options(runner_ui, preferred, default_model, default_effort)
    runner_config = _e(json.dumps(_runner_client_config(runner_ui), ensure_ascii=False))
    return (
        '<section class="panel phase-assistant" id="phase-assistant">'
        '<div class="panel-head phase-assistant-head"><div><span class="eyebrow">Assistente da fase</span>'
        '<h2>Diga o resultado que você quer</h2><p>O harness acrescenta contexto, paths permitidos e regras de segurança automaticamente. O agente só gera uma proposal para sua revisão.</p></div>'
        + _badge("Job em execução" if running else "Read-only", "info" if running else "ok") + '</div>'
        f'<form class="agent-form" method="post" action="/action/agent-run" data-agent-job-form data-runner-config="{runner_config}">'
        f'{_csrf(csrf_token)}<input type="hidden" name="slug" value="{_e(slug)}"><input type="hidden" name="stage" value="{_e(st.get("stage") or "")}">'
        '<label class="prompt-field"><span>Objetivo para o agente</span>'
        f'<textarea name="request" rows="5" required{disabled}>{_e(ux.get("prompt") or "")}</textarea>'
        '<small>Escreva a intenção editorial; não precisa explicar schemas, paths ou regras internas.</small></label>'
        '<div class="agent-controls">'
        '<label><span>CLI</span><select name="runner" data-runner-select' + disabled + '>' + runner_options + '</select><small>Codex, OpenCode ou Antigravity em todas as etapas de agente.</small></label>'
        f'<label><span>Modelo</span><select name="model" data-model-select{disabled}>{model_options}</select><small data-model-hint>Catálogo do CLI selecionado.</small></label>'
        f'<label><span>Reasoning</span><select name="reasoning_effort" data-effort-select{disabled}>{effort_options}</select><small data-effort-hint>Somente níveis compatíveis com o modelo.</small></label>'
        f'<button class="button button-primary" type="submit"{disabled}>{_icon("play")} {"Executando…" if running else "Gerar proposal"}</button></div>'
        '<div class="agent-cost-note" data-agent-cost-note><strong>Execução atual:</strong> <span data-agent-selection-summary></span></div>'
        '<div class="agent-submit-feedback" data-agent-feedback hidden></div></form>'
        f'<div class="studio-job-fragment" data-studio-job-endpoint="/ui/studio-job?slug={_q(slug)}&kind=agent-proposal">{render_studio_job(root, slug, "agent-proposal")}</div>'
        '</section>'
    )

def _next_action(root: str, st: dict, pending_props: int, slug: str, csrf_token: str) -> str:
    from . import operations as OPS, jobs as J
    state = str(st.get("state") or "")
    checks = list(st.get("checks", []) or [])
    failed = [c for c in checks if not c.get("ok")]
    current = str(st.get("stage") or "")
    stage_spec = next((s for s in _stage_data(root) if str(s.get("id")) == current), {})
    gate = str(stage_spec.get("gate") or "")
    gate_row = next((g for g in st.get("gates", []) or [] if str(g.get("gate")) == gate), {}) if gate else {}
    ux = OPS.experience(root, slug, st)
    J.mark_stale_failed(root, slug)
    running_job = next((j for j in J.list_jobs(root, slug, 20) if j.get("status") == "running"), None)

    if state == "paused":
        title, desc, tone = "Retomar a produção", "A produção está pausada. Retome antes de continuar o pipeline.", "warn"
        action = (
            '<form method="post" action="/action/resume">'
            f'{_csrf(csrf_token)}<input type="hidden" name="slug" value="{_e(slug)}">'
            '<button class="button button-primary" type="submit">Retomar produção</button></form>'
        )
    elif state == "abandoned":
        title, desc, tone, action = "Produção abandonada", "O histórico foi preservado e o pipeline não deve continuar.", "danger", ""
    elif running_job:
        title, desc, tone = "Execução em andamento", "O worker continua fora da request do navegador. Você pode acompanhar abaixo sem interromper o processo.", "info"
        action = '<a class="button button-primary" href="#phase-assistant">Acompanhar execução</a>' if ux.get("agent") else f'<a class="button button-primary" href="{_e(OPS.action_href("premiere.open" if "premiere" in str(running_job.get("type")) else "sources.open", slug))}">Abrir área</a>'
    elif pending_props:
        title, desc, tone = "Revise a proposal antes de continuar", f"Há {pending_props} proposal(s) esperando sua decisão. Nada será aplicado automaticamente.", "purple"
        action = f'<a class="button button-primary" href="/?page=reviews&slug={_q(slug)}">Revisar agora</a>'
    elif failed:
        title, desc, tone = ux.get("headline", "Continuar a fase"), ux.get("description", "Resolva as pendências atuais para seguir."), "focus"
        op_id, op_label = ux.get("primary", ("reviews.open", "Abrir revisão"))
        if op_id == "agent.propose":
            action = f'<a class="button button-primary" href="#phase-assistant">{_e(op_label)}</a>'
        else:
            action = f'<a class="button button-primary" href="{_e(OPS.action_href(op_id, slug))}">{_e(op_label)}</a>'
    elif gate and not gate_row.get("approved"):
        title, desc, tone = "Aprovação humana necessária", f"{gate} está pronto para sua decisão. O harness nunca aprova esse gate sozinho.", "purple"
        action = f'<a class="button button-primary" href="/?page=reviews&slug={_q(slug)}">Revisar gate</a>'
    else:
        title, desc, tone = "Fase concluída", "As verificações necessárias passaram. Avançar mantém todas as invariantes e fingerprints do harness.", "ok"
        action = (
            '<form method="post" action="/action/advance">'
            f'{_csrf(csrf_token)}<input type="hidden" name="slug" value="{_e(slug)}">'
            '<button class="button button-primary" type="submit">Avançar para a próxima fase</button></form>'
        )
    return (
        f'<section class="next-action next-{_e(tone)} cockpit-action"><div class="next-icon">{_icon("arrow")}</div><div class="next-copy">'
        '<span class="eyebrow">Faça agora</span>'
        f'<h2>{_e(title)}</h2><p>{_e(desc)}</p></div>'
        + (f'<div class="next-cta">{action}</div>' if action else "")
        + '</section>'
    )



def _editorial_cockpit(root: str, slug: str) -> str:
    from . import video_plans as VP
    try: sources = VP.source_catalog(root, slug)
    except Exception: sources = []
    try: proposals = VP.list_video_proposals(root, slug)
    except Exception: proposals = []
    try: videos = VP.list_videos(root, slug)
    except Exception: videos = []
    pending = [p for p in proposals if p.get("status") == "pending"]
    ready_sources = [x for x in sources if x.get("proposal_ready")]
    if not ready_sources:
        eyebrow, title = "Passo 1 · Fontes", "Transcreva os VODs que você quer entender"
        if sources:
            desc = f"{len(sources)} VOD(s) já foram identificados. Use áudio temporário para gerar evidência por segmento sem precisar manter todos os MP4s em disco."
        else:
            desc = "A produção é o pool compartilhado de fontes. Capture Twitch e gere as transcrições de descoberta antes de planejar vídeos."
        href, label = f"/?page=sources&slug={_q(slug)}", "Abrir Fontes"
    elif pending:
        eyebrow, title = "Passo 2 · Vídeos", "Continue as propostas que já estão em planejamento"
        desc = f"Há {len(pending)} proposta(s) pendente(s). Complete a Parte 2: responda as perguntas dinâmicas e consolide antes de aceitar cada vídeo."
        href, label = f"/?page=videos&slug={_q(slug)}", "Continuar em Vídeos"
    elif not videos:
        eyebrow, title = "Passo 2 · Vídeos", "Crie a primeira proposta de vídeo"
        desc = f"{len(ready_sources)} VOD(s) têm evidência textual pronta. Uma proposta representa um único vídeo; o download dos sources completos pode ficar para depois."
        href, label = f"/?page=videos&slug={_q(slug)}", "Planejar primeiro vídeo"
    else:
        eyebrow, title = "Pipeline editorial", "Planeje outro vídeo ou continue os já criados"
        desc = f"{len(videos)} vídeo(s) planejado(s) compartilham {len(ready_sources)} VOD(s) transcritos; word timestamps e mídia completa entram só onde forem necessários."
        href, label = f"/?page=videos&slug={_q(slug)}", "Abrir Vídeos"
    flow = (
        '<div class="video-flow cockpit-flow">'
        f'<article class="video-flow-step {"is-done" if ready_sources else "is-current"}"><span>1</span><div><strong>Fontes</strong><small>{len(ready_sources)} pronto(s) · {len(sources)} registrado(s)</small></div></article>'
        f'<article class="video-flow-step {"is-done" if videos else ("is-current" if ready_sources else "")}"><span>2</span><div><strong>Vídeos</strong><small>{len(pending)} proposta(s) · {len(videos)} aceito(s)</small></div></article>'
        f'<article class="video-flow-step {"is-current" if videos else ""}"><span>3</span><div><strong>Analisar e editar</strong><small>trabalho independente por vídeo</small></div></article>'
        '</div>'
    )
    return (
        '<section class="next-action next-action-info editorial-next-action"><div class="next-action-main"><span class="eyebrow">' + _e(eyebrow) + '</span><h2>' + _e(title) + '</h2><p>' + _e(desc) + '</p></div>'
        '<div class="next-action-side"><a class="button button-primary" href="' + href + '">' + _e(label) + ' ' + _icon("arrow") + '</a></div></section>'
        + '<div class="metric-grid metric-grid-3 cockpit-metrics">' + _metric("VODs prontos", str(len(ready_sources)), f"{len(sources)} registrado(s)", "blue", "sources") + _metric("Propostas", str(len(pending)), "uma por vídeo", "purple" if pending else "teal", "reviews") + _metric("Vídeos", str(len(videos)), "work items independentes", "green" if videos else "blue", "production") + '</div>'
        + flow
    )


def _production_page(root: str, prods: list[dict], slug: str, csrf_token: str) -> tuple[str, dict | None, list[dict]]:
    selected_status = None
    selected_history: list[dict] = []
    try:
        active = C.active_production(root)
    except Exception:
        active = None
    if not slug and active:
        slug = str(active.get("slug") or "")
    if slug:
        try:
            selected_status = C.workflow_status(root, slug)
            selected_history = _history_for(root, slug)
        except Exception:
            selected_status = None
    body = _page_header(
        "Produção",
        "Cockpit",
        "Uma ação principal por vez. O harness cuida dos detalhes; você decide o que produzir, revisar e aprovar.",
    )
    if selected_status:
        body += _editorial_cockpit(root, slug)
        body += (
            '<details class="technical-details"><summary><span>Estado técnico do harness</span><small>compatibilidade com o pipeline de 12 stages</small></summary>'
            '<div class="technical-details-body"><p class="muted">O fluxo principal do dashboard é Fontes → Vídeos → Edição. Os stages abaixo continuam como validação/compatibilidade enquanto o restante do harness é progressivamente escopado por vídeo.</p>'
            + _stage_details(root, selected_status, slug)
            + '<div class="details-links"><a class="text-link" href="/?page=reviews&slug=' + _q(slug) + '">Abrir revisões técnicas ' + _icon("arrow") + '</a></div></div></details>'
        )
    else:
        body += '<section class="empty-state hero-empty"><strong>Nenhuma produção selecionada</strong><span>Crie uma produção ou escolha uma existente abaixo.</span></section>'

    rows = []
    for p in prods:
        ps = str(p.get("slug") or "")
        state = str(p.get("state") or "")
        rows.append(
            '<tr>'
            f'<td><a class="production-cell" href="/?page=production&slug={_q(ps)}"><span class="production-avatar">{_e((ps[:2] or "··").upper())}</span><span><strong>{_e(p.get("title") or ps)}</strong><small>{_e(ps)}</small></span></a></td>'
            f'<td>{_e(_stage_label(root, str(p.get("stage") or "")))}</td><td>{_status_badge(state)}</td>'
            f'<td><a class="text-link" href="/?page=production&slug={_q(ps)}">Abrir {_icon("arrow")}</a></td></tr>'
        )
    prod_table = (
        '<div class="table-scroll"><table><thead><tr><th>Produção</th><th>Fase</th><th>Estado</th><th></th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>' if rows else '<p class="empty-state compact">Ainda não há produções.</p>'
    )
    body += (
        '<details class="workspace-management"><summary>Gerenciar produções</summary><div class="two-column lower-grid">'
        '<section class="panel"><div class="panel-head"><div><span class="eyebrow">Workspace</span><h2>Produções</h2></div></div>'
        f'{prod_table}</section>'
        '<section class="panel"><div class="panel-head"><div><span class="eyebrow">Nova</span><h2>Criar produção</h2></div></div>'
    )
    if active:
        aslug = str(active.get("slug") or "")
        body += (
            f'<div class="notice notice-warn">{_icon("warning")}<div><strong>Uma produção já está ativa</strong><span>{_e(active.get("title") or aslug)}. Pause ou abandone a atual antes de criar outra.</span></div></div>'
            '<div class="lifecycle-actions">'
            '<form method="post" action="/action/pause">'
            f'{_csrf(csrf_token)}<input type="hidden" name="slug" value="{_e(aslug)}"><button class="button button-ghost" type="submit">{_icon("pause")} Pausar</button></form>'
            '<form method="post" action="/action/abandon" data-confirm="Abandonar esta produção? O histórico será preservado, mas ela deixará de ser ativa.">'
            f'{_csrf(csrf_token)}<input type="hidden" name="slug" value="{_e(aslug)}"><input type="hidden" name="confirmo" value="on"><button class="button button-danger" type="submit">Abandonar</button></form>'
            '</div>'
        )
    else:
        body += (
            '<form class="form-stack" method="post" action="/action/new">'
            f'{_csrf(csrf_token)}'
            '<label><span>Título <b>*</b></span><input type="text" name="title" required placeholder="Ex.: melhores momentos da semana"></label>'
            '<label><span>Slug <small>opcional</small></span><input type="text" name="slug" placeholder="gerado automaticamente"></label>'
            '<label><span>Source URL <small>opcional</small></span><input type="url" name="source_url" placeholder="https://www.twitch.tv/canal/videos"></label>'
            '<button class="button button-primary" type="submit">Criar produção</button></form>'
        )
    body += (
        '<div class="panel-footer"><form method="post" action="/action/maintain">'
        f'{_csrf(csrf_token)}<input type="hidden" name="slug" value="{_e(slug)}"><button class="button button-ghost button-small" type="submit">Executar maintain</button></form>'
        '<span>Manutenção estrutural; não altera decisões editoriais.</span></div></section></div></details>'
    )
    return body, selected_status, selected_history


def _twitch_default_streamer(project: dict) -> str:
    source = str((project or {}).get("source_url", "") or "")
    m = re.search(r"(?:https?://)?(?:www\.)?twitch\.tv/([A-Za-z0-9_]{1,25})(?:/|$)", source, re.I)
    if m and m.group(1).lower() not in {"videos", "directory"}:
        return m.group(1)
    return ""


def _run_flags(run: dict) -> str:
    parts = ["--sequential" if run.get("sequential") else f"--threads {run.get('threads', 4)}"]
    if run.get("force"):
        parts.append("--force")
    if not run.get("resume", True):
        parts.append("--no-resume")
    return " ".join(parts)


def _twitch_runs_table(runs: list[dict]) -> str:
    if not runs:
        return '<p class="empty-state compact">Nenhuma captura Twitch registrada nesta produção.</p>'
    rows = []
    for run in runs:
        rows.append(
            '<tr>'
            f'<td><time>{_e(run.get("started_at", ""))}</time></td><td>{_status_badge(str(run.get("status") or "unknown"))}</td>'
            f'<td>{_e(run.get("streamer", ""))}</td><td><code>{_e(run.get("target", ""))}</code></td>'
            f'<td><code>{_e(_run_flags(run))}</code></td><td>{len(run.get("imported_assets") or [])}</td></tr>'
        )
    return '<div class="table-scroll"><table><thead><tr><th>Início</th><th>Status</th><th>Canal</th><th>Target</th><th>Flags</th><th>Assets</th></tr></thead>' + f'<tbody>{"".join(rows)}</tbody></table></div>'


def render_twitch_run(root: str, slug: str) -> str:
    """Render only the live Twitch run fragment. Used by progressive polling."""
    from . import twitch as TW

    runs = TW.list_runs(root, slug, 8)
    latest = runs[0] if runs else None
    if not latest:
        return (
            '<div class="live-run" data-twitch-live data-running="false">'
            '<div class="empty-state"><strong>Nenhuma execução ainda</strong><span>Configure a captura ao lado e inicie o primeiro ingest.</span></div></div>'
        )
    status = str(latest.get("status") or "unknown")
    running = status == "running"
    assets = list(latest.get("imported_assets") or [])
    log_tail = TW.tail_log(root, slug, latest.get("id"))
    asset_items = "".join(
        f'<li><code>{_e(a.get("asset_id", ""))}</code><span>{_e(a.get("kind", ""))}</span></li>' for a in assets
    ) or '<li class="empty-inline">Nenhum asset importado ainda.</li>'
    error = f'<div class="notice notice-danger">{_icon("warning")}<div><strong>Falha no scraper</strong><span>{_e(latest.get("error"))}</span></div></div>' if latest.get("error") else ""
    progress = '<span class="live-pulse" aria-hidden="true"></span>' if running else ""
    return (
        f'<div class="live-run" data-twitch-live data-running="{"true" if running else "false"}" data-run-id="{_e(latest.get("id", ""))}">'
        '<div class="live-head"><div>'
        f'<div class="live-status">{progress}{_status_badge(status)}<strong>{_e(latest.get("streamer", ""))}</strong></div>'
        f'<p>Target <code>{_e(latest.get("target", ""))}</code> · workers efetivos <strong>{_e(latest.get("effective_threads", ""))}</strong></p>'
        '</div><div class="live-run-id"><span>Run</span><code>' + _e(latest.get("id", "")) + '</code></div></div>'
        + error
        + '<div class="live-grid"><section><h3>Comando</h3><code class="command-line">' + _e(latest.get("command", "")) + '</code></section>'
        + f'<section><h3>Assets registrados <span class="count-pill">{len(assets)}</span></h3><ul class="asset-list">{asset_items}</ul></section></div>'
        + '<section class="log-panel"><div class="log-head"><h3>Log</h3>' + ('<span>Atualizando a cada 2 s</span>' if running else '<span>Execução finalizada</span>') + '</div>'
        + f'<pre class="log-output" tabindex="0">{_e(log_tail or "Sem log ainda.")}</pre></section></div>'
    )


def _twitch_page(root: str, slug: str, st: dict, csrf_token: str) -> str:
    from . import twitch as TW

    try:
        _pdir, project = C.load_project(root, slug)
    except Exception:
        project = {}
    health = TW.scraper_health(root)
    runs = TW.list_runs(root, slug, 8)
    latest = runs[0] if runs else None
    running = bool(latest and latest.get("status") == "running")
    can_run = bool(health.get("script_present") and health.get("bun_available"))
    default_streamer = _twitch_default_streamer(project)
    body = _page_header(
        "Twitch Ingest",
        "Captura operacional",
        "Colete VOD metadata e chat para a produção atual. A captura registra evidência, mas nunca concede direitos, aprova gate ou avança fase.",
        _badge("Scraper pronto" if can_run else "Setup pendente", "ok" if can_run else "danger") + _badge("Job em execução" if running else "Idle", "info" if running else "neutral"),
    )
    disabled = " disabled" if (running or not can_run) else ""
    opts = "".join(f'<option value="{n}"{" selected" if n == 4 else ""}>{n} worker{"s" if n != 1 else ""}</option>' for n in (1, 2, 4, 8))
    body += (
        '<div class="twitch-layout">'
        '<section class="panel setup-panel"><div class="panel-head"><div><span class="eyebrow">Run setup</span><h2>Nova captura</h2></div></div>'
        '<form class="form-stack" method="post" action="/action/twitch-scrape">'
        f'{_csrf(csrf_token)}<input type="hidden" name="slug" value="{_e(slug)}">'
        f'<label><span>Canal Twitch <b>*</b></span><input type="text" name=\'streamer\' value=\'{_e(default_streamer)}\' placeholder="ex.: alanzoka" required></label>'
        '<label><span>Target</span><input type="text" name=\'target\' value=\'3\' placeholder="3, VOD ID ou URL"></label>'
        f'<label><span>Workers</span><select name=\'threads\'>{opts}</select><small>8 workers equivale a <code>--threads 8</code>.</small></label>'
        '<fieldset class="option-group"><legend>Flags</legend>'
        '<label class="check-option"><input type="checkbox" name=\'sequential\' value=\'on\'><span><strong>Sequencial</strong><small><code>--sequential</code> força 1 worker.</small></span></label>'
        '<label class="check-option"><input type="checkbox" name=\'force\' value=\'on\'><span><strong>Forçar captura</strong><small><code>--force</code> ignora skip de VOD completo.</small></span></label>'
        '<label class="check-option"><input type="checkbox" name=\'no_resume\' value=\'on\'><span><strong>Desabilitar resume</strong><small><code>--no-resume</code> reinicia o trabalho aplicável.</small></span></label>'
        '</fieldset>'
        f'<button class="button button-primary button-wide" type="submit"{disabled}>{_icon("play")} {"Captura em execução" if running else ("Iniciar Twitch ingest" if can_run else "Bun necessário para executar")}</button>'
        '</form>'
        '<div class="setup-health">'
        f'<div><span>Script</span>{_badge("presente" if health.get("script_present") else "ausente", "ok" if health.get("script_present") else "danger")}</div>'
        f'<div><span>Bun</span><code>{_e(health.get("bun") or "não encontrado")}</code></div>'
        f'<div><span>Playwright</span>{_badge("instalado" if health.get("dependencies_present") else "instala no 1º run", "ok" if health.get("dependencies_present") else "warn")}</div>'
        '</div></section>'
        '<section class="panel live-panel"><div class="panel-head"><div><span class="eyebrow">Live run</span><h2>Execução atual</h2></div><span class="live-connection" data-live-connection>Monitor local</span></div>'
        f'<div id="twitch-run-fragment" data-twitch-endpoint="/ui/twitch-run?slug={_q(slug)}">{render_twitch_run(root, slug)}</div></section>'
        '</div>'
        '<section class="panel"><div class="panel-head"><div><span class="eyebrow">Histórico</span><h2>Capturas recentes</h2></div></div>'
        f'{_twitch_runs_table(runs)}</section>'
        '<section class="cli-strip"><div><span class="eyebrow">CLI equivalente</span><code>python -m cstudio --root . twitch-scrape '
        f'{_e(slug)} --streamer {_e(default_streamer or "CANAL")} --target 3 --threads 8</code></div><span>Saída isolada em <code>.studio/internal/ingest/twitch/</code>.</span></section>'
    )
    return body



def _youtube_state_badge(state: str) -> str:
    state = str(state or "unmatched")
    tone = {
        "verified": "ok", "likely": "info", "candidate": "neutral",
        "ambiguous": "warn", "rejected": "danger", "unmatched": "neutral",
    }.get(state, "neutral")
    return _badge(state.upper(), tone)


def _youtube_score_details(match: dict) -> str:
    evidence = match.get("candidate_evidence") or {}
    signals = evidence.get("signals") or {}
    rows = []
    for key in ("channel", "date", "duration", "title", "chapters"):
        item = signals.get(key) or {}
        rows.append(
            '<li><span>' + _e(key) + '</span><strong>' + _e(f"{float(item.get('score') or 0):.2f}") +
            '</strong><small>' + _e(item.get("detail", "")) + '</small></li>'
        )
    return '<ul class="signal-list">' + ''.join(rows) + '</ul>'


def _youtube_candidate_card(slug: str, match: dict, csrf_token: str) -> str:
    video = match.get("youtube") or {}
    verification_root = match.get("verification") or {}
    verification = (verification_root.get("audio") or {})
    transcript = (verification_root.get("transcript") or {})
    anchors = list(verification.get("anchors") or [])
    transcript_anchors = list(transcript.get("anchors") or [])
    assessment = verification.get("assessment") or {}
    transcript_assessment = transcript.get("assessment") or {}
    segments = list(match.get("timeline_segments") or [])
    download = match.get("download") or {}
    state = str(match.get("state") or "candidate")
    vod_id = str((match.get("twitch_vod_ids") or [""])[0])
    video_id = str(match.get("youtube_video_id") or "")
    score = float(match.get("candidate_score") or 0)
    anchor_text = ' · '.join(
        f"YT {float(a.get('youtube_time') or 0):.0f}s ↔ TW {float(a.get('twitch_time') or 0):.0f}s · {float(a.get('similarity') or 0):.2f}"
        for a in anchors[:5]
    ) or "Ainda não confirmado por áudio."
    transcript_text = ' · '.join(
        f"YT {float(a.get('youtube_time') or 0):.0f}s ↔ TW {float(a.get('twitch_time') or 0):.0f}s · {float(a.get('similarity') or 0):.2f}"
        for a in transcript_anchors[:5]
    ) or "Transcrição ainda não alinhada."
    max_height = ((video.get("formats_summary") or {}).get("max_height"))
    quality = f"{max_height}p" if max_height else "metadata pendente"
    actions = []
    if state != "rejected":
        actions.append(
            '<form method="post" action="/action/youtube-verify">' + _csrf(csrf_token) +
            f'<input type="hidden" name="slug" value="{_e(slug)}"><input type="hidden" name="vod_id" value="{_e(vod_id)}"><input type="hidden" name="video_id" value="{_e(video_id)}">'
            '<button class="button button-ghost button-small" type="submit">Verify</button></form>'
        )
    if state == "verified":
        actions.append(
            '<form method="post" action="/action/youtube-download">' + _csrf(csrf_token) +
            f'<input type="hidden" name="slug" value="{_e(slug)}"><input type="hidden" name="vod_id" value="{_e(vod_id)}"><input type="hidden" name="video_id" value="{_e(video_id)}">'
            '<button class="button button-primary button-small" type="submit">Download master</button></form>'
        )
    if state != "rejected":
        actions.append(
            '<form method="post" action="/action/youtube-reject" data-confirm="Rejeitar este candidato? O manifest será preservado.">' + _csrf(csrf_token) +
            f'<input type="hidden" name="slug" value="{_e(slug)}"><input type="hidden" name="vod_id" value="{_e(vod_id)}"><input type="hidden" name="video_id" value="{_e(video_id)}">'
            '<button class="button button-ghost button-small" type="submit">Reject</button></form>'
        )
    return (
        '<article class="resolver-candidate">'
        '<div class="resolver-candidate-head"><div>' + _youtube_state_badge(state) +
        f'<h3>{_e(video.get("title") or video_id)}</h3><p><code>{_e(video_id)}</code> · {_e(video.get("channel_name") or video.get("configured_channel_name") or "")}</p></div>'
        f'<div class="resolver-score"><span>candidate score</span><strong>{score:.2f}</strong></div></div>'
        '<div class="resolver-candidate-grid">'
        '<section><span class="eyebrow">Signals</span>' + _youtube_score_details(match) + '</section>'
        '<section><span class="eyebrow">Transcript alignment</span>'
        f'<p>{_e(transcript_text)}</p><div class="resolver-mini"><span>text anchors <strong>{len(transcript_anchors)}</strong></span><span>state <strong>{_e(transcript_assessment.get("state") or "pending")}</strong></span><span>consistency <strong>{_e(transcript_assessment.get("timeline_consistency") or "pending")}</strong></span></div></section>'
        '<section><span class="eyebrow">Audio confirmation</span>'
        f'<p>{_e(anchor_text)}</p><div class="resolver-mini"><span>audio anchors <strong>{len(anchors)}</strong></span><span>mapping <strong>{len(segments)}</strong></span><span>consistency <strong>{_e(assessment.get("timeline_consistency") or "pending")}</strong></span></div></section>'
        '<section><span class="eyebrow">Master</span>'
        f'<p>Qualidade: <strong>{_e(quality)}</strong><br>Status: <strong>{_e(download.get("status") or "not_downloaded")}</strong></p>'
        + (f'<code class="path-chip">{_e(download.get("path"))}</code>' if download.get("path") else '') + '</section></div>'
        '<div class="resolver-actions">' + ''.join(actions) + '</div></article>'
    )


def _youtube_duration_label(seconds) -> str:
    try:
        value = max(0, int(round(float(seconds or 0))))
    except (TypeError, ValueError):
        return "—"
    if not value:
        return "—"
    hours, rem = divmod(value, 3600)
    minutes = rem // 60
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{max(1, minutes)}m"


def _storage_bytes_label(value, *, approximate: bool = False) -> str:
    try:
        size = float(value)
    except (TypeError, ValueError):
        return "—"
    if size <= 0:
        return "—"
    units = ((1024.0 ** 4, "TB"), (1024.0 ** 3, "GB"), (1024.0 ** 2, "MB"), (1024.0, "KB"))
    amount, suffix = size, "B"
    for divisor, label in units:
        if size >= divisor:
            amount, suffix = size / divisor, label
            break
    decimals = 1 if amount >= 10 else 2
    prefix = "~" if approximate else ""
    return f"{prefix}{amount:.{decimals}f} {suffix}"


def _storage_estimate_label(estimate: dict | None) -> str:
    estimate = estimate or {}
    confidence = str(estimate.get("confidence") or "unknown")
    return _storage_bytes_label(estimate.get("bytes"), approximate=confidence not in {"exact"})


def _storage_quality_label(estimate: dict | None, fallback: str = "máx. qualidade") -> str:
    estimate = estimate or {}
    try:
        height = int(estimate.get("height") or 0)
    except (TypeError, ValueError):
        height = 0
    try:
        fps = float(estimate.get("fps") or 0)
    except (TypeError, ValueError):
        fps = 0
    if height:
        fps_label = f"{int(round(fps))}" if fps else ""
        return f"{height}p{fps_label}"
    return fallback


def _storage_total_copy(total: dict) -> tuple[str, str]:
    total = total or {}
    known = int(total.get("known") or 0)
    count = int(total.get("total") or 0)
    complete = bool(total.get("complete"))
    label = _storage_bytes_label(total.get("bytes"), approximate=True) if known else "—"
    if count <= 0:
        detail = "nenhuma source"
    elif complete:
        detail = f"{known}/{count} estimados"
    else:
        detail = f"{known}/{count} com tamanho conhecido"
    return label, detail


def _youtube_upload_label(video: dict) -> str:
    raw = str((video or {}).get("upload_date") or "")
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    raw = str((video or {}).get("timestamp") or "")
    return raw if raw else "data —"


def _youtube_assignment_badge(state: str) -> str:
    state = str(state or "pending")
    if state == "verified":
        return _badge("VERIFIED", "ok")
    if state in {"unmatched", "rejected"}:
        return _badge("NO MATCH", "neutral" if state == "unmatched" else "danger")
    return _badge("EM PROGRESSO", "warn")


def _youtube_vod_catalog(vods: list[dict], matches: list[dict]) -> dict[str, dict]:
    """Build VOD labels from live discovery when present, with persisted matches as fallback."""
    catalog: dict[str, dict] = {}
    for vod in vods:
        vod_id = str(vod.get("vod_id") or "")
        if vod_id:
            catalog[vod_id] = dict(vod)
    for match in matches:
        vod = match.get("twitch") or {}
        vod_id = str(vod.get("vod_id") or ((match.get("twitch_vod_ids") or [""])[0]))
        if vod_id and vod_id not in catalog:
            catalog[vod_id] = dict(vod) if isinstance(vod, dict) else {"vod_id": vod_id}
        elif vod_id and isinstance(vod, dict):
            current = catalog.setdefault(vod_id, {"vod_id": vod_id})
            for key, value in vod.items():
                if value not in (None, "", [], {}) and not current.get(key):
                    current[key] = value
    return catalog


def _youtube_match_index(matches: list[dict]) -> dict[tuple[str, str], dict]:
    rows: dict[tuple[str, str], dict] = {}
    for match in matches:
        video_id = str(match.get("youtube_video_id") or "")
        vod_id = str((match.get("twitch_vod_ids") or [""])[0])
        if video_id and vod_id:
            rows[(video_id, vod_id)] = match
    return rows


def _youtube_pair_summary(pair: dict) -> tuple[int, float | None, str, str]:
    audio = pair.get("audio") or ((pair.get("verification") or {}).get("audio") or {})
    transcript = pair.get("transcript") or ((pair.get("verification") or {}).get("transcript") or {})
    anchors = list(audio.get("anchors") or [])
    similarities = [float(a.get("similarity") or 0) for a in anchors if float(a.get("similarity") or 0) > 0]
    strongest = max(similarities) if similarities else None
    assessment = audio.get("assessment") or {}
    consistency = str(assessment.get("timeline_consistency") or "insufficient")
    transcript_state = str((transcript.get("assessment") or {}).get("state") or ("not-run" if not transcript else "insufficient"))
    return len(anchors), strongest, consistency, transcript_state


def _youtube_pair_table(slug: str, assignment: dict, vod_catalog: dict[str, dict], match_index: dict[tuple[str, str], dict], csrf_token: str) -> str:
    video_id = str(assignment.get("youtube_video_id") or "")
    primary_vod = str(assignment.get("primary_vod_id") or "")
    global_state = str(assignment.get("state") or "pending")
    pairs = []
    for vod_id, raw_pair in (assignment.get("pair_results") or {}).items():
        pair = dict(raw_pair or {})
        persisted = match_index.get((video_id, str(vod_id))) or {}
        if persisted:
            if not pair.get("candidate_evidence"):
                pair["candidate_evidence"] = persisted.get("candidate_evidence")
            if not pair.get("verification"):
                pair["verification"] = persisted.get("verification")
        pairs.append((str(vod_id), pair))
    pairs.sort(key=lambda item: (
        0 if item[0] == primary_vod else 1,
        0 if str(item[1].get("state") or "") == "verified" else 1,
        -float(item[1].get("candidate_score") or 0),
    ))
    rows = []
    for vod_id, pair in pairs:
        vod = vod_catalog.get(vod_id) or {"vod_id": vod_id}
        title = str(vod.get("title") or f"Twitch VOD {vod_id}")
        local_state = str(pair.get("state") or "candidate")
        anchor_count, strongest, consistency, transcript_state = _youtube_pair_summary(pair)
        score = float(pair.get("candidate_score") or 0)
        is_primary = vod_id == primary_vod
        actions = ""
        if global_state != "verified" and local_state != "rejected":
            actions = (
                '<div class="pair-actions">'
                '<form method="post" action="/action/youtube-verify">' + _csrf(csrf_token) +
                f'<input type="hidden" name="slug" value="{_e(slug)}"><input type="hidden" name="vod_id" value="{_e(vod_id)}"><input type="hidden" name="video_id" value="{_e(video_id)}">'
                '<button class="button button-ghost button-tiny" type="submit">Reverificar</button></form>'
                '<form method="post" action="/action/youtube-reject" data-confirm="Rejeitar este par? O manifest será preservado.">' + _csrf(csrf_token) +
                f'<input type="hidden" name="slug" value="{_e(slug)}"><input type="hidden" name="vod_id" value="{_e(vod_id)}"><input type="hidden" name="video_id" value="{_e(video_id)}">'
                '<button class="button button-ghost button-tiny" type="submit">Rejeitar par</button></form></div>'
            )
        peak_label = f"pico {strongest:.3f}" if strongest is not None else "sem pico forte"
        rows.append(
            f'<article class="pair-diagnostic-row {"pair-primary" if is_primary else ""}">'
            f'<div class="pair-vod-title"><span>Twitch VOD</span><strong>{_e(title)}</strong><small><code>{_e(vod_id)}</code>{" · referência global" if is_primary else ""}</small></div>'
            f'<div class="pair-local-state"><span>Sinal local</span>{_youtube_state_badge(local_state)}</div>'
            f'<div class="pair-evidence"><span>Evidência acústica</span><strong>{anchor_count} anchors · {_e(peak_label)}</strong><small>metadata prior {score:.2f} · timeline {_e(consistency)}</small></div>'
            f'<div class="pair-text-state"><span>Texto</span><strong>{_e(transcript_state)}</strong><small>fallback textual</small></div>'
            + actions + '</article>'
        )
    if not rows:
        return '<div class="empty-state compact"><strong>Sem pares persistidos</strong><span>Execute Resolve production para gerar a matriz global.</span></div>'
    return '<div class="pair-diagnostic-list">' + ''.join(rows) + '</div>'


def _youtube_assignment_card(slug: str, assignment: dict, vod_catalog: dict[str, dict], match_index: dict[tuple[str, str], dict], storage_youtube: dict[str, dict], csrf_token: str) -> str:
    video = assignment.get("youtube") or {}
    video_id = str(assignment.get("youtube_video_id") or video.get("video_id") or "")
    title = str(video.get("title") or video_id)
    url = str(video.get("url") or (f"https://www.youtube.com/watch?v={video_id}" if video_id else ""))
    state = str(assignment.get("state") or "pending")
    primary_vod = str(assignment.get("primary_vod_id") or "")
    evaluated = [str(v) for v in (assignment.get("evaluated_vod_ids") or []) if str(v)]
    pair = (assignment.get("pair_results") or {}).get(primary_vod) or {}
    persisted = match_index.get((video_id, primary_vod)) or {}
    if persisted and not pair.get("verification"):
        pair = dict(pair)
        pair["verification"] = persisted.get("verification")
    anchor_count, strongest, consistency, transcript_state = _youtube_pair_summary(pair)
    discovery = assignment.get("candidate_discovery") or {}
    discovery_reasons = [str(x) for x in (discovery.get("reasons") or [])]
    deep = assignment.get("deep_resolution") or {}
    deep_attempts = list((deep.get("attempted_vod_ids") or []))
    duration = _youtube_duration_label(video.get("duration"))
    upload = _youtube_upload_label(video)
    channel = str(video.get("channel_name") or assignment.get("streamer") or "")
    primary = vod_catalog.get(primary_vod) or {"vod_id": primary_vod}
    primary_title = str(primary.get("title") or (f"Twitch VOD {primary_vod}" if primary_vod else "—"))
    primary_url = str(primary.get("source_url") or (f"https://www.twitch.tv/videos/{primary_vod}" if primary_vod else ""))
    score = float(pair.get("candidate_score") or discovery.get("best_candidate_score") or 0)
    status_copy = ""
    status_tone = state
    if state == "verified":
        status_copy = f'Associado a <strong>{_e(primary_title)}</strong>.'
    elif state in {"unmatched", "rejected"}:
        status_copy = f'Nenhum dos <strong>{len(evaluated) or len(assignment.get("pair_results") or {})}</strong> VODs testados atingiu confirmação audiovisual.'
        status_tone = "unmatched"
    else:
        status_copy = f'Avaliação global em andamento: <strong>{len(evaluated)}</strong> VOD(s) concluído(s).'
        status_tone = "pending"
    reason_chips = ''.join(f'<span>{_e(reason.replace("-", " "))}</span>' for reason in discovery_reasons[:3])
    if not reason_chips:
        reason_chips = '<span>checkpoint anterior</span>'
    evidence_bits = [
        f'<div><span>VODs avaliados</span><strong>{len(evaluated) or len(assignment.get("pair_results") or {})}</strong></div>',
        f'<div><span>Audio anchors</span><strong>{anchor_count}</strong></div>',
        f'<div><span>Timeline</span><strong>{_e(consistency)}</strong></div>',
    ]
    if state == "verified":
        estimate = storage_youtube.get(video_id) or {}
        size_label = _storage_estimate_label(estimate)
        formats_summary = video.get("formats_summary") if isinstance(video.get("formats_summary"), dict) else {}
        fallback_height = formats_summary.get("max_height")
        fallback_fps = formats_summary.get("max_fps")
        fallback_quality = "4K/max"
        if fallback_height:
            try:
                fallback_quality = f"{int(fallback_height)}p{int(round(float(fallback_fps)))}" if fallback_fps else f"{int(fallback_height)}p"
            except (TypeError, ValueError):
                fallback_quality = "4K/max"
        quality_label = _storage_quality_label(estimate, fallback_quality)
        evidence_bits.append(f'<div class="assignment-storage"><span>Master { _e(quality_label) }</span><strong>{_e(size_label)}</strong></div>')
    if strongest is not None:
        evidence_bits.append(f'<div><span>Melhor pico</span><strong>{strongest:.3f}</strong></div>')
    if deep_attempts:
        evidence_bits.append(f'<div><span>Fallback textual</span><strong>{len(deep_attempts)} VOD(s)</strong></div>')
    elif transcript_state not in {"not-run", ""}:
        evidence_bits.append(f'<div><span>Texto</span><strong>{_e(transcript_state)}</strong></div>')
    action_html = ""
    if state == "verified" and primary_vod:
        download = persisted.get("download") or {}
        download_status = str(download.get("status") or "not_downloaded")
        if download_status in {"downloaded", "completed"} and download.get("path"):
            action_html += f'<span class="assignment-downloaded">{_icon("check")} Master baixado</span><code class="path-chip">{_e(download.get("path"))}</code>'
        else:
            action_html += (
                '<form method="post" action="/action/youtube-download">' + _csrf(csrf_token) +
                f'<input type="hidden" name="slug" value="{_e(slug)}"><input type="hidden" name="vod_id" value="{_e(primary_vod)}"><input type="hidden" name="video_id" value="{_e(video_id)}">'
                '<button class="button button-primary button-small" type="submit">Download master</button></form>'
            )
    search_blob = " ".join([title, video_id, channel, primary_title, primary_vod, state]).lower()
    pair_table = _youtube_pair_table(slug, assignment, vod_catalog, match_index, csrf_token)
    return (
        f'<article class="assignment-card assignment-{_e(status_tone)}" data-youtube-assignment data-state="{_e("verified" if state == "verified" else ("unmatched" if state in {"unmatched", "rejected"} else "pending"))}" data-search="{_e(search_blob)}">'
        '<div class="assignment-main">'
        '<div class="assignment-state-column">' + _youtube_assignment_badge(state) +
        f'<span class="assignment-sequence">#{_e(discovery.get("index_position") or "—")}</span></div>'
        '<div class="assignment-content"><div class="assignment-title-row"><div>'
        f'<h3><a href="{_e(url)}" target="_blank" rel="noreferrer">{_e(title)} {_icon("external")}</a></h3>'
        f'<p><code>{_e(video_id)}</code> · {_e(channel)} · {_e(upload)} · {_e(duration)}</p></div>'
        f'<div class="assignment-prior"><span>metadata prior</span><strong>{score:.2f}</strong></div></div>'
        f'<div class="assignment-decision"><span>{status_copy}</span>' +
        ((f'<a href="{_e(primary_url)}" target="_blank" rel="noreferrer"><code>{_e(primary_vod)}</code> {_icon("external")}</a>') if state == "verified" and primary_vod else
         (f'<span class="assignment-closest">referência mais próxima <code>{_e(primary_vod or "—")}</code></span>' if primary_vod else '')) +
        '</div><div class="assignment-evidence-strip">' + ''.join(evidence_bits) + '</div>'
        f'<div class="assignment-discovery"><span>admissão</span>{reason_chips}</div>'
        '</div><div class="assignment-actions">' + action_html + '</div></div>'
        '<details class="assignment-details"><summary><span>Ver evidência técnica e matriz de VODs</span><small>estado local dos pares não substitui a decisão global</small></summary>'
        '<div class="assignment-detail-body"><div class="assignment-detail-note">'
        f'<div><span>Assignment global</span><strong>{_e(state)}</strong></div><div><span>Matcher</span><strong>{_e(assignment.get("matcher_engine") or "—")}</strong></div>'
        f'<div><span>Policy</span><code>{_e(assignment.get("policy_version") or "—")}</code></div><div><span>Deep resolution</span><strong>{_e(deep.get("reason") or deep.get("status") or "não necessário")}</strong></div>'
        '</div><div class="assignment-tech-heading"><span class="eyebrow">Pair diagnostics</span><p>“candidate/likely” abaixo descreve somente um teste local contra aquele VOD. A decisão acima é a autoridade global.</p></div>'
        + pair_table + '</div></details></article>'
    )


def _youtube_vod_coverage(assignments: list[dict], vod_catalog: dict[str, dict], storage_twitch: dict[str, dict]) -> str:
    verified = [a for a in assignments if str(a.get("state") or "") == "verified"]
    by_vod: dict[str, list[dict]] = {}
    for assignment in verified:
        for vod_id in assignment.get("assigned_vod_ids") or []:
            by_vod.setdefault(str(vod_id), []).append(assignment)
    all_vods = sorted(vod_catalog, key=lambda vod_id: str((vod_catalog.get(vod_id) or {}).get("created_at") or vod_id))
    if not all_vods:
        all_vods = sorted(by_vod)
    if not all_vods:
        return ""
    cards = []
    for vod_id in all_vods:
        vod = vod_catalog.get(vod_id) or {"vod_id": vod_id}
        rows = by_vod.get(vod_id) or []
        source_estimate = storage_twitch.get(vod_id) or {}
        source_size = _storage_estimate_label(source_estimate)
        source_quality = _storage_quality_label(source_estimate, "source")
        chips = ''.join(
            f'<span class="vod-video-chip" title="{_e((a.get("youtube") or {}).get("title") or a.get("youtube_video_id"))}">{_e((a.get("youtube") or {}).get("title") or a.get("youtube_video_id"))}</span>'
            for a in sorted(rows, key=lambda a: str((a.get("youtube") or {}).get("upload_date") or ""))
        )
        cards.append(
            '<article class="vod-coverage-card"><div class="vod-coverage-head"><div>'
            f'<span class="eyebrow">Twitch VOD</span><h3>{_e(vod.get("title") or vod_id)}</h3><p><code>{_e(vod_id)}</code> · {_e(vod.get("game") or vod.get("streamer") or "")}</p>'
            f'<div class="vod-source-size"><span>source {_e(source_quality)}</span><strong>{_e(source_size)}</strong></div></div>'
            + _badge(f"{len(rows)} mirror" + ("s" if len(rows) != 1 else ""), "ok" if rows else "neutral") +
            '</div><div class="vod-video-chips">' + (chips or '<span class="vod-empty">Nenhum mirror verificado nesta janela.</span>') + '</div></article>'
        )
    return '<div class="vod-coverage-grid">' + ''.join(cards) + '</div>'


def render_youtube_job(root: str, slug: str) -> str:
    from . import youtube_resolver as YR
    latest = YR.latest_job(root, slug)
    if not latest:
        return '<div class="live-run" data-youtube-live data-running="false"><div class="empty-state"><strong>Nenhum job ainda</strong><span>Configure canais e execute index ou resolve.</span></div></div>'
    status = str(latest.get("status") or "unknown")
    running = status == "running"
    log_tail = YR.tail_job_log(root, slug, latest.get("id"), max_chars=None)
    error = f'<div class="notice notice-danger">{_icon("warning")}<div><strong>Falha no resolver</strong><span>{_e(latest.get("error"))}</span></div></div>' if latest.get("error") else ""
    result_summary = latest.get("result_summary") or {}
    summary_bits = []
    if isinstance(result_summary, dict):
        if str(latest.get("type") or "") == "sizes":
            for key, label in (("twitch_bytes", "Twitch"), ("youtube_bytes", "YouTube"), ("combined_bytes", "total")):
                if int(result_summary.get(key) or 0) > 0:
                    summary_bits.append(f'<span><strong>{_e(_storage_bytes_label(result_summary.get(key), approximate=True))}</strong> {_e(label)}</span>')
        for key in ("resolved", "verified", "downloaded", "indexed", "videos"):
            if key in result_summary and result_summary.get(key) not in (None, "", [], {}):
                summary_bits.append(f'<span><strong>{_e(result_summary.get(key))}</strong> {_e(key)}</span>')
    return (
        f'<div class="live-run youtube-live-run" data-youtube-live data-running="{"true" if running else "false"}" data-run-id="{_e(latest.get("id", ""))}">'
        '<div class="live-head"><div><div class="live-status">' + ('<span class="live-pulse"></span>' if running else '') + _status_badge(status) +
        f'<strong>{_e(latest.get("type") or "job")}</strong></div><p>streamer <code>{_e(latest.get("streamer") or "all")}</code> · VOD <code>{_e(latest.get("vod_id") or "all")}</code></p></div>'
        f'<div class="live-run-id"><span>Job</span><code>{_e(latest.get("id", ""))}</code></div></div>{error}'
        + (f'<div class="job-result-summary">{"".join(summary_bits)}</div>' if summary_bits else '') +
        f'<details class="job-log-details" {"open" if running else ""}><summary><span>{"Acompanhar log ao vivo" if running else "Ver log da execução"}</span><small>{"Atualizando a cada 2 s" if running else "Execução finalizada"}</small></summary>'
        '<section class="log-panel"><div class="log-head"><h3>Log</h3><div class="log-head-actions"><span>' + ('Atualizando a cada 2 s' if running else 'Execução finalizada') + '</span><button class="log-copy-button" type="button" data-copy-log>Copiar log</button></div></div>'
        f'<pre class="log-output" tabindex="0">{_e(log_tail or "Sem log ainda.")}</pre></section></details></div>'
    )


def _youtube_channels_panel(slug: str, channels: list[dict], csrf_token: str) -> str:
    rows = []
    for ch in channels:
        key = ch.get("channel_id") or ch.get("url") or ""
        enabled = bool(ch.get("enabled", True))
        rows.append(
            '<tr><td><strong>' + _e(ch.get("streamer")) + '</strong></td><td>' + _e(ch.get("name")) +
            f'</td><td><code>{_e(ch.get("channel_id") or "—")}</code></td><td><code>{_e(ch.get("transcription_language") or "auto")}</code></td><td class="muted-cell">{_e(ch.get("url"))}</td><td>{_badge("enabled" if enabled else "disabled", "ok" if enabled else "neutral")}</td><td>'
            '<form method="post" action="/action/youtube-channel-toggle">' + _csrf(csrf_token) +
            f'<input type="hidden" name="slug" value="{_e(slug)}"><input type="hidden" name="streamer" value="{_e(ch.get("streamer"))}"><input type="hidden" name="channel_key" value="{_e(key)}"><input type="hidden" name="enabled" value="{"0" if enabled else "1"}">'
            f'<button class="button button-ghost button-small" type="submit">{"Disable" if enabled else "Enable"}</button></form></td></tr>'
        )
    table = '<div class="table-scroll"><table><thead><tr><th>Twitch</th><th>YouTube</th><th>Channel ID</th><th>Whisper</th><th>URL</th><th>Status</th><th></th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>' if rows else '<p class="empty-state compact">Nenhum canal configurado.</p>'
    return (
        '<details class="panel resolver-settings"><summary><span class="resolver-settings-title"><span class="eyebrow">Configuration</span><strong>Mapeamento Twitch → YouTube</strong></span>' + _badge(f"{len(channels)} configurado(s)", "info") + '</summary><div class="resolver-settings-body">' + table +
        '<form class="form-row resolver-channel-form" method="post" action="/action/youtube-channel-set">' + _csrf(csrf_token) + f'<input type="hidden" name="slug" value="{_e(slug)}">'
        '<label><span>Twitch streamer</span><input name="streamer" placeholder="alanzoka" required></label><label><span>Nome do canal</span><input name="name" placeholder="alanzoka" required></label><label class="grow"><span>YouTube channel URL</span><input name="url" placeholder="https://youtube.com/@alanzoka" required></label><label><span>Channel ID</span><input name="channel_id" placeholder="opcional"></label><label><span>Whisper lang</span><input name="language" placeholder="pt / auto"></label><button class="button button-primary" type="submit">Adicionar</button></form></div></details>'
    )


def _youtube_legacy_vod_sections(slug: str, vods: list[dict], matches: list[dict], csrf_token: str, disabled: str) -> str:
    grouped = {str(v.get("vod_id")): v for v in vods}
    if not grouped:
        for match in matches:
            vod = match.get("twitch") or {}
            vod_id = str(vod.get("vod_id") or ((match.get("twitch_vod_ids") or [""])[0]))
            if vod_id:
                grouped.setdefault(vod_id, vod or {"vod_id": vod_id})
    match_by_vod: dict[str, list[dict]] = {}
    for match in matches:
        key = str((match.get("twitch_vod_ids") or [""])[0])
        match_by_vod.setdefault(key, []).append(match)
    cards = []
    for vod_id, vod in grouped.items():
        candidates = match_by_vod.get(vod_id, [])
        candidate_html = ''.join(_youtube_candidate_card(slug, m, csrf_token) for m in candidates) or '<p class="empty-state compact">Nenhum candidato. Execute Resolve.</p>'
        cards.append(
            '<section class="panel resolver-vod"><div class="panel-head"><div><span class="eyebrow">Twitch VOD</span>'
            f'<h2>{_e(vod.get("title") or vod_id)}</h2><p><code>{_e(vod_id)}</code> · {_e(vod.get("streamer"))} · {_e(vod.get("game") or "")}</p></div>'
            f'<form method="post" action="/action/youtube-resolve">{_csrf(csrf_token)}<input type="hidden" name="slug" value="{_e(slug)}"><input type="hidden" name="vod_id" value="{_e(vod_id)}"><input type="hidden" name="streamer" value="{_e(vod.get("streamer"))}"><button class="button button-ghost button-small" type="submit"{disabled}>Resolve VOD</button></form></div>'
            '<div class="resolver-candidates">' + candidate_html + '</div></section>'
        )
    return ''.join(cards) if cards else '<section class="panel"><div class="empty-state"><strong>Nenhum assignment global ainda</strong><span>Execute Resolve production para construir a matriz de VODs.</span></div></section>'


def _youtube_page(root: str, slug: str, st: dict, csrf_token: str) -> str:
    from . import youtube_resolver as YR
    state = YR.dashboard_state(root, slug)
    health = state["health"]
    channels = state["channels"]
    index = state["index"]
    vods = state["vods"]
    matches = state["matches"]
    assignments = state.get("assignments") or []
    assignment_verified = sum(1 for a in assignments if str(a.get("state") or "") == "verified")
    assignment_terminal = sum(1 for a in assignments if YR._assignment_resolution_terminal(a))
    assignment_pending = max(0, len(assignments) - assignment_terminal)
    assignment_no_match = max(0, assignment_terminal - assignment_verified)
    latest = state.get("latest_job") or {}
    running = latest.get("status") == "running"
    storage = YR.storage_status(root, slug)
    storage_youtube = storage.get("youtube") or {}
    storage_twitch = storage.get("twitch") or {}
    yt_storage_label, yt_storage_detail = _storage_total_copy(storage.get("youtube_total") or {})
    tw_storage_label, tw_storage_detail = _storage_total_copy(storage.get("twitch_total") or {})
    combined_storage_label, combined_storage_detail = _storage_total_copy(storage.get("combined_total") or {})
    disk_free_label = _storage_bytes_label(storage.get("disk_free_bytes"))
    transcription_backend = str(health.get("transcription_backend") or "")
    if transcription_backend == "faster-whisper":
        transcription_badge = _badge("faster-whisper pronto", "ok")
        transcription_model = os.path.basename(str(health.get("faster_whisper_model") or "large-v3-turbo"))
        transcription_runtime = f"faster-whisper · plain discovery · {health.get('faster_whisper_compute_type') or 'float16'}"
    elif health.get("whisper_available"):
        transcription_badge = _badge("OpenAI Whisper pronto", "ok")
        transcription_model = os.path.basename(str(health.get("whisper_model") or "turbo"))
        transcription_runtime = "OpenAI Whisper"
    else:
        transcription_badge = _badge("Whisper fallback", "warn")
        transcription_model = "—"
        transcription_runtime = "indisponível"
    body = _page_header(
        "YouTube Mirror Resolver", "Ingest audiovisual",
        "Assignment global primeiro: mirrors verificados ficam ligados ao VOD correto; candidatos locais aparecem apenas como evidência técnica.",
        _badge("yt-dlp pronto" if health.get("yt_dlp_available") else "yt-dlp ausente", "ok" if health.get("yt_dlp_available") else "danger") +
        _badge("FFmpeg pronto" if health.get("ffmpeg_available") else "FFmpeg ausente", "ok" if health.get("ffmpeg_available") else "danger") +
        _badge("NumPy exato" if health.get("numpy_acceleration") else "NumPy obrigatório", "ok" if health.get("numpy_acceleration") else "danger") +
        transcription_badge
    )
    disabled = ' disabled' if running else ''
    vod_catalog = _youtube_vod_catalog(vods, matches)
    match_index = _youtube_match_index(matches)
    visible_vods = len(vod_catalog)

    operation = (
        '<section class="panel resolver-command-center"><div class="resolver-command-main"><div><span class="eyebrow">Resolver state</span><h2>Assignment global</h2><p>A decisão global é a fonte de verdade. <strong>NO MATCH</strong> é terminal; estados candidate/likely de pares individuais não são pendências.</p></div>'
        '<div class="resolver-command-row"><form method="post" action="/action/youtube-index">' + _csrf(csrf_token) + f'<input type="hidden" name="slug" value="{_e(slug)}"><button class="button button-ghost" type="submit"{disabled}>Refresh index</button></form>'
        '<form method="post" action="/action/youtube-resolve">' + _csrf(csrf_token) + f'<input type="hidden" name="slug" value="{_e(slug)}"><button class="button button-primary" type="submit"{disabled}>Resolve production</button></form>'
        '<form method="post" action="/action/youtube-sizes">' + _csrf(csrf_token) + f'<input type="hidden" name="slug" value="{_e(slug)}"><input type="hidden" name="force" value="1"><button class="button button-ghost" type="submit"{disabled}>Atualizar tamanhos</button></form></div></div>'
        '<div class="resolver-kpis">'
        f'<div class="resolver-kpi"><span>Index</span><strong>{_e(index.get("videos") or 0)}</strong><small>{_e(index.get("last_indexed_at") or "nunca")}</small></div>'
        f'<div class="resolver-kpi"><span>VODs conhecidos</span><strong>{visible_vods}</strong><small>produção / manifests</small></div>'
        f'<div class="resolver-kpi resolver-kpi-ok"><span>Verified</span><strong>{assignment_verified}</strong><small>mirror confirmado</small></div>'
        f'<div class="resolver-kpi"><span>No match</span><strong>{assignment_no_match}</strong><small>decisão terminal</small></div>'
        f'<div class="resolver-kpi {"resolver-kpi-warn" if assignment_pending else ""}"><span>Em progresso</span><strong>{assignment_pending}</strong><small>{"resolver ativo" if assignment_pending else "fila limpa"}</small></div>'
        '</div><div class="resolver-runtime-line">'
        f'<span>matcher <strong>{_e(health.get("matcher_engine") or "—")}</strong></span><span>policy <code>{_e(health.get("verification_policy") or "—")}</code></span><span>fragments <strong>{_e(health.get("concurrent_fragments") or 1)}</strong></span><span>transcript <strong>{_e(transcription_runtime)}</strong></span><span>model <code>{_e(transcription_model)}</code></span><span>languages <code>{_e(", ".join(f"{k}={v}" for k, v in (health.get("whisper_languages") or {}).items()) or "auto")}</code></span>'
        '</div><form class="check-option resolver-auto" method="post" action="/action/youtube-auto-download">' + _csrf(csrf_token) + f'<input type="hidden" name="slug" value="{_e(slug)}"><input type="hidden" name="enabled" value="{"0" if state["config"].get("auto_download_verified") else "1"}"><button class="toggle-button" type="submit" aria-pressed="{"true" if state["config"].get("auto_download_verified") else "false"}"><span class="toggle-dot"></span></button><span><strong>Auto-download verified sources</strong><small>Somente assignments VERIFIED; NO MATCH e pares ambiguous nunca baixam automaticamente.</small></span></form></section>'
    )
    body += operation

    storage_updated = str(storage.get("updated_at") or "")
    storage_note = f"última leitura {_e(storage_updated)}" if storage_updated else "ainda não calculado"
    body += (
        '<section class="panel resolver-storage"><div class="panel-head"><div><span class="eyebrow">Storage planning</span><h2>Espaço das sources</h2>'
        '<p>Metadata only: o cálculo usa o mesmo seletor de qualidade do download real. Quando o servidor não informa filesize, o valor é estimado por bitrate × duração.</p></div>'
        f'<span class="storage-updated">{storage_note}</span></div>'
        '<div class="storage-kpis">'
        f'<article><span>Twitch sources</span><strong>{_e(tw_storage_label)}</strong><small>{_e(tw_storage_detail)}</small></article>'
        f'<article><span>YouTube VERIFIED</span><strong>{_e(yt_storage_label)}</strong><small>{_e(yt_storage_detail)} · máxima qualidade</small></article>'
        f'<article><span>Total se mantiver ambos</span><strong>{_e(combined_storage_label)}</strong><small>{_e(combined_storage_detail)}</small></article>'
        f'<article><span>Livre no disco</span><strong>{_e(disk_free_label)}</strong><small>volume da produção agora</small></article>'
        '</div><div class="storage-legend"><span><strong>sem ~</strong> filesize exato/local</span><span><strong>~</strong> approximate ou bitrate</span><span>O botão “Atualizar tamanhos” não baixa mídia.</span></div></section>'
    )

    live_panel = (
        '<section class="panel live-panel resolver-live-panel"><div class="panel-head"><div><span class="eyebrow">Background job</span><h2>Execução atual</h2></div><span class="live-connection" data-youtube-connection>Monitor local</span></div>'
        f'<div id="youtube-run-fragment" data-youtube-endpoint="/ui/youtube-run?slug={_q(slug)}">{render_youtube_job(root, slug)}</div></section>'
    )
    if running:
        body += live_panel

    if assignments:
        cards = sorted(assignments, key=lambda a: (
            0 if str(a.get("state") or "") == "verified" else (1 if str(a.get("state") or "") not in {"unmatched", "rejected"} else 2),
            str(a.get("primary_vod_id") or "zzzz"),
            str((a.get("youtube") or {}).get("upload_date") or ""),
            str(a.get("youtube_video_id") or ""),
        ))
        assignment_cards = ''.join(_youtube_assignment_card(slug, a, vod_catalog, match_index, storage_youtube, csrf_token) for a in cards)
        body += (
            f'<section class="panel resolver-results"><div class="panel-head resolver-results-head"><div><span class="eyebrow">Global results</span><h2>{len(assignments)} vídeos, uma decisão por source</h2><p>Use os filtros para auditar rapidamente o resultado. Abra um card apenas quando precisar inspecionar a matriz global de VODs.</p></div><span class="resolver-result-count" data-youtube-visible-count>{len(assignments)} visíveis</span></div>'
            '<div class="resolver-filterbar"><label class="resolver-search"><span class="sr-only">Buscar assignments</span><input type="search" placeholder="Buscar título, vídeo ou VOD…" data-youtube-assignment-search></label>'
            f'<div class="resolver-state-filters" role="group" aria-label="Filtrar assignments"><button type="button" class="resolver-filter is-active" data-youtube-state-filter="all">Todos <span>{len(assignments)}</span></button><button type="button" class="resolver-filter" data-youtube-state-filter="verified">Verified <span>{assignment_verified}</span></button><button type="button" class="resolver-filter" data-youtube-state-filter="unmatched">No match <span>{assignment_no_match}</span></button><button type="button" class="resolver-filter" data-youtube-state-filter="pending">Em progresso <span>{assignment_pending}</span></button></div></div>'
            '<div class="assignment-list" data-youtube-assignment-list>' + assignment_cards + '</div><div class="empty-state compact resolver-filter-empty" data-youtube-filter-empty hidden><strong>Nenhum assignment nesse filtro</strong><span>Tente outro estado ou termo de busca.</span></div></section>'
        )
        coverage = _youtube_vod_coverage(assignments, vod_catalog, storage_twitch)
        if coverage:
            body += '<section class="panel resolver-coverage"><div class="panel-head"><div><span class="eyebrow">VOD coverage</span><h2>Mirrors confirmados por live</h2><p>Esta visão contém somente assignments VERIFIED. VOD sem mirror permanece explicitamente vazio.</p></div>' + _badge(f"{assignment_verified} verified", "ok") + '</div>' + coverage + '</section>'
    else:
        body += '<section class="panel resolver-results"><div class="panel-head"><div><span class="eyebrow">Candidate discovery</span><h2>Pré-assignment</h2><p>Ainda não existe matriz global persistida; estes cards são sinais locais e não decisões finais.</p></div></div></section>'
        body += _youtube_legacy_vod_sections(slug, vods, matches, csrf_token, disabled)

    if not running:
        body += live_panel
    body += _youtube_channels_panel(slug, channels, csrf_token)
    body += '<section class="cli-strip"><div><span class="eyebrow">CLI equivalente</span><code>python -m cstudio --root . youtube-resolve ' + _e(slug) + ' --refresh-index</code><code>python -m cstudio --root . youtube-sizes ' + _e(slug) + ' --force</code></div><span>Audio-first preserva o verifier audiovisual; o cálculo de storage é metadata-only. Masters continuam restritos a assignments VERIFIED e rights permanecem fail-closed.</span></section>'
    return body

def _gates_page(root: str, slug: str, st: dict, csrf_token: str) -> str:
    gates = list(st.get("gates", []) or [])
    checks = list(st.get("checks", []) or [])
    pending = [g for g in gates if not g.get("approved")]
    failed = [c for c in checks if not c.get("ok")]
    actions = _badge(f"{len(pending)} gate(s) pendente(s)", "warn" if pending else "ok") + _badge(f"{len(failed)} check(s) falhando", "danger" if failed else "ok")
    body = _page_header("Aprovações e readiness", "Revisão humana", "Gates são decisões explícitas e vinculadas a fingerprints dos artefatos aprovados.", actions)
    body += (
        '<section class="panel gate-focus"><div class="panel-head"><div><span class="eyebrow">Fase atual</span>'
        f'<h2>{_e(_stage_label(root, str(st.get("stage") or "")))}</h2></div>{_badge("Bloqueado" if st.get("blocked") else "Pronto para avançar", "danger" if st.get("blocked") else "ok")}</div>'
        f'{_pipeline(root, str(st.get("stage") or ""))}</section>'
    )
    body += '<div class="two-column review-grid"><section class="panel"><div class="panel-head"><div><span class="eyebrow">Gates</span><h2>Fila de aprovação</h2></div></div>' + _gates_table(gates, slug, csrf_token, str(st.get("stage") or "")) + '</section>'
    body += '<section class="panel"><div class="panel-head"><div><span class="eyebrow">Checks</span><h2>Verificações da fase</h2></div></div>' + _checks_table(checks)
    body += (
        '<div class="advance-box"><div><strong>Avançar somente quando estiver pronto</strong><span>O backend continuará recusando avanço com check ou gate obrigatório pendente.</span></div>'
        '<form method="post" action="/action/advance">'
        f'{_csrf(csrf_token)}<input type="hidden" name="slug" value="{_e(slug)}"><button class="button button-primary" type="submit">Avançar fase</button></form></div></section></div>'
    )
    return body


def _proposals_page(slug: str, props: list[dict], csrf_token: str) -> str:
    pending = [p for p in props if str(p.get("status")) == "pending"]
    body = _page_header("Propostas", "Revisão humana", "Runners externos podem propor trabalho, mas nunca aplicam suas próprias decisões.", _badge(f"{len(pending)} pendente(s)", "warn" if pending else "ok"))
    body += '<section class="panel"><div class="panel-head"><div><span class="eyebrow">Inbox</span><h2>Fila para revisão</h2></div></div>' + _proposal_queue(root, props, slug, csrf_token) + '</section>'
    body += '<section class="panel"><div class="panel-head"><div><span class="eyebrow">Histórico</span><h2>Propostas processadas</h2></div></div>' + _proposal_history(props) + '</section>'
    return body


def _csv_preview(text: str, filterable: bool = False) -> str:
    try:
        rows = list(csv.DictReader(io.StringIO(text)))
    except Exception:
        rows = []
    if not rows:
        return '<p class="empty-state compact">CSV vazio ou ilegível.</p>'
    columns = list(rows[0].keys())
    head = "".join(f'<th>{_e(c)}</th>' for c in columns)
    body = "".join('<tr>' + "".join(f'<td>{_e(row.get(c, ""))}</td>' for c in columns) + '</tr>' for row in rows[:500])
    filterbar = (
        '<div class="filterbar"><label for="artifact-filter">Filtrar tabela</label><input id="artifact-filter" type="search" placeholder="Buscar em qualquer coluna" data-table-filter="artifact-table"><span data-table-count>'
        f'{len(rows)} linhas</span></div>' if filterable else ""
    )
    return filterbar + f'<div class="table-scroll artifact-table"><table id="artifact-table"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _json_preview(text: str) -> str:
    try:
        data = json.loads(text)
    except Exception:
        return f'<pre class="code-block">{_e(text[:12000])}</pre>'
    facts = []
    if isinstance(data, dict):
        for key, value in list(data.items())[:12]:
            if isinstance(value, (str, int, float, bool)) or value is None:
                display = str(value)
            elif isinstance(value, list):
                display = f"{len(value)} item(ns)"
            elif isinstance(value, dict):
                display = f"{len(value)} campo(s)"
            else:
                continue
            facts.append(f'<div><dt>{_e(key)}</dt><dd>{_e(display)}</dd></div>')
    summary = f'<dl class="json-facts">{"".join(facts)}</dl>' if facts else ""
    raw = _e(json.dumps(data, ensure_ascii=False, indent=2)[:20000])
    return summary + f'<details class="raw-details"><summary>Ver JSON bruto</summary><pre class="code-block">{raw}</pre></details>'


def _artifact_page(root: str, page: str, slug: str, st: dict) -> str:
    spec = ARTIFACT_PAGES[page]
    path = os.path.join(C.prod_path(root, slug), spec["path"])
    exists = os.path.isfile(path)
    text = open(path, encoding="utf-8", errors="replace").read() if exists else ""
    body = _page_header(spec["title"], "Artefato", spec["description"], _badge("Disponível" if exists else "Ausente", "ok" if exists else "warn"))
    body += (
        '<section class="artifact-hero"><div><span class="eyebrow">Artefato canônico</span>'
        f'<h2>{_e(spec["path"])}</h2><p>{"O arquivo existe e pode ser revisado abaixo." if exists else "Este artefato ainda não foi produzido para a produção atual."}</p></div>'
        f'<div class="artifact-state artifact-{_e(spec["accent"])}">{_icon(page)}<span>{"ready" if exists else "missing"}</span></div></section>'
    )
    preview = (
        _csv_preview(text, filterable=(page == "cutlist")) if exists and spec["kind"] == "csv" else
        _json_preview(text) if exists and spec["kind"] == "json" else
        '<div class="empty-state"><strong>Sem preview disponível</strong><span>Avance o pipeline ou produza o artefato correspondente para preencher esta tela.</span></div>'
    )
    body += '<div class="artifact-layout"><section class="panel artifact-preview"><div class="panel-head"><div><span class="eyebrow">Preview</span><h2>Conteúdo</h2></div></div>' + preview + '</section>'
    body += '<aside class="artifact-side"><section class="panel"><div class="panel-head"><div><span class="eyebrow">Readiness</span><h2>Checks da fase</h2></div></div>' + _checks_table(st.get("checks", [])) + '</section>'
    body += '<section class="panel"><div class="panel-head"><div><span class="eyebrow">Pipeline</span><h2>Posição atual</h2></div></div>' + _pipeline(root, str(st.get("stage") or "")) + '</section></aside></div>'
    return body



def _bytes_short(value: Any) -> str:
    try:
        size = float(value or 0)
    except (TypeError, ValueError):
        size = 0.0
    if size <= 0:
        return "—"
    units = ["B", "KB", "MB", "GB", "TB"]
    idx = 0
    while size >= 1024 and idx < len(units) - 1:
        size /= 1024.0; idx += 1
    return f"{size:.1f} {units[idx]}" if idx else f"{int(size)} B"


def _source_transcript_badge(status: dict) -> str:
    state = str((status or {}).get("status") or "missing")
    if state == "completed":
        return _badge("transcrito", "ok")
    if state == "running":
        pct = status.get("percent")
        return _badge(f"transcrevendo {pct}%" if pct is not None else "transcrevendo", "info")
    if state == "stale":
        return _badge("transcrição desatualizada", "warn")
    if state == "failed":
        return _badge("transcrição falhou", "danger")
    return _badge("sem transcrição", "neutral")


def _source_media_cards(root: str, slug: str, csrf_token: str, running: bool = False) -> str:
    from . import video_plans as VP
    from . import source_media as SM
    catalog = VP.source_catalog(root, slug)
    alignments = SM.list_alignments(root, slug)
    by_vod: dict[str, list[dict]] = {}
    for row in alignments:
        by_vod.setdefault(str(row.get("twitch_vod_id") or ""), []).append(row)
    if not catalog:
        return '<div class="empty-state"><strong>Nenhum VOD descoberto</strong><span>Capture os VODs da Twitch primeiro. Depois você decide, VOD por VOD, se quer apenas evidência textual ou a fonte completa.</span></div>'
    cards = []
    disabled = " disabled" if running else ""
    for source in catalog:
        vod_id = str(source.get("vod_id") or "")
        canonical_asset = f"twitch-video-{vod_id}"
        twitch_media = source.get("twitch_media") if isinstance(source.get("twitch_media"), dict) else None
        transcript = SM.transcript_status(root, slug, canonical_asset)
        audio = SM.twitch_audio_status(root, slug, vod_id)
        tr_state = str(transcript.get("status") or "missing")
        audio_present = bool(audio.get("file_present"))

        source_state = (
            '<div class="source-media-state"><span class="source-kind">Twitch source</span>'
            + (_badge("source baixado", "ok") if twitch_media else _badge("source não baixado", "neutral"))
            + _source_transcript_badge(transcript)
            + (f'<small>{_e(_bytes_short((twitch_media or {}).get("bytes")))} · arquivo durável para edição</small>' if twitch_media else '<small>A transcrição pode existir sem manter o MP4 completo em disco.</small>')
            + '</div>'
        )
        source_actions = []
        if not twitch_media:
            source_actions.append(
                '<form method="post" action="/action/source-download-twitch">' + _csrf(csrf_token)
                + f'<input type="hidden" name="slug" value="{_e(slug)}"><input type="hidden" name="vod_id" value="{_e(vod_id)}">'
                + f'<button class="button button-secondary button-small" type="submit"{disabled}>Baixar source completo</button></form>'
            )
        if tr_state != "completed":
            if twitch_media:
                source_actions.append(
                    '<form method="post" action="/action/source-transcribe">' + _csrf(csrf_token)
                    + f'<input type="hidden" name="slug" value="{_e(slug)}"><input type="hidden" name="asset_id" value="{_e(canonical_asset)}">'
                    + f'<button class="button button-primary button-small" type="submit"{disabled}>Transcrever source local</button></form>'
                )
            source_actions.append(
                '<form method="post" action="/action/source-audio-transcribe">' + _csrf(csrf_token)
                + f'<input type="hidden" name="slug" value="{_e(slug)}"><input type="hidden" name="vod_id" value="{_e(vod_id)}">'
                + f'<button class="button button-primary button-small" type="submit"{disabled}>Áudio → transcrever</button></form>'
            )
            if not audio_present:
                source_actions.append(
                    '<form method="post" action="/action/source-download-audio">' + _csrf(csrf_token)
                    + f'<input type="hidden" name="slug" value="{_e(slug)}"><input type="hidden" name="vod_id" value="{_e(vod_id)}">'
                    + f'<button class="button button-ghost button-small" type="submit"{disabled}>Baixar só áudio</button></form>'
                )
        if audio_present:
            source_state += (
                '<div class="source-transcript-meta"><strong>áudio temporário</strong><span>'
                + _e(_bytes_short(audio.get("bytes")))
                + ' · será apagado automaticamente depois de uma transcrição concluída</span></div>'
            )
        if tr_state == "completed":
            source_state += (
                '<div class="source-transcript-meta"><strong>' + _e(transcript.get("segment_count") or 0)
                + '</strong><span>segmentos · timestamps por segmento · '
                + _e(transcript.get("model") or "Large-v3-Turbo") + '</span></div>'
            )

        master_rows = []
        for media in [m for m in (source.get("media_sources") or []) if m.get("platform") == "youtube" and m.get("path")]:
            tr = media.get("transcript") or {}
            action = _source_transcript_badge(tr)
            if str(tr.get("status") or "") != "completed":
                action += (
                    '<form method="post" action="/action/source-transcribe">' + _csrf(csrf_token)
                    + f'<input type="hidden" name="slug" value="{_e(slug)}"><input type="hidden" name="asset_id" value="{_e(media.get("asset_id"))}">'
                    + f'<button class="button button-secondary button-small" type="submit"{disabled}>Transcrever master</button></form>'
                )
            else:
                action += '<small>timestamps por segmento</small>'
            master_rows.append(
                '<div class="master-source-row"><div><span class="source-kind">YouTube master</span><strong>' + _e(media.get("title") or media.get("youtube_video_id") or media.get("asset_id"))
                + '</strong><small>' + _e(_bytes_short(media.get("bytes"))) + '</small></div><div class="master-source-actions">' + action + '</div></div>'
            )
        if not master_rows:
            mirror_count = len(source.get("verified_mirrors") or [])
            if mirror_count:
                master_rows.append(f'<div class="master-source-row is-muted"><div><span class="source-kind">YouTube</span><strong>{_e(mirror_count)} mirror(s) verificado(s)</strong><small>Baixe o master somente quando fizer sentido para a edição/qualidade final.</small></div><a class="button button-ghost button-small" href="/?page=youtube&slug={_q(slug)}#youtube-assignments">Abrir mirrors</a></div>')
            else:
                master_rows.append('<div class="master-source-row is-muted"><div><span class="source-kind">YouTube</span><strong>Nenhum master local</strong><small>Isso não impede descoberta nem proposal se o VOD Twitch já estiver transcrito.</small></div></div>')

        align_html = ""
        rows = by_vod.get(vod_id) or []
        if rows:
            bits = []
            for row in rows[:6]:
                assessment = (row.get("alignment") or {}).get("assessment") or {}
                offset = row.get("estimated_twitch_minus_youtube_seconds")
                bits.append(
                    '<div class="alignment-hint"><span>' + _e(row.get("youtube_video_id") or row.get("youtube_asset_id")) + '</span>'
                    + f'<strong>{_e(assessment.get("state") or "unknown")}</strong><small>offset aprox. {_e(f"{float(offset):+.1f}s" if offset is not None else "—")}</small></div>'
                )
            align_html = '<details class="source-alignment"><summary>Mapa textual Twitch ↔ YouTube</summary><div>' + ''.join(bits) + '<p>É aproximação editorial. A sincronização final continua pelo waveform/readback no Premiere.</p></div></details>'

        proposal_state = _badge("evidência pronta", "ok") if source.get("proposal_ready") else _badge("transcrição pendente", "warn")
        cards.append(
            f'<article class="source-media-card" id="source-{_e(vod_id)}"><div class="source-media-card-head"><label class="source-select"><input type="checkbox" name="vod_ids" value="{_e(vod_id)}" form="source-batch-form" checked><span>Selecionar</span></label><div class="source-media-title"><span class="eyebrow">Twitch VOD <code>{_e(vod_id)}</code></span><h3>{_e(source.get("title") or vod_id)}</h3><p>{_e(source.get("created_at") or "")} · {_e(_format_hms(source.get("duration_seconds") or 0))}</p></div>{proposal_state}</div>'
            '<div class="source-media-lanes"><section><h4>Descoberta / source</h4>' + source_state + '<div class="master-source-actions">' + ''.join(source_actions) + '</div></section><section><h4>Masters de edição</h4>' + ''.join(master_rows) + '</section></div>'
            + align_html + '</article>'
        )
    return '<div class="source-media-grid">' + ''.join(cards) + '</div>'

def _sources_page(root: str, slug: str, st: dict, csrf_token: str) -> str:
    from . import twitch as TW
    from . import youtube_resolver as YR
    from . import video_plans as VP
    from . import source_media as SM
    from . import jobs as J
    try:
        twitch = TW.status_summary(root, slug)
    except Exception:
        twitch = {"health": {}, "latest": {}, "runs": []}
    try:
        youtube = YR.dashboard_state(root, slug)
    except Exception:
        youtube = {"health": {}, "vods": [], "assignments": [], "index": {}, "latest_job": {}}
    try:
        catalog = VP.source_catalog(root, slug)
    except Exception:
        catalog = []
    vods = list(youtube.get("vods") or [])
    assignments = list(youtube.get("assignments") or [])
    verified = [a for a in assignments if str(a.get("state") or "") == "verified"]
    downloaded_twitch = [x for x in catalog if x.get("twitch_media")]
    transcribed = [x for x in catalog if x.get("proposal_ready")]
    local_masters = sum(len([m for m in (x.get("media_sources") or []) if m.get("platform") == "youtube"]) for x in catalog)
    latest_twitch = twitch.get("latest") or {}
    latest_youtube = youtube.get("latest_job") or {}
    J.mark_stale_failed(root, slug)
    source_jobs = [j for j in J.list_jobs(root, slug, 50) if j.get("type") in {
        "source-download-twitch", "source-batch-download-twitch", "source-download-audio",
        "source-audio-transcribe", "source-batch-audio-transcribe", "source-transcribe", "source-prepare-vods"
    }]
    running = bool(source_jobs and source_jobs[0].get("status") == "running")
    body = _page_header(
        "Fontes",
        "Ingest audiovisual + transcrição",
        "Escolha por VOD: só áudio temporário para entender/transcrever, source completo para edição, ou ambos. Transcrição e download de mídia são decisões independentes.",
        _badge(f"{len(catalog) or len(vods)} VOD(s)", "info") + _badge(f"{len(transcribed)} pronto(s) para proposal", "ok" if transcribed else "warn"),
    )
    body += (
        '<section class="source-flow source-flow-four">'
        '<article class="source-step"><span class="source-number">1</span><div><span class="eyebrow">Descobrir</span><h2>Capturar VODs e chat</h2>'
        f'<p>{len(vods)} live(s) conhecidas. Última captura: {_e(latest_twitch.get("status") or "nenhuma")}.</p>'
        f'<a class="button button-primary" href="/?page=twitch&slug={_q(slug)}">Gerenciar captura</a></div><div class="source-stat"><strong>{len(vods)}</strong><span>VODs</span></div></article>'
        '<article class="source-step"><span class="source-number">2</span><div><span class="eyebrow">Entender</span><h2>Áudio → transcrição</h2>'
        f'<p>{len(transcribed)} VOD(s) já têm evidência textual. O áudio é temporário e apagado após sucesso; a transcrição completa usa timestamps por segmento.</p><a class="button button-primary" href="#source-library">Escolher VODs</a></div><div class="source-stat"><strong>{len(transcribed)}</strong><span>transcritos</span></div></article>'
        '<article class="source-step"><span class="source-number">3</span><div><span class="eyebrow">Materializar</span><h2>Baixar sources quando precisar</h2>'
        f'<p>{len(downloaded_twitch)} original(is) Twitch local(is). Você pode baixar antes, depois ou nunca — a proposal não depende do MP4 se já houver transcrição.</p><a class="button button-ghost" href="#source-library">Gerenciar sources</a></div><div class="source-stat"><strong>{len(downloaded_twitch)}</strong><span>Twitch</span></div></article>'
        '<article class="source-step"><span class="source-number">4</span><div><span class="eyebrow">Qualidade</span><h2>Resolver/baixar masters</h2>'
        f'<p>{len(verified)} mirror(s) verificado(s), {local_masters} master(s) local(is). Baixe a melhor fonte somente para os trechos/vídeos que realmente forem editar.</p><a class="button button-ghost" href="/?page=youtube&slug={_q(slug)}">Gerenciar mirrors</a></div><div class="source-stat"><strong>{local_masters}</strong><span>masters</span></div></article>'
        '</section>'
    )
    yt_health = youtube.get("health") or {}
    tw_health = twitch.get("health") or {}
    editorial_whisper = SM.editorial_runtime_status(root)
    readiness = [
        ("Twitch scraper", bool(tw_health.get("script_present")) and bool(tw_health.get("dependencies_present")), "descoberta + chat"),
        ("yt-dlp", bool(yt_health.get("yt_dlp_available")), "Twitch VOD + YouTube master"),
        ("FFmpeg", bool(yt_health.get("ffmpeg_available")), "áudio/chunks/sync"),
        ("Whisper Large Turbo", bool(editorial_whisper.get("available")), f"{editorial_whisper.get('backend') or 'local'} · segmento por padrão"),
    ]
    cards = []
    for label, ok, detail in readiness:
        cards.append(f'<div class="readiness-chip"><span class="readiness-mark {"ok" if ok else "warn"}"></span><div><strong>{_e(label)}</strong><small>{_e(detail)}</small></div><span>{_e("OK" if ok else "verificar")}</span></div>')
    body += '<section class="panel"><div class="panel-head"><div><span class="eyebrow">Saúde local</span><h2>Dependências essenciais</h2><p>A descoberta editorial reutiliza o backend Whisper otimizado do resolver. Word timestamps ficam reservados aos candidates selecionados.</p></div></div><div class="readiness-strip">' + ''.join(cards) + '</div></section>'
    batch_bar = (
        '<form id="source-batch-form" class="source-batch-bar" method="post" action="/action/source-batch-audio-transcribe">'
        + _csrf(csrf_token) + f'<input type="hidden" name="slug" value="{_e(slug)}">'
        + '<div><strong>Ações em lote</strong><span>A transcrição de descoberta baixa só áudio, persiste segmentos e apaga o áudio. Baixar source é uma ação separada.</span></div>'
        + '<div class="master-source-actions">'
        + f'<button class="button button-primary" type="submit"{" disabled" if running else ""}>Áudio → transcrever selecionados</button>'
        + f'<button class="button button-secondary" type="submit" formaction="/action/source-batch-download-twitch"{" disabled" if running else ""}>Baixar sources selecionados</button>'
        + '</div></form>'
    )
    body += '<section class="panel" id="source-library"><div class="panel-head"><div><span class="eyebrow">Biblioteca compartilhada</span><h2>VODs, masters e transcrições</h2><p>Transcrição de descoberta e mídia durável são independentes. Todas as propostas reutilizam a evidência já persistida.</p></div>' + (_badge("job em execução", "info") if running else _badge("local", "ok")) + '</div>' + batch_bar + _source_media_cards(root, slug, csrf_token, running=running) + '</section>'
    body += '<section class="panel"><div class="panel-head"><div><span class="eyebrow">Execução</span><h2>Download / transcrição atual</h2><p>Jobs longos continuam fora da request HTTP. Em áudio → transcrição, o arquivo temporário só é apagado depois do transcript persistido com sucesso.</p></div><span data-studio-job-connection>Monitor local</span></div><div class="studio-job-fragment" data-studio-job-endpoint="/ui/studio-job?slug=' + _q(slug) + '&kind=sources">' + render_studio_job(root, slug, "sources") + '</div></section>'
    if transcribed:
        body += '<section class="next-action next-action-ok"><div class="next-action-main"><span class="eyebrow">Evidência pronta</span><h2>Agora planeje os vídeos</h2><p>' + _e(f"{len(transcribed)} VOD(s) têm transcrição por segmento pronta para descoberta. Você pode decidir quais sources completos baixar somente depois que a proposal apontar o que realmente interessa.") + '</p></div><div class="next-action-side"><a class="button button-primary" href="/?page=videos&slug=' + _q(slug) + '">Abrir Vídeos ' + _icon("arrow") + '</a></div></section>'
    return body


def _video_runner_controls(root: str, selected_runner: str = "codex", selected_model: str = "", selected_effort: str = "", suffix: str = "video") -> str:
    from . import runners as R
    selected_runner = selected_runner if selected_runner in R.CLI_RUNNERS else "codex"
    options_html, ui = _runner_options(root, "analysis", selected_runner)
    selected_model, selected_effort = _runner_selection(ui, selected_runner, selected_model, selected_effort)
    model_opts = _runner_model_options(ui, selected_runner, selected_model)
    effort_opts = _runner_effort_options(ui, selected_runner, selected_model, selected_effort)
    config = _e(json.dumps(_runner_client_config(ui), ensure_ascii=False))
    return (
        f'<div class="agent-controls video-runner-controls" data-runner-config-holder="{config}">'
        f'<label><span>CLI</span><select name="runner" data-runner-select>{options_html}</select><small>As três opções ficam disponíveis em toda execução.</small></label>'
        f'<label><span>Modelo</span><select name="model" data-model-select>{model_opts}</select><small data-model-hint>Catálogo do CLI selecionado.</small></label>'
        f'<label><span>Reasoning</span><select name="reasoning_effort" data-effort-select>{effort_opts}</select><small data-effort-hint>Somente níveis válidos para este modelo.</small></label>'
        '<div class="agent-cost-note compact"><strong>Execução:</strong> <span data-agent-selection-summary></span></div>'
        '</div>'
    )

def _safe_dom_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", str(value or "x"))


def _format_hms(seconds: int) -> str:
    try: seconds = int(seconds or 0)
    except (TypeError, ValueError): seconds = 0
    h, rem = divmod(max(0, seconds), 3600); m, _s = divmod(rem, 60)
    return f"{h}h {m:02d}m" if h else f"{m} min"


def _candidate_moments_html(rows: list[dict]) -> str:
    if not rows:
        return '<section class="candidate-moments"><div class="panel-head compact-head"><div><span class="eyebrow">Momentos candidatos</span><h4>Nenhum timestamp forte ainda</h4><p>O agente não encontrou evidência textual suficiente para sugerir cortes nesta revisão.</p></div></div></section>'
    cards = []
    for row in rows[:40]:
        start = float(row.get("start_seconds") or 0); end = float(row.get("end_seconds") or 0)
        cards.append(
            '<article class="candidate-moment"><div><span class="eyebrow">' + _e(row.get("source_asset_id") or "fonte") + '</span><h5>' + _e(row.get("label") or "Momento candidato") + '</h5><p>' + _e(row.get("rationale") or "") + '</p><blockquote>' + _e(row.get("transcript_evidence") or "") + '</blockquote></div>'
            + f'<code>{_e(_hms_time(start))} → {_e(_hms_time(end))}</code></article>'
        )
    return '<section class="candidate-moments"><div class="panel-head compact-head"><div><span class="eyebrow">Momentos candidatos</span><h4>Pistas encontradas nas transcrições</h4><p>São hipóteses para análise/cutlist, não cortes finais. O Premiere fará o sync fino de áudio depois.</p></div>' + _badge(str(len(rows)), "info") + '</div><div class="candidate-moment-grid">' + ''.join(cards) + '</div></section>'


def _hms_time(seconds: float) -> str:
    value = max(0, int(seconds or 0)); h, rem = divmod(value, 3600); m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _video_proposal_card(root: str, slug: str, rec: dict, csrf_token: str) -> str:
    from . import video_plans as VP, jobs as J
    pid = str(rec.get("id") or "")
    video = rec.get("video") if isinstance(rec.get("video"), dict) else {}
    questions = list(rec.get("questions") or [])
    open_questions = VP.unanswered_questions(rec)
    phase = str(rec.get("planning_phase") or ("part1" if questions else "part2_final"))
    phase_labels = {
        "part1": ("Parte 1 · proposta inicial", "info"),
        "part2_questions": ("Parte 2 · perguntas", "warn"),
        "part2_answers_ready": ("Parte 2 · respostas prontas", "info"),
        "part2_final": ("Parte 2 · consolidada", "ok"),
        "final": ("Parte 2 · consolidada", "ok"),
    }
    phase_label, phase_tone = phase_labels.get(phase, (phase or "planejamento", "neutral"))
    is_final = phase in {"part2_final", "final"}
    source_rows = list(rec.get("source_snapshot") or [])
    source_html = "".join(
        f'<li><strong>{_e(x.get("title") or x.get("vod_id") or x.get("asset_id"))}</strong><span>{_e(x.get("created_at") or "")} · {_e(_format_hms(x.get("duration_seconds") or 0))}</span></li>'
        for x in source_rows
    ) or '<li><span>Nenhuma fonte registrada.</span></li>'
    question_html = ""
    for q in questions:
        qid = str(q.get("id") or "")
        answer = str(q.get("answer") or "")
        question_html += (
            '<label class="proposal-question"><span>' + _e(q.get("text") or "") + '</span>'
            f'<textarea name="answer_{_e(qid)}" rows="3" placeholder="Sua resposta…">{_e(answer)}</textarea>'
            + ('<small>Respondida · salvar novamente não usa IA.</small>' if answer else '<small>Pergunta dinâmica derivada da Parte 1; a resposta é decisão humana.</small>')
            + '</label>'
        )
    if not question_html:
        question_html = '<div class="notice notice-ok"><div><strong>Nenhuma pergunta aberta</strong><span>O agente não identificou uma decisão humana adicional nesta revisão.</span></div></div>'
    warnings = "".join(f'<li>{_e(x)}</li>' for x in rec.get("warnings") or []) or '<li>Nenhum warning.</li>'
    accepted = str(rec.get("status") or "") == "accepted"
    discarded = str(rec.get("status") or "") == "discarded"
    if accepted:
        status_tone, status_label = "ok", "Vídeo criado"
    elif discarded:
        status_tone, status_label = "neutral", "Descartada"
    elif open_questions:
        status_tone, status_label = "warn", f"{len(open_questions)} resposta(s) pendente(s)"
    elif is_final:
        status_tone, status_label = "ok", "Pronta para aceitar"
    else:
        status_tone, status_label = "info", "Aguardando consolidação"
    runner = str(rec.get("runner") or "codex")
    model = str(rec.get("model") or "")
    effort = str(rec.get("reasoning_effort") or "low")
    usage = rec.get("runner_usage") if isinstance(rec.get("runner_usage"), dict) else {}
    usage_text = f" · {usage.get('total_tokens')} tokens" if usage.get("total_tokens") else ""
    actions = ""
    if not accepted and not discarded:
        answers_panel = (
            '<section class="proposal-answer-panel"><div class="panel-head compact-head"><div><span class="eyebrow">Parte 2 · perguntas dinâmicas</span><h4>Responda o que realmente muda o vídeo</h4><p>As perguntas foram geradas a partir da Parte 1 e da evidência disponível. Salvar respostas não usa modelo.</p></div></div>'
            f'<form method="post" action="/action/video-proposal-answers">{_csrf(csrf_token)}<input type="hidden" name="slug" value="{_e(slug)}"><input type="hidden" name="id" value="{_e(pid)}">{question_html}<button class="button button-secondary" type="submit">Salvar respostas · sem IA</button></form></section>'
        ) if questions else ""
        consolidate = ""
        if not is_final:
            resume_candidate = J.video_resume_candidate(root, slug, "part2", proposal_id=pid)
            resume_html = ""
            if resume_candidate and not open_questions:
                sid = str(resume_candidate.get("session_id") or "")
                resume_html = (
                    '<div class="notice notice-info proposal-resume-notice"><div><strong>Tentativa anterior recuperável</strong>'
                    '<span>Continua exatamente a mesma sessão desta Parte 2 e envia somente <code>Continue.</code>. O prompt completo e as transcrições não são reenviados.</span>'
                    f'<small>{_e(resume_candidate.get("runner") or "runner")} · {_e(resume_candidate.get("model") or "modelo padrão")} · {_e(resume_candidate.get("reasoning_effort") or "default")} · sessão {_e(sid[:18] + ("…" if len(sid) > 18 else ""))}</small></div>'
                    f'<form class="agent-form resume-agent-form" method="post" action="/action/video-proposal-refine" data-runner-form data-runner-config="{{}}">{_csrf(csrf_token)}'
                    f'<input type="hidden" name="slug" value="{_e(slug)}"><input type="hidden" name="id" value="{_e(pid)}">'
                    f'<input type="hidden" name="continue_attempt" value="1"><input type="hidden" name="resume_job_id" value="{_e(resume_candidate.get("job_id") or "")}">'
                    f'<button class="button button-secondary button-small" type="submit">Continuar tentativa anterior</button><div class="agent-submit-feedback" data-agent-feedback hidden></div></form></div>'
                )
            consolidate = (
                '<section class="proposal-refine-panel"><div class="panel-head compact-head"><div><span class="eyebrow">Parte 2 · consolidação</span><h4>Transformar respostas em proposta final</h4><p>O agente aplica as decisões humanas à Parte 1, remove perguntas resolvidas e só pode abrir uma nova pergunta se surgir um bloqueador real.</p></div></div>'
                + resume_html
                + f'<form class="agent-form video-agent-form" method="post" action="/action/video-proposal-refine" data-runner-form data-runner-config="{_e(json.dumps(_runner_client_config(__import__("cstudio.runners", fromlist=["runner_ui_config"]).runner_ui_config(root, "analysis")), ensure_ascii=False))}">'
                + f'{_csrf(csrf_token)}<input type="hidden" name="slug" value="{_e(slug)}"><input type="hidden" name="id" value="{_e(pid)}">'
                + '<label class="prompt-field"><span>Instrução de consolidação</span><textarea name="request" rows="3" required>Consolide a Parte 2 usando todas as respostas humanas salvas como decisões autoritativas. Torne a proposta específica, remova perguntas resolvidas e preserve os candidate moments sustentados pela transcrição.</textarea></label>'
                + _video_runner_controls(root, runner, model, effort, f"refine-{pid}")
                + f'<button class="button button-primary" type="submit"{" disabled" if open_questions else ""}>Consolidar Parte 2 com agente</button><div class="agent-submit-feedback" data-agent-feedback hidden></div></form></section>'
            )
        decision = (
            '<div class="proposal-decision-actions"><div><strong>Decisão humana final</strong><span>Aceitar cria um work item de vídeo sem copiar mídia. Sources completos podem ser materializados antes da precisão/cutlist.</span></div><div class="review-actions">'
            f'<form method="post" action="/action/video-proposal-accept" data-confirm="Criar um vídeo planejado a partir desta proposta consolidada?">{_csrf(csrf_token)}<input type="hidden" name="slug" value="{_e(slug)}"><input type="hidden" name="id" value="{_e(pid)}"><button class="button button-success" type="submit"{" disabled" if (open_questions or not is_final) else ""}>Aceitar e criar vídeo</button></form>'
            f'<form method="post" action="/action/video-proposal-discard" data-confirm="Descartar esta proposta? O histórico será preservado.">{_csrf(csrf_token)}<input type="hidden" name="slug" value="{_e(slug)}"><input type="hidden" name="id" value="{_e(pid)}"><button class="button button-ghost" type="submit">Descartar</button></form>'
            '</div></div>'
        )
        actions = answers_panel + consolidate + decision
    return (
        f'<article class="video-proposal-card" id="video-proposal-{_e(pid)}">'
        '<div class="video-proposal-head"><div>'
        f'<div class="review-meta">{_badge(status_label, status_tone)}{_badge(phase_label, phase_tone)}<span>rev. {_e(rec.get("revision") or 1)}</span><code>{_e(pid)}</code></div>'
        f'<h3>{_e(video.get("working_title") or rec.get("summary") or "Vídeo sem título")}</h3>'
        f'<p>{_e(rec.get("summary") or "")}</p></div><div class="video-duration"><strong>{_e((video.get("target_duration_minutes") or {}).get("min") or 8)}–{_e((video.get("target_duration_minutes") or {}).get("max") or 15)} min</strong><span>alvo</span></div></div>'
        '<div class="video-proposal-meta">'
        f'<span>{_e(runner)} · {_e(model or "modelo padrão")} · reasoning {_e(effort)}{_e(usage_text)}</span><span>{len(source_rows)} VOD(s)</span></div>'
        '<details class="proposal-inspector"><summary><span>Abrir proposta</span><small>Parte 1 + evidência + Parte 2</small></summary><div class="proposal-inspector-body">'
        '<div class="video-brief-grid"><section><span class="eyebrow">Parte 1 / proposta atual</span><h4>Direção editorial deste vídeo</h4><div class="proposal-document"><pre>' + _e(rec.get("document") or "") + '</pre></div></section>'
        '<section><span class="eyebrow">Fontes compartilhadas</span><h4>VODs desta proposta</h4><ul class="video-source-list">' + source_html + '</ul><span class="eyebrow warning-eyebrow">Warnings</span><ul class="proposal-note-list">' + warnings + '</ul></section></div>'
        + _candidate_moments_html(rec.get("candidate_moments") or []) + actions + '</div></details></article>'
    )

def _videos_page(root: str, slug: str, st: dict, csrf_token: str) -> str:
    from . import video_plans as VP, jobs as J, runners as R, source_media as SM
    catalog = VP.source_catalog(root, slug)
    ready_catalog = [x for x in catalog if x.get("proposal_ready")]
    proposals = VP.list_video_proposals(root, slug)
    videos = VP.list_videos(root, slug)
    pending = [p for p in proposals if p.get("status") == "pending"]
    J.mark_stale_failed(root, slug)
    latest = next((j for j in J.list_jobs(root, slug, 50) if j.get("type") in {"video-proposal", "video-proposal-refine", "video-candidate-precision"}), None)
    running = bool(latest and latest.get("status") == "running")
    part1_resume = J.video_resume_candidate(root, slug, "part1") if not running else None
    body = _page_header(
        "Vídeos", "Planejamento editorial",
        "Cada proposal representa um vídeo. A descoberta usa transcrição completa com timestamps por segmento; word timestamps só entram depois, nos candidates escolhidos para a cutlist.",
        _badge(f"{len(videos)} planejado(s) · {len(pending)} proposta(s)", "info" if pending else "ok"),
    )
    body += '<section class="video-flow"><article class="video-flow-step is-done"><span>1</span><div><strong>Transcrever para descobrir</strong><small>Áudio temporário ou source local · timestamps por segmento</small></div></article><article class="video-flow-step is-current"><span>2</span><div><strong>Parte 1 → Parte 2</strong><small>Ideia inicial → perguntas dinâmicas → consolidação</small></div></article><article class="video-flow-step"><span>3</span><div><strong>Precisão + cutlist</strong><small>Word timestamps nos candidates → Premiere waveform</small></div></article></section>'
    if not ready_catalog:
        if catalog:
            empty_title = "Fontes ainda não prontas para proposal"
            downloaded = sum(1 for x in catalog if x.get("media_ready"))
            empty_copy = f"Há {len(catalog)} VOD(s) no pool e {downloaded} com mídia durável local. Para planejar não é necessário baixar o MP4: use Áudio → transcrever em Fontes e volte quando a evidência por segmento estiver pronta."
        else:
            empty_title = "Nenhum VOD registrado ainda"
            empty_copy = "Seu pipeline começa em Fontes: capture os VODs e gere transcrição de descoberta. O download dos sources completos pode ficar para depois da proposal."
        body += '<section class="panel"><div class="empty-state hero-empty"><strong>' + _e(empty_title) + '</strong><span>' + _e(empty_copy) + '</span><a class="button button-primary" href="/?page=sources&slug=' + _q(slug) + '">Abrir Fontes</a></div></section>'
    else:
        source_cards = []
        for item in ready_catalog:
            mirrors = len(item.get("verified_mirrors") or [])
            source_cards.append(
                '<label class="vod-choice"><input type="checkbox" name="source_asset_ids" value="' + _e(item.get("asset_id")) + '" checked>'
                '<span class="vod-choice-copy"><strong>' + _e(item.get("title")) + '</strong><small>' + _e(item.get("created_at") or "data desconhecida") + ' · ' + _e(_format_hms(item.get("duration_seconds") or 0)) + f' · {mirrors} mirror(s) · transcrição por segmento pronta</small><code>' + _e(item.get("vod_id")) + '</code></span></label>'
            )
        ui = R.runner_ui_config(root, "analysis")
        runner_config = _e(json.dumps(_runner_client_config(ui), ensure_ascii=False))
        part1_resume_html = ""
        if part1_resume:
            sid = str(part1_resume.get("session_id") or "")
            part1_resume_html = (
                '<div class="notice notice-info proposal-resume-notice"><div><strong>Parte 1 anterior pode continuar</strong>'
                '<span>Retoma a sessão exata da tentativa falha e envia somente <code>Continue.</code>. Use “nova tentativa” abaixo se quiser reconstruir o contexto do zero.</span>'
                f'<small>{_e(part1_resume.get("runner") or "runner")} · {_e(part1_resume.get("model") or "modelo padrão")} · {_e(part1_resume.get("reasoning_effort") or "default")} · sessão {_e(sid[:18] + ("…" if len(sid) > 18 else ""))}</small></div>'
                f'<form class="agent-form resume-agent-form" method="post" action="/action/video-proposal-run" data-runner-form data-runner-config="{{}}">{_csrf(csrf_token)}'
                f'<input type="hidden" name="slug" value="{_e(slug)}"><input type="hidden" name="continue_attempt" value="1"><input type="hidden" name="resume_job_id" value="{_e(part1_resume.get("job_id") or "")}">'
                f'<button class="button button-secondary button-small" type="submit">Continuar tentativa anterior da Parte 1</button><div class="agent-submit-feedback" data-agent-feedback hidden></div></form></div>'
            )
        body += (
            '<section class="panel new-video-panel"><div class="panel-head"><div><span class="eyebrow">Parte 1 · novo vídeo</span><h2>Comece pela ideia geral</h2><p>Escolha os VODs transcritos e descreva a intenção. O agente monta uma primeira proposta baseada em evidência e, em seguida, gera perguntas específicas para você estreitar o vídeo na Parte 2.</p></div>' + _badge("evidência local", "ok") + '</div>'
            + part1_resume_html
            + f'<form class="agent-form video-agent-form" method="post" action="/action/video-proposal-run" data-runner-form data-runner-config="{runner_config}">{_csrf(csrf_token)}<input type="hidden" name="slug" value="{_e(slug)}">'
            '<fieldset class="vod-selector"><legend>VODs disponíveis <small>marque o pool permitido para este vídeo</small></legend><div class="vod-choice-grid">' + ''.join(source_cards) + '</div><div class="vod-selector-actions"><button type="button" class="text-button" data-vod-select="all">Selecionar todos</button><button type="button" class="text-button" data-vod-select="none">Limpar seleção</button><span data-vod-selection-count></span></div></fieldset>'
            '<label class="prompt-field"><span>Ideia geral / objetivo da Parte 1</span><textarea name="request" rows="5" required placeholder="Ex.: Quero explorar um vídeo sobre os momentos mais engraçados durante Onimusha. Ainda quero decidir ritmo, foco e o que deve ficar de fora depois de ver a primeira proposta."></textarea><small>Não precisa fechar tudo agora. As perguntas da Parte 2 serão dinâmicas e baseadas nesta proposta inicial.</small></label>'
            + _video_runner_controls(root, "codex", "", "", "new-video")
            + f'<button class="button button-primary" type="submit"{" disabled" if running else ""}>{_icon("play")} {"Execução em andamento…" if running else "Gerar Parte 1 + perguntas"}</button><div class="agent-submit-feedback" data-agent-feedback hidden></div></form></section>'
        )
    body += '<section class="panel"><div class="panel-head"><div><span class="eyebrow">Execução</span><h2>Agente de planejamento</h2><p>Uma criação ou refinamento por vez. O job continua fora da request HTTP.</p></div><span data-studio-job-connection>Monitor local</span></div><div class="studio-job-fragment" data-studio-job-endpoint="/ui/studio-job?slug=' + _q(slug) + '&kind=video-proposals">' + render_studio_job(root, slug, "video-proposals") + '</div></section>'
    if pending:
        body += '<section class="video-proposals-section"><div class="section-heading"><span class="eyebrow">Em planejamento</span><h2>Parte 1 → perguntas → Parte 2</h2><p>Responda as perguntas dinâmicas sem IA e depois consolide a Parte 2 com o agente antes de aceitar o vídeo.</p></div>' + ''.join(_video_proposal_card(root, slug, p, csrf_token) for p in pending) + '</section>'
    else:
        body += '<section class="review-clear"><div class="review-clear-icon">' + _icon("check") + '</div><div><span class="eyebrow">Planejamento</span><h2>Nenhuma proposta pendente</h2><p>Crie a próxima ideia de vídeo usando o mesmo pool de VODs.</p></div></section>'
    old = [p for p in proposals if p.get("status") != "pending"]
    if old:
        body += '<details class="technical-details"><summary><span>Histórico de propostas de vídeo</span><small>' + _e(len(old)) + ' processada(s)</small></summary><div class="technical-details-body">' + ''.join(_video_proposal_card(root, slug, p, csrf_token) for p in old[:20]) + '</div></details>'
    body += '<section class="panel" id="planned-videos"><div class="panel-head"><div><span class="eyebrow">Depois da proposal</span><h2>Vídeos planejados</h2><p>Agora materialize apenas as fontes realmente necessárias e gere word timestamps somente para os candidate moments antes da cutlist.</p></div>' + _badge(str(len(videos)), "ok" if videos else "neutral") + '</div>'
    if videos:
        planned_cards = []
        for v in videos:
            precision = v.get("candidate_precision") if isinstance(v.get("candidate_precision"), dict) else SM.candidate_precision_status(root, slug, str(v.get("id") or ""))
            candidate_ids = sorted({str(m.get("source_asset_id") or "") for m in (v.get("candidate_moments") or []) if isinstance(m, dict) and str(m.get("source_asset_id") or "")})
            missing_media = []
            for aid in candidate_ids:
                try:
                    SM.asset_path(root, slug, aid)
                except C.StudioError:
                    missing_media.append(aid)
            precision_action = ""
            if not candidate_ids:
                precision_action = '<small>Sem candidates na proposal; a análise pode encontrar novos momentos antes da precisão.</small>'
            elif str(precision.get("status") or "") == "completed":
                precision_action = _badge(f'{precision.get("word_count") or 0} words alinhadas', "ok") + '<small>Word timestamps limitados aos candidates. Frame-level continua no Premiere.</small>'
            elif missing_media:
                precision_action = _badge("source necessário", "warn") + '<small>Baixe a fonte completa de ' + _e(", ".join(missing_media)) + ' antes do alinhamento fino.</small>'
            else:
                precision_action = (
                    '<form method="post" action="/action/video-candidate-precision">' + _csrf(csrf_token)
                    + f'<input type="hidden" name="slug" value="{_e(slug)}"><input type="hidden" name="video_id" value="{_e(v.get("id"))}">'
                    + f'<button class="button button-secondary button-small" type="submit"{" disabled" if running else ""}>Gerar word timestamps dos candidates</button></form>'
                )
            planned_cards.append(
                '<article class="planned-video-card"><div><span class="eyebrow">' + _e(v.get("stage") or "analysis") + '</span><h3>' + _e(v.get("title") or v.get("id")) + '</h3><p>' + _e(len(v.get("source_asset_ids") or [])) + ' VOD(s) · ' + _e((v.get("target_duration_minutes") or {}).get("min") or 8) + '–' + _e((v.get("target_duration_minutes") or {}).get("max") or 15) + ' min</p><div class="master-source-actions">' + precision_action + '</div></div><code>' + _e(v.get("id")) + '</code></article>'
            )
        body += '<div class="planned-video-grid">' + ''.join(planned_cards) + '</div>'
    else:
        body += '<div class="empty-state compact"><strong>Nenhum vídeo aceito ainda</strong><span>Quando você aceitar uma proposta, o work item aparece aqui no estágio de análise.</span></div>'
    body += '</section><div class="technical-link-row"><a class="text-link" href="/?page=reviews&slug=' + _q(slug) + '">Abrir revisões técnicas do harness ' + _icon("arrow") + '</a></div>'
    return body


def _reviews_page(root: str, slug: str, st: dict, props: list[dict], csrf_token: str) -> str:
    pending = [p for p in props if str(p.get("status") or "") == "pending"]
    current = str(st.get("stage") or "")
    gates = list(st.get("gates") or [])
    current_gate = next((g for g in gates if str(g.get("stage") or "") == current), None)
    body = _page_header(
        "Revisões técnicas",
        "Harness legado",
        "Aqui ficam proposals e gates dos 12 stages técnicos. Propostas editoriais de um vídeo ficam em Vídeos, com respostas e refinamento próprios.",
        _badge(f"{len(pending)} proposal(s)", "warn" if pending else "ok"),
    )
    if pending:
        body += '<section class="panel review-priority"><div class="panel-head"><div><span class="eyebrow">Primeiro</span><h2>Revise o trabalho dos agentes</h2><p>Abra a proposal para ver o diff e o conteúdo completo. Aplicar só aparece dentro da revisão aberta.</p></div></div>' + _proposal_queue(root, props, slug, csrf_token) + '</section>'
    else:
        body += '<section class="review-clear"><div class="review-clear-icon">' + _icon("check") + '</div><div><span class="eyebrow">Inbox</span><h2>Nenhuma proposal esperando você</h2><p>Quando um agente terminar, a decisão aparecerá aqui.</p></div></section>'
    body += '<div class="two-column review-grid"><section class="panel"><div class="panel-head"><div><span class="eyebrow">Fase atual</span><h2>Gate e readiness</h2></div>' + _badge("Bloqueado" if st.get("blocked") else "Pronto", "danger" if st.get("blocked") else "ok") + '</div>'
    body += _checks_table(st.get("checks", []))
    if current_gate:
        approved = bool(current_gate.get("approved"))
        if not approved:
            body += ('<div class="approval-card"><div><strong>' + _e(current_gate.get("gate")) + '</strong><span>Esta aprovação fica vinculada aos fingerprints atuais.</span></div>'
                     '<form method="post" action="/action/approve">' + _csrf(csrf_token) + f'<input type="hidden" name="slug" value="{_e(slug)}"><input type="hidden" name="gate" value="{_e(current_gate.get("gate"))}"><button class="button button-success" type="submit">Aprovar gate</button></form></div>')
        else:
            body += '<div class="approval-card approved"><div><strong>Gate aprovado</strong><span>Integridade preservada pelos fingerprints dos artefatos.</span></div>' + _badge("Aprovado", "ok") + '</div>'
    body += '</section><section class="panel"><div class="panel-head"><div><span class="eyebrow">Histórico</span><h2>Decisões recentes</h2></div></div>' + _proposal_history(props) + '</section></div>'
    if not st.get("blocked") and (not current_gate or current_gate.get("approved")):
        body += ('<section class="advance-banner"><div><span class="eyebrow">Pronto</span><h2>Esta fase pode avançar</h2><p>O backend revalida tudo antes de mover o pipeline.</p></div><form method="post" action="/action/advance">' + _csrf(csrf_token) + f'<input type="hidden" name="slug" value="{_e(slug)}"><button class="button button-primary" type="submit">Avançar fase</button></form></section>')
    return body


def _premiere_page(root: str, slug: str, st: dict, csrf_token: str) -> str:
    from . import nle as NLE
    from . import jobs as J
    from . import edit_media as EM
    driver = NLE.get_driver(root=root)
    status = driver.status()
    vdir = C.prod_path(root, slug)
    timeline = os.path.join(vdir, ".studio", "internal", "assembly", "timeline.json")
    timeline_ready = False
    if os.path.isfile(timeline):
        try:
            with open(timeline, encoding="utf-8") as fh:
                timeline_ready = bool((json.load(fh) or {}).get("events"))
        except Exception:
            timeline_ready = False
    handoff_dir = os.path.join(vdir, ".studio", "internal", "assembly", driver.name)
    handoff_ready = os.path.isfile(os.path.join(handoff_dir, "premiere-edit-spec.json"))
    media_manifest = EM.read_manifest(root, slug) or {}
    media_summary = dict(media_manifest.get("summary") or {})
    media_ready = int(media_summary.get("media_ready") or 0)
    media_missing = int(media_summary.get("media_missing") or 0)
    cutlist_gate = next((g for g in st.get("gates", []) or [] if g.get("gate") == "cutlist_lock"), {})
    J.mark_stale_failed(root, slug)
    latest = J.latest_job(root, slug)
    running = bool(latest and latest.get("status") == "running")
    body = _page_header(
        "Premiere",
        "Montagem e export",
        "O dashboard expõe só operações editoriais seguras. As centenas de ferramentas MCP permanecem atrás deste fluxo.",
        _badge("MCP detectado" if status.get("available") else "MCP não detectado", "ok" if status.get("available") else "warn"),
    )
    body += '<section class="premiere-flow">'
    steps = [
        ("1", "Organizar mídia", media_ready > 0 and media_missing == 0, "Mapeie os arquivos já baixados para bins lógicos sem mover nem duplicar os masters."),
        ("2", "Verificar integração", bool(status.get("available")), "Confirme instalação e bridge local sem alterar a timeline."),
        ("3", "Preparar handoff", handoff_ready, "Gere edit spec, timeline e runbook a partir do artefato de assembly."),
        ("4", "Montar e conferir", bool(cutlist_gate.get("approved")), "Mutação ao vivo só deve acontecer depois do cutlist_lock e com readback."),
        ("5", "Exportar master", str(st.get("stage")) in {"composition", "metadata", "publish", "learn"}, "O master volta ao harness como evidência de composição."),
    ]
    for num, title, ok, desc in steps:
        body += f'<article class="premiere-step {"is-ready" if ok else ""}"><span>{_e(num)}</span><div><strong>{_e(title)}</strong><small>{_e(desc)}</small></div>{_badge("OK" if ok else "pendente", "ok" if ok else "neutral")}</article>'
    body += '</section>'
    body += '<section class="panel" id="premiere-media"><div class="panel-head"><div><span class="eyebrow">Mídia</span><h2>Organização para edição</h2><p>Cria somente um mapa de bins para o Premiere. Os arquivos permanecem exatamente onde o resolver os baixou.</p></div>' + _badge(f"{media_ready} arquivo(s)", "ok" if media_ready else "neutral") + '</div>'
    if media_manifest:
        bin_items = ''.join(f'<div class="media-bin-row"><strong>{_e(name)}</strong><span>{_e(count)} arquivo(s)</span></div>' for name, count in sorted((media_summary.get("bins") or {}).items()))
        body += '<div class="media-manifest-summary"><div><strong>Manifest pronto</strong><span><code>.studio/internal/assembly/edit-media-manifest.json</code></span></div>' + (f'<div class="media-bin-list">{bin_items}</div>' if bin_items else '<span class="muted">Nenhuma mídia de vídeo registrada ainda.</span>') + '</div>'
        if media_missing:
            body += f'<div class="notice notice-warn"><div><strong>{media_missing} arquivo(s) registrado(s) não encontrado(s)</strong><span>O manifest não tenta corrigir paths automaticamente. Refaça o download ou ajuste o ingest antes da montagem.</span></div></div>'
    else:
        body += '<div class="notice"><div><strong>Manifest ainda não gerado</strong><span>Use o registry de ingest como fonte de verdade para organizar os masters em bins lógicos.</span></div></div>'
    body += ('<form method="post" action="/action/premiere-media-manifest">' + _csrf(csrf_token) + f'<input type="hidden" name="slug" value="{_e(slug)}"><button class="button button-primary" type="submit">{"Atualizar organização" if media_manifest else "Preparar mídia para edição"}</button></form></section>')
    body += '<div class="two-column premiere-grid"><section class="panel"><div class="panel-head"><div><span class="eyebrow">Bridge local</span><h2>Diagnóstico do Premiere MCP</h2><p>Detectar o executável não prova uma conexão live; o doctor é um preflight seguro.</p></div></div>'
    body += '<dl class="json-facts">' + ''.join([
        f'<div><dt>Driver</dt><dd>{_e(status.get("driver") or "—")}</dd></div>',
        f'<div><dt>Comando</dt><dd>{_e(status.get("command") or "—")}</dd></div>',
        f'<div><dt>Transport</dt><dd>{_e(status.get("transport") or "—")}</dd></div>',
        f'<div><dt>Unsafe script</dt><dd>{_e("bloqueado" if not status.get("unsafe_script") else "ATIVO")}</dd></div>',
    ]) + '</dl>'
    body += ('<form method="post" action="/action/premiere-doctor">' + _csrf(csrf_token) + f'<input type="hidden" name="slug" value="{_e(slug)}"><button class="button button-primary" type="submit"{" disabled" if running else ""}>Executar diagnóstico</button></form></section>')
    body += '<section class="panel"><div class="panel-head"><div><span class="eyebrow">Handoff</span><h2>Preparar arquivos para montagem</h2><p>Não move VODs nem duplica masters; gera apenas instruções e artefatos determinísticos para a integração.</p></div></div>'
    if timeline_ready:
        body += f'<div class="notice notice-ok"><div><strong>Timeline de assembly disponível</strong><span>{_e(os.path.relpath(timeline, vdir))}</span></div></div>'
        body += ('<form method="post" action="/action/premiere-export">' + _csrf(csrf_token) + f'<input type="hidden" name="slug" value="{_e(slug)}"><button class="button button-primary" type="submit"{" disabled" if running else ""}>Preparar handoff</button></form>')
    else:
        body += '<div class="notice notice-warn"><div><strong>Assembly ainda não tem uma timeline utilizável</strong><span>Conclua a cutlist/assembly antes de gerar o handoff. O template vazio não conta como montagem.</span></div></div>'
    body += '</section></div>'
    body += f'<section class="panel"><div class="panel-head"><div><span class="eyebrow">Execuções</span><h2>Job atual</h2></div><span data-studio-job-connection>Monitor local</span></div><div class="studio-job-fragment" data-studio-job-endpoint="/ui/studio-job?slug={_q(slug)}">{render_studio_job(root, slug)}</div></section>'
    body += '<section class="safety-note"><div>' + _icon("gates") + '</div><div><strong>Boundary de segurança</strong><p>Proposal runners continuam sem acesso de escrita ao Premiere. Mutação MCP permanece separada e deve respeitar cutlist_lock + readback.</p></div></section>'
    return body


def _diagnostics_page(root: str, slug: str, st: dict, history: list[dict]) -> str:
    from . import twitch as TW
    diag = {
        "stage": st.get("stage"), "state": st.get("state"), "blocked": st.get("blocked"),
        "gates": st.get("gates"), "checks": st.get("checks"), "history": history[-20:],
    }
    health = TW.scraper_health(root)
    body = _page_header("Diagnóstico", "Sistema", "Estado observável do harness para investigação. Esta página não altera nenhuma decisão da produção.")
    body += '<div class="metric-grid metric-grid-3">' + _metric("Stage", _stage_label(root, str(st.get("stage") or "")), str(st.get("stage") or ""), "blue", "production") + _metric("Estado", str(st.get("state") or "—"), "lifecycle da produção", "purple", "activity") + _metric("Readiness", "Bloqueado" if st.get("blocked") else "Pronto", "resultado determinístico", "red" if st.get("blocked") else "green", "check") + '</div>'
    body += '<div class="two-column diagnostics-grid"><section class="panel"><div class="panel-head"><div><span class="eyebrow">Checks</span><h2>Verificações atuais</h2></div></div>' + _checks_table(st.get("checks", [])) + '</section>'
    body += '<section class="panel"><div class="panel-head"><div><span class="eyebrow">Twitch scraper</span><h2>Saúde local</h2></div></div><dl class="json-facts">' + ''.join([
        f'<div><dt>Script</dt><dd>{_e("presente" if health.get("script_present") else "ausente")}</dd></div>',
        f'<div><dt>Bun</dt><dd>{_e(health.get("bun") or "não encontrado")}</dd></div>',
        f'<div><dt>Dependências</dt><dd>{_e("presentes" if health.get("dependencies_present") else "pendentes")}</dd></div>',
    ]) + '</dl></section></div>'
    body += '<section class="panel"><div class="panel-head"><div><span class="eyebrow">Estado bruto</span><h2>Workflow snapshot</h2></div></div><pre class="code-block">' + _e(json.dumps(diag, ensure_ascii=False, indent=2)) + '</pre></section>'
    return body


def render(root: str, page: str, slug: str = "", csrf_token: str = "") -> str:
    """Render a complete dashboard page.

    ``csrf_token`` is injected by the local HTTP server. CLI-generated HTML may omit it.
    """
    try:
        productions = list(C.list_productions(root) or [])
    except Exception:
        productions = []
    page = page if page in PAGE_LABELS else "production"

    if page == "production":
        body, selected_status, history = _production_page(root, productions, slug, csrf_token)
        # _production_page may choose the active production when no slug was supplied.
        if not slug and selected_status:
            try:
                active = C.active_production(root)
                slug = str((active or {}).get("slug") or "")
            except Exception:
                pass
        return layout(root, page, body, slug, productions, selected_status, history, csrf_token)

    if not slug:
        body = _page_header(PAGE_LABELS[page], "Produção necessária", "Escolha uma produção no topo para abrir esta área.")
        body += '<section class="empty-state hero-empty"><strong>Selecione uma produção</strong><span>As telas operacionais sempre trabalham dentro de uma produção explícita.</span><a class="button button-primary" href="/?page=production">Abrir produções</a></section>'
        return layout(root, page, body, "", productions, None, [], csrf_token)

    try:
        st = C.workflow_status(root, slug)
    except Exception as exc:
        body = _page_header("Produção indisponível", "Erro", "Não foi possível carregar o estado solicitado.")
        body += f'<div class="notice notice-danger">{_icon("warning")}<div><strong>Falha ao carregar</strong><span>{_e(exc)}</span></div></div>'
        return layout(root, page, body, slug, productions, None, _history_for(root, slug), csrf_token)

    history = _history_for(root, slug)
    try:
        props = list(P.list_proposals(root, slug) or [])
    except Exception:
        props = []

    if page == "sources":
        body = _sources_page(root, slug, st, csrf_token)
    elif page == "videos":
        body = _videos_page(root, slug, st, csrf_token)
    elif page == "reviews":
        body = _reviews_page(root, slug, st, props, csrf_token)
    elif page == "premiere":
        body = _premiere_page(root, slug, st, csrf_token)
    elif page == "twitch":
        body = _twitch_page(root, slug, st, csrf_token)
    elif page == "youtube":
        body = _youtube_page(root, slug, st, csrf_token)
    elif page == "gates":
        body = _gates_page(root, slug, st, csrf_token)
    elif page == "proposals":
        body = _proposals_page(slug, props, csrf_token)
    elif page in ARTIFACT_PAGES:
        body = _artifact_page(root, page, slug, st)
    else:
        body = _diagnostics_page(root, slug, st, history)
    return layout(root, page, body, slug, productions, st, history, csrf_token)
