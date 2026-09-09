"""HTML dashboard rendering (stdlib only, dark SnowUI).

SnowUI DARK — tokens reais via Figma Dev Mode (ver docs/SNOWUI-DARK-TOKENS.md,
fonte da verdade; substitui a paleta derivada anterior):

- Page bg #333333; texto #FFFFFF / rgba(255,255,255,0.4) / faint 0.15-0.2.
- Blocks rgba(255,255,255,0.04) radius 20 padding 24 gap 16.
- Stat cards PASTEL #EDEEFC/#E6F1FD alternados, texto #000000 (kit, mesmo no dark).
- Nav ativa rgba(255,255,255,0.1) radius 12; itens 36px; sidebar 212px pad16 gap8;
  borda direita 0.5px rgba(255,255,255,0.15).
- Header 68px padding 20/28, borda bottom 0.5px; search rgba(255,255,255,0.1)+blur
  radius 16.
- Icon chips pastel 24px radius 8 glifo #000 16px; avatares circulares branco 0.1.
- Series #A0BCE8 #6BE6D3 #ADADFB #7DBBFF #B899EB #71DD8C (sparklines/donut/badges).
- Inter 12/14/24 (ss01, cv01); botoes/pills radius 12, acoes radius 8;
  tags radius 8 com dot.
- Transicoes .3s ease-out + prefers-reduced-motion; responsivo <960px.

Tela 2 (eCommerce/Overview — deltas aplicados sobre a base acima):

- Chips pill 28px radius 80 padding 4/12: fundo cor@10% + borda 0.5px cor@20%
  + label 14/400 cor 100%. Cores iOS: OK #30D158, FAIL #FF453A,
  pending #FF9F0A, info #0A84FF, gate #BF5AF2 (gates/tabelas/feed).
- Stat cards em gradiente 285x100 radius 24 padding 16/20:
  Gradient/Primary = linear-gradient(180deg, branco 5%->40%), #0A84FF;
  alterna com variante escura Gradient/Black. Titulo 16/400 branco +
  chip pill branco 20% radius 80; valor 24/600 branco.
- Titulos de secao/bloco 18/600 na cor do contexto: gates #BF5AF2,
  sync #0A84FF, master #30D158, release #FF453A, cutlist #63E6E2.
- Tabelas: header 12/400 muted padding 12/16 min-h 40px; linhas 52px
  padding 12/16; zebra rgba(255,255,255,0.04); radius 16.
- Sidebar 220px: itens 48px radius 16 padding 12 gap 12, icones 24px;
  footer simples 12px muted.
- Accent iOS #0A84FF (logo usa #0A84FF; tela 1 usava #4C98FD).
"""
from __future__ import annotations
import html
import os
import urllib.parse as _up

from . import core as C
from . import proposals as P

NAV = [("production", "Produção"), ("proposals", "Propostas"), ("gates", "Gates"),
       ("cutlist", "Cutlist"), ("sync", "Sync"), ("graphics", "Gráficos"),
       ("master", "Master"), ("release", "Release"), ("diagnostics", "Diagnóstico")]

PALETTE = {
    # SnowUI DARK real (docs/SNOWUI-DARK-TOKENS.md)
    "bg": "#333333",
    "sidebar": "#333333",
    "card": "rgba(255,255,255,0.04)",
    "elevated": "rgba(255,255,255,0.1)",
    "border": "rgba(255,255,255,0.15)",
    "faint": "rgba(255,255,255,0.2)",
    "text": "#FFFFFF",
    "muted": "rgba(255,255,255,0.4)",
    "accent": "#0A84FF",
    "accent_soft": "rgba(255,255,255,0.1)",
    "success": "#30D158",
    "danger": "#FF453A",
    "warning": "#FF9F0A",
    # chips Tela 2 (fundo cor@10% + borda cor@20% + label 100%)
    "info": "#0A84FF",
    "gate": "#BF5AF2",
    "teal": "#63E6E2",
    # stat cards pastel (texto preto mesmo no dark)
    "pastel_a": "#EDEEFC",
    "pastel_b": "#E6F1FD",
    "ink": "#000000",
}

# Series exatas do kit (sparklines, donut, badges).
SERIES = ["#A0BCE8", "#6BE6D3", "#ADADFB", "#7DBBFF", "#B899EB", "#71DD8C"]


def _e(s) -> str:
    return html.escape(str(s))


def _q(s) -> str:
    return _up.quote(str(s), safe="")


def _icon(name: str) -> str:
    """Stroke icons 16px inline (fallback manual; Figma icon components sao remotos)."""
    p = {
        "production": '<rect x="2" y="2" width="12" height="12" rx="3"/><circle cx="8" cy="8" r="2.6"/><circle cx="8" cy="8" r=".9" fill="currentColor" stroke="none"/>',
        "proposals": '<path d="M4 1.8h4.5L12 5.3V14.2H4z"/><path d="M8.3 1.8v3.7H12"/><path d="M6 8.2h4M6 10.5h4"/>',
        "gates": '<path d="M8 1.6l4.8 1.9v3.8c0 3.3-2.3 5.2-4.8 6.7-2.5-1.5-4.8-3.4-4.8-6.7V3.5z"/><path d="M6 7.8l1.5 1.5L10.2 6.5"/>',
        "cutlist": '<path d="M2.4 4h11.2M2.4 8h11.2M2.4 12h7"/><circle cx="11.6" cy="12" r="1.8"/>',
        "sync": '<path d="M13.2 8A5.2 5.2 0 1 1 8 2.8c1.9 0 3.4.9 4.4 2.4"/><path d="M12.6 1.4v3.8h-3.8"/>',
        "graphics": '<rect x="2" y="3" width="12" height="10" rx="2"/><circle cx="5.6" cy="6.4" r="1.2"/><path d="M2.4 11.4l3.4-2.9 2.4 1.9 2-1.5 3 2.4"/>',
        "master": '<circle cx="8" cy="8" r="6.2"/><path d="M6.6 5.4l4.2 2.6-4.2 2.6z"/>',
        "release": '<path d="M8 12.5V2.6"/><path d="M4.6 6L8 2.6 11.4 6"/><path d="M2.8 14.4h10.4"/>',
        "diagnostics": '<path d="M1.6 8h2.8l1.5-3.8 2.9 7.6 1.5-3.8h4.1"/>',
    }.get(name, '<circle cx="8" cy="8" r="5.5"/>')
    return (
        '<svg class="ic" viewBox="0 0 16 16" width="16" height="16" fill="none" '
        'stroke="currentColor" stroke-width="1.5" stroke-linecap="round" '
        f'stroke-linejoin="round" aria-hidden="true">{p}</svg>'
    )


def _spark(points: str, color: str) -> str:
    return (
        '<svg class="spark" viewBox="0 0 120 36" width="120" height="36" fill="none" aria-hidden="true">'
        f'<polyline points="{points}" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
        f'<circle cx="112" cy="{points.split()[-1].split(",")[1]}" r="2.6" fill="{color}"/>'
        "</svg>"
    )


def _donut(done: int, total: int) -> str:
    total = max(int(total or 0), 1)
    done = max(0, min(int(done or 0), total))
    pct = (100.0 * done / total) if total else 0.0
    circ = 2 * 3.14159265 * 34
    off = circ * (1 - done / total)
    # SnowUI: donut 120px, serie #A0BCE8, trilha branco 0.1.
    return (
        '<div class="donut-wrap">'
        '<svg class="donut" viewBox="0 0 96 96" width="120" height="120" role="img" '
        f'aria-label="Gates {done} de {total}">'
        '<circle cx="48" cy="48" r="34" fill="none" stroke="rgba(255,255,255,0.1)" stroke-width="11"/>'
        '<circle class="donut-fg" cx="48" cy="48" r="34" fill="none" stroke="#A0BCE8" '
        'stroke-width="11" stroke-linecap="round" transform="rotate(-90 48 48)" '
        f'stroke-dasharray="{circ:.1f}" stroke-dashoffset="{off:.1f}"/>'
        "</svg>"
        f'<div class="donut-c"><strong class="num">{pct:.0f}%</strong><span class="muted">{done}/{total} gates</span></div>'
        "</div>"
    )


def _stepper(root: str, current: str) -> str:
    try:
        stages = C.load_stages(root)
    except Exception:
        return '<p class="empty">Etapas indisponíveis.</p>'
    ids = [s.get("id", "") for s in stages]
    try:
        cur = ids.index(current)
    except ValueError:
        cur = 0
    items = []
    for i, s in enumerate(stages):
        sid = s.get("id", "")
        label = s.get("label", sid)
        gate = s.get("gate")
        cls = "done" if i < cur else ("cur" if i == cur else "todo")
        dot = "✓" if i < cur else (str(i + 1))
        lock = " 🔒" if gate else ""
        items.append(
            f'<li class="step {cls}" title="{_e(sid)}{" · gate " + _e(gate) if gate else ""}">'
            f'<span class="dot num">{_e(dot)}</span>'
            f'<span class="step-t">{_e(label)}{_e(lock)}</span>'
            f'<span class="step-id mono">{_e(sid)}</span></li>'
        )
    return f'<ol class="stepper">{"".join(items)}</ol>'


def _stat_cards(st: dict, pending_props: int) -> str:
    gates = st.get("gates", []) or []
    checks = st.get("checks", []) or []
    total_g = len(gates)
    ok_g = sum(1 for g in gates if g.get("approved"))
    fails = sum(1 for c in checks if not c.get("ok"))
    stage = str(st.get("stage", "—"))
    try:
        idx = C.stage_index(".", stage)
        pos = f"{idx + 1}/12"
    except Exception:
        pos = "—"
    # Tela 2: cards em gradiente, alternando Primary (#0A84FF) / Black.
    # Titulo 16/400 branco + chip pill branco 20%; valor 24/600 branco.
    cards = [
        ("Stage", _e(stage), f"fase {pos}", _spark("4,28 24,24 44,26 64,18 84,20 104,12 112,14", "#FFFFFF"), "stat-primary"),
        ("Gates", f"{ok_g}/{total_g}", "aprovados", _spark("4,26 24,22 44,24 64,16 84,18 104,10 112,12", "#FFFFFF"), "stat-dark"),
        ("Propostas pendentes", str(int(pending_props)), "aguardam revisão", _spark("4,14 24,18 44,15 64,22 84,20 104,24 112,22", "#FFFFFF"), "stat-primary"),
        ("Bloqueios", str(int(fails)), "checks falhando" if fails else "nada bloqueando", _spark("4,20 24,20 44,21 64,19 84,20 104,20 112,20" if not fails else "4,24 24,22 44,26 64,14 84,18 104,10 112,12", "#FFFFFF"), "stat-dark"),
    ]
    out = []
    for i, (t, v, sub, spark, variant) in enumerate(cards, 1):
        out.append(
            f'<div class="stat {variant} anim anim-{i}"><div class="stat-h"><span>{t}</span>'
            f'<span class="stat-chip">{sub}</span></div>'
            f'<div class="stat-v num">{v}</div>'
            f'<div class="stat-f">{spark}</div></div>'
        )
    return f'<div class="stats">{"".join(out)}</div>'


def layout(page: str, body: str, slug: str = "", productions=None, status=None, history=None) -> str:
    prods = list(productions) if productions else []
    st = status or {}
    stage = str(st.get("stage", "") or "")
    state = str(st.get("state", "") or "")
    title = str(st.get("title", "") or "")
    blocked = bool(st.get("blocked", False))
    # Historico p/ painel contextual: prefere arg explícito, senão `status["history"]`.
    hist = list(history) if history is not None else list(st.get("history", []) or [])

    if page not in {p for p, _ in NAV}:
        page = "production" if not slug else page

    nav_links = "".join(
        f'<a class="nav-link{" active" if p == page else ""}" aria-current="{"page" if p == page else "false"}"'
        f' href="/?page={p}{("&slug=" + _q(slug)) if slug else ""}">{_icon(p)}<span>{_e(label)}</span></a>'
        for p, label in NAV)

    if prods:
        prod_links = "".join(
            f'<a class="prod-link{" active" if p.get("slug") == slug else ""}"'
            f' href="/?page={page}&slug={_q(p.get("slug", ""))}"'
            f' title="{_e(p.get("title", ""))}">{_e(p.get("slug", ""))}</a>'
            for p in prods[:20]
        )
    else:
        prod_links = '<span class="muted">Nenhuma produção</span>'

    if prods:
        options = "".join(
            f'<option value="{_e(p.get("slug", ""))}"{" selected" if p.get("slug") == slug else ""}>'
            f'{_e(p.get("slug", ""))}</option>'
            for p in prods
        )
        selector_inner = (
            '<form class="prod-switch" method="get" action="/">'
            f'<input type="hidden" name="page" value="{_e(page)}">'
            '<label class="muted" for="slug-sel">Produção</label>'
            f'<select id="slug-sel" name="slug">{options}</select>'
            '<button class="btn btn-ghost" type="submit">Trocar</button>'
            "</form>"
        )
        top_search = (
            '<div class="top-right">'
            '<input type="search" class="top-search" placeholder="Buscar…" aria-label="Buscar">'
            '<span class="avatar" title="showrunner">SR</span>'
            "</div>"
        )
        prod_selector = f'<div class="top-sel">{selector_inner}</div>'
    else:
        top_search = '<span class="avatar" title="showrunner">SR</span>'
        prod_selector = '<span class="muted">Nenhuma produção cadastrada</span>'

    crumb_label = dict(NAV).get(page, page)
    ctx = f" ctx-{page}" if page in ("gates", "sync", "master", "release", "cutlist") else ""
    if slug:
        crumb = (
            f'<nav class="crumb muted" aria-label="breadcrumb">Cuts Studio <span>/</span> {_e(crumb_label)} '
            f"<span>/</span> <strong>{_e(slug)}</strong>{(' <span>—</span> ' + _e(stage)) if stage else ''}</nav>"
        )
        prod_info = (
            f'<div class="prod-id"><strong>{_e(title or slug)}</strong>'
            f'<span class="muted mono">{_e(slug)}</span></div>'
            '<div class="top-badges">'
            + (f'<span class="badge badge-info">Fase: {_e(stage)}</span>' if stage else "")
            + (f'<span class="badge badge-muted">Estado: {_e(state)}</span>' if state else "")
            + ('<span class="badge badge-fail">Bloqueado</span>' if blocked
               else '<span class="badge badge-ok">Liberado</span>')
            + "</div>"
        )
    else:
        crumb = (
            f'<nav class="crumb muted" aria-label="breadcrumb">Cuts Studio <span>/</span> {_e(crumb_label)}</nav>'
        )
        prod_info = (
            '<div class="prod-id"><strong>Nenhuma produção selecionada</strong>'
            '<span class="muted">Escolha uma produção no seletor ou na lista.</span></div>'
        )
    # Painel contextual (right-sidebar 280px): reativa _activity_feed (antes código morto).
    try:
        feed_html = _activity_feed(hist[-8:] if hist else [])
    except Exception:
        feed_html = '<p class="empty">Sem atividade registrada.</p>'
    if slug:
        _ctx_badge = '<span class="badge badge-fail">Bloqueado</span>' if blocked else '<span class="badge badge-ok">Liberado</span>'
        ctx_meta = (
            '<div class="ctx-meta">'
            f"<div><span class='muted'>Fase</span><br><strong>{_e(stage or '—')}</strong></div>"
            f"<div><span class='muted'>Estado</span><br><strong>{_e(state or '—')}</strong></div>"
            f"<div>{_ctx_badge}</div>"
            "</div>"
        )
    else:
        ctx_meta = '<p class="muted">Selecione uma produção para ver o contexto.</p>'
    context_panel = (
        '<aside class="context-panel" aria-label="Painel contextual">'
        '<div class="ctx-card"><h3>Resumo</h3>'
        f"{ctx_meta}</div>"
        '<div class="ctx-card"><h3>Atividade recente</h3>'
        f"{feed_html}</div>"
        "</aside>"
    )

    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cuts Studio — {_e(page)}</title>
<style>
/* SnowUI DARK real — docs/SNOWUI-DARK-TOKENS.md (page bg #333333). */
:root{{color-scheme:dark;--bg:#333333;--sidebar:#333333;
--card:rgba(255,255,255,0.04);--elev:rgba(255,255,255,0.1);--border:rgba(255,255,255,0.15);
--border-soft:rgba(255,255,255,0.08);
--faint:rgba(255,255,255,0.2);--text:#FFFFFF;
--muted:rgba(255,255,255,0.4);--accent:#0A84FF;--accent-soft:rgba(255,255,255,0.1);--ok:#30D158;
--fail:#FF453A;--warn:#FF9F0A;--gate:#BF5AF2;--teal:#63E6E2;--pastel-a:#EDEEFC;--pastel-b:#E6F1FD;--ink:#000000;
--dur-fast:150ms;--dur-base:250ms;--dur-slow:400ms;--dur-chart:800ms;
--ease-out:cubic-bezier(0,0,0.2,1);--ease-spring:cubic-bezier(0.34,1.56,0.64,1)}}
*{{box-sizing:border-box}}body{{margin:0;background:#333333;background:var(--bg);color:var(--text);
font-family:Inter,system-ui,-apple-system,"Segoe UI",Roboto,Ubuntu,sans-serif;font-size:14px;line-height:20px;
font-feature-settings:"ss01" 1,"cv01" 1,"tnum" 1}}.num,.mono,td,.stat-v{{font-variant-numeric:tabular-nums}}
a{{color:var(--accent);text-decoration:none}}a:hover{{text-decoration:underline}}
img,svg{{max-width:100%}}
.app{{display:flex;min-height:100vh;border-radius:24px;overflow:hidden;max-width:100%}}
.sidebar{{width:220px;flex-shrink:0;background:var(--sidebar);border-right:1px solid var(--border-soft);
padding:16px;display:flex;flex-direction:column;gap:8px;position:sticky;top:0;height:100vh;overflow:auto;
transition:width var(--dur-base) var(--ease-out),transform var(--dur-base) var(--ease-out)}}
.logo{{font-size:18px;font-weight:800;letter-spacing:.2px;display:flex;align-items:center;gap:8px}}
.logo-mark{{width:28px;height:28px;border-radius:8px;background:#0A84FF;
display:inline-flex;align-items:center;justify-content:center;color:#fff;font-size:15px}}
.logo span{{color:var(--accent)}}
.logo-sub{{color:var(--muted);font-size:12px;line-height:16px;margin-top:2px}}
.nav{{display:flex;flex-direction:column;gap:8px}}
.nav-title{{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.08em;margin:4px 6px}}
.nav-link{{display:flex;align-items:center;gap:12px;min-height:48px;width:100%;padding:12px;border-radius:16px;
color:var(--text);border:1px solid transparent;transition:background var(--dur-base) var(--ease-out),border-color var(--dur-base) var(--ease-out),transform var(--dur-fast) var(--ease-out)}}
.nav-link .ic{{flex-shrink:0;width:24px;height:24px;border-radius:8px;background:var(--pastel-a);color:#000;
padding:4px;opacity:1}}
.nav a:nth-child(even) .ic,.nav-link:nth-child(even) .ic{{background:var(--pastel-b)}}
.nav-link:hover{{background:var(--elev);text-decoration:none;transform:translateX(2px)}}
.nav-link.active{{background:rgba(255,255,255,0.1);background:var(--accent-soft);border-color:transparent;font-weight:700}}
.side-block{{border-top:1px solid var(--border-soft);padding-top:12px;display:flex;flex-direction:column;gap:8px}}
.prod-link{{display:block;padding:5px 8px;border-radius:6px;color:var(--muted);
white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.prod-link:hover{{color:var(--text);background:var(--elev);text-decoration:none}}
.prod-link.active{{color:var(--text);background:var(--elev);font-weight:700}}
.side-hint{{color:var(--muted);font-size:12px;line-height:16px;overflow-wrap:anywhere;word-break:break-word}}.side-hint code{{color:var(--text)}}
.brand-foot{{margin-top:auto;padding:10px 6px;font-size:12px;line-height:16px;color:var(--muted)}}
.brand-foot strong{{color:var(--muted);font-weight:600}}
.main{{flex:1;min-width:0;display:flex;flex-direction:column;max-width:100%}}
.topbar{{display:flex;flex-direction:column;justify-content:center;gap:10px;
padding:16px 28px;border-bottom:1px solid var(--border-soft);background:var(--sidebar);min-height:68px}}
.topbar-row-1{{display:flex;justify-content:space-between;align-items:center;gap:24px;flex-wrap:wrap}}
.topbar-row-2{{display:flex;justify-content:space-between;align-items:flex-end;gap:24px;flex-wrap:wrap}}
.topbar>div,.topbar-row-1>div,.topbar-row-2>div{{min-width:0;max-width:100%}}
.prod-id-wrap{{display:flex;flex-direction:column;gap:6px;min-width:0;flex:1 1 280px}}
.crumb{{font-size:12px;line-height:16px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:100%}}.crumb span{{opacity:.5;margin:0 4px}}.crumb strong{{color:var(--text)}}
.prod-id{{display:flex;flex-direction:column;gap:2px;min-width:0;max-width:100%}}
.prod-id strong{{font-size:18px;font-weight:600;line-height:24px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:100%}}.mono{{font-family:ui-monospace,Consolas,monospace;font-size:12px}}
.top-badges{{display:flex;gap:6px;margin-top:6px;flex-wrap:wrap;max-width:100%}}
.top-right{{display:flex;align-items:center;gap:12px;flex-wrap:wrap;min-width:0;max-width:100%}}
.top-sel{{min-width:0;max-width:100%}}
.top-sel .prod-switch{{display:flex;align-items:center;gap:8px;flex-wrap:wrap;min-width:0;max-width:100%}}
.avatar{{width:32px;height:32px;border-radius:80px;background:rgba(255,255,255,0.1);
display:inline-flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;color:var(--text);flex-shrink:0}}
.avatar-sm{{width:24px;height:24px;font-size:10px}}
.cell-id{{display:flex;align-items:center;gap:8px;min-height:28px;min-width:0}}
.cell-id a{{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}}
.top-search{{width:160px;max-width:100%;flex:1 1 120px;min-width:0;height:28px;background:rgba(255,255,255,0.1);backdrop-filter:blur(10px);
-webkit-backdrop-filter:blur(10px);border:1px solid var(--border-soft);color:var(--text);border-radius:16px;padding:4px 12px;font-size:12px}}
.top-search::placeholder{{color:var(--muted)}}
.top-search:focus{{outline:2px solid var(--accent);outline-offset:1px;border-color:var(--accent)}}
.content{{padding:28px;width:100%;margin:0;flex:1 1 auto;min-width:0;box-sizing:border-box;
display:flex;flex-direction:column;gap:24px;max-width:1440px}}
.workspace{{display:flex;gap:24px;align-items:flex-start;width:100%;max-width:1440px;margin:0 auto;padding:28px;box-sizing:border-box;min-width:0}}
.workspace .content{{padding:0;max-width:none;margin:0}}
.context-panel{{width:280px;flex-shrink:0;display:flex;flex-direction:column;gap:16px;position:sticky;top:16px;max-height:calc(100vh - 32px);overflow:auto;min-width:0}}
.ctx-card{{background:var(--card);border:0;border-radius:24px;padding:20px;display:flex;flex-direction:column;gap:12px;min-width:0}}
.ctx-card h3{{margin:0;font-size:14px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}}
.ctx-meta{{display:flex;flex-direction:column;gap:8px;font-size:13px;color:var(--muted)}}
.ctx-meta strong{{color:var(--text)}}
.card{{background:rgba(255,255,255,0.04);background:var(--card);border:0;border-radius:24px;position:relative;
padding:24px;margin-bottom:0;display:flex;flex-direction:column;gap:16px;box-shadow:0 0.5px 1px rgba(0,0,0,0.1);
transition:transform var(--dur-base) var(--ease-out),box-shadow var(--dur-base) var(--ease-out),border-color var(--dur-base) var(--ease-out);min-width:0;max-width:100%;overflow:hidden;will-change:transform}}
@media(hover:hover){{.card:hover{{transform:translateY(-2px);box-shadow:0 12px 32px rgba(0,0,0,.3),0 2px 8px rgba(0,0,0,.2)}}}}
.card:active{{transform:translateY(0) scale(0.995)}}
.card h2,.card h3{{margin:0 0 10px;overflow-wrap:anywhere}}.card h2{{font-size:18px;font-weight:600;line-height:24px}}
.card h3{{font-size:14px;font-weight:600;color:var(--muted);
text-transform:uppercase;letter-spacing:.04em}}
.ctx-gates .card h2{{color:#BF5AF2}}.ctx-sync .card h2{{color:#0A84FF}}.ctx-master .card h2{{color:#30D158}}
.ctx-release .card h2{{color:#FF453A}}.ctx-cutlist .card h2{{color:#63E6E2}}
.ctx-gates .card::before{{background:#BF5AF2}}.ctx-sync .card::before{{background:#0A84FF}}.ctx-master .card::before{{background:#30D158}}
.ctx-release .card::before{{background:#FF453A}}.ctx-cutlist .card::before{{background:#63E6E2}}
.ctx-gates .card::before,.ctx-sync .card::before,.ctx-master .card::before,.ctx-release .card::before,.ctx-cutlist .card::before{{
content:'';position:absolute;left:0;top:20px;bottom:20px;width:3px;border-radius:0 3px 3px 0;opacity:.8}}
.muted{{color:var(--muted)}}.faint{{color:var(--faint)}}
.stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;max-width:100%}}
.stat{{border-radius:24px;padding:16px 20px;min-height:100px;min-width:0;max-width:100%;overflow:hidden;
display:flex;flex-direction:column;gap:8px;color:#FFFFFF;transition:transform var(--dur-base) var(--ease-out),box-shadow var(--dur-base) var(--ease-out);will-change:transform}}
.stat-primary{{background:linear-gradient(180deg,rgba(255,255,255,0.05),rgba(255,255,255,0.4)),#0A84FF}}
.stat-dark{{background:linear-gradient(180deg,rgba(255,255,255,0.05),rgba(255,255,255,0.2)),#000000}}
@media(hover:hover){{.stat:hover{{transform:translateY(-2px);box-shadow:0 12px 32px rgba(0,0,0,.3),0 2px 8px rgba(0,0,0,.2)}}}}
.stat:active{{transform:translateY(0) scale(0.995)}}
.stat-h{{display:flex;justify-content:space-between;align-items:center;gap:8px;min-width:0;
font-size:16px;line-height:22px;font-weight:400;color:#FFFFFF}}
.stat-h>span:first-child{{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}}
.stat-chip{{display:inline-flex;align-items:center;min-height:24px;padding:2px 10px;border-radius:80px;flex-shrink:0;max-width:100%;
background:rgba(255,255,255,0.2);color:#FFFFFF;font-size:12px;line-height:16px;font-weight:400;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.stat-v{{font-size:24px;font-weight:600;line-height:32px;color:#FFFFFF;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.stat-f{{display:flex;justify-content:flex-end;align-items:end;gap:8px;min-width:0;overflow:hidden}}
.spark{{opacity:.9;max-width:100%;height:auto}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:16px;max-width:100%}}
.stepper{{list-style:none;margin:0;padding:0 0 4px;display:flex;gap:8px;overflow-x:auto;-webkit-overflow-scrolling:touch;scrollbar-width:thin;max-width:100%}}
.step{{flex:1 0 96px;min-width:96px;max-width:180px;background:rgba(255,255,255,0.04);border:0;border-radius:12px;padding:10px;display:flex;flex-direction:column;gap:4px;min-width:0;
transition:background var(--dur-base) var(--ease-out),transform var(--dur-fast) var(--ease-out)}}
.step .dot{{width:24px;height:24px;border-radius:999px;display:inline-flex;align-items:center;justify-content:center;
font-size:12px;font-weight:700;background:rgba(255,255,255,0.1);color:var(--text);flex-shrink:0}}
.step.done .dot{{background:rgba(113,221,140,.25);color:#fff}}
.step.cur{{outline:1px solid var(--border-soft)}}.step.cur .dot{{background:var(--accent);color:#fff;animation:dotPulse 2s var(--ease-out) infinite}}
@keyframes dotPulse{{0%,100%{{box-shadow:0 0 0 0 rgba(10,132,255,0.4)}}50%{{box-shadow:0 0 0 6px rgba(10,132,255,0)}}}}
.step-t{{font-size:12px;line-height:16px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:100%}}.step-id{{font-size:11px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.donut-row{{display:flex;gap:24px;align-items:center;flex-wrap:wrap;max-width:100%}}
.donut-side{{flex:1 1 240px;min-width:0;max-width:100%}}
.donut-wrap{{position:relative;width:120px;height:120px;flex-shrink:0;animation:donutPulse 2.4s var(--ease-out) infinite}}
.donut-fg{{transition:stroke-dashoffset var(--dur-chart) var(--ease-out);animation:donutIn var(--dur-chart) var(--ease-out)}}
@keyframes donutIn{{from{{stroke-dashoffset:213.6}}}}
@keyframes donutPulse{{0%,100%{{filter:drop-shadow(0 0 0 rgba(10,132,255,0))}}50%{{filter:drop-shadow(0 0 8px rgba(10,132,255,0.3))}}}}
.donut-c{{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:0}}
.donut-c strong{{font-size:20px}}.donut-c span{{font-size:12px;line-height:16px}}
.chart-line{{border-top:1px dashed #A0BCE8}}
.bar{{height:28px;border-radius:8px}}
.table-wrap{{overflow-x:auto;-webkit-overflow-scrolling:touch;border-radius:16px;max-width:100%;margin-top:12px}}
.table-wrap table{{min-width:560px}}
table{{border-collapse:separate;border-spacing:0;width:100%;font-size:14px;line-height:20px;
border-radius:16px;overflow:hidden;max-width:100%}}
thead th{{color:var(--muted);font-weight:400;font-size:12px;line-height:16px;letter-spacing:.02em;
padding:12px 16px;text-align:left;height:40px;vertical-align:middle;border-bottom:1px solid var(--border-soft)}}
tbody td{{padding:12px 16px;height:52px;text-align:left;vertical-align:middle;
font-size:14px;font-weight:400;border-bottom:1px solid var(--border-soft);overflow-wrap:break-word}}
td .badge,td code{{flex-shrink:0}}
tbody tr:last-child td{{border-bottom:0}}
tbody tr{{transition:background var(--dur-fast) ease-out,transform var(--dur-fast) var(--ease-out)}}tbody tr:nth-child(even){{background:rgba(255,255,255,0.03)}}
tbody tr:hover{{background:rgba(255,255,255,0.08);transform:translateX(2px)}}
.badge{{display:inline-flex;align-items:center;gap:6px;min-height:28px;padding:4px 12px;border-radius:80px;
font-size:14px;line-height:20px;font-weight:400;border:0.5px solid transparent;white-space:nowrap}}
.badge-ok{{background:rgba(48,209,88,0.1);border-color:rgba(48,209,88,0.2);color:#30D158}}
.badge-fail{{background:rgba(255,69,58,0.1);border-color:rgba(255,69,58,0.2);color:#FF453A}}
.badge-warn{{background:rgba(255,159,10,0.1);border-color:rgba(255,159,10,0.2);color:#FF9F0A}}
.badge-info{{background:rgba(10,132,255,0.1);border-color:rgba(10,132,255,0.2);color:#0A84FF}}
.badge-gate{{background:rgba(191,90,242,0.1);border-color:rgba(191,90,242,0.2);color:#BF5AF2}}
.badge-muted{{background:rgba(255,255,255,0.1);border-color:rgba(255,255,255,0.2);color:var(--muted)}}
.ok{{color:var(--ok)}}.bad{{color:var(--fail)}}
pre{{background:rgba(255,255,255,0.04);border:0;border-radius:8px;padding:12px;max-width:100%;
overflow:auto;color:var(--text);font-size:12px;line-height:16px;white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word}}
code{{background:rgba(255,255,255,0.1);border:0;border-radius:6px;padding:1px 6px;font-size:12px;overflow-wrap:anywhere}}
kbd{{border:1px solid rgba(255,255,255,0.15);border-radius:6px;padding:1px 6px;font-size:12px;font-family:inherit}}
.tooltip{{background:rgba(255,255,255,0.8);color:#000000;border:0;
border-radius:80px;padding:4px 12px;font-size:12px;line-height:16px;max-width:100%}}
.btn{{display:inline-flex;align-items:center;justify-content:center;gap:6px;min-height:36px;padding:4px 12px;border-radius:12px;border:1px solid var(--border);
background:var(--elev);color:var(--text);cursor:pointer;font-weight:600;font-size:13px;text-decoration:none;white-space:nowrap;
transition:transform var(--dur-fast) var(--ease-out),filter var(--dur-fast) var(--ease-out),box-shadow var(--dur-fast) var(--ease-out)}}
.btn:hover{{transform:translateY(-1px);filter:brightness(1.1);box-shadow:0 2px 8px rgba(0,0,0,0.25);text-decoration:none}}
.btn:active{{transform:translateY(0);filter:brightness(0.95)}}
.btn-primary:hover{{box-shadow:0 4px 12px rgba(10,132,255,0.35)}}
.btn:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible{{outline:2px solid var(--accent);outline-offset:2px}}
.btn-primary{{background:var(--accent);border-color:var(--accent);color:#fff}}
.btn-success{{background:#30D158;border-color:#30D158;color:#fff}}
.btn-danger{{background:rgba(255,107,107,.2);border-color:var(--fail);color:#ffe3e3}}
.btn-ghost{{background:transparent}}
.btn-sm{{padding:4px 8px;font-size:12px;border-radius:8px;min-height:28px}}
.btn:disabled{{opacity:.5;cursor:not-allowed}}
form.inline{{display:inline}}form.stack{{display:flex;gap:8px;flex-wrap:wrap;align-items:end;max-width:100%}}
label.f{{display:flex;flex-direction:column;gap:4px;font-size:12px;color:var(--muted);flex:1 1 180px;min-width:0;max-width:100%}}
input[type=text],select,textarea{{background:rgba(255,255,255,0.1);border:1px solid var(--border-soft);color:var(--text);
border-radius:12px;padding:8px 10px;font-size:13px;min-width:0;max-width:100%;width:100%;box-sizing:border-box;font-family:inherit}}
select option{{background:#2a2a2a;color:#FFFFFF}}
input[type=text]:focus,select:focus,textarea:focus{{border-color:var(--accent);outline:2px solid var(--accent);outline-offset:1px}}
input[type=search]:not(.top-search){{background:rgba(255,255,255,0.1);backdrop-filter:blur(10px);
-webkit-backdrop-filter:blur(10px);border:1px solid var(--border-soft);color:var(--text);border-radius:16px;padding:6px 12px;font-size:13px;min-width:0;max-width:100%;flex:1 1 160px}}
.actions{{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px;max-width:100%}}
.empty{{color:var(--muted);padding:8px 0}}
.missing{{border-radius:8px;color:var(--muted);border:1px dashed var(--border-soft);
background:linear-gradient(90deg,rgba(255,255,255,0.03) 25%,rgba(255,255,255,0.09) 50%,rgba(255,255,255,0.03) 75%);
background-size:200% 100%;animation:shimmer 1.6s var(--ease-out) infinite}}
@keyframes shimmer{{from{{background-position:200% 0}}to{{background-position:-200% 0}}}}
.feed{{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:0;max-width:100%}}
.feed li{{display:flex;gap:10px;padding:10px 2px;border-bottom:1px solid var(--border-soft);font-size:13px;min-width:0}}
.feed li>div{{min-width:0;flex:1;overflow-wrap:anywhere;word-break:break-word}}
.feed .fdot{{width:8px;height:8px;border-radius:999px;background:#A0BCE8;margin-top:6px;flex-shrink:0}}
.feed time{{color:var(--muted);font-size:12px;overflow-wrap:anywhere}}
.feed .badge{{margin-bottom:4px}}
.anim{{opacity:0;animation:fadeSlideIn var(--dur-base) var(--ease-out) forwards}}
.anim-1{{animation-delay:0ms}}.anim-2{{animation-delay:60ms}}.anim-3{{animation-delay:120ms}}
.anim-4{{animation-delay:180ms}}.anim-5{{animation-delay:240ms}}.anim-6{{animation-delay:300ms}}
@keyframes fadeSlideIn{{from{{opacity:0;transform:translateY(12px) scale(0.99)}}to{{opacity:1;transform:none}}}}
.filterbar{{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:10px;max-width:100%}}
.filterbar .muted{{flex-shrink:0}}
@media(min-width:1441px){{.workspace{{max-width:1600px;margin:0 auto}}}}
@media(max-width:1280px){{.context-panel{{display:none}}.workspace{{max-width:100%}}.content{{max-width:100%}}}}
@media(max-width:1100px){{.stats{{grid-template-columns:1fr 1fr}}.topbar{{gap:10px}}.workspace{{gap:16px}}}}
@media(max-width:960px){{.app{{flex-direction:column}}.sidebar{{width:auto;height:auto;position:static;max-height:none;border-right:0;border-bottom:1px solid var(--border-soft)}}
.grid2{{grid-template-columns:1fr}}.topbar{{align-items:flex-start;gap:12px;padding:16px}}.workspace{{flex-direction:column;padding:16px}}.content{{padding:0;max-width:none}}.stats{{grid-template-columns:1fr 1fr}}.stat{{max-width:none}}.donut-row{{gap:16px}}
.stepper{{flex-direction:column;overflow-x:visible}}.step{{min-width:auto;max-width:none;flex:none}}.topbar-row-1,.topbar-row-2{{flex-direction:column;align-items:stretch;gap:8px}}}}
@media(max-width:640px){{body{{font-size:13px}}.sidebar{{padding:12px}}.nav-link{{min-height:44px;padding:10px}}.topbar{{padding:12px 16px}}
.top-right{{width:100%}}.top-sel,.top-sel .prod-switch{{width:100%}}.top-sel select{{flex:1}}.top-search{{width:100%;flex:1 1 100%}}
.workspace{{padding:12px 16px}}.content{{gap:16px}}.card{{padding:16px;border-radius:16px}}.stats{{grid-template-columns:1fr;gap:12px}}
form.stack{{flex-direction:column;align-items:stretch}}label.f{{flex:1 1 100%}}.donut-row{{flex-direction:column;align-items:flex-start}}
.donut-side{{flex:1 1 100%;width:100%}}th,td{{padding:8px 12px}}.filterbar{{align-items:stretch;flex-direction:column}}.filterbar input{{width:100%}}}}
@media(max-width:400px){{.stat-v{{font-size:20px;line-height:28px}}.card h2{{font-size:16px}}.btn:not(.btn-sm){{width:100%}}.table-wrap table{{min-width:520px}}}}
@media(prefers-reduced-motion:reduce){{*,*::before,*::after{{animation-duration:0.01ms !important;animation-iteration-count:1 !important;transition-duration:0.01ms !important}}.anim{{opacity:1}}}}
</style>
</head><body><div class="app">
<aside class="sidebar">
<div><div class="logo"><span class="logo-mark">✂</span><span>Cuts <span>Studio</span></span></div><div class="logo-sub">Painel local · YouTube escuro</div></div>
<div><div class="nav-title">Navegação</div><nav class="nav">{nav_links}</nav></div>
<div class="side-block"><div class="nav-title">Produções</div>{prod_links}</div>
<div class="side-block side-hint">CLI: <code>python -m cstudio new --title "..."</code><br>API: <code>GET /health</code> · <code>GET /api/status</code></div>
<div class="brand-foot"><strong>Cuts Studio</strong> · SnowUI dark #333333</div>
</aside>
<div class="main"><header class="topbar">
<div class="topbar-row-1"><div>{crumb}</div><div>{top_search}</div></div>
<div class="topbar-row-2"><div class="prod-id-wrap">{prod_info}</div><div>{prod_selector}</div></div>
</header>
<div class="workspace"><main class="content{ctx}">{body}</main>{context_panel}</div></div>
</div></body></html>"""


def _checks_table(checks) -> str:
    out = []
    badge_ok = '<span class="badge badge-ok">OK</span>'
    badge_fail = '<span class="badge badge-fail">FAIL</span>'
    for c in checks:
        badge = badge_ok if c.get('ok') else badge_fail
        label = _e(c.get('label', ''))
        detail = _e(c.get('detail', ''))
        out.append(f'<tr><td>{badge}</td><td>{label}</td><td class="muted">{detail}</td></tr>')
    rows = ''.join(out)
    return f'<div class="table-wrap"><table><thead><tr><th>Status</th><th>Verificação</th><th>Detalhe</th></tr></thead><tbody>{rows}</tbody></table></div>'


def _gates_table(gates, slug: str) -> str:
    rows = []
    for g in gates:
        approved = bool(g.get("approved"))
        badge = '<span class="badge badge-ok">Aprovado</span>' if approved else '<span class="badge badge-warn">Pendente</span>'
        if approved:
            action = '<span class="muted">—</span>'
        else:
            action = (
                f'<form class="inline" method="post" action="/action/approve">'
                f'<input type="hidden" name="slug" value="{_e(slug)}">'
                f'<input type="hidden" name="gate" value="{_e(g.get("gate", ""))}">'
                f'<button class="btn btn-sm btn-success" type="submit">Aprovar</button>'
                f'</form>'
            )
        rows.append(
            f"<tr><td><span class=\"badge badge-gate\">{_e(g.get('gate', ''))}</span></td><td>{_e(g.get('stage', ''))}</td>"
            f"<td>{badge}</td><td class=\"muted\">{_e(g.get('detail', ''))}</td><td>{action}</td></tr>")
    return ("<div class=\"table-wrap\"><table><thead><tr><th>Gate</th><th>Fase</th><th>Situação</th>"
            "<th>Detalhe</th><th>Ação</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table></div>")


def _proposals_table(props, slug: str) -> str:
    if not props:
        return '<p class="empty">Nenhuma proposta encontrada para esta produção.</p>'
    rows = []
    for p in props:
        pid = str(p.get("id", ""))
        stt = str(p.get("status", ""))
        if stt == "applied":
            badge = '<span class="badge badge-ok">Aplicada</span>'
        elif stt == "discarded":
            badge = '<span class="badge badge-muted">Descartada</span>'
        elif stt == "pending":
            badge = '<span class="badge badge-warn">Pendente</span>'
        else:
            badge = f'<span class="badge badge-info">{_e(stt)}</span>'
        if stt == "pending":
            action = (
                f'<form class="inline" method="post" action="/action/apply-proposal">'
                f'<input type="hidden" name="slug" value="{_e(slug)}">'
                f'<input type="hidden" name="id" value="{_e(pid)}">'
                f'<button class="btn btn-sm btn-primary" type="submit">Aplicar</button></form> '
                f'<form class="inline" method="post" action="/action/discard-proposal">'
                f'<input type="hidden" name="slug" value="{_e(slug)}">'
                f'<input type="hidden" name="id" value="{_e(pid)}">'
                f'<button class="btn btn-sm btn-danger" type="submit">Descartar</button></form>'
            )
        else:
            action = '<span class="muted">—</span>'
        rows.append(
            f"<tr><td><code>{_e(pid)}</code></td><td>{_e(p.get('runner', ''))}</td>"
            f"<td>{badge}</td><td title=\"{_e(p.get('summary', ''))}\">{_e(p.get('summary', '')[:120])}{'…' if len(str(p.get('summary', ''))) > 120 else ''}</td><td>{action}</td></tr>")
    return ("<div class=\"table-wrap\"><table><thead><tr><th>ID</th><th>Runner</th><th>Situação</th>"
            "<th>Resumo</th><th>Ações</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table></div>")


def _feed_badge(ev: str) -> str:
    """Chip Tela 2 para um evento do historico (OK/FAIL/pending/info/gate)."""
    e = ev.lower()
    if any(k in e for k in ("approv", "aplica", "appl", "conclu", "advanc", "ok", "avan")):
        return '<span class="badge badge-ok">OK</span>'
    if any(k in e for k in ("fail", "falh", "bloque", "block", "error", "erro", "discard", "descart", "neg")):
        return '<span class="badge badge-fail">FAIL</span>'
    if "pend" in e:
        return '<span class="badge badge-warn">Pendente</span>'
    if "gate" in e:
        return '<span class="badge badge-gate">Gate</span>'
    if "propos" in e:
        return '<span class="badge badge-gate">Proposta</span>'
    return '<span class="badge badge-info">Info</span>'


def _activity_feed(history) -> str:
    if not history:
        return '<p class="empty">Sem atividade registrada.</p>'
    items = []
    for h in reversed(list(history or [])):
        ev = _e(h.get("event", "—"))
        at = _e(h.get("at", ""))
        extra = []
        for k in ("gate", "by", "to", "from", "proposal_id", "reason"):
            if h.get(k):
                extra.append(f"{k}={_e(h.get(k))}")
        det = (" · " + " ".join(extra)) if extra else ""
        badge = _feed_badge(str(h.get("event", "")))
        items.append(f'<li><span class="fdot"></span><div>{badge}<div>{ev}{det}</div><time class="mono">{at}</time></div></li>')
    return f'<ul class="feed">{"".join(items)}</ul>'


def _cutlist_js() -> str:
    # Filtro client-side (<30 linhas).
    return (
        "<script>(function(){var i=document.getElementById('cutfilter'),"
        "t=document.getElementById('cuttable');if(!i||!t)return;"
        "i.addEventListener('input',function(){var q=i.value.toLowerCase(),"
        "rs=t.tBodies[0].rows,n=0;for(var k=0;k<rs.length;k++){"
        "var hit=rs[k].textContent.toLowerCase().indexOf(q)>=0;"
        "rs[k].style.display=hit?'':'none';if(hit)n++;}"
        "document.getElementById('cutcount').textContent=n+' linhas';});})();</script>"
    )


def _cutlist_table(csv_text: str) -> str:
    import csv as _csv
    import io as _io
    try:
        rows = list(_csv.DictReader(_io.StringIO(csv_text)))
    except Exception:
        return f"<pre>{_e(csv_text[:8000])}</pre>"
    if not rows:
        return '<p class="empty missing">Cutlist vazia ou ilegível.</p>'
    cols = list(rows[0].keys())
    head = "".join(f"<th>{_e(c)}</th>" for c in cols)
    body = "".join(
        "<tr>" + "".join(f"<td>{_e(r.get(c, ''))}</td>" for c in cols) + "</tr>"
        for r in rows[:500]
    )
    return (
        '<div class="filterbar"><label class="muted" for="cutfilter">Filtrar</label>'
        '<input type="search" id="cutfilter" placeholder="ex.: cut_id, fonte, tc…">'
        f'<span class="muted" id="cutcount">{len(rows)} linhas</span></div>'
        f'<div class="table-wrap"><table id="cuttable"><thead><tr>{head}</tr></thead>'
        f"<tbody>{body}</tbody></table></div>"
    )


def render(root: str, page: str, slug: str = "") -> str:
    prods = []
    try:
        prods = C.list_productions(root)
    except Exception:
        prods = []

    def _hist_for(s: str):
        try:
            _, _proj = C.load_project(root, s)
            return list((_proj or {}).get("history", []) or [])
        except Exception:
            return []
    if page == "production":
        rows = "".join(
            f"<tr><td><span class=\"cell-id\"><span class=\"avatar avatar-sm\" aria-hidden=\"true\">"
            f"{_e((p['slug'][:2] or '··').upper())}</span>"
            f"<a href='/?page=gates&slug={_q(p['slug'])}'>{_e(p['slug'])}</a></span></td>"
            f"<td>{_e(p.get('title', ''))}</td><td>{_e(p.get('stage', ''))}</td>"
            f"<td>{_e(p.get('state', ''))}</td></tr>" for p in prods)
        body = (f"<section class='card anim anim-1'><h2>Produções</h2>"
                f"<p class='muted'>Uma produção ativa por vez. Clique no slug para abrir os gates.</p>"
                f"<div class=\"table-wrap\"><table><thead><tr><th>Slug</th><th>Título</th>"
                f"<th>Fase</th><th>Estado</th></tr></thead><tbody>{rows}</tbody></table></div>"
                f"<div class='actions'><span class='muted'>CLI: "
                f"<code>python -m cstudio new --title \"...\"</code></span></div></section>")
        try:
            _active = C.active_production(root)
        except Exception:
            _active = None
        if _active:
            _aslug = str(_active.get("slug", "") or "")
            _atitle = str(_active.get("title", "") or "")
            _life = (
                f"<p><span class='badge badge-warn'>Uma ativa por vez</span> "
                f"<span class='muted'>Já existe uma produção ativa (<strong>{_e(_aslug)}</strong>"
                f"{(' — ' + _e(_atitle)) if _atitle else ''}). "
                f"Pause ou abandone a atual antes de criar outra.</span></p>"
                f"<div class='actions'>"
                f"<form class='inline' method='post' action='/action/pause'>"
                f"<input type='hidden' name='slug' value='{_e(_aslug)}'>"
                f"<button class='btn btn-sm' type='submit'>Pausar</button></form> "
                f"<form class='inline' method='post' action='/action/resume'>"
                f"<input type='hidden' name='slug' value='{_e(_aslug)}'>"
                f"<button class='btn btn-sm' type='submit'>Retomar</button></form> "
                f"<form class='inline' method='post' action='/action/abandon'>"
                f"<input type='hidden' name='slug' value='{_e(_aslug)}'>"
                f"<label class='muted' style='font-size:12px;display:inline-flex;align-items:center;gap:6px;white-space:nowrap'><input type='checkbox' name='confirmo' value='on' required> confirmo</label> "
                f"<button class='btn btn-sm btn-danger' type='submit'>Abandonar</button></form>"
                f"</div>")
        else:
            _life = "<p class='muted'>Nenhuma produção ativa. Preencha e crie.</p>"
        body += (
            f"<section class='card anim anim-2'><h2>Nova produção</h2>"
            f"{_life}"
            f"<form class='stack' method='post' action='/action/new'>"
            f"<label class='f'>Título*<input type='text' name='title' required placeholder='Ex.: React do episódio 12'></label>"
            f"<label class='f'>Slug (opcional)<input type='text' name='slug' placeholder='auto a partir do título'></label>"
            f"<label class='f'>Source URL (opcional)<input type='text' name='source_url' placeholder='https://...'></label>"
            f"<button class='btn btn-primary' type='submit'>Criar produção</button></form>"
            f"<div class='actions'><form class='inline' method='post' action='/action/maintain'>"
            f"<button class='btn btn-sm btn-ghost' type='submit'>Preparar (maintain)</button></form>"
            f"<span class='muted'>Prepara o repositório sem terminal.</span></div></section>")
        if slug:
            try:
                st = C.workflow_status(root, slug)
                props = P.list_proposals(root, slug)
                pend = sum(1 for x in props if x.get("status") == "pending")
                ok_g = sum(1 for g in st["gates"] if g.get("approved"))
                body += (
                    f"<section class='card anim anim-2'><h3>Resumo — {_e(slug)}</h3>"
                    f"{_stat_cards(st, pend)}"
                    f"<div class='donut-row'>{_donut(ok_g, len(st['gates']) or 1)}"
                    f"<div class='donut-side'><h3>Pipeline</h3>{_stepper(root, st['stage'])}</div></div></section>")
            except Exception:
                pass
        return layout(page, body, slug, productions=prods, status=None, history=_hist_for(slug) if slug else [])
    if not slug:
        body = ("<section class='card anim anim-1'><h2>Selecione uma produção</h2>"
                "<p class='muted'>Use o seletor no topo ou abra a página "
                "<a href='/?page=production'>Produção</a> para escolher.</p></section>")
        return layout(page, body, slug, productions=prods, status=None, history=[])
    try:
        st = C.workflow_status(root, slug)
    except Exception as exc:
        return layout(page, f"<section class='card'><p class='bad'>{_e(exc)}</p></section>",
                      slug, productions=prods, status=None, history=_hist_for(slug))
    try:
        props_all = P.list_proposals(root, slug)
    except Exception:
        props_all = []
    pend_n = sum(1 for x in props_all if x.get("status") == "pending")
    ok_g = sum(1 for g in st["gates"] if g.get("approved"))
    stats_html = _stat_cards(st, pend_n)
    stepper_html = _stepper(root, st["stage"])
    if page == "gates":
        pending = [g for g in st["gates"] if not g.get("approved")]
        if pending:
            opts = "".join(
                f'<option value="{_e(g["gate"])}">{_e(g["gate"])} ({_e(g["stage"])})</option>'
                for g in pending)
            approve_box = (
                "<section class='card anim anim-4'><h3>Aprovar gate pendente</h3>"
                "<form class='stack' method='post' action='/action/approve'>"
                f"<input type='hidden' name='slug' value='{_e(slug)}'>"
                f"<label class='f'>Gate<select name='gate'>{opts}</select></label>"
                "<label class='f'>Responsável<input type='text' name='by' value='showrunner'></label>"
                "<label class='f'>Nota<input type='text' name='note' placeholder='opcional'></label>"
                "<button class='btn btn-success' type='submit'>Aprovar gate</button></form>"
                "<div class='actions'><form class='inline' method='post' action='/action/advance'>"
                f"<input type='hidden' name='slug' value='{_e(slug)}'>"
                "<button class='btn btn-primary' type='submit'>Avançar fase</button></form>"
                "<span class='muted'>Avanço exige checks + gates aprovados.</span></div></section>")
        else:
            approve_box = (
                "<section class='card anim anim-4'><h3>Avançar fase</h3>"
                "<p class='muted'>Todos os gates visíveis estão aprovados.</p>"
                "<form class='inline' method='post' action='/action/advance'>"
                f"<input type='hidden' name='slug' value='{_e(slug)}'>"
                "<button class='btn btn-primary' type='submit'>Avançar fase</button></form></section>")
        body = (f"<section class='card anim anim-1'><h2>{_e(slug)} — fase {_e(st['stage'])}</h2>"
                f"<p class='muted'>Estado: {_e(st['state'])} · "
                f"{'Bloqueado' if st['blocked'] else 'Liberado'}</p>"
                f"{stats_html}</section>"
                f"<section class='card anim anim-2'><h3>Pipeline (12 stages)</h3>{stepper_html}</section>"
                f"<section class='card anim anim-3'><h3>Gates</h3>"
                f"<div class='donut-row'>{_donut(ok_g, len(st['gates']) or 1)}"
                f"<div class='donut-side'>{_gates_table(st['gates'], slug)}</div></div></section>"
                f"{approve_box}"
                f"<section class='card anim anim-5'><h3>Verificações da fase</h3>{_checks_table(st['checks'])}</section>")
        return layout(page, body, slug, productions=prods, status=st, history=_hist_for(slug))
    if page == "proposals":
        props = props_all
        body = (f"<section class='card anim anim-1'><h2>Propostas — {_e(slug)}</h2>"
                f"<p class='muted'>Propostas pendentes exigem revisão humana antes de aplicar.</p>"
                f"{stats_html}"
                f"{_proposals_table(props, slug)}</section>"
                f"<section class='card anim anim-2'><h3>Aplicar / descartar por ID</h3>"
                f"<form class='stack' method='post' action='/action/apply-proposal'>"
                f"<input type='hidden' name='slug' value='{_e(slug)}'>"
                f"<label class='f'>ID da proposta<input type='text' name='id' placeholder='ex.: a1b2c3d4e5f6' required></label>"
                f"<button class='btn btn-primary' type='submit'>Aplicar</button></form>"
                f"<div class='actions'><form class='stack' method='post' action='/action/discard-proposal'>"
                f"<input type='hidden' name='slug' value='{_e(slug)}'>"
                f"<label class='f'>ID da proposta<input type='text' name='id' placeholder='ex.: a1b2c3d4e5f6' required></label>"
                f"<button class='btn btn-danger' type='submit'>Descartar</button></form></div>"
                f"<p class='muted'>Aplicar grava os arquivos validados; descartar marca como descartada.</p></section>"
                f"<section class='card anim anim-3'><h3>Pipeline</h3>{stepper_html}</section>")
        return layout(page, body, slug, productions=prods, status=st, history=_hist_for(slug))
    if page in ("cutlist", "sync", "graphics", "master", "release"):
        titles = {"cutlist": "Cutlist", "sync": "Sync", "graphics": "Gráficos",
                  "master": "Master", "release": "Release"}
        mapping = {"cutlist": ".studio/internal/cutlist/cutlist.csv",
                   "sync": ".studio/internal/sync/sync-report.json",
                   "graphics": ".studio/internal/graphics/overlays.csv",
                   "master": ".studio/internal/composition/master.json",
                   "release": ".studio/internal/release/metadata.json"}
        from .core import prod_path
        p = os.path.join(prod_path(root, slug), mapping[page])
        content = open(p, encoding="utf-8", errors="replace").read() if os.path.isfile(p) else "(arquivo ausente)"
        is_missing = not os.path.isfile(p)
        if page == "cutlist" and not is_missing:
            content_html = _cutlist_table(content)
            extra_js = _cutlist_js()
        else:
            cls = " class='missing'" if is_missing else ""
            content_html = f"<pre{cls}>{_e(content[:8000])}</pre>"
            extra_js = ""
        body = (f"<section class='card anim anim-1'><h2>{_e(titles.get(page, page))} — {_e(slug)}</h2>"
                f"<p class='muted'><code>{_e(mapping[page])}</code></p>"
                f"{stats_html}"
                f"{content_html}</section>"
                f"<section class='card anim anim-2'><h3>Pipeline</h3>{stepper_html}</section>"
                f"<section class='card anim anim-3'><h3>Verificações da fase</h3>{_checks_table(st['checks'])}</section>")
        html_out = layout(page, body, slug, productions=prods, status=st, history=_hist_for(slug))
        if extra_js:
            html_out = html_out.replace("</body>", extra_js + "</body>")
        return html_out
    # diagnostics
    try:
        _vdir, _proj = C.load_project(root, slug)
        hist = (_proj or {}).get("history", [])[-10:]
    except Exception:
        hist = []
    diag = {"stage": st["stage"], "state": st["state"], "blocked": st["blocked"],
            "gates": st["gates"], "history": hist}
    import json as _j
    body = (f"<section class='card anim anim-1'><h2>Diagnóstico — {_e(slug)}</h2>{stats_html}"
            f"<div class='donut-row'>{_donut(ok_g, len(st['gates']) or 1)}"
            f"<div class='donut-side'><h3>Atividade recente</h3>{_activity_feed(hist)}</div></div></section>"
            f"<section class='card anim anim-2'><h3>Pipeline</h3>{stepper_html}</section>"
            f"<section class='card anim anim-3'><h2>Estado bruto</h2>"
            f"<pre>{_e(_j.dumps(diag, ensure_ascii=False, indent=2))}</pre></section>"
            f"<section class='card anim anim-4'><h3>Verificações</h3>{_checks_table(st['checks'])}</section>")
    return layout(page, body, slug, productions=prods, status=st)
