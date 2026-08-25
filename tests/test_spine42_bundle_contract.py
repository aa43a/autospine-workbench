"""Pure Spine 4.2 bundle contract and schema tests."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.png_rgba import RgbaImage, encode_rgba_png  # noqa: E402
from autospine_workbench.spine42_bundle_contract import (  # noqa: E402
    DOCUMENT_NAMES,
    Spine42BundleContractError,
    build_spine42_bundle_contract,
)
from tests.spine42_bundle_helpers import build_args, bundle_inputs  # noqa: E402


class Spine42BundleContractTests(unittest.TestCase):
    def build(self, values):
        return build_spine42_bundle_contract(
            *build_args(values), p5_source=values["p5_source"]
        )

    def test_setup_contract_is_fixed_pinned_and_deterministic(self):
        values = bundle_inputs()
        first = self.build(values)
        reordered = deepcopy(values)
        reordered["p3_source"] = dict(reversed(reordered["p3_source"].items()))
        reordered["source_image_sha256s"] = dict(
            reversed(reordered["source_image_sha256s"].items())
        )
        second = self.build(reordered)

        self.assertEqual(first, second)
        self.assertEqual(DOCUMENT_NAMES, first.inventory)
        self.assertEqual("setup-only", first.mode)
        self.assertIsNone(first.clip_id)
        self.assertEqual(64, len(first.bundle_sha256))
        run = json.loads(first.document_bytes["run-manifest.json"])
        report = json.loads(first.document_bytes["export-report.json"])
        self.assertEqual("4.2", run["adapter_profile"]["spine_major_minor"])
        self.assertEqual("4.2.119", run["adapter_profile"]["runtime"]["version"])
        self.assertIsNone(run["inputs"]["p5"])
        self.assertEqual("not_applicable", report["checks"][-1]["status"])
        self.assertEqual(2, report["metrics"]["atlas_regions"])

    def test_motion_contract_binds_exact_instance_clip_and_bundle(self):
        values = bundle_inputs(motion=True)
        contract = self.build(values)
        run = json.loads(contract.document_bytes["run-manifest.json"])
        report = json.loads(contract.document_bytes["export-report.json"])
        self.assertEqual("motion", contract.mode)
        self.assertEqual(values["p5_source"]["clip_id"], contract.clip_id)
        self.assertEqual(
            values["p5_source"]["motion_instance_sha256"],
            contract.motion_instance_sha256,
        )
        self.assertEqual("passed", report["checks"][-1]["status"])
        self.assertEqual(values["p5_source"], run["inputs"]["p5"])

        changed = deepcopy(values)
        changed["p5_source"]["bundle_sha256"] = "6" * 64
        changed_contract = self.build(changed)
        self.assertEqual(contract.skeleton_json_sha256,
                         changed_contract.skeleton_json_sha256)
        self.assertNotEqual(contract.run_document_sha256,
                            changed_contract.run_document_sha256)
        self.assertNotEqual(contract.bundle_sha256,
                            changed_contract.bundle_sha256)

    def test_cross_file_and_source_drift_fail_closed(self):
        values = bundle_inputs()
        cases = []
        stale = deepcopy(values)
        stale["p3_source"]["rig_sha256"] = "f" * 64
        cases.append(stale)
        missing_source = deepcopy(values)
        missing_source["source_image_sha256s"].pop("face-image")
        cases.append(missing_source)
        aliased_source = deepcopy(values)
        aliased_source["source_image_sha256s"]["FACE-IMAGE"] = "f" * 64
        cases.append(aliased_source)
        crlf_atlas = deepcopy(values)
        crlf_atlas["atlas_bytes"] = crlf_atlas["atlas_bytes"].replace(b"\n", b"\r\n")
        cases.append(crlf_atlas)
        wrong_page = deepcopy(values)
        wrong_page["atlas_bytes"] = wrong_page["atlas_bytes"].replace(
            b"skeleton.png\n", b"other.png\n", 1
        )
        cases.append(wrong_page)
        wrong_png = deepcopy(values)
        wrong_png["png_bytes"] = encode_rgba_png(RgbaImage(1, 1, b"\0\0\0\0"))
        cases.append(wrong_png)
        for index, invalid in enumerate(cases):
            with self.subTest(index=index), self.assertRaises(
                Spine42BundleContractError
            ):
                self.build(invalid)

        motion = bundle_inputs(motion=True)
        motion["p5_source"]["clip_id"] = "other"
        with self.assertRaises(Spine42BundleContractError):
            self.build(motion)

    def test_source_hash_change_is_a_new_evidence_address(self):
        values = bundle_inputs()
        first = self.build(values)
        changed = deepcopy(values)
        changed["source_image_sha256s"]["face-image"] = "e" * 64
        second = self.build(changed)
        self.assertEqual(first.skeleton_json_sha256, second.skeleton_json_sha256)
        self.assertEqual(first.atlas_sha256, second.atlas_sha256)
        self.assertEqual(first.png_sha256, second.png_sha256)
        self.assertNotEqual(first.run_identity_sha256, second.run_identity_sha256)
        self.assertNotEqual(first.bundle_sha256, second.bundle_sha256)

    def test_run_and_report_validate_against_published_schemas(self):
        try:
            from jsonschema import Draft202012Validator
            from referencing import Registry, Resource
        except ImportError:
            self.skipTest("jsonschema/referencing is optional")
        contract = self.build(bundle_inputs(motion=True))
        run_schema = json.loads((
            ROOT / "schemas" / "spine42-export-run-v1.schema.json"
        ).read_text(encoding="utf-8"))
        report_schema = json.loads((
            ROOT / "schemas" / "spine42-export-report-v1.schema.json"
        ).read_text(encoding="utf-8"))
        registry = Registry().with_resources([
            (run_schema["$id"], Resource.from_contents(run_schema)),
            (report_schema["$id"], Resource.from_contents(report_schema)),
        ])
        Draft202012Validator(run_schema, registry=registry).validate(
            json.loads(contract.document_bytes["run-manifest.json"])
        )
        Draft202012Validator(report_schema, registry=registry).validate(
            json.loads(contract.document_bytes["export-report.json"])
        )


if __name__ == "__main__":
    unittest.main()
