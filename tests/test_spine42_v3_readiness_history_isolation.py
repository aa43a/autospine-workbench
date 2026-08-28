"""Readiness replay is invariant to later seam-review history."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.seam_anchor_review_profile import (  # noqa: E402
    DECISION_NAMESPACE,
)
from autospine_workbench.spine42_v3_readiness import (  # noqa: E402
    audit_spine42_v3_readiness,
)
from tests.reviewed_seam_anchor_set_bundle_helpers import (  # noqa: E402
    PersistedReviewedSeamAnchorSetFixture,
)


def request_for(fixture) -> dict:
    source = fixture.address.public_document()
    return {
        "format": "autospine-spine42-v3-readiness-request",
        "format_version": 1,
        "samples": [{
            **source,
            "reviewed_motion_address": None,
            "reviewed_seam_anchor_set_address": {
                "reviewed_seam_anchor_set_sha256":
                    fixture.published.set_sha256,
                "bundle_sha256": fixture.published.bundle_sha256,
            },
            "motion_instance_v3_address": None,
            "spine42_v3_address": None,
            "runtime_capture_address": None,
            "raster_review_decision": None,
        }],
    }


class Spine42V3ReadinessHistoryIsolationTests(unittest.TestCase):
    def test_exact_revision_one_report_ignores_later_revision_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = PersistedReviewedSeamAnchorSetFixture(
                Path(temporary), advance=False,
            )
            request = request_for(fixture)
            before = audit_spine42_v3_readiness(request, fixture.state)
            fixture.advance()
            after_append = audit_spine42_v3_readiness(
                request, fixture.state
            )
            revision_two = (
                fixture.state / "builds" / fixture.published.project_id
                / DECISION_NAMESPACE / fixture.published.candidate_sha256
                / "revisions" / "r000002.json"
            )
            revision_two.write_bytes(b"{}")
            after_corruption = audit_spine42_v3_readiness(
                request, fixture.state
            )
        self.assertEqual(before, after_append)
        self.assertEqual(before, after_corruption)
        self.assertEqual(
            "verified", before["samples"][0]["checkpoints"][2]["status"]
        )


if __name__ == "__main__":
    unittest.main()
