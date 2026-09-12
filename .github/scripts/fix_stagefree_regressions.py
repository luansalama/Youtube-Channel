from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_once(rel: str, old: str, new: str) -> None:
    path = ROOT / rel
    text = path.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'{rel}: expected one match, got {count}: {old[:120]!r}')
    path.write_text(text.replace(old, new, 1), encoding='utf-8', newline='\n')


# Applying a cutlist updates harness-owned video state. Refresh that fingerprint so
# the subsequent explicit lock detects *new* drift, not our own applied_at write.
replace_once(
    'cstudio/video_cutlists.py',
    '''    C.write_json(_video_path(root, slug, video_id), video)\n    draft["status"] = "applied"\n    draft["applied_at"] = video["cutlist"]["applied_at"]\n    C.write_json(draft_path(root, slug, video_id), draft)\n''',
    '''    video_path = _video_path(root, slug, video_id)\n    C.write_json(video_path, video)\n    draft["status"] = "applied"\n    draft["applied_at"] = video["cutlist"]["applied_at"]\n    draft.setdefault("evidence", {})["video.json"] = C.sha256_file(video_path)\n    C.write_json(draft_path(root, slug, video_id), draft)\n''',
)

# The human lock must be recorded before assembly is persisted. Building the
# timeline object is harmless/read-only; writing assembly happens after approval.
replace_once(
    'cstudio/video_cutlists.py',
    '''    assembly_dir = os.path.join(vdir, ".studio", "internal", "assembly")\n    os.makedirs(assembly_dir, exist_ok=True)\n    C.write_json(os.path.join(assembly_dir, "timeline.json"), timeline)\n    with open(os.path.join(vdir, "07-assembly", "assembly.md"), "w", encoding="utf-8", newline="\\n") as fh:\n        fh.write(f"# Assembly — {video_id}\\n\\nTimeline derivada deterministicamente da cutlist revisada via `build_timeline()`.\\n\\nEventos: {len(timeline.get('events') or [])}\\nDuração total: {timeline.get('total_seconds')} s\\n")\n\n    approval = _approve_cutlist_lock(root, slug, by=by, note=note)\n''',
    '''    approval = _approve_cutlist_lock(root, slug, by=by, note=note)\n\n    assembly_dir = os.path.join(vdir, ".studio", "internal", "assembly")\n    os.makedirs(assembly_dir, exist_ok=True)\n    C.write_json(os.path.join(assembly_dir, "timeline.json"), timeline)\n    with open(os.path.join(vdir, "07-assembly", "assembly.md"), "w", encoding="utf-8", newline="\\n") as fh:\n        fh.write(f"# Assembly — {video_id}\\n\\nTimeline derivada deterministicamente da cutlist revisada via `build_timeline()`.\\n\\nEventos: {len(timeline.get('events') or [])}\\nDuração total: {timeline.get('total_seconds')} s\\n")\n''',
)

# _send uses `code`, not `status`.
replace_once(
    'cstudio/server.py',
    '''return self._send(json.dumps({"ok": False, "error": "manual phase advancement has been retired"}), "application/json; charset=utf-8", status=410)''',
    '''return self._send(json.dumps({"ok": False, "error": "manual phase advancement has been retired"}), "application/json; charset=utf-8", code=410)''',
)

# Remove the last dead UI branch that could still render an advance form if the
# old helper were called by a legacy deep-link.
replace_once(
    'cstudio/dashboard.py',
    '''    else:\n        title, desc, tone = "Fase concluída", "As verificações necessárias passaram. Avançar mantém todas as invariantes e fingerprints do harness.", "ok"\n        action = (\n            '<form method="post" action="/action/advance">'\n            f'{_csrf(csrf_token)}<input type="hidden" name="slug" value="{_e(slug)}">'\n            '<button class="button button-primary" type="submit">Avançar para a próxima fase</button></form>'\n        )\n''',
    '''    else:\n        title, desc, tone = "Pronto para continuar", "Continue pela área que produz o próximo artefato útil; não existe avanço manual de fase.", "ok"\n        action = f'<a class="button button-primary" href="/?page=videos&slug={_q(slug)}">Abrir Vídeos</a>'\n''',
)

# Update the pre-existing dashboard regression to assert the intentionally removed
# technical stage panel is absent.
replace_once(
    'tests/test_dashboard_ui.py',
    '''    assert "Estado técnico do harness" in page\n''',
    '''    assert "Estado técnico do harness" not in page\n''',
)

print('stage-free regressions fixed')
