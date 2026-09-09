"""Contrato de proposal + runner manual + lifecycle (determinístico)."""
import json
import os
import shutil

import pytest

from cstudio import core as C
from cstudio import proposals as P
from cstudio import runners as R


@pytest.fixture()
def root(tmp_path):
    r = str(tmp_path / "harness")
    shutil.copytree("K:/Applications/Youtube-Channel/studio", os.path.join(r, "studio"))
    shutil.copytree("K:/Applications/Youtube-Channel/templates", os.path.join(r, "templates"))
    open(os.path.join(r, "pyproject.toml"), "w").write("[project]\nname='x'\n")
    C.create_production(r, "Corte Teste", slug="corte-teste")
    return r


def _fill_config(root):
    vdir, _ = C.load_project(root, "corte-teste")
    open(os.path.join(vdir, "01-config/config.md"), "w", encoding="utf-8").write(
        "# Config\n" + "Origem Twitch VOD com direitos pendentes. " * 20)


def test_contract_normalise_list_and_dict():
    raw_list = {"summary": "s", "document": "x" * 50,
                "files": [{"path": "a.md", "content": "hi"}], "questions": [], "warnings": []}
    assert P.normalise_proposal(raw_list)["files"] == {"a.md": "hi"}
    raw_dict = {"summary": "s", "document": "x" * 50,
                "files": {"a.md": "hi"}, "questions": ["q?"], "warnings": ["w"]}
    n = P.normalise_proposal(raw_dict)
    assert n["questions"] == ["q?"]
    with pytest.raises(Exception):
        P.normalise_proposal({"summary": "s"})


def test_proposal_rejects_unapproved_path(root):
    bad = {"summary": "s", "document": "y" * 50, "files": {"../../evil.md": "x"},
           "questions": [], "warnings": []}
    with pytest.raises(Exception):
        P.validate_proposal(root, "corte-teste", bad, "config")


def test_manual_runner_lifecycle(root):
    _fill_config(root)
    payload = {"summary": "config inicial", "document": "Configuração do corte. " * 20,
               "files": {}, "questions": ["ok?"], "warnings": []}
    rec = R.import_proposal(root, "corte-teste", payload, user_request="setup")
    assert rec["status"] == "pending" and rec["runner"] == "manual"
    rec2 = P.update_proposal_document(root, "corte-teste", rec["id"], "Configuração revisada. " * 20)
    assert "revisada" in rec2["document"]
    applied = P.apply_proposal(root, "corte-teste", rec["id"], by="tester")
    assert applied["status"] == "applied"
    vdir, proj = C.load_project(root, "corte-teste")
    assert any(h.get("event") == "assistant_proposal_applied" for h in proj["history"])
    # second apply blocked
    with pytest.raises(Exception):
        P.apply_proposal(root, "corte-teste", rec["id"])
