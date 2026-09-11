"""Video-level planning on top of a shared production source pool.

A production owns the downloaded/registered VODs and mirrors.  A video proposal is
one editorial idea that references those shared assets.  Accepting a proposal
creates a lightweight video work item; media is never copied into the video item.
"""
from __future__ import annotations

import csv
import json
import os
import re
import secrets
from typing import Any

from . import core as C

VIDEO_PROPOSAL_SCHEMA_VERSION = 2
DEFAULT_DURATION = {"min": 8, "max": 15}


def _proposal_dir(root: str, slug: str) -> str:
    vdir, _ = C.load_project(root, slug)
    path = os.path.join(vdir, ".studio", "video-proposals")
    os.makedirs(os.path.join(path, "revisions"), exist_ok=True)
    return path


def _proposal_path(root: str, slug: str, proposal_id: str) -> str:
    return os.path.join(_proposal_dir(root, slug), f"{proposal_id}.json")


def _video_dir(root: str, slug: str) -> str:
    vdir, _ = C.load_project(root, slug)
    path = os.path.join(vdir, ".studio", "videos")
    os.makedirs(path, exist_ok=True)
    return path


def _safe_id(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "").strip()).strip("-.")
    return value[:80]


def _load_asset_rows(vdir: str) -> list[dict]:
    path = os.path.join(vdir, ".studio", "internal", "ingest", "assets.csv")
    if not os.path.isfile(path):
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _vod_id_from_asset(row: dict) -> str:
    aid = str(row.get("asset_id") or "")
    if aid.startswith("twitch-vod-"):
        return aid[len("twitch-vod-"):]
    path = str(row.get("path") or "")
    match = re.search(r"/discovery/([^/]+)\.json$", path.replace("\\", "/"))
    return match.group(1) if match else ""


def _read_vod_metadata(vdir: str, row: dict) -> dict:
    rel = str(row.get("path") or "")
    full = rel if os.path.isabs(rel) else os.path.join(vdir, rel)
    data = C.read_json(full, {}) if os.path.isfile(full) else {}
    vod_id = _vod_id_from_asset(row) or str(data.get("vod_id") or "") if isinstance(data, dict) else _vod_id_from_asset(row)

    # Current normalized imports may store the VOD directly. Raw Twitch scraper
    # captures contain many nested objects with their own ids/titles (games,
    # chapters, comments, etc.). Never accept an arbitrary nested title: select
    # only records whose id is the VOD we are rendering. Otherwise every card can
    # accidentally inherit the same game/chapter title.
    if isinstance(data, dict) and str(data.get("id") or "") == str(vod_id):
        return data
    candidates: list[dict] = []
    if isinstance(data, dict):
        stack: list[Any] = [data]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                if str(item.get("id") or "") == str(vod_id):
                    candidates.append(item)
                stack.extend(item.values())
            elif isinstance(item, list):
                stack.extend(item[:500])
    return max(candidates, key=lambda item: len(item.keys()), default={})


def _verified_mirrors(vdir: str) -> dict[str, list[dict]]:
    base = os.path.join(vdir, ".studio", "internal", "ingest", "youtube", "assignments")
    out: dict[str, list[dict]] = {}
    if not os.path.isdir(base):
        return out
    for name in os.listdir(base):
        if not name.endswith(".json"):
            continue
        rec = C.read_json(os.path.join(base, name), {})
        if not isinstance(rec, dict) or str(rec.get("state") or "") != "verified":
            continue
        yt = rec.get("youtube") if isinstance(rec.get("youtube"), dict) else {}
        info = {
            "youtube_video_id": str(rec.get("youtube_video_id") or os.path.splitext(name)[0]),
            "title": str(yt.get("title") or rec.get("title") or ""),
            "url": str(yt.get("url") or rec.get("url") or ""),
        }
        for vod_id in rec.get("assigned_vod_ids") or []:
            out.setdefault(str(vod_id), []).append(info)
    return out


def source_catalog(root: str, slug: str) -> list[dict]:
    """Return compact VOD choices backed by shared local media + transcripts.

    Twitch originals are first-class sources, not fallbacks: they preserve Just
    Chatting and other material omitted from edited YouTube uploads. VERIFIED
    YouTube masters remain attached as higher-quality alternate media. A VOD is
    proposal-ready once the canonical Twitch VOD has a completed discovery
    transcript. That transcript may have been produced from temporary audio;
    keeping the full MP4 is a separate editorial/storage decision.
    """
    from . import source_media as SM

    vdir, _ = C.load_project(root, slug)
    rows = _load_asset_rows(vdir)
    mirrors = _verified_mirrors(vdir)
    downloaded_by_video: dict[str, dict] = {}
    downloaded_twitch: dict[str, dict] = {}
    for row in rows:
        aid = str(row.get("asset_id") or "")
        if str(row.get("kind") or "") != "video-source":
            continue
        rel = str(row.get("path") or "")
        full = rel if os.path.isabs(rel) else os.path.join(vdir, rel)
        if not rel or not os.path.isfile(full):
            continue
        base = {
            "asset_id": aid,
            "path": rel.replace("\\", "/"),
            "bytes": os.path.getsize(full),
            "sha256": str(row.get("sha256") or ""),
        }
        if aid.startswith("youtube-"):
            downloaded_by_video[aid[len("youtube-"):]] = {**base, "platform": "youtube"}
        elif aid.startswith("twitch-video-"):
            downloaded_twitch[aid[len("twitch-video-"):]] = {**base, "platform": "twitch"}

    chat_ids = {str(r.get("asset_id") or "")[len("twitch-chat-"):]
                for r in rows if str(r.get("asset_id") or "").startswith("twitch-chat-")}
    result: list[dict] = []
    for row in rows:
        if str(row.get("kind") or "") != "vod-metadata":
            continue
        vod_id = _vod_id_from_asset(row)
        meta = _read_vod_metadata(vdir, row)
        timestamps = meta.get("timestamps") if isinstance(meta.get("timestamps"), dict) else {}
        duration_value = meta.get("duration")
        if isinstance(duration_value, dict):
            seconds = duration_value.get("seconds")
        else:
            seconds = duration_value
        if seconds in (None, ""):
            seconds = meta.get("lengthSeconds") or meta.get("durationSeconds")
        try:
            seconds = int(seconds or 0)
        except (TypeError, ValueError):
            seconds = 0

        mirror_rows = []
        media_sources = []
        twitch_media = downloaded_twitch.get(vod_id)
        twitch_transcript = SM.transcript_status(root, slug, f"twitch-video-{vod_id}")
        if twitch_media:
            tw = dict(twitch_media)
            tw["title"] = str(meta.get("title") or f"Twitch VOD {vod_id}")
            tw["vod_id"] = vod_id
            tw["transcript"] = twitch_transcript
            media_sources.append(tw)
        elif str(twitch_transcript.get("status") or "") == "completed":
            # Virtual evidence row: the temporary audio has already been
            # cleaned, but the durable transcript keeps the same canonical
            # asset id a later full-source download will register.
            media_sources.append({
                "asset_id": f"twitch-video-{vod_id}",
                "platform": "twitch",
                "title": str(meta.get("title") or f"Twitch VOD {vod_id}"),
                "vod_id": vod_id,
                "path": "",
                "bytes": 0,
                "downloaded": False,
                "transcript_only": True,
                "transcript": twitch_transcript,
            })

        for mirror in mirrors.get(vod_id, []):
            mirror = dict(mirror)
            video_id = str(mirror.get("youtube_video_id") or "")
            media = downloaded_by_video.get(video_id)
            mirror["downloaded"] = bool(media)
            if media:
                mirror["media_asset_id"] = media["asset_id"]
                mirror["media_path"] = media["path"]
                ym = dict(media, youtube_video_id=video_id, title=str(mirror.get("title") or ""))
                ym["transcript"] = SM.transcript_status(root, slug, ym["asset_id"])
                media_sources.append(ym)
            mirror_rows.append(mirror)

        transcript_ready = any(str((m.get("transcript") or {}).get("status") or "") == "completed" for m in media_sources)
        full_vod_transcript_ready = str(twitch_transcript.get("status") or "") == "completed"
        result.append({
            "asset_id": str(row.get("asset_id") or ""),
            "vod_id": vod_id or str(meta.get("id") or ""),
            "title": str(meta.get("title") or f"Twitch VOD {vod_id}"),
            "url": str(meta.get("url") or (f"https://www.twitch.tv/videos/{vod_id}" if vod_id else "")),
            "created_at": str(timestamps.get("created_at") or meta.get("createdAt") or meta.get("publishedAt") or meta.get("recordedAt") or ""),
            "duration_seconds": seconds,
            "rights_status": str(row.get("rights_status") or ""),
            "chat_available": bool(vod_id and vod_id in chat_ids),
            "verified_mirrors": mirror_rows,
            "twitch_media": next((m for m in media_sources if m.get("platform") == "twitch"), None),
            "media_ready": bool(twitch_media or any(m.get("platform") == "youtube" and m.get("path") for m in media_sources)),
            "transcript_ready": transcript_ready,
            "full_vod_transcript_ready": full_vod_transcript_ready,
            # The Twitch original is the canonical coverage source for proposal
            # planning. A transcribed YouTube master enriches quality/timing but
            # must not silently substitute for Just Chatting or other omitted
            # live sections.
            "proposal_ready": full_vod_transcript_ready,
            "media_sources": media_sources,
        })
    result.sort(key=lambda x: (str(x.get("created_at") or ""), str(x.get("vod_id") or "")))
    return result


def source_snapshot(root: str, slug: str, asset_ids: list[str], *, require_media: bool = True, require_transcript: bool = False) -> list[dict]:
    wanted = {str(x) for x in asset_ids if str(x)}
    catalog = source_catalog(root, slug)
    known = {str(x.get("asset_id")): x for x in catalog}
    missing = sorted(wanted - set(known))
    if missing:
        raise C.StudioError(f"unknown/non-VOD source assets: {', '.join(missing)}")
    selected = [known[aid] for aid in asset_ids if aid in known]
    if require_media:
        unready = [str(x.get("vod_id") or x.get("asset_id")) for x in selected if not x.get("media_ready")]
        if unready:
            raise C.StudioError(
                "download the selected VOD/master source before creating a video proposal: " + ", ".join(unready)
            )
    if require_transcript:
        missing_full_vod = [str(x.get("vod_id") or x.get("asset_id")) for x in selected if not x.get("full_vod_transcript_ready")]
        if missing_full_vod:
            raise C.StudioError(
                "transcribe the selected Twitch VOD (temporary audio or local source) before spending model usage on a video proposal: "
                + ", ".join(missing_full_vod)
            )
    return selected


def _normalize_questions(value: Any, previous: list[dict] | None = None) -> list[dict]:
    previous = previous or []
    old_answers = {str(q.get("text") or "").strip(): q for q in previous if isinstance(q, dict)}
    out = []
    if not isinstance(value, list):
        raise C.StudioError("video proposal questions must be a list")
    for index, item in enumerate(value):
        if isinstance(item, str):
            text = item.strip()
            qid = "q" + str(index + 1)
            answer = ""
            answered_at = ""
        elif isinstance(item, dict):
            text = str(item.get("text") or item.get("question") or "").strip()
            qid = _safe_id(str(item.get("id") or f"q{index + 1}")) or f"q{index + 1}"
            answer = str(item.get("answer") or "").strip()
            answered_at = str(item.get("answered_at") or "")
        else:
            raise C.StudioError("video proposal questions must contain strings or objects")
        if not text:
            continue
        prior = old_answers.get(text)
        if prior and not answer:
            answer = str(prior.get("answer") or "")
            answered_at = str(prior.get("answered_at") or "")
            qid = str(prior.get("id") or qid)
        out.append({"id": qid, "text": text, "answer": answer, "answered_at": answered_at})
    return out


def _normalize_candidate_moments(value: Any) -> list[dict]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise C.StudioError("candidate_moments must be a list")
    out: list[dict] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        asset_id = str(item.get("source_asset_id") or "").strip()
        try:
            start = float(item.get("start_seconds") or 0)
            end = float(item.get("end_seconds") or start)
        except (TypeError, ValueError):
            continue
        if not asset_id or end <= start:
            continue
        out.append({
            "source_asset_id": asset_id,
            "start_seconds": round(max(0.0, start), 3),
            "end_seconds": round(max(0.0, end), 3),
            "label": str(item.get("label") or "").strip()[:200],
            "rationale": str(item.get("rationale") or "").strip()[:2000],
            "transcript_evidence": str(item.get("transcript_evidence") or item.get("evidence") or "").strip()[:2000],
        })
    return out[:80]


def _validate_candidate_sources(norm: dict, snapshot: list[dict]) -> None:
    # Candidate timestamps are only trustworthy when the referenced media has a
    # completed detailed transcript. Registered/untranscribed masters are not
    # enough evidence for an agent to invent coordinates.
    allowed: dict[str, float] = {}
    for source in snapshot:
        for media in source.get("media_sources") or []:
            asset_id = str(media.get("asset_id") or "")
            transcript = media.get("transcript") if isinstance(media.get("transcript"), dict) else {}
            if not asset_id or str((transcript or {}).get("status") or "") != "completed":
                continue
            try:
                duration = float((transcript or {}).get("duration_seconds") or 0)
            except (TypeError, ValueError):
                duration = 0.0
            allowed[asset_id] = duration
    invalid = sorted({
        str(m.get("source_asset_id") or "")
        for m in norm.get("candidate_moments") or []
        if str(m.get("source_asset_id") or "") not in allowed
    })
    if invalid:
        raise C.StudioError("video proposal invented/used untranscribed media outside the evidence pool: " + ", ".join(invalid))
    for moment in norm.get("candidate_moments") or []:
        asset_id = str(moment.get("source_asset_id") or "")
        start = float(moment.get("start_seconds") or 0)
        end = float(moment.get("end_seconds") or 0)
        duration = float(allowed.get(asset_id) or 0)
        if duration > 0 and (start >= duration + 1 or end > duration + 5):
            raise C.StudioError(
                f"video proposal timestamp is outside transcript duration for {asset_id}: {start:.1f}-{end:.1f}s > {duration:.1f}s"
            )
        if not str(moment.get("transcript_evidence") or "").strip():
            raise C.StudioError(f"candidate moment for {asset_id} is missing transcript evidence")


def normalize_agent_payload(raw: dict, previous_questions: list[dict] | None = None) -> dict:
    if not isinstance(raw, dict):
        raise C.StudioError("video proposal response must be a JSON object")
    summary = str(raw.get("summary") or "").strip()
    document = str(raw.get("document") or raw.get("brief") or "").strip()
    video = raw.get("video") if isinstance(raw.get("video"), dict) else {}
    title = str(video.get("working_title") or raw.get("working_title") or "").strip()
    premise = str(video.get("premise") or "").strip()
    angle = str(video.get("editorial_angle") or "").strip()
    if len(document) < 80:
        raise C.StudioError("video proposal document is too short (<80 chars)")
    if not summary:
        summary = title or "Video proposal"
    if not title:
        title = summary[:120]
    duration = video.get("target_duration_minutes") if isinstance(video.get("target_duration_minutes"), dict) else {}
    try:
        dmin = int(duration.get("min") or DEFAULT_DURATION["min"])
        dmax = int(duration.get("max") or DEFAULT_DURATION["max"])
    except (TypeError, ValueError):
        dmin, dmax = DEFAULT_DURATION["min"], DEFAULT_DURATION["max"]
    dmin = max(1, min(dmin, 120)); dmax = max(dmin, min(dmax, 180))
    warnings = raw.get("warnings") or []
    if not isinstance(warnings, list):
        raise C.StudioError("video proposal warnings must be a list")
    criteria = video.get("selection_criteria") or []
    constraints = video.get("constraints") or []
    if not isinstance(criteria, list) or not isinstance(constraints, list):
        raise C.StudioError("selection_criteria and constraints must be lists")
    return {
        "summary": summary,
        "document": document,
        "video": {
            "working_title": title,
            "premise": premise,
            "editorial_angle": angle,
            "target_duration_minutes": {"min": dmin, "max": dmax},
            "selection_criteria": [str(x) for x in criteria if str(x).strip()],
            "constraints": [str(x) for x in constraints if str(x).strip()],
        },
        "candidate_moments": _normalize_candidate_moments(raw.get("candidate_moments") or video.get("candidate_moments") or []),
        "questions": _normalize_questions(raw.get("questions") or [], previous_questions),
        "warnings": [str(x) for x in warnings if str(x).strip()],
    }


def create_video_proposal(root: str, slug: str, raw: dict, *, source_asset_ids: list[str],
                          request: str, runner: str, model: str = "", reasoning_effort: str = "",
                          runner_session: dict | None = None, runner_usage: dict | None = None) -> dict:
    if not source_asset_ids:
        raise C.StudioError("select at least one VOD for this video proposal")
    snapshot = source_snapshot(root, slug, source_asset_ids, require_media=False, require_transcript=True)
    norm = normalize_agent_payload(raw)
    _validate_candidate_sources(norm, snapshot)
    pid = secrets.token_hex(6)
    now = C.utc_now()
    rec = {
        "schema_version": VIDEO_PROPOSAL_SCHEMA_VERSION,
        "id": pid,
        "kind": "video",
        "status": "pending",
        "revision": 1,
        "created_at": now,
        "updated_at": now,
        "runner": str(runner or ""),
        "model": str(model or ""),
        "reasoning_effort": str(reasoning_effort or ""),
        "runner_session": runner_session or {},
        "runner_usage": runner_usage or {},
        "request": str(request or "").strip(),
        "source_asset_ids": list(dict.fromkeys(source_asset_ids)),
        "source_snapshot": snapshot,
        "human_answers": [],
        **norm,
    }
    rec["planning_phase"] = "part1" if rec.get("questions") else "part2_final"
    rec["part1_completed_at"] = now
    if rec["planning_phase"] == "part2_final":
        rec["part2_consolidated_at"] = now
    C.write_json(_proposal_path(root, slug, pid), rec)
    return rec


def _planning_phase(rec: dict) -> str:
    """Return an explicit phase while keeping older pending proposals usable."""
    phase = str(rec.get("planning_phase") or "").strip()
    if phase:
        return phase
    questions = [q for q in (rec.get("questions") or []) if isinstance(q, dict)]
    if any(not str(q.get("answer") or "").strip() for q in questions):
        return "part2_questions" if rec.get("human_answers") else "part1"
    if questions and rec.get("human_answers"):
        # Legacy proposals did not record consolidation explicitly. A revision
        # after human answers is the closest durable signal that the agent saw
        # them and produced the final proposal.
        return "part2_final" if int(rec.get("revision") or 1) > 1 else "part2_answers_ready"
    return "part2_final"


def get_video_proposal(root: str, slug: str, proposal_id: str) -> dict:
    rec = C.read_json(_proposal_path(root, slug, proposal_id), None)
    if not isinstance(rec, dict):
        raise C.StudioError(f"video proposal not found: {proposal_id}")
    rec.setdefault("planning_phase", _planning_phase(rec))
    return rec


def list_video_proposals(root: str, slug: str) -> list[dict]:
    base = _proposal_dir(root, slug)
    rows = []
    for name in os.listdir(base):
        if not name.endswith(".json"):
            continue
        rec = C.read_json(os.path.join(base, name), None)
        if isinstance(rec, dict) and rec.get("kind") == "video":
            rec.setdefault("planning_phase", _planning_phase(rec))
            rows.append(rec)
    rows.sort(key=lambda x: str(x.get("updated_at") or x.get("created_at") or ""), reverse=True)
    return rows


def save_answers(root: str, slug: str, proposal_id: str, answers: dict[str, str]) -> dict:
    rec = get_video_proposal(root, slug, proposal_id)
    if rec.get("status") != "pending":
        raise C.StudioError("only pending video proposals can receive answers")
    now = C.utc_now()
    questions = []
    for q in rec.get("questions") or []:
        q = dict(q)
        qid = str(q.get("id") or "")
        if qid in answers:
            new = str(answers.get(qid) or "").strip()
            q["answer"] = new
            q["answered_at"] = now if new else ""
        questions.append(q)
    rec["questions"] = questions
    history = [dict(x) for x in (rec.get("human_answers") or []) if isinstance(x, dict)]
    by_text = {str(x.get("text") or ""): x for x in history}
    for q in questions:
        text = str(q.get("text") or "").strip()
        answer = str(q.get("answer") or "").strip()
        if text and answer:
            by_text[text] = {"question_id": str(q.get("id") or ""), "text": text, "answer": answer, "answered_at": str(q.get("answered_at") or now)}
    rec["human_answers"] = list(by_text.values())
    rec["updated_at"] = now
    rec["answers_updated_at"] = now
    if questions:
        rec["planning_phase"] = "part2_questions" if unanswered_questions(rec) else "part2_answers_ready"
    C.write_json(_proposal_path(root, slug, proposal_id), rec)
    return rec


def unanswered_questions(rec: dict) -> list[dict]:
    return [q for q in rec.get("questions") or [] if not str(q.get("answer") or "").strip()]


def _snapshot_revision(root: str, slug: str, rec: dict) -> None:
    base = os.path.join(_proposal_dir(root, slug), "revisions", str(rec.get("id") or ""))
    os.makedirs(base, exist_ok=True)
    revision = int(rec.get("revision") or 1)
    C.write_json(os.path.join(base, f"{revision:04d}.json"), rec)


def refine_video_proposal(root: str, slug: str, proposal_id: str, raw: dict, *,
                          runner: str, model: str = "", reasoning_effort: str = "",
                          runner_session: dict | None = None, runner_usage: dict | None = None) -> dict:
    rec = get_video_proposal(root, slug, proposal_id)
    if rec.get("status") != "pending":
        raise C.StudioError("only pending video proposals can be refined")
    if unanswered_questions(rec):
        raise C.StudioError("answer the current Part 2 questions before consolidating the proposal")
    _snapshot_revision(root, slug, rec)
    norm = normalize_agent_payload(raw, previous_questions=list(rec.get("questions") or []))
    snapshot = source_snapshot(root, slug, list(rec.get("source_asset_ids") or []), require_media=False, require_transcript=True)
    _validate_candidate_sources(norm, snapshot)
    rec["source_snapshot"] = snapshot
    rec.update(norm)
    rec["revision"] = int(rec.get("revision") or 1) + 1
    rec["updated_at"] = C.utc_now()
    rec["runner"] = str(runner or rec.get("runner") or "")
    rec["model"] = str(model or "")
    rec["reasoning_effort"] = str(reasoning_effort or "")
    if runner_session:
        rec["runner_session"] = runner_session
    if runner_usage:
        rec["runner_usage"] = runner_usage
    if unanswered_questions(rec):
        rec["planning_phase"] = "part2_questions"
        rec.pop("part2_consolidated_at", None)
    else:
        rec["planning_phase"] = "part2_final"
        rec["part2_consolidated_at"] = C.utc_now()
    C.write_json(_proposal_path(root, slug, proposal_id), rec)
    return rec


def _brief_text(rec: dict) -> str:
    lines = [str(rec.get("document") or "").strip(), "", "## Respostas humanas"]
    answered = [dict(q) for q in rec.get("human_answers") or [] if isinstance(q, dict) and str(q.get("answer") or "").strip()]
    # Backwards compatibility for proposals created before human_answers existed.
    if not answered:
        answered = [q for q in rec.get("questions") or [] if str(q.get("answer") or "").strip()]
    if not answered:
        lines.append("Nenhuma pergunta adicional foi necessária.")
    else:
        for q in answered:
            lines += [f"### {q.get('text')}", str(q.get("answer") or "").strip(), ""]
    return "\n".join(lines).strip() + "\n"


def accept_video_proposal(root: str, slug: str, proposal_id: str) -> dict:
    rec = get_video_proposal(root, slug, proposal_id)
    if rec.get("status") != "pending":
        raise C.StudioError("video proposal is not pending")
    open_q = unanswered_questions(rec)
    if open_q:
        raise C.StudioError(f"answer {len(open_q)} pending proposal question(s) before creating the video")
    if _planning_phase(rec) not in {"part2_final", "final"}:
        raise C.StudioError("consolidate Part 2 with the planning agent before creating the video")
    title = str((rec.get("video") or {}).get("working_title") or rec.get("summary") or "video")
    base = C.slugify(title) or "video"
    video_id = base
    target = os.path.join(_video_dir(root, slug), video_id)
    if os.path.exists(target):
        video_id = f"{base}-{secrets.token_hex(2)}"
        target = os.path.join(_video_dir(root, slug), video_id)
    os.makedirs(target, exist_ok=False)
    brief_path = os.path.join(target, "brief.md")
    with open(brief_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(_brief_text(rec))
    video = {
        "schema_version": 1,
        "id": video_id,
        "parent_production": slug,
        "proposal_id": proposal_id,
        "title": title,
        "status": "planned",
        "stage": "analysis",
        "created_at": C.utc_now(),
        "source_asset_ids": list(rec.get("source_asset_ids") or []),
        "target_duration_minutes": dict((rec.get("video") or {}).get("target_duration_minutes") or DEFAULT_DURATION),
        "candidate_moments": list(rec.get("candidate_moments") or []),
        "brief_path": f".studio/videos/{video_id}/brief.md",
        "media_policy": {"shared_source_pool": True, "copy_media": False},
    }
    C.write_json(os.path.join(target, "video.json"), video)
    rec["status"] = "accepted"
    rec["accepted_at"] = C.utc_now()
    rec["video_id"] = video_id
    rec["updated_at"] = rec["accepted_at"]
    C.write_json(_proposal_path(root, slug, proposal_id), rec)
    return video


def discard_video_proposal(root: str, slug: str, proposal_id: str) -> dict:
    rec = get_video_proposal(root, slug, proposal_id)
    if rec.get("status") != "pending":
        raise C.StudioError("video proposal is not pending")
    rec["status"] = "discarded"
    rec["discarded_at"] = C.utc_now()
    rec["updated_at"] = rec["discarded_at"]
    C.write_json(_proposal_path(root, slug, proposal_id), rec)
    return rec


def list_videos(root: str, slug: str) -> list[dict]:
    base = _video_dir(root, slug)
    rows = []
    for name in os.listdir(base):
        path = os.path.join(base, name, "video.json")
        rec = C.read_json(path, None)
        if isinstance(rec, dict):
            rows.append(rec)
    rows.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
    return rows


def context_pack(root: str, slug: str, asset_ids: list[str], query: str = "") -> dict:
    from . import source_media as SM
    _vdir, project = C.load_project(root, slug)
    snapshot = source_snapshot(root, slug, asset_ids, require_media=False, require_transcript=True)
    media_asset_ids = [
        str(media.get("asset_id") or "")
        for source in snapshot
        for media in (source.get("media_sources") or [])
        if str((media.get("transcript") or {}).get("status") or "") == "completed"
    ]
    return {
        "production": {"slug": slug, "title": project.get("title")},
        "selected_vods": snapshot,
        "transcript_evidence": SM.transcript_context(root, slug, media_asset_ids, query=query),
        "target_duration_minutes": dict(DEFAULT_DURATION),
        "policy": {
            "one_proposal_one_video": True,
            "sources_are_shared": True,
            "copy_media": False,
            "transcript_required_before_paid_agent": True,
            "full_media_required_before_paid_agent": False,
            "discovery_timestamp_mode": "segment",
            "word_timestamps_deferred_to_selected_candidates": True,
            "proposal_scope": "editorial direction + evidence-backed candidate moments for one video, not final cutlist",
        },
    }


def video_response_schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "summary": {"type": "string"},
            "document": {"type": "string"},
            "video": {
                "type": "object", "additionalProperties": False,
                "properties": {
                    "working_title": {"type": "string"},
                    "premise": {"type": "string"},
                    "editorial_angle": {"type": "string"},
                    "target_duration_minutes": {
                        "type": "object", "additionalProperties": False,
                        "properties": {"min": {"type": "integer"}, "max": {"type": "integer"}},
                        "required": ["min", "max"],
                    },
                    "selection_criteria": {"type": "array", "items": {"type": "string"}},
                    "constraints": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["working_title", "premise", "editorial_angle", "target_duration_minutes", "selection_criteria", "constraints"],
            },
            "candidate_moments": {
                "type": "array",
                "items": {
                    "type": "object", "additionalProperties": False,
                    "properties": {
                        "source_asset_id": {"type": "string"},
                        "start_seconds": {"type": "number"},
                        "end_seconds": {"type": "number"},
                        "label": {"type": "string"},
                        "rationale": {"type": "string"},
                        "transcript_evidence": {"type": "string"},
                    },
                    "required": ["source_asset_id", "start_seconds", "end_seconds", "label", "rationale", "transcript_evidence"],
                },
            },
            "questions": {"type": "array", "items": {"type": "string"}},
            "warnings": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["summary", "document", "video", "candidate_moments", "questions", "warnings"],
    }

