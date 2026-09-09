"""Threading and durable HTTP receipts; test doubles confer no Runtime evidence."""

from copy import deepcopy
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import time
from types import SimpleNamespace
import unittest
from zipfile import ZipFile

from autospine_workbench.automation.animated_jobs import AnimatedWebJobs, safe_file
from autospine_workbench.automation.pipeline_run import PipelineRunError
from autospine_workbench.automation.storage_io import canonical_bytes, publish_document


class ApplicationDouble:
    def __init__(self):
        self.entered, self.release = Event(), Event()
        self.release.set()
        self.stale = False

    def preview(self, project_id, expected_resolved_sha256, clip, resume,
                cancel_requested, progress):
        self.entered.set()
        progress({"steps": [{"id": "build-mesh", "status": "running"}]})
        if not self.release.wait(5):
            raise RuntimeError("test timed out")
        return {"schema": "autospine.animated-pipeline-run/v1", "project_id": project_id,
                "authority": "none", "status": "needs_review", "run_id": "run-test",
                "preview_available": True, "clip": clip,
                "sources": {"resolved_project_sha256": expected_resolved_sha256}}

    def verified_files(self, project_id, run):
        if self.stale:
            raise PipelineRunError("project_snapshot_stale")
        return {"skeleton.json": b"{}", "skeleton.atlas": b"atlas", "skeleton.png": b"PNG"}

    def verified_file(self, project_id, run, name):
        files = self.verified_files(project_id, run)
        if name not in files:
            raise PipelineRunError("animated_file_not_found")
        return files[name]


class AnimatedWebJobTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.store = SimpleNamespace(state_root=Path(temporary.name))
        self.application = ApplicationDouble()
        self.manager = AnimatedWebJobs(self.store, application=self.application)
        self.addCleanup(self.manager.close)

    def submit(self):
        return self.manager.submit("character", "a" * 64, "limb_diagnostic")

    def terminal(self, job):
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            result = self.manager.get("character", job["job_id"])
            if result["status"] not in {"pending", "running"}:
                return result
            Event().wait(.01)
        self.fail("job did not finish")

    def test_review_candidate_download_and_restart_revalidate_current(self):
        job = self.submit()
        result = self.terminal(job)
        self.assertEqual(result["status"], "needs_review")
        raw = self.manager.download("character", job["job_id"])
        with ZipFile(BytesIO(raw)) as archive:
            self.assertEqual(archive.namelist(), ["skeleton.atlas", "skeleton.json", "skeleton.png"])
        restarted = AnimatedWebJobs(self.store, application=self.application)
        self.addCleanup(restarted.close)
        self.assertEqual(restarted.get("character", job["job_id"]), result)
        self.assertEqual(restarted.download("character", job["job_id"]), raw)
        self.application.stale = True
        with self.assertRaisesRegex(PipelineRunError, "project_snapshot_stale"):
            restarted.download("character", job["job_id"])

    def test_active_dedup_progress_cancel_and_cross_project(self):
        self.application.release.clear()
        try:
            job = self.submit()
            self.assertTrue(self.application.entered.wait(3))
            self.assertEqual(self.submit()["job_id"], job["job_id"])
            self.assertEqual(self.manager.get("character", job["job_id"])["progress"]["steps"][0]["id"], "build-mesh")
            with self.assertRaises(PipelineRunError):
                self.manager.cancel("other", job["job_id"])
            self.assertTrue(self.manager.cancel("character", job["job_id"])["cancel_requested"])
        finally:
            self.application.release.set()
        self.assertEqual(self.terminal(job)["status"], "canceled")
        with self.assertRaises(PipelineRunError):
            self.manager.download("character", job["job_id"])

    def test_interrupted_request_and_forged_result_fail_closed(self):
        job_id = "job-" + "f" * 32
        path = self.manager._path(job_id, create=True)
        request = dict(project_id="character", expected_resolved_sha256="a" * 64,
                       clip="limb_diagnostic", resume=True)
        publish_document(path / "request.json", request, staging=path / "staging")
        self.assertEqual(self.manager.get("character", job_id)["reason_code"], "pipeline_interrupted")
        job = self.submit()
        result = deepcopy(self.terminal(job))
        result["run"]["sources"]["resolved_project_sha256"] = "b" * 64
        (self.manager._path(job["job_id"]) / "result.json").write_bytes(canonical_bytes(result))
        with self.assertRaises(PipelineRunError):
            self.manager.get("character", job["job_id"])

    def test_file_allowlist_rejects_traversal_and_executable_content(self):
        for name in ["../a.png", "/a.png", "a\\b.png", "a//b.png", "a/./b.png", "x.html", "x.js", "C:/a.png"]:
            with self.subTest(name=name), self.assertRaises(PipelineRunError):
                safe_file(name)
        self.assertEqual(safe_file("editor/images/layer-001.png"), "editor/images/layer-001.png")

    def test_receipt_cannot_substitute_another_clip_or_export_target(self):
        job = self.submit()
        original = self.terminal(job)
        path = self.manager._path(job["job_id"]) / "result.json"
        for kind in ("clip", "target"):
            forged = deepcopy(original)
            if kind == "clip":
                forged["run"]["clip"] = "another-valid-clip"
            else:
                forged["target_version"] = "4.2"
            path.write_bytes(canonical_bytes(forged))
            with self.subTest(kind=kind), self.assertRaises(PipelineRunError):
                self.manager.get("character", job["job_id"])


if __name__ == "__main__":
    unittest.main()
