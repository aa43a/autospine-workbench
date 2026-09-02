"""P10.7a v2 bundle identity, authority, schema, and freeze tests."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
for item in (ROOT, ROOT / "src"):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.spine42_v3_bundle_contract import (  # noqa: E402
    spine42_v3_bundle_address_sha256,
)
from autospine_workbench.spine42_v3_bundle_contract_v2 import (  # noqa: E402
    DOCUMENT_NAMES, Spine42V3BundleContractV2Error,
    build_spine42_v3_bundle_contract_v2,
    spine42_v3_bundle_address_sha256_v2,
)
from autospine_workbench.spine42_v3_export_evidence_v2 import (  # noqa: E402
    AUTHORITY, RELEASE_GATE,
)
from tests.spine42_v3_v2_helpers import Spine42V3V2Fixture  # noqa: E402


FROZEN_V1 = {
    "src/autospine_workbench/spine42_contract_v3.py":
        "38bb2349e8aecdf464371b80f5de38563ea5a4cab5ebcc66a0ffb66a42c85389",
    "src/autospine_workbench/spine42_json_adapter_v3.py":
        "8d72889faf7107154c0f5b97c6be866298f8485135fb07140962f9b88dd45c68",
    "src/autospine_workbench/spine42_v3_export_evidence.py":
        "a79d10e21ec81efeebcc9d61712945c35c1914aa9460f52be734be9d00a9b391",
    "src/autospine_workbench/spine42_v3_bundle_contract.py":
        "b2f44fca8abdbe5b16e37b99ae26b98f97d8cfecc8fe764699ab0d07ad3936ba",
    "src/autospine_workbench/spine42_v3_pipeline.py":
        "d3a63ce518e7da19e63c7343c772c4c270ce8de51c92275f2008bf7de8d02f53",
    "schemas/spine42-v3-export-run-v1.schema.json":
        "67c28bc4bdabbc3d454f38e5f6351b0f2e9ca707487e93969a6132a9bfc3162e",
    "schemas/spine42-v3-export-report-v1.schema.json":
        "aa1b1b3c79f8f595247a646c260a611f81669d82e77b49bccfd505587461146d",
}


class Spine42V3BundleContractV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = Spine42V3V2Fixture(Path(cls.temporary.name))
        cls.contract = cls.fixture.contract()

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def rebuild(self, *, reversed_inputs=False):
        first = self.contract
        p3 = first.p3_source
        motion = first.motion_instance_v3_source
        sources = first.source_image_sha256s
        if reversed_inputs:
            p3 = dict(reversed(tuple(p3.items())))
            motion = dict(reversed(tuple(motion.items())))
            sources = dict(reversed(tuple(sources.items())))
        return build_spine42_v3_bundle_contract_v2(
            first.project_id, first.clip_id, p3, motion,
            json.loads(first.document_bytes["skeleton.json"]),
            first.document_bytes["skeleton.atlas"],
            first.document_bytes["skeleton.png"], sources,
        )

    def test_deterministic_fixed_inventory_and_v2_address_domain(self):
        rebuilt = self.rebuild(reversed_inputs=True)
        self.assertEqual(self.contract, rebuilt)
        self.assertEqual(DOCUMENT_NAMES, self.contract.inventory)
        items = tuple(self.contract.document_bytes.items())
        self.assertEqual(
            self.contract.bundle_sha256,
            spine42_v3_bundle_address_sha256_v2(
                self.contract.project_id,
                self.contract.skeleton_json_sha256, items,
            ),
        )
        self.assertNotEqual(
            self.contract.bundle_sha256,
            spine42_v3_bundle_address_sha256(
                self.contract.project_id,
                self.contract.skeleton_json_sha256, items,
            ),
        )
        with self.assertRaises(Spine42V3BundleContractV2Error):
            spine42_v3_bundle_address_sha256_v2(
                self.contract.project_id,
                self.contract.skeleton_json_sha256,
                tuple(reversed(items)),
            )

    def test_evidence_is_v2_only_and_release_blocked(self):
        run = json.loads(self.contract.document_bytes["run-manifest.json"])
        report = json.loads(self.contract.document_bytes["export-report.json"])
        expected_gate = {
            "status": RELEASE_GATE["status"],
            "reason_codes": list(RELEASE_GATE["reason_codes"]),
        }
        self.assertEqual(2, run["format_version"])
        self.assertEqual(2, report["format_version"])
        self.assertIn("motion_instance_v3_v2", run["inputs"])
        self.assertNotIn("motion_instance_v3", run["inputs"])
        self.assertTrue(all(
            set(item) == {"attachment_id", "sha256"}
            for item in run["inputs"]["source_images"]
        ))
        self.assertEqual(dict(AUTHORITY), run["authority"])
        self.assertEqual(dict(AUTHORITY), report["authority"])
        self.assertEqual(expected_gate, run["release_gate"])
        self.assertEqual(expected_gate, report["release_gate"])
        self.assertEqual(
            {"spine_adapter_emitted"},
            {key for key, value in run["authority"].items() if value},
        )

    def test_public_authority_is_immutable(self):
        with self.assertRaises(TypeError):
            AUTHORITY["release_authority"] = True
        with self.assertRaises(TypeError):
            RELEASE_GATE["status"] = "passed"

    def test_v2_schemas_reject_v1_alias_path_and_escalation(self):
        try:
            from jsonschema import Draft202012Validator
            from referencing import Registry, Resource
        except ImportError:
            self.skipTest("jsonschema/referencing is optional")
        run = json.loads(self.contract.document_bytes["run-manifest.json"])
        report = json.loads(self.contract.document_bytes["export-report.json"])
        run_schema = json.loads((
            ROOT / "schemas/spine42-v3-export-run-v2.schema.json"
        ).read_text(encoding="utf-8"))
        report_schema = json.loads((
            ROOT / "schemas/spine42-v3-export-report-v2.schema.json"
        ).read_text(encoding="utf-8"))
        for schema in (run_schema, report_schema):
            Draft202012Validator.check_schema(schema)
        registry = Registry().with_resources([
            (run_schema["$id"], Resource.from_contents(run_schema)),
            (report_schema["$id"], Resource.from_contents(report_schema)),
        ])
        run_validator = Draft202012Validator(run_schema, registry=registry)
        report_validator = Draft202012Validator(
            report_schema, registry=registry,
        )
        run_validator.validate(run)
        report_validator.validate(report)
        old_alias = deepcopy(run)
        old_alias["inputs"]["motion_instance_v3"] = old_alias[
            "inputs"
        ].pop("motion_instance_v3_v2")
        old_path = deepcopy(run)
        image = old_path["inputs"]["source_images"][0]
        image["path"] = image.pop("attachment_id")
        escalated = deepcopy(report)
        escalated["authority"]["official_runtime_loaded"] = True
        for invalid, validator in (
            (old_alias, run_validator), (old_path, run_validator),
            (escalated, report_validator),
        ):
            self.assertTrue(list(validator.iter_errors(invalid)))

    def test_frozen_v1_literal_hashes_are_unchanged(self):
        for name, expected in FROZEN_V1.items():
            with self.subTest(name=name):
                self.assertEqual(
                    expected, hashlib.sha256((ROOT / name).read_bytes()).hexdigest(),
                )


if __name__ == "__main__":
    unittest.main()
