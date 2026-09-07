"""Target isolation through real P2 compilation, storage, and ZIP export."""

import json
from pathlib import Path
import unittest
from zipfile import ZipFile

from tests import test_rig_commands
from autospine_workbench.automation.pipeline_application import PipelineApplication
from autospine_workbench.automation.preview_download import export_preview
from autospine_workbench.automation.region_preview import verify_region_preview
from autospine_workbench.automation.region_preview_store import RegionPreviewError, publish_preview


class PipelineTargetPreviewTests(unittest.TestCase):
    def test_versions_reuse_p2_but_never_preview_identity_or_resealed_bytes(self):
        fixture = test_rig_commands.RigCommandIntegrationTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        app = PipelineApplication(fixture.fixture.store())
        bundles, runs = {}, {}
        for version in ("4.2", "4.3.26"):
            run = app.preview("fixture-project", target_version=version)
            self.assertEqual(run["status"], "succeeded", run)
            runs[version] = run
            bundle = verify_region_preview(app.state_root, "fixture-project",
                run["steps"][2]["outputs"]["bundle_sha256"], target_version=version)
            bundles[version] = bundle
            self.assertEqual(json.loads(bundle.files["skeleton.json"])["skeleton"]["spine"], version)
            destination = fixture.fixture.workspace / f"preview-{version}.zip"
            export_preview(app.state_root, run, destination)
            with ZipFile(destination) as archive:
                self.assertEqual(archive.read("skeleton.json"), bundle.files["skeleton.json"])
            self.assertEqual(app.preview("fixture-project", target_version=version), run)
        self.assertEqual(app.preview("fixture-project"), runs["4.3.26"])
        self.assertNotEqual(runs["4.2"]["run_id"], runs["4.3.26"]["run_id"])
        self.assertEqual(runs["4.2"]["steps"][1], runs["4.3.26"]["steps"][1])
        self.assertEqual(bundles["4.2"].files["skeleton.png"], bundles["4.3.26"].files["skeleton.png"])
        with self.assertRaises(RegionPreviewError):
            verify_region_preview(app.state_root, "fixture-project",
                bundles["4.3.26"].addresses["bundle_sha256"], target_version="4.2")
        # Even resealing a 4.2 skeleton with a genuine 4.3 source cannot pass replay.
        forged = dict(bundles["4.3.26"].files, **{"skeleton.json": bundles["4.2"].files["skeleton.json"]})
        digest = publish_preview(app.state_root, "fixture-project", forged, target_version="4.3.26")
        with self.assertRaises(RegionPreviewError):
            verify_region_preview(app.state_root, "fixture-project", digest, target_version="4.3.26")
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            return
        schema = json.loads((Path(__file__).resolve().parents[1] / "schemas" /
            "region-preview-source-spine43-v1.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(json.loads(bundles["4.3.26"].files["source.json"]))
