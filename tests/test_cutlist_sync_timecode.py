"""Timecodes + cutlist + sincronização (determinístico)."""
import os

import pytest

from cstudio import cutlist as CL
from cstudio import sync as SY
from cstudio.timecode import duration, format_timecode, parse_timecode


def test_timecodes():
    assert parse_timecode("00:01:30:00") == 90.0
    assert parse_timecode("01:30") == 90.0
    assert parse_timecode("90") == 90.0
    assert format_timecode(90.0) == "00:01:30:00"
    assert duration("00:00:00:00", "00:00:10:00") == 10.0
    with pytest.raises(ValueError):
        parse_timecode("banana")


def test_cutlist_ok_and_overlap(tmp_path):
    good = tmp_path / "good.csv"
    good.write_text("cut_id,t_start,t_end,source,rights_status\n"
                    "c1,00:00:00:00,00:00:10:00,vod.mp4,uso_proprio_confirmado\n"
                    "c2,00:01:00:00,00:01:20:00,vod.mp4,uso_proprio_confirmado\n",
                    encoding="utf-8")
    res = CL.validate_cutlist_file(str(good))
    assert res["ok"] and res["cuts"] == 2 and res["total_seconds"] == 30.0
    bad = tmp_path / "bad.csv"
    bad.write_text("cut_id,t_start,t_end,source,rights_status\n"
                   "c1,00:00:00:00,00:00:10:00,vod.mp4,uso_proprio_confirmado\n"
                   "c1,00:00:05:00,00:00:08:00,vod.mp4,uso_proprio_confirmado\n",
                   encoding="utf-8")
    res2 = CL.validate_cutlist_file(str(bad))
    assert not res2["ok"] and any("duplicate" in e or "overlap" in e for e in res2["errors"])
    short = tmp_path / "short.csv"
    short.write_text("cut_id,t_start,t_end,source,rights_status\n"
                     "c1,00:00:00:00,00:00:01:00,vod.mp4,uso_proprio_confirmado\n",
                     encoding="utf-8")
    assert not CL.validate_cutlist_file(str(short))["ok"]


def test_timeline_build():
    cuts = [{"cut_id": "c1", "t_start": "00:00:00:00", "t_end": "00:00:10:00", "source": "a.mp4"},
            {"cut_id": "c2", "t_start": "00:01:00:00", "t_end": "00:01:20:00", "source": "b.mp4"}]
    tl = CL.build_timeline(cuts)
    assert tl["total_seconds"] == 30.0 and tl["events"][1]["timeline_in"] == 10.0


def test_sync_estimate_and_validate():
    rep = SY.estimate_offset([10.0, 20.0, 30.0], [8.0, 18.0, 28.0])
    assert rep["offset_seconds"] == 2.0 and rep["pairs"] == 3
    ok, _ = SY.validate_sync_report(rep)
    assert ok
    ok2, _ = SY.validate_sync_report({"offset_seconds": 0, "method": "none", "confidence": 0})
    assert not ok2
    assert SY.apply_offset(10.0, 2.5) == 12.5
