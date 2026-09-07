"""Real P2 setup to isolated Spine preview integration and tamper checks."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from tests import test_rig_commands as rig_commands
from autospine_workbench.automation.region_preview import (
    build_region_preview, verify_region_preview,
)
from autospine_workbench.automation.region_preview_store import RegionPreviewError, publish_preview
from autospine_workbench.layer_manifest import LayerManifestBundleStore
from autospine_workbench.manifest_bundle import LayerManifestBundleReader
from autospine_workbench.png_rgba import decode_rgba_png

try:
    from jsonschema import Draft202012Validator
except ImportError:
    Draft202012Validator = None


class RegionPreviewTests(unittest.TestCase):
    def setUp(self):
        fixture = rig_commands.RigCommandIntegrationTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.state = fixture.fixture.state
        status, result = fixture._run(
            "compile-rig", "fixture-project", "--layer-manifest-sha256",
            fixture.manifest_sha, "--workspace", str(fixture.fixture.workspace),
            "--state-root", str(self.state),
        )
        self.assertEqual(status, 0, result)
        self.rig = result

    def build(self):
        return build_region_preview(
            self.state, "fixture-project", self.fixture.manifest_sha,
            self.rig["rig_sha256"], self.rig["bundle_sha256"],
        )

    def verify(self, address, **kwargs):
        return verify_region_preview(
            self.state, "fixture-project", address["bundle_sha256"], **kwargs,
        )

    def test_real_setup_is_deterministic_and_has_no_authority(self):
        first = self.build()
        self.assertEqual(first, self.build())
        bundle = self.verify(first, expected_source_addresses=first["source_addresses"])
        self.assertNotIn("path", first)
        self.assertEqual(set(bundle.files), {
            "skeleton.json", "skeleton.atlas", "skeleton.png", "source.json", "qa.json",
        })
        skeleton = json.loads(bundle.files["skeleton.json"])
        self.assertEqual(skeleton["skeleton"]["spine"], "4.2")
        self.assertEqual(skeleton["animations"], {})
        self.assertEqual(json.loads(bundle.files["source.json"])["authority"], "none")
        qa = json.loads(bundle.files["qa.json"])
        self.assertEqual(qa["runtime_status"], "not_run")
        self.assertEqual(qa["setup_rgba_sha256"], self.rig["setup_rgba_sha256"])
        image = decode_rgba_png(bundle.files["skeleton.png"])
        # Exact source RGBA, including transparency, survives untrimmed packing.
        pixels = [tuple(image.pixels[i:i + 4]) for i in range(0, len(image.pixels), 4)]
        self.assertEqual(pixels.count((40, 90, 160, 220)), 400)

    def test_tamper_extra_and_missing_files_fail_closed(self):
        address = self.build()
        bundle = self.verify(address)
        for name, action in (("qa.json", "tamper"), ("extra.txt", "extra"),
                             ("skeleton.atlas", "missing")):
            with self.subTest(action=action):
                path = bundle.path / name
                previous = path.read_bytes() if path.exists() else None
                if action == "missing":
                    path.unlink()
                else:
                    path.write_bytes(b"tampered")
                with self.assertRaises(RegionPreviewError):
                    self.verify(address)
                if previous is None:
                    path.unlink()
                else:
                    path.write_bytes(previous)

    def test_crosswired_sources_and_unsafe_project_fail(self):
        address = self.build()
        sources = dict(address["source_addresses"], rig_sha256="f" * 64)
        with self.assertRaises(RegionPreviewError):
            self.verify(address, expected_source_addresses=sources)
        with self.assertRaises(ValueError):
            build_region_preview(self.state, "../fixture-project", self.fixture.manifest_sha,
                                 self.rig["rig_sha256"], self.rig["bundle_sha256"])
        with self.assertRaises(RegionPreviewError):
            build_region_preview(self.state, "fixture-project", "f" * 64,
                                 self.rig["rig_sha256"], self.rig["bundle_sha256"])

    def test_resealed_report_cannot_claim_runtime_authority(self):
        bundle = self.verify(self.build())
        files = bundle.files
        qa = json.loads(files["qa.json"])
        qa["runtime_status"] = "passed"
        files["qa.json"] = json.dumps(qa).encode()
        digest = publish_preview(self.state, "fixture-project", files)
        with self.assertRaises(RegionPreviewError):
            verify_region_preview(self.state, "fixture-project", digest)

    @unittest.skipUnless(Draft202012Validator, "jsonschema optional validation dependency is unavailable")
    def test_real_preview_documents_match_strict_versioned_schemas(self):
        bundle = self.verify(self.build())
        schemas = Path(__file__).resolve().parents[1] / "schemas"
        for kind in ("source", "qa"):
            with self.subTest(kind=kind):
                schema = json.loads((schemas / f"region-preview-{kind}-v1.schema.json").read_text())
                Draft202012Validator.check_schema(schema)
                validator = Draft202012Validator(schema)
                document = json.loads(bundle.files[f"{kind}.json"])
                validator.validate(document)
                document["authority"] = "release"
                self.assertFalse(validator.is_valid(document))
                document["authority"] = "none"
                document["unrecognized"] = True
                self.assertFalse(validator.is_valid(document))
        qa = json.loads(bundle.files["qa.json"])
        qa["runtime_status"] = "passed"
        self.assertFalse(Draft202012Validator(json.loads(
            (schemas / "region-preview-qa-v1.schema.json").read_text()
        )).is_valid(qa))

    def test_diagnostic_p2_cannot_become_reviewed_spine_preview(self):
        loaded = LayerManifestBundleReader(self.state).load(
            "fixture-project", self.fixture.manifest_sha,
        )
        manifest = loaded.manifest
        manifest["qa"]["status"] = "manual_required"
        assets = {layer["layer_id"]: loaded.path / layer["raster"]["artifact_path"]
                  for layer in manifest["layers"]}
        _, digest = LayerManifestBundleStore(self.state).publish(
            "fixture-project", manifest, assets,
        )
        status, result = self.fixture._run(
            "compile-rig", "fixture-project", "--layer-manifest-sha256", digest,
            "--allow-manual-required", "--workspace", str(self.fixture.fixture.workspace),
            "--state-root", str(self.state),
        )
        self.assertEqual(status, 0, result)
        self.assertEqual(result["probe_status"], "manual_required")
        with self.assertRaises(RegionPreviewError):
            build_region_preview(self.state, "fixture-project", digest,
                                 result["rig_sha256"], result["bundle_sha256"])


if __name__ == "__main__":
    unittest.main()
