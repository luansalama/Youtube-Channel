"""Parsing da sessão Z.AI + reconstrução cronológica (determinístico)."""
import json
from cstudio import session as S


def test_extract_empty_on_403():
    data = {"detail": "Not authenticated"}
    assert S.extract_messages(data) == []
    assert S.session_meta(data)["has_history"] is False
    md = S.to_markdown(data, session_id="b73267bf-test")
    assert "b73267bf-test" in md and "history.messages" in md


def test_tree_order_parent_children():
    msgs = [
        {"id": "m3", "role": "assistant", "content": "terceira", "childrenIds": []},
        {"id": "m1", "role": "user", "content": "primeira", "childrenIds": ["m2"]},
        {"id": "m2", "role": "assistant", "content": "segunda", "childrenIds": ["m3"]},
    ]
    ordered = S.order_messages(msgs)
    assert [m["id"] for m in ordered] == ["m1", "m2", "m3"]
    md = S.to_markdown({"history": {"messages": msgs}}, session_id="x")
    assert md.index("primeira") < md.index("segunda") < md.index("terceira")


def test_content_list_shape():
    msg = {"id": "a", "role": "user",
           "content": [{"type": "text", "text": "olá"}, {"type": "text", "text": "mundo"}]}
    assert S.message_text(msg) == "olá\nmundo"
    assert S.message_role({"role": "human"}) == "User"
