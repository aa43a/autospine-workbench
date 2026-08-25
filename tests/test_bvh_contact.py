"""Deterministic source-world BVH contact detection tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import math
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.bvh_contact import (  # noqa: E402
    BvhContactError,
    detect_bvh_contacts,
)
from autospine_workbench.bvh_fk import (  # noqa: E402
    BvhProjectedFrame,
    BvhProjectedFrames,
    BvhProjectedPoint,
)
from autospine_workbench.bvh_map_validation import bvh_map_sha256  # noqa: E402
from autospine_workbench.bvh_parser import BvhDocument, BvhJoint  # noqa: E402


def _joint(name: str, parent: int | None, *, end: bool = False) -> BvhJoint:
    return BvhJoint(
        name=name,
        parent_index=parent,
        offset=(0.0, 0.0, 0.0),
        channels=(),
        rotation_order=("Xrotation", "Yrotation", "Zrotation"),
        end_site_offset=(0.0, 1.0, 0.0) if end else None,
    )


def source(frame_count: int) -> BvhDocument:
    return BvhDocument(
        source_sha256="0" * 64,
        source_byte_length=1,
        joints=(
            _joint("Hips", None),
            _joint("LeftFoot", 0, end=True),
            _joint("RightFoot", 0, end=True),
        ),
        frame_count=frame_count,
        frame_time_seconds=0.00001,
        channel_count=0,
        frames=tuple(() for _ in range(frame_count)),
    )


def mapping(*, both: bool = True) -> dict:
    feet = [{"limb": "leg.left", "foot_joint_name": "LeftFoot"}]
    if both:
        feet.append({"limb": "leg.right", "foot_joint_name": "RightFoot"})
    return {
        "format": "autospine-bvh-map",
        "format_version": 1,
        "map_id": "contact-test-v1",
        "clip": {"clip_id": "contact-test", "loop": False},
        "basis": {
            "screen_x": "+X",
            "screen_y": "-Y",
            "depth": "+Z",
            "rotation_convention": "bvh_declared_channel_postmultiply",
        },
        "root": {
            "joint_name": "Hips",
            "reference_length_source_units": 1.0,
            "translation_policy":
                "projected_frame0_delta_normalized_reference_length",
        },
        "bones": [{
            "role": "humanoid.root",
            "joint_name": "Hips",
            "aim": {"kind": "joint", "joint_name": "LeftFoot"},
            "rotation_policy": "projected_setup_local_delta",
        }],
        "contact": {
            "enabled": True,
            "feet": feet,
            "floor_height_source_units": 0.0,
            "height_threshold_source_units": 0.2,
            "speed_threshold_source_units_per_second": 1_000_000.0,
            "minimum_frames": 1,
            "gap_frames": 0,
            "height_policy":
                "absolute_signed_basis_screen_y_distance_to_floor",
            "speed_policy": "source_world_3d_euclidean",
            "mode": "annotation_only",
            "interval": "half_open",
        },
    }


def worlds(left, right=None):
    right = right if right is not None else [(0.0, 2.0, 0.0)] * len(left)
    return tuple({
        "Hips": (0.0, 0.0, 0.0),
        "LeftFoot": tuple(left_point),
        "RightFoot": tuple(right_point),
    } for left_point, right_point in zip(left, right, strict=True))


def ticks(count: int) -> tuple[int, ...]:
    return tuple(index * 10 for index in range(count))


def detect(document, value, frames, *, duration=None, frame_ticks=None):
    duration = (len(frames) - 1) * 10 if duration is None else duration
    frame_ticks = ticks(len(frames)) if frame_ticks is None else frame_ticks
    projection = BvhProjectedFrames(
        source_sha256=document.source_sha256,
        map_id=value["map_id"],
        map_sha256=bvh_map_sha256(value),
        clip_id=value["clip"]["clip_id"],
        loop=value["clip"]["loop"],
        duration_ticks=duration,
        frames=tuple(
            BvhProjectedFrame(
                tick=tick,
                joints=tuple(
                    (
                        joint.name,
                        BvhProjectedPoint(
                            tuple(frame[joint.name]), (0.0, 0.0), 0.0
                        ),
                    )
                    for joint in document.joints
                ),
                end_sites=(),
                root_translation_normalized=(0.0, 0.0),
                segments=(),
            )
            for tick, frame in zip(frame_ticks, frames, strict=True)
        ),
    )
    return detect_bvh_contacts(
        document,
        value,
        projected=projection,
    )


class BvhContactSuccessTests(unittest.TestCase):
    def test_left_right_markers_are_frozen_sorted_and_half_open(self):
        document = source(5)
        frames = worlds(
            [(0, 0, 0), (0, 0, 0), (0, 2, 0), (0, 2, 0), (0, 2, 0)],
            [(0, 2, 0), (0, 0, 0), (0, 0, 0), (0, 0, 0), (0, 2, 0)],
        )
        markers = detect(document, mapping(), frames)
        self.assertEqual([
            {"kind": "contact", "limb": "leg.left", "start_tick": 0,
             "end_tick": 20, "mode": "annotation_only"},
            {"kind": "contact", "limb": "leg.right", "start_tick": 10,
             "end_tick": 40, "mode": "annotation_only"},
        ], [marker.document for marker in markers])
        projected = _projection(document, mapping(), frames)
        self.assertEqual(markers, detect_bvh_contacts(
            document, mapping(), projected=projected
        ))
        self.assertIsInstance(projected.world_xyz_by_joint, tuple)
        with self.assertRaises(FrozenInstanceError):
            markers[0].limb = "leg.right"  # type: ignore[misc]

    def test_signed_screen_y_and_explicit_floor_control_height(self):
        document = source(3)
        value = mapping()
        value["contact"].update(
            floor_height_source_units=5.0,
            height_threshold_source_units=0.0,
        )
        frames = worlds([(0, -5, 0)] * 3, [(0, 5, 0)] * 3)
        negative_y = detect(document, value, frames)
        self.assertEqual(["leg.left"], [marker.limb for marker in negative_y])

        value["basis"]["screen_y"] = "+Y"
        positive_y = detect(document, value, frames)
        self.assertEqual(["leg.right"], [marker.limb for marker in positive_y])

    def test_internal_gap_is_filled_before_short_segments_are_removed(self):
        document = source(8)
        value = mapping(both=False)
        value["contact"].update(minimum_frames=3, gap_frames=1)
        frames = worlds([
            (0, 0, 0), (0, 0, 0), (0, 2, 0), (0, 0, 0),
            (0, 0, 0), (0, 2, 0), (0, 2, 0), (0, 0, 0),
        ])
        markers = detect(document, value, frames)
        self.assertEqual([(0, 50)], [
            (marker.start_tick, marker.end_tick) for marker in markers
        ])

    def test_speed_uses_source_world_depth_and_first_frame_next_delta(self):
        document = source(5)
        value = mapping(both=False)
        value["contact"].update(
            speed_threshold_source_units_per_second=0.5,
            minimum_frames=1,
        )
        depth_break = worlds([
            (0, 0, 0), (0, 0, 0), (0, 0, 2), (0, 0, 2), (0, 0, 2),
        ])
        markers = detect(document, value, depth_break)
        self.assertEqual([(0, 20), (30, 40)], [
            (marker.start_tick, marker.end_tick) for marker in markers
        ])

        four = source(4)
        moving_first = worlds([
            (0, 0, 0), (0, 0, 2), (0, 0, 2), (0, 0, 2),
        ])
        markers = detect(four, value, moving_first)
        self.assertEqual([(20, 30)], [
            (marker.start_tick, marker.end_tick) for marker in markers
        ])

    def test_tail_uses_duration_and_zero_length_tail_fails_closed(self):
        document = source(4)
        value = mapping(both=False)
        frames = worlds([
            (0, 2, 0), (0, 0, 0), (0, 0, 0), (0, 0, 0),
        ])
        markers = detect(document, value, frames)
        self.assertEqual((10, 30), (markers[0].start_tick, markers[0].end_tick))

        two = source(2)
        singleton = worlds([(0, 2, 0), (0, 0, 0)])
        with self.assertRaisesRegex(BvhContactError, "positive half-open"):
            detect(two, value, singleton, duration=10)

    def test_loop_seam_uses_both_incoming_and_outgoing_speed(self):
        document = source(5)
        value = mapping(both=False)
        value["clip"]["loop"] = True
        value["contact"].update(
            speed_threshold_source_units_per_second=100_000.0,
        )
        frames = worlds([
            (0, 0, 0), (0, 0, 2), (0, 0, 2), (0, 0, 2), (0, 0, 0),
        ])
        markers = detect(document, value, frames)
        self.assertEqual([(20, 40)], [
            (marker.start_tick, marker.end_tick) for marker in markers
        ])

    def test_disabled_contact_returns_an_empty_frozen_tuple(self):
        document = source(2)
        value = mapping()
        value["contact"] = {
            "enabled": False,
            "mode": "annotation_only",
            "interval": "half_open",
        }
        self.assertEqual((), detect(
            document, value, worlds([(0, 0, 0)] * 2, [(0, 0, 0)] * 2)
        ))


class BvhContactRejectionTests(unittest.TestCase):
    def test_missing_frames_joints_nonfinite_coordinates_and_ticks_fail(self):
        document = source(2)
        value = mapping()
        valid = worlds([(0, 0, 0)] * 2, [(0, 0, 0)] * 2)
        baseline = _projection(document, value, valid)
        first, second = baseline.frames
        missing = replace(first, joints=first.joints[:-1])
        left_name, left_point = second.joints[1]
        nonfinite_point = replace(left_point, world_xyz=(0.0, math.nan, 0.0))
        nonfinite = replace(
            second,
            joints=(second.joints[0], (left_name, nonfinite_point), second.joints[2]),
        )
        cases = (
            replace(baseline, frames=baseline.frames[:1]),
            replace(baseline, frames=(missing, second)),
            replace(baseline, frames=(first, nonfinite)),
            replace(baseline, frames=(first, replace(second, tick=0))),
            replace(baseline, duration_ticks=9),
            replace(baseline, source_sha256="f" * 64),
            replace(baseline, map_sha256="f" * 64),
        )
        for changed in cases:
            with self.subTest(changed=changed), self.assertRaises(BvhContactError):
                detect_bvh_contacts(document, value, projected=changed)

    def test_invalid_or_nonfinite_threshold_tampering_is_revalidated(self):
        document = source(2)
        frames = worlds([(0, 0, 0)] * 2, [(0, 0, 0)] * 2)
        for field, invalid in (
            ("height_threshold_source_units", -1.0),
            ("speed_threshold_source_units_per_second", math.nan),
            ("minimum_frames", True),
        ):
            value = deepcopy(mapping())
            value["contact"][field] = invalid
            projected = _projection(document, mapping(), frames)
            with self.subTest(field=field), self.assertRaises(BvhContactError):
                detect_bvh_contacts(document, value, projected=projected)


def _projection(document, value, frames):
    duration = (len(frames) - 1) * 10
    return BvhProjectedFrames(
        source_sha256=document.source_sha256,
        map_id=value["map_id"],
        map_sha256=bvh_map_sha256(value),
        clip_id=value["clip"]["clip_id"],
        loop=value["clip"]["loop"],
        duration_ticks=duration,
        frames=tuple(
            BvhProjectedFrame(
                tick=tick,
                joints=tuple(
                    (joint.name, BvhProjectedPoint(
                        tuple(frame[joint.name]), (0.0, 0.0), 0.0,
                    ))
                    for joint in document.joints
                ),
                end_sites=(), root_translation_normalized=(0.0, 0.0),
                segments=(),
            )
            for tick, frame in zip(ticks(len(frames)), frames, strict=True)
        ),
    )


if __name__ == "__main__":
    unittest.main()
