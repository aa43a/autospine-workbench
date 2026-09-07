"""Keep the existing A/B golden boundary explicit during product automation."""

import json
from pathlib import Path
import unittest


GOLDEN = Path(__file__).resolve().parent / "goldens" / "p10-seam-anchors" / "real-samples.approved.json"


class CertificationBaselineBoundaryTests(unittest.TestCase):
    def test_b_negative_fixture_retains_four_unobservable_lower_limb_seams(self):
        samples = json.loads(GOLDEN.read_text(encoding="utf-8"))["samples"]
        sample = next(row for row in samples if row["project_id"] == "seethrough_output_5")
        self.assertEqual(
            "f53d049df823b2507db5cafa7e0d06bf97519e6bf0494bbfb53c5911d37d2a37",
            sample["candidate_sha256"],
        )
        blocked = {row["relationship_id"]: row for row in sample["relationships"]
                   if row["status"] == "unobservable"}
        self.assertEqual({
            "seam.pelvis_leg.left", "seam.pelvis_leg.right",
            "seam.leg_foot.left", "seam.leg_foot.right",
        }, set(blocked))
        self.assertEqual(4, sample["summary"]["unobservable_count"])
        for row in blocked.values():
            self.assertEqual([], row["options"])
            self.assertIn("NO_SUPPORTED_CANDIDATE_PAIR", row["reason_codes"])

    def test_a_history_is_not_relabelled_as_current_or_as_runtime_approval(self):
        samples = json.loads(GOLDEN.read_text(encoding="utf-8"))["samples"]
        sample = next(row for row in samples if row["project_id"] == "seethrough_output")
        self.assertEqual(
            "8b84858b1a723e20374892c0fc570385c8a23ff91b7398839af3218b67f21ff6",
            sample["candidate_sha256"],
        )
        self.assertEqual(0, sample["summary"]["unobservable_count"])
        self.assertEqual(6, sample["summary"]["review_required_count"])
        self.assertEqual("manual_review_required", sample["summary"]["status"])
        self.assertEqual({
            "layer_manifest_sha256", "p3_rig_sha256", "p3_bundle_sha256",
        }, set(sample["source"]))
