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
            "generation": {"method": "fixture", "requires_review": False},
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
        self.assertEqual(
            ["canonical_role", "side", "disposition"],
            snapshot["layers"][0]["reviewed_fields"],
        )
        self.assertEqual("ready", snapshot["qa"]["status"])

    def test_layer_review_provenance_is_field_specific(self) -> None:
        overrides = {"revision": 1, "layer_overrides": {"arm-layer": {"visible": False}}}
        layer = ResolvedProjectBuilder().build(project_fixture(), overrides)["layers"][0]
        self.assertEqual("manual_adjusted", layer["review_state"])
        self.assertEqual(["visible"], layer["reviewed_fields"])
        self.assertEqual("unclassified.arm", layer["canonical_role"])
        self.assertEqual([10, 20], layer["pivot_xy"])

    def test_split_spec_is_authoring_intent_not_a_reviewed_raster_claim(self) -> None:
        overrides = override_fixture()
        layer_patch = overrides["layer_overrides"]["arm-layer"]
        layer_patch.update(
            side="bilateral",
            disposition="split_left_right",
            split_spec={"parts": {"left": {"guide": []}, "right": {"guide": []}}},
        )

        snapshot = ResolvedProjectBuilder().build(project_fixture(), overrides)
        layer = snapshot["layers"][0]
        self.assertEqual(layer_patch["split_spec"], layer["split_spec"])
        self.assertNotIn("split_spec", layer["reviewed_fields"])
        self.assertEqual(["arm-layer"], snapshot["qa"]["unreviewed_split_layer_ids"])
        self.assertEqual("needs_review", snapshot["qa"]["status"])

    def test_split_decision_status_is_projected_without_mutating_intent(self) -> None:
        overrides = override_fixture()
        overrides["layer_overrides"]["arm-layer"].update(
            side="bilateral",
            disposition="split_left_right",
            split_spec={"parts": {"left": {}, "right": {}}},
        )
        decision = {
            "action": "accept",
            "split_artifact_sha256": "1" * 64,
            "operation_config_sha256": "2" * 64,
            "review_target_sha256": "3" * 64,
            "binding_status": "current",
        }
        overrides["split_decisions"] = {"arm-layer": decision}

        snapshot = ResolvedProjectBuilder().build(project_fixture(), overrides)
        layer = snapshot["layers"][0]
        self.assertEqual(decision, layer["split_decision"])
        self.assertEqual(["arm-layer"], snapshot["qa"]["accepted_split_layer_ids"])
        self.assertEqual([], snapshot["qa"]["unreviewed_split_layer_ids"])
        self.assertEqual("ready", snapshot["qa"]["status"])

        rejected = deepcopy(overrides)
        rejected["split_decisions"]["arm-layer"] = {
            **decision,
            "action": "reject",
            "reason": "wrong partition",
        }
        rejected_snapshot = ResolvedProjectBuilder().build(project_fixture(), rejected)
        self.assertEqual(
            ["arm-layer"], rejected_snapshot["qa"]["rejected_split_layer_ids"]
        )
        self.assertEqual("needs_review", rejected_snapshot["qa"]["status"])

    def test_split_qa_lists_are_mutually_exclusive_and_stale_is_pending(self) -> None:
        project = project_fixture()
        template = project["layers"][0]
        project["layers"] = []
        overrides = {"revision": 1, "split_decisions": {}}
        statuses = {
            "accepted": {"action": "accept", "binding_status": "current"},
            "rejected": {"action": "reject", "binding_status": "current"},
            "stale": {"action": "accept", "binding_status": "stale"},
            "unreviewed": None,
        }
        for index, (label, decision) in enumerate(statuses.items()):
            layer = deepcopy(template)
            layer.update(id=label, disposition="split", side="bilateral", z_index=index)
            project["layers"].append(layer)
            if decision is not None:
                overrides["split_decisions"][label] = decision
        qa = ResolvedProjectBuilder().build(project, overrides)["qa"]
        self.assertEqual(["accepted"], qa["accepted_split_layer_ids"])
        self.assertEqual(["rejected"], qa["rejected_split_layer_ids"])
        self.assertEqual(["stale"], qa["stale_split_layer_ids"])
        self.assertEqual(["unreviewed"], qa["unreviewed_split_layer_ids"])
        classified = [
            set(qa[field])
            for field in (
                "accepted_split_layer_ids",
                "rejected_split_layer_ids",
                "stale_split_layer_ids",
                "unreviewed_split_layer_ids",
            )
        ]
        self.assertTrue(all(not left & right for i, left in enumerate(classified) for right in classified[i + 1 :]))
        self.assertEqual("needs_review", qa["status"])

    def test_stale_split_decision_stays_pending_after_authoring_is_removed(self) -> None:
        overrides = override_fixture()
        overrides["split_decisions"] = {
            "arm-layer": {"action": "accept", "binding_status": "stale"}
        }
        qa = ResolvedProjectBuilder().build(project_fixture(), overrides)["qa"]
        self.assertEqual(["arm-layer"], qa["stale_split_layer_ids"])
        self.assertEqual("needs_review", qa["status"])

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

    def test_candidate_actions_are_distinct_and_analysis_is_hashed(self) -> None:
        overrides = {"revision": 5, "joint_decisions": {}}
        analysis = {
            "provider": "fixture-provider",
            "provider_version": "2",
            "input_sha256": "1" * 64,
            "config_sha256": "2" * 64,
            "run_sha256": "3" * 64,
        }
        overrides["joint_decisions"] = {
            "elbow.left": {
                "action": "accept",
                "candidate_artifact_sha256": "4" * 64,
                "candidate_id": "elbow.left.pose.fixture",
                "final_xy": [27.0, 39.0],
                "analysis": analysis,
            },
            "head": {
                "action": "unobservable",
                "candidate_artifact_sha256": "4" * 64,
                "reason": "covered by hair",
                "analysis": analysis,
            },
        }
        snapshot = ResolvedProjectBuilder().build(project_fixture(), overrides)
        joints = {item["id"]: item for item in snapshot["skeleton"]["joints"]}
        self.assertEqual((27.0, 39.0), (joints["elbow.left"]["x"], joints["elbow.left"]["y"]))
        self.assertEqual("candidate_accepted", joints["elbow.left"]["review_state"])
        self.assertEqual("unobservable", joints["head"]["review_state"])
        self.assertEqual([], snapshot["qa"]["unresolved_joint_ids"])
        self.assertEqual(["head"], snapshot["qa"]["unobservable_joint_ids"])
        self.assertEqual("4" * 64, snapshot["inputs"]["candidate_analyses"][0]["candidate_artifact_sha256"])

        changed = deepcopy(overrides)
        changed["joint_decisions"]["elbow.left"]["analysis"]["provider_version"] = "3"
        self.assertNotEqual(
            snapshot["sha256"],
            ResolvedProjectBuilder().build(project_fixture(), changed)["sha256"],
        )

    def test_rejected_and_required_review_joints_cannot_be_ready(self) -> None:
        project = project_fixture()
        project["skeleton"]["generation"]["requires_review"] = True
        snapshot = ResolvedProjectBuilder().build(project, {"revision": 0})
        self.assertEqual(["elbow.left", "head"], snapshot["qa"]["unresolved_joint_ids"])

        analysis = {
            "provider": "fixture-provider",
            "provider_version": "2",
            "input_sha256": "1" * 64,
            "config_sha256": "2" * 64,
            "run_sha256": "3" * 64,
        }
        rejected = {
            "revision": 1,
            "joint_overrides": {"head": {"x": 50, "y": 20}},
            "joint_decisions": {
                "elbow.left": {
                    "action": "reject",
                    "candidate_artifact_sha256": "4" * 64,
                    "candidate_id": "elbow.left.pose.fixture",
                    "reason": "wrong elbow",
                    "analysis": analysis,
                }
            },
        }
        snapshot = ResolvedProjectBuilder().build(project, rejected)
        self.assertEqual(["elbow.left"], snapshot["qa"]["rejected_joint_ids"])
        self.assertEqual(["elbow.left"], snapshot["qa"]["unresolved_joint_ids"])
        self.assertEqual("needs_review", snapshot["qa"]["status"])


if __name__ == "__main__":
    unittest.main()
