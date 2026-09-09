from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class StoryFinding:
    ok: bool
    label: str
    detail: str
    severity: str = "error"


def _finding(ok: bool, label: str, detail: str, severity: str = "error") -> StoryFinding:
    return StoryFinding(ok=ok, label=label, detail=detail, severity=severity)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _csv_width_issues(path: Path) -> tuple[int, list[str]]:
    """Return the header width and concise row-width mismatches."""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration:
            return 0, []
        expected = len(header)
        issues: list[str] = []
        for line_number, row in enumerate(reader, start=2):
            if len(row) == expected:
                continue
            row_id = (row[0] if row else "").strip() or f"line {line_number}"
            issues.append(f"{row_id}: {len(row)} value(s), expected {expected}")
        return expected, issues


def _split_ids(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.replace(",", "|").split("|") if part.strip()]


PLACEHOLDER_TOKENS = ("TODO", "TBD", "{{", "<replace", "[write here]", "[fill")


def _nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return False
        lowered = stripped.casefold()
        return not any(token.casefold() in lowered for token in PLACEHOLDER_TOKENS)
    if isinstance(value, list):
        return bool(value) and all(_nonempty(item) for item in value)
    if isinstance(value, dict):
        return bool(value)
    return True


def _nested(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _required_nested(payload: dict[str, Any], paths: Iterable[str], label: str) -> list[StoryFinding]:
    missing = [path for path in paths if not _nonempty(_nested(payload, path))]
    if missing:
        return [_finding(False, label, f"missing or empty field(s): {', '.join(missing)}")]
    return [_finding(True, label, "required narrative decisions are recorded")]


def _unique_ids(rows: list[dict[str, str]], column: str, label: str) -> list[StoryFinding]:
    if not rows:
        return [_finding(False, label, "no populated rows")]
    values = [(row.get(column) or "").strip() for row in rows]
    missing_count = sum(not value for value in values)
    duplicates = sorted({value for value in values if value and values.count(value) > 1})
    findings: list[StoryFinding] = []
    if missing_count:
        findings.append(_finding(False, label, f"{missing_count} row(s) have no {column}"))
    if duplicates:
        findings.append(_finding(False, label, f"duplicate {column} value(s): {', '.join(duplicates)}"))
    if not findings:
        findings.append(_finding(True, label, f"{len(values)} unique ID(s)"))
    return findings


def _detect_cycle(edges: dict[str, list[str]]) -> list[str]:
    visiting: set[str] = set()
    visited: set[str] = set()
    trail: list[str] = []

    def visit(node: str) -> list[str]:
        if node in visiting:
            try:
                start = trail.index(node)
            except ValueError:
                start = 0
            return trail[start:] + [node]
        if node in visited:
            return []
        visiting.add(node)
        trail.append(node)
        for parent in edges.get(node, []):
            cycle = visit(parent)
            if cycle:
                return cycle
        trail.pop()
        visiting.remove(node)
        visited.add(node)
        return []

    for node in edges:
        cycle = visit(node)
        if cycle:
            return cycle
    return []


def validate_writing_doctrine(root: Path) -> list[StoryFinding]:
    path = root / "studio" / "writing-doctrine.json"
    if not path.is_file():
        return [_finding(False, "writing doctrine", "studio/writing-doctrine.json is missing")]
    try:
        payload = _read_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        return [_finding(False, "writing doctrine", f"invalid JSON: {exc}")]
    if not isinstance(payload, dict):
        return [_finding(False, "writing doctrine", "root must be an object")]
    required = ["schema_version", "position", "strong_doctrine", "flexible_conventions", "must_not_enforce", "audit"]
    missing = [key for key in required if not _nonempty(payload.get(key))]
    if missing:
        return [_finding(False, "writing doctrine", f"empty required key(s): {', '.join(missing)}")]
    strong = payload.get("strong_doctrine")
    flexible = payload.get("flexible_conventions")
    prohibited = payload.get("must_not_enforce")
    if not all(isinstance(item, dict) and item.get("id") for item in strong):
        return [_finding(False, "writing doctrine", "every strong doctrine entry requires an id")]
    if not all(isinstance(item, dict) and item.get("id") for item in flexible):
        return [_finding(False, "writing doctrine", "every flexible convention entry requires an id")]
    if not all(isinstance(item, str) and item.strip() for item in prohibited):
        return [_finding(False, "writing doctrine", "must_not_enforce must contain non-empty strings")]
    return [_finding(True, "writing doctrine", f"{len(strong)} strong principles, {len(flexible)} advisory conventions, {len(prohibited)} prohibited hard rules")]


def audit_story_model(video_dir: Path) -> list[StoryFinding]:
    path = video_dir / ".studio" / "internal" / "story" / "story-model.json"
    if not path.is_file():
        return [_finding(False, "story model", ".studio/internal/story/story-model.json is missing")]
    try:
        payload = _read_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        return [_finding(False, "story model", f"invalid JSON: {exc}")]
    if not isinstance(payload, dict):
        return [_finding(False, "story model", "root must be an object")]

    findings = _required_nested(
        payload,
        [
            "audience_promise.novel_situation",
            "audience_promise.human_problem",
            "audience_promise.pressure_source",
            "audience_promise.expected_pleasure",
            "audience_promise.disappointment_test",
            "premise.disruption",
            "premise.protagonist_id",
            "premise.difficult_goal",
            "premise.central_opposition",
            "premise.meaningful_consequence",
            "premise.logline",
            "theme.subject",
            "theme.question",
            "theme.provisional_argument",
            "theme.competing_values",
            "story_layers.chronological_story",
            "story_layers.causal_plot",
            "story_layers.audience_presentation",
            "ending_design.final_choice",
            "ending_design.climax_mechanism",
            "ending_design.emotional_result",
            "ending_design.thematic_consequence",
            "ending_design.final_state",
            "ending_design.final_image",
            "structure_choice.framework",
            "structure_choice.rationale",
            "minecraft_story_engine.mechanic",
            "minecraft_story_engine.causal_effect",
            "minecraft_story_engine.climactic_use",
        ],
        "story model decisions",
    )

    characters = payload.get("characters")
    if not isinstance(characters, list) or not characters:
        findings.append(_finding(False, "character system", "characters must be a non-empty list"))
        return findings

    required_character_fields = [
        "character_id", "role", "want", "need", "fear", "belief", "limitation",
        "strategy", "contradiction", "boundary", "pressure_point", "relationship_function", "agency",
    ]
    character_ids: list[str] = []
    incomplete: list[str] = []
    for index, character in enumerate(characters, start=1):
        if not isinstance(character, dict):
            incomplete.append(f"row {index}")
            continue
        character_id = str(character.get("character_id") or "").strip()
        if character_id:
            character_ids.append(character_id)
        missing = [key for key in required_character_fields if not _nonempty(character.get(key))]
        if missing:
            incomplete.append(f"{character_id or f'row {index}'} ({', '.join(missing)})")
    duplicates = sorted({value for value in character_ids if character_ids.count(value) > 1})
    if incomplete:
        findings.append(_finding(False, "character system", f"incomplete character record(s): {'; '.join(incomplete[:5])}"))
    elif duplicates:
        findings.append(_finding(False, "character system", f"duplicate character_id value(s): {', '.join(duplicates)}"))
    else:
        findings.append(_finding(True, "character system", f"{len(character_ids)} complete character record(s)"))

    protagonist_id = str(_nested(payload, "premise.protagonist_id") or "").strip()
    if protagonist_id and protagonist_id not in character_ids:
        findings.append(_finding(False, "protagonist reference", f"premise.protagonist_id '{protagonist_id}' is not present in characters"))
    elif protagonist_id:
        findings.append(_finding(True, "protagonist reference", f"{protagonist_id} resolves to a character record"))

    values = _nested(payload, "theme.competing_values")
    if isinstance(values, list) and len([value for value in values if _nonempty(value)]) < 2:
        findings.append(_finding(False, "thematic conflict", "record at least two competing values"))
    else:
        findings.append(_finding(True, "thematic conflict", "competing values are recorded"))

    return findings


def audit_causal_spine(video_dir: Path, doctrine: dict[str, Any]) -> list[StoryFinding]:
    path = video_dir / ".studio" / "internal" / "story" / "causal-spine.csv"
    if not path.is_file():
        return [_finding(False, "causal spine", ".studio/internal/story/causal-spine.csv is missing")]
    rows = [row for row in _read_csv(path) if any(str(value or "").strip() for value in row.values())]
    findings = _unique_ids(rows, "event_id", "causal event IDs")
    if not rows:
        return findings

    ids = {(row.get("event_id") or "").strip() for row in rows if (row.get("event_id") or "").strip()}
    edges: dict[str, list[str]] = {}
    bad_refs: list[str] = []
    self_refs: list[str] = []
    missing_logic: list[str] = []
    invalid_counterfactual: list[str] = []
    required_cells = ["summary", "actor_id", "consequence", "state_change", "new_information", "audience_effect", "deletion_impact"]
    allowed_counterfactual = set(doctrine.get("audit", {}).get("counterfactual_results", ["pass", "weak", "not_applicable"]))
    allowed_cause_types = set(doctrine.get("audit", {}).get("cause_types", ["initial_state", "prior_event", "external_disruption", "background_condition", "parallel_cause"]))
    invalid_cause_types: list[str] = []
    initial_count = 0

    for row in rows:
        event_id = (row.get("event_id") or "").strip()
        causes = _split_ids(row.get("cause_ids"))
        edges[event_id] = causes
        cause_type = (row.get("cause_type") or "").strip()
        if cause_type not in allowed_cause_types:
            invalid_cause_types.append(f"{event_id}:{cause_type or 'empty'}")
        if cause_type == "initial_state":
            initial_count += 1
        if cause_type != "initial_state" and not causes and cause_type not in {"external_disruption", "background_condition"}:
            missing_logic.append(f"{event_id}: no prior cause or declared external/background cause")
        if cause_type == "initial_state" and causes:
            missing_logic.append(f"{event_id}: initial_state must not cite prior events")
        for cause in causes:
            if cause == event_id:
                self_refs.append(event_id)
            elif cause not in ids:
                bad_refs.append(f"{event_id}->{cause}")
        for dependent in _split_ids(row.get("dependent_event_ids")):
            if dependent == event_id:
                self_refs.append(event_id)
            elif dependent not in ids:
                bad_refs.append(f"{event_id}=>{dependent}")
        missing = [column for column in required_cells if not _nonempty(row.get(column))]
        if missing:
            missing_logic.append(f"{event_id}: empty {', '.join(missing)}")
        counterfactual = (row.get("counterfactual_result") or "").strip()
        if counterfactual not in allowed_counterfactual:
            invalid_counterfactual.append(f"{event_id}:{counterfactual or 'empty'}")

    if invalid_cause_types:
        findings.append(_finding(False, "causal cause types", f"invalid cause type(s): {', '.join(invalid_cause_types[:8])}"))
    else:
        findings.append(_finding(True, "causal cause types", "all cause types are recognised"))
    if initial_count != 1:
        findings.append(_finding(False, "causal entry point", f"expected exactly one initial_state event; found {initial_count}"))
    else:
        findings.append(_finding(True, "causal entry point", "exactly one initial_state event"))
    if bad_refs:
        findings.append(_finding(False, "causal references", f"unknown event reference(s): {', '.join(sorted(set(bad_refs))[:8])}"))
    else:
        findings.append(_finding(True, "causal references", "all cause and dependency references resolve"))
    if self_refs:
        findings.append(_finding(False, "causal self-reference", f"self-reference in: {', '.join(sorted(set(self_refs)))}"))
    cycle = _detect_cycle(edges)
    if cycle:
        findings.append(_finding(False, "causal graph", f"cycle detected: {' -> '.join(cycle)}"))
    else:
        findings.append(_finding(True, "causal graph", "no causal cycle detected"))
    if missing_logic:
        findings.append(_finding(False, "causal event completeness", "; ".join(missing_logic[:8])))
    else:
        findings.append(_finding(True, "causal event completeness", "every event records cause logic, consequence, state change, information effect, and deletion impact"))
    if invalid_counterfactual:
        findings.append(_finding(False, "counterfactual tests", f"invalid or missing result(s): {', '.join(invalid_counterfactual[:8])}"))
    else:
        findings.append(_finding(True, "counterfactual tests", "every causal event has an allowed counterfactual result"))

    protagonist_id = ""
    model_path = video_dir / ".studio" / "internal" / "story" / "story-model.json"
    if model_path.is_file():
        try:
            protagonist_id = str(_nested(_read_json(model_path), "premise.protagonist_id") or "").strip()
        except (OSError, json.JSONDecodeError):
            protagonist_id = ""
    if protagonist_id:
        protagonist_events = [row for row in rows if (row.get("actor_id") or "").strip() == protagonist_id]
        decisions = [row for row in protagonist_events if (row.get("decision") or "").strip()]
        ratio = len(decisions) / len(rows) if rows else 0.0
        threshold = float(doctrine.get("audit", {}).get("protagonist_decision_warning_ratio", 0.35))
        if ratio < threshold:
            findings.append(_finding(True, "protagonist agency", f"only {len(decisions)}/{len(rows)} causal events contain a recorded {protagonist_id} decision; review whether the protagonist drives enough turns", "warning"))
        else:
            findings.append(_finding(True, "protagonist agency", f"{len(decisions)}/{len(rows)} causal events contain a recorded protagonist decision"))

    weak = [(row.get("event_id") or "").strip() for row in rows if (row.get("counterfactual_result") or "").strip() == "weak"]
    if weak:
        findings.append(_finding(True, "weak causal links", f"review deliberately marked weak link(s): {', '.join(weak)}", "warning"))
    return findings


def audit_setup_payoffs(video_dir: Path, doctrine: dict[str, Any]) -> list[StoryFinding]:
    path = video_dir / ".studio" / "internal" / "story" / "setup-payoff-ledger.csv"
    if not path.is_file():
        return [_finding(False, "setup/payoff ledger", ".studio/internal/story/setup-payoff-ledger.csv is missing")]
    rows = [row for row in _read_csv(path) if any(str(value or "").strip() for value in row.values())]
    findings = _unique_ids(rows, "setup_id", "setup IDs")
    if not rows:
        return findings
    allowed_status = set(doctrine.get("audit", {}).get("setup_statuses", ["planned", "paid_off", "intentionally_open", "cut"]))
    allowed_types = set(doctrine.get("audit", {}).get("payoff_types", []))
    errors: list[str] = []
    for row in rows:
        setup_id = (row.get("setup_id") or "").strip()
        status = (row.get("resolution_status") or "").strip()
        payoff_type = (row.get("planned_payoff_type") or "").strip()
        if status not in allowed_status:
            errors.append(f"{setup_id}: invalid resolution_status '{status or 'empty'}'")
            continue
        if status in {"planned", "paid_off"}:
            required = ["setup_beat_or_scene", "setup", "initial_audience_interpretation", "payoff_id", "payoff_beat_or_scene", "payoff", "planned_payoff_type", "latest_acceptable_point"]
            missing = [column for column in required if not _nonempty(row.get(column))]
            if missing:
                errors.append(f"{setup_id}: empty {', '.join(missing)}")
            if allowed_types and payoff_type not in allowed_types:
                errors.append(f"{setup_id}: invalid payoff type '{payoff_type or 'empty'}'")
        elif status == "intentionally_open" and not _nonempty(row.get("intentionally_open_reason")):
            errors.append(f"{setup_id}: intentionally_open requires a reason")
    if errors:
        findings.append(_finding(False, "setup/payoff obligations", "; ".join(errors[:8])))
    else:
        findings.append(_finding(True, "setup/payoff obligations", f"{len(rows)} setup obligation(s) have a planned payoff or explicit open-thread reason"))
    return findings


def audit_information_map(video_dir: Path) -> list[StoryFinding]:
    path = video_dir / ".studio" / "internal" / "story" / "information-map.csv"
    if not path.is_file():
        return [_finding(False, "information map", ".studio/internal/story/information-map.csv is missing")]
    rows = [row for row in _read_csv(path) if any((value or "").strip() for value in row.values())]
    findings = _unique_ids(rows, "info_id", "information IDs")
    if not rows:
        return findings
    required = [
        "question_or_fact", "audience_knows_before", "audience_expects_before", "character_knowledge_before",
        "delivery_beat_or_scene", "audience_knows_after", "audience_expects_after", "emotional_orientation_after",
        "withheld_or_revealed",
    ]
    incomplete: list[str] = []
    allowed_modes = {"withheld", "revealed", "partially_revealed", "recontextualised", "dramatic_irony"}
    for row in rows:
        info_id = (row.get("info_id") or "").strip()
        missing = [column for column in required if not _nonempty(row.get(column))]
        mode = (row.get("withheld_or_revealed") or "").strip()
        if mode and mode not in allowed_modes:
            missing.append(f"withheld_or_revealed invalid:{mode}")
        if missing:
            incomplete.append(f"{info_id}: {', '.join(missing)}")
    if incomplete:
        findings.append(_finding(False, "information state transitions", f"incomplete row(s): {'; '.join(incomplete[:8])}"))
    else:
        findings.append(_finding(True, "information state transitions", f"{len(rows)} audience/character knowledge transition(s) recorded"))
    return findings


def audit_sequences_and_beats(video_dir: Path) -> list[StoryFinding]:
    sequence_path = video_dir / ".studio" / "internal" / "story" / "sequence-outline.csv"
    beat_path = video_dir / ".studio" / "internal" / "story" / "beat-sheet.csv"
    scene_path = video_dir / ".studio" / "internal" / "story" / "scene-cards.csv"
    findings: list[StoryFinding] = []
    if not sequence_path.is_file():
        return [_finding(False, "sequence outline", ".studio/internal/story/sequence-outline.csv is missing")]
    sequences = [row for row in _read_csv(sequence_path) if any((value or "").strip() for value in row.values())]
    findings.extend(_unique_ids(sequences, "sequence_id", "sequence IDs"))
    sequence_ids = {(row.get("sequence_id") or "").strip() for row in sequences if (row.get("sequence_id") or "").strip()}
    required_sequence = ["temporary_goal", "strategy", "primary_location", "complications", "outcome", "story_state_afterward", "estimated_seconds", "production_note"]
    incomplete_sequences: list[str] = []
    for row in sequences:
        sequence_id = (row.get("sequence_id") or "").strip()
        missing = [column for column in required_sequence if not _nonempty(row.get(column))]
        if missing:
            incomplete_sequences.append(f"{sequence_id}: {', '.join(missing)}")
    if incomplete_sequences:
        findings.append(_finding(False, "sequence completeness", f"incomplete row(s): {'; '.join(incomplete_sequences[:8])}"))
    elif sequences:
        findings.append(_finding(True, "sequence completeness", f"{len(sequences)} temporary objective/outcome unit(s) recorded"))

    if not beat_path.is_file():
        findings.append(_finding(False, "beat sheet", ".studio/internal/story/beat-sheet.csv is missing"))
        return findings
    beats = [row for row in _read_csv(beat_path) if any((value or "").strip() for value in row.values())]
    findings.extend(_unique_ids(beats, "beat_id", "beat IDs"))
    incomplete_beats: list[str] = []
    bad_sequence_refs: list[str] = []
    required_beat = ["sequence_id", "actor_id", "attempt", "interference", "change", "next_cause", "purpose", "visual", "audio", "estimated_seconds"]
    for row in beats:
        beat_id = (row.get("beat_id") or "").strip()
        sequence_id = (row.get("sequence_id") or "").strip()
        missing = [column for column in required_beat if not _nonempty(row.get(column))]
        if missing:
            incomplete_beats.append(f"{beat_id}: {', '.join(missing)}")
        if sequence_id and sequence_id not in sequence_ids:
            bad_sequence_refs.append(f"{beat_id}->{sequence_id}")
    if incomplete_beats:
        findings.append(_finding(False, "beat change logic", f"incomplete row(s): {'; '.join(incomplete_beats[:8])}"))
    elif beats:
        findings.append(_finding(True, "beat change logic", f"{len(beats)} beat(s) record attempt, interference, change, and next-cause logic"))

    if scene_path.is_file():
        scenes = [row for row in _read_csv(scene_path) if any((value or "").strip() for value in row.values())]
        for row in scenes:
            scene_id = (row.get("scene_id") or "").strip()
            sequence_id = (row.get("sequence_id") or "").strip()
            if sequence_id and sequence_id not in sequence_ids:
                bad_sequence_refs.append(f"{scene_id}->{sequence_id}")
    if bad_sequence_refs:
        findings.append(_finding(False, "sequence references", f"unknown sequence reference(s): {', '.join(sorted(set(bad_sequence_refs))[:10])}"))
    elif sequence_ids:
        findings.append(_finding(True, "sequence references", "all beat and scene sequence references resolve"))
    return findings


def audit_relationships(video_dir: Path) -> list[StoryFinding]:
    relationship_path = video_dir / ".studio" / "internal" / "story" / "relationships.csv"
    model_path = video_dir / ".studio" / "internal" / "story" / "story-model.json"
    if not relationship_path.is_file():
        return [_finding(False, "relationship register", ".studio/internal/story/relationships.csv is missing")]
    character_ids: set[str] = set()
    if model_path.is_file():
        try:
            payload = _read_json(model_path)
            characters = payload.get("characters", []) if isinstance(payload, dict) else []
            character_ids = {str(item.get("character_id") or "").strip() for item in characters if isinstance(item, dict) and str(item.get("character_id") or "").strip()}
        except (OSError, json.JSONDecodeError):
            character_ids = set()
    rows = [row for row in _read_csv(relationship_path) if any((value or "").strip() for value in row.values())]
    if len(character_ids) <= 1 and not rows:
        return [_finding(True, "relationship register", "single-character model; no relationship row required")]
    findings = _unique_ids(rows, "relationship_id", "relationship IDs")
    required = ["character_a", "character_b", "public_relationship", "private_tension", "shared_history", "what_a_wants_from_b", "what_b_wants_from_a", "power_balance", "predicted_change"]
    errors: list[str] = []
    for row in rows:
        relationship_id = (row.get("relationship_id") or "").strip()
        a = (row.get("character_a") or "").strip()
        b = (row.get("character_b") or "").strip()
        missing = [column for column in required if not _nonempty(row.get(column))]
        if missing:
            errors.append(f"{relationship_id}: empty {', '.join(missing)}")
        if a == b and a:
            errors.append(f"{relationship_id}: character_a and character_b are identical")
        for character_id in [a, b]:
            if character_id and character_ids and character_id not in character_ids:
                errors.append(f"{relationship_id}: unknown character {character_id}")
    if errors:
        findings.append(_finding(False, "relationship dynamics", "; ".join(errors[:8])))
    elif rows:
        findings.append(_finding(True, "relationship dynamics", f"{len(rows)} relationship change model(s) recorded"))
    return findings


def audit_scene_cards(video_dir: Path) -> list[StoryFinding]:
    path = video_dir / ".studio" / "internal" / "story" / "scene-cards.csv"
    if not path.is_file():
        return [_finding(False, "scene cards", ".studio/internal/story/scene-cards.csv is missing")]
    _, width_issues = _csv_width_issues(path)
    rows = [row for row in _read_csv(path) if any(str(value or "").strip() for value in row.values())]
    findings = _unique_ids(rows, "scene_id", "scene IDs")
    if width_issues:
        findings.append(
            _finding(
                False,
                "scene-card CSV structure",
                "row width mismatch: " + "; ".join(width_issues[:8]),
            )
        )
    if not rows:
        return findings
    hard_fields = ["scene_purpose", "entry_state", "exit_state", "story_value", "production_requirements"]
    incomplete: list[str] = []
    advisory: list[str] = []
    static: list[str] = []
    for row in rows:
        scene_id = (row.get("scene_id") or "").strip()
        missing = [column for column in hard_fields if not _nonempty(row.get(column))]
        if missing:
            incomplete.append(f"{scene_id}: {', '.join(missing)}")
        convention_missing = [column for column in ["objective", "obstacle", "turn", "outcome"] if not _nonempty(row.get(column))]
        if convention_missing:
            advisory.append(f"{scene_id}: {', '.join(convention_missing)}")
        entry = (row.get("entry_state") or "").strip().casefold()
        exit_state = (row.get("exit_state") or "").strip().casefold()
        if entry and entry == exit_state:
            static.append(scene_id)
    if incomplete:
        findings.append(_finding(False, "scene necessity evidence", f"incomplete row(s): {'; '.join(incomplete[:8])}"))
    else:
        findings.append(_finding(True, "scene necessity evidence", f"{len(rows)} scene(s) record purpose, state change evidence, value, and production requirements"))
    if advisory:
        findings.append(_finding(True, "scene engine conventions", f"objective/obstacle/turn/outcome are advisory; review omissions in {'; '.join(advisory[:8])}", "warning"))
    else:
        findings.append(_finding(True, "scene engine conventions", "all scene cards use the optional objective/obstacle/turn/outcome diagnostic"))
    if static:
        findings.append(_finding(True, "scene state change", f"entry_state exactly matches exit_state in {', '.join(static)}; confirm that atmosphere/theme/setup earns the scene", "warning"))
    return findings


def audit_revision_passes(video_dir: Path, doctrine: dict[str, Any]) -> list[StoryFinding]:
    path = video_dir / ".studio" / "internal" / "script" / "revision-pass-status.json"
    if not path.is_file():
        return [_finding(False, "revision passes", ".studio/internal/script/revision-pass-status.json is missing")]
    try:
        payload = _read_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        return [_finding(False, "revision passes", f"invalid JSON: {exc}")]
    passes = payload.get("passes") if isinstance(payload, dict) else None
    if not isinstance(passes, list):
        return [_finding(False, "revision passes", "passes must be a list")]

    audit = doctrine.get("audit", {})
    core_ids = [str(item) for item in audit.get("core_revision_pass_ids", audit.get("revision_pass_ids", []))]
    optional_ids = [str(item) for item in audit.get("optional_revision_pass_ids", [])]
    known_ids = set(core_ids + optional_ids)
    allowed_status = set(audit.get("revision_statuses", ["complete", "not_applicable", "not_required", "blocked"]))
    by_id: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    for item in passes:
        if not isinstance(item, dict):
            errors.append("non-object pass entry")
            continue
        pass_id = str(item.get("id") or "").strip()
        if not pass_id:
            errors.append("pass with empty id")
            continue
        if pass_id in by_id:
            errors.append(f"duplicate pass id {pass_id}")
        by_id[pass_id] = item

    missing_core = [pass_id for pass_id in core_ids if pass_id not in by_id]
    if missing_core:
        errors.append(f"missing core pass(es): {', '.join(missing_core)}")
    unknown = [pass_id for pass_id in by_id if known_ids and pass_id not in known_ids]
    if unknown:
        errors.append(f"unknown pass(es): {', '.join(unknown)}")

    activated = 0
    for pass_id, item in by_id.items():
        required = bool(item.get("required", pass_id in core_ids)) or pass_id in core_ids
        status = str(item.get("status") or "").strip()
        evidence = str(item.get("evidence") or "").strip()
        decision = str(item.get("decision") or "").strip()
        if status not in allowed_status:
            errors.append(f"{pass_id}: invalid status '{status or 'empty'}'")
            continue
        if status == "blocked":
            errors.append(f"{pass_id}: still blocked")
            continue
        if required and status in {"not_required", "not_applicable"}:
            errors.append(f"{pass_id}: core pass cannot be skipped")
            continue
        if not required and status == "not_required":
            if len(evidence) < 15:
                errors.append(f"{pass_id}: explain why this optional pass is not relevant")
            continue
        if status == "not_applicable":
            if len(evidence) < 15:
                errors.append(f"{pass_id}: not_applicable rationale is too brief")
            continue
        if status == "complete":
            activated += 1
            if not _nonempty(evidence):
                errors.append(f"{pass_id}: evidence is empty")
            if not _nonempty(decision):
                errors.append(f"{pass_id}: decision/result is empty")

    if errors:
        return [_finding(False, "revision passes", "; ".join(errors[:12]))]
    return [_finding(True, "revision passes", f"{len(core_ids)} core pass(es) complete; {max(0, activated-len(core_ids))} optional pass(es) activated")]


def audit_outline(root: Path, video_dir: Path) -> list[StoryFinding]:
    doctrine_path = root / "studio" / "writing-doctrine.json"
    try:
        doctrine = _read_json(doctrine_path)
    except (OSError, json.JSONDecodeError):
        doctrine = {}
    findings: list[StoryFinding] = []
    findings.extend(audit_story_model(video_dir))
    findings.extend(audit_causal_spine(video_dir, doctrine))
    findings.extend(audit_sequences_and_beats(video_dir))
    findings.extend(audit_relationships(video_dir))
    findings.extend(audit_setup_payoffs(video_dir, doctrine))
    findings.extend(audit_information_map(video_dir))
    findings.extend(audit_scene_cards(video_dir))
    return findings


def audit_script(root: Path, video_dir: Path) -> list[StoryFinding]:
    doctrine_path = root / "studio" / "writing-doctrine.json"
    try:
        doctrine = _read_json(doctrine_path)
    except (OSError, json.JSONDecodeError):
        doctrine = {}
    return audit_revision_passes(video_dir, doctrine)


def audit_story(root: Path, video_dir: Path, scope: str = "auto", current_stage: str | None = None) -> list[StoryFinding]:
    try:
        stage_payload = _read_json(root / "studio" / "stages.json")
        stages = [str(item.get("name")) for item in stage_payload if isinstance(item, dict) and item.get("name")]
    except (OSError, json.JSONDecodeError, TypeError):
        stages = ["direction", "story", "script", "production", "edit", "release", "learn"]
    stage_index = stages.index(current_stage) if current_stage in stages else 0
    findings: list[StoryFinding] = []
    findings.extend(validate_writing_doctrine(root))
    if scope in {"outline", "all"} or (scope == "auto" and stage_index >= stages.index("story")):
        findings.extend(audit_outline(root, video_dir))
    if scope in {"script", "all"} or (scope == "auto" and stage_index >= stages.index("script")):
        findings.extend(audit_script(root, video_dir))
    if scope == "auto" and stage_index < stages.index("story"):
        findings.append(_finding(True, "story audit scope", "outline diagnostics become active at the Story phase", "info"))
    return findings
