import json
import shutil
import sys
import time
from pathlib import Path

from cstudio import core as C
from cstudio import dashboard as D
from cstudio import proposals as P
from cstudio import runners as R

REPO = Path(__file__).resolve().parents[1]


def _root(tmp_path):
    root = tmp_path / "harness"
    shutil.copytree(REPO / "studio", root / "studio")
    shutil.copytree(REPO / "templates", root / "templates")
    C.create_production(str(root), "Runner controls", slug="runner-controls")
    return str(root)


def test_dashboard_exposes_explicit_runner_model_and_reasoning(tmp_path):
    from cstudio import pipeline as PL
    root = _root(tmp_path)
    vdir = Path(root) / "productions" / "runner-controls"
    rel = ".studio/internal/ingest/twitch/test/discovery/111.json"
    path = vdir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"id":"111","title":"Live teste","duration":{"seconds":3600}}), encoding="utf-8")
    PL.register_asset(root, "runner-controls", "twitch-vod-111", "vod-metadata", rel)
    twitch_rel = ".studio/internal/ingest/twitch/media/111/111.mp4"
    twitch_media = vdir / twitch_rel
    twitch_media.parent.mkdir(parents=True, exist_ok=True)
    twitch_media.write_bytes(b"fake-twitch-media")
    PL.register_asset(root, "runner-controls", "twitch-video-111", "video-source", twitch_rel)
    from cstudio import source_media as SM
    tr_paths = SM.transcript_paths(root, "runner-controls", "twitch-video-111")
    transcript = {"asset_id":"twitch-video-111","model":"turbo","language":"pt","word_timestamps":True,"duration_seconds":3600,"segment_count":1,"word_count":3,"segments":[{"start":1,"end":2,"text":"teste de fala","words":[]}]}
    (vdir / tr_paths["json"]).write_text(json.dumps(transcript), encoding="utf-8")
    (vdir / tr_paths["windows"]).write_text(json.dumps({"start":0,"end":300,"text":"teste de fala"})+"\n", encoding="utf-8")
    (vdir / tr_paths["text"]).write_text("[00:00:01 --> 00:00:02] teste de fala\n", encoding="utf-8")
    media_rel = ".studio/internal/ingest/youtube/media/test/yt111/yt111.mp4"
    media = vdir / media_rel
    media.parent.mkdir(parents=True, exist_ok=True)
    media.write_bytes(b"fake-media")
    PL.register_asset(root, "runner-controls", "youtube-yt111", "video-source", media_rel)
    assignment = vdir / ".studio" / "internal" / "ingest" / "youtube" / "assignments" / "yt111.json"
    assignment.parent.mkdir(parents=True, exist_ok=True)
    assignment.write_text(json.dumps({"state":"verified","youtube_video_id":"yt111","assigned_vod_ids":["111"],"youtube":{"video_id":"yt111","title":"Master teste"}}), encoding="utf-8")
    page = D.render(root, "videos", "runner-controls", csrf_token="csrf")
    assert 'name="runner" data-runner-select' in page
    assert 'value="codex" selected' in page
    assert 'name="model" data-model-select' in page
    assert 'value="gpt-6-astra" selected' in page
    assert 'name="reasoning_effort"' in page
    assert '>Low</option>' in page
    assert 'Auto fallback · só infraestrutura' not in page
    assert '>OpenAI API' not in page
    assert 'OpenCode CLI' in page and 'Antigravity CLI' in page


def test_codex_runner_pins_selected_model_and_reasoning(tmp_path, monkeypatch):
    root = _root(tmp_path)
    captured = {}
    proposal = {
        "summary": "config",
        "document": "Configuração editorial explícita e válida. " * 3,
        "files": {},
        "questions": [],
        "warnings": [],
    }
    monkeypatch.setattr(R.shutil, "which", lambda name: f"/fake/{name}")

    def fake_stdin(cmd, cwd, stdin_text, timeout=600, log=None):
        captured["cmd"] = list(cmd)
        captured["stdin"] = stdin_text
        return json.dumps(proposal), ""

    monkeypatch.setattr(R, "_run_cmd_stdin_capture", fake_stdin)
    result = R.execute_runner(
        root,
        "runner-controls",
        "Prepare a configuração editorial mínima e verificável.",
        force_runner="codex",
        model="gpt-5.3-codex",
        reasoning_effort="low",
    )
    cmd = captured["cmd"]
    assert cmd[:4] == ["codex", "exec", "--sandbox", "read-only"]
    assert cmd[cmd.index("--model") + 1] == "gpt-5.3-codex"
    assert 'model_reasoning_effort="low"' in cmd
    assert "Prepare a configuração editorial mínima" not in " ".join(cmd)
    assert "Prepare a configuração editorial mínima" in captured["stdin"]
    assert result["model"] == "gpt-5.3-codex"
    assert result["reasoning_effort"] == "low"


def test_parser_accepts_valid_proposal_amid_multiple_json_objects():
    proposal = {
        "summary": "ok",
        "document": "Configuração editorial válida. " * 3,
        "files": {},
        "questions": [],
        "warnings": [],
    }
    noisy = json.dumps(proposal) + "\nrunner diagnostics\n" + json.dumps({"event": "done"})
    assert P.parse_json_text(noisy)["summary"] == "ok"


def test_stage_normalizer_promotes_target_document_from_files(tmp_path):
    root = _root(tmp_path)
    target = "01-config/config.md"
    full = "Configuração editorial completa e verificável para esta produção. " * 2
    raw = {
        "summary": "configuração",
        "document": "ver arquivo",
        "files": {target: full},
        "questions": [],
        "warnings": [],
    }
    validated = P.validate_proposal(root, "runner-controls", raw, stage_id="config")
    assert validated["document"] == full
    assert target not in validated["files"]


def test_parser_accepts_target_document_in_files_even_without_document_key():
    payload = {
        "summary": "configuração",
        "files": {"01-config/config.md": "Conteúdo editorial completo e seguro. " * 3},
        "questions": [],
        "warnings": [],
    }
    assert P.parse_json_text(json.dumps(payload))["files"]["01-config/config.md"]


def test_auto_does_not_spend_second_runner_on_invalid_proposal(tmp_path, monkeypatch):
    root = _root(tmp_path)
    calls = []
    monkeypatch.setattr(R, "runner_candidates", lambda _root, _stage: ["codex", "opencode"])
    monkeypatch.setattr(R.shutil, "which", lambda name: f"/fake/{name}")

    def fake_stdin(cmd, cwd, stdin_text, timeout=600, log=None):
        calls.append(cmd[0])
        # The runner DID answer; this is a content/contract issue, not availability.
        return json.dumps({
            "summary": "resposta recebida",
            "document": "curto",
            "files": {},
            "questions": [],
            "warnings": [],
        }), ""

    monkeypatch.setattr(R, "_run_cmd_stdin_capture", fake_stdin)
    try:
        R.execute_runner(root, "runner-controls", "Prepare a configuração.")
    except C.StudioError as exc:
        message = str(exc)
    else:
        raise AssertionError("invalid proposal should be reported")
    assert calls == ["codex"]
    assert "Automatic fallback was NOT used" in message
    assert "target document content is too short" in message


def test_auto_falls_back_only_for_infrastructure_and_uses_next_cli_defaults(tmp_path, monkeypatch):
    root = _root(tmp_path)
    calls = []
    monkeypatch.setattr(R, "runner_candidates", lambda _root, _stage: ["codex", "opencode"])
    monkeypatch.setattr(R.shutil, "which", lambda name: f"/fake/{name}")
    proposal = {
        "summary": "config",
        "document": "Configuração editorial explícita e válida. " * 3,
        "files": {},
        "questions": [],
        "warnings": [],
    }

    def fake_stdin(cmd, cwd, stdin_text, timeout=600, log=None):
        calls.append(list(cmd))
        raise R.RunnerInfrastructureError("sandbox unavailable")

    def fake_run_cmd(cmd, cwd, timeout=600, log=None):
        calls.append(list(cmd))
        return json.dumps(proposal)

    monkeypatch.setattr(R, "_run_cmd_stdin_capture", fake_stdin)
    monkeypatch.setattr(R, "_run_cmd", fake_run_cmd)
    result = R.execute_runner(
        root, "runner-controls", "Prepare a configuração.",
        model="gpt-5.3-codex", reasoning_effort="low",
    )
    assert [c[0] for c in calls] == ["codex", "opencode"]
    assert "--model" in calls[0]
    assert calls[1][calls[1].index("--model") + 1] == "opencode/muse-spark-1.3-contributor-free"
    assert calls[1][calls[1].index("--variant") + 1] == "xhigh"
    assert result["runner"] == "opencode"


def test_runner_catalog_defaults_match_requested_cli_profiles():
    ui = R.runner_ui_config(str(REPO), "analysis")
    assert ui["runners"] == ["codex", "opencode", "agy"]
    assert ui["defaults"]["opencode"] == {
        "model": "opencode/muse-spark-1.3-contributor-free",
        "reasoning_effort": "xhigh",
    }
    assert ui["defaults"]["agy"] == {"model": "gemini-3.8-flash", "reasoning_effort": "high"}
    assert ui["model_efforts"]["codex"]["gpt-6-astra"] == ["low", "medium", "high", "xhigh", "max", "ultra"]
    assert ui["model_efforts"]["agy"]["claude-opus-4-6"] == ["thinking"]
    assert ui["model_efforts"]["opencode"]["opencode/mimo-v2.5-free"] == ["default"]


def test_opencode_default_free_profile_pins_muse_xhigh(tmp_path, monkeypatch):
    root = _root(tmp_path)
    captured = {}
    proposal = {
        "summary": "config", "document": "Configuração editorial explícita e válida. " * 3,
        "files": {}, "questions": [], "warnings": [],
    }
    monkeypatch.setattr(R.shutil, "which", lambda name: f"/fake/{name}")
    def fake_run_cmd(cmd, cwd, timeout=600, log=None):
        captured["cmd"] = list(cmd); return json.dumps(proposal)
    monkeypatch.setattr(R, "_run_cmd", fake_run_cmd)
    result = R.execute_runner(root, "runner-controls", "Prepare a configuração.", force_runner="opencode")
    cmd = captured["cmd"]
    assert cmd[cmd.index("--model") + 1] == "opencode/muse-spark-1.3-contributor-free"
    assert cmd[cmd.index("--variant") + 1] == "xhigh"
    assert result["reasoning_effort"] == "xhigh"


def test_opencode_model_managed_reasoning_omits_variant(tmp_path, monkeypatch):
    root = _root(tmp_path)
    captured = {}
    proposal = {
        "summary": "config", "document": "Configuração editorial explícita e válida. " * 3,
        "files": {}, "questions": [], "warnings": [],
    }
    monkeypatch.setattr(R.shutil, "which", lambda name: f"/fake/{name}")
    def fake_run_cmd(cmd, cwd, timeout=600, log=None):
        captured["cmd"] = list(cmd); return json.dumps(proposal)
    monkeypatch.setattr(R, "_run_cmd", fake_run_cmd)
    R.execute_runner(root, "runner-controls", "Prepare a configuração.", force_runner="opencode",
                     model="opencode/mimo-v2.5-free", reasoning_effort="default")
    assert "--variant" not in captured["cmd"]


def test_agy_gemini_family_maps_reasoning_to_current_model_slug(tmp_path, monkeypatch):
    root = _root(tmp_path)
    captured = {}
    proposal = {
        "summary": "config", "document": "Configuração editorial explícita e válida. " * 3,
        "files": {}, "questions": [], "warnings": [],
    }
    monkeypatch.setattr(R.shutil, "which", lambda name: f"/fake/{name}")
    def fake_agy(cmd, cwd, prompt, timeout=600, log=None):
        captured["cmd"] = list(cmd)
        captured["prompt"] = prompt
        return {"status": "SUCCESS", "response": json.dumps(proposal), "conversation_id": "agy-stage-1"}
    monkeypatch.setattr(R, "_run_agy_stream", fake_agy)
    result = R.execute_runner(root, "runner-controls", "Prepare a configuração.", force_runner="agy")
    cmd = captured["cmd"]
    assert cmd[cmd.index("--model") + 1] == "gemini-3.8-flash-high"
    assert "--effort" not in cmd
    assert cmd[cmd.index("--input-format") + 1] == "stream-json"
    assert cmd[cmd.index("--output-format") + 1] == "stream-json"
    assert "Prepare a configuração." not in " ".join(cmd)
    assert "Prepare a configuração." in captured["prompt"]
    assert result["model"] == "gemini-3.8-flash"
    assert result["reasoning_effort"] == "high"


def test_opencode_catalog_is_free_only_snapshot():
    models = R.RUNNER_MODEL_SUGGESTIONS["opencode"]
    assert models == [
        "opencode/muse-spark-1.3-contributor-free",
        "opencode/ling-3.0-flash-fin-free",
        "opencode/nemotron-3.5-lightning-free",
        "opencode/muse-spark-1.2-contributor-free",
        "opencode/nemotron-3-ultra-free",
        "opencode/mimo-v2.5-free",
    ]
    assert all("claude" not in model and "gpt-" not in model for model in models)


def test_codex_ultra_is_available_only_on_supported_catalog_models():
    assert "ultra" in R.RUNNER_MODEL_EFFORTS["codex"]["gpt-6-astra"]
    assert "ultra" in R.RUNNER_MODEL_EFFORTS["codex"]["gpt-5.6-sol"]
    assert "ultra" in R.RUNNER_MODEL_EFFORTS["codex"]["gpt-5.6-terra"]
    assert "ultra" not in R.RUNNER_MODEL_EFFORTS["codex"]["gpt-5.6-luna"]
    assert "max" not in R.RUNNER_MODEL_EFFORTS["codex"]["gpt-5.5"]


def test_agy_fixed_thinking_model_omits_effort_flag(tmp_path, monkeypatch):
    root = _root(tmp_path)
    captured = {}
    proposal = {
        "summary": "config", "document": "Configuração editorial explícita e válida. " * 3,
        "files": {}, "questions": [], "warnings": [],
    }
    monkeypatch.setattr(R.shutil, "which", lambda name: f"/fake/{name}")
    def fake_agy(cmd, cwd, prompt, timeout=600, log=None):
        captured["cmd"] = list(cmd)
        captured["prompt"] = prompt
        return {"status": "SUCCESS", "response": json.dumps(proposal)}
    monkeypatch.setattr(R, "_run_agy_stream", fake_agy)
    result = R.execute_runner(root, "runner-controls", "Prepare a configuração.", force_runner="agy",
                              model="claude-opus-4-6", reasoning_effort="thinking")
    cmd = captured["cmd"]
    assert cmd[cmd.index("--model") + 1] == "claude-opus-4-6-thinking"
    assert "--effort" not in cmd
    assert result["reasoning_effort"] == "thinking"


def test_agy_low_uses_exact_tiered_model_slug_without_effort_override(tmp_path, monkeypatch):
    root = _root(tmp_path)
    captured = {}
    proposal = {
        "summary": "config", "document": "Configuração editorial explícita e válida. " * 3,
        "files": {}, "questions": [], "warnings": [],
    }
    monkeypatch.setattr(R.shutil, "which", lambda name: f"/fake/{name}")
    def fake_agy(cmd, cwd, prompt, timeout=600, log=None):
        captured["cmd"] = list(cmd)
        captured["prompt"] = prompt
        return {"status": "SUCCESS", "response": json.dumps(proposal)}
    monkeypatch.setattr(R, "_run_agy_stream", fake_agy)
    R.execute_runner(root, "runner-controls", "Prepare a configuração.", force_runner="agy",
                     model="gemini-3.8-flash", reasoning_effort="low")
    cmd = captured["cmd"]
    assert cmd[cmd.index("--model") + 1] == "gemini-3.8-flash-low"
    assert "--effort" not in cmd


def test_agy_current_fixed_slugs_and_pro_low_are_exact():
    assert R._agy_cli_selection("claude-sonnet-4-6", "thinking") == ("claude-sonnet-4-6", "")
    assert R._agy_cli_selection("claude-opus-4-6", "thinking") == ("claude-opus-4-6-thinking", "")
    assert R._agy_cli_selection("gpt-oss-120b", "medium") == ("gpt-oss-120b-medium", "")
    assert R._agy_cli_selection("gemini-3.1-pro", "low") == ("gemini-3.1-pro-low", "")
    assert R._agy_cli_selection("gemini-3.1-pro", "high") == ("gemini-3.1-pro-high", "")
    assert R.RUNNER_MODEL_EFFORTS["agy"]["gemini-3.1-pro"] == ["low", "high"]


def test_agy_binary_resolves_official_windows_user_location_without_path(tmp_path, monkeypatch):
    local = tmp_path / "Local"
    exe = local / "agy" / "bin" / "agy.exe"
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_bytes(b"fake")
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.delenv("CSTUDIO_AGY", raising=False)
    monkeypatch.delenv("USERPROFILE", raising=False)
    monkeypatch.setattr(R.shutil, "which", lambda name: None)
    assert R._resolve_agy_binary() == str(exe.resolve())


def test_agy_stage_runner_executes_resolved_binary_path(tmp_path, monkeypatch):
    root = _root(tmp_path)
    captured = {}
    proposal = {
        "summary": "config", "document": "Configuração editorial explícita e válida. " * 3,
        "files": {}, "questions": [], "warnings": [],
    }
    monkeypatch.setattr(R.shutil, "which", lambda name: "/resolved/agy.exe" if name == "agy" else f"/fake/{name}")
    def fake_agy(cmd, cwd, prompt, timeout=600, log=None):
        captured["cmd"] = list(cmd)
        captured["prompt"] = prompt
        return {"status": "SUCCESS", "response": json.dumps(proposal)}
    monkeypatch.setattr(R, "_run_agy_stream", fake_agy)
    R.execute_runner(root, "runner-controls", "Prepare a configuração.", force_runner="agy")
    assert captured["cmd"][0] == str(Path("/resolved/agy.exe").resolve())


def test_agy_stream_transport_keeps_very_large_prompt_out_of_argv(tmp_path):
    large_prompt = "context-line\n" * 11000  # > 100k chars; too large for Windows argv.
    capture_path = tmp_path / "prompt.txt"
    code = (
        "import json,sys; "
        "m=json.loads(sys.stdin.readline()); "
        f"open({str(capture_path)!r},'w',encoding='utf-8').write(m['message']['content']); "
        "print(json.dumps({'event':'result','result':{'status':'SUCCESS','response':'ok','conversation_id':'large-prompt-session','usage':{'total_tokens':1}}}), flush=True)"
    )
    cmd = [sys.executable, "-u", "-c", code]
    result = R._run_agy_stream(cmd, str(tmp_path), large_prompt, timeout=10)

    assert sum(len(part) + 1 for part in cmd) < 2000
    assert large_prompt[:100] not in " ".join(cmd)
    assert capture_path.read_text(encoding="utf-8") == large_prompt
    assert result["conversation_id"] == "large-prompt-session"


def test_agy_stream_finishes_on_terminal_result_even_if_process_lingers(tmp_path):
    # Regression for Windows/background Agy sessions that emit the documented
    # terminal result but keep a process/pipe alive afterwards.
    code = (
        "import json,sys,time; "
        "json.loads(sys.stdin.readline()); "
        "print(json.dumps({'event':'init','conversation_id':'linger-session'}), flush=True); "
        "print(json.dumps({'event':'step_update','step_update':{'step_type':'agent_response','state':'DONE','text_delta':'done\\n'}}), flush=True); "
        "print(json.dumps({'event':'result','result':{'status':'SUCCESS','response':'finished','conversation_id':'linger-session','usage':{'total_tokens':7}}}), flush=True); "
        "time.sleep(20)"
    )
    started = time.monotonic()
    result = R._run_agy_stream([sys.executable, "-u", "-c", code], str(tmp_path), "hello", timeout=10)
    elapsed = time.monotonic() - started

    assert elapsed < 5
    assert result["response"] == "finished"
    assert result["conversation_id"] == "linger-session"

def test_agy_stream_result_rejects_terminal_error_status():
    stdout = json.dumps({
        "event": "result",
        "result": {"status": "ERROR", "error": "out of credits", "response": ""},
    })
    try:
        R._parse_agy_stream_result(stdout)
    except R.RunnerInfrastructureError as exc:
        assert "out of credits" in str(exc)
    else:
        raise AssertionError("Agy ERROR result must not be treated as a successful proposal")


def test_agy_stream_persists_init_session_before_terminal_credit_error(tmp_path):
    captured = []
    code = (
        "import json,sys; "
        "json.loads(sys.stdin.readline()); "
        "print(json.dumps({'event':'init','conversation_id':'credit-session-123'}), flush=True); "
        "print(json.dumps({'event':'result','result':{'status':'ERROR','error':'out of credits','conversation_id':'credit-session-123'}}), flush=True)"
    )
    try:
        R._run_agy_stream(
            [sys.executable, "-u", "-c", code], str(tmp_path), "hello", timeout=10,
            session_callback=lambda sid: captured.append(sid),
        )
    except R.RunnerInfrastructureError as exc:
        assert "out of credits" in str(exc)
    else:
        raise AssertionError("credit error must fail the runner")
    assert captured and captured[0] == "credit-session-123"
