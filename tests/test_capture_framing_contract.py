"""P10.2b candidate, coordinate, decision, and history tests."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate_path in (ROOT, SRC):
    if str(candidate_path) not in sys.path:
        sys.path.insert(0, str(candidate_path))

from autospine_workbench.capture_framing_candidate import (  # noqa: E402
    CaptureFramingCandidate,
)
from autospine_workbench.capture_framing_decision import (  # noqa: E402
    CaptureFramingDecisionError,
    build_capture_framing_decision,
    require_capture_framing_decision,
)
from autospine_workbench.capture_framing_geometry import (  # noqa: E402
    canvas_bounds_to_runtime,
    contains_with_capture_margin,
    proposed_runtime_world_viewport,
    union_canvas_envelope,
)
from autospine_workbench.capture_framing_history import (  # noqa: E402
    CaptureFramingRevisionConflict,
    publish_capture_framing_decision,
    snapshot_capture_framing_history,
)
from autospine_workbench.capture_framing_profile import (  # noqa: E402
    CANDIDATE_RELEASE_GATE,
    CANDIDATE_SEMANTICS,
    CAPTURE_VIEWPORT,
    COORDINATE_TRANSFORM_ID,
    FORMAT,
    FORMAT_VERSION,
    capture_framing_profile,
)
from autospine_workbench.capture_framing_validation import (  # noqa: E402
    CaptureFramingValidationError,
    capture_framing_candidate_sha256,
    require_capture_framing_candidate,
)
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional dependency
    Draft202012Validator = None


class CaptureFramingContractTests(unittest.TestCase):
    def test_coordinate_reflection_and_margin_are_explicit(self):
        canvas = _bounds(100, 200, 900, 800)
        runtime = canvas_bounds_to_runtime(canvas, 1024.0)
        self.assertEqual(_bounds(100, 224, 900, 824), runtime)
        viewport = proposed_runtime_world_viewport(runtime)
        self.assertTrue(contains_with_capture_margin(
            viewport, runtime, CAPTURE_VIEWPORT,
        ))
        too_tight = {
            "x": 100.0, "y": 224.0, "width": 800.0, "height": 800.0,
        }
        self.assertFalse(contains_with_capture_margin(
            too_tight, runtime, CAPTURE_VIEWPORT,
        ))

    def test_candidate_is_deterministic_and_tamper_closed(self):
        candidate = _candidate()
        require_capture_framing_candidate(candidate.document)
        self.assertEqual(
            candidate.sha256,
            capture_framing_candidate_sha256(candidate.document),
        )
        self.assertEqual(
            {"setup": True, "base": True, "combined": True},
            candidate.document["coverage"],
        )
        self.assertEqual(
            "layer-combined",
            candidate.document["union_extrema_witnesses"]["left"][
                "attachment_id"
            ],
        )
        changed = candidate.document
        changed["coordinate_spaces"]["canvas_height"] = 201.0
        with self.assertRaises(CaptureFramingValidationError):
            require_capture_framing_candidate(changed)

    def test_decision_requires_exact_proposal_and_full_margin(self):
        candidate = _candidate()
        accepted = build_capture_framing_decision(
            candidate, action="accept", world_viewport=None,
            reason_code="human-approved-automatic-capture-framing-v1",
            revision=1, supersedes_decision_sha256=None,
        )
        require_capture_framing_decision(accepted.document, candidate=candidate)
        self.assertEqual(
            candidate.document["proposed_world_viewport"],
            accepted.document["decision"]["world_viewport"],
        )
        with self.assertRaises(CaptureFramingDecisionError):
            build_capture_framing_decision(
                candidate, action="adjust",
                world_viewport={
                    "x": -5.0, "y": 70.0, "width": 145.0, "height": 145.0,
                },
                reason_code="human-adjusted-capture-framing-v1",
                revision=1, supersedes_decision_sha256=None,
            )

    def test_history_is_linear_idempotent_and_candidate_bound(self):
        candidate = _candidate()
        first = build_capture_framing_decision(
            candidate, action="accept", world_viewport=None,
            reason_code="human-approved-automatic-capture-framing-v1",
            revision=1, supersedes_decision_sha256=None,
        )
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            initial = snapshot_capture_framing_history(state, candidate)
            self.assertEqual(0, initial.current_revision)
            published = publish_capture_framing_decision(
                state, first, candidate, base_revision=0,
                previous_decision_sha256=None,
            )
            retry = publish_capture_framing_decision(
                state, first, candidate, base_revision=0,
                previous_decision_sha256=None,
            )
            self.assertEqual(published.sha256, retry.sha256)
            self.assertTrue(retry.reused)
            snapshot = snapshot_capture_framing_history(state, candidate)
            self.assertEqual((1, "accept"), (
                snapshot.current_revision, snapshot.action,
            ))
            stale = build_capture_framing_decision(
                candidate, action="reject", world_viewport=None,
                reason_code="human-rejected-capture-framing-v1",
                revision=1, supersedes_decision_sha256=None,
            )
            with self.assertRaises(CaptureFramingRevisionConflict):
                publish_capture_framing_decision(
                    state, stale, candidate, base_revision=0,
                    previous_decision_sha256=None,
                )
            second = build_capture_framing_decision(
                candidate, action="accept", world_viewport=None,
                reason_code="human-approved-automatic-capture-framing-v1",
                revision=2, supersedes_decision_sha256=first.sha256,
                previous_decision=first,
            )
            publish_capture_framing_decision(
                state, second, candidate, base_revision=1,
                previous_decision_sha256=first.sha256,
            )
            self.assertEqual(
                2, snapshot_capture_framing_history(
                    state, candidate,
                ).current_revision,
            )

    @unittest.skipIf(Draft202012Validator is None, "jsonschema is optional")
    def test_json_schemas_accept_candidate_and_decision(self):
        candidate = _candidate()
        decision = build_capture_framing_decision(
            candidate, action="accept", world_viewport=None,
            reason_code="human-approved-automatic-capture-framing-v1",
            revision=1, supersedes_decision_sha256=None,
        )
        for name, document in (
            ("capture-framing-candidate-v1.schema.json", candidate.document),
            ("capture-framing-decision-v1.schema.json", decision.document),
        ):
            schema = json.loads((ROOT / "schemas" / name).read_text("utf-8"))
            Draft202012Validator.check_schema(schema)
            Draft202012Validator(schema).validate(document)


def _candidate():
    canvas_height = 200.0
    envelopes = {
        "setup": _record("setup", _bounds(10, 20, 110, 120), canvas_height),
        "base": _record("base", _bounds(0, 15, 130, 125), canvas_height),
        "combined": _record(
            "combined", _bounds(-5, 10, 140, 130), canvas_height,
        ),
    }
    union_canvas, witnesses = union_canvas_envelope(envelopes)
    union_runtime = canvas_bounds_to_runtime(union_canvas, canvas_height)
    viewport = proposed_runtime_world_viewport(union_runtime)
    profile = capture_framing_profile()
    manifest_sha = "1" * 64
    document = {
        "format": FORMAT, "format_version": FORMAT_VERSION,
        "project_id": "fixture-project", "clip_id": "fixture-clip",
        "source": {
            "package_id": "2" * 64,
            "body_sway_probe_report_sha256": "3" * 64,
            "dynamic_viewport_fit_sha256": "4" * 64,
            "tick_schedule_sha256": "5" * 64,
            "current_p10_1_head": {
                "candidate_sha256": "6" * 64,
                "decision_sha256": "7" * 64, "revision": 1,
            },
            "capture_framing_profile_sha256": canonical_sha256(profile),
            "layer_manifest_sha256": manifest_sha,
            "p3": _stage("p3", manifest_sha),
            "p5": _stage("p5"), "p9": _stage("p9"),
        },
        "timing": {
            "ticks_per_second": 1_000_000,
            "duration_ticks": 4_000_000, "loop": True,
        },
        "coordinate_spaces": {
            "envelope_space": "rig-canvas-top-left-y-down",
            "world_viewport_space": "spine-world-bottom-left-y-up",
            "canvas_height": canvas_height,
            "transform_id": COORDINATE_TRANSFORM_ID,
        },
        "envelopes": envelopes,
        "union_envelope_canvas": union_canvas,
        "union_envelope_runtime": union_runtime,
        "union_extrema_witnesses": witnesses,
        "capture_viewport": deepcopy(CAPTURE_VIEWPORT),
        "proposed_world_viewport": viewport,
        "coverage": {
            kind: contains_with_capture_margin(
                viewport, row["bounds_runtime"], CAPTURE_VIEWPORT,
            ) for kind, row in envelopes.items()
        },
        "compiler": profile,
        "compiler_sha256": canonical_sha256(profile),
        "semantics": deepcopy(CANDIDATE_SEMANTICS),
        "status": "candidate_only",
        "release_gate": deepcopy(CANDIDATE_RELEASE_GATE),
    }
    require_capture_framing_candidate(document)
    return CaptureFramingCandidate(_canonical(document))


def _record(kind, bounds, canvas_height):
    tick = 0 if kind == "setup" else 10
    identifier = f"layer-{kind}"
    minimum, maximum = bounds["min_xy"], bounds["max_xy"]
    points = {
        "left": [minimum[0], minimum[1]],
        "right": [maximum[0], minimum[1]],
        "top": [minimum[0], minimum[1]],
        "bottom": [minimum[0], maximum[1]],
    }
    return {
        "sample_count": 1, "attachment_sample_count": 1, "point_count": 4,
        "evidence_sha256": canonical_sha256({"kind": kind, "points": points}),
        "bounds_canvas": bounds,
        "bounds_runtime": canvas_bounds_to_runtime(bounds, canvas_height),
        "extrema_witnesses": {
            side: {
                "tick": tick, "attachment_id": identifier,
                "vertex_index": index, "point_xy": point,
            }
            for index, (side, point) in enumerate(points.items())
        },
    }


def _stage(name, manifest_sha=None):
    fields = {
        "p3": (
            "base_rig_sha256", "base_bundle_sha256", "layer_manifest_sha256",
            "resolved_project_sha256", "rig_sha256", "run_sha256",
            "probes_sha256", "visuals_sha256", "bundle_sha256",
        ),
        "p5": (
            "target_profile_sha256", "instance_sha256", "run_sha256",
            "retarget_report_sha256", "mesh_regression_sha256", "bundle_sha256",
        ),
        "p9": (
            "foot_lock_candidates_sha256", "depth_order_candidates_sha256",
            "motion_policy_decision_sha256", "reviewed_motion_policy_sha256",
            "motion_instance_v2_sha256", "run_sha256", "bundle_sha256",
        ),
    }[name]
    result = {field: "8" * 64 for field in fields}
    if manifest_sha is not None:
        result["layer_manifest_sha256"] = manifest_sha
    return result


def _bounds(min_x, min_y, max_x, max_y):
    return {
        "min_xy": [float(min_x), float(min_y)],
        "max_xy": [float(max_x), float(max_y)],
        "size": [float(max_x - min_x), float(max_y - min_y)],
        "center_xy": [float((min_x + max_x) / 2), float((min_y + max_y) / 2)],
    }


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":"))


if __name__ == "__main__":
    unittest.main()
