"""Coverage reads genuine compiled fixtures without rewriting their inventory."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tests import test_animated_application as fixture
from autospine_workbench.automation.character_coverage_reader import read_job_coverage


class CoverageReaderTests(unittest.TestCase):
    setUp = fixture.AnimatedApplicationTests.setUp
    preview = fixture.AnimatedApplicationTests.preview

    def test_exact_replay_preserves_preview_and_source_guard(self):
        run = self.preview()
        original = self.app.verified_files("project", run)
        info = {k: getattr(self.inputs, k) for k in ("candidate", "draft", "bindings", "source_addresses")}
        manager = SimpleNamespace(application=self.app, files=lambda *_: original,
                                  get=lambda *_: {"run": run})
        module = "autospine_workbench.automation.character_coverage_reader"
        with patch(module + ".inspect_registration", return_value=info), \
                patch(module + ".assert_registered_current") as guard:
            first = read_job_coverage(manager, "project", "job")
            self.assertEqual(first, read_job_coverage(manager, "project", "job"))
            self.assertEqual(first["document"]["summary"]["source_layers"], len(self.inputs.candidate["layers"]))
            guard.assert_called_with(self.projects, "project", self.inputs.source_addresses)
            info["source_addresses"] = {}
            with self.assertRaisesRegex(RuntimeError, "animated_input_changed"):
                read_job_coverage(manager, "project", "job")
        self.assertEqual(self.app.verified_files("project", run), original)
