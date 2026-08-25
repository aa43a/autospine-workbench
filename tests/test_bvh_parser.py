"""Strict syntax-only BVH hierarchy and motion parser tests."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import hashlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
FIXTURE = ROOT / "tests" / "fixtures" / "minimal_motion.bvh"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.bvh_parser import (  # noqa: E402
    BvhParseError,
    parse_bvh,
)


def source() -> bytes:
    return FIXTURE.read_bytes()


def changed(old: bytes, new: bytes) -> bytes:
    raw = source()
    assert old in raw
    return raw.replace(old, new, 1)


class BvhParserSuccessTests(unittest.TestCase):
    def test_fixture_preserves_hierarchy_channel_order_and_samples(self) -> None:
        raw = source()
        first, second = parse_bvh(raw), parse_bvh(raw)

        self.assertEqual(first, second)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), first.source_sha256)
        self.assertEqual(len(raw), first.source_byte_length)
        self.assertEqual(("Hips", "Chest"), tuple(j.name for j in first.joints))
        self.assertIsNone(first.joints[0].parent_index)
        self.assertEqual(0, first.joints[1].parent_index)
        self.assertEqual(
            ("Zrotation", "Xrotation", "Yrotation"),
            first.joints[0].rotation_order,
        )
        self.assertEqual(
            ("Yrotation", "Zrotation", "Xrotation"),
            first.joints[1].rotation_order,
        )
        self.assertEqual((0.0, 8.0, 0.0), first.joints[1].end_site_offset)
        self.assertEqual((2, 9, 18), (
            first.frame_count, first.channel_count, first.total_sample_count
        ))
        self.assertEqual((1.0, 101.0, 2.0), first.frames[1][:3])
        self.assertFalse(hasattr(first, "coordinate_system"))

    def test_value_objects_are_frozen_and_contain_only_immutable_tuples(self) -> None:
        document = parse_bvh(source())
        with self.assertRaises(FrozenInstanceError):
            document.frame_count = 9  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            document.joints[0].name = "changed"  # type: ignore[misc]
        with self.assertRaises(TypeError):
            document.frames[0][0] = 9  # type: ignore[index]

    def test_colon_joint_names_split_labels_and_crlf_are_supported(self) -> None:
        raw = source().replace(b"ROOT Hips", b"ROOT mixamorig:Hips")
        raw = raw.replace(b"Frames:", b"Frames :")
        raw = raw.replace(b"Time:", b"Time :").replace(b"\n", b"\r\n")
        document = parse_bvh(raw)

        self.assertEqual("mixamorig:Hips", document.joints[0].name)
        self.assertEqual(2, document.frame_count)

    def test_zero_frame_motion_is_valid_only_without_samples(self) -> None:
        raw = source().split(b"\n0 100 0 10", 1)[0]
        raw = raw.replace(b"Frames: 2", b"Frames: 0")
        document = parse_bvh(raw)

        self.assertEqual(0, document.frame_count)
        self.assertEqual((), document.frames)
        self.assertEqual(0, document.total_sample_count)


class BvhParserRejectionTests(unittest.TestCase):
    def assert_rejected(self, raw: bytes, message: str | None = None) -> None:
        context = self.assertRaisesRegex(BvhParseError, message) if message else self.assertRaises(BvhParseError)
        with context:
            parse_bvh(raw)

    def test_root_and_nonroot_channel_profiles_are_exact(self) -> None:
        root = b"CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation"
        joint = b"CHANNELS 3 Yrotation Zrotation Xrotation"
        cases = (
            (root, b"CHANNELS 3 Zrotation Xrotation Yrotation", "root channel count"),
            (root, b"CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Wrotation", "allowed channel"),
            (root, b"CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Xrotation", "allowed channel"),
            (joint, b"CHANNELS 4 Yrotation Zrotation Xrotation Xposition", "non-root channel count"),
            (joint, b"CHANNELS 3 Yrotation Zrotation Xposition", "allowed channel"),
            (joint, b"CHANNELS 3 Yrotation Zrotation Zrotation", "allowed channel"),
        )
        for old, new, message in cases:
            with self.subTest(new=new):
                self.assert_rejected(changed(old, new), message)

    def test_huge_declared_channel_count_is_rejected_before_consumption(self) -> None:
        raw = changed(b"CHANNELS 6", b"CHANNELS 999999999999999999999")
        self.assert_rejected(raw, "root channel count")

    def test_duplicate_joint_missing_root_second_root_and_reserved_name_fail(self) -> None:
        duplicate = changed(b"JOINT Chest", b"JOINT Hips")
        missing_root = changed(b"ROOT Hips", b"JOINT Hips")
        second_root = changed(b"MOTION", b"ROOT Other { OFFSET 0 0 0 CHANNELS 6 Xposition Yposition Zposition Xrotation Yrotation Zrotation } MOTION")
        reserved = changed(b"JOINT Chest", b"JOINT MOTION")
        for raw in (duplicate, missing_root, second_root, reserved):
            with self.subTest(raw=raw[:80]):
                self.assert_rejected(raw)

    def test_nonfinite_and_malformed_numbers_are_rejected(self) -> None:
        cases = (
            (b"OFFSET 0 100 0", b"OFFSET NaN 100 0"),
            (b"OFFSET 0 100 0", b"OFFSET 1e999 100 0"),
            (b"OFFSET 0 100 0", b"OFFSET 1000001 100 0"),
            (b"Frames: 2", b"Frames: -2"),
            (b"Frame Time: 0.0333333", b"Frame Time: 0"),
            (b"Frame Time: 0.0333333", b"Frame Time: inf"),
            (b"Frame Time: 0.0333333", b"Frame Time: 61"),
            (b"0 100 0 10", b"0 100 0 1e999"),
            (b"0 100 0 10", b"0 100 0 1000001"),
            (b"0 100 0 10", b"0 100 0 1_0"),
        )
        for old, new in cases:
            with self.subTest(new=new):
                self.assert_rejected(changed(old, new))

    def test_truncation_frame_value_mismatch_and_extra_tokens_fail(self) -> None:
        cases = (
            source()[:40],
            changed(b"Frames: 2", b"Frames: 3"),
            changed(b"Frames: 2", b"Frames: 1"),
            source() + b" EXTRA",
        )
        for raw in cases:
            with self.subTest(length=len(raw)):
                self.assert_rejected(raw)

    def test_end_site_cannot_be_duplicated_or_followed_by_a_joint(self) -> None:
        block = b"End Site\n    {\n      OFFSET 0 8 0\n    }"
        duplicate = changed(block, block + b"\n    " + block)
        followed = changed(block, block + b"\n    JOINT Tail { OFFSET 0 1 0 CHANNELS 3 Xrotation Yrotation Zrotation }")
        for raw in (duplicate, followed):
            self.assert_rejected(raw)

    def test_fixed_joint_depth_frame_and_sample_limits_are_enforced(self) -> None:
        cases = (
            ("MAX_BVH_JOINTS", 1, "joint count"),
            ("MAX_BVH_DEPTH", 1, "hierarchy depth"),
            ("MAX_BVH_FRAMES", 1, "frame count"),
            ("MAX_BVH_TOTAL_SAMPLES", 17, "sample count"),
        )
        for constant, limit, message in cases:
            with (
                self.subTest(constant=constant),
                patch(f"autospine_workbench.bvh_parser.{constant}", limit),
            ):
                self.assert_rejected(source(), message)

    def test_exact_parser_resource_boundaries_are_admitted(self) -> None:
        with (
            patch("autospine_workbench.bvh_parser.MAX_BVH_JOINTS", 2),
            patch("autospine_workbench.bvh_parser.MAX_BVH_DEPTH", 2),
            patch("autospine_workbench.bvh_parser.MAX_BVH_FRAMES", 2),
            patch("autospine_workbench.bvh_parser.MAX_BVH_TOTAL_SAMPLES", 18),
        ):
            document = parse_bvh(source())
        self.assertEqual(18, document.total_sample_count)

    def test_errors_include_source_location(self) -> None:
        with self.assertRaisesRegex(
            BvhParseError, r"byte \d+ \(line \d+, column \d+\)"
        ):
            parse_bvh(changed(b"MOTION", b"BROKEN"))


if __name__ == "__main__":
    unittest.main()
