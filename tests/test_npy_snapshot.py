"""Security and determinism tests for the dependency-free NPY decoder."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import math
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.npy_snapshot import (  # noqa: E402
    NpySnapshotError,
    parse_npy_snapshot,
)
from tests.fixtures.kimodo_npz_archive import (  # noqa: E402
    bool_payload,
    build_npy,
    float_payload,
)


class NpySnapshotTests(unittest.TestCase):
    def test_v1_v2_float_and_boolean_snapshots_are_immutable(self):
        shape = (2, 2)
        values = [0.0, 1.25, -2.5, 3.0]
        for version in ((1, 0), (2, 0)):
            raw = build_npy("<f4", shape, float_payload(shape, values), version=version)
            result = parse_npy_snapshot(
                raw, name="values", expected_dtype="<f4", expected_shape=shape
            )
            self.assertEqual(values, [result.float_at(row, column)
                                      for row in range(2) for column in range(2)])
            self.assertEqual(values, list(result.iter_floats()))
            self.assertEqual(raw, bytes(raw))
            with self.assertRaises(FrozenInstanceError):
                result.name = "changed"  # type: ignore[misc]

        flags = parse_npy_snapshot(
            build_npy("|b1", shape, bool_payload(shape, [False, True, True, False])),
            name="flags", expected_dtype="|b1", expected_shape=shape,
        )
        self.assertEqual([False, True, True, False], [
            flags.bool_at(row, column) for row in range(2) for column in range(2)
        ])

    def test_executable_ambiguous_or_nonportable_headers_fail_closed(self):
        shape = (2, 2)
        payload = float_payload(shape)
        headers = (
            "{'descr': '|O', 'fortran_order': False, 'shape': (2, 2), }",
            "{'descr': '=f4', 'fortran_order': False, 'shape': (2, 2), }",
            "{'descr': '>f4', 'fortran_order': False, 'shape': (2, 2), }",
            "{'descr': [('x','<f4')], 'fortran_order': False, 'shape': (2, 2), }",
            "{'descr': '<f4', 'descr': '<f4', 'shape': (2, 2), }",
            "{'descr': '<f4', 'fortran_order': False, 'shape': (2, 2), 'x': 1}",
            "__import__('os').system('echo unsafe')",
        )
        for header in headers:
            raw = build_npy("<f4", shape, payload, header_text=header)
            with self.subTest(header=header), self.assertRaises(NpySnapshotError):
                parse_npy_snapshot(
                    raw, name="bad", expected_dtype="<f4", expected_shape=shape
                )
        fortran = build_npy("<f4", shape, payload, fortran_order=True)
        with self.assertRaisesRegex(NpySnapshotError, "Fortran"):
            parse_npy_snapshot(
                fortran, name="bad", expected_dtype="<f4", expected_shape=shape
            )

    def test_bad_version_shape_length_trailing_and_values_fail_closed(self):
        shape = (2, 2)
        good = build_npy("<f4", shape, float_payload(shape))
        cases = (
            b"not-npy",
            good[:9],
            good[:-1],
            good + b"\x00",
            build_npy("<f4", shape, float_payload(shape), version=(3, 0)),
            build_npy("<f4", shape, float_payload(shape),
                      header_text="{'descr': '<f4', 'fortran_order': False, 'shape': (0, 2), }"),
            build_npy("<f4", shape, struct.pack("<ffff", 0, math.nan, 0, 0)),
            build_npy("<f4", shape, struct.pack("<ffff", 0, math.inf, 0, 0)),
            build_npy("|b1", shape, bytes((0, 1, 2, 0))),
        )
        for raw in cases:
            dtype = "|b1" if b"'|b1'" in raw else "<f4"
            with self.subTest(raw=raw[:20]), self.assertRaises(NpySnapshotError):
                parse_npy_snapshot(
                    raw, name="bad", expected_dtype=dtype, expected_shape=shape
                )

    def test_expected_profile_index_and_resource_limits_are_enforced(self):
        shape = (2, 2)
        raw = build_npy("<f4", shape, float_payload(shape))
        for dtype, expected_shape in (("|b1", shape), ("<f4", (4,))):
            with self.assertRaisesRegex(NpySnapshotError, "differs from profile"):
                parse_npy_snapshot(
                    raw, name="values", expected_dtype=dtype,
                    expected_shape=expected_shape,
                )
        value = parse_npy_snapshot(
            raw, name="values", expected_dtype="<f4", expected_shape=shape
        )
        for indices in ((0,), (0, 2), (True, 0), (-1, 0)):
            with self.subTest(indices=indices), self.assertRaises(NpySnapshotError):
                value.float_at(*indices)
        with self.assertRaises(NpySnapshotError):
            value.bool_at(0, 0)
        with patch("autospine_workbench.npy_snapshot.MAX_NPY_MEMBER_BYTES", 1):
            with self.assertRaisesRegex(NpySnapshotError, "byte limit"):
                parse_npy_snapshot(
                    raw, name="values", expected_dtype="<f4", expected_shape=shape
                )
        with patch("autospine_workbench.npy_snapshot.MAX_NPY_HEADER_BYTES", 1):
            with self.assertRaisesRegex(NpySnapshotError, "header"):
                parse_npy_snapshot(
                    raw, name="values", expected_dtype="<f4", expected_shape=shape
                )


if __name__ == "__main__":
    unittest.main()
