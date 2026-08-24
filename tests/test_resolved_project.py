"""Tests for effective authoring snapshots."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest


WORKBENCH_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = WORKBENCH_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from autospine_workbench.resolved_project import (  # noqa: E402
    ResolvedProjectBuilder,
    canonical_sha256,
)


def project_fixture() -> dict:
    return {
        "id": "sample",
        "source": {"sha256": "a" * 64},
        "canvas": {"width": 100, "height": 200},
        "layers": [
            {
                "id": "arm-layer",
                "canonical_role": "unclassified.arm",
                "side": "unknown",
                "disposition": "review",
                "visible": True,
                "empty": False,
                "pivot_xy": [10, 20],
            }
        ],
        "skeleton": {
            "joints": [
                {"id": "elbow.left", "x": 20, "y": 30, "confidence": 0.2},
                {"id": "head", "x": 50, "y": 20, "confidence": 0.9},
            ],
            "bones": [],
        },
    }


def override_fixture() -> dict:
    return {
        "revision": 3,
        "joint_overrides": {
            "elbow.left": {
                "x": 24.5,
                "y": 35.5,
                "confidence": 1.0,
                "reason": "manual review",
            }
        },
        "layer_overrides": {
            "arm-layer": {
                "canonical_role": "body.arm.lower",
                "side": "left",
                "disposition": "keep",
            }
        },
        "notes": "reviewed",
    }


class ResolvedProjectBuilderTests(unittest.TestCase):
    def test_applies_decisions_without_mutating_inputs_or_model_confidence(self) -> None:
        project = project_fixture()
        overrides = override_fixture()
        project_before = deepcopy(project)
        overrides_before = deepcopy(overrides)

        snapshot = ResolvedProjectBuilder().build(project, overrides)

        self.assertEqual(project_before, project)
        self.assertEqual(overrides_before, overrides)
        elbow = snapshot["skeleton"]["joints"][0]
        self.assertEqual((24.5, 35.5), (elbow["x"], elbow["y"]))
        self.assertEqual(0.2, elbow["model_confidence"])
        self.assertEqual(1.0, elbow["legacy_review_confidence"])
        self.assertEqual("manual_adjusted", elbow["review_state"])
        self.assertEqual("left", snapshot["layers"][0]["side"])
        self.assertEqual("ready", snapshot["qa"]["status"])

    def test_unreviewed_low_confidence_joint_remains_visible_in_qa(self) -> None:
        snapshot = ResolvedProjectBuilder().build(project_fixture(), {"revision": 0})
        self.assertEqual("needs_review", snapshot["qa"]["status"])
        self.assertEqual(["elbow.left"], snapshot["qa"]["unresolved_joint_ids"])
        self.assertEqual(["arm-layer"], snapshot["qa"]["review_layer_ids"])

    def test_snapshot_hash_is_deterministic_and_covers_revision(self) -> None:
        builder = ResolvedProjectBuilder()
        first = builder.build(project_fixture(), override_fixture())
        second = builder.build(project_fixture(), override_fixture())
        self.assertEqual(first, second)
        self.assertEqual(first["sha256"], canonical_sha256({k: v for k, v in first.items() if k != "sha256"}))
        changed = override_fixture()
        changed["revision"] = 4
        self.assertNotEqual(first["sha256"], builder.build(project_fixture(), changed)["sha256"])


if __name__ == "__main__":
    unittest.main()
