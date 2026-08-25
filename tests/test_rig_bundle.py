"""Immutable RigIR bundle publication and tamper-boundary tests."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.layer_manifest import (
    LayerManifestBuilder,
    LayerManifestBundleStore,
    sha256_file,
)
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.rig_bundle import RigBundleError, RigBundleStore
from autospine_workbench.rig_bundle_validation import bundle_address_sha256
from tests.test_layer_manifest import project_fixture, write_png


SHA_C = "c" * 64
SHA_D = "d" * 64


class BundleFixture:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.state = root / "state"
        asset = root / "arm.png"
        write_png(asset, 30, 40)
        project = project_fixture()
        self.manifest = LayerManifestBuilder().build(
            project, {"layer-001-arm-l": asset}
        )
        self.layer_bundle, self.layer_sha = LayerManifestBundleStore(self.state).publish(
            "sample-a", self.manifest, {"layer-001-arm-l": asset}
        )
        layer = self.manifest["layers"][0]
        self.run = {
            "format": "autospine-rig-compile-run",
            "format_version": 1,
            "project_id": "sample-a",
            "inputs": {
                "layer_manifest_sha256": self.layer_sha,
                "resolved_project_sha256": SHA_C,
                "override_patch_sha256": SHA_D,
            },
            "compiler": {
                "id": "region-rig-compiler",
                "version": "1.0.0",
                "config": {
                    "attachment_profile": "region-only",
                    "allow_manual_required": False,
                },
            },
        }
        self.rig = self._rig(layer)
        self.probes = {
            "format": "autospine-rig-setup-probes",
            "format_version": 1,
            "project_id": "sample-a",
            "source": {
                "rig_sha256": canonical_sha256(self.rig),
                "layer_manifest_sha256": self.layer_sha,
                "resolved_project_sha256": SHA_C,
            },
            "runner": {"id": "rig-setup-probes", "version": "1.0.0"},
            "status": "passed",
            "checks": [
                {
                    "id": check_id,
                    "status": "passed",
                    **(
                        {"metrics": {"exact": True}}
                        if check_id == "setup.pixel-reconstruction"
                        else {}
                    ),
                }
                for check_id in (
                    "source.identity",
                    "inputs.reviewed",
                    "bones.parent-links",
                    "fk.setup-reconstruction",
                    "attachments.region-bindings",
                    "attachments.pivot-roundtrip",
                    "slots.draw-order",
                    "setup.pixel-reconstruction",
                )
            ],
        }
        self.store = RigBundleStore(self.state)

    def _rig(self, layer: dict) -> dict:
        return {
            "format": "autospine-rig-ir",
            "format_version": 1,
            "source": {
                "run_manifest_sha256": canonical_sha256(self.run),
                "layer_manifest_sha256": self.layer_sha,
                "override_patch_sha256": SHA_D,
            },
            "canvas": {
                "width": 100,
                "height": 200,
                "origin": "top_left",
                "x_axis": "right",
                "y_axis": "down",
                "units": "pixel",
            },
            "capabilities": ["region_attachment", "setup_draw_order"],
            "unsupported_feature_policy": "fail",
            "bones": [{
                "id": "root",
                "parent": None,
                "setup": {
                    "x": 0, "y": 0, "rotation_deg": 0,
                    "scale_x": 1, "scale_y": 1, "length": 0,
                },
                "inference": {"method": "manual", "confidence": 1},
            }],
            "slots": [{
                "id": "arm-slot", "bone": "root", "setup_attachment": "arm-region",
                "setup_draw_order": 0, "blend": "normal", "color_rgba": "ffffffff",
            }],
            "attachments": [{
                "id": "arm-region", "slot": "arm-slot", "type": "region",
                "image_path": layer["raster"]["artifact_path"],
                "image_sha256": layer["raster"]["sha256"],
                "source_layer_ids": [layer["layer_id"]],
                "canvas_offset_xy": layer["raster"]["canvas_offset_xy"],
                "pivot_xy": [20, 25], "size": [30, 40],
            }],
            "skins": {"default": {"arm-slot": ["arm-region"]}},
            "animations": [],
            "qa": {"status": "passed", "checks": [], "manual_override_ids": []},
        }

    def publish(self, *, rig=None, run=None, probes=None, layer_bundle=None):
        return self.store.publish(
            "sample-a",
            rig or self.rig,
            run or self.run,
            probes or self.probes,
            layer_bundle or self.layer_bundle,
        )


class RigBundleStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.fixture = BundleFixture(Path(self.directory.name))

    def test_publish_is_content_addressed_complete_and_idempotent(self) -> None:
        first = self.fixture.publish()
        second = self.fixture.publish()

        self.assertEqual(first, second)
        bundle, rig_sha = first
        bundle_sha = bundle_address_sha256(
            rig_sha,
            canonical_sha256(self.fixture.run),
            canonical_sha256(self.fixture.probes),
        )
        self.assertEqual(
            self.fixture.state / "builds" / "sample-a" / "rig-ir" / rig_sha / bundle_sha,
            bundle,
        )
        self.assertEqual(
            {"rig.json", "run-manifest.json", "probes.json", "layers"},
            {item.name for item in bundle.iterdir()},
        )
        for name, expected in (
            ("rig.json", self.fixture.rig),
            ("run-manifest.json", self.fixture.run),
            ("probes.json", self.fixture.probes),
        ):
            self.assertEqual(expected, json.loads((bundle / name).read_text(encoding="utf-8")))
        source = self.fixture.layer_bundle / "layers" / "layer-001-arm-l.png"
        copied = bundle / "layers" / "layer-001-arm-l.png"
        self.assertEqual(source.read_bytes(), copied.read_bytes())
        self.assertEqual(sha256_file(source), sha256_file(copied))

    def test_probe_version_gets_a_distinct_bundle_under_the_same_rig(self) -> None:
        first, rig_sha = self.fixture.publish()
        probes = deepcopy(self.fixture.probes)
        probes["runner"]["version"] = "1.1.0"

        second, repeated_rig_sha = self.fixture.publish(probes=probes)

        self.assertEqual(rig_sha, repeated_rig_sha)
        self.assertEqual(first.parent, second.parent)
        self.assertNotEqual(first, second)
        self.assertEqual(
            bundle_address_sha256(
                rig_sha,
                canonical_sha256(self.fixture.run),
                canonical_sha256(probes),
            ),
            second.name,
        )
        self.assertEqual(
            {first.name, second.name},
            {item.name for item in first.parent.iterdir()},
        )
        self.assertEqual(
            "1.0.0",
            json.loads((first / "probes.json").read_text(encoding="utf-8"))["runner"][
                "version"
            ],
        )
        self.assertEqual(
            "1.1.0",
            json.loads((second / "probes.json").read_text(encoding="utf-8"))["runner"][
                "version"
            ],
        )

    def test_bundle_address_covers_all_three_documents(self) -> None:
        baseline = bundle_address_sha256("a" * 64, "b" * 64, "c" * 64)
        for index, digests in enumerate(
            (
                ("d" * 64, "b" * 64, "c" * 64),
                ("a" * 64, "d" * 64, "c" * 64),
                ("a" * 64, "b" * 64, "d" * 64),
            )
        ):
            with self.subTest(document=index):
                self.assertNotEqual(baseline, bundle_address_sha256(*digests))

    def test_legacy_flat_rig_bundle_fails_closed_without_mutation(self) -> None:
        rig_sha = canonical_sha256(self.fixture.rig)
        legacy = self.fixture.state / "builds" / "sample-a" / "rig-ir" / rig_sha
        legacy.mkdir(parents=True)
        marker = legacy / "rig.json"
        marker.write_text('{"legacy":true}\n', encoding="utf-8")

        with self.assertRaisesRegex(RigBundleError, "Legacy flat"):
            self.fixture.publish()

        self.assertEqual('{"legacy":true}\n', marker.read_text(encoding="utf-8"))
        self.assertEqual({"rig.json"}, {item.name for item in legacy.iterdir()})

    def test_existing_document_or_layer_tampering_fails_loudly(self) -> None:
        for name in ("rig.json", "run-manifest.json", "probes.json"):
            with self.subTest(name), tempfile.TemporaryDirectory() as directory:
                fixture = BundleFixture(Path(directory))
                bundle, _ = fixture.publish()
                (bundle / name).write_text("{}", encoding="utf-8")
                with self.assertRaises(RigBundleError):
                    fixture.publish()

        with tempfile.TemporaryDirectory() as directory:
            fixture = BundleFixture(Path(directory))
            bundle, _ = fixture.publish()
            write_png(bundle / "layers" / "layer-001-arm-l.png", 1, 1)
            with self.assertRaisesRegex(RigBundleError, "hash mismatch"):
                fixture.publish()

    def test_run_and_probe_bindings_are_checked_before_publication(self) -> None:
        cases = []
        rig = deepcopy(self.fixture.rig)
        rig["source"]["run_manifest_sha256"] = "f" * 64
        cases.append(("rig run", rig, self.fixture.run, self.fixture.probes))
        probes = deepcopy(self.fixture.probes)
        probes["source"]["rig_sha256"] = "f" * 64
        cases.append(("probe rig", self.fixture.rig, self.fixture.run, probes))
        probes = deepcopy(self.fixture.probes)
        probes["source"]["resolved_project_sha256"] = "f" * 64
        cases.append(("probe resolved", self.fixture.rig, self.fixture.run, probes))
        for label, candidate_rig, run, report in cases:
            with self.subTest(label), self.assertRaises(RigBundleError):
                self.fixture.publish(rig=candidate_rig, run=run, probes=report)
        self.assertFalse(
            (self.fixture.state / "builds" / "sample-a" / "rig-ir").exists()
        )

    def test_probe_contract_and_region_profile_cannot_be_bypassed(self) -> None:
        probes = deepcopy(self.fixture.probes)
        probes["checks"].pop()
        with self.assertRaisesRegex(RigBundleError, "not valid canonical JSON"):
            self.fixture.publish(probes=probes)

        rig = deepcopy(self.fixture.rig)
        rig["capabilities"].append("bone_rotate")
        probes = deepcopy(self.fixture.probes)
        probes["source"]["rig_sha256"] = canonical_sha256(rig)
        with self.assertRaisesRegex(RigBundleError, "not valid canonical JSON"):
            self.fixture.publish(rig=rig, probes=probes)

    def test_manual_required_bundle_must_be_explicitly_enabled(self) -> None:
        rig = deepcopy(self.fixture.rig)
        rig["qa"]["status"] = "manual_required"
        run = deepcopy(self.fixture.run)
        run["compiler"]["config"]["allow_manual_required"] = True
        rig["source"]["run_manifest_sha256"] = canonical_sha256(run)
        probes = deepcopy(self.fixture.probes)
        probes["status"] = "manual_required"
        next(
            check for check in probes["checks"] if check["id"] == "inputs.reviewed"
        )["status"] = "manual_required"
        probes["source"]["rig_sha256"] = canonical_sha256(rig)
        bundle, _ = self.fixture.publish(rig=rig, run=run, probes=probes)
        self.assertTrue(bundle.is_dir())

    def test_unsafe_or_unpinned_region_paths_are_rejected(self) -> None:
        for value in ("../outside.png", "/outside.png", "layers\\arm.png", "layers/missing.png"):
            rig = deepcopy(self.fixture.rig)
            rig["attachments"][0]["image_path"] = value
            probes = deepcopy(self.fixture.probes)
            probes["source"]["rig_sha256"] = canonical_sha256(rig)
            with self.subTest(value), self.assertRaises(RigBundleError):
                self.fixture.publish(rig=rig, probes=probes)

    def test_unsafe_project_and_sha_fields_are_rejected(self) -> None:
        with self.assertRaisesRegex(RigBundleError, "Project id"):
            self.fixture.store.publish(
                "../sample-a",
                self.fixture.rig,
                self.fixture.run,
                self.fixture.probes,
                self.fixture.layer_bundle,
            )
        rig = deepcopy(self.fixture.rig)
        rig["source"]["layer_manifest_sha256"] = "F" * 64
        probes = deepcopy(self.fixture.probes)
        probes["source"]["rig_sha256"] = canonical_sha256(rig)
        with self.assertRaisesRegex(RigBundleError, "SHA-256"):
            self.fixture.publish(rig=rig, probes=probes)

        rig = deepcopy(self.fixture.rig)
        rig["attachments"][0]["image_sha256"] = "f" * 64
        probes = deepcopy(self.fixture.probes)
        probes["source"]["rig_sha256"] = canonical_sha256(rig)
        with self.assertRaisesRegex(RigBundleError, "image hash"):
            self.fixture.publish(rig=rig, probes=probes)

    def test_copy_failure_leaves_no_visible_or_staging_bundle(self) -> None:
        with patch("autospine_workbench.rig_bundle.shutil.copyfile", side_effect=OSError("stop")):
            with self.assertRaises(RigBundleError):
                self.fixture.publish()
        parent = self.fixture.state / "builds" / "sample-a" / "rig-ir"
        rig_parent = parent / canonical_sha256(self.fixture.rig)
        self.assertEqual([], list(rig_parent.iterdir()))

    def test_layer_bundle_symlink_is_rejected_when_supported(self) -> None:
        original = self.fixture.layer_bundle
        target = original.with_name("real-layer-bundle")
        original.rename(target)
        try:
            original.symlink_to(target, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"directory symlink unavailable: {exc}")
        try:
            with self.assertRaisesRegex(RigBundleError, "symlink"):
                self.fixture.publish(layer_bundle=original)
        finally:
            original.rmdir()

    def test_matching_external_layer_bundle_is_not_accepted(self) -> None:
        external = self.fixture.root / "external-manifest"
        shutil.copytree(self.fixture.layer_bundle, external)
        with self.assertRaisesRegex(RigBundleError, "expected build path"):
            self.fixture.publish(layer_bundle=external)


if __name__ == "__main__":
    unittest.main()
