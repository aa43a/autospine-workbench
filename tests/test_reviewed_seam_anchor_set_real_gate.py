"""Opt-in real-source P10.5c contract gate without review publication."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
for item in (ROOT, ROOT / "src"):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.mesh_bundle_reader import VerifiedMeshBundleReader
from autospine_workbench.reviewed_seam_anchor_set_compiler import (
    ReviewedSeamAnchorSetCompilerError,
    compile_reviewed_seam_anchor_set,
)
from autospine_workbench.seam_anchor_candidate_commands import (
    compile_seam_anchor_candidates_command,
)
from autospine_workbench.seam_anchor_review_decision import (
    build_seam_anchor_review_decision,
)


GOLDEN = ROOT / "tests" / "goldens" / "p10-seam-anchors" / \
    "real-samples.approved.json"
ENABLE = os.environ.get(
    "AUTOSPINE_VERIFY_REAL_REVIEWED_SEAM_SET_GATE"
) == "1"


def _approval():
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def _state_root():
    configured = os.environ.get("AUTOSPINE_REAL_STATE_ROOT")
    return Path(configured) if configured else ROOT / "workspace"


def _inventory(root):
    """Record metadata only; reading the gate must not publish an artifact."""

    return tuple(
        (
            path.relative_to(root).as_posix(),
            path.is_dir(),
            0 if path.is_dir() else path.stat().st_size,
            path.stat().st_mtime_ns,
        )
        for path in sorted(root.rglob("*"))
    )


def _test_only_accept_first_rows(candidate):
    """Synthesize contract input, never an artist decision or approval golden."""

    rows = []
    for relationship in candidate["relationships"]:
        option = next((
            item for item in relationship["options"]
            if item["status"] == "candidate"
        ), None)
        observable = relationship["status"] == "review_required"
        rows.append({
            "relationship_id": relationship["relationship_id"],
            "relationship_evidence_sha256": relationship[
                "evidence_sha256"
            ],
            "action": "accept" if observable else "unobservable",
            "option_id": option["option_id"] if observable else None,
            "option_evidence_sha256": (
                option["evidence_sha256"] if observable else None
            ),
            "notes": "TEST-ONLY contract gate; not an artist approval",
        })
    return rows


def _load_real_inputs(root, approved):
    source = approved["source"]
    candidate = compile_seam_anchor_candidates_command(
        root, approved["project_id"],
        layer_manifest_sha256=source["layer_manifest_sha256"],
        p3_rig_sha256=source["p3_rig_sha256"],
        p3_bundle_sha256=source["p3_bundle_sha256"],
    )
    mesh = VerifiedMeshBundleReader(root).load(
        approved["project_id"], source["p3_rig_sha256"],
        source["p3_bundle_sha256"],
    )
    if candidate.seam_anchor_candidates_sha256 != approved[
        "candidate_sha256"
    ]:
        raise AssertionError("real candidate differs from its approved golden")
    return candidate.document, mesh.rig


def _synthetic_decision(candidate, rig):
    return build_seam_anchor_review_decision(
        candidate, rig,
        review={
            "reviewer_id": "test-only-contract-gate",
            "notes": "TEST-ONLY synthesized input; not human approval",
        },
        decisions=_test_only_accept_first_rows(candidate),
    ).document


@unittest.skipUnless(
    ENABLE, "real reviewed-seam-set gate is explicitly enabled"
)
class ReviewedSeamAnchorSetRealGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        samples = _approval()["samples"]
        cls.approved = {row["project_id"]: row for row in samples}
        cls.root = _state_root()

    def test_real_a_is_contract_compilable_without_an_approval_golden(self):
        before = _inventory(self.root)
        candidate, rig = _load_real_inputs(
            self.root, self.approved["seethrough_output"]
        )
        decision = _synthetic_decision(candidate, rig)
        result = compile_reviewed_seam_anchor_set(
            candidate, decision, rig
        )
        self.assertEqual(
            "reviewed_anchor_set_ready_for_compile", decision["status"]
        )
        self.assertIn("test-only", decision["review"]["reviewer_id"])
        self.assertIn("TEST-ONLY", decision["review"]["notes"])
        self.assertEqual("blocked", result.document["release_gate"]["status"])
        self.assertFalse(result.document["claims"]["release_authority"])
        self.assertNotIn("decision_sha256", self.approved["seethrough_output"])
        self.assertNotIn(
            "reviewed_seam_anchor_set_sha256",
            self.approved["seethrough_output"],
        )
        self.assertEqual(before, _inventory(self.root))

    def test_real_b_remains_blocked_and_cannot_compile(self):
        before = _inventory(self.root)
        candidate, rig = _load_real_inputs(
            self.root, self.approved["seethrough_output_5"]
        )
        decision = _synthetic_decision(candidate, rig)
        self.assertEqual(
            "reviewed_anchor_set_blocked", decision["status"]
        )
        self.assertEqual(4, decision["summary"]["unobservable_count"])
        with self.assertRaises(ReviewedSeamAnchorSetCompilerError):
            compile_reviewed_seam_anchor_set(candidate, decision, rig)
        self.assertEqual(before, _inventory(self.root))


if __name__ == "__main__":
    unittest.main()
