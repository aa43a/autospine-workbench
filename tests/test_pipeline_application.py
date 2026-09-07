"""Project-driven pipeline integration over real reviewed P2 fixtures."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from tests import test_rig_commands as rig_commands
from tests.png_helpers import write_rgba
from autospine_workbench.automation.pipeline_application import PipelineApplication
from autospine_workbench.automation.pipeline_run import PipelineRunError
from autospine_workbench.automation.project_snapshot import SnapshotError, observe_project
from autospine_workbench.automation.region_preview import verify_region_preview
from autospine_workbench.project_store import ProjectStore


class PipelineApplicationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = rig_commands.RigCommandIntegrationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.store = self.fixture.fixture.store()
        self.app = PipelineApplication(self.store)
        self.project_id = "fixture-project"

    def unreviewed_app(self):
        return PipelineApplication(ProjectStore(
            self.fixture.fixture.workspace,
            state_root=self.fixture.fixture.state.parent / "unreviewed-state",
            measure_composite_quality=False,
        ))

    def pending_run(self):
        with observe_project(self.store, self.project_id) as snapshot:
            return self.app.runs.create(self.project_id, "production_review", snapshot.source_addresses)

    def test_ready_project_builds_exact_preview_and_reuses_without_execution(self):
        first = self.app.preview(self.project_id)
        self.assertEqual(first["status"], "succeeded", first)
        self.assertEqual([row["status"] for row in first["steps"]], ["succeeded"] * 3)
        self.assertEqual(first["authority"], "none")
        with patch.object(self.app, "_execute_step", side_effect=AssertionError("must reuse")):
            self.assertEqual(self.app.preview(self.project_id), first)
        preview = verify_region_preview(
            self.store.state_root, self.project_id, first["steps"][2]["outputs"]["bundle_sha256"],
        )
        self.assertEqual(json.loads(preview.files["qa.json"])["runtime_status"], "not_run")
        self.assertNotIn(str(self.store.state_root), json.dumps(first))

    def test_reviewed_project_can_build_preview_under_draft_profile(self):
        result = self.app.preview(self.project_id, "draft_auto")
        self.assertEqual(result["status"], "succeeded", result)
        self.assertEqual(self.app.preview(self.project_id, "draft_auto"), result)

    def test_production_stops_before_rig_and_draft_preserves_diagnostic_review(self):
        app = self.unreviewed_app()
        production = app.preview(self.project_id)
        self.assertEqual(production["status"], "needs_review", production)
        self.assertEqual(production["steps"][0]["status"], "succeeded")
        self.assertEqual(production["steps"][1]["reason_code"], "project_review_required")
        self.assertEqual(production["steps"][1]["outputs"], {})
        draft = app.preview(self.project_id, "draft_auto")
        self.assertEqual(draft["status"], "needs_review", draft)
        self.assertEqual(draft["steps"][1]["status"], "succeeded")
        self.assertEqual(draft["steps"][2]["reason_code"], "spine_preview_review_required")
        self.assertEqual(draft["steps"][2]["outputs"], {})

    def test_certification_requires_its_exact_entry_without_any_step_execution(self):
        with patch.object(self.app, "_execute_step", side_effect=AssertionError("must block")):
            run = self.app.preview(self.project_id, "certification_exact")
        self.assertEqual(run["status"], "blocked")
        self.assertEqual(run["steps"][0]["reason_code"], "certification_exact_entry_required")
        self.assertTrue(all(not row["outputs"] for row in run["steps"]))

    def test_successful_preview_tamper_is_never_reused(self):
        run = self.app.preview(self.project_id)
        self.assertEqual(run["status"], "succeeded", run)
        bundle = verify_region_preview(
            self.store.state_root, self.project_id, run["steps"][2]["outputs"]["bundle_sha256"],
        )
        (bundle.path / "skeleton.png").write_bytes(b"corrupted")
        with self.assertRaises(PipelineRunError) as caught:
            self.app.preview(self.project_id)
        self.assertEqual(caught.exception.reason_code, "pipeline_artifact_invalid")

    def test_running_job_requires_resume_then_completes(self):
        pending = self.pending_run()
        running = self.app.runs.append(pending["run_id"], pending["state_sha256"], "start")
        self.assertEqual(self.app.preview(self.project_id), running)
        completed = self.app.preview(self.project_id, resume=True)
        self.assertEqual(completed["status"], "succeeded", completed)
        self.assertEqual(completed["run_id"], running["run_id"])
        self.assertGreater(completed["revision"], running["revision"])

    def test_interrupted_after_rig_resumes_without_rebuilding_completed_steps(self):
        original = self.app._execute_step

        def interrupt(index, snapshot, run):
            if index == 2:
                raise KeyboardInterrupt("simulated process interruption")
            return original(index, snapshot, run)

        with patch.object(self.app, "_execute_step", side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.app.preview(self.project_id)
        interrupted = self.app.preview(self.project_id)
        self.assertEqual(interrupted["status"], "running")
        self.assertEqual([row["status"] for row in interrupted["steps"]],
                         ["succeeded", "succeeded", "running"])
        with patch.object(self.app, "_execute_step", wraps=original) as execute:
            completed = self.app.preview(self.project_id, resume=True)
        self.assertEqual(completed["status"], "succeeded", completed)
        self.assertEqual([call.args[0] for call in execute.call_args_list], [2])
        self.assertEqual(completed["steps"][1]["outputs"], interrupted["steps"][1]["outputs"])

    def test_concurrent_cancel_cannot_be_overwritten_by_completion(self):
        original = self.app._execute_step

        def cancel_during_execute(index, snapshot, run):
            self.app.cancel(run["run_id"], run["state_sha256"])
            return original(index, snapshot, run)

        with patch.object(self.app, "_execute_step", side_effect=cancel_during_execute):
            canceled = self.app.preview(self.project_id)
        self.assertEqual(canceled["status"], "canceled", canceled)
        self.assertEqual(canceled["steps"][0]["outputs"], {})
        self.assertEqual(self.app.runs.load(canceled["run_id"]), canceled)

    def test_source_drift_blocks_original_run_and_never_builds_a_rig(self):
        original = self.app._execute_step
        run_ids = []

        def change_source(index, snapshot, run):
            run_ids.append(run["run_id"])
            result = original(index, snapshot, run)
            write_rgba(self.fixture.fixture.layer_image, [[(41, 90, 160, 220)] * 20 for _ in range(20)])
            return result

        with patch.object(self.app, "_execute_step", side_effect=change_source):
            with self.assertRaises(SnapshotError) as caught:
                self.app.preview(self.project_id)
        self.assertEqual(caught.exception.reason_code, "project_changed_during_snapshot")
        blocked = self.app.runs.load(run_ids[0])
        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(blocked["steps"][0]["reason_code"], "project_changed_during_snapshot")
        self.assertEqual(blocked["steps"][1]["status"], "pending")
        self.assertTrue(all(not step["outputs"] for step in blocked["steps"]))

    def test_cancel_survives_resume_and_stale_revision_cannot_cancel(self):
        pending = self.pending_run()
        running = self.app.runs.append(pending["run_id"], pending["state_sha256"], "start")
        with self.assertRaises(PipelineRunError) as caught:
            self.app.cancel(running["run_id"], pending["state_sha256"])
        self.assertEqual(caught.exception.reason_code, "pipeline_revision_conflict")
        canceled = self.app.cancel(running["run_id"], running["state_sha256"])
        self.assertEqual(canceled["status"], "canceled")
        with patch.object(self.app, "_execute_step", side_effect=AssertionError("must not restart")):
            self.assertEqual(self.app.preview(self.project_id, resume=True), canceled)


if __name__ == "__main__":
    unittest.main()
