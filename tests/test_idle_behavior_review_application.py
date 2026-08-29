"""Exact-chain and assisted P10.1 application-service tests."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from autospine_workbench.idle_behavior_review_address import (
    IdleBehaviorReviewAddress,
)
from autospine_workbench.idle_behavior_review_application import (
    IdleBehaviorReviewApplication,
)
from autospine_workbench.idle_behavior_decision import (
    build_idle_behavior_decision,
)
from autospine_workbench.idle_behavior_review_history import (
    IdleBehaviorReviewRevisionConflict,
)
from autospine_workbench.idle_behavior_review_replay import (
    replay_idle_behavior_review_package,
)
from tests.p10_candidate_helpers import P10PersistedFixture
from tests.test_idle_behavior_review_submission import valid_submission


class IdleBehaviorReviewApplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = P10PersistedFixture(Path(cls.temporary.name))
        reviewed = cls.fixture.reviewed
        cls.address = IdleBehaviorReviewAddress(
            "a" * 64,
            cls.fixture.mesh.project_id,
            "motion-a",
            reviewed.clip_id,
            reviewed.motion_instance_v2_sha256,
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
        self._reset_history()
        self.service = IdleBehaviorReviewApplication(self.fixture.state)

    def _reset_history(self) -> None:
        history = (
            self.fixture.state / "builds" / self.address.project_id
            / "idle-behavior-decisions"
        )
        shutil.rmtree(history, ignore_errors=True)

    def _patch_exact(self):
        address = patch(
            "autospine_workbench.idle_behavior_review_application."
            "get_idle_behavior_review_address",
            return_value=self.address,
        )
        replay = patch(
            "autospine_workbench.idle_behavior_review_application."
            "replay_idle_behavior_review_package",
            return_value=self.evidence,
        )
        return address, replay

    def prepare(self):
        address, replay = self._patch_exact()
        with address, replay:
            return self.service.prepare(self.address.package_id)

    def submit(self, value):
        address, replay = self._patch_exact()
        with address, replay:
            return self.service.submit(self.address.package_id, value)

    def request(self, entry, **changes):
        value = valid_submission(
            package_id=self.address.package_id,
            candidate_sha256=entry["candidate_sha256"],
        )
        value.update(changes)
        return value

    def test_exact_replay_is_deterministic_and_bound_to_adopted_p9(self):
        second = replay_idle_behavior_review_package(
            self.fixture.state, self.address,
        )
        self.assertEqual(self.evidence.candidates.sha256, second.candidates.sha256)
        self.assertEqual(
            self.address.p9_decision_sha256,
            second.candidates.document["source"]["p9"][
                "motion_policy_decision_sha256"
            ],
        )

    def test_prepare_is_path_free_and_exposes_four_bone_fk_preview(self):
        entry = self.prepare()
        self.assertEqual("review_required", entry["status"])
        self.assertEqual(
            ["pelvis-spine", "spine-chest", "chest-neck", "neck-head"],
            [row["bone_id"] for row in entry["preview"]["bones"]],
        )
        self.assertEqual("none", entry["suggestion"]["authority"])
        self.assertTrue(
            all(claim is False
                for claim in entry["suggestion"]["claims"].values())
        )
        encoded = json.dumps(entry)
        self.assertNotIn(str(self.fixture.state), encoded)
        self.assertNotIn("input_paths", encoded)

    def test_confirmed_adjustment_publishes_and_current_head_retry_reuses(self):
        entry = self.prepare()
        request = self.request(entry)
        first = self.submit(request)
        second = self.submit(request)
        self.assertFalse(first["reused"])
        self.assertTrue(second["reused"])
        self.assertEqual(first["decision_sha256"], second["decision_sha256"])
        self.assertEqual("pending_probe", first["probe_status"])
        self.assertEqual(1, first["revision"])
        reviewed = self.prepare()
        self.assertEqual("reviewed", reviewed["status"])
        self.assertEqual(1, reviewed["history"]["current_revision"])
        self.assertEqual(
            request["parameters"],
            reviewed["history"]["items"][0]["parameters"],
        )

    def test_reject_and_unobservable_are_terminal_without_probe_payload(self):
        for action, reason in (
            ("reject", "human-declined-body-sway-v1"),
            ("unobservable", "human-marked-unobservable-v1"),
        ):
            with self.subTest(action=action):
                self._reset_history()
                entry = self.prepare()
                receipt = self.submit(self.request(
                    entry, action=action, reason_code=reason, parameters=None,
                ))
                self.assertEqual(action, receipt["action"])
                self.assertEqual("not_applicable", receipt["probe_status"])

    def test_stale_different_revision_is_a_conflict(self):
        entry = self.prepare()
        first = self.request(entry)
        self.submit(first)
        changed = self.request(entry)
        changed["parameters"]["cycles"] = 3
        with self.assertRaises(IdleBehaviorReviewRevisionConflict):
            self.submit(changed)

    def test_receipt_stays_bound_to_its_linearized_revision(self):
        entry = self.prepare()
        original_publish = self.service._store.publish

        def publish_then_advance(decision, candidate, **baseline):
            first = original_publish(decision, candidate, **baseline)
            row = dict(decision.document["decisions"][0])
            row.update({
                "action": "reject",
                "reason_code": "human-declined-body-sway-v1",
                "payload": None,
                "probe_status": "not_applicable",
            })
            second = build_idle_behavior_decision(
                candidate,
                review={
                    "method": "human", "status": "completed",
                    "revision": 2,
                },
                decisions=[row],
            )
            original_publish(
                second, candidate, base_revision=1,
                previous_decision_sha256=first.sha256,
            )
            return first

        with patch.object(
            self.service._store, "publish", side_effect=publish_then_advance,
        ):
            receipt = self.submit(self.request(entry))
        self.assertEqual(1, receipt["revision"])
        self.assertEqual(1, receipt["history"]["current_revision"])
        self.assertEqual(
            receipt["decision_sha256"],
            receipt["history"]["head_decision_sha256"],
        )
        self.assertEqual(2, self.prepare()["history"]["current_revision"])


if __name__ == "__main__":
    unittest.main()
