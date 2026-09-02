"""JSON Schema checks for the P10.6b v2 immutable run."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional test dependency
    Draft202012Validator = None


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from tests.motion_instance_v3_bundle_v2_helpers import (  # noqa: E402
    MotionInstanceV3BundleV2Fixture,
)


@unittest.skipIf(Draft202012Validator is None, "jsonschema is optional")
class MotionInstanceV3BundleRunV2SchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        fixture = MotionInstanceV3BundleV2Fixture(Path(cls.temporary.name))
        cls.document = json.loads(
            fixture.contract.document_bytes["run-manifest-v2.json"],
        )
        schema = json.loads((
            ROOT / "schemas"
            / "motion-instance-v3-bundle-run-v2.schema.json"
        ).read_text(encoding="utf-8"))
        cls.validator = Draft202012Validator(schema)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_generated_run_is_valid(self):
        self.assertEqual(
            [], list(self.validator.iter_errors(self.document)),
        )

    def test_schema_rejects_v1_missing_source_and_overclaims(self):
        attacks = []
        v1 = deepcopy(self.document)
        v1["format_version"] = 1
        attacks.append(v1)
        missing = deepcopy(self.document)
        missing["inputs"]["body_sway_dynamic_seam_v2"].pop(
            "source_set_sha256"
        )
        attacks.append(missing)
        overlap = deepcopy(self.document)
        overlap["authority"]["attachment_area_overlap_assessed"] = True
        attacks.append(overlap)
        boundary = deepcopy(self.document)
        boundary["authority"][
            "full_attachment_boundary_continuity"
        ] = True
        attacks.append(boundary)
        publishable = deepcopy(self.document)
        publishable["authority"]["publishable_timeline"] = True
        attacks.append(publishable)
        released = deepcopy(self.document)
        released["release_gate"]["status"] = "passed"
        attacks.append(released)
        extra = deepcopy(self.document)
        extra["latest"] = True
        attacks.append(extra)
        for index, attack in enumerate(attacks):
            with self.subTest(index=index):
                self.assertNotEqual(
                    [], list(self.validator.iter_errors(attack)),
                )


if __name__ == "__main__":
    unittest.main()
