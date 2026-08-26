"""P10.4a canonical BodySwayReviewAdmission v1 contract tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional test dependency
    Draft202012Validator = None

from autospine_workbench.body_sway_review_admission import (  # noqa: E402
    BodySwayReviewAdmissionError,
    compile_body_sway_review_admission,
)
from autospine_workbench.body_sway_review_admission_inputs import (  # noqa: E402
    build_body_sway_review_admission_input,
)
from autospine_workbench.body_sway_review_admission_profile import (  # noqa: E402
    admission_claims,
    admission_release_gate,
    compiler_profile,
)
from autospine_workbench.body_sway_review_admission_validation import (  # noqa: E402
    BodySwayReviewAdmissionValidationError,
    body_sway_review_admission_sha256,
    require_body_sway_review_admission,
)
from autospine_workbench.body_sway_runtime_capture_reader import (  # noqa: E402
    VerifiedBodySwayRuntimeCaptureReader,
)
from autospine_workbench.body_sway_visual_review_address import (  # noqa: E402
    ExactVisualReviewAddress,
)
from autospine_workbench.body_sway_visual_review_application import (  # noqa: E402
    BodySwayVisualReviewApplication,
)
from tests.body_sway_runtime_capture_helpers import (  # noqa: E402
    fake_runtime_profile,
)
from tests.body_sway_visual_review_helpers import (  # noqa: E402
    BodySwayVisualReviewFixture,
    review_rows,
)
from tests.p10_review_admission_helpers import (  # noqa: E402
    forge_capture_detached_admission_input,
)


class BodySwayReviewAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profile_context = fake_runtime_profile()
        cls.profile_context.__enter__()
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.fixture = BodySwayVisualReviewFixture(cls.root)
        cls.address = ExactVisualReviewAddress(*cls.fixture.address)
        service = BodySwayVisualReviewApplication(cls.fixture.state_root)
        with fake_runtime_profile():
            capture = VerifiedBodySwayRuntimeCaptureReader(
                cls.fixture.state_root
            ).load(*cls.address.reader_arguments)
            prepared = service.prepare(cls.address)
            payload = {
                "base_revision": 0,
                "candidate_sha256": prepared.candidate_sha256,
                "previous_decision_sha256": None,
                "review": {
                    "reviewer_id": "artist-01",
                    "notes": "checked every sampled official-runtime still",
                },
                "decisions": review_rows(prepared.candidate_document),
            }
            submitted = service.submit(cls.address, payload)
            before = service.prepare(cls.address)
            exact = service.exact_decision(
                cls.address,
                candidate_sha256=prepared.candidate_sha256,
                revision=submitted.revision,
                decision_sha256=submitted.decision_sha256,
            )
            after = service.prepare(cls.address)
        cls.inputs = build_body_sway_review_admission_input(
            cls.fixture.inputs.preview, capture, before, exact, after,
            address=cls.address,
            candidate_sha256=prepared.candidate_sha256,
            revision=submitted.revision,
            decision_sha256=submitted.decision_sha256,
        )
        cls.admission = compile_body_sway_review_admission(cls.inputs)

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            cls.temporary.cleanup()
        finally:
            cls.profile_context.__exit__(None, None, None)

    def test_compiler_is_deterministic_path_free_and_exactly_bound(self):
        repeated = compile_body_sway_review_admission(self.inputs)
        document = self.admission.document
        self.assertEqual(self.admission.canonical_bytes,
                         repeated.canonical_bytes)
        self.assertEqual(self.admission.sha256, repeated.sha256)
        self.assertEqual(
            self.admission.sha256,
            body_sway_review_admission_sha256(document),
        )
        self.assertNotIn("path", _recursive_keys(document))
        self.assertEqual(self.inputs.source, document["source"]["p10_chain"])
        self.assertEqual(self.inputs.timing, document["timing"])
        self.assertEqual(self.inputs.selection, document["selection"])
        capture = document["source"]["capture"]
        self.assertEqual(self.address.public_document(), {
            key: capture[key] for key in self.address.public_document()
        })
        self.assertEqual(
            self.fixture.inputs.preview.artifact_set_sha256,
            capture["preview_artifact_set_sha256"],
        )
        self.assertEqual(
            self.inputs.runtime_capture_manifest_sha256,
            capture["runtime_capture_manifest_sha256"],
        )
        self.assertEqual({
            "candidate_sha256": self.inputs.visual_candidate_sha256,
            "revision": self.inputs.visual_revision,
            "decision_sha256": self.inputs.visual_decision_sha256,
            "head_decision_sha256": self.inputs.visual_decision_sha256,
        }, document["source"]["visual_review"])

    def test_claims_and_head_observation_never_grant_release(self):
        document = self.admission.document
        self.assertEqual("admitted_for_safety_analysis", document["status"])
        self.assertEqual({
            "sampled_visual_approved": True,
            "head_observed_at_compile_time": True,
            "safe_range": False,
            "continuous_time": False,
            "reviewed_seam_anchors": False,
            "publishable_timeline": False,
            "release_authority": False,
        }, document["claims"])
        self.assertEqual({
            "method": "double_snapshot",
            "scope": "compile_time",
            "revision": self.inputs.visual_revision,
            "head_decision_sha256": self.inputs.visual_decision_sha256,
            "permanent_authority_claimed": False,
        }, document["head_observation"])
        self.assertEqual("blocked", document["release_gate"]["status"])
        self.assertEqual(4, len(document["release_gate"]["reason_codes"]))

    def test_mutating_profile_results_cannot_escalate_contract(self):
        claims = admission_claims()
        claims["release_authority"] = True
        gate = admission_release_gate()
        gate["status"] = "passed"
        gate["reason_codes"].clear()
        profile = compiler_profile()
        profile["version"] = "mutated"

        document = compile_body_sway_review_admission(self.inputs).document
        self.assertFalse(document["claims"]["release_authority"])
        self.assertEqual("blocked", document["release_gate"]["status"])
        self.assertEqual("1.0.0", document["compiler"]["version"])

        overclaim = deepcopy(document)
        overclaim["claims"]["release_authority"] = True
        with self.assertRaises(BodySwayReviewAdmissionValidationError):
            require_body_sway_review_admission(overclaim)

    def test_semantic_validator_rejects_overclaims_and_crosswires(self):
        mutations = []
        claimed = deepcopy(self.admission.document)
        claimed["claims"]["safe_range"] = True
        mutations.append(claimed)
        released = deepcopy(self.admission.document)
        released["release_gate"]["status"] = "passed"
        mutations.append(released)
        crosswired = deepcopy(self.admission.document)
        crosswired["source"]["visual_review"]["head_decision_sha256"] = "a" * 64
        mutations.append(crosswired)
        stale = deepcopy(self.admission.document)
        stale["head_observation"]["revision"] += 1
        mutations.append(stale)
        path_bearing = deepcopy(self.admission.document)
        path_bearing["source"]["capture"]["path"] = "C:/private/capture"
        mutations.append(path_bearing)
        for value in mutations:
            with self.subTest(value=value), self.assertRaises(
                BodySwayReviewAdmissionValidationError
            ):
                require_body_sway_review_admission(value)

    def test_compiler_revalidates_exact_type_and_frozen_contents(self):
        with self.assertRaises(BodySwayReviewAdmissionError):
            compile_body_sway_review_admission(object())
        forged = replace(
            self.inputs, visual_decision_sha256="a" * 64
        )
        with self.assertRaises(BodySwayReviewAdmissionError):
            compile_body_sway_review_admission(forged)

    def test_self_consistent_candidate_cannot_replace_capture_case_evidence(self):
        forged = forge_capture_detached_admission_input(self.inputs)
        with self.assertRaises(BodySwayReviewAdmissionError):
            compile_body_sway_review_admission(forged)

    def test_canonical_hash_ignores_mapping_insertion_order(self):
        document = self.admission.document
        reordered = dict(reversed(list(document.items())))
        require_body_sway_review_admission(reordered)
        self.assertEqual(
            self.admission.sha256,
            body_sway_review_admission_sha256(reordered),
        )

    @unittest.skipIf(Draft202012Validator is None, "jsonschema is optional")
    def test_json_schema_accepts_only_the_bounded_contract(self):
        schema = json.loads((
            ROOT / "schemas" / "body-sway-review-admission-v1.schema.json"
        ).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        validator.validate(self.admission.document)
        invalid = deepcopy(self.admission.document)
        invalid["claims"]["release_authority"] = True
        self.assertFalse(validator.is_valid(invalid))
        wrong_order = deepcopy(self.admission.document)
        amplitudes = wrong_order["selection"]["parameters"][
            "per_bone_amplitude_deg"
        ]
        amplitudes[0]["bone_id"], amplitudes[1]["bone_id"] = (
            amplitudes[1]["bone_id"], amplitudes[0]["bone_id"]
        )
        self.assertFalse(validator.is_valid(wrong_order))


def _recursive_keys(value) -> set[str]:
    if type(value) is dict:
        result = set(value)
        for item in value.values():
            result.update(_recursive_keys(item))
        return result
    if type(value) is list:
        result = set()
        for item in value:
            result.update(_recursive_keys(item))
        return result
    return set()


if __name__ == "__main__":
    unittest.main()
