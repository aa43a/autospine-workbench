"""Exact-source, recomputation, and overclaim tests for P10.4b2."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from unittest.mock import patch
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

from autospine_workbench.body_sway_continuous_interval import (  # noqa: E402
    BodySwayContinuousIntervalError,
    BodySwayContinuousIntervalProof,
    BodySwayIntervalProofBudget,
    prove_body_sway_sampled_linear_segment,
)
from autospine_workbench.body_sway_continuous_interval_geometry import (  # noqa: E402
    BodySwayIntervalGeometryBounds,
)
from autospine_workbench.body_sway_probe_geometry_context import (  # noqa: E402
    PreparedBodySwayMesh,
    prepare_body_sway_geometry_context,
)
from autospine_workbench.body_sway_continuous_backend_validation import (  # noqa: E402
    BodySwayContinuousBackendValidationError,
    require_body_sway_interval_backend_result,
)
from autospine_workbench.body_sway_continuous_proof import (  # noqa: E402
    BodySwayContinuousProofError,
    compile_body_sway_continuous_preview_proof,
)
from autospine_workbench.body_sway_continuous_proof_analysis import (  # noqa: E402
    analyze_body_sway_continuous_source,
)
from autospine_workbench.body_sway_continuous_proof_inputs import (  # noqa: E402
    BodySwayContinuousProofInputError,
    require_body_sway_continuous_proof_inputs,
)
from autospine_workbench.body_sway_continuous_proof_profile import (  # noqa: E402
    MAX_DOCUMENT_BYTES,
    MAX_ENVELOPE_DOCUMENT_BYTES,
    MAX_MOTION_INSTANCE_V2_BYTES,
    MAX_PREVIEW_PROJECTION_BYTES,
    MAX_PROOF_OWN_BYTES,
    MAX_RIG_IR_BYTES,
    MAX_TARGET_PROFILE_BYTES,
    MAX_TEMPORARY_PREVIEW_BYTES,
    body_sway_continuous_problem_sha256,
    body_sway_continuous_proof_release_gate,
    body_sway_continuous_segment_sha256,
    body_sway_continuous_source_sha256,
)
from autospine_workbench.body_sway_continuous_proof_validation import (  # noqa: E402
    BodySwayContinuousProofValidationError,
    body_sway_continuous_proof_sha256,
    require_body_sway_continuous_proof,
)
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from tests.body_sway_continuous_proof_helpers import (  # noqa: E402
    admitted_continuous_proof_inputs,
)
from tests.body_sway_probe_geometry_helpers import (  # noqa: E402
    exact_rig_and_target,
    rebound,
)
from tests.p10_review_admission_helpers import (  # noqa: E402
    P10ReviewAdmissionFixture,
)


class BodySwayContinuousProofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = P10ReviewAdmissionFixture(Path(cls.temporary.name))
        cls.inputs = admitted_continuous_proof_inputs(cls.fixture)
        cls.proof = compile_body_sway_continuous_preview_proof(cls.inputs)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_full_adjacent_schedule_is_bound_and_deterministic(self):
        document = self.proof.document
        ticks = document["source"]["preview_projection"]["sample_ticks"]
        pairs = list(zip(ticks, ticks[1:]))
        self.assertEqual(pairs, [
            (row["left_tick"], row["right_tick"])
            for row in document["segments"]
        ])
        self.assertEqual(len(pairs), document["summary"]["segment_count"])
        self.assertEqual([0, 1], [
            document["problem"]["gain_domain"][key]["numerator"]
            for key in ("minimum", "maximum")
        ])
        certified = all(
            row["status"] == "continuous_structural_certified"
            for row in document["segments"]
        )
        self.assertEqual(
            certified,
            document["claims"][
                "continuous_preview_model_structural_safety"
            ],
        )
        self.assertEqual(
            certified,
            document["claims"][
                "uniform_gain_zero_to_reviewed_structurally_certified"
            ],
        )
        self.assertEqual("blocked", document["release_gate"]["status"])
        self.assertFalse(document["claims"]["runtime_equivalence"])
        self.assertFalse(document["claims"]["visual_range"])
        self.assertFalse(document["claims"]["reviewed_seam_anchors"])
        self.assertFalse(document["claims"]["motion_instance_v3"])
        self.assertFalse(document["claims"]["publishable_timeline"])
        self.assertFalse(document["claims"]["release_authority"])
        self.assertEqual(
            self.proof.sha256, body_sway_continuous_proof_sha256(document)
        )

    def test_source_recomputes_all_identities_and_upstream_chain(self):
        source = self.proof.document["source"]
        self.assertEqual(
            body_sway_continuous_source_sha256(source),
            source["source_set_sha256"],
        )
        self.assertEqual(
            canonical_sha256(source["rig_ir"]), source["rig_ir_sha256"]
        )
        self.assertEqual(
            canonical_sha256(source["target_profile"]),
            source["target_profile_sha256"],
        )
        self.assertEqual(
            canonical_sha256(source["temporary_preview_manifest"]),
            source["temporary_preview_manifest_sha256"],
        )
        self.assertEqual(
            canonical_sha256(source["preview_projection"]),
            source["preview_projection_sha256"],
        )

    def test_resealed_source_problem_and_segment_attacks_are_rejected(self):
        attacks = []
        source_attack = deepcopy(self.proof.document)
        source = source_attack["source"]
        source["rig_ir"]["bones"][0]["setup"]["x"] += 0.125
        source["rig_ir_sha256"] = canonical_sha256(source["rig_ir"])
        source["source_set_sha256"] = body_sway_continuous_source_sha256(
            source
        )
        source_attack["problem"]["source_set_sha256"] = source[
            "source_set_sha256"
        ]
        source_attack["problem"]["problem_sha256"] = (
            body_sway_continuous_problem_sha256(source_attack["problem"])
        )
        attacks.append(source_attack)

        problem_attack = deepcopy(self.proof.document)
        problem_attack["problem"]["gain_domain"]["maximum"]["numerator"] = 2
        problem_attack["problem"]["problem_sha256"] = (
            body_sway_continuous_problem_sha256(problem_attack["problem"])
        )
        attacks.append(problem_attack)

        segment_attack = deepcopy(self.proof.document)
        segment = segment_attack["segments"][0]
        margin = segment["bounds"]["canvas_margin_lower_px"]
        segment["bounds"]["canvas_margin_lower_px"] = (
            0.0 if margin is None else margin + 0.125
        )
        segment["segment_evidence_sha256"] = (
            body_sway_continuous_segment_sha256(segment)
        )
        attacks.append(segment_attack)

        claim_attack = deepcopy(self.proof.document)
        claim_attack["claims"]["release_authority"] = True
        attacks.append(claim_attack)

        for attack in attacks:
            with self.subTest(attack=attack), self.assertRaises(
                BodySwayContinuousProofValidationError
            ):
                require_body_sway_continuous_proof(attack)

    def test_interval_backend_failure_is_indeterminate_without_witness(self):
        with patch(
            "autospine_workbench.body_sway_continuous_proof_analysis."
            "prove_body_sway_sampled_linear_segment",
            side_effect=BodySwayContinuousIntervalError("forced"),
        ) as mocked:
            analysis = analyze_body_sway_continuous_source(
                self.inputs.source
            ).document
        self.assertEqual("indeterminate", analysis["status"])
        self.assertFalse(analysis["claims"][
            "continuous_preview_model_structural_safety"
        ])
        self.assertEqual(1, mocked.call_count)
        self.assertEqual(
            ["interval_backend_error"],
            analysis["segments"][0]["reason_codes"],
        )
        self.assertTrue(all(
            row["reason_codes"] == [
                "global_subdivision_box_budget_exhausted"
            ]
            for row in analysis["segments"][1:]
        ))
        self.assertNotIn("counterexample", analysis)

    def test_global_box_budget_is_shared_by_all_segments(self):
        def exhaust(context, left, right, *, budget):
            meshes = [row for row in context.attachments
                      if type(row) is PreparedBodySwayMesh]
            evaluated = budget.max_boxes \
                if budget.max_boxes % 2 else budget.max_boxes - 1
            terminal = (evaluated + 1) // 2
            return BodySwayContinuousIntervalProof(
                left_tick=left.tick, right_tick=right.tick,
                status="indeterminate",
                reason_codes=("subdivision_box_budget_exhausted",),
                bounds=BodySwayIntervalGeometryBounds(
                    -1.0,
                    0.0 if meshes else None,
                    100.0 if meshes else None,
                    100.0 if meshes else None,
                ),
                evaluated_box_count=evaluated,
                certified_terminal_box_count=terminal - 1,
                indeterminate_terminal_box_count=1,
                maximum_depth_reached=0,
                attachment_count=len(context.attachments),
                vertex_count=sum(len(row.setup_vertices_xy)
                                 for row in context.attachments),
                triangle_count=sum(len(row.deformation.triangles)
                                   for row in meshes),
                edge_count=sum(len(row.deformation.edges) for row in meshes),
            )

        with patch(
            "autospine_workbench.body_sway_continuous_proof_analysis."
            "prove_body_sway_sampled_linear_segment",
            side_effect=exhaust,
        ) as mocked:
            analysis = analyze_body_sway_continuous_source(
                self.inputs.source
            ).document
        self.assertEqual(2, mocked.call_count)
        self.assertLessEqual(
            analysis["summary"]["evaluated_box_count"], 32_768
        )
        self.assertIn(
            "global_subdivision_box_budget_exhausted",
            analysis["segments"][2]["reason_codes"],
        )
        self.assertIn(
            "continuous_preview_model_safety_unproven",
            body_sway_continuous_proof_release_gate(False)["reason_codes"],
        )
        self.assertNotIn(
            "continuous_preview_model_safety_unproven",
            body_sway_continuous_proof_release_gate(True)["reason_codes"],
        )

    def test_forged_certified_tiny_absolute_area_is_rejected(self):
        rig, target = exact_rig_and_target()
        mesh = next(row for row in rig["attachments"]
                    if row["type"] == "mesh")
        x, y = mesh["vertices"][0]
        mesh["vertices"] = [
            [x, y], [x + 4e-6, y], [x, y + 2e-6],
        ]
        rebound(rig, target)
        context = prepare_body_sway_geometry_context(rig, target)
        meshes = [row for row in context.attachments
                  if type(row) is PreparedBodySwayMesh]
        proof = BodySwayContinuousIntervalProof(
            left_tick=0, right_tick=1,
            status="continuous_structural_certified", reason_codes=(),
            bounds=BodySwayIntervalGeometryBounds(1.0, 0.1, 1.0, 1.0),
            evaluated_box_count=1, certified_terminal_box_count=1,
            indeterminate_terminal_box_count=0, maximum_depth_reached=0,
            attachment_count=len(context.attachments),
            vertex_count=sum(len(row.setup_vertices_xy)
                             for row in context.attachments),
            triangle_count=sum(len(row.deformation.triangles)
                               for row in meshes),
            edge_count=sum(len(row.deformation.edges) for row in meshes),
        )
        with self.assertRaisesRegex(
            BodySwayContinuousBackendValidationError,
            "absolute triangle area",
        ):
            require_body_sway_interval_backend_result(
                proof, context=context, left_tick=0, right_tick=1,
                budget=BodySwayIntervalProofBudget(),
            )

    def test_malformed_interval_backend_returns_fail_closed(self):
        def unsafe_certified(proof, _budget):
            bounds = replace(proof.bounds, canvas_margin_lower_px=-0.01)
            return replace(
                proof, status="continuous_structural_certified",
                reason_codes=(), bounds=bounds,
                evaluated_box_count=1,
                certified_terminal_box_count=1,
                indeterminate_terminal_box_count=0,
                maximum_depth_reached=0,
            )

        mutations = (
            lambda proof, _budget: replace(
                proof, left_tick=proof.left_tick + 1
            ),
            lambda proof, _budget: replace(proof, status="forged"),
            lambda proof, _budget: replace(
                proof, reason_codes=("unknown_backend_reason",)
            ),
            lambda proof, budget: replace(
                proof, evaluated_box_count=budget.max_boxes + 1
            ),
            lambda proof, budget: replace(
                proof, maximum_depth_reached=budget.max_depth + 1
            ),
            lambda proof, _budget: replace(
                proof, attachment_count=proof.attachment_count + 1
            ),
            lambda proof, _budget: replace(
                proof, bounds=replace(
                    proof.bounds, canvas_margin_lower_px=float("nan")
                )
            ),
            unsafe_certified,
        )
        for mutate in mutations:
            def malformed(context, left, right, *, budget):
                proof = prove_body_sway_sampled_linear_segment(
                    context, left, right, budget=budget
                )
                return mutate(proof, budget)

            with self.subTest(mutate=mutate), patch(
                "autospine_workbench.body_sway_continuous_proof_analysis."
                "prove_body_sway_sampled_linear_segment",
                side_effect=malformed,
            ) as mocked:
                analysis = analyze_body_sway_continuous_source(
                    self.inputs.source
                ).document
            self.assertEqual(1, mocked.call_count)
            self.assertEqual("indeterminate", analysis["status"])
            self.assertEqual(
                ["interval_backend_error"],
                analysis["segments"][0]["reason_codes"],
            )
            self.assertTrue(all(
                row["reason_codes"] == [
                    "global_subdivision_box_budget_exhausted"
                ]
                for row in analysis["segments"][1:]
            ))
            self.assertFalse(analysis["claims"][
                "continuous_preview_model_structural_safety"
            ])

    def test_oversized_and_non_json_inputs_stop_before_analyzer(self):
        oversized = (
            {"padding": "x" * 2_048},
            {"segments": [{"reason_codes": ["x" * 2_048]}]},
        )
        for value in oversized:
            with self.subTest(value=list(value)), patch(
                "autospine_workbench.body_sway_continuous_proof_validation."
                "MAX_DOCUMENT_BYTES", 512,
            ), patch(
                "autospine_workbench.body_sway_continuous_proof_validation."
                "analyze_body_sway_continuous_source"
            ) as analyzer, self.assertRaisesRegex(
                BodySwayContinuousProofValidationError,
                "exceeds its byte limit",
            ):
                require_body_sway_continuous_proof(value)
            analyzer.assert_not_called()

        for value in ({"value": float("nan")}, {"value": object()}):
            with self.subTest(value=type(value["value"]).__name__), patch(
                "autospine_workbench.body_sway_continuous_proof_validation."
                "analyze_body_sway_continuous_source"
            ) as analyzer, self.assertRaises(
                BodySwayContinuousProofValidationError
            ):
                require_body_sway_continuous_proof(value)
            analyzer.assert_not_called()

    def test_exact_input_types_fail_closed(self):
        with self.assertRaises(BodySwayContinuousProofInputError):
            require_body_sway_continuous_proof_inputs(
                object(), self.inputs.amplitude_inputs
            )
        forged = replace(self.inputs, _amplitude_candidate=object())
        with self.assertRaises(BodySwayContinuousProofError):
            compile_body_sway_continuous_preview_proof(forged)

    def test_document_budget_is_explicit_sum_of_embedded_ceilings(self):
        self.assertEqual(
            MAX_ENVELOPE_DOCUMENT_BYTES + MAX_RIG_IR_BYTES
            + MAX_TARGET_PROFILE_BYTES + MAX_MOTION_INSTANCE_V2_BYTES
            + MAX_TEMPORARY_PREVIEW_BYTES + MAX_PREVIEW_PROJECTION_BYTES
            + MAX_PROOF_OWN_BYTES,
            MAX_DOCUMENT_BYTES,
        )

    @unittest.skipIf(Draft202012Validator is None, "jsonschema is optional")
    def test_json_schema_accepts_exact_document_and_blocks_overclaim(self):
        names = (
            "body-sway-continuous-preview-proof-v1.schema.json",
            "body-sway-amplitude-envelope-candidate-v1.schema.json",
            "body-sway-review-admission-v1.schema.json",
            "body-sway-probe-report-v1.schema.json",
            "rig-ir-v1.schema.json", "motion-target-profile-v1.schema.json",
            "motion-instance-v2.schema.json",
            "temporary-body-sway-preview-v1.schema.json",
        )
        schemas = [json.loads((ROOT / "schemas" / name).read_text(
            encoding="utf-8"
        )) for name in names]
        Draft202012Validator.check_schema(schemas[0])
        registry = Registry().with_resources(tuple(
            (schema["$id"], Resource.from_contents(schema))
            for schema in schemas[1:]
        ))
        validator = Draft202012Validator(schemas[0], registry=registry)
        validator.validate(self.proof.document)
        forged = deepcopy(self.proof.document)
        forged["claims"]["runtime_equivalence"] = True
        self.assertFalse(validator.is_valid(forged))

        forged = deepcopy(self.proof.document)
        claim = "continuous_preview_model_structural_safety"
        forged["claims"][claim] = not forged["claims"][claim]
        self.assertFalse(validator.is_valid(forged))

        forged = deepcopy(self.proof.document)
        forged["problem"]["scope"] = list(reversed(
            forged["problem"]["scope"]
        ))
        self.assertFalse(validator.is_valid(forged))

        forged = deepcopy(self.proof.document)
        forged["analyzer"]["config"]["backend"]["method"] = "point-sampling"
        self.assertFalse(validator.is_valid(forged))


if __name__ == "__main__":
    unittest.main()
