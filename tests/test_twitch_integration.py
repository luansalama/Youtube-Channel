import csv
import json
import os
import shutil
from pathlib import Path

from cstudio import core as C
from cstudio import dashboard as D
from cstudio import twitch as TW


REPO = Path(__file__).resolve().parents[1]


def _harness(tmp_path):
    root = tmp_path / "harness"
    shutil.copytree(REPO / "studio", root / "studio")
    shutil.copytree(REPO / "templates", root / "templates")
    scraper = root / "integrations" / "twitch-scraper"
    scraper.mkdir(parents=True)
    (scraper / "scrape.mjs").write_text("console.log('fixture')\n", encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    C.create_production(str(root), "Twitch test", slug="tw", source_url="https://www.twitch.tv/alanzoka/videos")
    return str(root)


def test_build_command_exposes_worker_and_safety_flags(tmp_path, monkeypatch):
    root = _harness(tmp_path)
    monkeypatch.setattr(TW, "resolve_bun", lambda: "/fake/bun")
    spec = TW.build_command(
        root, "tw", "alanzoka", "https://www.twitch.tv/videos/2864229186",
        threads=8, force=True, resume=False,
    )
    assert spec["effective_threads"] == 8
    assert spec["cmd"][-4:] == ["--threads", "8", "--force", "--no-resume"]
    assert "--threads" in spec["cmd"] and "8" in spec["cmd"]
    assert "--force" in spec["cmd"] and "--no-resume" in spec["cmd"]
    assert spec["output_dir"].endswith(os.path.join("ingest", "twitch", "alanzoka"))

    seq = TW.build_command(root, "tw", "alanzoka", "3", threads=8, sequential=True)
    assert seq["effective_threads"] == 1
    assert "--sequential" in seq["cmd"]
    assert "--threads" not in seq["cmd"]


def test_import_outputs_registers_metadata_and_chat_as_blocked_assets(tmp_path):
    root = _harness(tmp_path)
    out = Path(TW.output_dir(root, "tw", "alanzoka"))
    (out / "discovery").mkdir(parents=True)
    (out / "chat").mkdir(parents=True)
    (out / "raw").mkdir(parents=True)
    vod = "2864229186"
    (out / "discovery" / f"{vod}.json").write_text(json.dumps({"vod_id": vod}), encoding="utf-8")
    (out / "chat" / f"{vod}.json").write_text(json.dumps({"vod_id": vod, "comments": []}), encoding="utf-8")
    (out / "raw" / f"{vod}.json").write_text(json.dumps({"vod_id": vod, "raw": True}), encoding="utf-8")

    imported = TW.import_outputs(root, "tw", str(out))
    assert {row["asset_id"] for row in imported} == {f"twitch-vod-{vod}", f"twitch-chat-{vod}"}

    assets_path = Path(C.prod_path(root, "tw")) / ".studio" / "internal" / "ingest" / "assets.csv"
    with assets_path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    twitch_rows = [row for row in rows if row["asset_id"].startswith("twitch-")]
    assert len(twitch_rows) == 2
    assert all(row["rights_status"] == "sem_autorizacao_confirmada" for row in twitch_rows)
    assert all(row["sha256"] != "missing-file" for row in twitch_rows)
    assert not any(row["kind"] == "raw" for row in twitch_rows)


def test_dashboard_has_twitch_ingest_controls(tmp_path):
    root = _harness(tmp_path)
    html = D.render(root, "twitch", "tw")
    assert "Twitch Ingest" in html
    assert "--threads 8" in html
    assert "name='threads'" in html
    assert '>8 workers</option>' in html
    assert "name='sequential'" in html
    assert "name='force'" in html
    assert "name='no_resume'" in html
    assert "value='alanzoka'" in html
