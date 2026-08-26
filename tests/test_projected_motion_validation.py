"""Contract tests for target-independent ProjectedMotionIR v1."""

from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.projected_motion_validation import (  # noqa: E402
    ProjectedMotionValidationError,
    projected_motion_ir_sha256,
    require_projected_motion_ir,
)
from tests.projected_motion_helpers import projected_motion_document  # noqa: E402

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional test extra
    Draft202012Validator = None


class ProjectedMotionValidationTests(unittest.TestCase):
    def test_valid_document_schema_and_stable_identity(self):
        document = projected_motion_document()
        require_projected_motion_ir(document)
        reordered = json.loads(json.dumps(document, sort_keys=True))
        self.assertEqual(
            projected_motion_ir_sha256(document),
            projected_motion_ir_sha256(reordered),
        )
        if Draft202012Validator is not None:
            schema = json.loads(
                (ROOT / "schemas" / "projected-motion-ir-v1.schema.json")
                .read_text(encoding="utf-8")
            )
            Draft202012Validator.check_schema(schema)
            Draft202012Validator(schema).validate(document)

    def test_collapsed_segment_is_preserved_as_evidence(self):
        document = projected_motion_document(collapsed=True)
        require_projected_motion_ir(document)
        self.assertEqual(
            "collapsed",
            document["segment_tracks"][0]["samples"][0]["projection_state"],
        )

    def test_rejects_shape_time_and_binding_drift(self):
        baseline = projected_motion_document()
        mutations = (
            lambda value: value.update(extra=True),
            lambda value: value["timing"].update(frame_count=3),
            lambda value: value["frames"][1].update(source_frame_index=0),
            lambda value: value["frames"][1].update(tick=0),
            lambda value: value["root_samples"][1].update(tick=4),
            lambda value: value["root_samples"][0].update(
                screen_translation_normalized=[1.0, 0.0]
            ),
            lambda value: value["source"].update(map_sha256="A" * 64),
            lambda value: value["segment_tracks"][0].update(
                delta_parent_role="humanoid.head"
            ),
        )
        self._reject_each(baseline, mutations)

    def test_rejects_inconsistent_projected_geometry(self):
        baseline = projected_motion_document()
        sample = lambda value: value["segment_tracks"][0]["samples"][1]
        mutations = (
            lambda value: sample(value).update(projected_length_normalized=0.5),
            lambda value: sample(value).update(foreshortening_ratio=0.5),
            lambda value: sample(value).update(depth_cosine=0.5),
            lambda value: sample(value).update(
                midpoint_depth_root_relative_normalized=0.5
            ),
            lambda value: sample(value).update(projected_world_angle_deg=90.0),
            lambda value: sample(value).update(projection_state="collapsed"),
            lambda value: sample(value).update(source_length_normalized=True),
            lambda value: sample(value).update(source_length_normalized=math.nan),
        )
        self._reject_each(baseline, mutations)

    def test_rejects_wrapped_angles_and_loop_drift(self):
        wrapped = projected_motion_document()
        sample = wrapped["segment_tracks"][0]["samples"][1]
        sample["projected_vector_normalized"] = [-1.0, 0.0]
        sample["projected_world_angle_deg"] = 180.0
        require_projected_motion_ir(wrapped)
        sample["projected_world_angle_deg"] = 180.001
        with self.assertRaises(ProjectedMotionValidationError):
            require_projected_motion_ir(wrapped)

        looped = projected_motion_document(loop=True)
        looped["root_samples"][1]["depth_translation_normalized"] = 0.1
        with self.assertRaisesRegex(ProjectedMotionValidationError, "root endpoints"):
            require_projected_motion_ir(looped)

    def _reject_each(self, baseline: dict, mutations) -> None:
        for mutate in mutations:
            candidate = deepcopy(baseline)
            mutate(candidate)
            with self.subTest(candidate=candidate), self.assertRaises(
                ProjectedMotionValidationError
            ):
                require_projected_motion_ir(candidate)


if __name__ == "__main__":
    unittest.main()
