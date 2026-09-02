"""P10.4a canonical BodySwayReviewAdmission v2 contract tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional dependency
    Draft202012Validator = None

from autospine_workbench.body_sway_review_admission_profile import (  # noqa: E402
    admission_claims, admission_release_gate,
    body_sway_review_head_observation, compiler_profile,
)
from autospine_workbench.body_sway_review_admission_validation import (  # noqa: E402
    BodySwayReviewAdmissionValidationError,
    require_body_sway_review_admission,
)
from autospine_workbench.body_sway_review_admission_inputs_v2 import (  # noqa: E402
    BodySwayReviewAdmissionInputV2Error,
    build_body_sway_review_admission_input_v2,
    require_body_sway_review_admission_input_v2,
)
from autospine_workbench.body_sway_review_admission_v2 import (  # noqa: E402
    BodySwayReviewAdmissionV2Error, compile_body_sway_review_admission_v2,
)
from autospine_workbench.body_sway_review_admission_validation_v2 import (  # noqa: E402
    BodySwayReviewAdmissionV2ValidationError,
    body_sway_review_admission_sha256_v2,
    require_body_sway_review_admission_v2,
)
from autospine_workbench.body_sway_runtime_capture_v2 import (  # noqa: E402
    BodySwayRuntimeCaptureV2,
)
from autospine_workbench.body_sway_visual_review_address_v2 import (  # noqa: E402
    ExactVisualReviewAddressV2,
)
from autospine_workbench.body_sway_visual_review_decision_v2 import (  # noqa: E402
    build_body_sway_visual_review_decision_v2,
)
from autospine_workbench.body_sway_visual_review_history_snapshot_v2 import (  # noqa: E402
    BodySwayVisualReviewHistoryRowV2,
)
from autospine_workbench.p10_visual_review_v2_verified_mount import (  # noqa: E402
    VerifiedP10VisualReviewV2Mount,
)
from autospine_workbench.temporary_body_sway_preview_v2 import (  # noqa: E402
    TemporaryBodySwayPreviewV2,
)
from tests.body_sway_visual_review_v2_helpers import (  # noqa: E402
    fake_runtime_profile_v2, review_rows_v2,
)
from tests.p10_review_admission_v2_helpers import (  # noqa: E402
    build_admission_inputs, recursive_keys,
    shared_p10_review_admission_v2_fixture,
)


class BodySwayReviewAdmissionV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = shared_p10_review_admission_v2_fixture()

    def test_compiler_is_deterministic_path_free_and_exactly_bound(self):
        with fake_runtime_profile_v2():
            repeated = compile_body_sway_review_admission_v2(
                self.fixture.inputs,
            )
        admission = self.fixture.admission
        document = admission.document
        self.assertEqual(admission.canonical_bytes, repeated.canonical_bytes)
        self.assertEqual(admission.sha256, repeated.sha256)
        self.assertEqual(
            admission.sha256,
            body_sway_review_admission_sha256_v2(document),
        )
        self.assertNotIn("path", recursive_keys(document))
        self.assertEqual(
            self.fixture.context.job_head_event_sha256,
            document["source"]["job"]["terminal_event_sha256"],
        )
        self.assertEqual(
            self.fixture.execution.execution.sha256,
            document["source"]["execution"]["runtime_execution_sha256"],
        )
        self.assertEqual(
            self.fixture.approved.decision_sha256,
            document["source"]["visual_review"]
                    ["head_decision_v2_sha256"],
        )

    def test_schema_and_semantic_validators_are_version_disjoint(self):
        v2 = self.fixture.admission.document
        v1 = _v1_from_v2(v2)
        require_body_sway_review_admission(v1)
        require_body_sway_review_admission_v2(v2)
        with self.assertRaises(BodySwayReviewAdmissionValidationError):
            require_body_sway_review_admission(v2)
        with self.assertRaises(BodySwayReviewAdmissionV2ValidationError):
            require_body_sway_review_admission_v2(v1)
        if Draft202012Validator is None:
            self.skipTest("jsonschema is optional")
        v1_schema = _schema("body-sway-review-admission-v1.schema.json")
        v2_schema = _schema("body-sway-review-admission-v2.schema.json")
        Draft202012Validator.check_schema(v1_schema)
        Draft202012Validator.check_schema(v2_schema)
        v1_validator = Draft202012Validator(v1_schema)
        v2_validator = Draft202012Validator(v2_schema)
        v1_validator.validate(v1)
        v2_validator.validate(v2)
        self.assertFalse(v1_validator.is_valid(v2))
        self.assertFalse(v2_validator.is_valid(v1))

    def test_validator_rejects_paths_claim_escalation_and_gate_escalation(self):
        variants = []
        path = deepcopy(self.fixture.admission.document)
        path["source"]["execution"]["path"] = "C:/private/evidence"
        variants.append(path)
        claim = deepcopy(self.fixture.admission.document)
        claim["claims"]["release_authority"] = True
        variants.append(claim)
        weakened = deepcopy(self.fixture.admission.document)
        weakened["claims"]["completed_sampled_execution_bound"] = False
        variants.append(weakened)
        gate = deepcopy(self.fixture.admission.document)
        gate["release_gate"] = {"status": "passed", "reason_codes": []}
        variants.append(gate)
        for document in variants:
            with self.subTest(document=document), self.assertRaises(
                BodySwayReviewAdmissionV2ValidationError
            ):
                require_body_sway_review_admission_v2(document)

    def test_approved_head_explicitly_approves_every_sampled_frame(self):
        candidate = self.fixture.inputs.candidate_document
        decision = self.fixture.inputs.decision_document
        candidate_ids = [row["case_id"] for row in candidate["cases"]]
        decision_ids = [row["case_id"] for row in decision["decisions"]]
        self.assertGreater(len(candidate_ids), 1)
        self.assertEqual(candidate_ids, decision_ids)
        self.assertTrue(all(
            row["action"] == "approve" for row in decision["decisions"]
        ))
        self.assertEqual("sampled_visual_approved", decision["status"])
        self.assertEqual(
            "sampled_visual_approved",
            self.fixture.inputs.history_before.rows[-1].status,
        )
        self.assertEqual(
            self.fixture.inputs.history_before,
            self.fixture.inputs.history_after,
        )

    def test_context_a_b_job_event_and_address_drift_fail_closed(self):
        context = self.fixture.context
        changed_address = ExactVisualReviewAddressV2(
            "other-project", context.address.temporary_preview_v2_sha256,
            context.address.runtime_execution_bundle_sha256,
            context.address.capture_artifact_set_sha256,
        )
        variants = (
            replace(context, job_id="0" * 64),
            replace(context, package_id="other-package"),
            replace(context, job_head_event_sha256="1" * 64),
            replace(context, job_event_count=context.job_event_count + 1),
            replace(context, address=changed_address),
        )
        for changed in variants:
            with self.subTest(changed=changed), self.assertRaises(
                BodySwayReviewAdmissionInputV2Error
            ):
                build_admission_inputs(
                    self.fixture, context_after=changed,
                )

    def test_context_a_b_preview_and_execution_bytes_drift_fail_closed(self):
        fixture = self.fixture
        preview = TemporaryBodySwayPreviewV2(
            fixture.preview._canonical_json + " ",
            fixture.preview._artifact_items,
        )
        result = replace(fixture.mount.result, _preview=preview)
        preview_mount = VerifiedP10VisualReviewV2Mount(
            type(fixture.mount.record)(result=result), fixture.execution,
        )
        execution_value = replace(
            fixture.execution.execution,
            _canonical_json=fixture.execution.execution._canonical_json + " ",
        )
        execution = replace(fixture.execution, execution=execution_value)
        execution_mount = VerifiedP10VisualReviewV2Mount(
            fixture.mount.record, execution,
        )
        capture = fixture.execution.execution.capture
        changed_capture = BodySwayRuntimeCaptureV2(
            capture._canonical_json,
            capture._capture_items + (("captures/unbound.png", b"drift"),),
        )
        capture_execution = replace(
            fixture.execution.execution, _capture=changed_capture,
        )
        capture_mount = VerifiedP10VisualReviewV2Mount(
            fixture.mount.record,
            replace(fixture.execution, execution=capture_execution),
        )
        for mount in (preview_mount, execution_mount, capture_mount):
            changed = replace(fixture.context, preview=mount)
            with self.subTest(mount=mount), self.assertRaises(
                BodySwayReviewAdmissionInputV2Error
            ):
                build_admission_inputs(
                    fixture, context_after=changed,
                )

    def test_builder_requires_exact_values_and_rejects_old_snapshot(self):
        with self.assertRaises(BodySwayReviewAdmissionInputV2Error):
            build_body_sway_review_admission_input_v2(
                object(), self.fixture.before, self.fixture.exact,
                self.fixture.context, self.fixture.after,
                candidate_sha256=self.fixture.approved.candidate_sha256,
                revision=self.fixture.approved.revision,
                decision_sha256=self.fixture.approved.decision_sha256,
            )
        stale = replace(
            self.fixture.after,
            history=replace(
                self.fixture.after.history,
                head_decision_sha256="f" * 64,
            ),
        )
        with fake_runtime_profile_v2(), self.assertRaises(
            BodySwayReviewAdmissionInputV2Error
        ):
            build_admission_inputs(self.fixture, after=stale)

    def test_pure_compiler_rejects_detached_completed_job_forgery(self):
        value = self.fixture.inputs
        changed = ExactVisualReviewAddressV2(
            "other-project", value.address.temporary_preview_v2_sha256,
            value.address.runtime_execution_bundle_sha256,
            value.address.capture_artifact_set_sha256,
        )
        variants = (
            replace(value, job_id="0" * 64),
            replace(value, package_id="f" * 64),
            replace(value, job_terminal_event_sha256="1" * 64),
            replace(
                value,
                job_terminal_sequence=value.job_terminal_sequence + 1,
            ),
            replace(value, address=changed),
            replace(
                value,
                _completed_job=replace(
                    value._completed_job,
                    _events=value._completed_job._events[:-1],
                ),
            ),
        )
        for forged in variants:
            with self.subTest(forged=forged), fake_runtime_profile_v2(), \
                    self.assertRaises(BodySwayReviewAdmissionV2Error):
                compile_body_sway_review_admission_v2(forged)

    def test_package_id_is_sha256_in_semantic_and_schema_contracts(self):
        document = deepcopy(self.fixture.admission.document)
        document["source"]["job"]["package_id"] = "legacy-token"
        with self.assertRaises(BodySwayReviewAdmissionV2ValidationError):
            require_body_sway_review_admission_v2(document)
        if Draft202012Validator is not None:
            validator = Draft202012Validator(
                _schema("body-sway-review-admission-v2.schema.json")
            )
            self.assertFalse(validator.is_valid(document))

    def test_rejected_unobservable_and_old_approved_heads_are_inadmissible(self):
        fixture = self.fixture
        candidate = json.loads(fixture.before._candidate_json)
        previous = fixture.inputs.decision_document
        rejected_inputs = []
        for action in ("reject", "unobservable"):
            decision = build_body_sway_visual_review_decision_v2(
                candidate,
                review={
                    "reviewer_id": "p10-v2-admission-test",
                    "notes": f"explicit {action}",
                },
                decisions=review_rows_v2(candidate, action=action),
                previous_decision=previous,
            )
            history = _append_history(
                fixture.inputs.history_before, decision.sha256,
                decision.document["status"],
            )
            rejected_inputs.append(replace(
                fixture.inputs,
                visual_revision=2,
                visual_decision_sha256=decision.sha256,
                history_before=history, history_after=history,
                _decision_json=decision.canonical_bytes.decode("utf-8"),
            ))
        current_history = rejected_inputs[0].history_before
        old_head = replace(
            fixture.inputs,
            history_before=current_history, history_after=current_history,
        )
        for value in (*rejected_inputs, old_head):
            with self.subTest(value=value), fake_runtime_profile_v2(), \
                    self.assertRaises(BodySwayReviewAdmissionInputV2Error):
                require_body_sway_review_admission_input_v2(value)


def _schema(name: str):
    return json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))


def _v1_from_v2(v2):
    preview = v2["source"]["preview_source"]
    evidence = v2["source"]["evidence"]
    visual = v2["source"]["visual_review"]
    revision = visual["revision"]
    decision = visual["decision_v2_sha256"]
    chain_fields = (
        "body_sway_probe_report_sha256",
        "idle_behavior_candidates_sha256",
        "idle_behavior_decision_sha256", "layer_manifest_sha256",
        "p3", "p5", "p9",
    )
    return {
        "format": "autospine-body-sway-review-admission",
        "format_version": 1,
        "project_id": v2["project_id"], "clip_id": v2["clip_id"],
        "source": {
            "p10_chain": {field: deepcopy(preview[field])
                          for field in chain_fields},
            "capture": {
                "project_id": v2["project_id"],
                "temporary_preview_sha256":
                    evidence["temporary_preview_v2_sha256"],
                "runtime_capture_manifest_sha256":
                    evidence["runtime_capture_v2_sha256"],
                "runtime_capture_bundle_sha256":
                    evidence["runtime_execution_bundle_sha256"],
                "capture_artifact_set_sha256":
                    evidence["capture_artifact_set_sha256"],
                "preview_artifact_set_sha256":
                    evidence["preview_artifact_set_sha256"],
            },
            "visual_review": {
                "candidate_sha256": visual["candidate_v2_sha256"],
                "revision": revision,
                "decision_sha256": decision,
                "head_decision_sha256": decision,
            },
        },
        "timing": deepcopy(v2["timing"]),
        "selection": deepcopy(v2["selection"]),
        "head_observation": body_sway_review_head_observation(
            revision, decision,
        ),
        "compiler": compiler_profile(), "claims": admission_claims(),
        "status": "admitted_for_safety_analysis",
        "release_gate": admission_release_gate(),
    }


def _append_history(history, decision_sha256, status):
    row = BodySwayVisualReviewHistoryRowV2(
        history.current_revision + 1, decision_sha256, status,
    )
    return replace(
        history,
        revision_count=history.revision_count + 1,
        current_revision=history.current_revision + 1,
        head_decision_sha256=decision_sha256,
        rows=history.rows + (row,),
    )


if __name__ == "__main__":
    unittest.main()
