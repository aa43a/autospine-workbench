"""JSON Schema instances for the immutable MotionInstance v3 bundle run."""

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

from tests.motion_instance_v3_bundle_helpers import (  # noqa: E402
    MotionInstanceV3StorageFixture,
)


@unittest.skipIf(Draft202012Validator is None, "jsonschema is optional")
class MotionInstanceV3BundleRunSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        fixture = MotionInstanceV3StorageFixture(Path(cls.temporary.name))
        cls.document = json.loads(
            fixture.contract.document_bytes["run-manifest.json"]
        )
        schema = json.loads((
            ROOT / "schemas" / "motion-instance-v3-bundle-run-v1.schema.json"
        ).read_text(encoding="utf-8"))
        cls.validator = Draft202012Validator(schema)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_generated_run_is_a_valid_schema_instance(self):
        self.assertEqual([], list(self.validator.iter_errors(self.document)))

    def test_schema_rejects_authority_release_and_shape_overclaims(self):
        attacks = []
        missing = deepcopy(self.document)
        missing.pop("authority")
        attacks.append(missing)
        extra = deepcopy(self.document)
        extra["latest"] = True
        attacks.append(extra)
        for field in (
            "spine_adapter_emitted", "runtime_equivalence",
            "raster_visual_quality", "persistent_current_head_authority",
            "release_authority",
        ):
            changed = deepcopy(self.document)
            changed["authority"][field] = True
            attacks.append(changed)
        emitted = deepcopy(self.document)
        emitted["authority"]["motion_instance_v3_emitted"] = False
        attacks.append(emitted)
        passed = deepcopy(self.document)
        passed["release_gate"]["status"] = "passed"
        attacks.append(passed)
        reasons = deepcopy(self.document)
        reasons["release_gate"]["reason_codes"].pop()
        attacks.append(reasons)
        for index, attack in enumerate(attacks):
            with self.subTest(index=index):
                self.assertNotEqual(
                    [], list(self.validator.iter_errors(attack))
                )


if __name__ == "__main__":
    unittest.main()
