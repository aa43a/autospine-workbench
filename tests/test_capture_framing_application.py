"""Exact replay and CAS tests for P10.2b framing publication."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.capture_framing_application import (  # noqa: E402
    CaptureFramingApplication,
    CaptureFramingApplicationHeadChanged,
)
from autospine_workbench.capture_framing_candidate import (  # noqa: E402
    CaptureFramingCandidate,
)
from autospine_workbench.capture_framing_history import (  # noqa: E402
    CaptureFramingHistorySnapshot,
    CaptureFramingRevisionConflict,
    PublishedCaptureFramingDecision,
)
from autospine_workbench.capture_framing_profile import (  # noqa: E402
    INTENT,
    SUBMISSION_FORMAT,
)
from autospine_workbench.current_project_chain import (  # noqa: E402
    CurrentProjectChain,
)
from tests.motion_policy_preflight_helpers import tree_snapshot  # noqa: E402
from tests.test_project_store import StoreFixture  # noqa: E402


PACKAGE = "a" * 64
P10_CANDIDATE = "c" * 64
P10_DECISION = "d" * 64
DECISION = "e" * 64


class CaptureFramingApplicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.fixture = StoreFixture(Path(self.temporary.name))
        self.store = self.fixture.store()
        project = self.store.get_project("fixture-project")
        self.project_id = project["id"]
        self.chain = CurrentProjectChain(
            self.project_id, project["resolved"]["sha256"], "f" * 64,
        )
        self.address = SimpleNamespace(project_id=self.project_id)
        self.candidate = self._candidate()
        self.detail = {
            "package": {
                "package_id": PACKAGE,
                "project_id": self.project_id,
                "clip_id": "wave-left-v1",
            },
            "candidate_sha256": P10_CANDIDATE,
            "history": {
                "current_revision": 1,
                "head_decision_sha256": P10_DECISION,
                "action": "adjust",
                "probe_status": "pending_probe",
            },
            "capture_framing": {
                "candidate_sha256": self.candidate.sha256,
                "document": self.candidate.document,
                "history": {
                    "current_revision": 0,
                    "head_decision_sha256": None,
                    "action": None,
                    "status": None,
                },
            },
        }
        self.request = {
            "format": SUBMISSION_FORMAT,
            "format_version": 1,
            "intent": INTENT,
            "explicit_confirmation": True,
            "package_id": PACKAGE,
            "candidate_sha256": self.candidate.sha256,
            "p10_1_head": {
                "candidate_sha256": P10_CANDIDATE,
                "decision_sha256": P10_DECISION,
                "revision": 1,
            },
            "base_revision": 0,
            "previous_decision_sha256": None,
            "action": "accept",
            "reason_code": "human-approved-automatic-capture-framing-v1",
            "world_viewport": None,
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _candidate(self):
        document = {
            "project_id": self.project_id,
            "clip_id": "wave-left-v1",
            "source": {
                "package_id": PACKAGE,
                "current_p10_1_head": {
                    "candidate_sha256": P10_CANDIDATE,
                    "decision_sha256": P10_DECISION,
                    "revision": 1,
                },
                "p3": {
                    "resolved_project_sha256": self.chain.resolved_project_sha256,
                    "layer_manifest_sha256": self.chain.layer_manifest_sha256,
                },
            },
        }
        return CaptureFramingCandidate(json.dumps(
            document, sort_keys=True, separators=(",", ":"),
        ))

    def _patches(self, *, details=None, snapshot=None):
        details = details or [self.detail, self.detail]
        snapshot = snapshot or CaptureFramingHistorySnapshot(
            0, None, None, None,
        )
        fake_decision = SimpleNamespace(document={
            "decision": {"action": "accept"},
            "status": "ready_for_temporary_preview_v2",
        })
        prefix = "autospine_workbench.capture_framing_application."
        return (
            patch(prefix + "rebuild_current_project_chains",
                  return_value={self.project_id: self.chain}),
            patch(prefix + "require_current_idle_behavior_review_address",
                  return_value=self.address),
            patch(prefix + "BodySwayProbeApplication.prepare",
                  side_effect=details),
            patch(prefix + "capture_framing_candidate_sha256",
                  return_value=self.candidate.sha256),
            patch(prefix + "snapshot_capture_framing_history",
                  return_value=snapshot),
            patch(prefix + "load_capture_framing_head", return_value=None),
            patch(prefix + "build_capture_framing_decision",
                  return_value=fake_decision),
            patch(prefix + "publish_capture_framing_decision",
                  return_value=PublishedCaptureFramingDecision(
                      Path("ignored.json"), DECISION, 1, False,
                  )),
        )

    def _submit(self, *, details=None, snapshot=None):
        patches = self._patches(details=details, snapshot=snapshot)
        with patches[0] as chains, patches[1] as current, \
                patches[2] as prepare, patches[3], patches[4], \
                patches[5], patches[6] as build, patches[7] as publish:
            result = CaptureFramingApplication(self.store).submit(
                PACKAGE, self.request,
            )
        return result, chains, current, prepare, build, publish

    def test_success_replays_inside_lock_and_returns_path_free_receipt(self):
        result, chains, current, prepare, build, publish = self._submit()
        self.assertEqual("recorded", result["status"])
        self.assertEqual(DECISION, result["decision_sha256"])
        self.assertEqual(4, chains.call_count)
        self.assertEqual(3, current.call_count)
        self.assertEqual(2, prepare.call_count)
        self.assertEqual(1, build.call_count)
        self.assertEqual(1, publish.call_count)
        self.assertNotIn("path", json.dumps(result).lower())
        self.assertNotIn(str(self.fixture.state), json.dumps(result))

    def test_last_moment_p10_head_change_is_zero_write(self):
        changed = deepcopy(self.detail)
        changed["history"]["head_decision_sha256"] = "0" * 64
        before = tree_snapshot(self.fixture.state)
        patches = self._patches(details=[self.detail, changed])
        with patches[0], patches[1], patches[2], patches[3], patches[4], \
                patches[5], patches[6], patches[7] as publish, \
                self.assertRaises(CaptureFramingApplicationHeadChanged):
            CaptureFramingApplication(self.store).submit(
                PACKAGE, self.request,
            )
        publish.assert_not_called()
        self.assertEqual(before, tree_snapshot(self.fixture.state))

    def test_stale_framing_revision_is_deterministic_and_zero_write(self):
        stale = CaptureFramingHistorySnapshot(1, "1" * 64, "accept", "ready")
        before = tree_snapshot(self.fixture.state)
        patches = self._patches(snapshot=stale)
        with patches[0], patches[1], patches[2], patches[3], patches[4], \
                patches[5], patches[6], patches[7] as publish, \
                self.assertRaises(CaptureFramingRevisionConflict) as caught:
            CaptureFramingApplication(self.store).submit(
                PACKAGE, self.request,
            )
        publish.assert_not_called()
        self.assertEqual(1, caught.exception.current_revision)
        self.assertEqual("1" * 64, caught.exception.current_head)
        self.assertEqual(before, tree_snapshot(self.fixture.state))


if __name__ == "__main__":
    unittest.main()
