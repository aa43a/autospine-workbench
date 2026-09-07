"""Real setup jobs with bounded concurrency and interruption semantics."""

import json
import hashlib
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from threading import Event
import time
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZIP_STORED

from tests import test_rig_commands as fixtures
from autospine_workbench.automation.pipeline_run import PipelineRunError
from autospine_workbench.automation.storage_io import canonical_bytes, publish_document
from autospine_workbench.automation.web_jobs import PipelineWebJobs
from autospine_workbench.automation.web_download import download_job
from autospine_workbench.automation.pipeline_run import seal
from autospine_workbench.automation.region_preview_store import publish_preview


class PipelineWebJobTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.RigCommandIntegrationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.store = self.fixture.fixture.store()
        self.manager = PipelineWebJobs(self.store)
        self.addCleanup(self.manager.close)
        self.project = "fixture-project"
        self.sha = self.store.get_project(self.project)["resolved"]["sha256"]

    def submit(self, sha=None):
        return self.manager.submit(self.project, "production_review", sha or self.sha)

    def wait(self, job):
        end = time.monotonic() + 15
        while time.monotonic() < end:
            result = self.manager.get(self.project, job["job_id"])
            if result["status"] not in {"pending", "running"}:
                return result
            time.sleep(.01)
        self.fail("job did not finish")

    def test_success_download_restart_and_exact_journal_binding(self):
        job = self.submit()
        result = self.wait(job)
        self.assertEqual(result["status"], "succeeded", result)
        import jsonschema
        schema = json.loads((Path(__file__).resolve().parents[1] /
                             "schemas/pipeline-web-job-v1.schema.json").read_text())
        jsonschema.Draft202012Validator(schema).validate(result)
        data = download_job(self.manager, self.project, job["job_id"])
        self.assertTrue(data.startswith(b"PK"))
        restarted = PipelineWebJobs(self.store)
        self.addCleanup(restarted.close)
        self.assertEqual(restarted.get(self.project, job["job_id"]), result)
        self.assertEqual(download_job(restarted, self.project, job["job_id"]), data)
        path = self.manager._path(job["job_id"]) / "result.json"
        forged = json.loads(path.read_text())
        forged["run"]["source_addresses"]["resolved_project_sha256"] = "a" * 64
        path.write_bytes(canonical_bytes(forged))
        with self.assertRaises(PipelineRunError):
            restarted.get(self.project, job["job_id"])

    def test_submission_is_nonblocking_deduplicated_and_cancel_wins(self):
        entered, release = Event(), Event()
        original = self.manager.application._execute_step

        def hold(*args):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("test release timed out")
            return original(*args)

        with patch.object(self.manager.application, "_execute_step", side_effect=hold):
            try:
                job = self.submit()
                self.assertTrue(entered.wait(5))
                self.assertEqual(self.submit()["job_id"], job["job_id"])
                cancel = self.manager.cancel(self.project, job["job_id"])
                self.assertTrue(cancel["cancel_requested"])
            finally:
                release.set()
            self.assertEqual(self.wait(job)["status"], "canceled")
        with self.assertRaises(PipelineRunError):
            download_job(self.manager, self.project, job["job_id"])

    def test_stale_project_blocks_without_building(self):
        job = self.submit("a" * 64)
        result = self.wait(job)
        self.assertEqual(result["reason_code"], "project_changed_during_snapshot")
        self.assertFalse((self.store.state_root / "jobs/pipeline-runs-v1").exists())

    def test_interrupted_request_is_not_automatically_executed_after_restart(self):
        job_id = "job-" + "a" * 32
        path = self.manager._path(job_id, create=True)
        request = {"project_id": self.project, "profile": "production_review",
                   "expected_resolved_sha256": self.sha, "resume": True}
        publish_document(path / "request.json", request, staging=path / "staging")
        result = self.manager.get(self.project, job_id)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason_code"], "pipeline_interrupted")
        self.assertFalse(self.manager._active)

    def test_cross_project_and_corrupted_zip_fail_closed(self):
        job = self.submit()
        self.assertEqual(self.wait(job)["status"], "succeeded")
        with self.assertRaises(PipelineRunError):
            self.manager.get("another-project", job["job_id"])
        path = self.manager._path(job["job_id"]) / "preview.zip"
        path.write_bytes(b"untrusted")
        with self.assertRaises(PipelineRunError):
            download_job(self.manager, self.project, job["job_id"])

    def test_resealed_journal_zip_and_preview_cannot_forge_compilation(self):
        job = self.submit()
        result = self.wait(job)
        path = self.manager._path(job["job_id"])
        with ZipFile(path / "preview.zip") as archive:
            files = {name: archive.read(name) for name in archive.namelist()}
        qa = json.loads(files["qa.json"])
        qa["runtime_status"] = "passed"
        files["qa.json"] = canonical_bytes(qa)
        digest = publish_preview(self.store.state_root, self.project, files)
        forged = deepcopy(result)
        outputs = forged["run"]["steps"][2]["outputs"]
        outputs.update(bundle_sha256=digest, qa_sha256=hashlib.sha256(files["qa.json"]).hexdigest())
        forged["run"] = seal(forged["run"])
        run = forged["run"]
        event = self.manager.application.runs._path(run["run_id"]) / "events" / f"{run['revision']:06d}.json"
        event.write_bytes(canonical_bytes(run))
        buffer = BytesIO()
        with ZipFile(buffer, "w", compression=ZIP_STORED) as archive:
            for name, data in files.items():
                archive.writestr(name, data)
        raw = buffer.getvalue()
        (path / "preview.zip").write_bytes(raw)
        forged["zip_sha256"] = hashlib.sha256(raw).hexdigest()
        (path / "result.json").write_bytes(canonical_bytes(forged))
        # The state chain is structurally valid, but it proves no compilation.
        self.assertEqual(self.manager.get(self.project, job["job_id"])["status"], "succeeded")
        with self.assertRaises(PipelineRunError) as caught:
            download_job(self.manager, self.project, job["job_id"])
        self.assertEqual(caught.exception.reason_code, "pipeline_artifact_invalid")


if __name__ == "__main__":
    unittest.main()
