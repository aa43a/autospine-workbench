"""Adversarial Schema and sealed-validator checks for P10.4b v2."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
for item in (ROOT, ROOT / "src"):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from jsonschema import Draft202012Validator  # noqa: E402
from referencing import Registry, Resource  # noqa: E402

from autospine_workbench.body_sway_amplitude_envelope_v2 import (  # noqa: E402
    compile_body_sway_amplitude_envelope_candidate_v2,
)
from autospine_workbench.body_sway_amplitude_envelope_validation import (  # noqa: E402
    BodySwayAmplitudeEnvelopeValidationError,
    require_body_sway_amplitude_envelope_candidate,
)
from autospine_workbench.body_sway_amplitude_envelope_validation_v2 import (  # noqa: E402
    BodySwayAmplitudeEnvelopeValidationV2Error,
    body_sway_amplitude_envelope_candidate_sha256_v2,
    body_sway_amplitude_envelope_probe_sha256_v2,
    require_body_sway_amplitude_envelope_candidate_v2,
)
from autospine_workbench.body_sway_continuous_interval import (  # noqa: E402
    BodySwayContinuousIntervalError,
)
from autospine_workbench.body_sway_continuous_proof import (  # noqa: E402
    BodySwayContinuousProofValidationError,
    require_body_sway_continuous_proof,
)
from autospine_workbench.body_sway_continuous_proof_profile_v2 import (  # noqa: E402
    continuous_claims_v2, continuous_problem_sha256_v2,
    continuous_release_gate_v2, continuous_segment_sha256_v2,
    continuous_source_sha256_v2,
)
from autospine_workbench.body_sway_continuous_proof_v2 import (  # noqa: E402
    compile_body_sway_continuous_preview_proof_v2,
)
from autospine_workbench.body_sway_continuous_proof_validation_v2 import (  # noqa: E402
    BodySwayContinuousProofValidationV2Error,
    require_sealed_body_sway_continuous_preview_proof_v2,
)
from autospine_workbench.body_sway_dynamic_seam_source import (  # noqa: E402
    BodySwayDynamicSeamSourceError, build_body_sway_dynamic_seam_source,
)
from autospine_workbench.body_sway_preview_projection_v2 import (  # noqa: E402
    compile_body_sway_preview_projection_v2,
)
from autospine_workbench.body_sway_review_admission_consumer_v2 import (  # noqa: E402
    CurrentBodySwayReviewAdmissionV2,
)
from autospine_workbench.p10_review_admission_v2_commands import (  # noqa: E402
    _result,
)
from autospine_workbench.p10_safety_analysis_source_v2 import (  # noqa: E402
    P10SafetyAnalysisSourceV2,
)
from tests.p10_review_admission_v2_helpers import (  # noqa: E402
    shared_p10_review_admission_v2_fixture,
)


def _validator(name):
    registry = Registry()
    for path in (ROOT / "schemas").glob("*.schema.json"):
        schema = json.loads(path.read_text(encoding="utf-8"))
        if "$id" in schema:
            registry = registry.with_resource(
                schema["$id"], Resource.from_contents(schema),
            )
    schema = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, registry=registry)


class P10SafetyAnalysisV2ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = shared_p10_review_admission_v2_fixture()
        command = _result(fixture.inputs, fixture.admission)
        admission = CurrentBodySwayReviewAdmissionV2(
            command.admission_sha256, command,
        )
        source = P10SafetyAnalysisSourceV2(
            fixture.context.package_id,
            SimpleNamespace(result=fixture.preview_result),
            fixture.preview_inputs,
            compile_body_sway_preview_projection_v2(fixture.preview_inputs),
            fixture.mesh_bundle,
        )
        amplitude = compile_body_sway_amplitude_envelope_candidate_v2(
            admission, source,
        )
        with patch(
            "autospine_workbench.body_sway_continuous_proof_v2."
            "prove_body_sway_sampled_linear_segment",
            side_effect=BodySwayContinuousIntervalError("forced"),
        ):
            continuous = compile_body_sway_continuous_preview_proof_v2(
                amplitude, source,
            )
        cls.amplitude = amplitude.document
        cls.continuous = continuous.document
        cls.amplitude_schema = _validator(
            "body-sway-amplitude-envelope-candidate-v2.schema.json"
        )
        cls.continuous_schema = _validator(
            "body-sway-continuous-preview-proof-v2.schema.json"
        )

    def test_exact_documents_pass_schema_and_sealed_semantics(self):
        self.amplitude_schema.validate(self.amplitude)
        self.continuous_schema.validate(self.continuous)
        require_body_sway_amplitude_envelope_candidate_v2(self.amplitude)
        require_sealed_body_sway_continuous_preview_proof_v2(self.continuous)

    def test_amplitude_schema_rejects_nested_overclaim_and_mismatch(self):
        attacks = []
        for name, mutate in (
            ("timing-extra", lambda row: row["timing"].__setitem__("release_authority", True)),
            ("selection-extra", lambda row: row["reviewed_selection"].__setitem__(
                "publishable_timeline", True
            )),
            ("parameterization-extra", lambda row: row["parameterization"].__setitem__(
                "safe_range", True
            )),
            ("check-extra", lambda row: row["probes"][0]["checks"][0].__setitem__(
                "release_authority", True
            )),
            ("gain-order", lambda row: row["probes"][0]["gain"].__setitem__("numerator", 1)),
            ("summary-status-count", lambda row: row["summary"].__setitem__(
                "sampled_structural_passed_count", 9
            )),
        ):
            value = deepcopy(self.amplitude)
            mutate(value)
            attacks.append((name, value))
        for name, value in attacks:
            with self.subTest(attack=name):
                self.assertFalse(self.amplitude_schema.is_valid(value))

    def test_amplitude_semantics_reject_resealed_detachment(self):
        attacks = []
        malformed_schedule = deepcopy(self.amplitude)
        for probe in malformed_schedule["probes"]:
            probe["tick_schedule_sha256"] = "not-a-digest"
            probe["sampled_evidence_sha256"] = (
                body_sway_amplitude_envelope_probe_sha256_v2(probe)
            )
        attacks.append(malformed_schedule)
        malformed_stream = deepcopy(self.amplitude)
        malformed_stream["probes"][0]["sample_stream_sha256"] = "bad"
        malformed_stream["probes"][0]["sampled_evidence_sha256"] = (
            body_sway_amplitude_envelope_probe_sha256_v2(
                malformed_stream["probes"][0]
            )
        )
        attacks.append(malformed_stream)
        detached_checks = deepcopy(self.amplitude)
        detached_checks["probes"][-1]["checks"][1][
            "evidence_sha256"
        ] = "a" * 64
        detached_checks["probes"][-1]["sampled_evidence_sha256"] = (
            body_sway_amplitude_envelope_probe_sha256_v2(
                detached_checks["probes"][-1]
            )
        )
        attacks.append(detached_checks)
        version = deepcopy(self.amplitude)
        version["format_version"] = 2.0
        attacks.append(version)
        for value in attacks:
            with self.subTest(value=value), self.assertRaises(
                BodySwayAmplitudeEnvelopeValidationV2Error
            ):
                require_body_sway_amplitude_envelope_candidate_v2(value)

    def test_continuous_schema_rejects_projection_and_summary_overclaim(self):
        attacks = []
        for name, mutate in (
            ("projection-extra", lambda row: row["source"]["preview_projection_v2"].__setitem__(
                "release_authority", True
            )),
            ("backend-method", lambda row: row["problem"]["backend"].__setitem__(
                "method", "point-sampling"
            )),
            ("segment-scope", lambda row: row["segments"][0]["scope"].append("visual_safety")),
        ):
            value = deepcopy(self.continuous)
            mutate(value)
            attacks.append((name, value))
        certified = deepcopy(self.continuous)
        certified["status"] = "continuous_preview_model_structural_certified"
        certified["claims"] = continuous_claims_v2(True)
        certified["release_gate"] = continuous_release_gate_v2(True)
        attacks.append(("certified-overclaim", certified))
        for name, value in attacks:
            with self.subTest(attack=name):
                self.assertFalse(self.continuous_schema.is_valid(value))

    def test_sealed_validator_rejects_resealed_identity_and_segment(self):
        projection = deepcopy(self.continuous)
        candidate = projection["source"]["amplitude_envelope_candidate_v2"]
        candidate["source"]["preview_projection_v2_sha256"] = "a" * 64
        projection["source"]["amplitude_envelope_candidate_v2_sha256"] = (
            body_sway_amplitude_envelope_candidate_sha256_v2(candidate)
        )
        projection["source"]["source_set_sha256"] = (
            continuous_source_sha256_v2(projection["source"])
        )
        projection["problem"]["source_set_sha256"] = projection["source"][
            "source_set_sha256"
        ]
        projection["problem"]["problem_sha256"] = (
            continuous_problem_sha256_v2(projection["problem"])
        )
        segment = deepcopy(self.continuous)
        segment["segments"][0]["bounds"]["canvas_margin_lower_px"] = 0.0
        segment["segments"][0]["segment_evidence_sha256"] = (
            continuous_segment_sha256_v2(segment["segments"][0])
        )
        summary = deepcopy(self.continuous)
        summary["summary"]["segment_count"] = 1
        version = deepcopy(self.continuous)
        version["format_version"] = 2.0
        for name, value in (
            ("projection-identity", projection),
            ("segment-evidence", segment),
            ("summary-count", summary),
            ("format-version-type", version),
        ):
            with self.subTest(attack=name), self.assertRaises(
                BodySwayContinuousProofValidationV2Error
            ):
                require_sealed_body_sway_continuous_preview_proof_v2(value)

    def test_v1_and_p105_consumers_reject_v2_documents(self):
        with self.assertRaises(BodySwayAmplitudeEnvelopeValidationError):
            require_body_sway_amplitude_envelope_candidate(self.amplitude)
        with self.assertRaises(BodySwayContinuousProofValidationError):
            require_body_sway_continuous_proof(self.continuous)
        with self.assertRaises(BodySwayDynamicSeamSourceError):
            build_body_sway_dynamic_seam_source(
                continuous_proof=self.continuous,
                seam_anchor_candidates={}, seam_anchor_review_decision={},
                reviewed_seam_anchor_set={},
                reviewed_set_bundle_sha256="b" * 64,
            )


if __name__ == "__main__":
    unittest.main()
