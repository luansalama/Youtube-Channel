"""Server-rendered dashboard for Cuts Studio.

The dashboard is deliberately stdlib-first: Python remains authoritative for domain
state/actions and the browser is only a progressively enhanced presentation layer.
CSS and JavaScript live in ``cstudio/static`` so the server can enforce a strict CSP.
"""
from __future__ import annotations

import csv
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
    ("Operação", [("production", "Visão geral"), ("twitch", "Captura Twitch"), ("youtube", "YouTube Mirrors")]),
    ("Revisão humana", [("proposals", "Propostas"), ("gates", "Aprovações")]),
    ("Construção", [
        ("cutlist", "Cutlist"), ("sync", "Sincronização"), ("graphics", "Gráficos"),
        ("master", "Master"), ("release", "Release"),
    ]),
    ("Sistema", [("diagnostics", "Diagnóstico")]),
]
NAV = [item for _group, items in NAV_GROUPS for item in items]
PAGE_LABELS = dict(NAV)

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
<link rel="stylesheet" href="/static/dashboard.css?v=3">
<script src="/static/dashboard.js?v=3" defer></script>
</head>
<body data-page="{_e(page)}" data-slug="{_e(slug)}">
<div class="app-shell">
<div class="mobile-backdrop" data-close-sidebar></div>
<aside class="sidebar" id="sidebar" aria-label="Navegação principal">
  <a class="brand" href="/?page=production"><span class="brand-mark">C</span><span><strong>Cuts Studio</strong><small>Twitch → YouTube</small></span></a>
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


def _proposal_queue(props: list[dict], slug: str, csrf_token: str) -> str:
    pending = [p for p in props if str(p.get("status")) == "pending"]
    if not pending:
        return '<div class="empty-state"><strong>Fila limpa</strong><span>Não há propostas aguardando revisão humana.</span></div>'
    cards = []
    for p in pending:
        pid = str(p.get("id") or "")
        cards.append(
            '<article class="review-card">'
            '<div class="review-copy">'
            f'<div class="review-meta">{_badge("Pendente", "warn")}<code>{_e(pid)}</code><span>{_e(p.get("runner", "manual"))}</span></div>'
            f'<h3>{_e(p.get("summary", "Proposta sem resumo"))}</h3>'
            '<p>Aplicar grava somente os arquivos já validados pelo contrato de propostas; a decisão continua humana.</p>'
            '</div><div class="review-actions">'
            '<form method="post" action="/action/apply-proposal">'
            f'{_csrf(csrf_token)}<input type="hidden" name="slug" value="{_e(slug)}"><input type="hidden" name="id" value="{_e(pid)}">'
            '<button class="button button-primary" type="submit">Aplicar proposta</button></form>'
            '<form method="post" action="/action/discard-proposal" data-confirm="Descartar esta proposta? O registro será preservado no histórico.">'
            f'{_csrf(csrf_token)}<input type="hidden" name="slug" value="{_e(slug)}"><input type="hidden" name="id" value="{_e(pid)}">'
            '<button class="button button-ghost" type="submit">Descartar</button></form>'
            '</div></article>'
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
    gates = list(st.get("gates", []) or [])
    failed = sum(1 for c in checks if not c.get("ok"))
    approved = sum(1 for g in gates if g.get("approved"))
    stage = str(st.get("stage") or "—")
    total_stages = len(_stage_data(root)) or 12
    ids = [str(s.get("id")) for s in _stage_data(root)]
    try:
        stage_no = ids.index(stage) + 1
    except ValueError:
        stage_no = 1
    return (
        '<div class="metric-grid">'
        + _metric("Fase atual", _stage_label(root, stage), f"{stage_no} de {total_stages}", "blue", "production")
        + _metric("Checks", str(len(checks) - failed), f"{failed} falhando" if failed else "todos da fase passaram", "green" if not failed else "red", "check")
        + _metric("Propostas", str(pending_props), "aguardando revisão", "purple", "proposals")
        + _metric("Gates", f"{approved}/{len(gates)}", "aprovações preservadas por fingerprint", "teal", "gates")
        + '</div>'
    )


def _next_action(root: str, st: dict, pending_props: int, slug: str, csrf_token: str) -> str:
    state = str(st.get("state") or "")
    checks = list(st.get("checks", []) or [])
    failed = [c for c in checks if not c.get("ok")]
    current = str(st.get("stage") or "")
    stage_spec = next((s for s in _stage_data(root) if str(s.get("id")) == current), {})
    gate = str(stage_spec.get("gate") or "")
    gate_row = next((g for g in st.get("gates", []) or [] if str(g.get("gate")) == gate), {}) if gate else {}

    if state == "paused":
        title, desc, tone = "Retomar a produção", "A produção está pausada. Retome antes de continuar o pipeline.", "warn"
        action = (
            '<form method="post" action="/action/resume">'
            f'{_csrf(csrf_token)}<input type="hidden" name="slug" value="{_e(slug)}">'
            '<button class="button button-primary" type="submit">Retomar produção</button></form>'
        )
    elif state == "abandoned":
        title, desc, tone, action = "Produção abandonada", "O histórico foi preservado e o pipeline não deve continuar.", "danger", ""
    elif failed:
        title, desc, tone = "Resolver verificações da fase", f"{len(failed)} check(s) ainda bloqueiam o avanço. Corrija os artefatos da fase {current} e valide novamente.", "danger"
        action = f'<a class="button button-primary" href="/?page=gates&slug={_q(slug)}">Ver verificações</a>'
    elif pending_props:
        title, desc, tone = "Revisar propostas pendentes", f"Há {pending_props} proposta(s) esperando decisão humana antes de serem aplicadas.", "purple"
        action = f'<a class="button button-primary" href="/?page=proposals&slug={_q(slug)}">Abrir fila de revisão</a>'
    elif gate and not gate_row.get("approved"):
        title, desc, tone = f"Revisar {gate}", "A fase está pronta para uma decisão humana. O gate não será aprovado automaticamente.", "purple"
        action = f'<a class="button button-primary" href="/?page=gates&slug={_q(slug)}">Revisar aprovação</a>'
    else:
        title, desc, tone = "Avançar o pipeline", "As verificações necessárias para a fase atual estão atendidas. O avanço continuará validando invariantes no backend.", "ok"
        action = (
            '<form method="post" action="/action/advance">'
            f'{_csrf(csrf_token)}<input type="hidden" name="slug" value="{_e(slug)}">'
            '<button class="button button-primary" type="submit">Avançar fase</button></form>'
        )
    return (
        f'<section class="next-action next-{_e(tone)}"><div class="next-icon">{_icon("arrow")}</div><div class="next-copy">'
        '<span class="eyebrow">Próxima ação</span>'
        f'<h2>{_e(title)}</h2><p>{_e(desc)}</p></div>'
        + (f'<div class="next-cta">{action}</div>' if action else "")
        + '</section>'
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
        "Central de produção",
        "Operação",
        "Acompanhe o trabalho que realmente destrava o próximo estágio, sem esconder checks, gates ou decisões humanas.",
    )
    if selected_status:
        try:
            props = P.list_proposals(root, slug)
        except Exception:
            props = []
        pending = sum(1 for p in props if str(p.get("status")) == "pending")
        body += _next_action(root, selected_status, pending, slug, csrf_token)
        body += _readiness_summary(root, selected_status, pending)
        body += (
            '<section class="panel"><div class="panel-head"><div><span class="eyebrow">Pipeline</span><h2>Fluxo da produção</h2></div>'
            f'<a class="text-link" href="/?page=gates&slug={_q(slug)}">Abrir aprovações {_icon("arrow")}</a></div>{_pipeline(root, str(selected_status.get("stage") or ""))}</section>'
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
            f'<td><a class="text-link" href="/?page=gates&slug={_q(ps)}">Abrir {_icon("arrow")}</a></td></tr>'
        )
    prod_table = (
        '<div class="table-scroll"><table><thead><tr><th>Produção</th><th>Fase</th><th>Estado</th><th></th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>' if rows else '<p class="empty-state compact">Ainda não há produções.</p>'
    )
    body += (
        '<div class="two-column lower-grid">'
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
        '<span>Prepara a estrutura do repositório sem alterar decisões editoriais.</span></div></section></div>'
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


def _youtube_assignment_card(slug: str, assignment: dict, vod_catalog: dict[str, dict], match_index: dict[tuple[str, str], dict], csrf_token: str) -> str:
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
        if download_status == "downloaded" and download.get("path"):
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


def _youtube_vod_coverage(assignments: list[dict], vod_catalog: dict[str, dict]) -> str:
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
        chips = ''.join(
            f'<span class="vod-video-chip" title="{_e((a.get("youtube") or {}).get("title") or a.get("youtube_video_id"))}">{_e((a.get("youtube") or {}).get("title") or a.get("youtube_video_id"))}</span>'
            for a in sorted(rows, key=lambda a: str((a.get("youtube") or {}).get("upload_date") or ""))
        )
        cards.append(
            '<article class="vod-coverage-card"><div class="vod-coverage-head"><div>'
            f'<span class="eyebrow">Twitch VOD</span><h3>{_e(vod.get("title") or vod_id)}</h3><p><code>{_e(vod_id)}</code> · {_e(vod.get("game") or vod.get("streamer") or "")}</p></div>'
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
    transcription_backend = str(health.get("transcription_backend") or "")
    if transcription_backend == "faster-whisper":
        transcription_badge = _badge("faster-whisper pronto", "ok")
        transcription_model = os.path.basename(str(health.get("faster_whisper_model") or "large-v3-turbo"))
        transcription_runtime = f"faster-whisper · batch {health.get('faster_whisper_batch_size') or 8} · {health.get('faster_whisper_compute_type') or 'float16'}"
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
        '<form method="post" action="/action/youtube-resolve">' + _csrf(csrf_token) + f'<input type="hidden" name="slug" value="{_e(slug)}"><button class="button button-primary" type="submit"{disabled}>Resolve production</button></form></div></div>'
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
        assignment_cards = ''.join(_youtube_assignment_card(slug, a, vod_catalog, match_index, csrf_token) for a in cards)
        body += (
            f'<section class="panel resolver-results"><div class="panel-head resolver-results-head"><div><span class="eyebrow">Global results</span><h2>{len(assignments)} vídeos, uma decisão por source</h2><p>Use os filtros para auditar rapidamente o resultado. Abra um card apenas quando precisar inspecionar a matriz global de VODs.</p></div><span class="resolver-result-count" data-youtube-visible-count>{len(assignments)} visíveis</span></div>'
            '<div class="resolver-filterbar"><label class="resolver-search"><span class="sr-only">Buscar assignments</span><input type="search" placeholder="Buscar título, vídeo ou VOD…" data-youtube-assignment-search></label>'
            f'<div class="resolver-state-filters" role="group" aria-label="Filtrar assignments"><button type="button" class="resolver-filter is-active" data-youtube-state-filter="all">Todos <span>{len(assignments)}</span></button><button type="button" class="resolver-filter" data-youtube-state-filter="verified">Verified <span>{assignment_verified}</span></button><button type="button" class="resolver-filter" data-youtube-state-filter="unmatched">No match <span>{assignment_no_match}</span></button><button type="button" class="resolver-filter" data-youtube-state-filter="pending">Em progresso <span>{assignment_pending}</span></button></div></div>'
            '<div class="assignment-list" data-youtube-assignment-list>' + assignment_cards + '</div><div class="empty-state compact resolver-filter-empty" data-youtube-filter-empty hidden><strong>Nenhum assignment nesse filtro</strong><span>Tente outro estado ou termo de busca.</span></div></section>'
        )
        coverage = _youtube_vod_coverage(assignments, vod_catalog)
        if coverage:
            body += '<section class="panel resolver-coverage"><div class="panel-head"><div><span class="eyebrow">VOD coverage</span><h2>Mirrors confirmados por live</h2><p>Esta visão contém somente assignments VERIFIED. VOD sem mirror permanece explicitamente vazio.</p></div>' + _badge(f"{assignment_verified} verified", "ok") + '</div>' + coverage + '</section>'
    else:
        body += '<section class="panel resolver-results"><div class="panel-head"><div><span class="eyebrow">Candidate discovery</span><h2>Pré-assignment</h2><p>Ainda não existe matriz global persistida; estes cards são sinais locais e não decisões finais.</p></div></div></section>'
        body += _youtube_legacy_vod_sections(slug, vods, matches, csrf_token, disabled)

    if not running:
        body += live_panel
    body += _youtube_channels_panel(slug, channels, csrf_token)
    body += '<section class="cli-strip"><div><span class="eyebrow">CLI equivalente</span><code>python -m cstudio --root . youtube-resolve ' + _e(slug) + ' --refresh-index</code></div><span>Audio-first preserva o verifier audiovisual; texto localizado é apenas desempate. Masters continuam restritos a assignments VERIFIED e rights permanecem fail-closed.</span></section>'
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
    body += '<section class="panel"><div class="panel-head"><div><span class="eyebrow">Inbox</span><h2>Fila para revisão</h2></div></div>' + _proposal_queue(props, slug, csrf_token) + '</section>'
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

    if page == "twitch":
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
