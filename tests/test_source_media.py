import json
import os
import shutil
from pathlib import Path

from cstudio import core as C
from cstudio import pipeline as PL
from cstudio import source_media as SM
from cstudio import video_plans as VP

REPO = Path(__file__).resolve().parents[1]


def _root(tmp_path):
    root = tmp_path / "harness"
    shutil.copytree(REPO / "studio", root / "studio")
    shutil.copytree(REPO / "templates", root / "templates")
    C.create_production(str(root), "Sources", slug="sources")
    vdir = root / "productions" / "sources"
    rel = ".studio/internal/ingest/twitch/test/discovery/111.json"
    path = vdir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "id": "111", "url": "https://www.twitch.tv/videos/111", "title": "Live completa",
        "timestamps": {"created_at": "2026-09-01T18:00:00Z"}, "duration": {"seconds": 7200},
    }), encoding="utf-8")
    PL.register_asset(str(root), "sources", "twitch-vod-111", "vod-metadata", rel)
    return str(root)


def _write_transcript(root, asset_id, text="alan toma um susto e começa a rir"):
    vdir = Path(root) / "productions" / "sources"
    paths = SM.transcript_paths(root, "sources", asset_id)
    transcript = {
        "schema_version": SM.EDITORIAL_TRANSCRIPT_SCHEMA_VERSION,
        "provider": SM.EDITORIAL_TRANSCRIPT_PROVIDER,
        "asset_id": asset_id,
        "source_sha256": "",
        "source_identity": SM._source_identity(asset_id),
        "source_mode": "temporary-audio",
        "model": "large-v3-turbo",
        "language": "pt",
        "word_timestamps": False,
        "timestamp_mode": "segment",
        "duration_seconds": 7200,
        "segment_count": 1,
        "word_count": len(text.split()),
        "text": text,
        "segments": [{
            "start": 125.0, "end": 129.0, "text": text,
            "words": [],
        }],
    }
    (vdir / paths["json"]).write_text(json.dumps(transcript, ensure_ascii=False), encoding="utf-8")
    (vdir / paths["text"]).write_text(f"[00:02:05 --> 00:02:09] {text}\n", encoding="utf-8")
    (vdir / paths["windows"]).write_text(json.dumps({"start": 0, "end": 300, "text": text}, ensure_ascii=False) + "\n", encoding="utf-8")


def test_twitch_download_command_uses_ytdlp_and_optional_auth(tmp_path, monkeypatch):
    root = _root(tmp_path)
    monkeypatch.setattr(SM.YR, "resolve_ytdlp", lambda: "yt-dlp")
    monkeypatch.setattr(SM.YR, "resolve_ffmpeg", lambda required=False: "ffmpeg")
    monkeypatch.setenv("CSTUDIO_TWITCH_COOKIES_FROM_BROWSER", "chrome")
    cmd = SM.build_twitch_download_command(root, "sources", "111")
    assert cmd[0] == "yt-dlp"
    assert "https://www.twitch.tv/videos/111" in cmd
    assert "--continue" in cmd and "--write-info-json" in cmd
    assert cmd[cmd.index("--cookies-from-browser") + 1] == "chrome"
    assert cmd[cmd.index("-f") + 1] == "best"
    assert cmd[cmd.index("--concurrent-fragments") + 1] == "8"


def test_twitch_download_registers_first_class_video_source(tmp_path, monkeypatch):
    root = _root(tmp_path)
    monkeypatch.setattr(SM.YR, "resolve_ytdlp", lambda: "yt-dlp")
    monkeypatch.setattr(SM.YR, "resolve_ffmpeg", lambda required=False: "ffmpeg")
    monkeypatch.setattr(SM.YR, "_probe_media", lambda path: {"duration": 7200, "height": 1080})

    def fake_stream(cmd, cwd=None, log=None, env=None):
        template = cmd[cmd.index("-o") + 1]
        media = template.replace("%(ext)s", "mp4")
        Path(media).parent.mkdir(parents=True, exist_ok=True)
        Path(media).write_bytes(b"full-twitch-vod")
        return 0

    monkeypatch.setattr(SM, "_stream_process", fake_stream)
    rec = SM.download_twitch_vod(root, "sources", "111")
    assert rec["asset_id"] == "twitch-video-111"
    assert rec["status"] == "completed"
    assert SM.asset_path(root, "sources", "twitch-video-111").endswith("111.mp4")
    catalog = VP.source_catalog(root, "sources")
    assert catalog[0]["twitch_media"]["asset_id"] == "twitch-video-111"
    assert catalog[0]["proposal_ready"] is False  # transcription is still required


def test_official_whisper_editorial_command_uses_segment_timestamps_for_discovery(tmp_path, monkeypatch):
    root = _root(tmp_path)
    monkeypatch.setattr(SM.YR, "resolve_whisper_python", lambda root, required=False: "python")
    monkeypatch.setattr(SM.YR, "resolve_whisper", lambda root, required=True: "whisper")
    monkeypatch.setattr(SM.YR, "_whisper_model_cli", lambda root: ("turbo", ""))
    monkeypatch.setattr(SM.YR, "whisper_device", lambda root: "cuda")
    monkeypatch.setattr(SM.YR, "whisper_language", lambda root, streamer: "pt")
    cmd = SM._editorial_whisper_command(root, "chunk.wav", "out", streamer="test")
    assert cmd[:3] == ["python", "-m", "whisper"]
    assert cmd[cmd.index("--model") + 1] == "turbo"
    assert cmd[cmd.index("--word_timestamps") + 1] == "False"
    assert cmd[cmd.index("--condition_on_previous_text") + 1] == "False"
    assert cmd[cmd.index("--device") + 1] == "cuda"
    assert cmd[cmd.index("--language") + 1] == "pt"


def test_full_twitch_transcript_is_required_while_youtube_is_enrichment(tmp_path):
    root = _root(tmp_path)
    vdir = Path(root) / "productions" / "sources"
    tw_rel = ".studio/internal/ingest/twitch/media/111/111.mp4"
    tw = vdir / tw_rel; tw.parent.mkdir(parents=True, exist_ok=True); tw.write_bytes(b"twitch")
    PL.register_asset(root, "sources", "twitch-video-111", "video-source", tw_rel)
    yt_rel = ".studio/internal/ingest/youtube/media/test/yt111/yt111.mp4"
    yt = vdir / yt_rel; yt.parent.mkdir(parents=True, exist_ok=True); yt.write_bytes(b"youtube")
    PL.register_asset(root, "sources", "youtube-yt111", "video-source", yt_rel)
    assignment = vdir / ".studio/internal/ingest/youtube/assignments/yt111.json"
    assignment.parent.mkdir(parents=True, exist_ok=True)
    assignment.write_text(json.dumps({"state":"verified","youtube_video_id":"yt111","assigned_vod_ids":["111"],"youtube":{"video_id":"yt111","title":"Master"}}), encoding="utf-8")
    _write_transcript(root, "youtube-yt111", "vídeo editado do youtube")
    row = VP.source_catalog(root, "sources")[0]
    assert row["transcript_ready"] is True
    assert row["full_vod_transcript_ready"] is False
    assert row["proposal_ready"] is False
    _write_transcript(root, "twitch-video-111")
    row = VP.source_catalog(root, "sources")[0]
    assert row["full_vod_transcript_ready"] is True
    assert row["proposal_ready"] is True
    context = SM.transcript_context(root, "sources", ["twitch-video-111", "youtube-yt111"], query="susto")
    assert {x["asset_id"] for x in context["transcripts"]} == {"twitch-video-111", "youtube-yt111"}
    assert context["relevant_excerpts"][0]["asset_id"] == "twitch-video-111"


def test_discovery_transcription_is_one_pass_segment_only_and_reused(tmp_path, monkeypatch):
    root = _root(tmp_path)
    vdir = Path(root) / "productions" / "sources"
    rel = ".studio/internal/ingest/twitch/media/111/111.mp4"
    media = vdir / rel; media.parent.mkdir(parents=True, exist_ok=True); media.write_bytes(b"media")
    PL.register_asset(root, "sources", "twitch-video-111", "video-source", rel)
    monkeypatch.setattr(SM, "_duration_seconds", lambda path: 3700.0)
    monkeypatch.setattr(SM.YR, "whisper_language", lambda root, streamer: "pt")
    monkeypatch.setattr(SM, "refresh_transcript_alignments", lambda *args, **kwargs: [])
    calls = []

    def fake_run_whisper(root_arg, media_path, *, source_kind, source_id, streamer="", log=None):
        calls.append((media_path, source_kind, source_id, streamer))
        return {
            "provider": "faster-whisper",
            "model": "large-v3-turbo",
            "device": "cuda",
            "language": "pt",
            "processed_duration_seconds": 3700.0,
            "decoding_profile": {"backend": "faster-whisper"},
            "text": "fala zero fala um",
            "segments": [
                {"start": 0.0, "end": 2.0, "text": "fala zero", "words": [{"word": "fala", "start": 0.0, "end": 0.5}]},
                {"start": 1800.0, "end": 1802.0, "text": "fala um", "words": [{"word": "fala", "start": 1800.0, "end": 1800.5}]},
            ],
        }

    monkeypatch.setattr(SM.YR, "_run_whisper", fake_run_whisper)
    rec = SM.transcribe_asset(root, "sources", "twitch-video-111")
    assert len(calls) == 1
    assert calls[0][1:3] == ("editorial", "twitch-video-111")
    assert rec["model"] == "large-v3-turbo"
    assert rec["word_timestamps"] is False
    assert rec["timestamp_mode"] == "segment"
    assert rec["segment_count"] == 2
    assert rec["duration_seconds"] == 3700.0
    assert all(seg["words"] == [] for seg in rec["segments"])
    paths = SM.transcript_paths(root, "sources", "twitch-video-111")
    assert (vdir / paths["text"]).is_file()
    assert (vdir / paths["windows"]).is_file()
    # Completed discovery transcript is durable and does not spend GPU again.
    SM.transcribe_asset(root, "sources", "twitch-video-111")
    assert len(calls) == 1


def test_twitch_audio_download_is_strict_bestaudio_and_temporary(tmp_path, monkeypatch):
    root = _root(tmp_path)
    monkeypatch.setattr(SM.YR, "resolve_ytdlp", lambda: "yt-dlp")
    monkeypatch.setattr(SM.YR, "resolve_ffmpeg", lambda required=False: "ffmpeg")
    cmd = SM.build_twitch_audio_download_command(root, "sources", "111")
    assert cmd[cmd.index("-f") + 1] == "bestaudio"
    assert cmd[cmd.index("--concurrent-fragments") + 1] == "8"
    output = cmd[cmd.index("-o") + 1].replace("\\", "/")
    assert "/.studio/tmp/transcription-audio/111/" in output
    assert "bestvideo" not in " ".join(cmd)


def test_twitch_download_fragment_concurrency_is_configurable(tmp_path, monkeypatch):
    root = _root(tmp_path)
    monkeypatch.setattr(SM.YR, "resolve_ytdlp", lambda: "yt-dlp")
    monkeypatch.setattr(SM.YR, "resolve_ffmpeg", lambda required=False: "ffmpeg")
    monkeypatch.setenv("CSTUDIO_YTDLP_FRAGMENTS", "12")
    source_cmd = SM.build_twitch_download_command(root, "sources", "111")
    audio_cmd = SM.build_twitch_audio_download_command(root, "sources", "111")
    assert source_cmd[source_cmd.index("--concurrent-fragments") + 1] == "12"
    assert audio_cmd[audio_cmd.index("--concurrent-fragments") + 1] == "12"


def test_audio_is_deleted_only_after_successful_transcription(tmp_path, monkeypatch):
    root = _root(tmp_path)
    vdir = Path(root) / "productions" / "sources"
    temp = vdir / ".studio/tmp/transcription-audio/111/111.m4a"
    temp.parent.mkdir(parents=True, exist_ok=True)
    temp.write_bytes(b"temporary-audio")
    rel = temp.relative_to(vdir).as_posix()
    C.write_json(SM.twitch_audio_manifest_path(root, "sources", "111"), {
        "schema_version": 1, "status": "completed", "vod_id": "111",
        "temp_path": rel, "temporary": True,
    })
    monkeypatch.setattr(SM, "transcript_status", lambda *args, **kwargs: {"status": "missing"})
    monkeypatch.setattr(SM, "transcribe_media_path", lambda *args, **kwargs: {"status": "completed", "segments": [{"start": 0, "end": 1, "text": "ok"}]})
    rec = SM.transcribe_twitch_audio(root, "sources", "111", download_if_missing=False)
    assert rec["segments"]
    assert not temp.exists()
    status = SM.twitch_audio_status(root, "sources", "111")
    assert status["status"] == "cleaned"
    assert status["file_present"] is False


def test_audio_survives_failed_transcription_for_retry(tmp_path, monkeypatch):
    root = _root(tmp_path)
    vdir = Path(root) / "productions" / "sources"
    temp = vdir / ".studio/tmp/transcription-audio/111/111.m4a"
    temp.parent.mkdir(parents=True, exist_ok=True)
    temp.write_bytes(b"temporary-audio")
    rel = temp.relative_to(vdir).as_posix()
    C.write_json(SM.twitch_audio_manifest_path(root, "sources", "111"), {
        "schema_version": 1, "status": "completed", "vod_id": "111",
        "temp_path": rel, "temporary": True,
    })
    monkeypatch.setattr(SM, "transcript_status", lambda *args, **kwargs: {"status": "missing"})
    def fail(*args, **kwargs):
        raise C.StudioError("whisper failed")
    monkeypatch.setattr(SM, "transcribe_media_path", fail)
    try:
        SM.transcribe_twitch_audio(root, "sources", "111", download_if_missing=False)
        assert False, "transcription failure should propagate"
    except C.StudioError as exc:
        assert "whisper failed" in str(exc)
    assert temp.is_file()
    assert SM.twitch_audio_status(root, "sources", "111")["status"] == "completed"


def test_candidate_precision_decodes_only_selected_ranges_with_word_timestamps(tmp_path, monkeypatch):
    root = _root(tmp_path)
    vdir = Path(root) / "productions" / "sources"
    rel = ".studio/internal/ingest/twitch/media/111/111.mp4"
    media = vdir / rel; media.parent.mkdir(parents=True, exist_ok=True); media.write_bytes(b"media")
    PL.register_asset(root, "sources", "twitch-video-111", "video-source", rel)
    video_id = "planned-video"
    video_dir = vdir / ".studio/videos" / video_id
    video_dir.mkdir(parents=True, exist_ok=True)
    C.write_json(str(video_dir / "video.json"), {
        "id": video_id, "proposal_id": "proposal-1",
        "candidate_moments": [{
            "source_asset_id": "twitch-video-111", "start_seconds": 100.0, "end_seconds": 110.0, "label": "reaction"
        }],
    })
    extracted = []
    def fake_extract(root_arg, media_path, start, duration, output, log=None):
        extracted.append((media_path, start, duration))
        Path(output).write_bytes(b"wav")
    def fake_precise(root_arg, clips, *, source_kind, source_id, streamer="", log=None, word_timestamps=False):
        assert word_timestamps is True
        assert source_kind == "candidate-precision"
        assert source_id == video_id
        assert len(clips) == 1
        assert clips[0][1:] == (97.0, 113.0)
        return {
            "provider": "faster-whisper", "model": "large-v3-turbo", "language": "pt",
            "segments": [{"start": 100.0, "end": 101.0, "text": "momento", "words": [{"word": "momento", "start": 100.0, "end": 100.5}]}],
        }
    monkeypatch.setattr(SM, "_extract_audio_chunk", fake_extract)
    monkeypatch.setattr(SM.YR, "_run_whisper_clip_files", fake_precise)
    rec = SM.generate_candidate_word_timestamps(root, "sources", video_id)
    assert extracted == [(str(media), 97.0, 16.0)]
    assert rec["word_timestamps"] is True
    assert rec["precision_scope"] == "selected-candidate-ranges-only"
    assert rec["processed_duration_seconds"] == 16.0
    assert rec["word_count"] == 1
    assert "Premiere waveform/readback" in rec["final_sync_policy"]

def test_prepare_selected_vods_reuses_completed_steps_and_enriches_local_masters(tmp_path, monkeypatch):
    root = _root(tmp_path)
    calls = []

    def fake_download(root_arg, slug, vod_id, force=False, log=None):
        calls.append(("download", vod_id))
        return {"asset_id": f"twitch-video-{vod_id}", "status": "completed"}

    def fake_transcribe(root_arg, slug, asset_id, force=False, log=None):
        calls.append(("transcribe", asset_id))
        return {"segment_count": 10, "word_count": 100}

    monkeypatch.setattr(SM, "download_twitch_vod", fake_download)
    monkeypatch.setattr(SM, "transcribe_asset", fake_transcribe)
    monkeypatch.setattr(VP, "source_catalog", lambda root_arg, slug: [{
        "vod_id": "111",
        "media_sources": [
            {"platform": "twitch", "asset_id": "twitch-video-111"},
            {"platform": "youtube", "asset_id": "youtube-yt111"},
        ],
    }])
    rec = SM.prepare_vods(root, "sources", ["111"], include_masters=True)
    assert rec["vods_prepared"] == 1
    assert calls == [
        ("download", "111"),
        ("transcribe", "twitch-video-111"),
        ("transcribe", "youtube-yt111"),
    ]
