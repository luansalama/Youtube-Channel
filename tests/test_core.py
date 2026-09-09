from __future__ import annotations

import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from mcstudio.core import (
    StudioError,
    active_project,
    approve_gate,
    business_entry,
    business_summary,
    continue_workflow,
    create_video,
    evaluate_stage,
    maintain_repository,
    pause_video,
    phase_progress,
    read_json,
    resume_video,
    stage_evidence_hashes,
    validate_repository,
    workflow_status,
    write_json,
)
from mcstudio.story import audit_revision_passes

SOURCE_ROOT = Path(__file__).resolve().parents[1]


class RepoCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for rel in ["studio", "templates", ".agents", ".codex"]:
            shutil.copytree(SOURCE_ROOT / rel, self.root / rel)
        shutil.copy2(SOURCE_ROOT / "AGENTS.md", self.root / "AGENTS.md")
        shutil.copy2(SOURCE_ROOT / "opencode.json", self.root / "opencode.json")
        (self.root / "videos").mkdir()
        maintain_repository(self.root)

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def complete_direction(self, slug: str, research_mode: str = "none") -> None:
        video = self.root / "videos" / slug
        text = "\n".join([
            "# Direction",
            "The viewer is promised a contained Minecraft mystery with a fair answer and an emotional reversal.",
            "A builder finds an archive that changes a room before the player enters it, forcing controlled experiments.",
            "Chunk loading and redstone memory cause the investigation, remove safe routes, and enable the climax.",
            "The emotional movement is curiosity, controlled dread, recognition, and uncertain relief.",
            "The climax requires the player to destroy certainty to preserve responsibility for the final choice.",
            "The smallest worthwhile production uses one hero chamber, one corridor kit, two lighting states, and one performer.",
            "Research is not needed because this is original fiction with no factual, cultural, or technical public claim.",
            "The selected direction is the archive mystery; broader lore and exterior builds are rejected to protect scope.",
        ]) * 3
        (video / "01-direction" / "direction.md").write_text(text, encoding="utf-8")
        write_json(video / ".studio" / "internal" / "direction" / "idea-score.json", {
            "premise": "A predictive archive changes a room before entry.",
            "viewer_promise": "A fair contained Minecraft mystery.",
            "expected_pleasure": "Curiosity, dread, and earned reinterpretation.",
            "hook": "The room changes before the player enters.",
            "dramatic_engine": "Every controlled test teaches the archive and closes an option.",
            "thematic_question": "Does prediction remove responsibility?",
            "minecraft_causality": "Chunk loading and redstone memory drive the plot.",
            "climactic_choice": "Destroy certainty to preserve agency.",
            "ending": "An unpredicted torch flickers after the archive is unloaded.",
            "final_state": "The base survives but certainty is lost.",
            "scope": "small",
            "score": 85,
            "decision": "approve for story development",
            "research_mode": research_mode,
            "research_reason": "Original fiction needs only the selected level of research for accuracy and originality control.",
        })

    def fake_upstream_approvals(self, slug: str, through: str) -> None:
        video = self.root / "videos" / slug
        project = read_json(video / "project.json")
        stages = read_json(self.root / "studio" / "stages.json")
        names = [stage["name"] for stage in stages]
        for stage in stages[: names.index(through)]:
            gate = stage.get("approval_gate")
            if gate:
                project.setdefault("approvals", {})[gate] = {
                    "by": "Luan",
                    "at": "2026-07-15T00:00:00+00:00",
                    "note": "test",
                    "evidence": stage_evidence_hashes(video, stage),
                }
        project["stage"] = through
        project["state"] = "active"
        write_json(video / "project.json", project)


class WorkflowTests(RepoCase):
    def test_repository_structure_and_defaults(self):
        results = validate_repository(self.root)
        self.assertTrue(all(item.ok for item in results))
        stages = read_json(self.root / "studio" / "stages.json")
        self.assertEqual([item["name"] for item in stages], ["direction", "story", "script", "production", "edit", "release", "learn"])
        self.assertEqual(sum(bool(item.get("approval_gate")) for item in stages), 5)
        studio = read_json(self.root / "studio" / "studio.json")
        self.assertEqual(studio["business"]["base_currency"], "BRL")
        self.assertEqual(studio["business"]["commercial_currency"], "BRL")
        self.assertEqual(studio["automation"]["max_parallel_agents"], 1)

    def test_new_video_has_seven_human_documents(self):
        video = create_video(self.root, "The Archive Below")
        visible = sorted(path.relative_to(video).as_posix() for path in video.glob("[0-9][0-9]-*/*.md"))
        self.assertEqual(len(visible), 7)
        self.assertEqual(read_json(video / "project.json")["stage"], "direction")
        self.assertEqual(active_project(self.root)["slug"], "the-archive-below")
        self.assertTrue((video / ".studio" / "internal" / "story" / "causal-spine.csv").is_file())

    def test_maintenance_quarantines_incomplete_v030_project(self):
        orphan = self.root / "videos" / "crashed-title"
        orphan.mkdir(parents=True)
        (orphan / "partial.txt").write_text("partial", encoding="utf-8")
        results = maintain_repository(self.root)
        self.assertFalse(orphan.exists())
        recovered = list((self.root / "exports" / "recovery" / "incomplete-video-projects").glob("crashed-title-*"))
        self.assertEqual(len(recovered), 1)
        self.assertEqual((recovered[0] / "partial.txt").read_text(encoding="utf-8"), "partial")
        self.assertTrue(any(item.label == "incomplete project recovered" for item in results))
        created = create_video(self.root, "Crashed Title")
        self.assertEqual(created.name, "crashed-title")

    def test_only_one_video_can_be_active(self):
        create_video(self.root, "First")
        with self.assertRaises(StudioError):
            create_video(self.root, "Second")
        pause_video(self.root, "first")
        create_video(self.root, "Second")
        with self.assertRaises(StudioError):
            resume_video(self.root, "first")

    def test_direction_none_research_can_be_approved_and_continued(self):
        create_video(self.root, "Direction Test")
        self.complete_direction("direction-test", "none")
        checks = evaluate_stage(self.root, "direction-test", include_approval=False)
        self.assertTrue(all(item.ok for item in checks))
        approve_gate(self.root, "direction-test", "direction_lock", "Luan")
        result = continue_workflow(self.root)
        self.assertEqual(result["project"]["stage"], "story")
        self.assertEqual(result["status"], "work_needed")

    def test_full_research_is_conditional(self):
        create_video(self.root, "Research Test")
        self.complete_direction("research-test", "full")
        checks = evaluate_stage(self.root, "research-test", include_approval=False)
        failed = {item.label for item in checks if not item.ok}
        self.assertIn("research source ledger", failed)
        self.assertIn("claims and evidence map", failed)
        self.assertIn("inspiration/originality review", failed)

    def test_approval_fingerprint_drift_remains_visible(self):
        create_video(self.root, "Drift Test")
        self.complete_direction("drift-test")
        approve_gate(self.root, "drift-test", "direction_lock", "Luan")
        continue_workflow(self.root)
        path = self.root / "videos" / "drift-test" / "01-direction" / "direction.md"
        path.write_text(path.read_text(encoding="utf-8") + "\nChanged after lock.\n", encoding="utf-8")
        status = workflow_status(self.root)
        self.assertTrue(any("approved evidence changed" in item.detail for item in status["blockers"]))

    def test_adaptive_revision_requires_core_not_every_optional_pass(self):
        video = create_video(self.root, "Revision Test")
        doctrine = read_json(self.root / "studio" / "writing-doctrine.json")
        passes = []
        for pass_id in doctrine["audit"]["core_revision_pass_ids"]:
            passes.append({"id": pass_id, "required": True, "status": "complete", "evidence": f"Reviewed {pass_id} against the locked story.", "decision": "No blocker remains."})
        for pass_id in doctrine["audit"]["optional_revision_pass_ids"]:
            passes.append({"id": pass_id, "required": False, "status": "not_required", "evidence": f"This script does not need a separate {pass_id} pass.", "decision": ""})
        write_json(video / ".studio" / "internal" / "script" / "revision-pass-status.json", {"schema_version": 2, "draft_id": "draft-01", "passes": passes})
        findings = audit_revision_passes(video, doctrine)
        self.assertTrue(all(item.ok for item in findings))

    def test_safe_production_phase_auto_advances(self):
        video = create_video(self.root, "Production Test")
        self.fake_upstream_approvals("production-test", "production")
        (video / "04-production" / "production-plan.md").write_text("Complete minimal production plan and capture record. " * 40, encoding="utf-8")
        (video / ".studio/internal/production/storyboard-plan.md").write_text("Literal spatial storyboard with camera, blocking, lighting, transition and continuity. " * 30, encoding="utf-8")
        (video / ".studio/internal/production/technical-research.md").write_text("Sourced toolchain research, version boundaries, deterministic controls and integrated test procedure. " * 30, encoding="utf-8")
        (video / ".studio/internal/production/location-plan.md").write_text("Modular location plan, camera-safe geometry, build order, perceived scale and Blender split. " * 15, encoding="utf-8")
        (video / ".studio/internal/production/build-budget.md").write_text("Solo hours, BRL approval boundary, reuse value and must should could cut lines. " * 10, encoding="utf-8")
        self.write_csv(video / ".studio/internal/production/toolchain-matrix.csv", ["component_id","category","candidate","exact_version","minecraft_version","loader","purpose","official_source","licence","compatibility_status","decision","fallback","notes"], [
            {"component_id":f"TC{i}","category":"tool","candidate":f"Tool {i}","exact_version":"1","minecraft_version":"1.20.1","loader":"Fabric","purpose":"test","official_source":"official","licence":"verified","compatibility_status":"tested","decision":"use","fallback":"plate","notes":""} for i in range(1,9)
        ])
        self.write_csv(video / ".studio/internal/production/scene-implementation-matrix.csv", ["scene_id","script_requirement","preferred_method","minecraft_version","tool_or_mod","deterministic_control","camera_method","vfx_method","fallback","test_id","evidence_status","notes"], [
            {"scene_id":str(i),"script_requirement":"beat","preferred_method":"live","minecraft_version":"1.20.1","tool_or_mod":"tool","deterministic_control":"reset","camera_method":"path","vfx_method":"plate","fallback":"composite","test_id":f"T{i}","evidence_status":"verified","notes":""} for i in range(1,14)
        ])
        self.write_csv(video / ".studio/internal/production/test-matrix.csv", ["test_id","capability","scene_ids","stack","procedure","pass_criteria","failure_evidence","fallback","status","notes"], [
            {"test_id":f"T{i}","capability":"capability","scene_ids":str(i),"stack":"stack","procedure":"procedure","pass_criteria":"pass","failure_evidence":"log","fallback":"plate","status":"passed","notes":""} for i in range(1,9)
        ])
        self.write_csv(video / ".studio/internal/production/storyboard-panels.csv", ["panel_id","scene_id","shot_id","order","frame_description","composition","camera","subject_blocking","environment","lighting","movement","transition","audio","continuity","generation_reference","status"], [
            {"panel_id":f"P{i}","scene_id":str(((i-1)//2)+1),"shot_id":f"SH{i}","order":str(i),"frame_description":"frame","composition":"thirds","camera":"fixed","subject_blocking":"mark","environment":"set","lighting":"key","movement":"left","transition":"cut","audio":"cue","continuity":"matched","generation_reference":"none","status":"approved"} for i in range(1,27)
        ])
        self.write_csv(video / ".studio/internal/production/camera-paths.csv", ["path_id","shot_id","tool","duration_seconds","fps","start_state","end_state","notes"], [
            {"path_id":f"CP{i}","shot_id":f"SH{i}","tool":"replay","duration_seconds":"5","fps":"24","start_state":"A","end_state":"B","notes":""} for i in range(1,14)
        ])
        self.write_csv(video / ".studio/internal/production/shot-list.csv", ["shot_id","beat","location","framing","camera_move","action","dialogue_or_vo","duration_seconds","capture_method","assets","status"], [
            {"shot_id":f"SH{i}","beat":str(i),"location":"archive","framing":"wide","camera_move":"locked","action":"test","dialogue_or_vo":"narration","duration_seconds":"5","capture_method":"Minecraft","assets":"room","status":"captured"} for i in range(1,7)
        ])
        self.write_csv(video / ".studio/internal/production/asset-register.csv", ["asset_id","asset","type","source_or_owner","licence","version","needed_for","status","notes"], [{"asset_id":"A1","asset":"Archive room","type":"build","source_or_owner":"Luan","licence":"owned","version":"1","needed_for":"all scenes","status":"ready","notes":""}])
        self.write_csv(video / ".studio/internal/production/location-cards.csv", ["location_id","name","story_function","hero_angle","modular_elements","lighting_state","completion","notes"], [{"location_id":"L1","name":"Archive","story_function":"hero set","hero_angle":"door","modular_elements":"corridor","lighting_state":"two states","completion":"complete","notes":""}])
        self.write_csv(video / ".studio/internal/production/capture-log.csv", ["shot_id","take","file","captured_at","technical_ok","performance_ok","selected","notes"], [{"shot_id":"SH1","take":"1","file":"SH1_T01.mov","captured_at":"2026-07-15","technical_ok":"yes","performance_ok":"yes","selected":"yes","notes":""}])
        result = continue_workflow(self.root)
        self.assertIn("edit", result["advanced"])
        self.assertEqual(result["project"]["stage"], "edit")

    def test_learn_completion_releases_active_slot(self):
        video = create_video(self.root, "Learn Test")
        self.fake_upstream_approvals("learn-test", "learn")
        (video / "07-learn" / "lessons.md").write_text("Observed lesson with evidence and a concrete next-video decision. " * 20, encoding="utf-8")
        result = continue_workflow(self.root)
        self.assertEqual(result["status"], "completed")
        self.assertIsNone(active_project(self.root))
        self.assertEqual(phase_progress(self.root, result["project"])["percent"], 100)

    def test_business_preserves_foreign_entries_but_defaults_are_brl(self):
        business_entry(self.root, {"date":"2026-07-15","type":"expense","amount":"100","currency":"BRL","category":"asset","video":"","counterparty":"","note":""})
        business_entry(self.root, {"date":"2026-07-15","type":"revenue","amount":"50","currency":"GBP","category":"sponsor","video":"","counterparty":"","note":""})
        summary = business_summary(self.root)
        self.assertEqual(summary["BRL"]["profit"], -100.0)
        self.assertEqual(summary["GBP"]["profit"], 50.0)

    def test_maintenance_migrates_old_project_to_paused(self):
        path = self.root / "videos" / "old"
        path.mkdir()
        write_json(path / "project.json", {"schema_version": 1, "slug": "old", "title": "Old", "stage": "outline", "approvals": {}, "history": []})
        maintain_repository(self.root)
        project = read_json(path / "project.json")
        self.assertEqual(project["schema_version"], 2)
        self.assertEqual(project["stage"], "story")
        self.assertEqual(project["state"], "paused")


if __name__ == "__main__":
    unittest.main()
