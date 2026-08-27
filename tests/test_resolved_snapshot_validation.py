"""Dependency-free semantic validation for resolved project v1 snapshots."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from autospine_workbench.resolved_project import ResolvedProjectBuilder  # noqa: E402
from autospine_workbench.resolved_snapshot_validation import (  # noqa: E402
    ResolvedSnapshotValidationError,
    require_resolved_snapshot,
    resolved_snapshot_sha256,
)
from tests.resolved_snapshot_helpers import (  # noqa: E402
    PROJECT_ID,
    REVISION,
    reseal,
    resolved_snapshot_fixture,
    with_candidate_accept,
)


class ResolvedSnapshotValidationTests(unittest.TestCase):
    def test_complete_snapshot_and_expected_context_validate(self) -> None:
        document = resolved_snapshot_fixture()
        require_resolved_snapshot(
            document,
            expected_project_id=PROJECT_ID,
            expected_revision=REVISION,
            expected_base_project_sha256="a" * 64,
            expected_override_sha256="b" * 64,
        )
        self.assertEqual(document["sha256"], resolved_snapshot_sha256(document))

    def test_candidate_inventory_and_run_identity_validate(self) -> None:
        document = with_candidate_accept(resolved_snapshot_fixture())
        require_resolved_snapshot(document)
        self.assertEqual(
            document["skeleton"]["joints"][3]["decision"]["analysis"],
            {key: value for key, value in document["inputs"]["candidate_analyses"][0].items()
             if key != "candidate_artifact_sha256"},
        )

    def test_hash_is_deterministic_and_tampering_fails(self) -> None:
        first = resolved_snapshot_fixture()
        second = resolved_snapshot_fixture()
        self.assertEqual(first, second)
        first["layers"][0]["name"] = "tampered"
        with self.assertRaisesRegex(ResolvedSnapshotValidationError, "canonical snapshot content"):
            require_resolved_snapshot(first)

    def test_unknown_authority_field_fails_even_when_resealed(self) -> None:
        document = resolved_snapshot_fixture()
        document["layers"][0]["metrics"]["release_approved"] = True
        document = reseal(document)
        with self.assertRaisesRegex(ResolvedSnapshotValidationError, "authority field"):
            require_resolved_snapshot(document)

    def test_nonfinite_and_out_of_canvas_coordinates_fail(self) -> None:
        nonfinite = resolved_snapshot_fixture()
        nonfinite["skeleton"]["joints"][0]["x"] = float("nan")
        with self.assertRaisesRegex(ResolvedSnapshotValidationError, "finite"):
            require_resolved_snapshot(nonfinite)

        outside = resolved_snapshot_fixture()
        outside["layers"][0]["pivot_xy"] = [201.0, 10.0]
        with self.assertRaisesRegex(ResolvedSnapshotValidationError, "inside the canvas"):
            require_resolved_snapshot(reseal(outside))

    def test_duplicate_ids_and_broken_bone_references_fail(self) -> None:
        duplicate = resolved_snapshot_fixture()
        duplicate["skeleton"]["joints"][1]["id"] = "root"
        with self.assertRaisesRegex(ResolvedSnapshotValidationError, "duplicated"):
            require_resolved_snapshot(reseal(duplicate))

        broken = resolved_snapshot_fixture()
        broken["skeleton"]["bones"][0]["end_joint_id"] = "missing"
        with self.assertRaisesRegex(ResolvedSnapshotValidationError, "unknown joint"):
            require_resolved_snapshot(reseal(broken))

    def test_candidate_inventory_cannot_be_missing_or_spoofed(self) -> None:
        missing = with_candidate_accept(resolved_snapshot_fixture())
        missing["inputs"]["candidate_analyses"] = []
        with self.assertRaisesRegex(ResolvedSnapshotValidationError, "artifact inventory"):
            require_resolved_snapshot(reseal(missing))

        bad_run = with_candidate_accept(resolved_snapshot_fixture())
        bad_run["inputs"]["candidate_analyses"][0]["run_sha256"] = "9" * 64
        bad_run["skeleton"]["joints"][3]["decision"]["analysis"]["run_sha256"] = "9" * 64
        with self.assertRaisesRegex(ResolvedSnapshotValidationError, "run identity"):
            require_resolved_snapshot(reseal(bad_run))

    def test_candidate_state_and_final_coordinates_are_derived(self) -> None:
        wrong_xy = with_candidate_accept(resolved_snapshot_fixture())
        wrong_xy["skeleton"]["joints"][3]["decision"]["final_xy"] = [1.0, 2.0]
        with self.assertRaisesRegex(ResolvedSnapshotValidationError, "resolved joint"):
            require_resolved_snapshot(reseal(wrong_xy))

        wrong_state = with_candidate_accept(resolved_snapshot_fixture())
        wrong_state["skeleton"]["joints"][3]["decision_kind"] = "candidate_reject"
        with self.assertRaisesRegex(ResolvedSnapshotValidationError, "review state"):
            require_resolved_snapshot(reseal(wrong_state))

    def test_current_split_is_bound_to_current_authoring(self) -> None:
        wrong_spec = resolved_snapshot_fixture()
        decision = wrong_spec["layers"][1]["split_decision"]
        decision["analysis"]["split_spec_sha256"] = "f" * 64
        with self.assertRaisesRegex(ResolvedSnapshotValidationError, "current split_spec"):
            require_resolved_snapshot(reseal(wrong_spec))

        masquerade = resolved_snapshot_fixture()
        masquerade["layers"][1]["disposition"] = "keep"
        with self.assertRaisesRegex(ResolvedSnapshotValidationError, "bilateral split"):
            require_resolved_snapshot(reseal(masquerade))

    def test_stale_split_cannot_remain_in_accepted_qa(self) -> None:
        document = resolved_snapshot_fixture()
        document["layers"][1]["split_decision"]["binding_status"] = "stale"
        with self.assertRaisesRegex(ResolvedSnapshotValidationError, "accepted_split"):
            require_resolved_snapshot(reseal(document))

        document["qa"]["accepted_split_layer_ids"] = []
        document["qa"]["stale_split_layer_ids"] = ["layer-001-legwear"]
        document["qa"]["status"] = "needs_review"
        require_resolved_snapshot(reseal(document))

    def test_qa_lists_and_status_are_recomputed(self) -> None:
        document = resolved_snapshot_fixture()
        joint = document["skeleton"]["joints"][3]
        joint["review_state"] = "candidate_rejected"
        joint["decision_kind"] = "candidate_reject"
        analysis = {
            "provider": "fixture-provider",
            "provider_version": "2.0.0",
            "input_sha256": "6" * 64,
            "config_sha256": "7" * 64,
        }
        analysis["run_sha256"] = canonical_sha256(analysis)
        joint["decision"] = {
            "action": "reject",
            "candidate_artifact_sha256": "8" * 64,
            "candidate_id": "knee.left.pose.0123456789ab",
            "reason": "wrong candidate",
            "analysis": analysis,
        }
        document["inputs"]["candidate_analyses"] = [
            {"candidate_artifact_sha256": "8" * 64, **analysis}
        ]
        with self.assertRaisesRegex(ResolvedSnapshotValidationError, "unresolved_joint_ids"):
            require_resolved_snapshot(reseal(document))

        document["qa"]["unresolved_joint_ids"] = ["knee.left"]
        document["qa"]["rejected_joint_ids"] = ["knee.left"]
        document["qa"]["status"] = "needs_review"
        require_resolved_snapshot(reseal(document))

    def test_trusted_context_mismatch_fails_closed(self) -> None:
        document = resolved_snapshot_fixture()
        with self.assertRaisesRegex(ResolvedSnapshotValidationError, "trusted project"):
            require_resolved_snapshot(document, expected_project_id="other-project")
        with self.assertRaisesRegex(ResolvedSnapshotValidationError, "trusted identity"):
            require_resolved_snapshot(document, expected_override_sha256="c" * 64)

    def test_two_real_historical_snapshots_keep_their_approved_v1_hashes(self) -> None:
        from autospine_workbench.project_store import ProjectStore

        audit_root = ROOT.parent / "tmp" / "psd_audit" / "results"
        cases = (
            (
                "seethrough_output",
                "r000005.json",
                "3d96f605d428f1dbe66198c8a864004631ad1627839bf9849493d44f60178f11",
            ),
            (
                "seethrough_output_5",
                "r000007.json",
                "0d959229af6916e9878f509b43c73d29b084043f4b84620966fad3d76d0d0ece",
            ),
        )
        if not all((audit_root / project_id / "audit.json").is_file() for project_id, _, _ in cases):
            self.skipTest("real See-through audit fixtures are not present")
        state_root = ROOT / "workspace"
        store = ProjectStore(ROOT.parent, state_root=state_root)
        for project_id, history_name, expected_sha in cases:
            history = state_root / "overrides" / project_id / "history" / history_name
            if not history.is_file():
                self.skipTest(f"historical override is not present: {history}")
            base = store._build_project(  # noqa: SLF001 - exact historical fixture reconstruction
                store._record(project_id),  # noqa: SLF001
                include_overrides=False,
            )
            override = json.loads(history.read_text(encoding="utf-8"))
            snapshot = ResolvedProjectBuilder().build(base, override)
            require_resolved_snapshot(
                snapshot,
                expected_project_id=project_id,
                expected_revision=override["revision"],
            )
            self.assertEqual(expected_sha, snapshot["sha256"])


if __name__ == "__main__":
    unittest.main()
