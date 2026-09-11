import json
import shutil
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from cstudio import core as C
from cstudio import dashboard as D
from cstudio.server import Handler


REPO = Path(__file__).resolve().parents[1]


def _harness(tmp_path):
    root = tmp_path / "harness"
    shutil.copytree(REPO / "studio", root / "studio")
    shutil.copytree(REPO / "templates", root / "templates")
    C.create_production(
        str(root),
        "UI test",
        slug="ui-test",
        source_url="https://www.twitch.tv/alanzoka/videos",
    )
    return str(root)


def test_dashboard_uses_external_assets_and_csrf(tmp_path):
    root = _harness(tmp_path)
    page = D.render(root, "production", "ui-test", csrf_token="csrf-test")
    assert '/static/dashboard.css?v=9' in page
    assert '/static/dashboard.js?v=9' in page
    assert '<script>' not in page
    assert 'style=' not in page
    assert 'name="csrf_token" value="csrf-test"' in page
    assert "Passo 1 · Fontes" in page
    assert "dark" not in page.lower() or 'content="dark"' in page


def test_twitch_page_uses_partial_live_run_polling(tmp_path):
    root = _harness(tmp_path)
    page = D.render(root, "twitch", "ui-test", csrf_token="csrf-test")
    assert "Twitch Ingest" in page
    assert '/ui/twitch-run?slug=ui-test' in page
    assert "location.reload" not in page
    assert "name='threads'" in page
    assert ">8 workers</option>" in page
    fragment = D.render_twitch_run(root, "ui-test")
    assert 'data-twitch-live' in fragment
    assert 'data-running="false"' in fragment


def test_dashboard_static_assets_are_packaged_sources():
    css = REPO / "cstudio" / "static" / "dashboard.css"
    js = REPO / "cstudio" / "static" / "dashboard.js"
    assert css.is_file() and css.stat().st_size > 10_000
    assert js.is_file() and js.stat().st_size > 2_000
    text = js.read_text(encoding="utf-8")
    assert "fetch(endpoint" in text
    assert "location.reload" not in text
    assert "prefers-reduced-motion" in text



def test_dashboard_primary_nav_is_pipeline_oriented(tmp_path):
    root = _harness(tmp_path)
    page = D.render(root, "production", "ui-test", csrf_token="csrf-test")
    assert ">Produção</span>" in page
    assert ">Fontes</span>" in page
    assert ">Vídeos</span>" in page
    assert ">Premiere</span>" in page
    assert "Captura Twitch</span>" not in page
    assert "YouTube Mirrors</span>" not in page
    assert "Estado técnico do harness" in page
    assert "pool compartilhado" in page
    assert "Gerenciar produções" in page


def test_videos_page_models_one_proposal_per_video_and_answers_inline(tmp_path):
    from cstudio import pipeline as PL
    from cstudio import video_plans as VP

    root = _harness(tmp_path)
    vdir = Path(root) / "productions" / "ui-test"
    rel = ".studio/internal/ingest/twitch/alanzoka/discovery/123.json"
    path = vdir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"id":"123","title":"Live teste","timestamps":{"created_at":"2026-09-01T12:00:00Z"},"duration":{"seconds":14400}}), encoding="utf-8")
    PL.register_asset(root, "ui-test", "twitch-vod-123", "vod-metadata", rel)
    twitch_rel = ".studio/internal/ingest/twitch/media/123/123.mp4"
    twitch_media = vdir / twitch_rel
    twitch_media.parent.mkdir(parents=True, exist_ok=True)
    twitch_media.write_bytes(b"fake-twitch-media")
    PL.register_asset(root, "ui-test", "twitch-video-123", "video-source", twitch_rel)
    from cstudio import source_media as SM
    tr_paths = SM.transcript_paths(root, "ui-test", "twitch-video-123")
    tr = {"asset_id":"twitch-video-123","source_identity":"twitch-vod:123","model":"large-v3-turbo","language":"pt","word_timestamps":False,"timestamp_mode":"segment","duration_seconds":14400,"segment_count":1,"word_count":4,"segments":[{"start":1,"end":2,"text":"momento engraçado da live","words":[]}]}
    (vdir / tr_paths["json"]).write_text(json.dumps(tr), encoding="utf-8")
    (vdir / tr_paths["windows"]).write_text(json.dumps({"start":0,"end":300,"text":"momento engraçado da live"})+"\n", encoding="utf-8")
    (vdir / tr_paths["text"]).write_text("[00:00:01 --> 00:00:02] momento engraçado da live\n", encoding="utf-8")
    media_rel = ".studio/internal/ingest/youtube/media/alanzoka/yt123/yt123.mp4"
    media = vdir / media_rel
    media.parent.mkdir(parents=True, exist_ok=True)
    media.write_bytes(b"fake-media")
    PL.register_asset(root, "ui-test", "youtube-yt123", "video-source", media_rel)
    assignment = vdir / ".studio" / "internal" / "ingest" / "youtube" / "assignments" / "yt123.json"
    assignment.parent.mkdir(parents=True, exist_ok=True)
    assignment.write_text(json.dumps({"state":"verified","youtube_video_id":"yt123","assigned_vod_ids":["123"],"youtube":{"video_id":"yt123","title":"Master live teste"}}), encoding="utf-8")
    rec = VP.create_video_proposal(root, "ui-test", {
        "summary":"Vídeo de teste",
        "document":"Uma proposta editorial suficientemente detalhada para transformar a live de teste em um vídeo autocontido de aproximadamente dez minutos, sem inventar evidências.",
        "video":{"working_title":"Vídeo teste","premise":"Premissa","editorial_angle":"Humor","target_duration_minutes":{"min":8,"max":15},"selection_criteria":["humor"],"constraints":[]},
        "candidate_moments":[],"questions":["Qual é o foco principal?"],"warnings":[]
    }, source_asset_ids=["twitch-vod-123"], request="Planeje", runner="agy", model="model-x", reasoning_effort="low")
    page = D.render(root, "videos", "ui-test", csrf_token="csrf-test")
    assert "Planejamento editorial" in page
    assert "Parte 1 → Parte 2" in page
    assert 'name="source_asset_ids" value="twitch-vod-123"' in page
    assert "Codex CLI" in page and "OpenCode CLI" in page and "Antigravity CLI" in page
    assert "Qual é o foco principal?" in page
    assert f'name="answer_{rec["questions"][0]["id"]}"' in page
    assert "Salvar respostas · sem IA" in page
    assert "Consolidar Parte 2 com agente" in page
    assert "Aceitar e criar vídeo" in page
    assert '<details class="proposal-inspector" open>' not in page
    assert "transcrição por segmento pronta" in page


def test_composite_pages_render_without_exposing_arbitrary_mcp(tmp_path):
    root = _harness(tmp_path)
    sources = D.render(root, "sources", "ui-test", csrf_token="csrf-test")
    reviews = D.render(root, "reviews", "ui-test", csrf_token="csrf-test")
    premiere = D.render(root, "premiere", "ui-test", csrf_token="csrf-test")
    assert "Capturar VODs e chat" in sources
    assert "Áudio → transcrição" in sources
    assert "Áudio → transcrever selecionados" in sources
    assert "/action/source-batch-audio-transcribe" in sources
    assert "/action/source-batch-download-twitch" in sources
    assert "Baixar sources selecionados" in sources
    assert "Whisper" in sources
    assert "timestamps por segmento" in sources
    assert "Revisões técnicas" in reviews
    assert "Diagnóstico do Premiere MCP" in premiere
    assert "/action/premiere-doctor" in premiere
    assert "/action/premiere-media-manifest" in premiere
    assert "Preparar mídia para edição" in premiere
    assert "/action/premiere-export" not in premiere  # no timeline yet
    assert "POST /mcp/call" not in premiere


def test_reviews_make_proposal_openable_before_apply(tmp_path):
    from cstudio import proposals as P

    root = _harness(tmp_path)
    proposal = P.create_proposal(
        root,
        "ui-test",
        {
            "summary": "Configuração editorial revisável",
            "document": (
                "Objetivo editorial: preparar cortes de uma transmissão para revisão humana.\n\n"
                "Fontes: usar somente assets registrados pelo harness e manter qualquer lacuna explícita.\n\n"
                "Restrições: não publicar, não aprovar gates e não inventar direitos ou evidência.\n"
            ),
            "files": {},
            "questions": ["Qual duração alvo do vídeo final?"],
            "warnings": ["Direitos ainda precisam de confirmação humana."],
        },
        runner="codex",
        stage_id="config",
        model="gpt-test",
        reasoning_effort="low",
    )
    page = D.render(root, "reviews", "ui-test", csrf_token="csrf-test")
    assert proposal["id"] in page
    assert "Abrir proposta" in page
    assert "diff + conteúdo completo" in page
    assert "O que muda" in page
    assert "Ver conteúdo proposto completo" in page
    assert "Qual duração alvo do vídeo final?" in page
    assert "Direitos ainda precisam de confirmação humana." in page
    assert "gpt-test" in page
    # Apply/discard only live inside the expandable review inspector, not as
    # immediate top-level card actions.
    assert page.index("Abrir proposta") < page.index("Aplicar proposta")



def test_server_serves_static_assets_csp_and_enforces_form_csrf(tmp_path):
    root = _harness(tmp_path)
    Handler.root = root
    Handler.csrf_token = "csrf-server-test"
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urllib.request.urlopen(base + "/?page=production&slug=ui-test") as response:
            page = response.read().decode("utf-8")
            csp = response.headers.get("Content-Security-Policy", "")
        assert "script-src 'self'" in csp
        assert "unsafe-inline" not in csp
        assert 'name="csrf_token" value="csrf-server-test"' in page

        with urllib.request.urlopen(base + "/static/dashboard.css") as response:
            assert response.headers.get_content_type() == "text/css"
            assert len(response.read()) > 10_000

        bad = urllib.request.Request(
            base + "/action/maintain",
            data=urllib.parse.urlencode({"slug": "ui-test"}).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            urllib.request.urlopen(bad)
            assert False, "POST sem CSRF deveria falhar"
        except urllib.error.HTTPError as exc:
            assert exc.code == 400

        good = urllib.request.Request(
            base + "/action/maintain",
            data=urllib.parse.urlencode({"slug": "ui-test", "csrf_token": "csrf-server-test"}).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(good) as response:
            assert response.status == 200  # urllib seguiu o 303 para o dashboard
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_agent_job_uses_json_without_navigation_and_server_stays_alive(tmp_path, monkeypatch):
    from cstudio import jobs as J

    root = _harness(tmp_path)
    Handler.root = root
    Handler.csrf_token = "csrf-agent-test"

    def fake_start_job(root_arg, slug, job_type, **params):
        assert root_arg == root
        assert slug == "ui-test"
        assert job_type == "agent-proposal"
        assert params["request"].startswith("Prepare")
        return {"id": "job-test", "status": "running", "type": job_type, "slug": slug}

    monkeypatch.setattr(J, "start_job", fake_start_job)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        payload = json.dumps({
            "csrf_token": "csrf-agent-test",
            "slug": "ui-test",
            "stage": "config",
            "request": "Prepare a configuração editorial mínima para esta produção.",
            "runner": "",
            "model": "",
        }).encode("utf-8")
        req = urllib.request.Request(
            base + "/action/agent-run",
            data=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode("utf-8"))
            assert response.status == 200
            assert data["ok"] is True
            assert data["job"]["id"] == "job-test"

        # A failed/successful agent POST must never take the local HTTP server down.
        with urllib.request.urlopen(base + "/?page=production&slug=ui-test") as response:
            assert response.status == 200
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_source_transcription_job_renders_live_chunk_progress(tmp_path, monkeypatch):
    from cstudio import jobs as J
    from cstudio import pipeline as PL
    from cstudio import source_media as SM

    root = _harness(tmp_path)
    vdir = Path(root) / "productions" / "ui-test"
    rel = ".studio/internal/ingest/twitch/media/123/123.mp4"
    media = vdir / rel
    media.parent.mkdir(parents=True, exist_ok=True)
    media.write_bytes(b"fake-media")
    PL.register_asset(root, "ui-test", "twitch-video-123", "video-source", rel)
    paths = SM.transcript_paths(root, "ui-test", "twitch-video-123")
    progress_path = vdir / paths["progress"]
    progress_path.write_text(json.dumps({
        "status": "running",
        "asset_id": "twitch-video-123",
        "model": "turbo",
        "chunks_total": 16,
        "chunks_completed": 5,
        "current_chunk": 6,
        "chunk_seconds": 1800,
        "duration_seconds": 28800,
        "processed_seconds": 9000,
        "percent": 31.25,
        "started_at": "2026-09-11T07:00:00Z",
        "updated_at": "2026-09-11T07:12:34Z",
    }), encoding="utf-8")
    job = {
        "id": "job-source-1", "type": "source-transcribe", "status": "running",
        "started_at": "2026-09-11T07:00:00Z", "params": {"asset_id": "twitch-video-123"},
        "result_summary": {},
    }
    monkeypatch.setattr(J, "mark_stale_failed", lambda *args, **kwargs: 0)
    monkeypatch.setattr(J, "list_jobs", lambda *args, **kwargs: [job])
    monkeypatch.setattr(J, "tail_log", lambda *args, **kwargs: "transcript chunk 6/16")
    html = D.render_studio_job(root, "ui-test", "sources")
    assert "Whisper Turbo · transcrevendo" in html
    assert "31.2%" in html
    assert "5/16 chunks" in html
    assert "2h 30m / 8h 00m de mídia" in html
    assert "chunk atual 6/16" in html
    assert 'class="transcription-progress-bar"' in html
    assert 'value="31.2"' in html


def test_part2_card_offers_explicit_same_session_continue(monkeypatch, tmp_path):
    from cstudio import jobs as J

    root = _harness(tmp_path)
    rec = {
        "id": "proposal-resume-1", "status": "pending", "revision": 1,
        "planning_phase": "part2_answers_ready", "runner": "agy",
        "model": "gemini-3.8-flash", "reasoning_effort": "high",
        "summary": "Teste", "document": "Documento editorial detalhado o suficiente para teste.",
        "video": {"working_title": "Teste", "target_duration_minutes": {"min": 8, "max": 15}},
        "questions": [{"id": "q1", "text": "Foco?", "answer": "Humor"}],
        "human_answers": [{"question_id": "q1", "text": "Foco?", "answer": "Humor"}],
        "candidate_moments": [], "warnings": [], "source_snapshot": [],
    }
    monkeypatch.setattr(J, "video_resume_candidate", lambda *args, **kwargs: {
        "job_id": "failed-job-1", "session_id": "opus-session-1234567890",
        "runner": "agy", "model": "claude-opus-4-6", "reasoning_effort": "thinking",
    })
    html = D._video_proposal_card(root, "ui-test", rec, "csrf-test")
    assert "Continuar tentativa anterior" in html
    assert "Continue.</code>" in html
    assert 'name="continue_attempt" value="1"' in html
    assert 'name="resume_job_id" value="failed-job-1"' in html
