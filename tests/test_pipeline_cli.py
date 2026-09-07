"""No-SHA CLI, deterministic downloads, and public error boundaries."""

from contextlib import redirect_stdout
from io import StringIO
import json
import unittest
from zipfile import ZipFile

from tests import test_rig_commands as rig_commands
from autospine_workbench.automation.__main__ import main


class PipelineCliTests(unittest.TestCase):
    def setUp(self):
        self.fixture = rig_commands.RigCommandIntegrationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.state = self.fixture.fixture.state
        self.workspace = self.fixture.fixture.workspace

    def invoke(self, *args):
        output = StringIO()
        with redirect_stdout(output):
            status = main(["--workspace", str(self.workspace), "--state-root", str(self.state), *args])
        document = json.loads(output.getvalue())
        self.assertNotIn(str(self.state), output.getvalue())
        return status, document

    def test_preview_download_is_deterministic_and_contains_real_spine_files(self):
        target = self.workspace / "download.zip"
        status, run = self.invoke("preview", "fixture-project", "--output", str(target))
        self.assertEqual(status, 0, run)
        previous = target.read_bytes()
        with ZipFile(target) as archive:
            self.assertEqual(set(archive.namelist()), {
                "skeleton.json", "skeleton.atlas", "skeleton.png", "source.json", "qa.json",
            })
            self.assertEqual(json.loads(archive.read("skeleton.json"))["skeleton"]["spine"], "4.3.26")
            self.assertEqual(json.loads(archive.read("qa.json"))["runtime_status"], "not_run")
        self.assertEqual(self.invoke("preview", "fixture-project", "--output", str(target)), (0, run))
        self.assertEqual(target.read_bytes(), previous)
        self.assertEqual(self.invoke("status", run["run_id"]), (0, run))

    def test_export_does_not_replace_user_file(self):
        target = self.workspace / "existing.zip"
        target.write_bytes(b"user content")
        status, error = self.invoke("preview", "fixture-project", "--output", str(target))
        self.assertEqual(status, 1)
        self.assertEqual(error["reason_code"], "pipeline_output_exists")
        self.assertEqual(target.read_bytes(), b"user content")

    def test_capabilities_do_not_publish_jobs(self):
        status, report = self.invoke("capabilities", "fixture-project")
        self.assertEqual(status, 0)
        self.assertTrue(report["can_build_spine_preview"])
        self.assertFalse((self.state / "jobs").exists())

    def test_invalid_requests_have_structured_path_free_errors(self):
        for args, reason in [
            (("preview", "missing-project"), "project_not_found"),
            (("preview", "fixture-project", "--profile", "invented"), "unsupported_pipeline_profile"),
            (("preview", "fixture-project", "--target-version", "4.3"), "unsupported_target_version"),
            (("status", "../outside"), "pipeline_run_id_invalid"),
        ]:
            with self.subTest(args=args):
                status, error = self.invoke(*args)
                self.assertEqual(status, 1)
                self.assertEqual(error["reason_code"], reason)

    def test_exact_profile_cannot_masquerade_as_certified_export(self):
        status, run = self.invoke("preview", "fixture-project", "--profile", "certification_exact")
        self.assertEqual(status, 2)
        self.assertEqual(run["status"], "blocked")
        self.assertEqual(run["steps"][0]["reason_code"], "certification_exact_entry_required")
        status, canceled = self.invoke("cancel", run["run_id"])
        self.assertEqual(status, 3)
        self.assertEqual(canceled["status"], "canceled")


if __name__ == "__main__":
    unittest.main()
