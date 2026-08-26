"""Projection, rational timing, unwrap, loop, and contact tests for P7."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.kimodo_npz_consistency import (  # noqa: E402
    validate_kimodo_consistency,
)
from autospine_workbench.kimodo_npz_contact import (  # noqa: E402
    kimodo_contact_markers,
)
from autospine_workbench.kimodo_npz_projection import (  # noqa: E402
    KimodoNpzProjectionError,
    kimodo_frame_ticks,
    project_kimodo_frames,
)
from autospine_workbench.kimodo_npz_reader import decode_kimodo_npz  # noqa: E402
from tests.fixtures.kimodo_npz_archive import (  # noqa: E402
    build_npz,
    motion_member_bytes,
)
from tests.kimodo_npz_helpers import map_document, source_document  # noqa: E402


def fixture(*, contacts=4, **keywords):
    members = motion_member_bytes(contacts=contacts, **keywords)
    raw = build_npz(members)
    layout = (
        "left-heel-toe-right-heel-toe-v1" if contacts == 4 else
        "left-heel-toe-toe_end-right-heel-toe-toe_end-v1"
    )
    source = source_document(raw, contact_layout=layout)
    mapping = map_document(contact_layout=layout)
    snapshot = decode_kimodo_npz(raw, source)
    motion = validate_kimodo_consistency(snapshot, source)
    return source, mapping, snapshot, motion


def values(projected, role):
    return [
        next(segment for segment in frame.segments if segment.role == role)
        .setup_local_additive_delta_deg
        for frame in projected.frames
    ]


class KimodoNpzProjectionTests(unittest.TestCase):
    def test_frame0_parent_cancellation_sign_and_root_normalization(self):
        source, mapping, _snapshot, motion = fixture()
        result = project_kimodo_frames(motion, source, mapping)
        self.assertEqual((0, 33333, 66667), tuple(
            frame.tick for frame in result.frames
        ))
        self.assertEqual([0.0, -10.0, 5.0], values(result, "humanoid.root"))
        self.assertEqual([0.0, 0.0, 0.0], values(
            result, "humanoid.spine.lower"
        ))
        self.assertEqual([0.0, -20.0, 10.0], values(
            result, "humanoid.arm.upper.left"
        ))
        self.assertEqual(
            [(0.0, 0.0), (0.1, 0.0), (0.2, 0.0)],
            [frame.root_translation_normalized for frame in result.frames],
        )

    def test_rational_tick_schedule_never_uses_implicit_30hz(self):
        source, _mapping, _snapshot, _motion = fixture()
        source["raw_npz"]["frames_per_second"] = {
            "numerator": 24, "denominator": 1,
        }
        self.assertEqual((0, 41667, 83333), kimodo_frame_ticks(source))
        source["raw_npz"]["frames_per_second"] = {
            "numerator": 30000, "denominator": 1001,
        }
        self.assertEqual((0, 33367, 66733), kimodo_frame_ticks(source))

    def test_angle_unwrap_avoids_false_358_degree_step(self):
        rotations = ({}, {"Hips": 179.0}, {"Hips": -179.0})
        source, mapping, _snapshot, motion = fixture(frame_rotations=rotations)
        result = project_kimodo_frames(motion, source, mapping)
        self.assertEqual([0.0, -179.0, -181.0], values(result, "humanoid.root"))

    def test_loop_endpoints_and_projection_degeneracy_fail_closed(self):
        source, mapping, _snapshot, motion = fixture()
        mapping["clip"]["loop"] = True
        with self.assertRaisesRegex(KimodoNpzProjectionError, "endpoints"):
            project_kimodo_frames(motion, source, mapping)

        source, mapping, _snapshot, motion = fixture(loop=True)
        mapping["clip"]["loop"] = True
        project_kimodo_frames(motion, source, mapping)

        source, mapping, _snapshot, motion = fixture(
            offset_overrides={"LeftForeArm": (0.0, 0.0, 0.2)}
        )
        with self.assertRaisesRegex(KimodoNpzProjectionError, "degenerate"):
            project_kimodo_frames(motion, source, mapping)

    def test_contact_four_and_six_layouts_compile_to_same_intervals(self):
        results = []
        for contacts in (4, 6):
            source, mapping, snapshot, motion = fixture(contacts=contacts)
            projected = project_kimodo_frames(motion, source, mapping)
            results.append(kimodo_contact_markers(snapshot, projected, mapping))
        self.assertEqual(results[0], results[1])
        self.assertEqual([
            {
                "kind": "contact", "limb": "leg.left",
                "start_tick": 0, "end_tick": 66667,
                "mode": "annotation_only",
            },
            {
                "kind": "contact", "limb": "leg.right",
                "start_tick": 33333, "end_tick": 66667,
                "mode": "annotation_only",
            },
        ], results[0])

    def test_last_sample_alone_creates_no_zero_length_contact(self):
        rows = (
            (False, False, False, False),
            (False, False, False, False),
            (True, False, False, False),
        )
        source, mapping, snapshot, motion = fixture(contact_rows=rows)
        projected = project_kimodo_frames(motion, source, mapping)
        self.assertEqual([], kimodo_contact_markers(snapshot, projected, mapping))
        disabled = deepcopy(mapping)
        disabled["contact"] = {
            "enabled": False, "mode": "annotation_only", "interval": "half_open",
        }
        self.assertEqual([], kimodo_contact_markers(snapshot, projected, disabled))


if __name__ == "__main__":
    unittest.main()
