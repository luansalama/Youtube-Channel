from __future__ import annotations

import csv
import http.client
import io
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlencode
from pathlib import Path

from mcstudio.analytics import import_youtube_csv, report_for_slug
from mcstudio.assistant import (
    build_prompt,
    create_proposal,
    load_settings,
    recover_latest_runner_proposal,
    validate_proposal,
)
from mcstudio.core import StudioError, create_video, evaluate_stage, load_project, maintain_repository, save_project, write_json
from mcstudio.dashboard import dashboard_html, generate_dashboard, render_page
from mcstudio.server import StudioHTTPServer, StudioHandler
from mcstudio.runners import execute_runner, runner_candidates, _prioritise_web_research, _write_elevated_runner_script
from mcstudio.svg import generate_thumbnail_wireframes
from mcstudio.youtube import build_request, upload

SOURCE_ROOT = Path(__file__).resolve().parents[1]


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for rel in ["studio", "templates"]:
            shutil.copytree(SOURCE_ROOT / rel, self.root / rel)
        (self.root / "videos").mkdir()
        maintain_repository(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def _write_runner_script(self, name: str, source: str) -> str:
        path = self.root / name
        path.write_text(source, encoding="utf-8")
        return f'"{sys.executable}" "{path}"'

    def test_runner_manager_default_routes(self):
        (self.root / "studio" / "local-settings.json").unlink(missing_ok=True)
        settings = load_settings(self.root, include_secret=True)
        self.assertEqual(runner_candidates(settings, "story", "develop")[0], "codex")
        self.assertEqual(runner_candidates(settings, "production", "develop")[0], "opencode")
        self.assertEqual(runner_candidates(settings, "story", "audit")[0], "opencode")
        self.assertTrue(settings["codex_full_output"])

    def test_web_research_prioritises_explicit_search_runners(self):
        self.assertEqual(
            _prioritise_web_research(["opencode", "codex", "openai"], True),
            ["codex", "openai", "opencode"],
        )
        self.assertEqual(
            _prioritise_web_research(["opencode", "codex"], False),
            ["opencode", "codex"],
        )
        self.assertEqual(
            _prioritise_web_research(["opencode", "codex"], True, "opencode"),
            ["opencode", "codex"],
        )

    def test_production_prompt_exposes_research_and_storyboard_files(self):
        slug = create_video(self.root, "Research Production")
        _, project = load_project(self.root, slug)
        project["stage"] = "production"
        save_project(self.root / "videos" / slug, project)
        instructions, request, allowed = build_prompt(
            self.root, slug, "Research the complete production stack and storyboard.", mode="develop"
        )
        self.assertIn(".studio/internal/production/storyboard-plan.md", allowed)
        self.assertIn(".studio/internal/production/technical-research.md", allowed)
        self.assertIn(".studio/internal/production/storyboard-panels.csv", allowed)
        self.assertIn("Do not generate, embed or claim any storyboard image", instructions)
        self.assertIn("storyboard-panels.csv", request)

    def test_codex_runner_returns_structured_read_only_proposal(self):
        command = self._write_runner_script("mock_codex.py", r'''
import json
import pathlib
import sys
args = sys.argv[1:]
if args and args[0] == "--version":
    print("mock-codex 1.0")
    raise SystemExit(0)
if args[:2] == ["login", "status"]:
    print("authenticated")
    raise SystemExit(0)
if args and args[0] == "exec":
    sys.stdin.read()
    output = pathlib.Path(args[args.index("-o") + 1])
    output.write_text(json.dumps({
        "summary": "Codex proposal",
        "document": "# Direction\\n\\nCodex completed the proposal.",
        "files": {},
        "questions": [],
        "warnings": []
    }), encoding="utf-8")
    raise SystemExit(0)
print("unsupported", file=sys.stderr)
raise SystemExit(2)
''')
        settings = load_settings(self.root, include_secret=True)
        settings["runners"]["codex"]["command"] = command
        result, metadata = execute_runner(
            self.root, settings, "Return JSON.", "Create a direction.",
            stage="direction", mode="develop", force_runner="codex"
        )
        self.assertEqual(result["summary"], "Codex proposal")
        self.assertEqual(metadata["runner"], "codex")
        self.assertEqual(metadata["attempts"][-1]["status"], "success")

    def test_codex_focused_mode_uses_disposable_workspace(self):
        capture = self.root / "codex-capture.json"
        source = f'''
import json
import os
import pathlib
import sys
args = sys.argv[1:]
prompt = sys.stdin.read()
pathlib.Path({str(capture)!r}).write_text(json.dumps({{
    "args": args,
    "cwd": os.getcwd(),
    "prompt": prompt,
}}), encoding="utf-8")
output = pathlib.Path(args[args.index("-o") + 1])
output.write_text(json.dumps({{
    "summary": "Focused proposal",
    "document": "# Direction\\n\\nFocused generation completed without repository inspection.",
    "files": [],
    "questions": [],
    "warnings": []
}}), encoding="utf-8")
raise SystemExit(0)
'''
        command = self._write_runner_script("mock_codex_focused.py", source)
        settings = load_settings(self.root, include_secret=True)
        settings["visible_runner_terminal"] = False
        settings["codex_full_output"] = False
        settings["runners"]["codex"]["command"] = command
        result, _ = execute_runner(
            self.root, settings, "Do not inspect the repository.", "Return the proposal.",
            stage="direction", mode="develop", force_runner="codex"
        )
        captured = json.loads(capture.read_text(encoding="utf-8"))
        self.assertEqual(result["summary"], "Focused proposal")
        self.assertNotEqual(Path(captured["cwd"]).resolve(), self.root.resolve())
        self.assertIn("--ignore-user-config", captured["args"])
        self.assertIn("--ignore-rules", captured["args"])
        self.assertIn('approval_policy="on-request"', captured["args"])
        self.assertIn('windows.sandbox="elevated"', captured["args"])
        self.assertIn("--json", captured["args"])
        self.assertIn('model_reasoning_summary="detailed"', captured["args"])
        workspace = captured["args"][captured["args"].index("-C") + 1]
        self.assertNotEqual(Path(workspace).resolve(), self.root.resolve())
        self.assertIn("Do not inspect the repository", captured["prompt"])

    def test_codex_full_output_mode_preserves_native_stream(self):
        capture = self.root / "codex-full-output-capture.json"
        source = rf'''
import json
import pathlib
import sys
args = sys.argv[1:]
pathlib.Path({str(capture)!r}).write_text(json.dumps({{"args": args}}), encoding="utf-8")
output = pathlib.Path(args[args.index("-o") + 1])
output.write_text(json.dumps({{
    "summary": "Native output proposal",
    "document": "# Direction\n\nNative Codex output stayed enabled.",
    "files": [],
    "questions": [],
    "warnings": []
}}), encoding="utf-8")
raise SystemExit(0)
'''
        command = self._write_runner_script("mock_codex_full_output.py", source)
        settings = load_settings(self.root, include_secret=True)
        settings["visible_runner_terminal"] = False
        settings["codex_full_output"] = True
        settings["runners"]["codex"]["command"] = command
        result, metadata = execute_runner(
            self.root, settings, "Return JSON.", "Create a direction.",
            stage="direction", mode="develop", force_runner="codex"
        )
        args = json.loads(capture.read_text(encoding="utf-8"))["args"]
        self.assertEqual(result["summary"], "Native output proposal")
        self.assertNotIn("--json", args)
        self.assertEqual(metadata["terminal_output_mode"], "full-native")

    def test_codex_run_is_archived_and_session_is_persistent(self):
        capture = self.root / "codex-archive-capture.json"
        source = rf'''
import json
import pathlib
import sys
args = sys.argv[1:]
sys.stdin.read()
print("session id: 019f6854-f3cd-71d2-b093-b7b5881ec55f", file=sys.stderr)
pathlib.Path({str(capture)!r}).write_text(json.dumps({{"args": args}}), encoding="utf-8")
output = pathlib.Path(args[args.index("-o") + 1])
output.write_text(json.dumps({{
    "summary": "Archived Codex proposal",
    "document": "# Direction\n\nThe durable run archive retained this proposal.",
    "files": [],
    "questions": [],
    "warnings": []
}}), encoding="utf-8")
raise SystemExit(0)
'''
        command = self._write_runner_script("mock_codex_archive.py", source)
        settings = load_settings(self.root, include_secret=True)
        settings["visible_runner_terminal"] = False
        settings["runners"]["codex"]["command"] = command
        result, metadata = execute_runner(
            self.root, settings, "Return JSON.", "Archive this direction proposal.",
            stage="direction", mode="develop", force_runner="codex"
        )
        args = json.loads(capture.read_text(encoding="utf-8"))["args"]
        self.assertEqual(result["summary"], "Archived Codex proposal")
        self.assertNotIn("--ephemeral", args)
        archive = self.root / metadata["run_archive"]
        self.assertTrue((archive / "prompt.txt").is_file())
        self.assertTrue((archive / "proposal-schema.json").is_file())
        self.assertTrue((archive / "final-proposal.json").is_file())
        self.assertTrue((archive / "stderr.log").is_file())
        record = json.loads((archive / "metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "success")
        self.assertEqual(record["session_id"], "019f6854-f3cd-71d2-b093-b7b5881ec55f")

    def test_failed_codex_run_creates_resume_script(self):
        command = self._write_runner_script("mock_codex_resume.py", "raise SystemExit(0)\n")
        settings = load_settings(self.root, include_secret=True)
        settings["visible_runner_terminal"] = False
        settings["runners"]["codex"]["command"] = command
        session_id = "019f6854-f3cd-71d2-b093-b7b5881ec55f"
        with patch(
            "mcstudio.runners._run",
            return_value=subprocess.CompletedProcess(["codex"], 124, "", f"session id: {session_id}"),
        ):
            with self.assertRaisesRegex(StudioError, "session was preserved"):
                execute_runner(
                    self.root, settings, "Return JSON.", "Continue this story.",
                    stage="story", mode="revise", force_runner="codex"
                )
        archives = sorted((self.root / "exports/runner-runs").glob("*/metadata.json"))
        self.assertEqual(len(archives), 1)
        archive = archives[0].parent
        record = json.loads(archives[0].read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "timed_out")
        self.assertEqual(record["session_id"], session_id)
        self.assertTrue((archive / "RESUME-CODEX.ps1").is_file())
        self.assertIn("resume", (archive / "RESUME-CODEX.ps1").read_text(encoding="utf-8-sig"))
        self.assertTrue((archive / "README.txt").is_file())

    def test_manual_import_accepts_codex_path_content_entries(self):
        create_video(self.root, "Import Codex Output")
        proposal = validate_proposal(self.root, "import-codex-output", {
            "summary": "Recovered Codex proposal",
            "document": "# Direction\n\nRecovered proposal content is substantive and ready for review.",
            "files": [
                {"path": ".studio/internal/direction/idea-score.json", "content": "{}"}
            ],
            "questions": [],
            "warnings": [],
        })
        self.assertEqual(proposal["files"][".studio/internal/direction/idea-score.json"], "{}")

    def test_proposal_accepts_duplicate_main_document_and_drops_it(self):
        video = create_video(self.root, "Duplicate Main Document")
        project = json.loads((video / "project.json").read_text(encoding="utf-8"))
        project["stage"] = "story"
        write_json(video / "project.json", project)
        document = "# Story plan\n\n" + ("A substantive revised story document. " * 8)
        proposal = validate_proposal(self.root, "duplicate-main-document", {
            "summary": "Story revision",
            "document": document,
            "files": [
                {"path": "02-story/story-plan.md", "content": document + "\n"},
                {"path": ".studio/internal/story/story-model.json", "content": "{}"},
            ],
            "questions": [],
            "warnings": [],
        })
        self.assertNotIn("02-story/story-plan.md", proposal["files"])
        self.assertEqual(proposal["files"][".studio/internal/story/story-model.json"], "{}")

    def test_proposal_rejects_conflicting_duplicate_main_document(self):
        video = create_video(self.root, "Conflicting Main Document")
        project = json.loads((video / "project.json").read_text(encoding="utf-8"))
        project["stage"] = "story"
        write_json(video / "project.json", project)
        document = "# Story plan\n\n" + ("Canonical proposal content. " * 8)
        with self.assertRaisesRegex(StudioError, "conflicting content for the main document"):
            validate_proposal(self.root, "conflicting-main-document", {
                "summary": "Story revision",
                "document": document,
                "files": {"02-story/story-plan.md": document + "Different ending."},
                "questions": [],
                "warnings": [],
            })

    def test_story_proposal_repairs_missing_scene_exit_state_column(self):
        video = create_video(self.root, "Repair Scene Card Columns")
        project = json.loads((video / "project.json").read_text(encoding="utf-8"))
        project["stage"] = "story"
        write_json(video / "project.json", project)
        header = [
            "scene_id", "sequence_id", "location", "time", "pov", "scene_purpose",
            "entry_state", "objective", "reason_objective_matters", "obstacle",
            "opposing_agent", "tactics", "information_revealed", "information_withheld",
            "emotional_progression", "visual_event", "turn", "outcome", "exit_state",
            "new_question", "setup_or_payoff", "story_value", "production_requirements",
        ]
        # Codex omitted exit_state, shifting all four trailing values one column left.
        malformed_row = [
            "SC-01", "SQ-01", "Ravine", "Night", "Close protagonist", "Open the mystery",
            "The player arrives", "Inspect the portal", "The contradiction matters", "Darkness",
            "Environment", "Inspect blocks", "The frame is active", "The builder is unknown",
            "Unease to resolve", "Purple light", "The player enters", "The known world is left",
            "Where did it lead?", "SP-01;PAY-01", "Inciting agency and mystery",
            "Matched set, controlled transition and continuity capture",
        ]
        output = io.StringIO(newline="")
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(header)
        writer.writerow(malformed_row)
        document = "# Story plan\n\n" + ("A substantive story proposal. " * 10)
        proposal = validate_proposal(self.root, "repair-scene-card-columns", {
            "summary": "Story revision",
            "document": document,
            "files": {
                ".studio/internal/story/scene-cards.csv": output.getvalue(),
            },
            "questions": [],
            "warnings": [],
        })
        repaired = list(csv.DictReader(io.StringIO(
            proposal["files"][".studio/internal/story/scene-cards.csv"]
        )))[0]
        self.assertEqual(repaired["exit_state"], "The known world is left")
        self.assertEqual(repaired["new_question"], "Where did it lead?")
        self.assertEqual(repaired["setup_or_payoff"], "SP-01;PAY-01")
        self.assertEqual(repaired["story_value"], "Inciting agency and mystery")
        self.assertEqual(
            repaired["production_requirements"],
            "Matched set, controlled transition and continuity capture",
        )
        self.assertIn("scene-card CSV column shift", proposal["warnings"][-1])

    def test_story_prompt_keeps_main_document_out_of_auxiliary_files(self):
        video = create_video(self.root, "Prompt Main Document")
        project = json.loads((video / "project.json").read_text(encoding="utf-8"))
        project["stage"] = "story"
        write_json(video / "project.json", project)
        instructions, request, allowed = build_prompt(self.root, "prompt-main-document", "Revise the story.")
        self.assertIn("Do not repeat 02-story/story-plan.md inside files", instructions)
        self.assertIn("MAIN DOCUMENT\n- 02-story/story-plan.md", request)
        auxiliary = request.split("ALLOWED AUXILIARY FILES", 1)[1].split("WRITING DOCTRINE", 1)[0]
        self.assertNotIn("02-story/story-plan.md", auxiliary)
        self.assertNotIn("02-story/story-plan.md", allowed)

    def test_recover_latest_runner_proposal_for_current_video(self):
        video = create_video(self.root, "Recover Completed Story")
        project = json.loads((video / "project.json").read_text(encoding="utf-8"))
        project["stage"] = "story"
        write_json(video / "project.json", project)
        archive = self.root / "exports/runner-runs/20260716-story-run"
        archive.mkdir(parents=True)
        archive.joinpath("prompt.txt").write_text(
            "VIDEO\nTitle: Recover Completed Story\nSlug: recover-completed-story\n",
            encoding="utf-8",
        )
        document = "# Story plan\n\n" + ("Recovered complete story proposal. " * 8)
        archive.joinpath("final-proposal.json").write_text(json.dumps({
            "summary": "Recovered story",
            "document": document,
            "files": [
                {"path": "02-story/story-plan.md", "content": document},
                {"path": ".studio/internal/story/story-model.json", "content": "{}"},
            ],
            "questions": [],
            "warnings": [],
        }), encoding="utf-8")
        archive.joinpath("metadata.json").write_text(json.dumps({
            "runner": "codex", "model": "gpt-5.6-sol", "reasoning_effort": "max",
            "session_id": "session-123", "status": "success",
        }), encoding="utf-8")
        proposal = recover_latest_runner_proposal(self.root, "recover-completed-story")
        self.assertEqual(proposal["status"], "pending")
        self.assertEqual(proposal["mode"], "recovered")
        self.assertEqual(proposal["source_run_archive"], "exports/runner-runs/20260716-story-run")
        self.assertNotIn("02-story/story-plan.md", proposal["files"])
        self.assertEqual(proposal["files"][".studio/internal/story/story-model.json"], "{}")
        duplicate = recover_latest_runner_proposal(self.root, "recover-completed-story")
        self.assertEqual(duplicate["id"], proposal["id"])

    def test_story_prompt_uses_existing_continuity_bible(self):
        video = create_video(self.root, "Continuity Prompt")
        project = json.loads((video / "project.json").read_text(encoding="utf-8"))
        project["stage"] = "story"
        write_json(video / "project.json", project)
        _, request, allowed = build_prompt(self.root, "continuity-prompt", "Develop the story.")
        self.assertIn(".studio/internal/story/continuity-bible.md", allowed)
        self.assertNotIn(".studio/internal/story/continuity-register.csv", allowed)
        self.assertIn("continuity-bible.md", request)
        self.assertNotIn("continuity-register.csv", request)

    def test_production_proposal_skips_capture_only_completion_checks(self):
        video = create_video(self.root, "Production Proposal Scope")
        project = json.loads((video / "project.json").read_text(encoding="utf-8"))
        project["stage"] = "production"
        write_json(video / "project.json", project)

        def csv_text(fieldnames, rows):
            buffer = io.StringIO(newline="")
            writer = csv.DictWriter(buffer, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
            return buffer.getvalue()

        deep_files = {
            ".studio/internal/production/storyboard-plan.md": "# Storyboard plan\n\n" + ("Literal spatial panel descriptions with camera, blocking, lighting, transition and continuity. " * 30),
            ".studio/internal/production/technical-research.md": "# Technical research\n\n" + ("Official-source version research, dependencies, boundaries, deterministic controls and untested compatibility. " * 30),
            ".studio/internal/production/toolchain-matrix.csv": csv_text(
                ["component_id","category","candidate","exact_version","minecraft_version","loader","purpose","official_source","licence","compatibility_status","decision","fallback","notes"],
                [{"component_id":f"TC-{i:02d}","category":"tool","candidate":f"Candidate {i}","exact_version":"to verify","minecraft_version":"1.20.1 candidate","loader":"Fabric","purpose":"planned capability","official_source":"https://example.invalid/official","licence":"to verify","compatibility_status":"individual support only","decision":"test","fallback":"composite","notes":"No integrated test claim."} for i in range(1,9)],
            ),
            ".studio/internal/production/scene-implementation-matrix.csv": csv_text(
                ["scene_id","script_requirement","preferred_method","minecraft_version","tool_or_mod","deterministic_control","camera_method","vfx_method","fallback","test_id","evidence_status","notes"],
                [{"scene_id":str(i),"script_requirement":f"Scene {i} beat","preferred_method":"planned controlled plate","minecraft_version":"1.20.1 candidate","tool_or_mod":"commands plus camera tool","deterministic_control":"tagged entities and reset function","camera_method":"planned keyframe","vfx_method":"layered plate","fallback":"locked composite","test_id":f"T-{i:02d}","evidence_status":"planned not tested","notes":"No success claim."} for i in range(1,14)],
            ),
            ".studio/internal/production/test-matrix.csv": csv_text(
                ["test_id","capability","scene_ids","stack","procedure","pass_criteria","failure_evidence","fallback","status","notes"],
                [{"test_id":f"T-{i:02d}","capability":f"Capability {i}","scene_ids":str(i),"stack":"candidate stack","procedure":"install then save reload and record","pass_criteria":"repeatable documented result","failure_evidence":"log and recording","fallback":"controlled plate","status":"not run","notes":"Planned only."} for i in range(1,9)],
            ),
            ".studio/internal/production/storyboard-panels.csv": csv_text(
                ["panel_id","scene_id","shot_id","order","frame_description","composition","camera","subject_blocking","environment","lighting","movement","transition","audio","continuity","generation_reference","status"],
                [{"panel_id":f"P-{i:02d}","scene_id":str(((i-1)//2)+1),"shot_id":f"SH-{i:02d}","order":str(i),"frame_description":"Literal planned frame","composition":"subject on rule-of-thirds mark","camera":"recorded height and FOV to establish","subject_blocking":"marked foreground and midground positions","environment":"planned modular set","lighting":"key direction specified","movement":"screen-left to screen-right","transition":"cut","audio":"planned cue","continuity":"match recorded state","generation_reference":"future greybox only; no image generated","status":"planned"} for i in range(1,27)],
            ),
            ".studio/internal/production/camera-paths.csv": csv_text(
                ["path_id","shot_id","tool","duration_seconds","fps","start_state","end_state","notes"],
                [{"path_id":f"CP-{i:02d}","shot_id":f"SH-{i:02d}","tool":"candidate replay camera","duration_seconds":"5","fps":"24","start_state":"planned transform A","end_state":"planned transform B","notes":"Not recorded."} for i in range(1,14)],
            ),
            ".studio/internal/production/location-plan.md": "# Location plan\n\n" + ("Modular hero location, camera-safe geometry, reset state, perceived-scale cheat and build order. " * 15),
            ".studio/internal/production/build-budget.md": "# Build budget\n\n" + ("Planned solo hours, BRL approval boundary, reuse value and must-should-could cut line. " * 10),
        }

        proposal_payload = {
            "summary": "Production planning proposal",
            "document": "# Production plan\n\n" + (
                "This plan defines the next honest build, staging, camera, asset and risk decisions "
                "without claiming that capture has already happened. " * 18
            ),
            "files": {
                **deep_files,
                ".studio/internal/production/shot-list.csv": csv_text(
                    ["shot_id", "beat", "location", "framing", "camera_move", "action", "dialogue_or_vo", "duration_seconds", "capture_method", "assets", "status"],
                    [
                        {
                            "shot_id": f"SH-{index:02d}",
                            "beat": f"Beat {index}",
                            "location": "Archive",
                            "framing": "wide",
                            "camera_move": "locked",
                            "action": "Planned player action",
                            "dialogue_or_vo": "Planned narration",
                            "duration_seconds": "5",
                            "capture_method": "Minecraft replay capture",
                            "assets": "Archive set",
                            "status": "planned",
                        }
                        for index in range(1, 7)
                    ],
                ),
                ".studio/internal/production/asset-register.csv": csv_text(
                    ["asset_id", "asset", "type", "source_or_owner", "licence", "version", "needed_for", "status", "notes"],
                    [{
                        "asset_id": "A-01",
                        "asset": "Archive set",
                        "type": "build",
                        "source_or_owner": "project owner",
                        "licence": "ownership to verify before use",
                        "version": "planned",
                        "needed_for": "all archive shots",
                        "status": "planned",
                        "notes": "No completion claim.",
                    }],
                ),
                ".studio/internal/production/location-cards.csv": csv_text(
                    ["location_id", "name", "story_function", "hero_angle", "modular_elements", "lighting_state", "completion", "notes"],
                    [{
                        "location_id": "L-01",
                        "name": "Archive",
                        "story_function": "Primary mystery location",
                        "hero_angle": "Entrance towards central chamber",
                        "modular_elements": "Corridor and chamber",
                        "lighting_state": "Planned neutral and warning states",
                        "completion": "planned",
                        "notes": "Build state must be recorded by the user.",
                    }],
                ),
            },
            "questions": [],
            "warnings": ["Capture evidence remains required before advancing to Edit."],
        }
        counter = self.root / "production-proposal-count.txt"
        encoded_proposal = json.dumps(proposal_payload)
        source = f'''
import pathlib
import sys
count_path = pathlib.Path({str(counter)!r})
count = int(count_path.read_text() or "0") if count_path.exists() else 0
count_path.write_text(str(count + 1), encoding="utf-8")
args = sys.argv[1:]
sys.stdin.read()
pathlib.Path(args[args.index("-o") + 1]).write_text({encoded_proposal!r}, encoding="utf-8")
raise SystemExit(0)
'''
        command = self._write_runner_script("mock_production_scope.py", source)
        settings = load_settings(self.root, include_secret=True)
        settings["visible_runner_terminal"] = False
        settings["routing_mode"] = "fixed"
        settings["fixed_runner"] = "codex"
        settings["fallback_enabled"] = False
        settings["runners"]["codex"]["command"] = command
        write_json(self.root / "studio" / "local-settings.json", settings)

        proposal = create_proposal(self.root, "production-proposal-scope", "Plan production honestly.")

        self.assertEqual(counter.read_text(encoding="utf-8"), "1")
        self.assertEqual(proposal["deterministic_validation"], "passed")
        self.assertFalse(proposal["repair_pass_used"])
        completion_failures = {
            item.label for item in evaluate_stage(
                self.root, "production-proposal-scope", include_approval=False
            ) if not item.ok
        }
        self.assertIn("internal capture log", completion_failures)
        self.assertIn("selected captured take", completion_failures)
        self.assertIn("technically usable selected take", completion_failures)

    def test_proposal_gets_one_bounded_repair_after_failed_checks(self):
        create_video(self.root, "Repair Proposal")
        counter = self.root / "repair-count.txt"
        valid_score = {
            "premise": "A player discovers an impossible portal beneath a familiar home.",
            "viewer_promise": "A fair visual mystery with a causal emotional resolution.",
            "expected_pleasure": ["pattern recognition", "earned reinterpretation"],
            "hook": "A lit portal appears in a private single-player world.",
            "dramatic_engine": "Each investigation changes what the player believes and can save.",
            "thematic_question": "Can a choice matter when an outcome is fixed?",
            "minecraft_causality": "Persistent blocks, geography and survival resources drive the mystery.",
            "climactic_choice": "Save a living companion instead of an already lost structure.",
            "ending": "The home burns, but the companion survives.",
            "final_state": "The player leaves with loss, knowledge and a meaningful responsibility.",
            "scope": "small solo production",
            "score": 86,
            "decision": "develop",
            "research_mode": "none",
            "research_reason": "This original fictional premise makes no external factual claim requiring research.",
        }
        source = f'''
import json
import pathlib
import sys
count_path = pathlib.Path({str(counter)!r})
count = int(count_path.read_text() or "0") if count_path.exists() else 0
count += 1
count_path.write_text(str(count), encoding="utf-8")
args = sys.argv[1:]
sys.stdin.read()
output = pathlib.Path(args[args.index("-o") + 1])
if count == 1:
    proposal = {{
        "summary": "Incomplete first attempt",
        "document": "# Direction\\n\\nThis draft is substantive enough to parse but too short for the phase gate.",
        "files": [],
        "questions": [],
        "warnings": []
    }}
else:
    proposal = {{
        "summary": "Repaired proposal",
        "document": "# Direction\\n\\n" + ("A focused, causal direction with clear audience promise and production scope. " * 25),
        "files": [{{
            "path": ".studio/internal/direction/idea-score.json",
            "content": json.dumps({valid_score!r})
        }}],
        "questions": [],
        "warnings": []
    }}
output.write_text(json.dumps(proposal), encoding="utf-8")
raise SystemExit(0)
'''
        command = self._write_runner_script("mock_codex_repair.py", source)
        settings = load_settings(self.root, include_secret=True)
        settings["visible_runner_terminal"] = False
        settings["routing_mode"] = "fixed"
        settings["fixed_runner"] = "codex"
        settings["fallback_enabled"] = False
        settings["runners"]["codex"]["command"] = command
        write_json(self.root / "studio" / "local-settings.json", settings)

        proposal = create_proposal(self.root, "repair-proposal", "Develop a strong direction.")
        self.assertEqual(counter.read_text(encoding="utf-8"), "2")
        self.assertEqual(proposal["deterministic_validation"], "passed")
        self.assertTrue(proposal["repair_pass_used"])
        self.assertEqual(proposal["summary"], "Repaired proposal")
        self.assertEqual(proposal["runner_attempts"][-1]["status"], "repair_success")

    def test_opencode_runner_and_cross_runner_fallback(self):
        failing_codex = self._write_runner_script("mock_codex_fail.py", r'''
import sys
print("intentional failure", file=sys.stderr)
raise SystemExit(3)
''')
        opencode = self._write_runner_script("mock_opencode.py", r'''
import json
import sys
args = sys.argv[1:]
proposal = {
    "summary": "OpenCode proposal",
    "document": "# Production plan\\n\\nOpenCode completed the proposal.",
    "files": {},
    "questions": [],
    "warnings": []
}
if args and args[0] == "--version":
    print("mock-opencode 1.0")
    raise SystemExit(0)
if args[:2] == ["auth", "list"]:
    print("provider connected")
    raise SystemExit(0)
if args and args[0] == "run":
    print(json.dumps({"sessionID": "mock-session", "part": {"type": "text", "text": json.dumps(proposal)}}))
    raise SystemExit(0)
if args and args[0] == "export":
    print(json.dumps({"messages": [{"parts": [{"type": "text", "text": json.dumps(proposal)}]}]}))
    raise SystemExit(0)
print("unsupported", file=sys.stderr)
raise SystemExit(2)
''')
        settings = load_settings(self.root, include_secret=True)
        settings["routing_mode"] = "fixed"
        settings["fixed_runner"] = "codex"
        settings["fallback_enabled"] = True
        settings["fallback_order"] = ["opencode"]
        settings["runners"]["codex"]["command"] = failing_codex
        settings["runners"]["opencode"]["command"] = opencode
        result, metadata = execute_runner(
            self.root, settings, "Return JSON.", "Create a production plan.",
            stage="production", mode="develop"
        )
        self.assertEqual(result["summary"], "OpenCode proposal")
        self.assertEqual(metadata["runner"], "opencode")
        self.assertEqual([item["status"] for item in metadata["attempts"]], ["failed", "success"])

    def test_dashboard_runner_test_action_executes_configured_codex(self):
        command = self._write_runner_script("mock_dashboard_codex.py", r'''
import json
import pathlib
import sys
args = sys.argv[1:]
if args and args[0] == "exec":
    sys.stdin.read()
    pathlib.Path(args[args.index("-o") + 1]).write_text(json.dumps({
        "summary": "Runner connection works",
        "document": "# Runner test\n\nConnection successful.",
        "files": {},
        "questions": [],
        "warnings": []
    }), encoding="utf-8")
    raise SystemExit(0)
raise SystemExit(0)
''')
        settings = load_settings(self.root, include_secret=True)
        settings["runners"]["codex"]["command"] = command
        write_json(self.root / "studio/local-settings.json", settings)
        server = StudioHTTPServer(("127.0.0.1", 0), StudioHandler, self.root)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address
            payload = urlencode({"runner": "codex"})
            connection = http.client.HTTPConnection(host, port, timeout=5)
            connection.request("POST", "/action/runner-test", body=payload, headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Content-Length": str(len(payload)),
            })
            response = connection.getresponse(); body = response.read().decode("utf-8"); connection.close()
            self.assertIn(response.status, {200, 303})
            if response.status == 200:
                self.assertIn("Connection test started", body)
            deadline = time.time() + 5
            while time.time() < deadline and any(job.get("status") == "running" for job in server.jobs.values()):
                time.sleep(0.05)
            self.assertEqual(len(server.jobs), 1)
            job = next(iter(server.jobs.values()))
            self.assertEqual(job["status"], "complete")
            self.assertIn("connection works", job.get("message", "").lower())
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=5)

    def test_thumbnail_wireframe_uses_hidden_release_schema(self):
        create_video(self.root, "Wireframe Test")
        source = self.root / "videos" / "wireframe-test" / ".studio" / "internal" / "release" / "thumbnail-concepts.json"
        write_json(source, {"concepts":[{
            "id":"A", "name":"Tiny player at door", "focal_shape":"left",
            "secondary_shape":"impossible doorway", "headline":"DON'T OPEN IT", "note":"dread"
        }]})
        outputs = generate_thumbnail_wireframes(self.root, "wireframe-test")
        self.assertEqual(len(outputs), 1)
        self.assertIn("DON&#x27;T OPEN IT", outputs[0].read_text(encoding="utf-8"))

    def test_dashboard_is_the_primary_interface(self):
        output = generate_dashboard(self.root)
        text = output.read_text(encoding="utf-8")
        self.assertIn("One active video, one next action", text)
        self.assertIn("What video are you making?", text)
        interactive = dashboard_html(self.root, interactive=True)
        self.assertIn('/action/new', interactive)
        self.assertIn('v0.3.6 · Dashboard control', interactive)
        self.assertIn('Close Studio', interactive)

    def test_dashboard_start_video_keeps_server_reachable(self):
        server = StudioHTTPServer(("127.0.0.1", 0), StudioHandler, self.root)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address
            connection = http.client.HTTPConnection(host, port, timeout=5)
            payload = "title=HTTP+Start+Test"
            connection.request(
                "POST", "/action/new", body=payload,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Content-Length": str(len(payload)),
                },
            )
            response = connection.getresponse()
            body = response.read().decode("utf-8")
            self.assertIn(response.status, {200, 303})
            self.assertIn("Started http-start-test", body)
            connection.close()

            connection = http.client.HTTPConnection(host, port, timeout=5)
            connection.request("GET", "/health")
            health = connection.getresponse()
            self.assertEqual(health.status, 200)
            self.assertEqual(health.read(), b"ok")
            connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_all_dashboard_pages_render_after_video_creation(self):
        create_video(self.root, "Dashboard Pages")
        for page in ["home", "workspace", "media", "release", "operations", "channel", "settings", "diagnostics"]:
            text = render_page(self.root, page)
            self.assertIn("Minecraft Narrative Studio", text, page)
            self.assertNotIn("Traceback (most recent call last)", text, page)

    def test_dashboard_renders_only_requested_page(self):
        create_video(self.root, "Lazy Dashboard")
        with patch("mcstudio.dashboard.media_page", side_effect=AssertionError("unrequested page rendered")):
            text = render_page(self.root, "home")
        self.assertIn("Minecraft Narrative Studio", text)

    def test_get_render_failure_does_not_stop_server(self):
        server = StudioHTTPServer(("127.0.0.1", 0), StudioHandler, self.root)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        try:
            with patch("mcstudio.server.render_page", side_effect=RuntimeError("simulated page failure")):
                connection = http.client.HTTPConnection(host, port, timeout=5)
                connection.request("GET", "/?page=home")
                response = connection.getresponse()
                self.assertEqual(response.status, 500)
                self.assertIn("server is still running", response.read().decode("utf-8"))
                connection.close()

            connection = http.client.HTTPConnection(host, port, timeout=5)
            connection.request("GET", "/health")
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read(), b"ok")
            connection.close()
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=5)

    def test_dashboard_can_save_document_and_apply_imported_proposal(self):
        server = StudioHTTPServer(("127.0.0.1", 0), StudioHandler, self.root)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address

        def post(path: str, fields: dict[str, str]) -> tuple[int, str]:
            payload = urlencode(fields)
            connection = http.client.HTTPConnection(host, port, timeout=5)
            connection.request("POST", path, body=payload, headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Content-Length": str(len(payload)),
            })
            response = connection.getresponse()
            body = response.read().decode("utf-8")
            connection.close()
            return response.status, body

        try:
            status, _ = post("/action/new", {"title": "Browser Orchestration"})
            self.assertIn(status, {200, 303})
            document = "# Direction\n\n" + ("A complete browser-edited direction with promise, causality, Minecraft relevance and scope. " * 15)
            status, body = post("/action/save-document", {
                "slug": "browser-orchestration",
                "path": "01-direction/direction.md",
                "content": document,
            })
            self.assertIn(status, {200, 303})
            self.assertIn("Saved", body)
            saved = self.root / "videos/browser-orchestration/01-direction/direction.md"
            self.assertEqual(saved.read_text(encoding="utf-8"), document)

            score = {
                "premise":"A sealed archive changes when its owner returns.",
                "viewer_promise":"A contained mystery resolved through Minecraft rules.",
                "expected_pleasure":"Discovery, dread and a consequential choice.",
                "hook":"A door appears where no door was built.",
                "dramatic_engine":"Each investigation unloads another safe room.",
                "thematic_question":"What does safety cost when memory is editable?",
                "minecraft_causality":"Chunks, redstone and inventory rules cause the plot.",
                "climactic_choice":"Preserve the archive or unload it permanently.",
                "ending":"The archive is unloaded and the base survives.",
                "final_state":"Safety remains but certainty is gone.",
                "scope":"small","score":88,"decision":"approve","research_mode":"none",
                "research_reason":"Original fiction without external factual claims."
            }
            proposal = json.dumps({
                "summary":"Complete direction and scorecard",
                "document": document,
                "files":{".studio/internal/direction/idea-score.json":json.dumps(score)},
                "questions":[],"warnings":[]
            })
            status, body = post("/action/import-proposal", {"slug":"browser-orchestration", "proposal":proposal})
            self.assertIn(status, {200, 303})
            self.assertIn("Proposal imported", body)
            proposal_files = list((self.root / "videos/browser-orchestration/.studio/proposals").glob("*.json"))
            self.assertEqual(len(proposal_files), 1)
            proposal_id = json.loads(proposal_files[0].read_text(encoding="utf-8"))["id"]
            status, body = post("/action/apply-proposal", {"slug":"browser-orchestration", "proposal_id":proposal_id})
            self.assertIn(status, {200, 303})
            self.assertIn("Applied proposal", body)
            internal = self.root / "videos/browser-orchestration/.studio/internal/direction/idea-score.json"
            self.assertEqual(json.loads(internal.read_text(encoding="utf-8"))["score"], 88)
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=5)

    def test_pending_proposal_can_be_edited_saved_and_accepted_from_dashboard(self):
        create_video(self.root, "Editable Proposal")
        server = StudioHTTPServer(("127.0.0.1", 0), StudioHandler, self.root)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address

        def post(path: str, fields: dict[str, str]) -> tuple[int, str]:
            payload = urlencode(fields)
            connection = http.client.HTTPConnection(host, port, timeout=5)
            connection.request("POST", path, body=payload, headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Content-Length": str(len(payload)),
            })
            response = connection.getresponse()
            body = response.read().decode("utf-8")
            connection.close()
            return response.status, body

        try:
            original = "# Direction\n\n" + ("Original assistant proposal with enough detail for safe validation. " * 8)
            imported = json.dumps({
                "summary": "Editable direction",
                "document": original,
                "files": {},
                "questions": [],
                "warnings": [],
            })
            status, body = post("/action/import-proposal", {
                "slug": "editable-proposal",
                "proposal": imported,
            })
            self.assertEqual(status, 200)
            self.assertIn("Proposal imported", body)
            proposal_path = next((self.root / "videos/editable-proposal/.studio/proposals").glob("*.json"))
            proposal_id = json.loads(proposal_path.read_text(encoding="utf-8"))["id"]

            edited = "# Direction\n\n" + ("Human-edited proposal saved in the dashboard before acceptance. " * 8)
            status, body = post("/action/save-proposal", {
                "slug": "editable-proposal",
                "proposal_id": proposal_id,
                "document": edited,
            })
            self.assertEqual(status, 200)
            self.assertIn("Proposal edits saved", body)
            saved_proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
            self.assertEqual(saved_proposal["document"], edited)
            self.assertEqual(saved_proposal["status"], "pending")
            self.assertEqual(saved_proposal["manual_edit_count"], 1)
            revisions = list((proposal_path.parent / "revisions" / proposal_id).glob("*.json"))
            self.assertEqual(len(revisions), 1)

            final_edit = "# Direction\n\n" + ("Final edited version accepted directly from the proposal editor. " * 8)
            status, body = post("/action/apply-edited-proposal", {
                "slug": "editable-proposal",
                "proposal_id": proposal_id,
                "document": final_edit,
            })
            self.assertEqual(status, 200)
            self.assertIn("Accepted edited proposal", body)
            document_path = self.root / "videos/editable-proposal/01-direction/direction.md"
            self.assertEqual(document_path.read_text(encoding="utf-8"), final_edit)
            applied = json.loads(proposal_path.read_text(encoding="utf-8"))
            self.assertEqual(applied["status"], "applied")
            self.assertEqual(applied["manual_edit_count"], 2)
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=5)

    def test_status_badges_do_not_collapse_and_live_terminal_is_default(self):
        css_source = (SOURCE_ROOT / "mcstudio/dashboard.py").read_text(encoding="utf-8")
        self.assertIn("min-width:max-content", css_source)
        self.assertIn("flex:0 0 auto", css_source)
        settings_source = (SOURCE_ROOT / "mcstudio/assistant.py").read_text(encoding="utf-8")
        self.assertIn('"visible_runner_terminal": True', settings_source)
        self.assertIn('"runner_terminal_host": "windows_terminal"', settings_source)
        self.assertIn('"codex_full_output": True', settings_source)
        dashboard_source = (SOURCE_ROOT / "mcstudio/dashboard.py").read_text(encoding="utf-8")
        self.assertIn('name="codex_full_output"', dashboard_source)
        self.assertIn("Show the full native Codex output", dashboard_source)

    def test_elevated_runner_script_uses_admin_powershell_handshake(self):
        work = self.root / "elevated-script-test"
        work.mkdir()
        script = work / "runner.ps1"
        _write_elevated_runner_script(
            script_path=script,
            command=["codex.cmd", "exec", "-"],
            cwd=self.root,
            timeout=123,
            input_path=work / "prompt.txt",
            stdout_path=work / "stdout.log",
            stderr_path=work / "stderr.log",
            log_path=work / "runner.log",
            started_path=work / "started",
            done_path=work / "done",
            exit_path=work / "exit",
            session_path=work / "session-id.txt",
            partial_path=work / "partial-response.txt",
            title="Studio Assistant test",
            env=None,
            json_event_stream=True,
        )
        text = script.read_text(encoding="utf-8-sig")
        self.assertIn("$PSVersionTable.PSVersion", text)
        self.assertIn("RedirectStandardInput", text)
        self.assertIn("Set-Content -LiteralPath $donePath", text)
        self.assertLess(text.index("Set-Location -LiteralPath (Split-Path -Parent $logPath)"), text.index("Set-Content -LiteralPath $donePath"))
        self.assertIn("Read-Host", text)
        runner_source = (SOURCE_ROOT / "mcstudio/runners.py").read_text(encoding="utf-8")
        self.assertIn("-Verb RunAs", runner_source)
        self.assertIn("PowerShell 7.6.3 or newer", runner_source)
        self.assertIn("terminal was closed before the CLI finished", runner_source)
        self.assertIn("Windows Terminal", runner_source)
        self.assertIn("terminal_start_dir = (log_root or cwd).resolve()", runner_source)
        self.assertIn("_cleanup_temp_workspace(temp_dir)", runner_source)
        self.assertIn("Show-CodexEvent", text)
        self.assertIn("thread.started", text)
        self.assertIn("Live Codex events", text)
        self.assertNotIn("Still working", text)
        self.assertNotIn("No intermediate model output is expected", text)

    def test_background_failure_clears_running_status(self):
        server = StudioHTTPServer(("127.0.0.1", 0), StudioHandler, self.root)
        try:
            def fail():
                raise StudioError("simulated elevated terminal closure")
            job_id = server.start_job("Failure test", fail, dedupe_key="failure-test")
            deadline = time.time() + 3
            while time.time() < deadline and server.jobs[job_id]["status"] == "running":
                time.sleep(0.02)
            self.assertEqual(server.jobs[job_id]["status"], "failed")
            self.assertIn("terminal closure", server.jobs[job_id]["error"])
        finally:
            server.server_close()

    def test_no_terminal_launcher_is_in_release(self):
        self.assertTrue((SOURCE_ROOT / "START-STUDIO.vbs").is_file())
        powershell = (SOURCE_ROOT / "START-STUDIO.ps1").read_text(encoding="utf-8")
        self.assertIn("-m mcstudio studio", powershell)
        self.assertIn("launcher.log", powershell)

    def test_dashboard_allows_dry_run_but_blocks_unapproved_real_upload(self):
        video_dir = create_video(self.root, "Release Safety")
        master = video_dir / "assets/masters/master.mp4"
        master.parent.mkdir(parents=True, exist_ok=True)
        master.write_bytes(b"m" * 2048)
        loaded_dir, project = load_project(self.root, "release-safety")
        project.setdefault("media", {})["master_file"] = master.relative_to(video_dir).as_posix()
        save_project(loaded_dir, project)

        server = StudioHTTPServer(("127.0.0.1", 0), StudioHandler, self.root)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address

        def post(fields: dict[str, str]) -> tuple[int, str]:
            payload = urlencode(fields)
            connection = http.client.HTTPConnection(host, port, timeout=5)
            connection.request("POST", "/action/youtube", body=payload, headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Content-Length": str(len(payload)),
            })
            response = connection.getresponse(); body = response.read().decode("utf-8"); connection.close()
            return response.status, body

        try:
            status, body = post({"slug":"release-safety", "privacy":"private"})
            self.assertIn(status, {200, 303})
            if status == 200:
                self.assertIn("Uploader started", body)
            status, body = post({"slug":"release-safety", "privacy":"private", "execute":"yes"})
            self.assertEqual(status, 400)
            self.assertIn("Publication approval", body)
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=5)

    def test_youtube_request_defaults_and_schedule_rule(self):
        body = build_request({"title":"Test","default_language":"en-GB"}, "private")
        self.assertEqual(body["snippet"]["defaultLanguage"], "en-GB")
        self.assertFalse(body["status"]["selfDeclaredMadeForKids"])
        with self.assertRaises(StudioError):
            build_request({"title":"Test"}, "public", "2026-08-01T15:00:00Z")

    def test_uploader_is_dry_run_without_execute(self):
        video = self.root / "master.mp4"
        video.write_bytes(b"test")
        metadata = self.root / "metadata.json"
        metadata.write_text(json.dumps({"title":"Test","description":"Description"}), encoding="utf-8")
        result = upload(video, metadata, self.root/"missing.json", self.root/"token.json", "private", None, False)
        self.assertFalse(result["execute"])
        self.assertEqual(result["request_body"]["status"]["privacyStatus"], "private")

    def test_analytics_import_and_delta(self):
        source = self.root / "analytics.csv"
        with source.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["Video ID","Video title","Views","Watch time (hours)","Impressions","Impressions click-through rate (%)","Subscribers"])
            writer.writeheader(); writer.writerow({"Video ID":"abc","Video title":"Pilot","Views":"100","Watch time (hours)":"10","Impressions":"1000","Impressions click-through rate (%)":"5%","Subscribers":"3"})
        import_youtube_csv(self.root, source, "pilot", "abc")
        source.write_text(source.read_text(encoding="utf-8").replace("100,10,1000,5%,3", "150,15,1400,6%,5"), encoding="utf-8")
        import_youtube_csv(self.root, source, "pilot", "abc")
        report = report_for_slug(self.root, "pilot")
        self.assertEqual(report["snapshots"], 2)
        self.assertEqual(report["deltas"]["views"], 50.0)


if __name__ == "__main__":
    unittest.main()
