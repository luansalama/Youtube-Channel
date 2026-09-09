from __future__ import annotations

import html
import importlib.util
import json
import platform
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .analytics import report_for_slug
from .assistant import MODEL_REASONING_PROFILES, REASONING_LEVELS, list_proposals, load_settings, reasoning_profile
from .runners import RUNNER_LABELS, runner_candidates, runner_status
from .core import (
    business_summary,
    list_projects,
    load_stages,
    read_csv_rows,
    time_summary,
    utc_now,
    validate_repository,
    workflow_status,
)
from .workspace import list_project_files, media_status, read_root_text, read_text_file

VERSION = "0.3.6"


def esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def url(value: str) -> str:
    return quote(value, safe="")


def form(action: str, label: str, fields: str = "", css: str = "primary", confirm: str = "") -> str:
    confirm_attr = f' data-confirm="{esc(confirm)}"' if confirm else ""
    return f'<form method="post" action="{esc(action)}" class="inline-form"{confirm_attr}>{fields}<button class="{esc(css)}" type="submit">{esc(label)}</button></form>'


def rows_table(headers: list[str], rows: list[list[Any]], empty: str) -> str:
    if not rows:
        return f'<p class="empty">{esc(empty)}</p>'
    head = "".join(f"<th>{esc(item)}</th>" for item in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell if isinstance(cell, SafeHTML) else esc(cell)}</td>" for cell in row) + "</tr>" for row in rows)
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


class SafeHTML(str):
    pass


def nav_link(page: str, current: str, label: str, badge: str = "") -> str:
    cls = "active" if current == page else ""
    badge_html = f'<span class="nav-badge">{esc(badge)}</span>' if badge else ""
    return f'<a class="{cls}" href="/?page={url(page)}">{esc(label)}{badge_html}</a>'


def phase_rail(stages: list[dict[str, Any]], current: str, state: str) -> str:
    names = [stage["name"] for stage in stages]
    index = names.index(current) if current in names else 0
    items = []
    for position, stage in enumerate(stages):
        cls = "done" if state == "completed" or position < index else "current" if position == index else "future"
        items.append(f'<a href="/?page=workspace" class="phase {cls}"><span>{position + 1}</span><strong>{esc(stage["label"])}</strong></a>')
    return '<div class="phase-rail">' + "".join(items) + "</div>"


CSS = r"""
:root{color-scheme:dark;--bg:#0e120d;--panel:#1b211a;--panel2:#232a21;--line:#394234;--text:#f3eddd;--muted:#aab1a1;--accent:#8bae66;--accent2:#628141;--warm:#ebd5ab;--danger:#d78b76;--ok:#9bc67c;--blue:#86a9c8}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.55 Inter,Segoe UI,Arial,sans-serif}a{color:var(--accent)}.shell{display:grid;grid-template-columns:235px minmax(0,1fr);min-height:100vh}.sidebar{position:sticky;top:0;height:100vh;padding:24px 16px;background:#141913;border-right:1px solid var(--line);overflow:auto}.brand{padding:0 10px 22px}.brand .kicker{font-size:10px;text-transform:uppercase;letter-spacing:.15em;color:var(--accent)}.brand strong{display:block;font-size:19px;line-height:1.15;margin:5px 0}.brand small{color:var(--muted)}nav{display:grid;gap:4px}nav a{display:flex;justify-content:space-between;align-items:center;color:var(--muted);text-decoration:none;padding:10px 12px;border-radius:9px}nav a:hover,nav a.active{background:var(--panel2);color:var(--text)}.nav-badge{font-size:10px;background:#343d31;padding:2px 6px;border-radius:999px}.sidebar-foot{position:absolute;bottom:16px;left:16px;right:16px}.main{min-width:0;padding:28px 32px 50px;max-width:1450px}.topbar{display:flex;justify-content:space-between;gap:20px;align-items:start;margin-bottom:20px}.topbar h1{font-size:clamp(27px,4vw,44px);letter-spacing:-.04em;margin:0}.topbar p{margin:5px 0 0}.message{padding:12px 16px;border:1px solid var(--accent2);background:#202c1c;border-radius:10px;margin-bottom:16px}.message.error{border-color:#814e43;background:#321f1b}.panel,.hero{background:var(--panel);border:1px solid var(--line);border-radius:14px}.panel{padding:20px}.hero{padding:26px;box-shadow:0 16px 40px #0004}.grid{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:14px;margin-top:14px}.span12{grid-column:span 12}.span8{grid-column:span 8}.span7{grid-column:span 7}.span6{grid-column:span 6}.span5{grid-column:span 5}.span4{grid-column:span 4}.span3{grid-column:span 3}.hero-top{display:flex;justify-content:space-between;align-items:flex-start;gap:22px}.hero-top>div:first-child{flex:1 1 auto;min-width:0}.hero-top>.tag,.hero-top>.status-pill{flex:0 0 auto;align-self:flex-start}.eyebrow{color:var(--accent);font-size:11px;text-transform:uppercase;letter-spacing:.14em}.title{font-size:clamp(25px,4vw,40px);line-height:1.08;margin:5px 0}.status-pill,.tag{display:inline-flex;align-items:center;justify-content:center;flex:0 0 auto;min-width:max-content;max-width:100%;border:1px solid var(--line);border-radius:999px;padding:5px 10px;color:var(--warm);white-space:nowrap;font-size:12px;line-height:1.2}.tag.ok{color:var(--ok);border-color:#557146}.tag.bad{color:#ffb9aa;border-color:#75483c}.muted,p{color:var(--muted)}h2{margin:0 0 12px;font-size:19px;color:var(--warm)}h3{margin:0 0 8px;font-size:15px}.progress{height:10px;background:#0f120e;border-radius:999px;overflow:hidden;margin:18px 0 8px}.progress>div{height:100%;background:linear-gradient(90deg,var(--accent2),var(--accent));border-radius:999px}.phase-rail{display:grid;grid-template-columns:repeat(7,1fr);gap:7px;margin:18px 0}.phase{padding:10px 7px;border:1px solid var(--line);border-radius:9px;text-decoration:none;color:var(--text);min-width:0}.phase span{display:block;font-size:10px;color:var(--muted)}.phase strong{display:block;font-size:12px;overflow:hidden;text-overflow:ellipsis}.phase.done{background:#25331f;border-color:#506b42}.phase.current{background:#343825;border-color:var(--warm)}.phase.future{opacity:.48}.actions,.inline-form{display:flex;flex-wrap:wrap;gap:9px;align-items:center}.actions{margin-top:14px}button,.button{display:inline-flex;align-items:center;justify-content:center;border:1px solid var(--line);background:#293126;color:var(--text);padding:10px 14px;border-radius:9px;font-weight:700;text-decoration:none;cursor:pointer}button:hover,.button:hover{filter:brightness(1.12)}button.primary,.button.primary{background:var(--accent);color:#10140f;border-color:var(--accent)}button.danger,.button.danger{color:#ffd7ce;border-color:#75483c;background:#34201b}button.subtle,.button.subtle{background:transparent}input,select,textarea{width:100%;background:#11150f;border:1px solid var(--line);color:var(--text);padding:10px;border-radius:8px;font:inherit}textarea{min-height:180px;resize:vertical;font-family:Consolas,ui-monospace,monospace;line-height:1.55}.editor{min-height:62vh}.field{display:grid;gap:6px;margin-bottom:12px}.field label{font-size:12px;color:var(--warm);font-weight:700}.field small{color:var(--muted)}.form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.form-grid .wide{grid-column:1/-1}.check{display:flex;gap:9px;align-items:flex-start;padding:8px 0;border-bottom:1px solid #2c3329}.check:last-child{border-bottom:0}.check .mark{font-weight:900;color:var(--ok)}.check.fail .mark{color:var(--danger)}.check.warn .mark{color:var(--warm)}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;white-space:nowrap}th{text-align:left;color:var(--accent);font-size:10px;text-transform:uppercase;letter-spacing:.08em;border-bottom:1px solid var(--line);padding:8px}td{padding:8px;border-bottom:1px solid #2c3329;max-width:390px;overflow:hidden;text-overflow:ellipsis}.empty{font-style:italic}.callout{padding:14px;border-left:3px solid var(--accent);background:#20271e;border-radius:6px}.callout.warn{border-color:var(--warm)}.callout.danger{border-color:var(--danger)}details{border:1px solid var(--line);border-radius:12px;background:var(--panel);margin-top:14px}summary{padding:15px 18px;cursor:pointer;color:var(--warm);font-weight:700}.details-body{padding:0 18px 18px}.metric{font-size:27px;font-weight:800;letter-spacing:-.04em}.small{font-size:12px}.file-path{font-family:Consolas,monospace;font-size:12px;color:var(--warm);word-break:break-all}.proposal{border:1px solid var(--line);background:var(--panel2);padding:15px;border-radius:10px;margin:10px 0}.proposal.pending{border-color:var(--accent2)}.job{padding:12px;border-radius:9px;background:#19211a;border:1px solid var(--line);margin:8px 0}.job.running{border-color:var(--blue)}.job.failed{border-color:var(--danger)}.job.complete{border-color:var(--ok)}.footer{margin:24px 0;color:var(--muted);font-size:12px}.new-card{padding:34px;text-align:center}.split{display:grid;grid-template-columns:1fr 1fr;gap:14px}.sticky-actions{position:sticky;bottom:10px;padding:10px;background:#141913e8;backdrop-filter:blur(10px);border:1px solid var(--line);border-radius:10px;margin-top:10px}.hidden{display:none}code{color:var(--warm)}
@media(max-width:1050px){.shell{grid-template-columns:1fr}.sidebar{position:static;height:auto}.sidebar nav{grid-template-columns:repeat(4,1fr)}.sidebar-foot{position:static;margin-top:12px}.main{padding:20px}.span8,.span7,.span6,.span5,.span4,.span3{grid-column:span 12}}
@media(max-width:700px){.sidebar nav{grid-template-columns:repeat(2,1fr)}.hero-top,.form-grid,.split{display:grid;grid-template-columns:1fr}.phase-rail{grid-template-columns:repeat(2,1fr)}.main{padding:14px}.topbar{display:block}}
"""

JS = r"""
document.querySelectorAll('form[data-confirm]').forEach(f=>f.addEventListener('submit',e=>{if(!confirm(f.dataset.confirm))e.preventDefault()}));
const running=document.querySelector('[data-running-jobs="1"]');if(running&&document.body.dataset.page==='diagnostics'){setTimeout(()=>location.reload(),5000)}
document.querySelectorAll('[data-copy]').forEach(b=>b.addEventListener('click',()=>{const el=document.getElementById(b.dataset.copy);navigator.clipboard.writeText(el.value||el.textContent);b.textContent='Copied';setTimeout(()=>b.textContent='Copy',1500)}));
"""


def layout(root: Path, page: str, title: str, subtitle: str, content: str, message: str = "", error: bool = False, jobs: list[dict[str, Any]] | None = None) -> str:
    status = workflow_status(root)
    active = status.get("project")
    jobs = jobs or []
    running = [job for job in jobs if job.get("status") == "running"]
    message_html = f'<div class="message {"error" if error else ""}">{esc(message)}</div>' if message else ""
    active_badge = active.get("stage", "") if active else ""
    nav = "".join([
        nav_link("home", page, "Production", active_badge),
        nav_link("workspace", page, "Workspace"),
        nav_link("media", page, "Files & media"),
        nav_link("release", page, "Release"),
        nav_link("operations", page, "Operations"),
        nav_link("channel", page, "Channel"),
        nav_link("settings", page, "Settings"),
        nav_link("diagnostics", page, "Diagnostics", str(len(running)) if running else ""),
    ])
    job_html = ""
    if jobs:
        cards = []
        for job in jobs[:6]:
            detail = job.get("error") or job.get("message") or ""
            cards.append(f'<div class="job {esc(job.get("status",""))}"><strong>{esc(job.get("label","Job"))}</strong> · {esc(job.get("status",""))}<div class="small muted">{esc(detail)}</div></div>')
        job_html = '<details open><summary>Running and recent tasks</summary><div class="details-body" data-running-jobs="' + ("1" if running else "0") + '">' + "".join(cards) + '</div></details>'
    return f'''<!doctype html><html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)} · Minecraft Narrative Studio</title><style>{CSS}</style></head><body data-page="{esc(page)}"><div class="shell">
<aside class="sidebar"><div class="brand"><div class="kicker">Video-at-a-time harness</div><strong>Minecraft Narrative Studio</strong><small>v{VERSION} · Dashboard control</small></div><nav>{nav}</nav><div class="sidebar-foot">{form('/action/open-root','Open studio folder',css='subtle')}<div style="height:8px"></div>{form('/action/shutdown','Close Studio',css='subtle',confirm='Stop the local studio server?')}</div></aside>
<main class="main"><header class="topbar"><div><h1>{esc(title)}</h1><p>{esc(subtitle)}</p></div><div class="status-pill">Local · private</div></header>{message_html}{job_html}{content}<div class="footer">Minecraft Narrative Studio v{VERSION} · Generated {esc(utc_now())} · British English · BRL</div></main>
</div><script>{JS}</script></body></html>'''


def home_page(root: Path) -> str:
    status = workflow_status(root)
    stages = load_stages(root)
    projects = list_projects(root)
    paused = [p for p in projects if p.get("state") == "paused"]
    finished = [p for p in projects if p.get("state") in {"completed", "abandoned"}]
    if status["status"] == "no_active_video":
        create = '''<section class="hero new-card"><div class="eyebrow">One active production</div><div class="title">What video are you making?</div><p>Start with a working title and any rough idea. The workspace will guide the production from direction to postmortem.</p><form method="post" action="/action/new" class="inline-form" style="justify-content:center"><input name="title" required placeholder="Working title" style="max-width:560px"><button class="primary">Start this video</button></form></section>'''
    else:
        project = status["project"]; stage = status["stage"]; progress = status["progress"]; slug = project["slug"]
        primary = SafeHTML(f'<a class="button primary" href="/?page=workspace">Open {esc(stage["label"])} workspace</a>')
        action = ""
        if status["status"] == "approval_needed":
            fields = f'<input type="hidden" name="slug" value="{esc(slug)}"><input type="hidden" name="gate" value="{esc(status["approval_gate"])}">'
            action = form('/action/approve', f'Approve {stage["label"]}', fields)
        elif status["status"] == "ready_to_advance":
            action = form('/action/continue', 'Continue production')
        blockers = "".join(f'<div class="check fail"><span class="mark">×</span><div><strong>{esc(item.label)}</strong><div class="muted">{esc(item.detail)}</div></div></div>' for item in status.get("blockers", [])[:5]) or '<p class="empty">No mechanical blockers.</p>'
        app_settings = load_settings(root, include_secret=False).get("apps", {})
        launcher_buttons = []
        for app_id, app in app_settings.items():
            if app.get("command"):
                launcher_buttons.append(form("/action/launch", f"Launch {app.get('label', app_id)}", f'<input type="hidden" name="app_id" value="{esc(app_id)}">', css="subtle"))
        launchers = "".join(launcher_buttons) or '<a class="button subtle" href="/?page=settings">Configure production apps</a>'
        create = f'''<section class="hero"><div class="hero-top"><div><div class="eyebrow">Current video · {esc(stage["label"])}</div><div class="title">{esc(project["title"])}</div><p>{esc(status["headline"])}</p></div><div class="status-pill">{esc(project.get("state","active"))}</div></div><div class="progress"><div style="width:{progress['percent']}%"></div></div><div class="small muted">{progress['percent']}% through the production pipeline</div>{phase_rail(stages,project['stage'],project.get('state','active'))}<div class="grid"><div class="panel span7"><h2>Next action</h2><p>{esc(status['next_action'])}</p><div class="actions">{primary}{action}</div></div><div class="panel span5"><h2>Studio Assistant</h2><p>{esc(status['assistant_focus'])}</p><a class="button" href="/?page=workspace#assistant">Work with assistant</a></div></div></section><section class="grid"><div class="panel span7"><h2>Current blockers</h2>{blockers}</div><div class="panel span5"><h2>Launch production tools</h2><div class="actions">{launchers}</div><hr style="border:0;border-top:1px solid var(--line);margin:16px 0"><h2>Project controls</h2><div class="actions">{form("/action/open-project","Open project folder",f'<input type="hidden" name="slug" value="{esc(slug)}">',css="subtle")}{form("/action/pause","Pause video",f'<input type="hidden" name="slug" value="{esc(slug)}">',css="subtle")}{form("/action/abandon","Abandon",f'<input type="hidden" name="slug" value="{esc(slug)}">',css="danger",confirm="Abandon this video? Its files will be kept.")}</div></div></section>'''
    paused_rows=[]
    for item in paused:
        action=form('/action/resume','Resume',f'<input type="hidden" name="slug" value="{esc(item["slug"])}">') if status["status"]=="no_active_video" else 'Pause current first'
        paused_rows.append([item.get('title'),item.get('stage'),SafeHTML(action)])
    history_rows=[[p.get('title'),p.get('state'),p.get('stage'),p.get('updated_at','')[:10]] for p in finished[:12]]
    secondary = ''
    if paused or finished:
        secondary=f'<section class="grid"><div class="panel span6"><h2>Paused videos</h2>{rows_table(["Title","Phase","Action"],paused_rows,"No paused videos.")}</div><div class="panel span6"><h2>History</h2>{rows_table(["Title","State","Last phase","Updated"],history_rows,"No finished videos.")}</div></section>'
    return create+secondary


def _checks_html(checks: list[Any]) -> str:
    cards=[]
    for check in checks:
        cls="" if check.ok else "fail"
        mark="✓" if check.ok else "×"
        if getattr(check,"severity","error")=="warning" and check.ok:
            cls="warn";mark="!"
        cards.append(f'<div class="check {cls}"><span class="mark">{mark}</span><div><strong>{esc(check.label)}</strong><div class="muted">{esc(check.detail)}</div></div></div>')
    return "".join(cards) or '<p class="empty">No checks configured.</p>'


def workspace_page(root: Path) -> str:
    status=workflow_status(root)
    if status["status"]=="no_active_video":
        return '<section class="panel"><h2>No active video</h2><p>Start a video from Production first.</p><a class="button primary" href="/?page=home">Go to Production</a></section>'
    project=status["project"];stage=status["stage"];slug=project["slug"];doc=stage["user_document"]
    try:text=read_text_file(root,slug,doc)
    except Exception as exc:text=f"Could not load document: {exc}"
    settings=load_settings(root,include_secret=False)
    proposals=list_proposals(root,slug)
    proposal_cards=[]
    for p in proposals[:6]:
        proposal_cards.append(f'<div class="proposal {esc(p.get("status",""))}"><strong>{esc(p.get("summary","Assistant proposal"))}</strong><div class="small muted">{esc(p.get("created_at",""))} · {esc(RUNNER_LABELS.get(p.get("runner",""),p.get("runner","") or "external"))} · {esc(p.get("model",""))} · {esc(p.get("status",""))}</div><div class="actions"><a class="button subtle" href="/?page=proposal&id={url(str(p.get("id","")))}">Review proposal</a></div></div>')
    available=[name for name,item in settings.get('runner_status',{}).items() if item.get('available')]
    preferred=(runner_candidates(settings,project['stage'],'develop') or [''])[0]
    assistant_status=f'<span class="tag ok">{esc(RUNNER_LABELS.get(preferred,preferred))} routed</span>' if available else '<span class="tag bad">No runner ready</span>'
    approval=''
    if status['status']=='approval_needed':
        approval=form('/action/approve',f'Approve {stage["label"]}',f'<input type="hidden" name="slug" value="{esc(slug)}"><input type="hidden" name="gate" value="{esc(status["approval_gate"])}">')
    elif status['status']=='ready_to_advance': approval=form('/action/continue','Continue production')
    stage_tools=''
    if project['stage']=='production':
        production_links = (
            f'<section class="panel"><h2>Production development</h2>'
            f'<p>The research, implementation matrix and storyboard remain separate from the main plan so each can be reviewed without hiding operational evidence.</p>'
            f'<div class="actions"><a class="button" href="/?page=file&path={url(".studio/internal/production/storyboard-plan.md")}">Storyboard plan</a>'
            f'<a class="button subtle" href="/?page=file&path={url(".studio/internal/production/technical-research.md")}">Technical research</a>'
            f'<a class="button subtle" href="/?page=file&path={url(".studio/internal/production/scene-implementation-matrix.csv")}">Scene methods</a></div>'
            f'<p class="callout">For a research-deepening pass, select <strong>Develop phase</strong> and <strong>Allow web search</strong>. The runner manager will prioritise Codex or the API for that run.</p></section>'
        )
        capture_panel=f'''<section class="panel" id="capture"><h2>Record a captured take</h2><form method="post" action="/action/capture"><input type="hidden" name="slug" value="{esc(slug)}"><div class="form-grid"><div class="field"><label>Shot ID</label><input name="shot_id" required></div><div class="field"><label>Take</label><input name="take" required></div><div class="field"><label>File</label><input name="file" placeholder="SH01_T01.mp4"></div><div class="field"><label>Captured at</label><input name="captured_at" type="date"></div><div class="field"><label>Technical</label><select name="technical_ok"><option>yes</option><option>no</option></select></div><div class="field"><label>Performance</label><select name="performance_ok"><option>yes</option><option>no</option></select></div><div class="field"><label>Selected</label><select name="selected"><option>yes</option><option>no</option></select></div><div class="field wide"><label>Notes</label><input name="notes"></div></div><button class="primary">Add take</button></form></section>'''
        stage_tools = production_links + capture_panel
    if project['stage']=='edit':
        stage_tools='<section class="panel"><h2>Final media</h2><p>Upload the locked master and captions from Files & media. The edit gate will not pass without a real master file.</p><a class="button primary" href="/?page=media">Upload final media</a></section>'
    if project['stage']=='release':
        stage_tools='<section class="panel"><h2>Release assets</h2><p>Upload the final human-approved thumbnail, prepare the package, and configure YouTube from Release.</p><a class="button primary" href="/?page=release">Open Release control</a></section>'
    all_stages = load_stages(root)
    current_index = [item['name'] for item in all_stages].index(project['stage'])
    reopen_options = ''.join(f'<option value="{esc(item["name"])}">{esc(item["label"])}</option>' for item in all_stages[:current_index + 1])
    reopen_panel = f'''<details><summary>Reopen an earlier phase</summary><div class="details-body"><form method="post" action="/action/reopen"><input type="hidden" name="slug" value="{esc(slug)}"><div class="field"><label>Phase</label><select name="to_stage">{reopen_options}</select></div><div class="field"><label>Reason</label><input name="reason" required minlength="10" placeholder="What changed and why?"></div><button class="danger">Reopen and invalidate affected approvals</button></form></div></details>'''
    advanced=[]
    for f in list_project_files(root,slug,include_internal=True):
        if f['internal']:
            edit=f'<a href="/?page=file&path={url(f["path"])}">Edit</a>' if f['editable'] else 'binary'
            advanced.append([f['path'],f['bytes'],SafeHTML(edit)])
    return f'''<section class="grid"><div class="panel span8"><div class="hero-top"><div><div class="eyebrow">{esc(stage['label'])} workspace</div><h2 style="font-size:25px">{esc(project['title'])}</h2></div>{assistant_status}</div><form method="post" action="/action/save-document"><input type="hidden" name="slug" value="{esc(slug)}"><input type="hidden" name="path" value="{esc(doc)}"><textarea class="editor" name="content">{esc(text)}</textarea><div class="sticky-actions actions"><button class="primary">Save document</button><button type="button" class="subtle" data-copy="current-document">Copy</button>{approval}<a class="button subtle" href="/?page=media">Files</a></div><textarea id="current-document" class="hidden">{esc(text)}</textarea></form></div><div class="span4"><section class="panel" id="assistant"><h2>Studio Assistant</h2><p>{esc(stage['assistant_focus'])}</p><form method="post" action="/action/assistant"><input type="hidden" name="slug" value="{esc(slug)}"><div class="field"><label>What should it do?</label><textarea name="request" placeholder="Develop this phase from my notes, strengthen the ending, make it cheaper to produce…"></textarea></div><div class="form-grid"><div class="field"><label>Mode</label><select name="mode"><option value="develop">Develop phase</option><option value="revise">Revise current work</option><option value="audit">Audit and repair</option></select></div><div class="field"><label>Research</label><select name="use_web"><option value="" {'selected' if not settings.get('web_search_default') else ''}>No web search</option><option value="yes" {'selected' if settings.get('web_search_default') else ''}>Allow web search</option></select></div></div><button class="primary" {'disabled' if not available else ''}>Run Studio Assistant</button></form>{'<p class="callout warn">Install and connect Codex or OpenCode in Settings, enable the API fallback, or import a JSON proposal below.</p>' if not available else ''}<details><summary>Import or recover assistant work</summary><div class="details-body"><p>Recover the newest completed Codex result for this video, or paste a proposal matching the dashboard JSON contract.</p><form method="post" action="/action/recover-runner-proposal"><input type="hidden" name="slug" value="{esc(slug)}"><button type="submit">Recover latest completed run</button></form><hr style="border:0;border-top:1px solid var(--line);margin:16px 0"><form method="post" action="/action/import-proposal"><input type="hidden" name="slug" value="{esc(slug)}"><textarea name="proposal" placeholder='{{"summary":"…","document":"# …","files":{{}},"questions":[],"warnings":[]}}'></textarea><button>Import pasted proposal</button></form></div></details></section><section class="panel" style="margin-top:14px"><h2>Assistant proposals</h2>{''.join(proposal_cards) or '<p class="empty">No proposals yet.</p>'}</section></div></section><section class="grid"><div class="panel span7"><h2>Phase checks</h2>{_checks_html(status['checks'])}<div class="actions">{form('/action/check','Run checks',f'<input type="hidden" name="slug" value="{esc(slug)}">',css='subtle')}{approval}</div></div><div class="span5">{stage_tools}{reopen_panel}</div></section><details><summary>Advanced internal evidence · {len(advanced)} files</summary><div class="details-body">{rows_table(['Path','Bytes','Action'],advanced,'No internal files.')}</div></details>'''


def proposal_page(root: Path, proposal_id: str) -> str:
    status = workflow_status(root)
    if status["status"] == "no_active_video":
        return '<section class="panel"><p>No active video.</p></section>'
    slug = status["project"]["slug"]
    proposal = next((item for item in list_proposals(root, slug) if item.get("id") == proposal_id), None)
    if not proposal:
        return '<section class="panel"><h2>Proposal not found</h2></section>'

    file_previews = []
    for path, content in proposal.get("files", {}).items():
        file_previews.append(
            f'<details><summary>{esc(path)} · {len(content)} characters</summary>'
            f'<div class="details-body"><textarea readonly>{esc(content)}</textarea></div></details>'
        )
    questions = ''.join(f'<li>{esc(question)}</li>' for question in proposal.get("questions", [])) or '<li>None</li>'
    warnings = ''.join(f'<li>{esc(warning)}</li>' for warning in proposal.get("warnings", [])) or '<li>None</li>'
    pending = proposal.get("status") == "pending"
    fields = (
        f'<input type="hidden" name="slug" value="{esc(slug)}">'
        f'<input type="hidden" name="proposal_id" value="{esc(proposal_id)}">'
    )
    discard = form(
        '/action/discard-proposal', 'Discard', fields, css='danger',
        confirm='Discard this assistant proposal?'
    ) if pending else ''

    if pending:
        editor = f'''<form method="post">{fields}
<div class="callout">Edit the proposal directly below. <strong>Save edits</strong> keeps it pending. <strong>Accept edited version</strong> saves and applies exactly what is in the editor.</div>
<textarea class="editor" name="document">{esc(proposal.get('document', ''))}</textarea>
<div class="sticky-actions actions">
<button type="submit" formaction="/action/save-proposal">Save edits</button>
<button class="primary" type="submit" formaction="/action/apply-edited-proposal">Accept edited version</button>
</div></form>'''
    else:
        editor = f'<textarea class="editor" readonly>{esc(proposal.get("document", ""))}</textarea>'

    edited_note = ''
    if proposal.get("edited_at"):
        edited_note = f' · manually edited {esc(proposal.get("manual_edit_count", 1))} time(s), last saved {esc(proposal.get("edited_at"))}'

    return f'''<section class="hero"><div class="eyebrow">Assistant proposal · {esc(proposal.get('status'))}</div><div class="title">{esc(proposal.get('summary'))}</div><p>{esc(proposal.get('created_at'))} · {esc(RUNNER_LABELS.get(proposal.get('runner',''), proposal.get('runner','') or 'external'))} · {esc(proposal.get('model'))} · {esc(proposal.get('reasoning_effort',''))}{edited_note}</p><div class="actions">{discard}<a class="button subtle" href="/?page=workspace">Back to workspace</a></div></section><section class="grid"><div class="panel span8"><h2>Proposed main document</h2>{editor}</div><div class="span4"><section class="panel"><h2>Questions</h2><ul>{questions}</ul></section><section class="panel" style="margin-top:14px"><h2>Warnings</h2><ul>{warnings}</ul></section><section class="panel" style="margin-top:14px"><h2>Editing scope</h2><p>Your edits change the main document only. The supporting internal evidence below remains as proposed.</p></section></div></section><section class="panel" style="margin-top:14px"><h2>Proposed internal evidence</h2>{''.join(file_previews) or '<p class="empty">No supporting files in this proposal.</p>'}</section>'''


def file_page(root: Path, relative: str) -> str:
    status=workflow_status(root)
    if status['status']=='no_active_video':return '<section class="panel"><p>No active video.</p></section>'
    slug=status['project']['slug']
    try:text=read_text_file(root,slug,relative)
    except Exception as exc:return f'<section class="panel"><h2>Cannot edit file</h2><p>{esc(exc)}</p></section>'
    return f'''<section class="panel"><div class="eyebrow">Browser file editor</div><h2 class="file-path">{esc(relative)}</h2><form method="post" action="/action/save-file"><input type="hidden" name="slug" value="{esc(slug)}"><input type="hidden" name="path" value="{esc(relative)}"><textarea class="editor" name="content">{esc(text)}</textarea><div class="sticky-actions actions"><button class="primary">Save file</button><a class="button subtle" href="/?page=workspace">Back</a></div></form></section>'''


def media_page(root: Path) -> str:
    status=workflow_status(root)
    if status['status']=='no_active_video':return '<section class="panel"><p>Start a video first.</p></section>'
    project=status['project'];slug=project['slug'];media=media_status(root,slug)
    cards=[]
    for key,label in [('master_file','Final master'),('thumbnail_file','Final thumbnail'),('youtube_client_secrets','YouTube OAuth file')]:
        item=media[key];tag='<span class="tag ok">Ready</span>' if item['exists'] else '<span class="tag bad">Missing</span>'
        cards.append(f'<div class="panel span4"><div class="hero-top"><h2>{label}</h2>{tag}</div><div class="file-path">{esc(item["relative"] or "Not uploaded")}</div><div class="small muted">{item["bytes"]} bytes</div></div>')
    files=[]
    for f in list_project_files(root,slug,include_internal=False):
        action=f'<a href="/download/{url(slug)}/{quote(f["path"],safe="/")}">Download</a>'
        if f['editable']:action+=' · <a href="/?page=file&path='+url(f['path'])+'">Edit</a>'
        action+=form('/action/delete-file','Delete',f'<input type="hidden" name="slug" value="{esc(slug)}"><input type="hidden" name="path" value="{esc(f["path"])}">',css='subtle',confirm='Delete this file? A backup will be retained.')
        files.append([f['path'],f['bytes'],f['modified'],SafeHTML(action)])
    upload_forms=[]
    labels={'master':'Final master video','thumbnail':'Final thumbnail','capture':'Captured footage','audio':'Audio and narration','project':'Editor/project files','reference':'References','youtube':'YouTube OAuth client JSON','analytics':'Analytics CSV'}
    for bucket,label in labels.items():
        native = form("/action/select-file", "Choose with native picker", f'<input type="hidden" name="slug" value="{esc(slug)}"><input type="hidden" name="bucket" value="{esc(bucket)}">', css="primary")
        upload_forms.append(f'<div class="panel span4"><h2>{esc(label)}</h2>{native}<details><summary>Browser upload</summary><div class="details-body"><p class="small muted">Best for smaller files. Use the native picker for large footage and masters; it registers the original file without copying it.</p><form method="post" action="/action/upload" enctype="multipart/form-data"><input type="hidden" name="slug" value="{esc(slug)}"><input type="hidden" name="bucket" value="{esc(bucket)}"><div class="field"><input type="file" name="file" required></div><button>Upload</button></form></div></details></div>')
    return f'''<section class="grid">{''.join(cards)}</section><section class="grid">{''.join(upload_forms)}</section><section class="panel" style="margin-top:14px"><div class="hero-top"><h2>Project files</h2>{form('/action/open-project','Open in file manager',f'<input type="hidden" name="slug" value="{esc(slug)}">',css='subtle')}</div>{rows_table(['Path','Bytes','Modified','Actions'],files,'No user files yet.')}</section>'''


def release_page(root: Path) -> str:
    status=workflow_status(root)
    if status['status']=='no_active_video':return '<section class="panel"><p>Start a video first.</p></section>'
    project=status['project'];slug=project['slug'];media=media_status(root,slug);youtube=project.get('youtube',{})
    metadata_rel='.studio/internal/release/metadata.json'; metadata=''
    try:metadata=read_text_file(root,slug,metadata_rel)
    except Exception:pass
    deps=importlib.util.find_spec('googleapiclient') is not None
    package_rows=[]
    export_root=root/'exports'/slug
    if export_root.exists():
        for path in sorted(export_root.glob('publish-*'),reverse=True):
            if path.is_dir():package_rows.append([path.name,SafeHTML(form('/action/open-path','Open package',f'<input type="hidden" name="path" value="{esc(str(path))}">',css='subtle'))])
    readiness=[]
    for key,label in [('master_file','Final master'),('thumbnail_file','Final thumbnail'),('youtube_client_secrets','OAuth client file')]:
        readiness.append([label,'ready' if media[key]['exists'] else 'missing',media[key]['relative']])
    upload_enabled=bool(media['master_file']['exists'])
    return f'''<section class="grid"><div class="panel span7"><h2>Release readiness</h2>{rows_table(['Item','Status','File'],readiness,'')}</div><div class="panel span5"><h2>YouTube status</h2><div class="metric">{esc(youtube.get('upload_status','not started'))}</div><p>Video ID: {esc(youtube.get('video_id') or '—')}</p><p>Published: {esc(youtube.get('published_at') or '—')}</p></div></section><section class="grid"><div class="panel span7"><h2>Metadata</h2><form method="post" action="/action/save-file"><input type="hidden" name="slug" value="{esc(slug)}"><input type="hidden" name="path" value="{esc(metadata_rel)}"><textarea name="content" style="min-height:430px">{esc(metadata)}</textarea><button class="primary">Save metadata</button></form></div><div class="span5"><section class="panel"><h2>Publish package</h2><p>Create a checksummed release folder after publication approval.</p>{form('/action/package','Build publish package',f'<input type="hidden" name="slug" value="{esc(slug)}">')}{form('/action/wireframes','Generate thumbnail wireframes',f'<input type="hidden" name="slug" value="{esc(slug)}">',css='subtle')}{rows_table(['Package','Action'],package_rows,'No package built yet.')}</section><section class="panel" style="margin-top:14px"><h2>YouTube uploader</h2><div class="callout {' ' if deps else 'warn'}">Uploader support: {'installed' if deps else 'not installed'}</div>{'' if deps else form('/action/install-youtube','Install YouTube support') }<form method="post" action="/action/youtube" style="margin-top:12px"><input type="hidden" name="slug" value="{esc(slug)}"><div class="field"><label>Privacy</label><select name="privacy"><option>private</option><option>unlisted</option><option>public</option></select></div><div class="field"><label>Schedule at (RFC3339; private only)</label><input name="publish_at" placeholder="2026-08-01T18:00:00-03:00"></div><div class="field"><label><input type="checkbox" name="notify_subscribers" value="yes" style="width:auto"> Notify subscribers</label><small>Off by default for safer testing.</small></div><div class="field"><label><input type="checkbox" name="execute" value="yes" style="width:auto"> Execute real upload</label><small>Unchecked creates a dry-run plan only.</small></div><button class="primary" {'disabled' if not upload_enabled else ''}>Build plan or upload</button></form><p class="small muted">Dry run requires only the master and metadata. Real upload additionally requires Publication approval, OAuth credentials, and YouTube support.</p></section></div></section>'''


def operations_page(root: Path) -> str:
    status = workflow_status(root)
    slug = status.get("project", {}).get("slug", "")
    ideas = read_csv_rows(root / "data/ideas.csv")
    ideas.sort(key=lambda row: float(row.get("score") or 0), reverse=True)
    money = business_summary(root)
    hours = time_summary(root)
    calendar = read_csv_rows(root / "data/channel/content_calendar.csv")
    social = read_csv_rows(root / "data/channel/social_queue.csv")
    assets = read_csv_rows(root / "data/library/assets.csv")
    deals = read_csv_rows(root / "data/business/deals.csv")
    money_rows = [[currency, f"{values['revenue']:.2f}", f"{values['expense']:.2f}", f"{values['profit']:.2f}"] for currency, values in sorted(money.items())]
    analytics_html = '<p class="empty">No active video or analytics snapshots.</p>'
    if slug:
        try:
            report = report_for_slug(root, slug)
            latest = report["latest"]
            analytics_html = rows_table(
                ["Snapshots", "Views", "Watch hours", "Impressions", "CTR", "Subscribers"],
                [[report["snapshots"], latest.get("views"), latest.get("watch_hours"), latest.get("impressions"), latest.get("ctr_percent"), latest.get("subscribers_gained")]],
                "No analytics.",
            )
        except Exception:
            pass

    idea_ratings = "".join(
        f'<div class="field"><label>{name.replace("_", " ").title()} 1–5</label><input name="{name}" type="number" min="1" max="5" value="3"></div>'
        for name in ["clarity", "hook_strength", "visual_potential", "feasibility", "originality", "series_potential"]
    )
    forms = f'''
<details open><summary>Add an idea</summary><div class="details-body"><form method="post" action="/action/idea"><div class="form-grid"><div class="field wide"><label>Title</label><input name="title" required></div><div class="field wide"><label>Premise</label><textarea name="premise"></textarea></div><div class="field wide"><label>Hook</label><input name="hook"></div>{idea_ratings}</div><input type="hidden" name="format" value="scripted story"><input type="hidden" name="scope" value="small"><button class="primary">Add and score idea</button></form></div></details>
<details><summary>Log creator time</summary><div class="details-body"><form method="post" action="/action/time"><div class="form-grid"><div class="field"><label>Date</label><input type="date" name="date" required></div><div class="field"><label>Hours</label><input type="number" step="0.25" name="hours" required></div><div class="field"><label>Area</label><input name="area" placeholder="writing, build, edit"></div><div class="field"><label>Tool</label><input name="tool"></div><div class="field wide"><label>Task</label><input name="task"></div><div class="field wide"><label>Notes</label><input name="notes"></div><input type="hidden" name="video" value="{esc(slug)}"></div><button>Log time</button></form></div></details>
<details><summary>Add money entry</summary><div class="details-body"><form method="post" action="/action/money"><div class="form-grid"><div class="field"><label>Date</label><input type="date" name="date" required></div><div class="field"><label>Type</label><select name="type"><option>expense</option><option>revenue</option></select></div><div class="field"><label>Amount</label><input type="number" step="0.01" name="amount" required></div><div class="field"><label>Currency</label><input name="currency" value="BRL"></div><div class="field"><label>Category</label><input name="category"></div><div class="field"><label>Counterparty</label><input name="counterparty"></div><div class="field wide"><label>Note</label><input name="note"></div><input type="hidden" name="video" value="{esc(slug)}"></div><button>Add entry</button></form></div></details>
<details><summary>Add calendar milestone</summary><div class="details-body"><form method="post" action="/action/calendar"><div class="form-grid"><div class="field"><label>Working title</label><input name="working_title" value="{esc(status.get('project',{}).get('title',''))}"></div><div class="field"><label>Target publication</label><input type="date" name="target_publish"></div><div class="field"><label>Status</label><input name="status" value="planned"></div><div class="field"><label>Priority</label><input name="priority" value="normal"></div><div class="field"><label>Format</label><input name="format" value="scripted story"></div><div class="field"><label>Pillar</label><input name="pillar"></div><div class="field wide"><label>Dependency</label><input name="dependency"></div><div class="field wide"><label>Notes</label><input name="notes"></div><input type="hidden" name="video_slug" value="{esc(slug)}"></div><button>Add milestone</button></form></div></details>
<details><summary>Add social item</summary><div class="details-body"><form method="post" action="/action/social"><div class="form-grid"><div class="field"><label>Platform</label><input name="platform" required></div><div class="field"><label>Target date</label><input type="date" name="target_publish"></div><div class="field"><label>Status</label><input name="status" value="draft"></div><div class="field"><label>Copy file</label><input name="copy_file"></div><div class="field"><label>Asset</label><input name="asset"></div><div class="field"><label>Approved by</label><input name="approved_by"></div><div class="field wide"><label>Notes</label><input name="notes"></div><input type="hidden" name="video_slug" value="{esc(slug)}"></div><button>Add social item</button></form></div></details>
<details><summary>Add commercial opportunity</summary><div class="details-body"><form method="post" action="/action/deal"><div class="form-grid"><div class="field"><label>Brand</label><input name="brand" required></div><div class="field"><label>Contact</label><input name="contact"></div><div class="field"><label>Status</label><input name="status" value="lead"></div><div class="field"><label>Value</label><input type="number" step="0.01" name="value"></div><div class="field"><label>Currency</label><input name="currency" value="BRL"></div><div class="field"><label>Next action date</label><input type="date" name="next_action_date"></div><div class="field wide"><label>Deliverables</label><input name="deliverables"></div><div class="field wide"><label>Next action</label><input name="next_action"></div><div class="field wide"><label>Notes</label><input name="notes"></div></div><button>Add opportunity</button></form></div></details>
<details><summary>Add reusable asset</summary><div class="details-body"><form method="post" action="/action/asset"><div class="form-grid"><div class="field"><label>Name</label><input name="name" required></div><div class="field"><label>Type</label><input name="type" required></div><div class="field wide"><label>Path or URL</label><input name="path_or_url"></div><div class="field"><label>Owner</label><input name="owner" value="Luan"></div><div class="field"><label>Licence</label><input name="licence"></div><div class="field"><label>Version</label><input name="version" value="1"></div><div class="field"><label>Reuse status</label><input name="reuse_status" value="ready"></div><div class="field"><label>Used in</label><input name="used_in" value="{esc(slug)}"></div><div class="field wide"><label>Notes</label><input name="notes"></div><input type="hidden" name="asset_id" value=""></div><button>Add asset</button></form></div></details>
<details><summary>Import YouTube analytics</summary><div class="details-body"><form method="post" action="/action/upload-analytics" enctype="multipart/form-data"><div class="field"><label>Video slug</label><input name="slug" value="{esc(slug)}" required></div><div class="field"><label>YouTube video ID</label><input name="video_id"></div><div class="field"><input type="file" name="file" accept=".csv" required></div><button>Import CSV</button></form></div></details>
'''
    return f'''<section class="grid"><div class="span5">{forms}</div><div class="span7"><section class="panel"><h2>Ideas</h2>{rows_table(["Score","Status","Title","Hook"],[[row.get("score"),row.get("status"),row.get("title"),row.get("hook")] for row in ideas[:12]],"No ideas.")}</section><section class="panel" style="margin-top:14px"><h2>Money and time</h2>{rows_table(["Currency","Revenue","Expense","Profit"],money_rows,"No money entries.")}<p>Total creator-hours: <strong>{hours['total_hours']:.2f}</strong></p></section><section class="panel" style="margin-top:14px"><h2>Latest analytics</h2>{analytics_html}</section><section class="panel" style="margin-top:14px"><h2>Calendar and social</h2>{rows_table(["Target","Status","Title"],[[row.get("target_publish"),row.get("status"),row.get("working_title")] for row in calendar[:10]],"No calendar items.")}{rows_table(["Target","Platform","Status"],[[row.get("target_publish"),row.get("platform"),row.get("status")] for row in social[:10]],"No social items.")}</section><section class="panel" style="margin-top:14px"><h2>Assets and opportunities</h2>{rows_table(["Type","Name","Status"],[[row.get("type"),row.get("name"),row.get("reuse_status")] for row in assets[:10]],"No assets.")}{rows_table(["Status","Brand","Value","Currency"],[[row.get("status"),row.get("brand"),row.get("value"),row.get("currency")] for row in deals[:10]],"No opportunities.")}</section></div></section>'''

def channel_page(root: Path) -> str:
    docs = [
        ("channel/channel-strategy.md", "Channel strategy", "Positioning, audience, formats and growth choices."),
        ("channel/brand-voice.md", "Brand voice", "Public language, tone, spelling and boundaries."),
        ("channel/series-bible.md", "Series bible", "Canon, recurring rules, characters, locations and continuity."),
    ]
    cards = []
    for path, label, help_text in docs:
        text = read_root_text(root, path)
        cards.append(f'''<section class="panel"><div class="eyebrow">{esc(path)}</div><h2>{esc(label)}</h2><p>{esc(help_text)}</p><form method="post" action="/action/save-root-file"><input type="hidden" name="path" value="{esc(path)}"><textarea class="editor" name="content">{esc(text)}</textarea><button class="primary">Save {esc(label)}</button></form></section>''')
    return "".join(cards)


def settings_page(root: Path) -> str:
    s = load_settings(root, include_secret=False)
    apps = s.get("apps", {})
    runners = s.get("runners", {})
    statuses = s.get("runner_status", {})

    def checked(value: Any) -> str:
        return "checked" if value else ""

    def runner_options(selected: str) -> str:
        return "".join(
            f'<option value="{esc(name)}" {"selected" if name == selected else ""}>{esc(label)}</option>'
            for name, label in RUNNER_LABELS.items()
        )

    def reasoning_options(model: str, selected: str) -> str:
        profile = reasoning_profile(model)
        more = set(profile.get("more_reasoning", []))
        normal = []
        extra = []
        for level in profile["levels"]:
            details = REASONING_LEVELS[level]
            suffix = " (default)" if level == profile.get("default") else ""
            option = f'<option value="{esc(level)}" {"selected" if level == selected else ""}>{esc(details["label"] + suffix)}</option>'
            (extra if level in more else normal).append(option)
        grouped = '<optgroup label="More reasoning…">' + "".join(extra) + "</optgroup>" if extra else ""
        return "".join(normal) + grouped

    known_models = "".join(f'<option value="{esc(model)}"></option>' for model in MODEL_REASONING_PROFILES)
    codex = runners.get("codex", {})
    opencode = runners.get("opencode", {})
    openai = runners.get("openai", {})
    codex_status = statuses.get("codex", {})
    opencode_status = statuses.get("opencode", {})

    route = s.get("routes", {})
    routing = f'''<section class="panel"><div class="eyebrow">Runner Manager</div><h2>Automatic task routing</h2><p>The Studio Assistant prepares the project context and deterministic checks first, sends a focused generation request, validates the returned proposal, and performs at most one automatic repair pass. You always review before applying.</p><div class="form-grid"><div class="field"><label>Routing mode</label><select name="routing_mode"><option value="automatic" {'selected' if s.get('routing_mode') != 'fixed' else ''}>Automatic by task</option><option value="fixed" {'selected' if s.get('routing_mode') == 'fixed' else ''}>Always use one runner</option></select></div><div class="field"><label>Fixed runner</label><select name="fixed_runner">{runner_options(str(s.get('fixed_runner') or 'codex'))}</select></div><div class="field"><label>Creative development</label><select name="route_creative">{runner_options(str(route.get('creative') or 'codex'))}</select><small>Direction, story and script.</small></div><div class="field"><label>Production support</label><select name="route_production">{runner_options(str(route.get('production') or 'opencode'))}</select><small>Production, edit, release and learning.</small></div><div class="field"><label>Audit and repair</label><select name="route_audit">{runner_options(str(route.get('audit') or 'opencode'))}</select></div><div class="field"><label>Fallback order</label><input name="fallback_order" value="{esc(','.join(s.get('fallback_order', [])))}"><small>Comma-separated: codex, opencode, openai.</small></div><div class="field"><label>Runner terminal host</label><select name="runner_terminal_host"><option value="windows_terminal" {'selected' if s.get('runner_terminal_host', 'windows_terminal') == 'windows_terminal' else ''}>Windows Terminal (recommended)</option><option value="powershell" {'selected' if s.get('runner_terminal_host') == 'powershell' else ''}>Standalone PowerShell window</option></select><small>Both options run PowerShell 7.6.3+ as Administrator.</small><label style="display:block;margin-top:10px"><input style="width:auto" type="checkbox" name="codex_full_output" {checked(s.get('codex_full_output', True))}> Show the full native Codex output</label><small>Checked: unfiltered Codex terminal output. Unchecked: compact readable events.</small></div></div><label><input style="width:auto" type="checkbox" name="fallback_enabled" {checked(s.get('fallback_enabled'))}> Try enabled fallback runners if the preferred runner fails</label><br><label><input style="width:auto" type="checkbox" name="web_search_default" {checked(s.get('web_search_default'))}> Allow web research by default</label><br><label><input style="width:auto" type="checkbox" name="visible_runner_terminal" {checked(s.get('visible_runner_terminal', True))}> Open an Administrator runner terminal, show live CLI activity, and keep it open after completion</label></section>'''

    codex_panel = f'''<section class="panel span6"><div class="hero-top"><div><div class="eyebrow">Primary creative runner</div><h2>Codex CLI</h2></div><span class="tag {'ok' if codex_status.get('installed') else 'bad'}">{'Installed' if codex_status.get('installed') else 'Not found'}</span></div><p>Uses <code>codex exec</code> in a disposable workspace with no project files mounted. Codex receives the prepared context directly and cannot wander through the repository. ChatGPT sign-in uses your Codex subscription limits; API-key sign-in uses API billing.</p><label><input style="width:auto" type="checkbox" name="runner_codex_enabled" {checked(codex.get('enabled'))}> Enabled</label><div class="field"><label>Executable</label><input name="runner_codex_command" value="{esc(codex.get('command','codex'))}"></div><div class="form-grid"><div class="field"><label>Model</label><input id="codex-model" data-reasoning-model="codex-reasoning" name="runner_codex_model" list="assistant-models" value="{esc(codex.get('model','gpt-5.6-luna'))}"></div><div class="field"><label>Reasoning</label><select id="codex-reasoning" name="runner_codex_reasoning">{reasoning_options(str(codex.get('model')), str(codex.get('reasoning_effort')))}</select></div><div class="field"><label>Timeout, seconds</label><input type="number" min="300" max="14400" step="300" name="runner_codex_timeout" value="{esc(codex.get('timeout_seconds',3600))}"><small>3600 seconds is recommended for max-reasoning story runs. Every run is archived under <code>exports/runner-runs</code>.</small></div></div></section>'''

    opencode_panel = f'''<section class="panel span6"><div class="hero-top"><div><div class="eyebrow">Secondary flexible runner</div><h2>OpenCode CLI</h2></div><span class="tag {'ok' if opencode_status.get('installed') else 'bad'}">{'Installed' if opencode_status.get('installed') else 'Not found'}</span></div><p>Uses <code>opencode run</code> with the bundled focused <code>studio-assistant</code> agent. Repository browsing, commands and edits are disabled; OpenCode uses whichever provider you connect in its own setup.</p><label><input style="width:auto" type="checkbox" name="runner_opencode_enabled" {checked(opencode.get('enabled'))}> Enabled</label><div class="field"><label>Executable</label><input name="runner_opencode_command" value="{esc(opencode.get('command','opencode'))}"></div><div class="form-grid"><div class="field"><label>Model</label><input name="runner_opencode_model" value="{esc(opencode.get('model',''))}" placeholder="provider/model — blank uses OpenCode default"></div><div class="field"><label>Variant / reasoning</label><input name="runner_opencode_variant" value="{esc(opencode.get('variant',''))}" placeholder="provider-specific, optional"></div><div class="field"><label>Agent</label><input name="runner_opencode_agent" value="{esc(opencode.get('agent','studio-assistant'))}"></div><div class="field"><label>Timeout, seconds</label><input type="number" min="300" max="14400" step="300" name="runner_opencode_timeout" value="{esc(opencode.get('timeout_seconds',3600))}"></div></div></section>'''

    api_panel = f'''<section class="panel"><div class="hero-top"><div><div class="eyebrow">Optional metered fallback</div><h2>OpenAI API</h2></div><span class="tag {'ok' if openai.get('has_api_key') else 'bad'}">{'Key available' if openai.get('has_api_key') else 'No key'}</span></div><p>This remains separate from ChatGPT Plus and Codex subscription usage.</p><label><input style="width:auto" type="checkbox" name="runner_openai_enabled" {checked(openai.get('enabled'))}> Enabled</label><div class="form-grid"><div class="field wide"><label>API key</label><input type="password" name="api_key" placeholder="Leave blank to keep current key"></div><div class="field"><label>Base URL</label><input name="runner_openai_base_url" value="{esc(openai.get('base_url'))}"></div><div class="field"><label>Model</label><input id="openai-model" data-reasoning-model="openai-reasoning" name="runner_openai_model" list="assistant-models" value="{esc(openai.get('model'))}"></div><div class="field"><label>Reasoning</label><select id="openai-reasoning" name="runner_openai_reasoning">{reasoning_options(str(openai.get('model')), str(openai.get('reasoning_effort')))}</select></div><div class="field"><label>Timeout, seconds</label><input type="number" min="60" name="runner_openai_timeout" value="{esc(openai.get('timeout_seconds',600))}"></div></div><label><input style="width:auto" type="checkbox" name="remember_api_key" {checked(openai.get('remember_api_key'))}> Remember key locally</label><br><label><input style="width:auto" type="checkbox" name="clear_api_key"> Clear saved/session key</label></section>'''

    app_fields = "".join(
        f'''<div class="panel span6"><h2>{esc(info.get('label', app_id))}</h2><div class="field"><label>Executable or command</label><input name="app_{esc(app_id)}_command" value="{esc(info.get('command', ''))}" placeholder="C:\\Path\\Application.exe"></div><div class="field"><label>Working directory (optional)</label><input name="app_{esc(app_id)}_cwd" value="{esc(info.get('working_directory', ''))}"></div></div>'''
        for app_id, info in apps.items()
    )

    controls = f'''<section class="grid"><div class="panel span6"><h2>Codex controls</h2><div class="actions">{form('/action/runner-install','Install / update Codex','<input type="hidden" name="runner" value="codex">',css='subtle')}{form('/action/runner-setup','Sign in with Codex','<input type="hidden" name="runner" value="codex">')}{form('/action/runner-test','Test Codex','<input type="hidden" name="runner" value="codex">',css='subtle')}</div><p class="small muted">Sign-in opens the official browser authentication flow without requiring you to type in a terminal.</p></div><div class="panel span6"><h2>OpenCode controls</h2><div class="actions">{form('/action/runner-install','Install / update OpenCode','<input type="hidden" name="runner" value="opencode">',css='subtle')}{form('/action/runner-setup','Open provider setup','<input type="hidden" name="runner" value="opencode">')}{form('/action/runner-test','Test OpenCode','<input type="hidden" name="runner" value="opencode">',css='subtle')}</div><p class="small muted">Provider setup launches OpenCode Web on <code>127.0.0.1:4096</code>; connect a provider there, then return here.</p></div></section>'''

    profiles_json = json.dumps(MODEL_REASONING_PROFILES, ensure_ascii=False).replace("</", "<\\/")
    levels_json = json.dumps(REASONING_LEVELS, ensure_ascii=False).replace("</", "<\\/")
    script = f'''<script>(()=>{{const profiles={profiles_json};const levels={levels_json};const generic={{default:'medium',levels:['low','medium','high','xhigh'],more_reasoning:[]}};function render(model){{const select=document.getElementById(model.dataset.reasoningModel);if(!select)return;const profile=profiles[model.value.trim()]||generic;const previous=select.value;const chosen=profile.levels.includes(previous)?previous:profile.default;select.replaceChildren();const more=new Set(profile.more_reasoning||[]);const add=(parent,level)=>{{const o=document.createElement('option');o.value=level;o.textContent=levels[level].label+(level===profile.default?' (default)':'');parent.appendChild(o)}};profile.levels.filter(x=>!more.has(x)).forEach(x=>add(select,x));if(more.size){{const g=document.createElement('optgroup');g.label='More reasoning…';profile.levels.filter(x=>more.has(x)).forEach(x=>add(g,x));select.appendChild(g)}}select.value=chosen}}document.querySelectorAll('[data-reasoning-model]').forEach(model=>{{model.addEventListener('change',()=>render(model));model.addEventListener('blur',()=>render(model))}})}})();</script>'''

    return f'''<datalist id="assistant-models">{known_models}</datalist><form method="post" action="/action/settings">{routing}<section class="grid">{codex_panel}{opencode_panel}</section>{api_panel}<h2 style="margin-top:24px">Application launchers</h2><section class="grid">{app_fields}</section><div class="sticky-actions"><button class="primary">Save all settings</button></div></form>{controls}{script}'''


def diagnostics_page(root: Path, jobs: list[dict[str,Any]]) -> str:
    checks=validate_repository(root);log=root/'exports/studio-server.log';logtext=log.read_text(encoding='utf-8',errors='replace')[-20000:] if log.is_file() else 'No server errors recorded.'
    settings=load_settings(root,include_secret=False);deps=importlib.util.find_spec('googleapiclient') is not None
    statuses=settings.get('runner_status',{})
    env_rows=[['Python',sys.version.split()[0]],['Platform',platform.platform()],['Studio root',str(root)],['YouTube support','installed' if deps else 'not installed']]
    runner_rows=[]
    for name,label in RUNNER_LABELS.items():
        status=statuses.get(name,{})
        if name=='openai':
            state='ready' if status.get('available') else 'API key missing or disabled'
            detail='Direct API fallback'
        else:
            state='installed' if status.get('installed') else 'not found'
            detail=status.get('command') or status.get('detail','')
        runner_rows.append([label,state,detail])
    job_rows=[[j.get('label'),j.get('status'),j.get('message') or j.get('error') or '',j.get('updated_at','')] for j in jobs]
    archive_root=root/'exports/runner-runs'; archive_rows=[]
    if archive_root.is_dir():
        for metadata_path in sorted(archive_root.glob('*/metadata.json'), key=lambda item:item.stat().st_mtime, reverse=True)[:10]:
            try:
                record=json.loads(metadata_path.read_text(encoding='utf-8'))
            except (OSError,json.JSONDecodeError):
                continue
            terminal_result=metadata_path.parent/'terminal-result.json'
            if record.get('status')=='running' and terminal_result.is_file():
                try:
                    terminal_record=json.loads(terminal_result.read_text(encoding='utf-8-sig'))
                    record['status']=terminal_record.get('status',record.get('status'))
                    record['session_id']=terminal_record.get('session_id',record.get('session_id'))
                except (OSError,json.JSONDecodeError):
                    pass
            session=str(record.get('session_id') or '')
            recovery='RESUME-CODEX.ps1 available' if record.get('resume_script') else ('final-proposal.json' if record.get('status')=='success' else 'logs preserved')
            archive_rows.append([metadata_path.parent.name,record.get('status','unknown'),session or '—',recovery])
    archive_table=rows_table(['Run','Status','Session','Recovery'],archive_rows,'No archived runner runs yet.')
    return f'''<section class="grid"><div class="panel span5"><h2>Environment</h2>{rows_table(['Item','Value'],env_rows,'')}<h2 style="margin-top:20px">AI runners</h2>{rows_table(['Runner','State','Detail'],runner_rows,'')}</div><div class="panel span7"><h2>Repository checks</h2>{_checks_html(checks)}<div class="actions">{form('/action/maintain','Run maintenance')}{form('/action/open-root','Open studio folder',css='subtle')}</div></div></section><section class="panel" style="margin-top:14px"><h2>Tasks</h2>{rows_table(['Task','Status','Detail','Updated'],job_rows,'No background tasks in this session.')}</section><section class="panel" style="margin-top:14px"><h2>Runner archives</h2><p class="small muted">Full prompts, native output, stderr, metadata, final proposals and resumable Codex sessions are kept in <code>exports/runner-runs</code>.</p>{archive_table}</section><details><summary>Server log</summary><div class="details-body"><textarea readonly style="min-height:400px">{esc(logtext)}</textarea></div></details>'''


def render_page(root: Path, page: str = "home", params: dict[str,str] | None = None, message: str = "", error: bool = False, jobs: list[dict[str,Any]] | None = None) -> str:
    params = params or {}
    jobs = jobs or []
    if page == 'proposal':
        return layout(root, page, 'Assistant proposal', 'Review before applying.', proposal_page(root, params.get('id', '')), message, error, jobs)
    if page == 'file':
        return layout(root, 'workspace', 'File editor', 'Advanced browser editing.', file_page(root, params.get('path', '')), message, error, jobs)

    # Render only the requested page. The previous eager dictionary evaluated
    # every page on every request, multiplying filesystem scans and allowing an
    # error in an unrelated page to break ordinary navigation.
    pages = {
        'home': ('Production', 'One active video, one next action.', home_page),
        'workspace': ('Workspace', 'Write, generate, validate, approve and advance the current phase.', workspace_page),
        'media': ('Files & media', 'Upload and manage every production asset from the browser.', media_page),
        'release': ('Release', 'Package and publish without leaving the dashboard.', release_page),
        'operations': ('Operations', 'Ideas, time, money, analytics and reusable knowledge.', operations_page),
        'channel': ('Channel', 'Edit channel strategy, voice and canon without leaving the dashboard.', channel_page),
        'settings': ('Settings', 'Configure AI autonomy and one-click application launchers.', settings_page),
        'diagnostics': ('Diagnostics', 'Health checks, maintenance, logs and background tasks.', lambda value: diagnostics_page(value, jobs)),
    }
    selected_page = page if page in pages else 'home'
    title, subtitle, renderer = pages[selected_page]
    content = renderer(root)
    return layout(root, selected_page, title, subtitle, content, message, error, jobs)


def dashboard_html(root: Path, interactive: bool = True, message: str = "") -> str:
    return render_page(root,"home",message=message)


def generate_dashboard(root: Path, output: Path | None = None) -> Path:
    output=output or (root/'exports'/'studio-dashboard.html')
    if not output.is_absolute():output=root/output
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(render_page(root,'home'),encoding='utf-8',newline='\n')
    return output
