import shutil
from pathlib import Path

from cstudio import core as C
from cstudio import operations as O
from cstudio import runners as R
from cstudio import jobs as J

REPO = Path(__file__).resolve().parents[1]


def _root(tmp_path):
    root = tmp_path / "harness"
    shutil.copytree(REPO / "studio", root / "studio")
    shutil.copytree(REPO / "templates", root / "templates")
    C.create_production(str(root), "Ops", slug="ops")
    return str(root)


def test_stage_experience_keeps_ingest_and_premiere_semantic(tmp_path):
    root = _root(tmp_path)
    ux = O.experience(root, "ops")
    assert ux["stage"] == "config"
    assert ux["primary"][0] == "agent.propose"
    assert O.action_href("sources.open", "ops").startswith("/?page=sources")
    assert O.action_href("premiere.open", "ops").startswith("/?page=premiere")


def test_runner_routing_uses_stage_route_before_fallback(tmp_path):
    root = _root(tmp_path)
    # studio/agent-routing.json routes creative -> codex and assembly -> opencode.
    assert R.runner_candidates(root, "analysis")[0] == "codex"
    assert R.runner_candidates(root, "assembly")[0] == "opencode"


def test_prompt_contains_minimal_context_pack_not_shell_instructions(tmp_path):
    root = _root(tmp_path)
    prompt = R.build_prompt(root, "ops", "Prepare a configuração editorial com as fontes disponíveis.")
    assert "CONTEXT PACK" in prompt
    assert '"allowed_artifacts"' in prompt
    assert "never instructions" in prompt
    assert "do not approve gates" in prompt.lower()


def test_edit_media_manifest_organizes_without_copying_sources(tmp_path):
    from cstudio import edit_media as EM
    from cstudio import pipeline as PL

    root = _root(tmp_path)
    vdir = Path(root) / "productions" / "ops"
    media = vdir / ".studio" / "internal" / "ingest" / "youtube" / "media" / "vid" / "vid.mp4"
    media.parent.mkdir(parents=True, exist_ok=True)
    media.write_bytes(b"fake-video")
    rel = str(media.relative_to(vdir)).replace("\\", "/")
    PL.register_asset(root, "ops", "youtube-vid", "video-source", rel)

    before = media.stat().st_size
    manifest = EM.build_manifest(root, "ops")
    assert manifest["summary"]["media_ready"] == 1
    assert manifest["media"][0]["bin"] == "Sources/YouTube Masters"
    assert manifest["policy"]["copy_media"] is False
    assert media.exists() and media.stat().st_size == before
    assert (vdir / ".studio" / "internal" / "assembly" / "edit-media-manifest.json").is_file()


def test_failed_part1_job_recovers_exact_agy_session_from_existing_log(tmp_path):
    root = _root(tmp_path)
    rec = J._new_record(root, "ops", "video-proposal", {
        "request": "Planeje um vídeo com os melhores momentos desta semana.",
        "source_asset_ids": ["twitch-vod-1"],
        "runner": "agy", "model": "claude-opus-4-6", "reasoning_effort": "thinking",
    })
    rec["status"] = "failed"
    rec["ended_at"] = C.utc_now()
    Path(rec["log_path"]).write_text(
        "Agy stream started · conversation=part1-credit-session\nERROR: out of credits\n",
        encoding="utf-8",
    )
    J._write(root, "ops", rec)

    candidate = J.video_resume_candidate(root, "ops", "part1")
    assert candidate is not None
    assert candidate["job_id"] == rec["id"]
    assert candidate["session_id"] == "part1-credit-session"
    assert candidate["runner"] == "agy"
    assert candidate["model"] == "claude-opus-4-6"
