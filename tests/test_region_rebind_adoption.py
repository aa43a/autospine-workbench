"""Exact-current, zero-implicit-authority region rebind adoption tests."""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.current_project_chain import (  # noqa: E402
    CurrentProjectChain,
    CurrentProjectChainChangedError,
)
from autospine_workbench.idle_behavior_review_packages import (  # noqa: E402
    IdleBehaviorReviewPackageStale,
)
from autospine_workbench.idle_behavior_review_store import (  # noqa: E402
    IdleBehaviorReviewStore,
)
import autospine_workbench.idle_behavior_review_transaction as transaction_module  # noqa: E402, E501
from autospine_workbench.project_errors import RevisionConflictError  # noqa: E402
from autospine_workbench.override_files import OverrideFileError  # noqa: E402
from autospine_workbench.region_rebind_adoption import (  # noqa: E402
    RegionRebindAdoptionApplication,
    RegionRebindAdoptionBindingChanged,
    RegionRebindAdoptionHistorical,
    RegionRebindAdoptionHeadChanged,
    RegionRebindAdoptionInvalid,
    RegionRebindAdoptionNotFound,
)
from autospine_workbench.region_rebind_candidates import (  # noqa: E402
    compile_region_rebind_candidates,
)
from autospine_workbench.region_rebind_revision_provenance import (  # noqa: E402
    normalize_region_rebind_revision_provenance,
    region_rebind_revision_provenance_sha256,
)
from tests.motion_policy_preflight_helpers import tree_snapshot  # noqa: E402
from tests.test_project_store import StoreFixture  # noqa: E402
from tests.test_region_rebind_candidates import (  # noqa: E402
    MOTION_SHA,
    motion_samples,
    rig_fixture,
)


PACKAGE_ID = "a" * 64


class RegionRebindAdoptionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.fixture = StoreFixture(Path(self.temporary.name))
        self.store = self.fixture.store()
        project = self.store.get_project("fixture-project")
        self.project_id = project["id"]
        self.layer_id = project["layers"][0]["id"]
        self.store.save_overrides(
            self.project_id,
            {
                "base_revision": 0,
                "joint_overrides": {},
                "joint_decisions": {},
                "split_decisions": {},
                "layer_overrides": {
                    self.layer_id: {"candidate_bone": "forearm.left"},
                },
                "notes": "operator-authored note",
            },
        )
        project = self.store.get_project(self.project_id)
        self.chain = CurrentProjectChain(
            self.project_id, project["resolved"]["sha256"], "b" * 64,
        )
        rig = rig_fixture()
        rig["slots"][0].update({
            "id": self.layer_id, "setup_attachment": self.layer_id,
        })
        rig["attachments"][0].update({
            "id": self.layer_id, "slot": self.layer_id,
        })
        rig["skins"] = {"default": {self.layer_id: [self.layer_id]}}
        self.candidate = compile_region_rebind_candidates(
            rig, motion_samples(), project_id=self.project_id,
            motion_sha256=MOTION_SHA, attachment_id=self.layer_id,
        )
        self.detail = {
            "package": {"project_id": self.project_id},
            "candidate_sha256": "e" * 64,
            "rebind_candidates": [{
                "candidate_sha256": self.candidate.sha256,
                "document": self.candidate.document,
            }],
            "technical": {"report": {
                "source": {
                    "idle_behavior_candidates_sha256": "e" * 64,
                    "p3": {
                        "rig_sha256": self.candidate.document["source"]["rig_sha256"],
                        "resolved_project_sha256": self.chain.resolved_project_sha256,
                        "layer_manifest_sha256": self.chain.layer_manifest_sha256,
                    },
                    "p9": {"motion_instance_v2_sha256": MOTION_SHA},
                },
                "schedule": {"sample_count": len(motion_samples())},
            }},
            "history": {
                "current_revision": 1,
                "head_decision_sha256": "c" * 64,
                "action": "adjust",
                "probe_status": "pending_probe",
            },
        }
        self.request = {
            "project_id": self.project_id,
            "layer_id": self.layer_id,
            "from_bone_id": "forearm.left",
            "to_bone_id": "upper-arm.left",
            "candidate_sha256": self.candidate.sha256,
            "base_revision": 1,
            "overrides": project["overrides"],
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @contextmanager
    def _exact_evidence(self, *, current_error=None):
        current = current_error or SimpleNamespace(project_id=self.project_id)
        kwargs = {"return_value": current} if current_error is None \
            else {"side_effect": current_error}
        with patch(
            "autospine_workbench.region_rebind_adoption."
            "rebuild_current_project_chains",
            return_value={self.project_id: self.chain},
        ), patch(
            "autospine_workbench.region_rebind_adoption."
            "require_current_idle_behavior_review_address",
            **kwargs,
        ), patch(
            "autospine_workbench.region_rebind_adoption."
            "BodySwayProbeApplication.prepare",
            return_value=self.detail,
        ):
            yield

    def _adopt(self, request=None, candidate_sha256=None):
        candidate_sha256 = candidate_sha256 or self.candidate.sha256
        with self._exact_evidence():
            return RegionRebindAdoptionApplication(self.store).adopt(
                PACKAGE_ID, candidate_sha256, request or self.request,
            )

    def test_success_preserves_notes_and_receipt_reloads_with_revision(self):
        receipt = self._adopt()
        self.assertEqual("adopted", receipt["status"])
        self.assertEqual(2, receipt["revision"])
        self.assertEqual("operator-authored note", receipt["overrides"]["notes"])
        self.assertNotIn("autospine-region-rebind", receipt["overrides"]["notes"])
        self.assertEqual(
            "upper-arm.left",
            receipt["overrides"]["layer_overrides"][self.layer_id][
                "candidate_bone"
            ],
        )
        reloaded = self.fixture.store().get_project(self.project_id)["overrides"]
        provenance = reloaded["revision_provenance"]
        self.assertEqual(receipt["provenance"], provenance)
        self.assertEqual(2, provenance["revision"])
        self.assertEqual(self.project_id, provenance["project_id"])
        self.assertEqual(
            receipt["provenance_sha256"],
            region_rebind_revision_provenance_sha256(provenance),
        )
        self.assertEqual(
            provenance,
            normalize_region_rebind_revision_provenance(
                provenance, project_id=self.project_id, revision=2,
            ),
        )
        history = (
            self.fixture.state / "overrides" / self.project_id
            / "history" / "r000002.json"
        )
        raw = json.loads(history.read_text("utf-8"))
        self.assertEqual(provenance, raw["revision_provenance"])

    def test_latest_repair_failure_still_returns_adopted_revision(self):
        files = self.store._override_store._files
        with patch.object(
            files,
            "write_latest",
            side_effect=OverrideFileError("injected persistent latest failure"),
        ) as write_latest:
            receipt = self._adopt()

        self.assertEqual(2, write_latest.call_count)
        self.assertEqual("adopted", receipt["status"])
        self.assertEqual(2, receipt["revision"])
        project_dir = self.fixture.state / "overrides" / self.project_id
        latest = json.loads((project_dir / "latest.json").read_text("utf-8"))
        self.assertEqual(1, latest["revision"])
        self.assertTrue((project_dir / "history" / "r000002.json").is_file())
        reloaded = self.fixture.store().get_project(self.project_id)["overrides"]
        self.assertEqual(2, reloaded["revision"])
        self.assertEqual(receipt["provenance"], reloaded["revision_provenance"])

    def test_historical_package_is_read_only_and_zero_write(self):
        before = tree_snapshot(self.fixture.state)
        historical = IdleBehaviorReviewPackageStale("historical")
        with self._exact_evidence(current_error=historical), self.assertRaises(
            RegionRebindAdoptionHistorical
        ):
            RegionRebindAdoptionApplication(self.store).adopt(
                PACKAGE_ID, self.candidate.sha256, self.request,
            )
        self.assertEqual(before, tree_snapshot(self.fixture.state))

    def test_tampered_from_to_and_candidate_are_rejected_without_writes(self):
        cases = []
        wrong_from = deepcopy(self.request)
        wrong_from["from_bone_id"] = "spine-chest"
        cases.append((wrong_from, self.candidate.sha256,
                      RegionRebindAdoptionBindingChanged))
        wrong_to = deepcopy(self.request)
        wrong_to["to_bone_id"] = "spine-chest"
        cases.append((wrong_to, self.candidate.sha256,
                      RegionRebindAdoptionInvalid))
        wrong_candidate = deepcopy(self.request)
        wrong_candidate["candidate_sha256"] = "0" * 64
        cases.append((wrong_candidate, "0" * 64, RegionRebindAdoptionNotFound))
        before = tree_snapshot(self.fixture.state)
        for request, candidate_sha, error in cases:
            with self.subTest(error=error.__name__), self.assertRaises(error):
                self._adopt(request, candidate_sha)
            self.assertEqual(before, tree_snapshot(self.fixture.state))

    def test_revision_conflict_precedes_evidence_and_is_zero_write(self):
        request = deepcopy(self.request)
        request["base_revision"] = 0
        request["overrides"]["revision"] = 0
        before = tree_snapshot(self.fixture.state)
        with self.assertRaises(RevisionConflictError):
            self._adopt(request)
        self.assertEqual(before, tree_snapshot(self.fixture.state))

    def test_p10_head_change_after_prepare_is_conflict_and_zero_write(self):
        changed = deepcopy(self.detail)
        changed["history"]["head_decision_sha256"] = "d" * 64
        before = tree_snapshot(self.fixture.state)
        target = "autospine_workbench.region_rebind_adoption."
        with patch(
            target + "rebuild_current_project_chains",
            return_value={self.project_id: self.chain},
        ), patch(
            target + "require_current_idle_behavior_review_address",
            return_value=SimpleNamespace(project_id=self.project_id),
        ), patch(
            target + "BodySwayProbeApplication.prepare",
            side_effect=[self.detail, changed],
        ) as prepared, self.assertRaises(RegionRebindAdoptionHeadChanged):
            RegionRebindAdoptionApplication(self.store).adopt(
                PACKAGE_ID, self.candidate.sha256, self.request,
            )
        self.assertEqual(2, prepared.call_count)
        self.assertEqual(before, tree_snapshot(self.fixture.state))

    def test_final_current_chain_drift_is_conflict_and_zero_write(self):
        changed = CurrentProjectChain(
            self.project_id, "f" * 64, self.chain.layer_manifest_sha256,
            self.chain.input_identity_sha256,
        )
        snapshots = [
            {self.project_id: self.chain},
            {self.project_id: self.chain},
            {self.project_id: changed},
        ]
        before = tree_snapshot(self.fixture.state)
        target = "autospine_workbench.region_rebind_adoption."
        with patch(
            target + "rebuild_current_project_chains",
            side_effect=snapshots,
        ), patch(
            target + "require_current_idle_behavior_review_address",
            return_value=SimpleNamespace(project_id=self.project_id),
        ), patch(
            target + "BodySwayProbeApplication.prepare",
            return_value=self.detail,
        ), self.assertRaises(CurrentProjectChainChangedError):
            RegionRebindAdoptionApplication(self.store).adopt(
                PACKAGE_ID, self.candidate.sha256, self.request,
            )
        self.assertEqual(before, tree_snapshot(self.fixture.state))

    def test_adoption_holds_shared_p10_lock_through_override_write(self):
        """Cover both lock orderings with the preceding zero-write test."""

        save_entered = threading.Event()
        release_save = threading.Event()
        writer_started = threading.Event()
        writer_published = threading.Event()
        adoption_results = []
        worker_errors = []
        original_save = self.store.save_overrides

        def guarded_save(*args, **kwargs):
            save_entered.set()
            if not release_save.wait(5):
                raise AssertionError("test did not release override save")
            return original_save(*args, **kwargs)

        def adopt_worker():
            try:
                adoption_results.append(
                    RegionRebindAdoptionApplication(self.store).adopt(
                        PACKAGE_ID, self.candidate.sha256, self.request,
                    )
                )
            except BaseException as exc:  # pragma: no cover - diagnostic
                worker_errors.append(exc)

        def publish_worker():
            writer_started.set()
            try:
                IdleBehaviorReviewStore(self.store.state_root).publish(
                    object(), {}, base_revision=1,
                    previous_decision_sha256="c" * 64,
                )
            except BaseException as exc:  # pragma: no cover - diagnostic
                worker_errors.append(exc)

        store_module = "autospine_workbench.idle_behavior_review_store."
        with self._exact_evidence(), patch.object(
            self.store, "save_overrides", side_effect=guarded_save,
        ), patch(
            store_module + "idle_behavior_candidates_sha256",
            return_value="e" * 64,
        ), patch(
            store_module + "publish_idle_behavior_review_decision",
            side_effect=lambda *_args, **_kwargs: writer_published.set(),
        ):
            adoption = threading.Thread(target=adopt_worker)
            adoption.start()
            self.assertTrue(save_entered.wait(5))
            matching = [
                lock for (_root, digest), lock in transaction_module._LOCKS.items()
                if digest == "e" * 64
            ]
            self.assertEqual(1, len(matching))
            self.assertFalse(matching[0].acquire(blocking=False))

            writer = threading.Thread(target=publish_worker)
            writer.start()
            self.assertTrue(writer_started.wait(5))
            self.assertFalse(writer_published.wait(0.05))
            release_save.set()
            adoption.join(5)
            writer.join(5)

        self.assertFalse(adoption.is_alive())
        self.assertFalse(writer.is_alive())
        self.assertFalse(worker_errors)
        self.assertEqual("adopted", adoption_results[0]["status"])
        self.assertTrue(writer_published.is_set())


if __name__ == "__main__":
    unittest.main()
