"""JSON Schema and independent exact-replay validation for P10.7b v2."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from autospine_workbench.spine42_v3_bundle_store_v2 import (  # noqa: E402
    Spine42V3BundleStoreV2,
)
from autospine_workbench.spine42_v3_pipeline_v2 import (  # noqa: E402
    VerifiedSpine42V3PipelineV2,
)
from autospine_workbench.spine42_v3_runtime_plan_v2 import (  # noqa: E402
    Spine42V3RuntimePlanV2Error,
    require_spine42_v3_runtime_plan_v2,
    spine42_v3_runtime_plan_sha256_v2,
)
from autospine_workbench.spine42_v3_runtime_profile_v2 import (  # noqa: E402
    ADMISSION_HASH_DOMAIN, PLAN_HASH_DOMAIN,
)
from autospine_workbench.spine42_v3_runtime_source_admission_v2 import (  # noqa: E402
    Spine42V3RuntimeSourceAdmissionV2Error,
    require_spine42_v3_runtime_source_admission_v2,
    spine42_v3_runtime_source_admission_sha256_v2,
)
from autospine_workbench.spine42_v3_runtime_source_bridge_v2 import (  # noqa: E402
    VerifiedSpine42V3RuntimeSourceBridgeV2,
)
from tests.spine42_v3_v2_helpers import Spine42V3V2Fixture  # noqa: E402


HEADS = (
    "autospine_workbench.spine42_v3_current_heads_v2."
    "require_current_body_sway_dynamic_seam_heads_v2"
)
PLAN_SCHEMA = ROOT / "schemas/spine42-v3-runtime-plan-v2.schema.json"
ADMISSION_SCHEMA = (
    ROOT / "schemas/spine42-v3-runtime-source-admission-v2.schema.json"
)


class Spine42V3RuntimeSourceSchemaV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = Spine42V3V2Fixture(Path(cls.temporary.name))
        with cls.fixture.pipeline_sources():
            compilation = VerifiedSpine42V3PipelineV2(
                cls.fixture.state_root
            ).build(
                cls.fixture.motion_bundle.project_id,
                cls.fixture.motion_bundle.motion_instance_v3_sha256,
                cls.fixture.motion_bundle.bundle_sha256,
            )
        observation = cls.fixture.motion_fixture.observation
        with patch(HEADS, return_value=observation):
            published = Spine42V3BundleStoreV2(
                cls.fixture.motion_fixture.capture,
                cls.fixture.motion_fixture.project_store,
            ).publish(compilation, cls.fixture.motion_bundle, observation)
        cls.bundle = published.verified_bundle
        cls.result = VerifiedSpine42V3RuntimeSourceBridgeV2(
            cls.fixture.state_root
        ).build_from_verified(cls.bundle)
        cls.plan_schema = json.loads(PLAN_SCHEMA.read_text(encoding="utf-8"))
        cls.admission_schema = json.loads(
            ADMISSION_SCHEMA.read_text(encoding="utf-8")
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def validators(self):
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest("jsonschema is optional")
        Draft202012Validator.check_schema(self.plan_schema)
        Draft202012Validator.check_schema(self.admission_schema)
        return (
            Draft202012Validator(self.plan_schema),
            Draft202012Validator(self.admission_schema),
        )

    def test_optional_jsonschema_accepts_exact_instances(self):
        plan_validator, admission_validator = self.validators()
        plan_validator.validate(self.result.plan)
        admission_validator.validate(self.result.admission)

    def test_schemas_reject_unknown_fields_bad_digest_and_wrong_version(self):
        plan_validator, admission_validator = self.validators()
        bad_plan = deepcopy(self.result.plan)
        bad_plan["source"]["unexpected"] = True
        bad_digest = deepcopy(self.result.plan)
        bad_digest["capture_plan_sha256"] = "A" * 64
        bad_admission = deepcopy(self.result.admission)
        bad_admission["source_contract"]["format_version"] = 1
        for value, validator in (
            (bad_plan, plan_validator),
            (bad_digest, plan_validator),
            (bad_admission, admission_validator),
        ):
            self.assertTrue(list(validator.iter_errors(value)))

    def test_plan_schema_enforces_bounds_and_case_artifact_structure(self):
        validator, _admission_validator = self.validators()
        too_many_cases = deepcopy(self.result.plan)
        too_many_cases["cases"] = [
            deepcopy(too_many_cases["cases"][0]) for _index in range(56)
        ]
        too_many_attachments = deepcopy(self.result.plan)
        row = deepcopy(too_many_attachments["attachments"][0])
        too_many_attachments["attachments"] = [row] * 33
        too_many_artifacts = deepcopy(self.result.plan)
        artifact = deepcopy(too_many_artifacts["artifacts"][0])
        too_many_artifacts["artifacts"] = [artifact] * 1871
        malformed = deepcopy(self.result.plan)
        malformed["artifacts"][0]["kind"] = "attachment_isolate"
        for value in (
            too_many_cases, too_many_attachments,
            too_many_artifacts, malformed,
        ):
            self.assertTrue(list(validator.iter_errors(value)))

    def test_admission_schema_fixes_authority_and_release_reasons(self):
        _plan_validator, validator = self.validators()
        overclaim = deepcopy(self.result.admission)
        overclaim["authority"]["official_runtime_loaded"] = True
        reordered = deepcopy(self.result.admission)
        reordered["release_gate"]["reason_codes"].reverse()
        missing = deepcopy(self.result.admission)
        missing["release_gate"]["reason_codes"].pop()
        for value in (overclaim, reordered, missing):
            self.assertTrue(list(validator.iter_errors(value)))

    def test_schema_valid_resealed_source_drift_still_fails_exact_replay(self):
        plan_validator, admission_validator = self.validators()
        plan = deepcopy(self.result.plan)
        plan["source"]["project_id"] = "other-project"
        plan.pop("capture_plan_sha256")
        plan["capture_plan_sha256"] = canonical_sha256({
            "domain": PLAN_HASH_DOMAIN, **plan,
        })
        plan_validator.validate(plan)
        self.assertEqual(
            plan["capture_plan_sha256"],
            spine42_v3_runtime_plan_sha256_v2(plan),
        )
        with self.assertRaisesRegex(Spine42V3RuntimePlanV2Error, "exact"):
            require_spine42_v3_runtime_plan_v2(plan, bundle=self.bundle)

        admission = deepcopy(self.result.admission)
        admission["project_id"] = "other-project"
        admission.pop("admission_sha256")
        admission["admission_sha256"] = canonical_sha256({
            "domain": ADMISSION_HASH_DOMAIN, **admission,
        })
        admission_validator.validate(admission)
        self.assertEqual(
            admission["admission_sha256"],
            spine42_v3_runtime_source_admission_sha256_v2(admission),
        )
        with self.assertRaisesRegex(
            Spine42V3RuntimeSourceAdmissionV2Error, "exact"
        ):
            require_spine42_v3_runtime_source_admission_v2(
                admission, bundle=self.bundle, plan=self.result.plan,
            )

    def test_python_validator_independently_rejects_resealed_overclaim(self):
        admission = deepcopy(self.result.admission)
        admission["authority"]["release_authority"] = True
        admission.pop("admission_sha256")
        admission["admission_sha256"] = canonical_sha256({
            "domain": ADMISSION_HASH_DOMAIN, **admission,
        })
        self.assertEqual(
            admission["admission_sha256"],
            spine42_v3_runtime_source_admission_sha256_v2(admission),
        )
        with self.assertRaises(Spine42V3RuntimeSourceAdmissionV2Error):
            require_spine42_v3_runtime_source_admission_v2(
                admission, bundle=self.bundle, plan=self.result.plan,
            )


if __name__ == "__main__":
    unittest.main()
