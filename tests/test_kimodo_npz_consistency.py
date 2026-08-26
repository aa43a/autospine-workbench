"""Redundant-matrix and position evidence tests for Kimodo NPZ."""

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
    KimodoNpzConsistencyError,
    validate_kimodo_consistency,
)
from autospine_workbench.kimodo_npz_reader import decode_kimodo_npz  # noqa: E402
from tests.fixtures.kimodo_npz_archive import (  # noqa: E402
    build_npy,
    build_npz,
    float_payload,
    motion_member_bytes,
)
from tests.kimodo_npz_helpers import source_document  # noqa: E402


def fixture(**keywords):
    members = motion_member_bytes(**keywords)
    raw = build_npz(members)
    source = source_document(
        raw,
        inventory=keywords.get("inventory", "complete-v1"),
        contact_layout=(
            "left-heel-toe-right-heel-toe-v1"
            if keywords.get("contacts", 4) == 4 else
            "left-heel-toe-toe_end-right-heel-toe-toe_end-v1"
        ),
    )
    return raw, source, decode_kimodo_npz(raw, source)


class KimodoNpzConsistencyTests(unittest.TestCase):
    def test_local_root_truth_rebuilds_global_and_posed_evidence(self):
        for inventory in ("core-v1", "complete-v1"):
            _raw, source, snapshot = fixture(inventory=inventory)
            result = validate_kimodo_consistency(snapshot, source)
            self.assertEqual(3, result.frame_count)
            self.assertLessEqual(result.max_global_matrix_error, 1e-6)
            self.assertLessEqual(result.max_position_error_meters, 1e-6)
            self.assertLessEqual(result.max_root_position_error_meters, 1e-6)
            self.assertEqual(
                None if inventory == "core-v1" else 0.0,
                result.max_heading_norm_error,
            )
            self.assertAlmostEqual(0.1, result.positions[1][0][0], places=6)

    def test_non_so3_and_local_global_hierarchy_drift_fail(self):
        scaling = ((2.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
        _, source, snapshot = fixture(
            local_overrides={(1, "LeftArm"): scaling}
        )
        with self.assertRaisesRegex(KimodoNpzConsistencyError, r"SO\(3\)"):
            validate_kimodo_consistency(snapshot, source)

        rotate_90 = ((0.0, -1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0))
        _, source, snapshot = fixture(
            global_overrides={(1, "LeftArm"): rotate_90}
        )
        with self.assertRaisesRegex(KimodoNpzConsistencyError, "hierarchy"):
            validate_kimodo_consistency(snapshot, source)

    def test_posed_and_root_evidence_cannot_drift_from_rebuilt_fk(self):
        cases = (
            {(1, "LeftHand"): (9.0, 9.0, 9.0)},
            {(1, "Hips"): (0.2, 1.0, 0.0)},
        )
        for overrides in cases:
            _raw, source, snapshot = fixture(posed_overrides=overrides)
            with self.subTest(overrides=overrides), self.assertRaisesRegex(
                KimodoNpzConsistencyError, "posed joint"
            ):
                validate_kimodo_consistency(snapshot, source)

    def test_complete_heading_is_evidence_not_an_unchecked_hint(self):
        members = motion_member_bytes()
        shape = (3, 2)
        members["global_root_heading.npy"] = build_npy(
            "<f4", shape, float_payload(shape, [0.0] * 6)
        )
        raw = build_npz(members)
        source = source_document(raw)
        snapshot = decode_kimodo_npz(raw, source)
        with self.assertRaisesRegex(KimodoNpzConsistencyError, "unit direction"):
            validate_kimodo_consistency(snapshot, source)

    def test_snapshot_and_sidecar_identity_are_cross_bound(self):
        _raw, source, snapshot = fixture()
        changed = deepcopy(source)
        changed["source_id"] = "kimodo.other"
        with self.assertRaisesRegex(KimodoNpzConsistencyError, "differs"):
            validate_kimodo_consistency(snapshot, changed)


if __name__ == "__main__":
    unittest.main()
