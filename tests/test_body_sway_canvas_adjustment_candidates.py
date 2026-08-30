"""Pure P10.2 canvas diagnosis and draft-candidate contract tests."""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

try:
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
except ImportError:  # pragma: no cover - optional test dependency
    Draft202012Validator = None
    Registry = Resource = None

from autospine_workbench.body_sway_canvas_adjustment_candidates import (  # noqa: E402
    BodySwayCanvasAdjustmentCandidates,
    BodySwayCanvasAdjustmentError,
    compile_body_sway_canvas_adjustment_candidates,
    require_exact_body_sway_canvas_adjustment_candidates,
)
from autospine_workbench.body_sway_canvas_adjustment_candidate_validation import (  # noqa: E402
    body_sway_canvas_adjustment_candidate_id,
)
from autospine_workbench.body_sway_canvas_adjustment_validation import (  # noqa: E402
    BodySwayCanvasAdjustmentValidationError,
    body_sway_canvas_adjustment_candidates_sha256,
    require_body_sway_canvas_adjustment_candidates,
)
from autospine_workbench.body_sway_probe_inputs import (  # noqa: E402
    require_body_sway_probe_inputs,
)
from autospine_workbench.body_sway_probe_report import (  # noqa: E402
    BodySwayProbeReport,
    compile_body_sway_probe_report,
)
from autospine_workbench.idle_behavior_candidates import (  # noqa: E402
    compile_idle_behavior_candidates,
)
from autospine_workbench.idle_behavior_decision import (  # noqa: E402
    build_idle_behavior_decision,
)
from autospine_workbench.idle_behavior_review_head import (  # noqa: E402
    read_idle_behavior_review_head,
)
from autospine_workbench.idle_behavior_review_profile import (  # noqa: E402
    MAX_REVISIONS,
)
from autospine_workbench.idle_behavior_review_store import (  # noqa: E402
    IdleBehaviorReviewStore,
)
from tests.idle_behavior_decision_helpers import (  # noqa: E402
    adjust_decision,
    completed_review,
)
from tests.idle_behavior_helpers import IdleBehaviorFixture  # noqa: E402


def _canonical(value):
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )


class BodySwayCanvasAdjustmentCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        root = Path(cls.temporary.name)
        cls.fixture = IdleBehaviorFixture(root)
        cls.candidates = compile_idle_behavior_candidates(
            cls.fixture.manifest, cls.fixture.mesh,
            cls.fixture.retarget, cls.fixture.reviewed,
        ).document
        cls.decision = build_idle_behavior_decision(
            cls.candidates, review=completed_review(),
            decisions=[adjust_decision(cls.candidates)],
        )
        cls.inputs = require_body_sway_probe_inputs(
            cls.fixture.manifest, cls.candidates, cls.decision.document,
            cls.fixture.mesh, cls.fixture.retarget, cls.fixture.reviewed,
        )
        cls.state = root / "state"
        cls.state.mkdir()
        IdleBehaviorReviewStore(cls.state).publish(
            cls.decision, cls.candidates,
            base_revision=0, previous_decision_sha256=None,
        )
        cls.head = read_idle_behavior_review_head(cls.state, cls.candidates)
        cls.report = compile_body_sway_probe_report(cls.inputs)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_real_exact_fixture_distinguishes_zero_gain_base_blocker(self):
        result = compile_body_sway_canvas_adjustment_candidates(
            self.inputs, self.head,
        )
        document = result.document
        self.assertEqual(
            "upstream_base_motion_canvas_overflow",
            document["diagnosis"]["classification"],
        )
        self.assertEqual([], document["adjustment_candidates"])
        self.assertEqual("rejected", document["diagnosis"][
            "zero_gain_canvas_status"
        ])
        self.assertEqual([0, 8], [
            row["gain"]["numerator"] for row in document["probes"]
        ])
        zero = document["probes"][0]
        self.assertGreater(zero["canvas_failure_tick_count"], 0)
        self.assertTrue(zero["affected_attachment_ids"])
        self.assertTrue(zero["failure_sides"])
        self.assertGreater(zero["max_overflow_px"], 0.0)
        self.assertIsNotNone(zero["worst_failure"])
        self.assertTrue(all(
            row["value"] == 0.0
            for row in zero["sampled_body_sway_peak_abs_delta_deg"]
        ))
        reviewed = document["probes"][-1]
        self.assertTrue(any(
            row["value"] > 0.0
            for row in reviewed["sampled_body_sway_peak_abs_delta_deg"]
        ))
        self.assertEqual(self.report.sha256, document["source"][
            "body_sway_probe_report_sha256"
        ])
        require_body_sway_canvas_adjustment_candidates(document)
        self.assertEqual(
            result.sha256,
            body_sway_canvas_adjustment_candidates_sha256(document),
        )

    def test_lower_gain_is_only_an_unvalidated_p10_1_draft(self):
        with self._synthetic_probes({
            8: _probe(8, failures=12),
            0: _probe(0),
            7: _probe(7, failures=3),
            6: _probe(6),
        }):
            first = compile_body_sway_canvas_adjustment_candidates(
                self.inputs, self.head,
            )
        with self._synthetic_probes({
            8: _probe(8, failures=12),
            0: _probe(0),
            7: _probe(7, failures=3),
            6: _probe(6),
        }):
            second = compile_body_sway_canvas_adjustment_candidates(
                self.inputs, self.head,
            )
            replayed_sha = require_exact_body_sway_canvas_adjustment_candidates(
                self.inputs, self.head, first.document,
            )
        self.assertEqual(first, second)
        self.assertEqual(first.sha256, replayed_sha)
        document = first.document
        self.assertEqual(
            "sampled_adjustment_candidate_available",
            document["diagnosis"]["classification"],
        )
        self.assertEqual([0, 6, 7, 8], [
            row["gain"]["numerator"] for row in document["probes"]
        ])
        draft = document["adjustment_candidates"][0]
        self.assertEqual({"numerator": 6, "denominator": 8}, draft["gain"])
        self.assertEqual("none", draft["authority"])
        self.assertEqual("unvalidated_draft", draft["status"])
        self.assertTrue(draft["requires_explicit_p10_1_revision"])
        self.assertFalse(draft["claims"]["safe_parameters"])
        self.assertFalse(draft["claims"]["release_authority"])
        original = self.inputs.selection["parameters"]
        proposed = draft["parameters"]
        self.assertEqual(original["cycles"], proposed["cycles"])
        self.assertEqual(
            original["per_bone_phase_fraction"],
            proposed["per_bone_phase_fraction"],
        )
        self.assertEqual(
            [value * 0.75 for value in (1.0, 2.0, 1.0, 0.5)],
            [row["value"] for row in proposed["per_bone_amplitude_deg"]],
        )
        self.assertNotIn("review", draft)
        self.assertNotIn("revision", draft)

    def test_zero_pass_without_positive_grid_pass_does_not_invent_parameters(self):
        probes = {8: _probe(8, failures=12), 0: _probe(0)}
        probes.update({gain: _probe(gain, failures=1) for gain in range(1, 8)})
        with self._synthetic_probes(probes):
            result = compile_body_sway_canvas_adjustment_candidates(
                self.inputs, self.head,
            )
        document = result.document
        self.assertEqual(
            "no_nonzero_sampled_adjustment_candidate",
            document["diagnosis"]["classification"],
        )
        self.assertEqual([], document["adjustment_candidates"])
        self.assertEqual(list(range(9)), [
            row["gain"]["numerator"] for row in document["probes"]
        ])

    def test_reviewed_canvas_pass_needs_no_adjustment(self):
        report = _report_with_canvas(self.report, status="passed", failures=0)
        with self._synthetic_probes({8: _probe(8)}, report=report):
            result = compile_body_sway_canvas_adjustment_candidates(
                self.inputs, self.head,
            )
        self.assertEqual(
            "reviewed_canvas_passed",
            result.document["diagnosis"]["classification"],
        )
        self.assertEqual([], result.document["adjustment_candidates"])
        self.assertEqual([8], [row["gain"]["numerator"]
                              for row in result.document["probes"]])

    def test_stale_head_and_tampered_candidate_fail_closed(self):
        stale = replace(
            self.head,
            snapshot=replace(self.head.snapshot, current_revision=2),
        )
        with self.assertRaisesRegex(BodySwayCanvasAdjustmentError, "stale"):
            compile_body_sway_canvas_adjustment_candidates(self.inputs, stale)
        with self._synthetic_probes({
            8: _probe(8, failures=12), 0: _probe(0), 7: _probe(7),
        }):
            result = compile_body_sway_canvas_adjustment_candidates(
                self.inputs, self.head,
            )
        changed = result.document
        changed["adjustment_candidates"][0]["claims"]["safe_parameters"] = True
        with self.assertRaises(BodySwayCanvasAdjustmentValidationError):
            require_body_sway_canvas_adjustment_candidates(changed)
        changed = result.document
        draft = changed["adjustment_candidates"][0]
        draft["parameters"]["per_bone_amplitude_deg"][0]["value"] += 0.1
        draft["candidate_id"] = body_sway_canvas_adjustment_candidate_id(
            changed["source"], changed["reviewed_selection"], draft,
        )
        with self.assertRaises(BodySwayCanvasAdjustmentValidationError):
            require_body_sway_canvas_adjustment_candidates(changed)
        with self._synthetic_probes({
            8: _probe(8, failures=12), 0: _probe(0), 7: _probe(7),
        }), self.assertRaisesRegex(
            BodySwayCanvasAdjustmentError, "differs from exact replay",
        ):
            require_exact_body_sway_canvas_adjustment_candidates(
                self.inputs, self.head, changed,
            )

    def test_result_is_frozen_path_free_and_production_files_stay_small(self):
        with self._synthetic_probes({
            8: _probe(8, failures=12), 0: _probe(0), 7: _probe(7),
        }):
            result = compile_body_sway_canvas_adjustment_candidates(
                self.inputs, self.head,
            )
        self.assertIsInstance(result, BodySwayCanvasAdjustmentCandidates)
        encoded = result.canonical_bytes.decode("utf-8")
        self.assertNotIn(str(self.state), encoded)
        self.assertNotIn("path", encoded.lower())
        self.assertFalse(result.document["semantics"][
            "discrete_gain_samples_are_safe_interval"
        ])
        for path in SRC.glob(
            "autospine_workbench/body_sway_canvas_adjustment*.py"
        ):
            self.assertLessEqual(
                len(path.read_text(encoding="utf-8").splitlines()), 300,
                path.name,
            )

    @unittest.skipIf(Draft202012Validator is None, "jsonschema is optional")
    def test_json_schema_accepts_exact_result_and_rejects_authority(self):
        result = compile_body_sway_canvas_adjustment_candidates(
            self.inputs, self.head,
        )
        schema = json.loads((
            ROOT / "schemas" /
            "body-sway-canvas-adjustment-candidates-v1.schema.json"
        ).read_text(encoding="utf-8"))
        probe_schema = json.loads((
            ROOT / "schemas" / "body-sway-probe-report-v1.schema.json"
        ).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        registry = Registry().with_resources(((
            probe_schema["$id"], Resource.from_contents(probe_schema),
        ),))
        validator = Draft202012Validator(schema, registry=registry)
        validator.validate(result.document)
        changed = result.document
        changed["semantics"]["safe_parameters_claimed"] = True
        self.assertFalse(validator.is_valid(changed))

    @unittest.skipIf(Draft202012Validator is None, "jsonschema is optional")
    def test_schema_rejects_zero_and_reviewed_gain_as_adjustment(self):
        with self._synthetic_probes({
            8: _probe(8, failures=12), 0: _probe(0), 7: _probe(7),
        }):
            document = compile_body_sway_canvas_adjustment_candidates(
                self.inputs, self.head,
            ).document
        validator = _canvas_adjustment_schema_validator()
        validator.validate(document)
        for numerator in (0, 8):
            changed = deepcopy(document)
            changed["adjustment_candidates"][0]["gain"][
                "numerator"
            ] = numerator
            self.assertFalse(validator.is_valid(changed))

    @unittest.skipIf(Draft202012Validator is None, "jsonschema is optional")
    def test_revision_limit_matches_p10_1_history_contract(self):
        document = compile_body_sway_canvas_adjustment_candidates(
            self.inputs, self.head,
        ).document
        validator = _canvas_adjustment_schema_validator()
        document["source"]["current_p10_1_head"][
            "revision"
        ] = MAX_REVISIONS
        require_body_sway_canvas_adjustment_candidates(document)
        validator.validate(document)
        document["source"]["current_p10_1_head"][
            "revision"
        ] = MAX_REVISIONS + 1
        with self.assertRaises(BodySwayCanvasAdjustmentValidationError):
            require_body_sway_canvas_adjustment_candidates(document)
        self.assertFalse(validator.is_valid(document))

    @contextmanager
    def _synthetic_probes(self, probes, *, report=None):
        report = report or _report_with_canvas(
            self.report, status="rejected", failures=12,
        )

        def sample(_prepared, numerator):
            return deepcopy(probes[numerator])

        with patch(
            "autospine_workbench.body_sway_canvas_adjustment_candidates."
            "compile_body_sway_probe_report", return_value=report,
        ), patch(
            "autospine_workbench.body_sway_canvas_adjustment_candidates."
            "prepare_body_sway_canvas_adjustment_probe",
            return_value=_Prepared(report.document["schedule"][
                "tick_schedule_sha256"
            ]),
        ), patch(
            "autospine_workbench.body_sway_canvas_adjustment_candidates."
            "probe_body_sway_canvas_gain", side_effect=sample,
        ), patch(
            "autospine_workbench.body_sway_canvas_adjustment_builder."
            "probe_body_sway_canvas_gain", side_effect=sample,
        ):
            yield


class _Prepared:
    def __init__(self, schedule_sha):
        self.tick_schedule_sha256 = schedule_sha


def _canvas_adjustment_schema_validator():
    schema = json.loads((
        ROOT / "schemas" /
        "body-sway-canvas-adjustment-candidates-v1.schema.json"
    ).read_text(encoding="utf-8"))
    probe_schema = json.loads((
        ROOT / "schemas" / "body-sway-probe-report-v1.schema.json"
    ).read_text(encoding="utf-8"))
    registry = Registry().with_resources(((
        probe_schema["$id"], Resource.from_contents(probe_schema),
    ),))
    return Draft202012Validator(schema, registry=registry)


def _probe(numerator, *, failures=0, geometry_failures=None):
    geometry_failures = failures if geometry_failures is None else geometry_failures
    rejected = failures > 0
    worst = None if not rejected else {
        "tick": 100,
        "attachment_id": "layer-body",
        "vertex_index": 0,
        "point_xy": [-2.0, 20.0],
        "sides": ["left"],
        "overflow_px": 2.0,
    }
    return {
        "gain": {"numerator": numerator, "denominator": 8},
        "sample_count": 65,
        "canvas_status": "rejected" if rejected else "passed",
        "sampled_geometry_status": (
            "rejected" if geometry_failures else "passed"
        ),
        "canvas_failure_tick_count": failures,
        "canvas_failure_vertex_count": failures,
        "geometry_rejection_tick_count": geometry_failures,
        "first_failure_tick": 100 if rejected else None,
        "last_failure_tick": 100 if rejected else None,
        "affected_attachment_ids": ["layer-body"] if rejected else [],
        "failure_sides": ["left"] if rejected else [],
        "max_overflow_px": 2.0 if rejected else 0.0,
        "worst_failure": worst,
        "sampled_body_sway_peak_abs_delta_deg": [
            {"bone_id": bone_id, "value": float(numerator)}
            for bone_id in (
                "pelvis-spine", "spine-chest", "chest-neck", "neck-head",
            )
        ],
        "evidence_sha256": f"{numerator + 1:x}" * 64,
    }


def _report_with_canvas(report, *, status, failures):
    document = report.document
    check = next(row for row in document["checks"]
                 if row["check_id"] == "sampled_canvas_containment")
    check["status"] = status
    check["reason_code"] = f"sampled_check_{status}"
    check["sample_count"] = 65
    check["failure_count"] = failures
    check["evidence_sha256"] = "9" * 64
    return BodySwayProbeReport(_canonical(document))


if __name__ == "__main__":
    unittest.main()
