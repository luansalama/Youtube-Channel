"""Locks/fingerprints + rights gate + publish blockade (determinístico)."""
import csv
import json
import os
import shutil

import pytest

from cstudio import core as C
from cstudio import pipeline as PL
from cstudio import rights as RT


@pytest.fixture()
def root(tmp_path):
    r = str(tmp_path / "harness")
    shutil.copytree("K:/Applications/Youtube-Channel/studio", os.path.join(r, "studio"))
    shutil.copytree("K:/Applications/Youtube-Channel/templates", os.path.join(r, "templates"))
    open(os.path.join(r, "pyproject.toml"), "w").write("[project]\nname='x'\n")
    C.create_production(r, "Corte Gates", slug="gates")
    return r


def _write(vdir, rel, content):
    p = os.path.join(vdir, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w", encoding="utf-8", newline="\n").write(content)


def _fill_through_cutlist(root):
    vdir, _ = C.load_project(root, "gates")
    _write(vdir, "01-config/config.md", "# C\n" + "configuração inicial do corte. " * 30)
    _write(vdir, "02-ingest/ingest.md", "# I\n" + "ingestão dos VODs e chats. " * 30)
    with open(os.path.join(vdir, ".studio/internal/ingest/assets.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["asset_id", "kind", "path", "sha256", "rights_status"])
        w.writeheader()
        w.writerow({"asset_id": "vod1", "kind": "vod", "path": "vod.mp4",
                    "sha256": "abc", "rights_status": "uso_proprio_confirmado"})
    _write(vdir, ".studio/internal/analysis/moments.csv",
           "moment_id,t_start,t_end,score,rationale\nm1,00:00:01:00,00:00:20:00,0.9,hype\n")
    with open(os.path.join(vdir, ".studio/internal/sync/sync-report.json"), "w") as fh:
        json.dump({"offset_seconds": 1.5, "method": "nearest-neighbour-median", "confidence": 0.9}, fh)
    _write(vdir, ".studio/internal/highlights/ranking.csv", "moment_id,rank,score\nm1,1,0.9\n")
    _write(vdir, "06-cutlist/cutlist.md", "# Cutlist\n" + "decisão editorial humana. " * 30)
    with open(os.path.join(vdir, ".studio/internal/cutlist/cutlist.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["cut_id", "t_start", "t_end", "source", "rights_status"])
        w.writeheader()
        w.writerow({"cut_id": "c1", "t_start": "00:00:00:00", "t_end": "00:00:10:00",
                    "source": "vod.mp4", "rights_status": "uso_proprio_confirmado"})


def test_cutlist_lock_and_fingerprint_drift(root):
    _fill_through_cutlist(root)
    # cutlist approval requires upstream evidence only; config..highlights have no gates, so it passes
    C.approve_gate(root, "gates", "cutlist_lock", by="showrunner", note="aprovado")
    assert any(g["gate"] == "cutlist_lock" and g["approved"] for g in C.gate_status(root, "gates"))
    # drift: modify approved evidence -> integrity fails
    vdir, _ = C.load_project(root, "gates")
    with open(os.path.join(vdir, "06-cutlist/cutlist.md"), "a", encoding="utf-8") as fh:
        fh.write("\n trailing edit")
    gates = C.gate_status(root, "gates")
    assert any(g["gate"] == "cutlist_lock" and not g["approved"] for g in gates)


def test_rights_gate_blocks_and_clears(root):
    _fill_through_cutlist(root)
    vdir, proj = C.load_project(root, "gates")
    # default blocked: cutlist row cleared but ingest row + sources still blocked?
    ok, msg = RT.rights_gate(proj, vdir)
    assert ok  # fixture rows are cleared
    RT.set_asset_rights(root, "gates", "trilha", "sem_autorizacao_confirmada")
    _, proj2 = C.load_project(root, "gates")
    ok2, _ = RT.rights_gate(proj2, vdir)
    assert not ok2
    RT.set_asset_rights(root, "gates", "trilha", "licenca_confirmada",
                        authorizer="Artista X", scope="youtube", evidence="email.pdf")
    _, proj3 = C.load_project(root, "gates")
    assert RT.rights_gate(proj3, vdir)[0]


def test_publish_blocked_without_locks(root):
    _fill_through_cutlist(root)
    dry = PL.publish_dry_run(root, "gates")
    assert not dry["would_publish"] and dry["blockers"]
    with pytest.raises(Exception):
        PL.publish_execute(root, "gates")
    with pytest.raises(Exception):
        C.package_publish(root, "gates")
