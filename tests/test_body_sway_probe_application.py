"""Exact-head, inventory, and read-only P10.2 application tests."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.body_sway_probe_application import (  # noqa: E402
    BodySwayProbeApplication,
    BodySwayProbeApplicationHeadChanged,
    BodySwayProbeApplicationUnavailable,
)
from autospine_workbench.current_project_chain import (  # noqa: E402
    CurrentProjectChain,
)
from autospine_workbench.body_sway_canvas_adjustment_candidates import (  # noqa: E402
    compile_body_sway_canvas_adjustment_candidates,
)
from autospine_workbench.body_sway_derived_cache import (  # noqa: E402
    clear_body_sway_derived_cache,
)
from autospine_workbench.body_sway_probe_inputs import (  # noqa: E402
    require_body_sway_probe_inputs,
)
from autospine_workbench.body_sway_probe_report import (  # noqa: E402
    compile_body_sway_probe_report,
)
from autospine_workbench.idle_behavior_decision import (  # noqa: E402
    build_idle_behavior_decision,
)
from autospine_workbench.idle_behavior_review_address import (  # noqa: E402
    IdleBehaviorReviewAddress,
)
from autospine_workbench.idle_behavior_review_head import (  # noqa: E402
    IdleBehaviorReviewHeadError,
    read_idle_behavior_review_head,
)
from autospine_workbench.idle_behavior_review_replay import (  # noqa: E402
    IdleBehaviorReviewEvidence,
    replay_idle_behavior_review_package,
)
from autospine_workbench import idle_behavior_review_replay  # noqa: E402
from autospine_workbench.idle_behavior_review_store import (  # noqa: E402
    IdleBehaviorReviewStore,
)
from tests.motion_policy_preflight_helpers import tree_snapshot  # noqa: E402
from tests.p10_candidate_helpers import P10PersistedFixture  # noqa: E402
from tests.test_idle_behavior_review_submission import valid_submission  # noqa: E402


class BodySwayProbeApplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = P10PersistedFixture(Path(cls.temporary.name))
        reviewed = cls.fixture.reviewed
        cls.address = IdleBehaviorReviewAddress(
            "a" * 64, cls.fixture.mesh.project_id, "motion-a",
            reviewed.clip_id, reviewed.motion_instance_v2_sha256,
            reviewed.bundle_sha256,
            reviewed.motion_policy_decision_sha256,
        )
        cls.evidence = replay_idle_behavior_review_package(
            cls.fixture.state, cls.address,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def setUp(self) -> None:
        clear_body_sway_derived_cache()
        shutil.rmtree(self._history_root(), ignore_errors=True)
        self.service = BodySwayProbeApplication(self.fixture.state)

    def _history_root(self) -> Path:
        return (
            self.fixture.state / "builds" / self.address.project_id
            / "idle-behavior-decisions"
        )

    def _current_chains(self):
        return {
            self.address.project_id: CurrentProjectChain(
                self.address.project_id,
                self.evidence.mesh_bundle.resolved_project_sha256,
                self.evidence.mesh_bundle.layer_manifest_sha256,
            ),
        }

    @contextmanager
    def _patch_detail(self):
        with patch(
            "autospine_workbench.body_sway_probe_application."
            "get_idle_behavior_review_address",
            return_value=self.address,
        ), patch(
            "autospine_workbench.body_sway_probe_application."
            "replay_idle_behavior_review_package",
            return_value=self.evidence,
        ):
            yield

    @contextmanager
    def _patch_inventory(self, addresses=None, evidences=None):
        addresses = tuple(addresses or (self.address,))
        evidences = tuple(evidences or (self.evidence,))
        by_id = {row.address.package_id: row for row in evidences}
        with patch(
            "autospine_workbench.body_sway_probe_packages."
            "list_idle_behavior_review_addresses",
            return_value=(addresses, 0),
        ), patch(
            "autospine_workbench.body_sway_probe_packages."
            "list_current_idle_behavior_review_addresses",
            return_value=(addresses, 0),
        ), patch(
            "autospine_workbench.body_sway_probe_packages."
            "replay_idle_behavior_review_package",
            side_effect=lambda _root, address: by_id[address.package_id],
        ):
            yield

    def _publish(
        self, action="adjust", *, revision=1,
        previous=None, cycles=2,
    ):
        candidates = self.evidence.candidates.document
        feature = next(
            row for row in candidates["features"]
            if row["feature_id"] == "body_sway"
        )
        parameters = valid_submission()["parameters"] \
            if action == "adjust" else None
        if parameters is not None:
            parameters["cycles"] = cycles
        row = {
            "candidate_id": feature["candidate_id"],
            "feature_id": "body_sway",
            "action": action,
            "reason_code": f"human-{action}-test",
            "payload": parameters,
            "probe_status": (
                "pending_probe" if action == "adjust" else "not_applicable"
            ),
        }
        decision = build_idle_behavior_decision(
            candidates,
            review={
                "method": "human", "status": "completed",
                "revision": revision,
            },
            decisions=[row],
        )
        published = IdleBehaviorReviewStore(self.fixture.state).publish(
            decision, candidates, base_revision=revision - 1,
            previous_decision_sha256=previous,
        )
        return decision, published

    def test_no_head_is_review_required_and_read_only(self):
        before = tree_snapshot(self.fixture.state)
        head = read_idle_behavior_review_head(
            self.fixture.state, self.evidence.candidates.document,
        )
        self.assertEqual(0, head.current_revision)
        self.assertIsNone(head.decision)
        with self._patch_inventory():
            inventory = self.service.list_packages(
                current_project_chains=self._current_chains(),
            )
        with self._patch_detail():
            detail = self.service.prepare(self.address.package_id)
        self.assertEqual("p10_1_review_required", inventory["packages"][0]["status"])
        self.assertEqual("p10_1_review_required", detail["status"])
        self.assertIsNone(detail["technical"]["report"])
        self.assertEqual(before, tree_snapshot(self.fixture.state))

    def test_terminal_head_is_not_applicable(self):
        decision, _published = self._publish("unobservable")
        head = read_idle_behavior_review_head(
            self.fixture.state, self.evidence.candidates.document,
        )
        self.assertEqual(decision.sha256, head.decision_sha256)
        self.assertEqual(decision.document, head.decision.document)
        with self._patch_inventory():
            inventory = self.service.list_packages(
                current_project_chains=self._current_chains(),
            )
        with self._patch_detail():
            detail = self.service.prepare(self.address.package_id)
        self.assertEqual(0, inventory["ready_count"])
        self.assertEqual(1, inventory["not_applicable_count"])
        self.assertIsNone(inventory["recommended_package_id"])
        self.assertEqual("not_applicable", detail["status"])
        self.assertIsNone(detail["report_sha256"])

    def test_ready_is_recommended_deterministic_and_matches_core_sha(self):
        self._publish()
        before = tree_snapshot(self.fixture.state)
        with self._patch_inventory():
            inventory = self.service.list_packages(
                current_project_chains=self._current_chains(),
            )
        with self._patch_detail(), patch(
            "autospine_workbench.body_sway_probe_application."
            "compile_body_sway_canvas_adjustment_candidates",
            wraps=compile_body_sway_canvas_adjustment_candidates,
        ) as compiler:
            first = self.service.prepare(self.address.package_id)
            second = self.service.prepare(self.address.package_id)
        head = read_idle_behavior_review_head(
            self.fixture.state, self.evidence.candidates.document,
        )
        inputs = require_body_sway_probe_inputs(
            self.evidence.manifest, self.evidence.candidates.document,
            head.decision.document, self.evidence.mesh_bundle,
            self.evidence.retarget_bundle, self.evidence.reviewed_contract,
        )
        direct = compile_body_sway_probe_report(inputs)
        self.assertEqual(self.address.package_id, inventory["recommended_package_id"])
        self.assertEqual("probe_ready", inventory["packages"][0]["status"])
        self.assertEqual(first, second)
        self.assertEqual(1, compiler.call_count)
        self.assertEqual(2, first["format_version"])
        self.assertEqual(direct.sha256, first["report_sha256"])
        self.assertEqual(direct.document, first["technical"]["report"])
        adjustment = first["canvas_adjustment"]
        self.assertIsNotNone(adjustment)
        adjustment_document = adjustment["document"]
        self.assertEqual(
            direct.sha256,
            adjustment_document["source"][
                "body_sway_probe_report_sha256"
            ],
        )
        self.assertEqual(
            first["candidate_sha256"],
            adjustment_document["source"]["current_p10_1_head"][
                "candidate_sha256"
            ],
        )
        self.assertEqual(
            first["history"]["head_decision_sha256"],
            adjustment_document["source"]["current_p10_1_head"][
                "decision_sha256"
            ],
        )
        self.assertIn(first["status"], {"manual_visual_required", "structural_rejected"})
        self.assertEqual("none", first["preview"]["authority"])
        self.assertEqual(
            direct.document["timing"], first["preview"]["timing"],
        )
        self.assertLessEqual(first["preview"]["witness_count"], 9)
        representative_ticks = {
            row["tick"] for row in direct.document["sample_stream"][
                "representative_samples"
            ]
        }
        witnesses = first["preview"]["witnesses"]
        self.assertEqual(
            ["pelvis-spine", "spine-chest", "chest-neck", "neck-head"],
            [row["bone_id"] for row in witnesses[0]["target_bones"]],
        )
        self.assertTrue(
            all(row["tick"] in representative_ticks for row in witnesses)
        )
        self.assertTrue(all(
            len(row["canvas_failure_markers"]) <= 16
            for row in witnesses
        ))
        encoded = json.dumps(first, ensure_ascii=False)
        self.assertNotIn(str(self.fixture.state), encoded)
        self.assertNotIn("input_paths", encoded)
        self.assertEqual(before, tree_snapshot(self.fixture.state))

    def test_multiple_ready_packages_have_no_recommendation(self):
        self._publish()
        other = IdleBehaviorReviewAddress(
            "b" * 64, self.address.project_id, self.address.motion_id,
            self.address.clip_id, self.address.motion_instance_v2_sha256,
            self.address.reviewed_motion_bundle_sha256,
            self.address.p9_decision_sha256,
        )
        other_evidence = replace(self.evidence, address=other)
        with self._patch_inventory(
            (self.address, other), (self.evidence, other_evidence),
        ):
            inventory = self.service.list_packages(
                current_project_chains=self._current_chains(),
            )
        self.assertEqual(2, inventory["ready_count"])
        self.assertIsNone(inventory["recommended_package_id"])

    def test_missing_current_chain_inventory_never_recommends(self):
        self._publish()
        with self._patch_inventory():
            inventory = self.service.list_packages()
        self.assertEqual(1, inventory["ready_count"])
        self.assertIsNone(inventory["recommended_package_id"])

    def test_cache_hit_keeps_both_exact_replay_and_head_checks(self):
        self._publish()
        target = "autospine_workbench.body_sway_probe_application."
        with patch(
            target + "get_idle_behavior_review_address",
            return_value=self.address,
        ), patch(
            target + "replay_idle_behavior_review_package",
            return_value=self.evidence,
        ) as replay, patch(
            target + "read_idle_behavior_review_head",
            wraps=read_idle_behavior_review_head,
        ) as read_head, patch(
            target + "compile_body_sway_canvas_adjustment_candidates",
            wraps=compile_body_sway_canvas_adjustment_candidates,
        ) as compiler:
            self.service.prepare(self.address.package_id)
            self.service.prepare(self.address.package_id)
        self.assertEqual(4, replay.call_count)
        self.assertEqual(4, read_head.call_count)
        self.assertEqual(1, compiler.call_count)

    def test_warm_cache_does_not_mask_concurrent_head_change(self):
        _decision, published = self._publish()
        with self._patch_detail():
            self.service.prepare(self.address.package_id)
        real_read = read_idle_behavior_review_head
        reads = 0

        def read_then_advance(state_root, candidates):
            nonlocal reads
            head = real_read(state_root, candidates)
            reads += 1
            if reads == 1:
                self._publish(
                    revision=2, previous=published.sha256, cycles=3,
                )
            return head

        target = "autospine_workbench.body_sway_probe_application."
        with self._patch_detail(), patch(
            target + "read_idle_behavior_review_head",
            side_effect=read_then_advance,
        ), patch(
            target + "compile_body_sway_canvas_adjustment_candidates",
            wraps=compile_body_sway_canvas_adjustment_candidates,
        ) as compiler, self.assertRaises(BodySwayProbeApplicationHeadChanged):
            self.service.prepare(self.address.package_id)
        self.assertEqual(2, reads)
        self.assertEqual(0, compiler.call_count)

    def test_skipped_package_suppresses_automatic_recommendation(self):
        self._publish()
        with patch(
            "autospine_workbench.body_sway_probe_packages."
            "list_current_idle_behavior_review_addresses",
            return_value=((self.address,), 1),
        ), patch(
            "autospine_workbench.body_sway_probe_packages."
            "replay_idle_behavior_review_package",
            return_value=self.evidence,
        ):
            inventory = self.service.list_packages(
                current_project_chains=self._current_chains(),
            )
        self.assertEqual(1, inventory["ready_count"])
        self.assertEqual(1, inventory["skipped_count"])
        self.assertIsNone(inventory["recommended_package_id"])

    def test_stale_chain_is_not_discovered_but_exact_id_remains_viewable(self):
        self._publish()
        current = {
            self.address.project_id: CurrentProjectChain(
                self.address.project_id, "e" * 64, "f" * 64,
            ),
        }
        with patch(
            "autospine_workbench.body_sway_probe_packages."
            "list_current_idle_behavior_review_addresses",
            return_value=((), 0),
        ) as listed:
            inventory = self.service.list_packages(
                current_project_chains=current,
            )
        self.assertEqual((0, []), (
            inventory["count"], inventory["packages"],
        ))
        self.assertIsNone(inventory["recommended_package_id"])
        listed.assert_called_once_with(
            self.fixture.state,
            project_ids=None,
            current_project_chains=current,
        )
        with self._patch_detail():
            detail = self.service.prepare(self.address.package_id)
        self.assertEqual(self.address.package_id, detail["package"]["package_id"])

    def test_head_change_during_compile_discards_report(self):
        first, published = self._publish()
        real_compile = compile_body_sway_canvas_adjustment_candidates

        def compile_then_advance(inputs, current_head):
            adjustment = real_compile(inputs, current_head)
            self._publish(
                revision=2, previous=published.sha256, cycles=3,
            )
            return adjustment

        with self._patch_detail(), patch(
            "autospine_workbench.body_sway_probe_application."
            "compile_body_sway_canvas_adjustment_candidates",
            side_effect=compile_then_advance,
        ), self.assertRaises(BodySwayProbeApplicationHeadChanged):
            self.service.prepare(self.address.package_id)
        self.assertEqual(1, first.document["review"]["revision"])

    def test_no_head_becoming_adjust_is_rejected(self):
        real_read = read_idle_behavior_review_head
        reads = 0

        def read_then_publish(state_root, candidates):
            nonlocal reads
            head = real_read(state_root, candidates)
            reads += 1
            if reads == 1:
                self._publish()
            return head

        with self._patch_detail(), patch(
            "autospine_workbench.body_sway_probe_application."
            "read_idle_behavior_review_head",
            side_effect=read_then_publish,
        ), self.assertRaises(BodySwayProbeApplicationHeadChanged):
            self.service.prepare(self.address.package_id)
        self.assertEqual(2, reads)

    def test_unobservable_head_becoming_adjust_is_rejected(self):
        _decision, published = self._publish("unobservable")
        real_read = read_idle_behavior_review_head
        reads = 0

        def read_then_publish(state_root, candidates):
            nonlocal reads
            head = real_read(state_root, candidates)
            reads += 1
            if reads == 1:
                self._publish(
                    revision=2, previous=published.sha256, cycles=3,
                )
            return head

        with self._patch_detail(), patch(
            "autospine_workbench.body_sway_probe_application."
            "read_idle_behavior_review_head",
            side_effect=read_then_publish,
        ), self.assertRaises(BodySwayProbeApplicationHeadChanged):
            self.service.prepare(self.address.package_id)
        self.assertEqual(2, reads)

    def test_reviewed_contract_is_rebuilt_instead_of_retained(self):
        self.assertNotIn(
            "reviewed_contract",
            IdleBehaviorReviewEvidence.__dataclass_fields__,
        )
        real_replay = (
            idle_behavior_review_replay.
            replay_verified_reviewed_motion_bundle
        )
        with patch.object(
            idle_behavior_review_replay,
            "replay_verified_reviewed_motion_bundle",
            wraps=real_replay,
        ) as replay:
            first = self.evidence.reviewed_contract
            second = self.evidence.reviewed_contract
        self.assertEqual(2, replay.call_count)
        self.assertEqual(first.identities, second.identities)
        self.assertIsNot(first, second)

    def test_tampered_head_fails_closed(self):
        _decision, published = self._publish()
        published.path.write_bytes(b"{}")
        with self.assertRaises(IdleBehaviorReviewHeadError):
            read_idle_behavior_review_head(
                self.fixture.state, self.evidence.candidates.document,
            )
        with self._patch_detail(), self.assertRaises(
            BodySwayProbeApplicationUnavailable,
        ):
            self.service.prepare(self.address.package_id)


if __name__ == "__main__":
    unittest.main()
