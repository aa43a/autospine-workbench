"""Contract, compiler, and adversarial tests for P10.4b1 candidates."""

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
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

try:
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
except ImportError:  # pragma: no cover - optional test dependency
    Draft202012Validator = None
    Registry = Resource = None

from autospine_workbench.body_sway_amplitude_envelope import (  # noqa: E402
    BodySwayAmplitudeEnvelopeError,
    compile_body_sway_amplitude_envelope_candidate,
)
from autospine_workbench.body_sway_amplitude_envelope_inputs import (  # noqa: E402
    BodySwayAmplitudeEnvelopeInputError,
    require_body_sway_amplitude_envelope_inputs,
)
from autospine_workbench.body_sway_amplitude_envelope_profile import (  # noqa: E402
    MAX_ENVELOPE_DOCUMENT_BYTES,
    MAX_ENVELOPE_OWN_BYTES,
    MAX_PROBE_REPORT_BYTES,
    body_sway_amplitude_envelope_analyzer_profile,
    body_sway_amplitude_envelope_claims,
    body_sway_amplitude_envelope_release_gate,
    body_sway_scaled_amplitudes,
)
from autospine_workbench.body_sway_review_admission_profile import (  # noqa: E402
    MAX_ADMISSION_DOCUMENT_BYTES,
)
from autospine_workbench.body_sway_amplitude_envelope_validation import (  # noqa: E402
    BodySwayAmplitudeEnvelopeValidationError,
    body_sway_amplitude_envelope_candidate_sha256,
    body_sway_amplitude_envelope_probe_sha256,
    require_body_sway_amplitude_envelope_candidate,
)
from tests.body_sway_amplitude_envelope_helpers import (  # noqa: E402
    admitted_envelope_inputs,
)
from tests.p10_review_admission_helpers import (  # noqa: E402
    P10ReviewAdmissionFixture,
)


P104B1_CANONICAL_SHA256 = (
    "637efc59b73bdb21fd1c9a49ec1271a763d4c0444b311c6ff777a3564b5cc929"
)


class BodySwayAmplitudeEnvelopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = P10ReviewAdmissionFixture(Path(cls.temporary.name))
        cls.admitted, cls.inputs = admitted_envelope_inputs(cls.fixture)
        cls.candidate = compile_body_sway_amplitude_envelope_candidate(
            cls.inputs
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_candidate_is_deterministic_exact_and_sampled_only(self):
        repeated = compile_body_sway_amplitude_envelope_candidate(self.inputs)
        document = self.candidate.document
        self.assertEqual(self.candidate.canonical_bytes,
                         repeated.canonical_bytes)
        self.assertEqual(
            self.candidate.sha256,
            body_sway_amplitude_envelope_candidate_sha256(document),
        )
        self.assertEqual(P104B1_CANONICAL_SHA256, self.candidate.sha256)
        self.assertEqual(list(range(9)), [
            row["gain"]["numerator"] for row in document["probes"]
        ])
        self.assertEqual({8}, {
            row["gain"]["denominator"] for row in document["probes"]
        })
        reviewed = document["probes"][-1]
        report = self.inputs.preview_inputs.report
        self.assertEqual(
            report["sample_stream"]["sample_stream_sha256"],
            reviewed["sample_stream_sha256"],
        )
        self.assertEqual(report["checks"], reviewed["checks"])
        self.assertEqual("approved", reviewed["visual_review_status"])
        self.assertEqual(
            "exact-reviewed-probe-replay", reviewed["preview_relation"]
        )
        self.assertEqual("candidate_only", document["status"])
        self.assertFalse(document["claims"]["safe_range"])
        self.assertFalse(document["claims"]["continuous_time"])
        self.assertFalse(document["claims"]["release_authority"])
        self.assertEqual("blocked", document["release_gate"]["status"])

    def test_validator_rejects_crosswires_overclaims_and_timeline_fields(self):
        mutations = []
        for mutate in (
            lambda row: row["claims"].__setitem__("safe_range", True),
            lambda row: row["source"].__setitem__(
                "review_admission_sha256", "a" * 64
            ),
            lambda row: row["probes"][0]["gain"].__setitem__(
                "numerator", 1
            ),
            lambda row: row["probes"][0].__setitem__(
                "sampled_evidence_sha256", "b" * 64
            ),
            lambda row: row["probes"][0].__setitem__(
                "visual_review_status", "approved"
            ),
            lambda row: row["summary"].__setitem__(
                "gain_probe_count", 8
            ),
            lambda row: row.__setitem__("tracks", []),
            lambda row: row["source"].__setitem__("path", "private/input"),
        ):
            value = deepcopy(self.candidate.document)
            mutate(value)
            mutations.append(value)
        for value in mutations:
            with self.subTest(value=value), self.assertRaises(
                BodySwayAmplitudeEnvelopeValidationError
            ):
                require_body_sway_amplitude_envelope_candidate(value)

    def test_reviewed_probe_cannot_be_resealed_away_from_p10_report(self):
        forged = deepcopy(self.candidate.document)
        reviewed = forged["probes"][-1]
        reviewed["sample_stream_sha256"] = "f" * 64
        reviewed["sampled_evidence_sha256"] = (
            body_sway_amplitude_envelope_probe_sha256(reviewed)
        )
        with self.assertRaises(BodySwayAmplitudeEnvelopeValidationError):
            require_body_sway_amplitude_envelope_candidate(forged)
        self.assertNotIn("preview_projection_sha256", forged["source"])

    def test_reviewed_rejection_cannot_be_resealed_away_from_p10_report(self):
        forged = deepcopy(self.candidate.document)
        reviewed = forged["probes"][-1]
        reviewed["checks"][1].update({
            "status": "rejected",
            "reason_code": "sampled_check_rejected",
            "failure_count": 1,
        })
        reviewed["status"] = "sampled_structural_rejected"
        reviewed["sampled_evidence_sha256"] = (
            body_sway_amplitude_envelope_probe_sha256(reviewed)
        )
        summary = forged["summary"]
        summary["sampled_structural_passed_count"] -= 1
        summary["sampled_structural_rejected_count"] += 1
        summary["reviewed_gain_status"] = "sampled_structural_rejected"
        with self.assertRaises(BodySwayAmplitudeEnvelopeValidationError):
            require_body_sway_amplitude_envelope_candidate(forged)

    def test_input_and_compiler_fail_closed_on_spoofed_exact_values(self):
        with self.assertRaises(BodySwayAmplitudeEnvelopeInputError):
            require_body_sway_amplitude_envelope_inputs(
                object(), self.inputs.preview_inputs, self.inputs.preview
            )
        forged = replace(self.inputs, _preview=object())
        with self.assertRaises(BodySwayAmplitudeEnvelopeError):
            compile_body_sway_amplitude_envelope_candidate(forged)

    def test_canonical_hash_ignores_mapping_insertion_order(self):
        reordered = dict(reversed(list(self.candidate.document.items())))
        require_body_sway_amplitude_envelope_candidate(reordered)
        self.assertEqual(
            self.candidate.sha256,
            body_sway_amplitude_envelope_candidate_sha256(reordered),
        )

    def test_mutating_profile_results_cannot_escalate_candidate(self):
        claims = body_sway_amplitude_envelope_claims()
        claims["release_authority"] = True
        gate = body_sway_amplitude_envelope_release_gate()
        gate["status"] = "passed"
        gate["reason_codes"].clear()
        analyzer = body_sway_amplitude_envelope_analyzer_profile()
        analyzer["config"]["gain_grid"]["maximum_numerator"] = 80
        document = compile_body_sway_amplitude_envelope_candidate(
            self.inputs
        ).document
        self.assertFalse(document["claims"]["release_authority"])
        self.assertEqual("blocked", document["release_gate"]["status"])
        self.assertEqual(
            8, document["analyzer"]["config"]["gain_grid"][
                "maximum_numerator"
            ],
        )

    def test_decimal_gain_scaling_is_shared_and_not_prematurely_quantized(self):
        reviewed = [{"bone_id": "pelvis-spine", "value": 1.234567891}]
        self.assertEqual(
            0.154320986375,
            body_sway_scaled_amplitudes(reviewed, 1)[0]["value"],
        )
        self.assertEqual(
            reviewed, body_sway_scaled_amplitudes(reviewed, 8)
        )

    def test_document_budget_covers_both_embedded_upstream_contracts(self):
        self.assertEqual(
            MAX_PROBE_REPORT_BYTES
            + MAX_ADMISSION_DOCUMENT_BYTES
            + MAX_ENVELOPE_OWN_BYTES,
            MAX_ENVELOPE_DOCUMENT_BYTES,
        )
        self.assertGreater(MAX_ENVELOPE_OWN_BYTES, 0)

    @unittest.skipIf(Draft202012Validator is None, "jsonschema is optional")
    def test_json_schema_matches_bounded_semantics(self):
        schema = json.loads((
            ROOT / "schemas" /
            "body-sway-amplitude-envelope-candidate-v1.schema.json"
        ).read_text(encoding="utf-8"))
        admission_schema = json.loads((
            ROOT / "schemas" / "body-sway-review-admission-v1.schema.json"
        ).read_text(encoding="utf-8"))
        probe_schema = json.loads((
            ROOT / "schemas" / "body-sway-probe-report-v1.schema.json"
        ).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        registry = Registry().with_resources((
            (admission_schema["$id"], Resource.from_contents(admission_schema)),
            (probe_schema["$id"], Resource.from_contents(probe_schema)),
        ))
        validator = Draft202012Validator(schema, registry=registry)
        validator.validate(self.candidate.document)
        invalid = deepcopy(self.candidate.document)
        invalid["claims"]["continuous_time"] = True
        self.assertFalse(validator.is_valid(invalid))
        nested = deepcopy(self.candidate.document)
        nested["source"]["review_admission"]["claims"][
            "release_authority"
        ] = True
        self.assertFalse(validator.is_valid(nested))


if __name__ == "__main__":
    unittest.main()
