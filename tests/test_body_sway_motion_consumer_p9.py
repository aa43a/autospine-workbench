"""Focused cross-document replay tests for the P10.6a P9 boundary."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.body_sway_motion_consumer_p9 import (  # noqa: E402
    BodySwayMotionConsumerP9Error,
    _require_cross_document_sources,
    require_verified_reviewed_motion_bundle,
)
from autospine_workbench.reviewed_motion_bundle_contract import (  # noqa: E402
    DOCUMENT_NAMES,
)
from tests.body_sway_motion_consumer_helpers import (  # noqa: E402
    consumer_fixture,
)


class BodySwayMotionConsumerP9Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        _fixture, cls.bundle, _probe, _identity = consumer_fixture(
            Path(cls.temporary.name)
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_six_file_replay_returns_exact_motion_instance(self):
        motion = require_verified_reviewed_motion_bundle(
            self.bundle,
            self.bundle.identities,
        )
        self.assertEqual(
            self.bundle.document("motion-instance-v2.json"),
            motion,
        )

    def test_project_clip_and_policy_source_cross_wiring_fail(self):
        documents = {
            name: self.bundle.document(name)
            for name in DOCUMENT_NAMES
        }
        with self.assertRaises(BodySwayMotionConsumerP9Error):
            require_verified_reviewed_motion_bundle(
                replace(self.bundle, clip_id="other-clip"),
                self.bundle.identities,
            )

        policy = deepcopy(documents["reviewed-motion-policy.json"])
        policy["source"]["foot_lock_candidates_sha256"] = "0" * 64
        with self.assertRaises(BodySwayMotionConsumerP9Error):
            _require_cross_document_sources(
                self.bundle,
                documents["foot-lock-candidates.json"],
                documents["depth-order-candidates.json"],
                documents["motion-policy-decision.json"],
                policy,
                self.bundle.identities,
            )


if __name__ == "__main__":
    unittest.main()
