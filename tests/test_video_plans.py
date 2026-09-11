import json
import os
import shutil
from pathlib import Path

import pytest

from cstudio import core as C
from cstudio import pipeline as PL
from cstudio import runners as R
from cstudio import source_media as SM
from cstudio import video_plans as VP

REPO = Path(__file__).resolve().parents[1]


def _write_transcript(root: str, slug: str, asset_id: str, text: str = "momento engraçado e reação forte") -> None:
    paths = SM.transcript_paths(root, slug, asset_id)
    vdir = Path(root) / "productions" / slug
    transcript = {
        "schema_version": SM.EDITORIAL_TRANSCRIPT_SCHEMA_VERSION, "provider": SM.EDITORIAL_TRANSCRIPT_PROVIDER, "asset_id": asset_id,
        "model": "large-v3-turbo", "language": "pt", "word_timestamps": False, "timestamp_mode": "segment", "duration_seconds": 3600,
        "segment_count": 1, "word_count": len(text.split()), "source_sha256": "", "source_identity": SM._source_identity(asset_id),
        "segments": [{"start": 10.0, "end": 14.0, "text": text, "words": []}],
        "text": text,
    }
    target = vdir / paths["json"]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(transcript), encoding="utf-8")
    windows = vdir / paths["windows"]
    windows.write_text(json.dumps({"start": 0, "end": 300, "text": text}, ensure_ascii=False) + "\n", encoding="utf-8")
    (vdir / paths["text"]).write_text(f"[00:00:10 --> 00:00:14] {text}\n", encoding="utf-8")


def _root(tmp_path):
    root = tmp_path / "harness"
    shutil.copytree(REPO / "studio", root / "studio")
    shutil.copytree(REPO / "templates", root / "templates")
    C.create_production(str(root), "Video planning", slug="video-planning")
    vdir = root / "productions" / "video-planning"
    for vod_id, title, date in (("111", "Live de Onimusha", "2026-09-01T18:00:00Z"), ("222", "Live de outro jogo", "2026-09-03T18:00:00Z")):
        rel = f".studio/internal/ingest/twitch/test/discovery/{vod_id}.json"
        path = vdir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "id": vod_id, "url": f"https://www.twitch.tv/videos/{vod_id}", "title": title,
            "timestamps": {"created_at": date}, "duration": {"seconds": 4 * 3600},
        }), encoding="utf-8")
        PL.register_asset(str(root), "video-planning", f"twitch-vod-{vod_id}", "vod-metadata", rel)
        # The full Twitch VOD is the canonical coverage source for proposals.
        twitch_media_rel = f".studio/internal/ingest/twitch/media/{vod_id}/{vod_id}.mp4"
        twitch_media = vdir / twitch_media_rel
        twitch_media.parent.mkdir(parents=True, exist_ok=True)
        twitch_media.write_bytes((f"fake-twitch-media-{vod_id}").encode("utf-8"))
        PL.register_asset(str(root), "video-planning", f"twitch-video-{vod_id}", "video-source", twitch_media_rel)
        _write_transcript(str(root), "video-planning", f"twitch-video-{vod_id}", f"{title} momento engraçado reação susto")
        # A verified/downloaded YouTube master remains an optional higher-quality source.
        yt_id = f"yt{vod_id}"
        media_rel = f".studio/internal/ingest/youtube/media/test/{yt_id}/{yt_id}.mp4"
        media = vdir / media_rel
        media.parent.mkdir(parents=True, exist_ok=True)
        media.write_bytes((f"fake-media-{vod_id}").encode("utf-8"))
        PL.register_asset(str(root), "video-planning", f"youtube-{yt_id}", "video-source", media_rel)
        assignment = vdir / ".studio" / "internal" / "ingest" / "youtube" / "assignments" / f"{yt_id}.json"
        assignment.parent.mkdir(parents=True, exist_ok=True)
        assignment.write_text(json.dumps({
            "state": "verified", "youtube_video_id": yt_id, "assigned_vod_ids": [vod_id],
            "youtube": {"video_id": yt_id, "title": f"Master {title}", "url": f"https://youtube.com/watch?v={yt_id}"},
        }), encoding="utf-8")
    return str(root)


def _raw(title="Onimusha engraçado", questions=None):
    return {
        "summary": f"Planejar um vídeo sobre {title}",
        "document": (
            f"Este vídeo deve contar uma história clara em torno de {title}, usando apenas os VODs selecionados. "
            "A abertura deve estabelecer rapidamente o contexto, o miolo deve priorizar progressão e momentos fortes, "
            "e o final deve fechar o arco sem depender de conhecimento da live completa."
        ),
        "video": {
            "working_title": title,
            "premise": "Transformar uma sessão longa em um vídeo autocontido.",
            "editorial_angle": "Humor e progressão de gameplay.",
            "target_duration_minutes": {"min": 8, "max": 15},
            "selection_criteria": ["humor", "progressão", "reações"],
            "constraints": ["não inventar contexto"],
        },
        "candidate_moments": [],
        "questions": questions or [],
        "warnings": [],
    }


def test_source_pool_can_feed_many_independent_video_proposals(tmp_path):
    root = _root(tmp_path)
    catalog = VP.source_catalog(root, "video-planning")
    assert [x["asset_id"] for x in catalog] == ["twitch-vod-111", "twitch-vod-222"]
    assert all(x["media_ready"] for x in catalog)
    assert all(x["media_sources"] for x in catalog)
    selected = [x["asset_id"] for x in catalog]
    first = VP.create_video_proposal(root, "video-planning", _raw("Vídeo A"), source_asset_ids=selected,
                                     request="Faça um vídeo A", runner="codex")
    second = VP.create_video_proposal(root, "video-planning", _raw("Vídeo B"), source_asset_ids=selected,
                                      request="Faça um vídeo B", runner="agy")
    assert first["id"] != second["id"]
    assert first["source_asset_ids"] == second["source_asset_ids"] == selected
    assert len(VP.list_video_proposals(root, "video-planning")) == 2



def test_video_proposal_requires_transcript_but_not_downloaded_full_media(tmp_path):
    root = _root(tmp_path)
    catalog = VP.source_catalog(root, "video-planning")
    first = catalog[0]
    vdir = Path(root) / "productions" / "video-planning"
    for media in first["media_sources"]:
        path = str(media.get("path") or "")
        if path and (vdir / path).is_file():
            (vdir / path).unlink()
    refreshed = VP.source_catalog(root, "video-planning")
    assert refreshed[0]["media_ready"] is False
    assert refreshed[0]["proposal_ready"] is True
    rec = VP.create_video_proposal(
        root, "video-planning", _raw(), source_asset_ids=["twitch-vod-111"],
        request="Planeje", runner="codex",
    )
    assert rec["source_asset_ids"] == ["twitch-vod-111"]

    tr_path = vdir / SM.transcript_paths(root, "video-planning", "twitch-video-111")["json"]
    tr_path.unlink()
    with pytest.raises(C.StudioError, match="transcribe the selected Twitch VOD"):
        VP.create_video_proposal(
            root, "video-planning", _raw(), source_asset_ids=["twitch-vod-111"],
            request="Planeje", runner="codex",
        )

def test_answers_are_free_state_and_survive_agent_refinement(tmp_path):
    root = _root(tmp_path)
    rec = VP.create_video_proposal(
        root, "video-planning", _raw(questions=["Qual deve ser o foco editorial?"]),
        source_asset_ids=["twitch-vod-111"], request="Planeje este vídeo", runner="codex",
    )
    qid = rec["questions"][0]["id"]
    assert rec["planning_phase"] == "part1"
    answered = VP.save_answers(root, "video-planning", rec["id"], {qid: "Priorizar humor e reações."})
    assert answered["questions"][0]["answer"] == "Priorizar humor e reações."
    assert answered["human_answers"][0]["answer"] == "Priorizar humor e reações."
    assert answered["planning_phase"] == "part2_answers_ready"

    refined = VP.refine_video_proposal(
        root, "video-planning", rec["id"], _raw("Versão refinada", questions=[]),
        runner="codex", model="gpt-test", reasoning_effort="low",
    )
    assert refined["id"] == rec["id"]
    assert refined["revision"] == 2
    assert refined["questions"] == []
    assert refined["planning_phase"] == "part2_final"
    assert refined["human_answers"][0]["answer"] == "Priorizar humor e reações."
    revision = Path(root) / "productions" / "video-planning" / ".studio" / "video-proposals" / "revisions" / rec["id"] / "0001.json"
    assert revision.is_file()


def test_accept_requires_answers_and_creates_lightweight_video_without_copying_media(tmp_path):
    root = _root(tmp_path)
    rec = VP.create_video_proposal(
        root, "video-planning", _raw(questions=["Evitar spoilers?"]), source_asset_ids=["twitch-vod-111"],
        request="Planeje", runner="opencode",
    )
    with pytest.raises(C.StudioError, match="pending proposal question"):
        VP.accept_video_proposal(root, "video-planning", rec["id"])
    qid = rec["questions"][0]["id"]
    VP.save_answers(root, "video-planning", rec["id"], {qid: "Sim, quando possível."})
    with pytest.raises(C.StudioError, match="consolidate Part 2"):
        VP.accept_video_proposal(root, "video-planning", rec["id"])
    VP.refine_video_proposal(
        root, "video-planning", rec["id"], _raw("Versão final", questions=[]),
        runner="opencode",
    )
    video = VP.accept_video_proposal(root, "video-planning", rec["id"])
    vdir = Path(root) / "productions" / "video-planning"
    assert video["stage"] == "analysis"
    assert video["source_asset_ids"] == ["twitch-vod-111"]
    assert video["media_policy"] == {"shared_source_pool": True, "copy_media": False}
    assert (vdir / ".studio" / "videos" / video["id"] / "video.json").is_file()
    brief = (vdir / ".studio" / "videos" / video["id"] / "brief.md").read_text(encoding="utf-8")
    assert "Sim, quando possível." in brief
    # Only metadata/brief exists under the video; the source stays in the shared ingest tree.
    assert not any(p.suffix in {".mp4", ".mkv", ".webm"} for p in (vdir / ".studio" / "videos" / video["id"]).rglob("*"))


def test_codex_video_runner_uses_output_schema_and_records_session(tmp_path, monkeypatch):
    root = _root(tmp_path)
    captured = {}
    monkeypatch.setattr(R.shutil, "which", lambda name: f"/fake/{name}")

    def fake_stdin(cmd, cwd, stdin_text, timeout=600, log=None):
        captured["cmd"] = list(cmd)
        captured["stdin"] = stdin_text
        return json.dumps(_raw()), "session id: 12345678-1234-1234-1234-123456789abc\n"

    monkeypatch.setattr(R, "_run_cmd_stdin_capture", fake_stdin)
    result = R.execute_video_runner(
        root, "video-planning", "Planeje um vídeo engraçado de Onimusha.", ["twitch-vod-111"],
        force_runner="codex", model="gpt-test", reasoning_effort="low",
    )
    assert "--output-schema" in captured["cmd"]
    assert captured["cmd"][captured["cmd"].index("--model") + 1] == "gpt-test"
    assert "Planeje um vídeo engraçado" not in " ".join(captured["cmd"])
    assert "Planeje um vídeo engraçado" in captured["stdin"]
    assert result["proposal"]["runner_session"]["session_id"].startswith("12345678-")



def test_agy_video_runner_uses_schema_sandbox_model_effort_and_stdin(tmp_path, monkeypatch):
    root = _root(tmp_path)
    captured = {}
    monkeypatch.setattr(R.shutil, "which", lambda name: f"/fake/{name}")

    def fake_agy(cmd, cwd, prompt, timeout=600, log=None):
        captured["cmd"] = list(cmd)
        captured["prompt"] = prompt
        return {
            "status": "SUCCESS",
            "structured_output": _raw("Agy proposal"),
            "conversation_id": "conversation-123",
            "usage": {"total_tokens": 321},
        }

    monkeypatch.setattr(R, "_run_agy_stream", fake_agy)
    result = R.execute_video_runner(
        root, "video-planning", "Planeje com Agy.", ["twitch-vod-111"],
        force_runner="agy", model="gemini-test", reasoning_effort="low",
    )
    assert captured["cmd"][0] == str(Path("/fake/agy").resolve())
    assert "--input-format" in captured["cmd"] and captured["cmd"][captured["cmd"].index("--input-format") + 1] == "stream-json"
    assert "--output-format" in captured["cmd"] and captured["cmd"][captured["cmd"].index("--output-format") + 1] == "stream-json"
    assert "--json-schema" in captured["cmd"]
    assert "--sandbox" in captured["cmd"]
    assert captured["cmd"][captured["cmd"].index("--model") + 1] == "gemini-test"
    assert captured["cmd"][captured["cmd"].index("--effort") + 1] == "low"
    assert "Planeje com Agy." not in " ".join(captured["cmd"])
    assert "Planeje com Agy." in captured["prompt"]
    assert result["proposal"]["runner_session"]["session_id"] == "conversation-123"
    assert result["proposal"]["runner_usage"]["total_tokens"] == 321


def test_agy_video_runner_opus_uses_current_headless_slug(tmp_path, monkeypatch):
    root = _root(tmp_path)
    captured = {}
    monkeypatch.setattr(R.shutil, "which", lambda name: f"/fake/{name}")

    def fake_agy(cmd, cwd, prompt, timeout=600, log=None):
        captured["cmd"] = list(cmd)
        return {
            "status": "SUCCESS",
            "structured_output": _raw("Opus proposal"),
            "conversation_id": "opus-conversation",
        }

    monkeypatch.setattr(R, "_run_agy_stream", fake_agy)
    R.execute_video_runner(
        root, "video-planning", "Refine with Opus.", ["twitch-vod-111"],
        force_runner="agy", model="claude-opus-4-6", reasoning_effort="thinking",
    )
    cmd = captured["cmd"]
    assert cmd[cmd.index("--model") + 1] == "claude-opus-4-6-thinking"
    assert "--effort" not in cmd


def test_part2_fresh_attempt_never_reuses_part1_session(tmp_path, monkeypatch):
    root = _root(tmp_path)
    rec = VP.create_video_proposal(
        root, "video-planning", _raw(), source_asset_ids=["twitch-vod-111"], request="Planeje",
        runner="codex", model="same-model", reasoning_effort="low",
        runner_session={"runner": "codex", "session_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"},
    )
    calls = []
    prompts = []
    monkeypatch.setattr(R.shutil, "which", lambda name: f"/fake/{name}")

    def fake_stdin(cmd, cwd, stdin_text, timeout=600, log=None):
        calls.append(list(cmd)); prompts.append(stdin_text)
        return json.dumps(_raw("Refinada")), "session id: bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

    monkeypatch.setattr(R, "_run_cmd_stdin_capture", fake_stdin)
    R.execute_video_runner(root, "video-planning", "Refine com minhas respostas.", [], proposal_id=rec["id"],
                           force_runner="codex", model="same-model", reasoning_effort="low")
    assert calls[-1][:3] == ["codex", "exec", "--sandbox"]
    assert "resume" not in calls[-1]
    assert "PART 2" in prompts[-1]
    assert prompts[-1] != "Continue."


def test_explicit_same_part_continuation_reuses_session_and_sends_only_continue(tmp_path, monkeypatch):
    root = _root(tmp_path)
    rec = VP.create_video_proposal(
        root, "video-planning", _raw(), source_asset_ids=["twitch-vod-111"], request="Planeje",
        runner="codex", model="same-model", reasoning_effort="low",
    )
    captured = {}
    monkeypatch.setattr(R.shutil, "which", lambda name: f"/fake/{name}")

    def fake_stdin(cmd, cwd, stdin_text, timeout=600, log=None):
        captured["cmd"] = list(cmd); captured["prompt"] = stdin_text
        return json.dumps(_raw("Refinada")), "session id: cccccccc-cccc-cccc-cccc-cccccccccccc"

    monkeypatch.setattr(R, "_run_cmd_stdin_capture", fake_stdin)
    R.execute_video_runner(
        root, "video-planning", "Texto original que não deve ser reenviado.", [], proposal_id=rec["id"],
        force_runner="codex", model="same-model", reasoning_effort="low",
        resume_session_id="cccccccc-cccc-cccc-cccc-cccccccccccc", continue_attempt=True,
    )
    assert captured["cmd"][:4] == ["codex", "exec", "resume", "cccccccc-cccc-cccc-cccc-cccccccccccc"]
    assert captured["cmd"][-1] == "-"
    assert captured["prompt"] == "Continue."


def test_source_catalog_uses_matching_vod_object_not_nested_game_title(tmp_path):
    root = _root(tmp_path)
    vdir = Path(root) / "productions" / "video-planning"
    path = vdir / ".studio" / "internal" / "ingest" / "twitch" / "test" / "discovery" / "111.json"
    path.write_text(json.dumps({
        "vod_id": "111",
        "misleading_game": {"id": "game-1", "title": "God of War III Remastered"},
        "important_operations": {
            "ChannelVideoCore": [{
                "data": {
                    "video": {
                        "id": "111",
                        "title": "METAL GEAR SOLID 4 - continunando nossa saga",
                        "lengthSeconds": 25902,
                        "publishedAt": "2026-08-31T18:13:55Z",
                    }
                }
            }]
        },
    }), encoding="utf-8")

    source = next(x for x in VP.source_catalog(root, "video-planning") if x["vod_id"] == "111")
    assert source["title"] == "METAL GEAR SOLID 4 - continunando nossa saga"
    assert source["duration_seconds"] == 25902
    assert source["created_at"] == "2026-08-31T18:13:55Z"
