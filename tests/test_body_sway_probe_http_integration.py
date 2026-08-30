"""Persisted-chain HTTP integration for the public P10.2 detail contract."""

from __future__ import annotations

import http.client
import json
from pathlib import Path
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

from autospine_workbench.idle_behavior_decision import (  # noqa: E402
    build_idle_behavior_decision,
)
from autospine_workbench.idle_behavior_review_address import (  # noqa: E402
    IdleBehaviorReviewAddress,
)
from autospine_workbench.idle_behavior_review_replay import (  # noqa: E402
    replay_idle_behavior_review_package,
)
from autospine_workbench.idle_behavior_review_store import (  # noqa: E402
    IdleBehaviorReviewStore,
)
from autospine_workbench.body_sway_probe_validation import (  # noqa: E402
    body_sway_probe_report_sha256,
)
from autospine_workbench.server import create_server  # noqa: E402
from tests.motion_policy_preflight_helpers import tree_snapshot  # noqa: E402
from tests.p10_candidate_helpers import P10PersistedFixture, PROJECT  # noqa: E402
from tests.test_idle_behavior_review_submission import (  # noqa: E402
    valid_submission,
)


class BodySwayProbeHttpIntegrationTests(unittest.TestCase):
    """Exercise route, application, replay, compiler, and public projection."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        root = Path(cls.temporary.name)
        chain_root = root / "chain"
        chain_root.mkdir()
        cls.fixture = P10PersistedFixture(chain_root)
        reviewed = cls.fixture.reviewed
        cls.address = IdleBehaviorReviewAddress(
            "a" * 64, PROJECT, "motion-a", reviewed.clip_id,
            reviewed.motion_instance_v2_sha256, reviewed.bundle_sha256,
            reviewed.motion_policy_decision_sha256,
        )
        evidence = replay_idle_behavior_review_package(
            cls.fixture.state, cls.address,
        )
        feature = next(
            row for row in evidence.candidates.document["features"]
            if row["feature_id"] == "body_sway"
        )
        decision = build_idle_behavior_decision(
            evidence.candidates.document,
            review={"method": "human", "status": "completed", "revision": 1},
            decisions=[{
                "candidate_id": feature["candidate_id"],
                "feature_id": "body_sway",
                "action": "adjust",
                "reason_code": "human-http-integration",
                "payload": valid_submission()["parameters"],
                "probe_status": "pending_probe",
            }],
        )
        IdleBehaviorReviewStore(cls.fixture.state).publish(
            decision, evidence.candidates.document,
            base_revision=0, previous_decision_sha256=None,
        )
        workspace = root / "empty-workspace"
        workspace.mkdir()
        cls.server = create_server(
            "127.0.0.1", 0, workspace, state_root=cls.fixture.state,
        )
        cls.thread = threading.Thread(
            target=cls.server.serve_forever, daemon=True,
        )
        cls.thread.start()
        cls.host, cls.port = cls.server.server_address[:2]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls.temporary.cleanup()

    def test_persisted_ready_detail_uses_current_public_projection(self) -> None:
        before = tree_snapshot(self.fixture.state)
        with patch(
            "autospine_workbench.body_sway_probe_routes._project_ids",
            return_value=(PROJECT,),
        ), patch(
            "autospine_workbench.body_sway_probe_application."
            "get_idle_behavior_review_address",
            return_value=self.address,
        ):
            connection = http.client.HTTPConnection(
                self.host, self.port, timeout=30,
            )
            connection.request(
                "GET",
                "/api/idle-behavior/structural-probes/"
                f"{self.address.package_id}",
            )
            response = connection.getresponse()
            raw = response.read()
            connection.close()
        payload = json.loads(raw)
        self.assertEqual(200, response.status)
        self.assertEqual(
            "autospine-body-sway-probe-entry", payload["format"],
        )
        self.assertEqual(self.address.package_id, payload["package"]["package_id"])
        self.assertEqual(1, payload["history"]["current_revision"])
        self.assertEqual("adjust", payload["history"]["action"])
        self.assertEqual("none", payload["preview"]["authority"])
        self.assertEqual(payload["status"], payload["result"]["status"])
        self.assertEqual(
            payload["report_sha256"],
            body_sway_probe_report_sha256(payload["technical"]["report"]),
        )
        self.assertEqual(7, len(payload["result"]["checks"]))
        self.assertNotIn(str(self.fixture.state), raw.decode("utf-8"))
        self.assertEqual(before, tree_snapshot(self.fixture.state))


if __name__ == "__main__":
    unittest.main()
