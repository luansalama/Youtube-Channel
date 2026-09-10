import csv
import json
import os
import shutil
import subprocess
import struct
import threading
import time
from pathlib import Path

import pytest

from cstudio import core as C
from cstudio import dashboard as D
from cstudio import rights as RT
from cstudio import youtube_resolver as YR

REPO = Path(__file__).resolve().parents[1]


def _harness(tmp_path, slug="yt"):
    root = tmp_path / "harness"
    shutil.copytree(REPO / "studio", root / "studio")
    shutil.copytree(REPO / "templates", root / "templates")
    # Tests must not inherit the developer machine's configured mirror channels.
    C.write_json(str(root / "studio" / "youtube-mirrors.json"), YR.default_config())
    (root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    C.create_production(str(root), "YouTube resolver test", slug=slug, source_url="https://www.twitch.tv/alanzoka/videos")
    return str(root)


def _write_vod(root, slug="yt", streamer="alanzoka", vod_id="1234567890", *, created="2026-09-04T16:00:00Z", duration=20000):
    vdir = Path(C.prod_path(root, slug))
    d = vdir / ".studio" / "internal" / "ingest" / "twitch" / streamer / "discovery"
    d.mkdir(parents=True, exist_ok=True)
    data = {
        "vod_id": vod_id,
        "important_operations": {
            "VideoMetadata": [{"data": {"video": {
                "id": vod_id,
                "title": "Onimusha e Blood of Dawnwalker",
                "publishedAt": created,
                "lengthSeconds": duration,
                "game": {"name": "Just Chatting"},
            }}}],
            "VideoPlayer_ChapterSelectButtonVideo": [{"data": {"video": {"moments": {"edges": [
                {"node": {"positionMilliseconds": 1000, "durationMilliseconds": 5000000, "description": "Onimusha: Way of the Sword", "details": {"game": {"displayName": "Onimusha: Way of the Sword"}}}},
                {"node": {"positionMilliseconds": 7000000, "durationMilliseconds": 5000000, "description": "The Blood of Dawnwalker", "details": {"game": {"displayName": "The Blood of Dawnwalker"}}}},
            ]}}}}],
        },
    }
    path = d / f"{vod_id}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _write_index(root, slug="yt", streamer="alanzoka"):
    base = Path(YR.youtube_dir(root, slug)) / "index"
    base.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "video_id": "abcDEF12345",
            "url": "https://www.youtube.com/watch?v=abcDEF12345",
            "streamer": streamer,
            "channel_name": "alanzoka",
            "configured_channel_name": "alanzoka",
            "title": "ONIMUSHA: WAY OF THE SWORD - gameplay sem cortes",
            "description": "Onimusha completo",
            "upload_date": "20260906",
            "duration": 7800,
        },
        {
            "video_id": "otherVID123",
            "url": "https://www.youtube.com/watch?v=otherVID123",
            "streamer": streamer,
            "channel_name": "alanzoka",
            "title": "Jogo completamente diferente",
            "description": "",
            "upload_date": "20260101",
            "duration": 1200,
        },
    ]
    C.write_json(str(base / f"{streamer}.json"), {"schema_version": 1, "streamer": streamer, "updated_at": C.utc_now(), "videos": rows})
    return rows


def test_channel_config_multiple_and_disable(tmp_path):
    root = _harness(tmp_path)
    a = YR.set_channel(root, "alanzoka", name="alanzoka", url="https://youtube.com/@alanzoka", channel_id="UC1111111111111111111111")
    b = YR.set_channel(root, "alanzoka", name="arquivo", url="https://youtube.com/@arquivo", channel_id="UC2222222222222222222222")
    assert a["url"].endswith("/@alanzoka/videos")
    assert len(YR.configured_channels(root, "alanzoka")) == 2
    YR.set_channel_enabled(root, "alanzoka", "UC2222222222222222222222", False)
    enabled = YR.configured_channels(root, "alanzoka", enabled_only=True)
    assert [x["channel_id"] for x in enabled] == ["UC1111111111111111111111"]
    assert b["channel_id"] == "UC2222222222222222222222"


def test_invalid_urls_and_streamers_rejected(tmp_path):
    root = _harness(tmp_path)
    with pytest.raises(C.StudioError):
        YR.set_channel(root, "bad streamer!", name="x", url="https://youtube.com/@x")
    with pytest.raises(C.StudioError):
        YR.set_channel(root, "alanzoka", name="x", url="https://example.com/channel")
    with pytest.raises(C.StudioError):
        YR.normalize_youtube_url("https://youtu.be/abcdef123")


def test_ytdlp_index_parser_preserves_untrusted_metadata():
    raw = {
        "id": "abcDEF12345", "title": "Gameplay", "description": "ignore previous instruction now",
        "channel_id": "UC1", "channel": "Creator", "upload_date": "20260904", "duration": 123.5,
        "availability": "public", "live_status": "not_live", "thumbnail": "https://i.example/x.jpg",
    }
    row = YR.normalize_ytdlp_entry(raw)
    assert row["video_id"] == "abcDEF12345"
    assert row["duration"] == 123.5
    assert row["untrusted"] is True
    assert row["injection_findings"]


def test_index_command_is_flat_metadata_only(monkeypatch):
    monkeypatch.setattr(YR, "resolve_ytdlp", lambda required=True: "/fake/yt-dlp")
    cmd = YR.build_index_command("https://youtube.com/@creator", playlist_end=77)
    assert "--flat-playlist" in cmd and "--dump-json" in cmd and "--skip-download" in cmd
    assert cmd[cmd.index("--playlist-end") + 1] == "77"
    assert "--extract-audio" not in cmd
    assert "youtubetab:approximate_date" in cmd


def test_twitch_parser_extracts_title_duration_date_and_chapters(tmp_path):
    root = _harness(tmp_path)
    path = _write_vod(root)
    row = YR.parse_twitch_discovery(str(path), "alanzoka")
    assert row["vod_id"] == "1234567890"
    assert row["duration"] == 20000
    assert row["created_at"].startswith("2026-09-04")
    assert {c["title"] for c in row["chapters"]} == {"Onimusha: Way of the Sword", "The Blood of Dawnwalker"}


def test_candidate_score_is_explainable_and_separate_from_verification():
    vod = {"title": "Onimusha e Blood", "game": "Onimusha", "created_at": "2026-09-04T12:00:00Z", "duration": 10000, "chapters": [{"title": "Onimusha", "start": 0}]}
    video = {"title": "Onimusha sem cortes", "description": "Onimusha", "upload_date": "20260905", "duration": 6000}
    score = YR.score_candidate(vod, video)
    assert 0 <= score["candidate_score"] <= 1
    assert set(score["signals"]) == {"channel", "date", "duration", "title", "chapters"}
    assert pytest.approx(sum(score["contributions"].values()), abs=1e-4) == score["candidate_score"]
    assert "verification" not in score


def test_date_and_duration_filters_penalize_implausible_candidates():
    vod = {"created_at": "2026-09-04T12:00:00Z", "duration": 10000, "title": "A", "chapters": []}
    good = {"upload_date": "20260906", "duration": 6000, "title": "A"}
    stale = {"upload_date": "20250101", "duration": 30000, "title": "A"}
    assert YR.score_candidate(vod, good)["candidate_score"] > YR.score_candidate(vod, stale)["candidate_score"]


def test_missing_metadata_is_neutral_and_weights_are_renormalized():
    vod = {"created_at": "2026-09-04T12:00:00Z", "duration": 10000, "title": "Onimusha", "chapters": []}
    video = {"title": "Onimusha gameplay", "description": ""}
    scored = YR.score_candidate(vod, video)
    assert scored["signals"]["date"]["available"] is False
    assert scored["signals"]["duration"]["available"] is False
    assert scored["signals"]["channel"]["effective_weight"] == 0
    assert pytest.approx(sum(scored["contributions"].values()), abs=1e-4) == scored["candidate_score"]


def test_generate_candidates_filters_old_index_and_persists_manifest(tmp_path):
    root = _harness(tmp_path)
    _write_vod(root)
    _write_index(root)
    out = YR.generate_candidates(root, "yt")
    assert out["candidates"] == 1
    rec = out["matches"][0]
    assert rec["youtube_video_id"] == "abcDEF12345"
    assert rec["rights_status"] == "sem_autorizacao_confirmada"
    assert rec["verification"]["providers"]["transcript"] == "pending"
    assert Path(YR._candidate_file(root, "yt", "1234567890", "abcDEF12345")).is_file()


def test_ambiguous_candidate_state_when_top_scores_close(tmp_path, monkeypatch):
    root = _harness(tmp_path)
    _write_vod(root)
    rows = _write_index(root)
    rows[1].update(rows[0]); rows[1]["video_id"] = "secondVID999"; rows[1]["url"] = "https://www.youtube.com/watch?v=secondVID999"
    base = Path(YR.youtube_dir(root, "yt")) / "index" / "alanzoka.json"
    C.write_json(str(base), {"schema_version": 1, "streamer": "alanzoka", "updated_at": C.utc_now(), "videos": rows})
    monkeypatch.setattr(YR, "LIKELY_THRESHOLD", 0.2)
    out = YR.generate_candidates(root, "yt")
    assert {m["state"] for m in out["matches"][:2]} == {"ambiguous"}


def test_rejected_match_is_preserved(tmp_path):
    root = _harness(tmp_path)
    _write_vod(root); _write_index(root)
    rec = YR.generate_candidates(root, "yt")["matches"][0]
    rejected = YR.reject_match(root, "yt", "1234567890", rec["youtube_video_id"], "wrong game")
    assert rejected["state"] == "rejected"
    assert rejected["rejection"]["reason"] == "wrong game"


def test_assess_verified_requires_multiple_ordered_anchors():
    anchors = [
        {"youtube_time": 100, "twitch_time": 500, "similarity": 0.91},
        {"youtube_time": 500, "twitch_time": 910, "similarity": 0.90},
        {"youtube_time": 900, "twitch_time": 1330, "similarity": 0.89},
    ]
    assert YR.assess_verification(anchors)["state"] == "verified"
    assert YR.assess_verification(anchors[:1])["state"] == "candidate"


def test_out_of_order_audio_matches_are_ambiguous():
    anchors = [
        {"youtube_time": 100, "twitch_time": 900, "similarity": 0.93},
        {"youtube_time": 500, "twitch_time": 700, "similarity": 0.92},
        {"youtube_time": 900, "twitch_time": 1500, "similarity": 0.91},
    ]
    assert YR.assess_verification(anchors)["state"] == "ambiguous"


def test_offset_consistency_rejects_large_backwards_jump_from_verified():
    anchors = [
        {"youtube_time": 100, "twitch_time": 1100, "similarity": 0.94},
        {"youtube_time": 500, "twitch_time": 1510, "similarity": 0.93},
        {"youtube_time": 900, "twitch_time": 1650, "similarity": 0.92},
    ]
    assessment = YR.assess_verification(anchors)
    assert assessment["state"] == "likely"
    assert assessment["timeline_consistency"] == "weak"
    assert assessment["backwards_offset_jumps"]


def test_piecewise_mapping_helpers_support_gaps():
    manifest = {"timeline_segments": [
        {"youtube_start": 0, "youtube_end": 100, "twitch_start": 1000, "twitch_end": 1100, "confidence": .95},
        {"youtube_start": 100, "youtube_end": 200, "twitch_start": 1300, "twitch_end": 1400, "confidence": .94},
    ]}
    assert YR.map_youtube_to_twitch(manifest, 50) == pytest.approx(1050)
    assert YR.map_youtube_to_twitch(manifest, 150) == pytest.approx(1350)
    assert YR.map_twitch_to_youtube(manifest, 1350) == pytest.approx(150)
    assert YR.map_twitch_to_youtube(manifest, 1200) is None


def test_download_command_requests_best_video_plus_audio(monkeypatch):
    monkeypatch.setattr(YR, "resolve_ytdlp", lambda required=True: "/tools/yt-dlp")
    monkeypatch.setattr(YR, "resolve_ffmpeg", lambda required=True: "/tools/ffmpeg")
    cmd = YR.build_download_command("https://youtube.com/watch?v=abcDEF12345", "/tmp/%(id)s.%(ext)s")
    assert cmd[cmd.index("-f") + 1] == "bv*+ba/b"
    assert "--merge-output-format" in cmd and "mkv" in cmd
    assert "2160" not in " ".join(cmd) and "1080" not in " ".join(cmd)
    assert "--write-info-json" in cmd


def test_missing_tools_fail_cleanly(monkeypatch):
    monkeypatch.delenv("CSTUDIO_YTDLP", raising=False)
    monkeypatch.delenv("CSTUDIO_FFMPEG", raising=False)
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(C.StudioError, match="yt-dlp"):
        YR.resolve_ytdlp()
    with pytest.raises(C.StudioError, match="ffmpeg"):
        YR.resolve_ffmpeg()


def test_download_registers_blocked_asset_and_aux_manifest(tmp_path, monkeypatch):
    root = _harness(tmp_path)
    _write_vod(root); _write_index(root)
    rec = YR.generate_candidates(root, "yt")["matches"][0]
    rec["state"] = "verified"
    YR.save_match(root, "yt", rec)
    monkeypatch.setattr(YR, "resolve_ytdlp", lambda required=True: "/fake/yt-dlp")
    monkeypatch.setattr(YR, "resolve_ffmpeg", lambda required=True: "/fake/ffmpeg")
    monkeypatch.setattr(YR, "_probe_media", lambda path: {"height": 2160, "fps": 60.0})

    class P:
        returncode = 0
        stdout = "ok"

    def fake_run(cmd, **kwargs):
        template = cmd[cmd.index("-o") + 1]
        out = template.replace("%(ext)s", "mkv")
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_bytes(b"x" * 4096)
        Path(out.replace(".mkv", ".info.json")).write_text("{}", encoding="utf-8")
        return P()

    monkeypatch.setattr(subprocess, "run", fake_run)
    done = YR.download_verified(root, "yt", "1234567890", rec["youtube_video_id"])
    assert done["download"]["height"] == 2160
    assert done["rights_status"] == "sem_autorizacao_confirmada"
    assets = Path(C.prod_path(root, "yt")) / ".studio" / "internal" / "ingest" / "assets.csv"
    with assets.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    yt = [r for r in rows if r["asset_id"].startswith("youtube-")][0]
    assert yt["kind"] == "video-source"
    assert yt["rights_status"] == "sem_autorizacao_confirmada"
    ok, detail = RT.rights_gate(C.load_project(root, "yt")[1], C.prod_path(root, "yt"))
    assert not ok and "youtube-" in detail



def test_no_download_overrides_auto_download(tmp_path, monkeypatch):
    root = _harness(tmp_path)
    _write_vod(root); _write_index(root)
    YR.set_auto_download(root, True)
    seen = []

    def fake_global(*args, **kwargs):
        seen.append(bool(kwargs.get("no_download")))
        return {"verified": 1, "likely": 0, "errors": [], "videos": 1, "completed": 1,
                "resumed": 0, "evaluated_pairs": 1, "skipped_pairs": 0, "assignments": []}

    monkeypatch.setattr(YR, "_resolve_global_assignments", fake_global)
    out = YR.resolve(root, "yt", no_download=True)
    assert out["verified"] >= 1
    assert seen == [True]

def test_path_isolation_is_per_production(tmp_path):
    root = _harness(tmp_path, slug="one")
    C.pause_production(root, "one")
    C.create_production(root, "Two", slug="two")
    assert YR.youtube_dir(root, "one") != YR.youtube_dir(root, "two")
    assert os.path.join("productions", "one") in YR.youtube_dir(root, "one")
    assert os.path.join("productions", "two") in YR.youtube_dir(root, "two")


def test_dashboard_operational_page_and_forms(tmp_path):
    root = _harness(tmp_path)
    _write_vod(root)
    _write_index(root)
    YR.generate_candidates(root, "yt")
    YR.set_channel(root, "alanzoka", name="alanzoka", url="https://youtube.com/@alanzoka")
    page = D.render(root, "youtube", "yt", csrf_token="csrf")
    assert "YouTube Mirror Resolver" in page
    assert "Transcript alignment" in page
    assert "Audio confirmation" in page
    assert "Whisper" in page
    assert "Whisper lang" in page
    assert "alanzoka=pt" in page
    assert "/action/youtube-channel-set" in page
    assert "/action/youtube-index" in page
    assert "/action/youtube-resolve" in page
    assert "Auto-download verified sources" in page
    assert 'name="url"' in page and "required" in page
    fragment = D.render_youtube_job(root, "yt")
    assert "data-youtube-live" in fragment and 'data-running="false"' in fragment


def test_dashboard_global_assignment_is_primary_and_uses_match_vod_fallback(tmp_path):
    root = _harness(tmp_path)
    vod_id = "2861744268"
    vod = {
        "vod_id": vod_id, "streamer": "alanzoka", "title": "MGS4 live",
        "game": "Metal Gear Solid 4", "source_url": f"https://www.twitch.tv/videos/{vod_id}",
        "created_at": "2026-09-01T18:00:00Z",
    }
    verified_video = {
        "video_id": "verifiedABC1", "title": "Metal Gear Parte 5", "channel_name": "alanzoka",
        "url": "https://www.youtube.com/watch?v=verifiedABC1", "upload_date": "20260903", "duration": 3600,
    }
    unmatched_video = {
        "video_id": "unmatchedABC2", "title": "Outro upload", "channel_name": "alanzoka",
        "url": "https://www.youtube.com/watch?v=unmatchedABC2", "upload_date": "20260903", "duration": 900,
    }
    verified_pair = {
        "vod_id": vod_id, "state": "verified", "candidate_score": .74,
        "audio": {"anchors": [{"similarity": .98}] * 4, "assessment": {"timeline_consistency": "strong"}},
    }
    unmatched_pair = {
        "vod_id": vod_id, "state": "candidate", "candidate_score": .62,
        "audio": {"anchors": [{"similarity": .81}], "assessment": {"timeline_consistency": "insufficient"}},
        "transcript": {"assessment": {"state": "insufficient"}},
    }
    YR.save_assignment(root, "yt", {
        "youtube_video_id": verified_video["video_id"], "streamer": "alanzoka", "status": "completed",
        "state": "verified", "primary_vod_id": vod_id, "assigned_vod_ids": [vod_id],
        "evaluated_vod_ids": [vod_id], "pair_results": {vod_id: verified_pair}, "youtube": verified_video,
        "matcher_engine": "numpy-exact", "candidate_discovery": {"reasons": ["production-time-window"], "index_position": 13},
    })
    YR.save_assignment(root, "yt", {
        "youtube_video_id": unmatched_video["video_id"], "streamer": "alanzoka", "status": "completed",
        "state": "unmatched", "primary_vod_id": vod_id, "assigned_vod_ids": [],
        "evaluated_vod_ids": [vod_id], "pair_results": {vod_id: unmatched_pair}, "youtube": unmatched_video,
        "matcher_engine": "numpy-exact", "candidate_discovery": {"reasons": ["production-time-window"], "index_position": 14},
        "deep_resolution": {"status": "completed", "attempted_vod_ids": [vod_id], "reason": "localized tiebreak exhausted"},
    })
    # Persisted match carries the VOD label even when the Twitch ingest directory is absent.
    YR.save_match(root, "yt", {
        "youtube_video_id": verified_video["video_id"], "youtube": verified_video,
        "twitch_vod_ids": [vod_id], "twitch": vod, "streamer": "alanzoka", "state": "verified",
        "candidate_score": .74, "verification": {"audio": verified_pair["audio"]},
        "timeline_segments": [], "download": {"status": "not_downloaded", "path": ""},
    })
    page = D.render(root, "youtube", "yt", csrf_token="csrf")
    assert "2 vídeos, uma decisão por source" in page
    assert page.count('data-youtube-assignment ') == 2
    assert page.count('data-state="verified"') == 1
    assert page.count('data-state="unmatched"') == 1
    assert "NO MATCH" in page
    assert "estado local dos pares não substitui a decisão global" in page
    assert "Mirrors confirmados por live" in page
    assert "MGS4 live" in page
    assert "Pair diagnostics" in page
    assert "metadata prior" in page
    assert "resolver-vod" not in page


def test_dashboard_assignment_filter_javascript_is_packaged():
    script = (Path(__file__).resolve().parents[1] / "cstudio" / "static" / "dashboard.js").read_text(encoding="utf-8")
    assert "data-youtube-assignment-search" in script
    assert "data-youtube-state-filter" in script
    assert "applyAssignmentFilter" in script


def test_youtube_job_log_ui_keeps_full_log_and_copy_control(tmp_path):
    root = _harness(tmp_path)
    job_id = "job-log-ui"
    log_path = YR._job_log_path(root, "yt", job_id)
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    full_log = "BEGIN-OF-LONG-LOG\n" + ("0123456789abcdef\n" * 1200) + "END-OF-LONG-LOG\n"
    Path(log_path).write_text(full_log, encoding="utf-8")
    YR._write_job(root, "yt", {
        "id": job_id, "type": "resolve", "status": "running", "slug": "yt",
        "streamer": "alanzoka", "vod_id": "123", "created_at": C.utc_now(),
        "started_at": C.utc_now(), "ended_at": "", "log_path": log_path,
    })
    fragment = D.render_youtube_job(root, "yt")
    assert "Copiar log" in fragment
    assert "data-copy-log" in fragment
    assert "BEGIN-OF-LONG-LOG" in fragment
    assert "END-OF-LONG-LOG" in fragment
    assert YR.tail_job_log(root, "yt", job_id, max_chars=None) == full_log


def test_windows_hidden_subprocess_flags_include_create_no_window(monkeypatch):
    monkeypatch.setattr(YR.os, "name", "nt")
    merged = YR._merge_hidden_subprocess_kwargs({"creationflags": 0x00000200})
    assert merged["creationflags"] & 0x08000000
    assert merged["creationflags"] & 0x00000200


def test_hidden_popen_forwards_no_window_flag(monkeypatch):
    monkeypatch.setattr(YR.os, "name", "nt")
    captured = {}

    class Proc:
        pass

    def fake_popen(*args, **kwargs):
        captured.update(kwargs)
        return Proc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    assert isinstance(YR._popen_hidden(["fake-tool.exe"]), Proc)
    assert captured["creationflags"] & 0x08000000


def test_job_duplicate_protection(tmp_path, monkeypatch):
    root = _harness(tmp_path)
    YR.set_channel(root, "alanzoka", name="alanzoka", url="https://youtube.com/@alanzoka")

    class Worker:
        pid = 424242
        def poll(self):
            return None

    monkeypatch.setattr(YR, "_spawn_job_process", lambda *a, **k: Worker())
    first = YR.start_job(root, "yt", "index")
    assert first["worker_pid"] == 424242
    assert first["worker_mode"] == "process"
    with pytest.raises(C.StudioError, match="already running"):
        YR.start_job(root, "yt", "resolve")
    with YR._LOCK:
        YR._RUNNING.clear()


def test_job_failure_is_persisted_not_completed(tmp_path, monkeypatch):
    root = _harness(tmp_path)
    monkeypatch.setattr(YR, "index_all", lambda *a, **k: (_ for _ in ()).throw(C.StudioError("boom")))
    rec = YR.run_job(root, "yt", "index")
    assert rec["status"] == "failed"
    assert rec["return_code"] == 1
    assert "boom" in rec["error"]


def test_mark_stale_jobs_respects_live_persisted_pid(tmp_path, monkeypatch):
    root = _harness(tmp_path)
    rec = YR._new_job_record(root, "yt", "index", {})
    rec["worker_pid"] = 12345
    YR._write_job(root, "yt", rec)
    monkeypatch.setattr(YR, "_pid_alive", lambda pid: int(pid or 0) == 12345)
    assert YR.mark_stale_jobs_failed(root, "yt") == 0
    assert YR.read_job(root, "yt", rec["id"])["status"] == "running"
    monkeypatch.setattr(YR, "_pid_alive", lambda pid: False)
    assert YR.mark_stale_jobs_failed(root, "yt") == 1
    failed = YR.read_job(root, "yt", rec["id"])
    assert failed["status"] == "failed"
    assert "worker process" in failed["error"]


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_real_ffmpeg_recompression_multiple_anchors_and_gap(tmp_path):
    source = tmp_path / "source.wav"
    mirror = tmp_path / "mirror.m4a"
    ffmpeg = shutil.which("ffmpeg")
    # Use a deterministic non-stationary signal: both frequency and amplitude
    # evolve over time. This avoids an artificially ambiguous white-noise fixture
    # while still exercising codec tolerance, offset recovery and a real cut.
    subprocess.run([
        ffmpeg, "-v", "error", "-f", "lavfi", "-i",
        "aevalsrc=0.24*sin(2*PI*(180+8*t+35*sin(0.31*t))*t)*(0.58+0.35*sin(2*PI*(0.11+0.003*t)*t)):s=48000:d=28",
        str(source)
    ], check=True)
    subprocess.run([
        ffmpeg, "-v", "error", "-i", str(source), "-filter_complex",
        "[0:a]atrim=0:8,asetpts=N/SR/TB[a0];[0:a]atrim=12:28,asetpts=N/SR/TB[a1];[a0][a1]concat=n=2:v=0:a=1",
        "-c:a", "aac", "-b:a", "96k", str(mirror)
    ], check=True)
    target = YR.extract_audio_features(str(source))
    anchors = []
    for yt_time in (1.0, 9.0, 17.0):
        query = YR.extract_audio_features(str(mirror), start=yt_time, duration=4.0)
        frame, sim = YR.match_feature_window(query, target, step_frames=1)
        anchors.append({"youtube_time": yt_time, "twitch_time": frame * YR.FRAME_SECONDS, "similarity": sim})
    # The gap moves later anchors by +4s on the source timeline.
    assert anchors[0]["twitch_time"] == pytest.approx(1.0, abs=0.6)
    assert anchors[1]["twitch_time"] == pytest.approx(13.0, abs=0.6)
    assert anchors[2]["twitch_time"] == pytest.approx(21.0, abs=0.6)
    assessment = YR.assess_verification(anchors)
    assert assessment["state"] == "verified"
    segments = YR._piecewise_segments(anchors)
    assert len(segments) == 2
    assert segments[0]["slope"] > 1.2  # removed interval detected in piecewise mapping


def _transcript_from_words(words, *, offset=0.0, step=1.0):
    seg_words = []
    for i, word in enumerate(words):
        start = offset + i * step
        seg_words.append({"word": " " + word, "start": start, "end": start + step * 0.7, "probability": 0.99})
    return {"provider": YR.TRANSCRIPT_PROVIDER, "segments": [{"start": offset, "end": offset + len(words) * step, "text": " ".join(words), "words": seg_words}]}


def test_whisper_discovery_relative_layout_and_local_checkpoint(tmp_path):
    apps = tmp_path / "Applications"
    root = apps / "Youtube-Channel"
    (root / "studio").mkdir(parents=True)
    C.write_json(str(root / "studio" / "youtube-mirrors.json"), YR.default_config())
    home = apps / "LLMS" / "Whisper"
    exe = home / ".venv" / "Scripts" / "whisper.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"x")
    model = home / "large-v3-turbo.pt"
    model.write_bytes(b"x")
    assert Path(YR.resolve_whisper(str(root))).resolve() == exe.resolve()
    assert Path(YR.resolve_whisper_model(str(root))).resolve() == model.resolve()


def test_build_whisper_command_uses_venv_python_segment_timestamps_and_cuda_override(tmp_path, monkeypatch):
    root = _harness(tmp_path)
    home = tmp_path / "Whisper"
    scripts = home / ".venv" / "Scripts"
    scripts.mkdir(parents=True)
    fake_whisper = scripts / "whisper.exe"
    fake_python = scripts / "python.exe"
    fake_whisper.write_bytes(b"x")
    fake_python.write_bytes(b"x")
    model = home / "large-v3-turbo.pt"
    model.write_bytes(b"x")
    monkeypatch.setenv("CSTUDIO_WHISPER", str(fake_whisper))
    monkeypatch.setenv("CSTUDIO_WHISPER_MODEL", str(model))
    monkeypatch.setenv("CSTUDIO_WHISPER_DEVICE", "cuda")
    cmd = YR.build_whisper_command(root, "/tmp/audio.m4a", "/tmp/out", streamer="alanzoka")
    assert cmd[:3] == [str(fake_python), "-m", "whisper"]
    assert cmd[cmd.index("--model") + 1] == "turbo"
    assert cmd[cmd.index("--model_dir") + 1] == str(home)
    assert "--word_timestamps" not in cmd
    assert cmd[cmd.index("--condition_on_previous_text") + 1] == "False"
    assert cmd[cmd.index("--device") + 1] == "cuda"
    assert cmd[cmd.index("--language") + 1] == "pt"
    clipped = YR.build_whisper_command(
        root, "/tmp/audio.m4a", "/tmp/out", streamer="alanzoka",
        clip_timestamps=[(10.0, 58.0), (120.0, 168.0)],
    )
    assert clipped[clipped.index("--clip_timestamps") + 1] == "10.000,58.000,120.000,168.000"




def test_whisper_preflight_reports_cuda_and_is_cached(tmp_path, monkeypatch):
    root = _harness(tmp_path)
    fake_python = tmp_path / "python.exe"
    fake_python.write_bytes(b"x")
    monkeypatch.setattr(YR, "resolve_whisper_python", lambda root="", required=False: str(fake_python))
    monkeypatch.setattr(YR, "whisper_device", lambda root="": "")
    calls = []

    class P:
        returncode = 0
        stdout = '{"torch":"2.6.0+cu124","whisper":"20250625","cuda_available":true,"cuda_device":"RTX 4070 SUPER"}\n'

    def run(cmd, **kwargs):
        calls.append(cmd)
        return P()

    monkeypatch.setattr(subprocess, "run", run)
    with YR._LOCK:
        YR._WHISPER_PREFLIGHTS.pop(str(fake_python), None)
    first = YR._whisper_preflight(root)
    second = YR._whisper_preflight(root)
    assert first["effective_device"] == "cuda"
    assert first["cuda_device"] == "RTX 4070 SUPER"
    assert second == first
    assert len(calls) == 1
    with YR._LOCK:
        YR._WHISPER_PREFLIGHTS.pop(str(fake_python), None)


def test_audio_fetch_uses_parallel_fragments_and_streams_progress(tmp_path, monkeypatch):
    monkeypatch.setenv("CSTUDIO_YTDLP_FRAGMENTS", "8")
    monkeypatch.setattr(YR, "resolve_ytdlp", lambda required=True: "/fake/yt-dlp")
    out_template = str(tmp_path / "audio.%(ext)s")
    logs = []

    class Log:
        def write(self, text): logs.append(text)
        def flush(self): pass

    class P:
        def __init__(self, cmd, **kwargs):
            self.cmd = cmd
            Path(out_template.replace("%(ext)s", "m4a")).write_bytes(b"audio")
            self.stdout = iter(["[download] 10% frag 1/10\n", "[download] 100% frag 10/10\n"])
        def wait(self): return 0

    monkeypatch.setattr(subprocess, "Popen", P)
    path = YR._download_audio("https://example.test/audio", out_template, log=Log())
    assert path.endswith("audio.m4a")
    joined = "".join(logs)
    assert "--concurrent-fragments 8" in joined
    assert "frag 10/10" in joined




def test_media_subprocess_env_exposes_resolved_ffmpeg_to_whisper(tmp_path, monkeypatch):
    tools = tmp_path / "ffmpeg-bin"
    tools.mkdir()
    ffmpeg = tools / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    ffprobe = tools / ("ffprobe.exe" if os.name == "nt" else "ffprobe")
    ffmpeg.write_bytes(b"x")
    ffprobe.write_bytes(b"x")
    monkeypatch.setattr(YR, "resolve_ffmpeg", lambda required=True: str(ffmpeg))
    monkeypatch.setattr(YR, "resolve_ffprobe", lambda required=True: str(ffprobe))
    env = YR._media_subprocess_env()
    assert env["PATH"].split(os.pathsep)[0] == str(tools)
    assert env["PYTHONUTF8"] == "1"
    assert env["PYTHONIOENCODING"] == "utf-8"
    assert YR._ffmpeg_location_args() == ["--ffmpeg-location", str(tools)]


def test_audio_first_analysis_reuses_fingerprint_without_whisper_or_download(tmp_path, monkeypatch):
    root = _harness(tmp_path)
    source_id = "2861744268"
    fp_path = Path(YR._audio_cache_file(root, "yt", source_id))
    transcript_path = Path(YR._transcript_file(root, "yt", "twitch", source_id))
    fp_path.parent.mkdir(parents=True, exist_ok=True)
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    C.write_json(str(fp_path), {"provider": "ffmpeg-temporal-features-v1", "features": [[1.0, 2.0, 3.0]] * 20})
    C.write_json(str(transcript_path), {"provider": "legacy", "segments": [{"start": 0, "end": 30, "text": "E aí"}]})
    monkeypatch.setattr(YR, "_whisper_preflight", lambda *a, **k: (_ for _ in ()).throw(AssertionError("Whisper preflight must not run")))
    monkeypatch.setattr(YR, "_download_audio", lambda *a, **k: (_ for _ in ()).throw(AssertionError("audio must not redownload")))
    result = YR._ensure_media_analysis(
        root, "yt", source_kind="twitch", source_id=source_id,
        source_url="https://www.twitch.tv/videos/2861744268", streamer="alanzoka",
        want_transcript=False,
    )
    assert result["fingerprint"]["features"]
    assert result["transcript"] is None
    assert result["cache_hit"] is True


def test_whisper_failure_does_not_redownload_same_cached_source_in_server_lifetime(tmp_path, monkeypatch):
    root = _harness(tmp_path)
    source_id = "1234567890"
    fp_path = Path(YR._audio_cache_file(root, "yt", source_id))
    fp_path.parent.mkdir(parents=True, exist_ok=True)
    C.write_json(str(fp_path), {"features": [[1.0, 2.0, 3.0]] * 16})
    fake_whisper = tmp_path / "whisper"
    fake_whisper.write_bytes(b"x")
    monkeypatch.setattr(YR, "resolve_whisper", lambda root="", required=False: str(fake_whisper))
    monkeypatch.setattr(YR, "transcript_enabled", lambda root: True)
    monkeypatch.setattr(YR, "_whisper_preflight", lambda root, log=None: {"effective_device": "cuda"})
    downloads = []

    def download(url, template, **kwargs):
        downloads.append(url)
        media = tmp_path / f"media-{len(downloads)}.mp4"
        media.write_bytes(b"audio")
        return str(media)

    monkeypatch.setattr(YR, "_download_audio", download)
    monkeypatch.setattr(
        YR, "_run_whisper",
        lambda *a, **k: (_ for _ in ()).throw(C.StudioError("ffmpeg missing from child PATH")),
    )
    with YR._LOCK:
        YR._TRANSCRIPT_FAILURES.clear()
    first = YR._ensure_media_analysis(
        root, "yt", source_kind="twitch", source_id=source_id,
        source_url="https://www.twitch.tv/videos/1234567890",
    )
    second = YR._ensure_media_analysis(
        root, "yt", source_kind="twitch", source_id=source_id,
        source_url="https://www.twitch.tv/videos/1234567890",
    )
    assert len(downloads) == 1
    assert first["fingerprint"]["features"]
    assert second["fingerprint"]["features"]
    assert "ffmpeg missing" in second["transcript_failure"]
    with YR._LOCK:
        YR._TRANSCRIPT_FAILURES.clear()


def test_streamer_language_defaults_and_config_override(tmp_path, monkeypatch):
    root = _harness(tmp_path)
    assert YR.whisper_language(root, "alanzoka") == "pt"
    assert YR.whisper_language(root, "otherstreamer") == ""
    YR.set_channel(root, "alanzoka", name="alanzoka", url="https://youtube.com/@alanzoka", language="en")
    assert YR.whisper_language(root, "alanzoka") == "en"
    monkeypatch.setenv("CSTUDIO_WHISPER_LANGUAGE_ALANZOKA", "es")
    assert YR.whisper_language(root, "alanzoka") == "es"
    monkeypatch.setenv("CSTUDIO_WHISPER_LANGUAGE", "pt")
    assert YR.whisper_language(root, "alanzoka") == "pt"
    monkeypatch.delenv("CSTUDIO_WHISPER_LANGUAGE")
    monkeypatch.delenv("CSTUDIO_WHISPER_LANGUAGE_ALANZOKA")
    YR.set_channel(root, "alanzoka", name="alanzoka", url="https://youtube.com/@alanzoka", language="auto")
    assert YR.whisper_language(root, "alanzoka") == ""


def _quality_cache_record(texts, *, duration=60.0, language="pt"):
    step = duration / max(1, len(texts))
    record = {
        "schema_version": YR.TRANSCRIPT_SCHEMA_VERSION,
        "provider": YR.TRANSCRIPT_PROVIDER,
        "timestamp_mode": "segment",
        "language_requested": language,
        "decoding_profile": {
            "name": YR.TRANSCRIPT_DECODING_PROFILE,
            "condition_on_previous_text": False,
            "word_timestamps": False,
        },
        "duration_seconds": duration,
        "segments": [
            {"start": i * step, "end": (i + 1) * step, "text": text, "words": []}
            for i, text in enumerate(texts)
        ],
    }
    record["quality"] = YR.assess_transcript_quality(record)
    record["quality_state"] = record["quality"]["state"]
    return record


def test_transcript_quality_rejects_real_e_ai_degeneration_shape():
    # Mirrors the production evidence from Twitch VOD 2861744268:
    # 864 segments = 842 "E aí", 14 empty and 8 doubled variants.
    texts = ["E aí"] * 842 + [""] * 14 + ["E aí E aí"] * 8
    record = _quality_cache_record(texts, duration=25909.22)
    quality = record["quality"]
    metrics = quality["metrics"]
    assert quality["state"] == "invalid"
    assert quality["classification"] == "hallucination_loop"
    assert metrics["dominant_text_count"] == 842
    assert metrics["dominant_text_ratio"] > 0.98
    assert metrics["unique_normalized_segments"] == 2
    assert metrics["lexical_diversity"] < 0.01


def test_transcript_quality_accepts_diverse_normal_transcript():
    texts = [
        f"segmento {i} conversa sobre jogo missao personagem objetivo numero {i % 17}"
        for i in range(120)
    ]
    record = _quality_cache_record(texts, duration=3600.0)
    quality = record["quality"]
    assert quality["state"] == "valid"
    assert quality["classification"] == "usable"
    assert quality["metrics"]["unique_ratio"] > 0.9


def test_transcript_cache_invalidates_legacy_wrong_language_or_old_profile(tmp_path):
    root = _harness(tmp_path)
    current = _quality_cache_record(["oi esta e uma frase suficientemente normal"], duration=1.0)
    assert YR._transcript_cache_compatible(current, root, "alanzoka")
    legacy = {**current, "provider": "openai-whisper-turbo-v1"}
    assert not YR._transcript_cache_compatible(legacy, root, "alanzoka")
    wrong = {**current, "language_requested": "en"}
    assert not YR._transcript_cache_compatible(wrong, root, "alanzoka")
    old_profile = {**current, "decoding_profile": {"name": "legacy", "condition_on_previous_text": True}}
    assert not YR._transcript_cache_compatible(old_profile, root, "alanzoka")


def test_degenerate_cache_becomes_stale_but_fingerprint_remains_reusable(tmp_path, monkeypatch):
    root = _harness(tmp_path)
    source_id = "2861744268"
    transcript_path = Path(YR._transcript_file(root, "yt", "twitch", source_id))
    fp_path = Path(YR._audio_cache_file(root, "yt", source_id))
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    fp_path.parent.mkdir(parents=True, exist_ok=True)
    old = {
        "schema_version": 1,
        "provider": "openai-whisper-turbo-segment-v2",
        "timestamp_mode": "segment",
        "language_requested": "pt",
        "duration_seconds": 25909.22,
        "segments": ([{"start": i * 30, "end": (i + 1) * 30, "text": "E aí", "words": []} for i in range(842)]
                     + [{"start": 25260 + i, "end": 25261 + i, "text": "", "words": []} for i in range(14)]
                     + [{"start": 25274 + i, "end": 25275 + i, "text": "E aí E aí", "words": []} for i in range(8)]),
    }
    C.write_json(str(transcript_path), old)
    original_fp = {"provider": "ffmpeg-temporal-features-v1", "features": [[1.0, 2.0, 3.0]] * 16}
    C.write_json(str(fp_path), original_fp)
    ok, reason = YR._transcript_cache_status(old, root, "alanzoka")
    assert not ok
    assert "hallucination_loop" in reason

    fake_whisper = tmp_path / "whisper"
    fake_whisper.write_bytes(b"x")
    monkeypatch.setattr(YR, "resolve_whisper", lambda root="", required=False: str(fake_whisper))
    monkeypatch.setattr(YR, "_whisper_preflight", lambda root, log=None: {"effective_device": "cuda"})
    downloads = []
    monkeypatch.setattr(YR, "_download_audio", lambda url, template, **kwargs: downloads.append(url) or str(tmp_path / "audio.m4a"))
    monkeypatch.setattr(YR, "extract_audio_features", lambda *a, **k: (_ for _ in ()).throw(AssertionError("fingerprint must be reused")))
    fresh = _quality_cache_record([
        f"fala distinta numero {i} com contexto de gameplay e objetivo {i % 9}" for i in range(80)
    ], duration=600.0)
    monkeypatch.setattr(YR, "_run_whisper", lambda *a, **k: fresh)
    (tmp_path / "audio.m4a").write_bytes(b"audio")

    result = YR._ensure_media_analysis(
        root, "yt", source_kind="twitch", source_id=source_id,
        source_url="https://www.twitch.tv/videos/2861744268", streamer="alanzoka",
    )
    assert len(downloads) == 1
    assert result["transcript"]["quality_state"] == "valid"
    assert result["fingerprint"]["features"] == original_fp["features"]


def test_transcript_alignment_finds_piecewise_correspondence_with_cut():
    twitch_words = [f"token{i}" for i in range(140)]
    # Mirror contains two chunks from one Twitch VOD; 20 Twitch words were removed.
    youtube_words = twitch_words[20:80] + twitch_words[100:135]
    twitch = _transcript_from_words(twitch_words, offset=0.0, step=1.0)
    youtube = _transcript_from_words(youtube_words, offset=0.0, step=1.0)
    aligned = YR.align_transcripts(youtube, twitch)
    assessment = aligned["assessment"]
    assert assessment["state"] == "strong"
    assert assessment["good_anchors"] >= 3
    anchors = sorted(aligned["anchors"], key=lambda a: a["youtube_time"])
    assert anchors[0]["twitch_time"] - anchors[0]["youtube_time"] == pytest.approx(20.0, abs=1.5)
    assert anchors[-1]["twitch_time"] - anchors[-1]["youtube_time"] == pytest.approx(40.0, abs=1.5)


def test_verify_match_audio_first_verified_skips_whisper(tmp_path, monkeypatch):
    root = _harness(tmp_path)
    _write_vod(root); _write_index(root)
    rec = YR.generate_candidates(root, "yt")["matches"][0]
    monkeypatch.setattr(YR, "enrich_video_metadata", lambda video, log=None: {**video, "duration": 1000.0})
    fp = {"duration_seconds": 3000.0, "features": [[float(i % 9), float((i * 3) % 7), float((i * 5) % 11)] for i in range(7000)]}
    calls = []

    def analysis(root, slug, **kwargs):
        calls.append(kwargs)
        assert kwargs["want_transcript"] is False
        return {"transcript": None, "fingerprint": fp, "cache_hit": True, "media_path": ""}

    audio_anchors = [
        {"youtube_time": 100.0, "twitch_time": 500.0, "similarity": .95, "duration": YR.ANCHOR_SECONDS},
        {"youtube_time": 300.0, "twitch_time": 700.0, "similarity": .94, "duration": YR.ANCHOR_SECONDS},
        {"youtube_time": 500.0, "twitch_time": 900.0, "similarity": .93, "duration": YR.ANCHOR_SECONDS},
        {"youtube_time": 700.0, "twitch_time": 1100.0, "similarity": .92, "duration": YR.ANCHOR_SECONDS},
    ]
    monkeypatch.setattr(YR, "_ensure_media_analysis", analysis)
    monkeypatch.setattr(YR, "_audio_only_anchors_from_caches", lambda *a, **k: audio_anchors)
    monkeypatch.setattr(
        YR, "confirm_audio_anchors_with_localized_transcripts",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("Whisper must not run after audiovisual VERIFIED")),
    )
    done = YR.verify_match(root, "yt", "1234567890", rec["youtube_video_id"])
    assert len(calls) == 2
    assert done["state"] == "verified"
    assert done["verification"]["mode"] == "audio-first"
    assert done["verification"]["providers"]["transcript"] == "not_needed"
    assert done["verification"]["transcript"]["full_source_whisper"] is False


def test_verify_match_likely_audio_uses_localized_text_but_cannot_promote_verified(tmp_path, monkeypatch):
    root = _harness(tmp_path)
    _write_vod(root); _write_index(root)
    rec = YR.generate_candidates(root, "yt")["matches"][0]
    monkeypatch.setattr(YR, "enrich_video_metadata", lambda video, log=None: {**video, "duration": 1000.0})
    fp = {"duration_seconds": 3000.0, "features": [[1.0, 2.0, 3.0]] * 7000}
    monkeypatch.setattr(
        YR, "_ensure_media_analysis",
        lambda *a, **k: {"transcript": None, "fingerprint": fp, "cache_hit": True, "media_path": ""},
    )
    audio_anchors = [
        {"youtube_time": 100.0, "twitch_time": 500.0, "similarity": .91, "duration": YR.ANCHOR_SECONDS},
        {"youtube_time": 300.0, "twitch_time": 700.0, "similarity": .90, "duration": YR.ANCHOR_SECONDS},
        {"youtube_time": 500.0, "twitch_time": 900.0, "similarity": .79, "duration": YR.ANCHOR_SECONDS},
        {"youtube_time": 700.0, "twitch_time": 1100.0, "similarity": .77, "duration": YR.ANCHOR_SECONDS},
    ]
    monkeypatch.setattr(YR, "_audio_only_anchors_from_caches", lambda *a, **k: audio_anchors)
    fake_whisper = tmp_path / "whisper"
    fake_whisper.write_bytes(b"x")
    monkeypatch.setattr(YR, "resolve_whisper", lambda root="", required=False: str(fake_whisper))
    localized_calls = []

    def localized(*args, **kwargs):
        localized_calls.append(kwargs)
        return {
            "method": YR.LOCALIZED_TRANSCRIPT_PROVIDER,
            "anchors": [{"similarity": .92}, {"similarity": .90}, {"similarity": .89}],
            "assessment": {"state": "strong", "good_anchors": 3, "total_anchors": 3, "median_similarity": .90, "timeline_consistency": "strong"},
        }

    monkeypatch.setattr(YR, "confirm_audio_anchors_with_localized_transcripts", localized)
    done = YR.verify_match(root, "yt", "1234567890", rec["youtube_video_id"])
    assert localized_calls
    assert done["state"] == "likely"
    assert done["verification"]["mode"] == "audio-first+localized-transcript"
    assert done["verification"]["providers"]["transcript"] == "localized_complete"
    assert done["state"] != "verified"


def test_localized_quality_uses_processed_duration_not_absolute_timeline():
    record = _quality_cache_record([
        "fala distinta com bastante contexto para comparar o trecho corretamente",
        "segunda fala diferente com objetivo missao personagem e conversa",
        "terceiro trecho de gameplay com palavras suficientes para matching",
    ], duration=15000.0)
    record["processed_duration_seconds"] = 144.0
    quality = YR.assess_transcript_quality(record)
    assert quality["state"] == "valid"
    assert quality["metrics"]["duration_seconds"] == pytest.approx(144.0)


def test_resolve_uses_global_source_assignment_instead_of_per_vod_shortlist(tmp_path, monkeypatch):
    root = _harness(tmp_path)
    _write_vod(root); _write_index(root)
    candidate = YR.generate_candidates(root, "yt")["matches"][0]
    monkeypatch.setattr(YR, "generate_candidates", lambda *a, **k: {"candidates": 1, "matches": [candidate]})
    calls = []
    def global_assign(*args, **kwargs):
        calls.append((args, kwargs))
        return {"verified": 0, "likely": 1, "errors": [], "videos": 1, "completed": 1,
                "resumed": 0, "evaluated_pairs": 1, "skipped_pairs": 0, "assignments": []}
    monkeypatch.setattr(YR, "_resolve_global_assignments", global_assign)
    out = YR.resolve(root, "yt")
    assert calls
    assert out["likely"] == 1

def test_enriched_metadata_can_skip_expensive_media(tmp_path, monkeypatch):
    root = _harness(tmp_path)
    _write_vod(root); _write_index(root)
    rec = YR.generate_candidates(root, "yt")["matches"][0]
    monkeypatch.setattr(
        YR,
        "enrich_video_metadata",
        lambda video, log=None: {**video, "upload_date": "20200101", "duration": 7800},
    )
    monkeypatch.setattr(
        YR,
        "_ensure_media_analysis",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("media should not be downloaded")),
    )
    done = YR.verify_match(root, "yt", "1234567890", rec["youtube_video_id"])
    assert done["state"] == "candidate"
    assert done["verification"]["mode"] == "metadata-rejected-before-media"


def test_faster_whisper_discovery_and_auto_backend(tmp_path):
    apps = tmp_path / "Applications"
    root = apps / "Youtube-Channel"
    (root / "studio").mkdir(parents=True)
    C.write_json(str(root / "studio" / "youtube-mirrors.json"), YR.default_config())
    home = apps / "LLMS" / "Whisper"
    python = home / ".venv" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.write_bytes(b"x")
    model = home / "faster-whisper-large-v3-turbo"
    model.mkdir(parents=True)
    (model / "model.bin").write_bytes(b"x")
    assert Path(YR.resolve_faster_whisper_model(str(root))).resolve() == model.resolve()
    assert Path(YR.resolve_whisper_python(str(root))).resolve() == python.resolve()
    assert YR.transcription_backend(str(root)) == "faster-whisper"


def test_faster_whisper_preflight_reports_ctranslate2_cuda_and_is_cached(tmp_path, monkeypatch):
    root = _harness(tmp_path)
    fake_python = tmp_path / "python.exe"
    fake_python.write_bytes(b"x")
    model = tmp_path / "faster-model"
    model.mkdir()
    (model / "model.bin").write_bytes(b"x")
    monkeypatch.setattr(YR, "resolve_whisper_python", lambda root="", required=False: str(fake_python))
    monkeypatch.setattr(YR, "resolve_faster_whisper_model", lambda root="", required=False: str(model))
    monkeypatch.setattr(YR, "whisper_device", lambda root="": "cuda")
    calls = []

    class P:
        returncode = 0
        stdout = '{"faster_whisper":"1.2.1","ctranslate2":"4.8.2","cuda_devices":1}\n'

    def run(cmd, **kwargs):
        calls.append(cmd)
        return P()

    monkeypatch.setattr(subprocess, "run", run)
    with YR._LOCK:
        YR._FASTER_WHISPER_PREFLIGHTS.clear()
    first = YR._faster_whisper_preflight(root)
    second = YR._faster_whisper_preflight(root)
    assert first["effective_device"] == "cuda"
    assert first["faster_whisper"] == "1.2.1"
    assert first["ctranslate2"] == "4.8.2"
    assert first["batch_size"] == 8
    assert second == first
    assert len(calls) == 1
    with YR._LOCK:
        YR._FASTER_WHISPER_PREFLIGHTS.clear()


def test_faster_whisper_runner_spec_uses_batching_and_independent_windows(tmp_path, monkeypatch):
    root = _harness(tmp_path)
    media = tmp_path / "clip.m4a"
    media.write_bytes(b"audio")
    fake_python = tmp_path / "python.exe"
    fake_python.write_bytes(b"x")
    model = tmp_path / "faster-model"
    model.mkdir()
    (model / "model.bin").write_bytes(b"x")
    monkeypatch.setattr(YR, "resolve_whisper_python", lambda root="", required=False: str(fake_python))
    monkeypatch.setattr(YR, "resolve_faster_whisper_model", lambda root="", required=False: str(model))
    monkeypatch.setattr(YR, "_faster_whisper_preflight", lambda root, log=None: {
        "model": str(model), "effective_device": "cuda", "compute_type": "float16",
        "batch_size": 8, "faster_whisper": "1.2.1", "ctranslate2": "4.8.2",
    })
    captured = {}

    class P:
        def __init__(self, cmd, **kwargs):
            spec_path = Path(cmd[cmd.index("--spec") + 1])
            output_path = Path(cmd[cmd.index("--output") + 1])
            captured["spec"] = json.loads(spec_path.read_text(encoding="utf-8"))
            output_path.write_text(json.dumps({
                "text": "fala distinta para matching",
                "language": "pt",
                "segments": [{"start": 10.0, "end": 20.0, "text": "fala distinta para matching", "words": []}],
                "backend": {"faster_whisper": "1.2.1", "ctranslate2": "4.8.2"},
                "processed_duration_seconds": 48.0,
            }), encoding="utf-8")
            self.stdout = iter(['CSTUDIO_FW {"event":"done","segments":1}\n'])
        def wait(self):
            return 0

    monkeypatch.setattr(subprocess, "Popen", P)
    transcript = YR._run_faster_whisper(
        root, str(media), source_kind="twitch", source_id="123", streamer="alanzoka",
        clip_timestamps=[(10.0, 58.0)],
    )
    spec = captured["spec"]
    assert spec["batch_size"] == 8
    assert spec["compute_type"] == "float16"
    assert spec["device"] == "cuda"
    assert spec["language"] == "pt"
    assert spec["inputs"][0]["ranges"] == [[10.0, 58.0]]
    assert transcript["provider"] == YR.TRANSCRIPT_PROVIDER_FASTER
    profile = transcript["decoding_profile"]
    assert profile["condition_on_previous_text"] is False
    assert profile["backend"] == "faster-whisper"
    assert profile["batch_size"] == 8
    assert transcript["quality_state"] == "valid"


def test_faster_whisper_failure_falls_back_to_openai(tmp_path, monkeypatch):
    root = _harness(tmp_path)
    media = tmp_path / "clip.m4a"
    media.write_bytes(b"audio")
    fake_openai = tmp_path / "whisper"
    fake_openai.write_bytes(b"x")
    monkeypatch.setattr(YR, "transcription_backend", lambda root="": "faster-whisper")
    monkeypatch.setattr(YR, "_run_faster_whisper", lambda *a, **k: (_ for _ in ()).throw(C.StudioError("CUDA DLL missing")))
    monkeypatch.setattr(YR, "resolve_whisper", lambda root="", required=False: str(fake_openai))
    expected = {"provider": YR.TRANSCRIPT_PROVIDER, "segments": [{"start": 0, "end": 1, "text": "ok"}]}
    monkeypatch.setattr(YR, "_run_openai_whisper", lambda *a, **k: expected)
    result = YR._run_whisper(root, str(media), source_kind="youtube", source_id="abc123")
    assert result is expected


def test_likely_audio_can_use_faster_whisper_when_openai_executable_is_absent(tmp_path, monkeypatch):
    root = _harness(tmp_path)
    _write_vod(root); _write_index(root)
    rec = YR.generate_candidates(root, "yt")["matches"][0]
    monkeypatch.setattr(YR, "enrich_video_metadata", lambda video, log=None: {**video, "duration": 1000.0})
    fp = {"duration_seconds": 3000.0, "features": [[1.0, 2.0, 3.0]] * 7000}
    monkeypatch.setattr(YR, "_ensure_media_analysis", lambda *a, **k: {
        "transcript": None, "fingerprint": fp, "cache_hit": True, "media_path": "",
    })
    audio_anchors = [
        {"youtube_time": 100.0, "twitch_time": 500.0, "similarity": .91, "duration": YR.ANCHOR_SECONDS},
        {"youtube_time": 300.0, "twitch_time": 700.0, "similarity": .90, "duration": YR.ANCHOR_SECONDS},
        {"youtube_time": 500.0, "twitch_time": 900.0, "similarity": .79, "duration": YR.ANCHOR_SECONDS},
        {"youtube_time": 700.0, "twitch_time": 1100.0, "similarity": .77, "duration": YR.ANCHOR_SECONDS},
    ]
    monkeypatch.setattr(YR, "_audio_only_anchors_from_caches", lambda *a, **k: audio_anchors)
    monkeypatch.setattr(YR, "transcription_backend", lambda root="": "faster-whisper")
    monkeypatch.setattr(YR, "resolve_whisper", lambda root="", required=False: "")
    calls = []
    monkeypatch.setattr(YR, "confirm_audio_anchors_with_localized_transcripts", lambda *a, **k: calls.append(k) or {
        "method": YR.LOCALIZED_TRANSCRIPT_PROVIDER,
        "anchors": [{"similarity": .9}, {"similarity": .88}],
        "assessment": {"state": "likely", "good_anchors": 2, "total_anchors": 2, "median_similarity": .89, "timeline_consistency": "strong"},
    })
    done = YR.verify_match(root, "yt", "1234567890", rec["youtube_video_id"])
    assert calls
    assert done["state"] == "likely"
    assert done["verification"]["providers"]["transcript"] == "localized_complete"


def test_faster_whisper_quality_rejection_does_not_disable_backend_or_waste_openai_retry(tmp_path, monkeypatch):
    root = _harness(tmp_path)
    media = tmp_path / "silent.m4a"
    media.write_bytes(b"audio")
    monkeypatch.setattr(YR, "transcription_backend", lambda root="": "faster-whisper")
    monkeypatch.setattr(
        YR, "_run_faster_whisper",
        lambda *a, **k: (_ for _ in ()).throw(YR._TranscriptContentError("insufficient localized speech")),
    )
    monkeypatch.setattr(
        YR, "_run_openai_whisper",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("content rejection must not trigger a second engine")),
    )
    with pytest.raises(YR._TranscriptContentError):
        YR._run_whisper(root, str(media), source_kind="youtube", source_id="silent1")


def test_webvtt_parser_creates_timestamped_caption_transcript(tmp_path):
    path = tmp_path / "x.pt.vtt"
    path.write_text(
        "WEBVTT\n\n00:00:10.000 --> 00:00:12.500\n<c>fala de teste</c>\n\n"
        "00:00:13.000 --> 00:00:15.000\nsegunda fala\n",
        encoding="utf-8",
    )
    rec = YR._parse_webvtt(str(path), video_id="abcDEF12345", language="pt")
    assert rec["provider"] == "yt-dlp-youtube-captions-v1"
    assert rec["segments"][0]["start"] == 10.0
    assert rec["segments"][0]["text"] == "fala de teste"
    assert YR._transcript_text_in_range(rec, 9.0, 12.9) == "fala de teste"


def test_metadata_cache_deduplicates_ytdlp_calls(tmp_path, monkeypatch):
    root = _harness(tmp_path)
    calls = []
    def enrich(video, log=None):
        calls.append(video["video_id"])
        return {**video, "duration": 123.0, "channel_id": "UC1111111111111111111111"}
    monkeypatch.setattr(YR, "enrich_video_metadata", enrich)
    video = {"video_id": "abcDEF12345", "url": "https://youtube.com/watch?v=abcDEF12345"}
    first = YR.enrich_video_metadata_cached(root, "yt", video)
    second = YR.enrich_video_metadata_cached(root, "yt", video)
    assert first["duration"] == second["duration"] == 123.0
    assert calls == ["abcDEF12345"]


def test_match_window_details_reports_competing_peak_margin():
    query = [[float(i % 5), float((i * 2) % 7), float((i * 3) % 11)] for i in range(20)]
    target = [[0.0, 0.0, 0.0] for _ in range(200)]
    target[20:40] = query
    target[120:140] = query
    details = YR.match_feature_window_details(query, target, step_frames=1)
    assert details["similarity"] > 0.99
    assert details["second_best"] > 0.99
    assert details["peak_margin"] < 0.01


def test_ytdlp_runtime_args_enable_supported_deno(monkeypatch):
    monkeypatch.setattr(YR, "resolve_deno", lambda required=False: "/tools/deno")
    monkeypatch.setattr(YR, "_deno_supported", lambda executable: executable == "/tools/deno")
    assert YR._yt_dlp_runtime_args() == ["--js-runtimes", "deno:/tools/deno"]


def test_webvtt_parser_deduplicates_cumulative_auto_captions(tmp_path):
    path = tmp_path / "cumulative.pt.vtt"
    path.write_text(
        "WEBVTT\n\n"
        "00:00:01.000 --> 00:00:02.000\nolá\n\n"
        "00:00:02.000 --> 00:00:03.000\nolá mundo\n\n"
        "00:00:03.000 --> 00:00:04.000\nolá mundo de novo\n",
        encoding="utf-8",
    )
    rec = YR._parse_webvtt(str(path), video_id="abcDEF12345", language="pt")
    assert [row["text"] for row in rec["segments"]] == ["olá", "mundo", "de novo"]
    assert rec["text"] == "olá mundo de novo"


def test_chromaprint_shadow_match_locates_exact_raw_fingerprint():
    query = [((i * 2654435761) ^ (i << 11)) & 0xFFFFFFFF for i in range(160)]
    target = [((i * 2246822519) ^ 0x9E3779B9) & 0xFFFFFFFF for i in range(900)]
    offset = 376
    target[offset:offset + len(query)] = query
    start, similarity = YR._match_chromaprint_window(query, target)
    assert start == offset
    assert similarity > 0.99


def test_caption_lookup_with_auto_language_skips_external_call(tmp_path, monkeypatch):
    root = _harness(tmp_path)
    monkeypatch.setattr(YR, "whisper_language", lambda root, streamer="": "auto")
    monkeypatch.setattr(YR, "resolve_ytdlp", lambda required=True: (_ for _ in ()).throw(AssertionError("yt-dlp should not run")))
    assert YR._youtube_caption_transcript(
        root, "yt", "abcDEF12345", "https://youtube.com/watch?v=abcDEF12345", streamer="other"
    ) is None
    cached = C.read_json(YR._caption_cache_file(root, "yt", "abcDEF12345"), {})
    assert cached["status"] == "skipped_auto_language"


def test_localized_youtube_fallback_warms_full_analysis_audio_once(tmp_path, monkeypatch):
    root = _harness(tmp_path)
    media = tmp_path / "youtube-full.webm"
    calls = []
    monkeypatch.setattr(YR, "_youtube_caption_transcript", lambda *a, **k: None)
    monkeypatch.setattr(YR, "_analysis_audio_cached", lambda *a, **k: "")

    def download(url, template, **kwargs):
        calls.append((url, template, kwargs.get("section")))
        media.write_bytes(b"audio")
        return str(media)

    monkeypatch.setattr(YR, "_download_audio", download)
    monkeypatch.setattr(YR, "_persist_youtube_analysis_audio", lambda *a, **k: str(media))
    monkeypatch.setattr(YR, "_download_localized_clips", lambda *a, **k: (_ for _ in ()).throw(AssertionError("range downloads should be skipped")))
    monkeypatch.setattr(YR, "_run_whisper", lambda *a, **k: {"segments": [{"start": 1.0, "end": 2.0, "text": "ok"}]})
    out = YR._localized_transcript_for_source(
        root, "yt", source_kind="youtube", source_id="abcDEF12345",
        source_url="https://youtube.com/watch?v=abcDEF12345", streamer="alanzoka",
        ranges=[(100.0, 148.0), (500.0, 548.0)], existing_media="",
    )
    assert out["segments"]
    assert len(calls) == 1
    assert calls[0][2] is None


def test_verified_requires_at_least_one_stable_offset_pair():
    anchors = [
        {"youtube_time": 100.0, "twitch_time": 1100.0, "similarity": .94},
        {"youtube_time": 1100.0, "twitch_time": 4100.0, "similarity": .93},
        {"youtube_time": 2100.0, "twitch_time": 7100.0, "similarity": .92},
    ]
    assessment = YR.assess_verification(anchors)
    assert assessment["continuous_offset_pairs"] == 0
    assert assessment["state"] == "likely"


def test_verified_allows_forward_cut_gap_with_one_continuous_pair():
    anchors = [
        {"youtube_time": 100.0, "twitch_time": 1100.0, "similarity": .94},
        {"youtube_time": 1100.0, "twitch_time": 2470.0, "similarity": .93},
        {"youtube_time": 2100.0, "twitch_time": 3474.0, "similarity": .92},
    ]
    assessment = YR.assess_verification(anchors)
    assert assessment["forward_cut_gaps"]
    assert assessment["continuous_offset_pairs"] == 1
    assert assessment["state"] == "verified"


def test_numpy_frame_feature_matches_stdlib_formula():
    if YR._np is None:
        pytest.skip("NumPy fast path not installed")
    samples = tuple(((i * 7919) % 65535) - 32768 for i in range(4000))
    raw = struct.pack("<" + "h" * len(samples), *samples)
    slow = YR._frame_feature(samples)
    fast = YR._frame_feature_numpy(raw)
    assert fast == pytest.approx(slow, rel=1e-10, abs=1e-10)


def test_numpy_exact_matcher_finds_inserted_peak_at_exact_frame():
    if YR._np is None:
        pytest.skip("NumPy fast path not installed")
    query = [[float((i * 7) % 19), float((i * 11) % 23), float((i * 13) % 29)] for i in range(56)]
    target = [[float((i * 5) % 31), float((i * 3) % 17), float((i * 2) % 37)] for i in range(700)]
    offset = 123
    target[offset:offset + len(query)] = query
    details = YR.match_feature_window_details(query, target, step_frames=8)
    assert details["engine"] == "numpy-exact"
    assert details["start_frame"] == offset
    assert details["similarity"] > 0.999


def test_global_discovery_keeps_low_metadata_video_with_strong_chapter_overlap(tmp_path, monkeypatch):
    root = _harness(tmp_path)
    vod = {
        "vod_id": "1111111111", "streamer": "alanzoka", "title": "live", "game": "Just Chatting",
        "created_at": "2026-09-01T10:00:00Z", "duration": 25000,
        "source_url": "https://www.twitch.tv/videos/1111111111",
        "chapters": [{"title": "Rocket League", "start": 1000.0, "duration": 8000.0}],
    }
    video = {
        "video_id": "rocketABC123", "streamer": "alanzoka", "title": "ROCKET LEAGUE COM OS AMIGOS",
        "description": "", "duration": 1000.0, "url": "https://youtube.com/watch?v=rocketABC123",
    }
    monkeypatch.setattr(YR, "list_twitch_vods", lambda *a, **k: [vod])
    monkeypatch.setattr(YR, "load_index", lambda *a, **k: [video])
    monkeypatch.setattr(YR, "_channel_allowed_for_video", lambda *a, **k: True)
    monkeypatch.setattr(YR, "GLOBAL_DISCOVERY_MIN_SCORE", 0.99)
    vods, pool = YR._discover_global_video_pool(root, "yt")
    assert len(vods) == 1
    assert [row["video"]["video_id"] for row in pool] == ["rocketABC123"]
    assert pool[0]["best_chapter_shared_tokens"] >= 2




def test_global_discovery_includes_temporally_plausible_placeholder_title(tmp_path, monkeypatch):
    root = _harness(tmp_path)
    vod = {
        "vod_id": "1111111111", "streamer": "alanzoka", "title": "Metal Gear continuation", "game": "Just Chatting",
        "created_at": "2026-09-01T10:00:00Z", "duration": 25000,
        "source_url": "https://www.twitch.tv/videos/1111111111", "chapters": [],
    }
    video = {
        "video_id": "placeholder1", "streamer": "alanzoka", "title": "guns5", "description": "",
        "duration": 6700.0, "url": "https://youtube.com/watch?v=placeholder1",
    }
    monkeypatch.setattr(YR, "list_twitch_vods", lambda *a, **k: [vod])
    monkeypatch.setattr(YR, "load_index", lambda *a, **k: [video])
    monkeypatch.setattr(YR, "_channel_allowed_for_video", lambda *a, **k: True)
    monkeypatch.setattr(YR, "GLOBAL_DISCOVERY_MIN_SCORE", 0.99)
    monkeypatch.setattr(YR, "GLOBAL_DISCOVERY_MIN_CHAPTER_SHARED", 99)
    monkeypatch.setattr(
        YR, "enrich_video_metadata_cached",
        lambda *a, **k: {**video, "upload_date": "20260904", "timestamp": None},
    )
    _vods, pool = YR._discover_global_video_pool(root, "yt")
    assert [row["video"]["video_id"] for row in pool] == ["placeholder1"]
    assert "production-time-window" in pool[0]["discovery_reasons"]


def test_global_discovery_excludes_old_low_signal_placeholder_after_metadata(tmp_path, monkeypatch):
    root = _harness(tmp_path)
    vod = {
        "vod_id": "1111111111", "streamer": "alanzoka", "title": "new production", "game": "Just Chatting",
        "created_at": "2026-09-01T10:00:00Z", "duration": 20000,
        "source_url": "https://www.twitch.tv/videos/1111111111", "chapters": [],
    }
    video = {
        "video_id": "oldPlaceholder", "streamer": "alanzoka", "title": "oldx", "description": "",
        "duration": 5000.0, "url": "https://youtube.com/watch?v=oldPlaceholder",
    }
    monkeypatch.setattr(YR, "list_twitch_vods", lambda *a, **k: [vod])
    monkeypatch.setattr(YR, "load_index", lambda *a, **k: [video])
    monkeypatch.setattr(YR, "_channel_allowed_for_video", lambda *a, **k: True)
    monkeypatch.setattr(YR, "GLOBAL_DISCOVERY_MIN_SCORE", 0.99)
    monkeypatch.setattr(YR, "GLOBAL_DISCOVERY_MIN_CHAPTER_SHARED", 99)
    monkeypatch.setattr(
        YR, "enrich_video_metadata_cached",
        lambda *a, **k: {**video, "upload_date": "20260820", "timestamp": None},
    )
    _vods, pool = YR._discover_global_video_pool(root, "yt")
    assert pool == []


def test_global_discovery_keeps_recent_unknown_when_metadata_probe_fails(tmp_path, monkeypatch):
    root = _harness(tmp_path)
    vod = {
        "vod_id": "1111111111", "streamer": "alanzoka", "title": "production", "game": "Just Chatting",
        "created_at": "2026-09-01T10:00:00Z", "duration": 20000,
        "source_url": "https://www.twitch.tv/videos/1111111111", "chapters": [],
    }
    video = {
        "video_id": "unknownRecent", "streamer": "alanzoka", "title": "tmp7", "description": "",
        "duration": 5000.0, "url": "https://youtube.com/watch?v=unknownRecent",
    }
    monkeypatch.setattr(YR, "list_twitch_vods", lambda *a, **k: [vod])
    monkeypatch.setattr(YR, "load_index", lambda *a, **k: [video])
    monkeypatch.setattr(YR, "_channel_allowed_for_video", lambda *a, **k: True)
    monkeypatch.setattr(YR, "GLOBAL_DISCOVERY_MIN_SCORE", 0.99)
    monkeypatch.setattr(YR, "GLOBAL_DISCOVERY_MIN_CHAPTER_SHARED", 99)
    monkeypatch.setattr(YR, "enrich_video_metadata_cached", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline")))
    _vods, pool = YR._discover_global_video_pool(root, "yt")
    assert [row["video"]["video_id"] for row in pool] == ["unknownRecent"]
    assert "recent-date-unknown" in pool[0]["discovery_reasons"]


def test_global_discovery_stops_metadata_frontier_after_old_boundary(tmp_path, monkeypatch):
    root = _harness(tmp_path)
    vod = {
        "vod_id": "1111111111", "streamer": "alanzoka", "title": "production", "game": "Just Chatting",
        "created_at": "2026-09-10T10:00:00Z", "duration": 10000,
        "source_url": "https://www.twitch.tv/videos/1111111111", "chapters": [],
    }
    videos = [
        {"video_id": f"oldVideo{i:02d}", "streamer": "alanzoka", "title": f"tmp{i}", "description": "", "duration": 1000.0,
         "url": f"https://youtube.com/watch?v=oldVideo{i:02d}"}
        for i in range(1, 6)
    ]
    calls = []
    def enrich(_root, _slug, video, **kwargs):
        calls.append(video["video_id"])
        return {**video, "upload_date": "20260801"}
    monkeypatch.setattr(YR, "list_twitch_vods", lambda *a, **k: [vod])
    monkeypatch.setattr(YR, "load_index", lambda *a, **k: videos)
    monkeypatch.setattr(YR, "_channel_allowed_for_video", lambda *a, **k: True)
    monkeypatch.setattr(YR, "GLOBAL_DISCOVERY_MIN_SCORE", 0.99)
    monkeypatch.setattr(YR, "GLOBAL_DISCOVERY_MIN_CHAPTER_SHARED", 99)
    monkeypatch.setattr(YR, "GLOBAL_DISCOVERY_OLD_BOUNDARY_STREAK", 3)
    monkeypatch.setattr(YR, "enrich_video_metadata_cached", enrich)
    _vods, pool = YR._discover_global_video_pool(root, "yt")
    assert calls == ["oldVideo01", "oldVideo02", "oldVideo03"]
    assert pool == []


def test_pair_result_reusable_only_accepts_chronology_not_run():
    chronology = {
        "state": "candidate", "policy_version": YR.VERIFICATION_POLICY_VERSION,
        "reason": "known upload date predates this Twitch VOD",
        "audio": {"assessment": {"state": "not_run"}},
    }
    transient = {
        "state": "candidate", "policy_version": YR.VERIFICATION_POLICY_VERSION,
        "reason": "YouTube duration unavailable",
        "audio": {"assessment": {"state": "not_run"}},
    }
    assert YR._pair_result_reusable(chronology) is True
    assert YR._pair_result_reusable(transient) is False


def test_completed_assignment_skips_all_media_work_on_next_run(tmp_path, monkeypatch):
    root = _harness(tmp_path)
    vod = {"vod_id": "1111111111", "streamer": "alanzoka", "created_at": "2026-09-01T10:00:00Z"}
    video = {"video_id": "abcDEF12345", "streamer": "alanzoka", "title": "Onimusha", "url": "https://youtube.com/watch?v=abcDEF12345"}
    YR.save_assignment(root, "yt", {
        "youtube_video_id": video["video_id"], "streamer": "alanzoka", "status": "completed",
        "state": "verified", "primary_vod_id": vod["vod_id"], "assigned_vod_ids": [vod["vod_id"]],
        "matcher_engine": YR._current_matcher_engine(),
        "evaluated_vod_ids": [vod["vod_id"]], "pair_results": {vod["vod_id"]: {"vod_id": vod["vod_id"], "state": "verified"}},
    })
    monkeypatch.setattr(YR, "_discover_global_video_pool", lambda *a, **k: ([vod], [{"video": video, "streamer": "alanzoka"}]))
    monkeypatch.setattr(YR, "_ensure_media_analysis", lambda *a, **k: (_ for _ in ()).throw(AssertionError("completed assignment must resume without media work")))
    out = YR._resolve_global_assignments(root, "yt", no_download=True)
    assert out["resumed"] == 1
    assert out["evaluated_pairs"] == 0
    assert out["verified"] == 1


def test_partial_assignment_resumes_only_missing_vod_pairs(tmp_path, monkeypatch):
    root = _harness(tmp_path)
    video = {"video_id": "abcDEF12345", "streamer": "alanzoka", "title": "Onimusha", "duration": 400.0, "url": "https://youtube.com/watch?v=abcDEF12345"}
    vod1 = {"vod_id": "1111111111", "streamer": "alanzoka", "created_at": "2026-09-01T10:00:00Z", "duration": 1000.0, "source_url": "https://www.twitch.tv/videos/1111111111", "chapters": []}
    vod2 = {"vod_id": "2222222222", "streamer": "alanzoka", "created_at": "2026-09-02T10:00:00Z", "duration": 1000.0, "source_url": "https://www.twitch.tv/videos/2222222222", "chapters": []}
    prior_result = {"vod_id": vod1["vod_id"], "state": "candidate", "candidate_score": 0.5,
                    "policy_version": YR.VERIFICATION_POLICY_VERSION, "matcher_engine": YR._current_matcher_engine(),
                    "audio": {"assessment": {"state": "candidate"}}}
    YR.save_assignment(root, "yt", {
        "youtube_video_id": video["video_id"], "streamer": "alanzoka", "status": "partial",
        "evaluated_vod_ids": [vod1["vod_id"]], "pair_results": {vod1["vod_id"]: prior_result},
    })
    monkeypatch.setattr(YR, "_discover_global_video_pool", lambda *a, **k: ([vod1, vod2], [{"video": video, "streamer": "alanzoka", "best_candidate_score": .7}]))
    monkeypatch.setattr(YR, "enrich_video_metadata_cached", lambda *a, **k: video)
    fp = {"provider": YR.AUDIO_FINGERPRINT_PROVIDER, "duration_seconds": 400.0, "features": [[float(i % 17), float(i % 13), float(i % 11)] for i in range(900)]}
    media_calls = []
    def ensure(*args, **kwargs):
        media_calls.append((kwargs["source_kind"], kwargs["source_id"]))
        return {"fingerprint": fp, "media_path": ""}
    monkeypatch.setattr(YR, "_ensure_media_analysis", ensure)
    eval_calls = []
    def evaluate(vod, video, youtube_fp, twitch_fp, log=None):
        eval_calls.append(vod["vod_id"])
        return {"vod_id": vod["vod_id"], "state": "candidate", "candidate_score": .5,
                "candidate_evidence": {}, "audio": {"method": YR.AUDIO_VERIFIER_PROVIDER, "anchors": [], "assessment": {"state": "candidate"}},
                "timeline_segments": [], "policy_version": YR.VERIFICATION_POLICY_VERSION,
                "matcher_engine": YR._current_matcher_engine()}
    monkeypatch.setattr(YR, "_evaluate_global_audio_pair", evaluate)
    out = YR._resolve_global_assignments(root, "yt", no_download=True)
    assert eval_calls == [vod2["vod_id"]]
    assert out["skipped_pairs"] == 1
    saved = YR.load_assignment(root, "yt", video["video_id"])
    assert saved["status"] == "completed"
    assert set(saved["evaluated_vod_ids"]) == {vod1["vod_id"], vod2["vod_id"]}


def test_completed_unmatched_assignment_reopens_only_deep_stage(tmp_path, monkeypatch):
    root = _harness(tmp_path)
    video = {"video_id": "abcDEF12345", "streamer": "alanzoka", "title": "Onimusha", "duration": 400.0,
             "url": "https://youtube.com/watch?v=abcDEF12345"}
    vod = {"vod_id": "1111111111", "streamer": "alanzoka", "created_at": "2026-09-01T10:00:00Z",
           "duration": 1000.0, "source_url": "https://www.twitch.tv/videos/1111111111", "chapters": []}
    pair = {
        "vod_id": vod["vod_id"], "state": "candidate", "candidate_score": .62,
        "candidate_evidence": {}, "policy_version": YR.VERIFICATION_POLICY_VERSION,
        "matcher_engine": YR._current_matcher_engine(),
        "audio": {"method": YR.AUDIO_VERIFIER_PROVIDER, "anchors": [
            {"youtube_time": 10.0, "twitch_time": 100.0, "similarity": .79},
            {"youtube_time": 100.0, "twitch_time": 190.0, "similarity": .80},
            {"youtube_time": 200.0, "twitch_time": 290.0, "similarity": .78},
        ], "assessment": {"state": "candidate", "good_anchors": 0, "median_similarity": 0.0}},
        "timeline_segments": [],
    }
    YR.save_assignment(root, "yt", {
        "youtube_video_id": video["video_id"], "streamer": "alanzoka", "status": "completed",
        "state": "unmatched", "matcher_engine": YR._current_matcher_engine(),
        "primary_vod_id": vod["vod_id"], "assigned_vod_ids": [],
        "evaluated_vod_ids": [vod["vod_id"]], "pair_results": {vod["vod_id"]: pair},
    })
    monkeypatch.setattr(YR, "_discover_global_video_pool", lambda *a, **k: ([vod], [{"video": video, "streamer": "alanzoka"}]))
    monkeypatch.setattr(YR, "enrich_video_metadata_cached", lambda *a, **k: video)
    fp = {"provider": YR.AUDIO_FINGERPRINT_PROVIDER, "duration_seconds": 400.0,
          "features": [[float(i % 17), float(i % 13), float(i % 11)] for i in range(900)]}
    monkeypatch.setattr(YR, "_ensure_media_analysis", lambda *a, **k: {"fingerprint": fp, "media_path": ""})
    monkeypatch.setattr(YR, "_evaluate_global_audio_pair", lambda *a, **k: (_ for _ in ()).throw(AssertionError("pair checkpoint must not be recomputed")))
    monkeypatch.setattr(YR, "transcript_enabled", lambda *a, **k: True)
    monkeypatch.setattr(YR, "transcription_backend", lambda *a, **k: "faster-whisper")
    deep_calls = []
    def confirm(*args, **kwargs):
        deep_calls.append(kwargs["vod"]["vod_id"])
        result = dict(kwargs["pair_result"])
        result["state"] = "verified"
        result["transcript"] = {"method": YR.LOCALIZED_TRANSCRIPT_PROVIDER, "anchors": [{"similarity": .9}, {"similarity": .88}],
                                "assessment": {"state": "likely", "good_anchors": 2, "total_anchors": 2, "median_similarity": .89}}
        return result
    monkeypatch.setattr(YR, "_maybe_localized_confirm_global_pair", confirm)

    out = YR._resolve_global_assignments(root, "yt", no_download=True)
    assert out["skipped_pairs"] == 1
    assert out["evaluated_pairs"] == 0
    assert out["deepened_pairs"] == 1
    assert out["verified"] == 1
    assert deep_calls == [vod["vod_id"]]
    saved = YR.load_assignment(root, "yt", video["video_id"])
    assert saved["state"] == "verified"
    assert saved["deep_resolution"]["status"] == "completed"


def test_deep_exhausted_unmatched_assignment_becomes_terminal(tmp_path, monkeypatch):
    root = _harness(tmp_path)
    video = {"video_id": "abcDEF12345", "streamer": "alanzoka", "title": "Onimusha", "duration": 400.0,
             "url": "https://youtube.com/watch?v=abcDEF12345"}
    vod = {"vod_id": "1111111111", "streamer": "alanzoka", "created_at": "2026-09-01T10:00:00Z",
           "duration": 1000.0, "source_url": "https://www.twitch.tv/videos/1111111111", "chapters": []}
    pair = {
        "vod_id": vod["vod_id"], "state": "candidate", "candidate_score": .62,
        "candidate_evidence": {}, "policy_version": YR.VERIFICATION_POLICY_VERSION,
        "matcher_engine": YR._current_matcher_engine(),
        "audio": {"method": YR.AUDIO_VERIFIER_PROVIDER, "anchors": [
            {"youtube_time": 10.0, "twitch_time": 100.0, "similarity": .79},
            {"youtube_time": 100.0, "twitch_time": 190.0, "similarity": .80},
        ], "assessment": {"state": "candidate", "good_anchors": 0, "median_similarity": 0.0}},
        "timeline_segments": [],
    }
    YR.save_assignment(root, "yt", {
        "youtube_video_id": video["video_id"], "streamer": "alanzoka", "status": "completed",
        "state": "unmatched", "matcher_engine": YR._current_matcher_engine(),
        "evaluated_vod_ids": [vod["vod_id"]], "pair_results": {vod["vod_id"]: pair},
    })
    monkeypatch.setattr(YR, "_discover_global_video_pool", lambda *a, **k: ([vod], [{"video": video, "streamer": "alanzoka"}]))
    monkeypatch.setattr(YR, "enrich_video_metadata_cached", lambda *a, **k: video)
    fp = {"provider": YR.AUDIO_FINGERPRINT_PROVIDER, "duration_seconds": 400.0,
          "features": [[float(i % 17), float(i % 13), float(i % 11)] for i in range(900)]}
    monkeypatch.setattr(YR, "_ensure_media_analysis", lambda *a, **k: {"fingerprint": fp, "media_path": ""})
    monkeypatch.setattr(YR, "transcript_enabled", lambda *a, **k: True)
    monkeypatch.setattr(YR, "transcription_backend", lambda *a, **k: "faster-whisper")
    def insufficient(*args, **kwargs):
        result = dict(kwargs["pair_result"])
        result["transcript"] = {"method": YR.LOCALIZED_TRANSCRIPT_PROVIDER, "anchors": [],
                                "assessment": {"state": "insufficient", "good_anchors": 0, "total_anchors": 2}}
        return result
    monkeypatch.setattr(YR, "_maybe_localized_confirm_global_pair", insufficient)

    first = YR._resolve_global_assignments(root, "yt", no_download=True)
    assert first["deepened_pairs"] == 1
    saved = YR.load_assignment(root, "yt", video["video_id"])
    assert saved["state"] == "unmatched"
    assert saved["deep_resolution"]["status"] == "completed"

    monkeypatch.setattr(YR, "_ensure_media_analysis", lambda *a, **k: (_ for _ in ()).throw(AssertionError("deep-exhausted assignment must resume")))
    second = YR._resolve_global_assignments(root, "yt", no_download=True)
    assert second["resumed"] == 1
    assert second["evaluated_pairs"] == 0
    assert second["deepened_pairs"] == 0


def test_legacy_coarse_assignment_replays_from_fingerprints_once(tmp_path, monkeypatch):
    root = _harness(tmp_path)
    video = {"video_id": "abcDEF12345", "streamer": "alanzoka", "title": "Onimusha", "duration": 400.0,
             "url": "https://youtube.com/watch?v=abcDEF12345"}
    vod = {"vod_id": "1111111111", "streamer": "alanzoka", "created_at": "2026-09-01T10:00:00Z",
           "duration": 1000.0, "source_url": "https://www.twitch.tv/videos/1111111111", "chapters": []}
    old_pair = {
        "vod_id": vod["vod_id"], "state": "candidate", "candidate_score": .6,
        "policy_version": YR.VERIFICATION_POLICY_VERSION, "matcher_engine": "stdlib-coarse",
        "audio": {"anchors": [{"similarity": .78}], "assessment": {"state": "candidate"}},
    }
    YR.save_assignment(root, "yt", {
        "youtube_video_id": video["video_id"], "streamer": "alanzoka", "status": "completed",
        "state": "unmatched", "matcher_engine": "stdlib-coarse",
        "evaluated_vod_ids": [vod["vod_id"]], "pair_results": {vod["vod_id"]: old_pair},
    })
    monkeypatch.setattr(YR, "_discover_global_video_pool", lambda *a, **k: ([vod], [{"video": video, "streamer": "alanzoka"}]))
    monkeypatch.setattr(YR, "enrich_video_metadata_cached", lambda *a, **k: video)
    fp = {"provider": YR.AUDIO_FINGERPRINT_PROVIDER, "duration_seconds": 400.0,
          "features": [[float(i % 17), float(i % 13), float(i % 11)] for i in range(900)]}
    monkeypatch.setattr(YR, "_ensure_media_analysis", lambda *a, **k: {"fingerprint": fp, "media_path": ""})
    eval_calls = []
    def exact(vod_arg, video_arg, youtube_fp, twitch_fp, log=None):
        eval_calls.append(vod_arg["vod_id"])
        return {
            "vod_id": vod_arg["vod_id"], "state": "verified", "candidate_score": .6,
            "candidate_evidence": {}, "policy_version": YR.VERIFICATION_POLICY_VERSION,
            "matcher_engine": YR._current_matcher_engine(), "timeline_segments": [],
            "audio": {"method": YR.AUDIO_VERIFIER_PROVIDER, "anchors": [],
                      "assessment": {"state": "verified", "good_anchors": 4, "median_similarity": .98}},
        }
    monkeypatch.setattr(YR, "_evaluate_global_audio_pair", exact)

    first = YR._resolve_global_assignments(root, "yt", no_download=True)
    assert eval_calls == [vod["vod_id"]]
    assert first["verified"] == 1
    saved = YR.load_assignment(root, "yt", video["video_id"])
    assert saved["matcher_engine"] == "numpy-exact"

    monkeypatch.setattr(YR, "_ensure_media_analysis", lambda *a, **k: (_ for _ in ()).throw(AssertionError("exact assignment must resume")))
    second = YR._resolve_global_assignments(root, "yt", no_download=True)
    assert second["resumed"] == 1


def test_generate_candidates_preserves_current_global_candidate_evidence(tmp_path):
    root = _harness(tmp_path)
    _write_vod(root)
    rows = _write_index(root)
    index_path = Path(YR.youtube_dir(root, "yt")) / "index" / "alanzoka.json"
    index = C.read_json(str(index_path), {})
    index["videos"][0].pop("upload_date", None)
    C.write_json(str(index_path), index)
    vod = YR.list_twitch_vods(root, "yt")[0]
    prior_video = {**rows[0], "upload_date": "20260906", "timestamp": 1788700000}
    prior_evidence = YR.score_candidate(vod, prior_video, configured_channel=True)
    YR.save_match(root, "yt", {
        "youtube_video_id": prior_video["video_id"], "youtube": prior_video,
        "twitch_vod_ids": [vod["vod_id"]], "twitch": vod, "streamer": "alanzoka",
        "state": "candidate", "candidate_score": .4321, "candidate_evidence": prior_evidence,
        "verification": {"policy_version": YR.VERIFICATION_POLICY_VERSION, "providers": {"metadata": "complete"}},
        "timeline_segments": [], "download": {"status": "not_downloaded", "path": ""},
        "rights_status": "sem_autorizacao_confirmada", "global_assignment": True,
    })
    out = YR.generate_candidates(root, "yt")
    rec = next(r for r in out["matches"] if r["youtube_video_id"] == prior_video["video_id"])
    assert rec["candidate_score"] == pytest.approx(.4321)
    assert rec["youtube"]["upload_date"] == "20260906"
    assert rec["candidate_evidence"]["signals"]["date"]["available"] is True


def test_global_assignment_requires_numpy_exact(tmp_path, monkeypatch):
    root = _harness(tmp_path)
    monkeypatch.setattr(YR, "_np", None)
    with pytest.raises(C.StudioError, match="NumPy is required"):
        YR._resolve_global_assignments(root, "yt", no_download=True)


def test_video_sort_key_uses_playlist_index_when_flat_dates_are_missing():
    rows = [
        {"video_id": "legacy", "playlist_index": None, "timestamp": None, "upload_date": ""},
        {"video_id": "second", "playlist_index": 2, "timestamp": None, "upload_date": ""},
        {"video_id": "first", "playlist_index": 1, "timestamp": None, "upload_date": ""},
    ]
    ordered = sorted(rows, key=YR._video_sort_key, reverse=True)
    assert [row["video_id"] for row in ordered] == ["first", "second", "legacy"]
