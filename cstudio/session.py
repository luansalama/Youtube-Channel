"""Z.AI shared-session parsing + chronological Markdown reconstruction.

Handles the real endpoint shape:
  GET /api/v1/chats/share/<uuid> -> {chat/history/title/model/...}
where history.messages is a TREE linked by parent_id/childrenIds,
not a flat chronological list. Also tolerates the 403 body
{"detail": ...} so tests stay deterministic.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone


def load_session_file(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("session JSON must be an object")
    return data


def extract_messages(data: dict) -> list[dict]:
    """Return raw message nodes from known shapes, else []."""
    if not isinstance(data, dict):
        return []
    for key in ("history", "chat", "data", "session"):
        node = data.get(key)
        if isinstance(node, dict) and isinstance(node.get("messages"), list):
            return node["messages"]
    if isinstance(data.get("messages"), list):
        return data["messages"]
    return []


def order_messages(messages: list[dict]) -> list[dict]:
    """Order by parent_id/childrenIds tree walk; fallback to created_at/order."""
    if not messages:
        return []
    by_id = {m.get("id"): m for m in messages if isinstance(m, dict) and m.get("id")}
    if not by_id:
        return list(messages)
    children: dict[str, list[str]] = {}
    for m in messages:
        if not isinstance(m, dict):
            continue
        for c in m.get("childrenIds") or m.get("children_ids") or m.get("children") or []:
            if isinstance(c, str):
                children.setdefault(m.get("id"), []).append(c)
    referenced = {c for v in children.values() for c in v}
    roots = [m for m in messages if isinstance(m, dict) and m.get("id") not in referenced]
    if not roots:  # cycle-safe fallback
        return sorted(messages, key=lambda m: (str(m.get("created_at", "")), str(m.get("id", ""))))
    # deterministic child order: by created_at then id
    for k, v in children.items():
        v.sort(key=lambda cid: (str((by_id.get(cid) or {}).get("created_at", "")), cid))

    ordered: list[dict] = []
    seen: set[str] = set()

    def visit(mid: str) -> None:
        if mid in seen or mid not in by_id:
            return
        seen.add(mid)
        ordered.append(by_id[mid])
        for c in children.get(mid, []):
            visit(c)

    # multiple roots: chronological first
    roots.sort(key=lambda m: (str(m.get("created_at", "")), str(m.get("id", ""))))
    for r in roots:
        visit(r.get("id"))
    # orphan safety net
    for m in messages:
        if isinstance(m, dict) and m.get("id") not in seen:
            ordered.append(m)
    return ordered


def message_role(msg: dict) -> str:
    r = str(msg.get("role", "")).lower()
    if "user" in r or "human" in r:
        return "User"
    if "assist" in r or "gpt" in r or "glM".lower() in r:
        return "Assistant"
    if "system" in r:
        return "System"
    return msg.get("role", "Unknown") or "Unknown"


def message_text(msg: dict) -> str:
    c = msg.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        parts = []
        for b in c:
            if isinstance(b, str):
                parts.append(b)
            elif isinstance(b, dict):
                for k in ("text", "content", "value"):
                    if isinstance(b.get(k), str):
                        parts.append(b[k])
                        break
        return "\n".join(parts)
    if isinstance(c, dict):
        for k in ("text", "content", "value"):
            if isinstance(c.get(k), str):
                return c[k]
    return json.dumps(c, ensure_ascii=False) if c is not None else ""


def session_meta(data: dict) -> dict:
    chat = data.get("chat") if isinstance(data.get("chat"), dict) else {}
    return {
        "title": data.get("title") or chat.get("title") or "",
        "model": data.get("model") or chat.get("model") or data.get("model_name") or "",
        "session_id": data.get("id") or data.get("share_id") or chat.get("id") or "",
        "has_history": bool(extract_messages(data)),
    }


def to_markdown(data: dict, session_id: str = "") -> str:
    msgs = order_messages(extract_messages(data))
    meta = session_meta(data)
    sid = session_id or meta["session_id"]
    out = ["# Z.AI Shared Session", "", f"Session ID: {sid}"]
    if meta["title"]:
        out.append(f"Title: {meta['title']}")
    if meta["model"]:
        out.append(f"Model: {meta['model']}")
    out += ["", f"Messages: {len(msgs)}",
            f"Exported: {datetime.now(timezone.utc).isoformat()}", "", "---", ""]
    if not msgs:
        out += ["## Retrieval note", "",
                "No `history.messages` present in this payload "
                "(e.g. public endpoint returned 403 `{\"detail\":\"Not authenticated\"}`).",
                "See CONTEXT/zai-session.md for the validated retrieval evidence.", ""]
        return "\n".join(out)
    for m in msgs:
        out += [f"## {message_role(m)}", ""]
        ts = m.get("created_at") or m.get("timestamp") or m.get("time")
        if ts:
            out += [f"*{ts}*", ""]
        out += [message_text(m) or "*(empty)*", "", "---", ""]
    return "\n".join(out)
