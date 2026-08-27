"""Approved P10.5a projections for the two real See-through samples."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.seam_anchor_candidate_commands import (
    compile_seam_anchor_candidates_command,
)


GOLDEN = ROOT / "tests" / "goldens" / "p10-seam-anchors" / \
    "real-samples.approved.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
RELATIONSHIPS = (
    "seam.torso_arm.left", "seam.torso_arm.right",
    "seam.pelvis_leg.left", "seam.pelvis_leg.right",
    "seam.leg_foot.left", "seam.leg_foot.right",
)
PROJECT_IDS = ("seethrough_output", "seethrough_output_5")
SOURCE_FIELDS = {
    "layer_manifest_sha256", "p3_rig_sha256", "p3_bundle_sha256",
}


def _approval():
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate seam golden key: {key}")
            result[key] = value
        return result

    def nonfinite(value):
        raise ValueError(f"non-finite seam golden value: {value}")

    return json.loads(
        GOLDEN.read_text(encoding="utf-8"),
        object_pairs_hook=pairs, parse_constant=nonfinite,
    )


def _projection(result):
    document = result.document
    return {
        "candidate_sha256": result.seam_anchor_candidates_sha256,
        "summary": document["summary"],
        "relationships": [{
            "relationship_id": row["relationship_id"],
            "status": row["status"],
            "reason_codes": row["reason_codes"],
            "options": [{
                "parent": option["parent_attachment_id"],
                "child": option["child_attachment_id"],
                "types": [option["parent_attachment_type"],
                          option["child_attachment_type"]],
                "status": option["status"],
                "mode": None if option["contact_evidence"] is None
                else option["contact_evidence"]["mode"],
                "anchor_pair_count": len(option["anchors"]),
            } for option in row["options"]],
        } for row in document["relationships"]],
    }


class SeamAnchorGoldenTests(unittest.TestCase):
    def test_approval_is_strict_complete_and_counted(self):
        approved = _approval()
        self.assertEqual({"format", "format_version", "samples"},
                         set(approved))
        self.assertEqual("autospine-p10-seam-anchor-goldens",
                         approved["format"])
        self.assertEqual(1, approved["format_version"])
        self.assertEqual(2, len(approved["samples"]))
        project_ids = tuple(
            sample.get("project_id") for sample in approved["samples"]
        )
        self.assertEqual(PROJECT_IDS, project_ids)
        self.assertEqual(2, len(set(project_ids)))
        for sample in approved["samples"]:
            with self.subTest(project=sample["project_id"]):
                self.assertEqual({
                    "project_id", "source", "candidate_sha256", "summary",
                    "relationships",
                }, set(sample))
                self.assertEqual(SOURCE_FIELDS, set(sample["source"]))
                self.assertTrue(SHA256.fullmatch(sample["candidate_sha256"]))
                self.assertTrue(all(
                    SHA256.fullmatch(value) for value in sample["source"].values()
                ))
                self.assertEqual(RELATIONSHIPS, tuple(
                    row["relationship_id"] for row in sample["relationships"]
                ))
                options = [option for row in sample["relationships"]
                           for option in row["options"]]
                self.assertEqual(len(options), sample["summary"]["option_count"])
                self.assertEqual(sum(
                    option["anchor_pair_count"] for option in options
                ), sample["summary"]["anchor_pair_count"])

    @unittest.skipUnless(
        os.environ.get("AUTOSPINE_VERIFY_REAL_SEAM_GOLDENS") == "1",
        "real static seam golden verification is explicitly enabled",
    )
    def test_real_bundles_reproduce_approved_projection(self):
        for sample in _approval()["samples"]:
            source = sample["source"]
            with self.subTest(project=sample["project_id"]):
                result = compile_seam_anchor_candidates_command(
                    ROOT / "workspace", sample["project_id"],
                    layer_manifest_sha256=source["layer_manifest_sha256"],
                    p3_rig_sha256=source["p3_rig_sha256"],
                    p3_bundle_sha256=source["p3_bundle_sha256"],
                )
                expected = {key: sample[key] for key in (
                    "candidate_sha256", "summary", "relationships",
                )}
                self.assertEqual(expected, _projection(result))


if __name__ == "__main__":
    unittest.main()
