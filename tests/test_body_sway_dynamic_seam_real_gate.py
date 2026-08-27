"""Opt-in real-source P10.5d boundary gate; never creates authority."""

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

from autospine_workbench.mesh_bundle_reader import (  # noqa: E402
    VerifiedMeshBundleReader,
)
from autospine_workbench.reviewed_seam_anchor_set_compiler import (  # noqa: E402
    ReviewedSeamAnchorSetCompilerError,
    compile_reviewed_seam_anchor_set,
)
from autospine_workbench.seam_anchor_candidate_commands import (  # noqa: E402
    compile_seam_anchor_candidates_command,
)
from autospine_workbench.seam_anchor_review_decision import (  # noqa: E402
    build_seam_anchor_review_decision,
)


GOLDEN = ROOT / "tests" / "goldens" / "p10-seam-anchors" / \
    "real-samples.approved.json"
ENABLE = os.environ.get(
    "AUTOSPINE_VERIFY_REAL_BODY_SWAY_DYNAMIC_SEAM_GATE"
) == "1"
_DYNAMIC_AUTHORITY_FIELDS = {
    "body_sway_continuous_proof_sha256",
    "review_revision",
    "seam_anchor_review_decision_sha256",
    "reviewed_seam_anchor_set_sha256",
    "reviewed_seam_anchor_set_bundle_sha256",
}


def _state_root():
    configured = os.environ.get("AUTOSPINE_REAL_STATE_ROOT")
    return Path(configured) if configured else ROOT / "workspace"


def _inventory(root):
    if not root.is_dir():
        return ()
    return tuple(
        (
            path.relative_to(root).as_posix(), path.is_dir(),
            0 if path.is_dir() else path.stat().st_size,
            path.stat().st_mtime_ns,
        )
        for path in sorted(root.rglob("*"))
    )


def _test_only_rows(candidate):
    rows = []
    for relationship in candidate["relationships"]:
        observable = relationship["status"] == "review_required"
        option = next((row for row in relationship["options"]
                       if row["status"] == "candidate"), None)
        rows.append({
            "relationship_id": relationship["relationship_id"],
            "relationship_evidence_sha256": relationship["evidence_sha256"],
            "action": "accept" if observable else "unobservable",
            "option_id": option["option_id"] if observable else None,
            "option_evidence_sha256": (
                option["evidence_sha256"] if observable else None
            ),
            "notes": "TEST-ONLY mechanics; not an artist approval",
        })
    return rows


@unittest.skipUnless(
    ENABLE, "real body-sway dynamic-seam gate is explicitly enabled"
)
class BodySwayDynamicSeamRealGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not GOLDEN.is_file():
            raise unittest.SkipTest(
                "real seam golden is unavailable; no authority was inferred"
            )
        cls.root = _state_root()
        if not cls.root.is_dir():
            raise unittest.SkipTest(
                "real state root is unavailable; no artifact was generated"
            )
        samples = json.loads(GOLDEN.read_text(encoding="utf-8"))["samples"]
        cls.samples = {row["project_id"]: row for row in samples}

    def _load(self, project_id):
        approved = self.samples[project_id]
        source = approved["source"]
        try:
            candidate = compile_seam_anchor_candidates_command(
                self.root, project_id,
                layer_manifest_sha256=source["layer_manifest_sha256"],
                p3_rig_sha256=source["p3_rig_sha256"],
                p3_bundle_sha256=source["p3_bundle_sha256"],
            )
            mesh = VerifiedMeshBundleReader(self.root).load(
                project_id, source["p3_rig_sha256"],
                source["p3_bundle_sha256"],
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            self.skipTest(
                "real exact inputs are unavailable; gate stayed blocked: "
                f"{type(exc).__name__}: {exc}"
            )
        self.assertEqual(
            approved["candidate_sha256"],
            candidate.seam_anchor_candidates_sha256,
        )
        return approved, candidate.document, mesh.rig

    def _decision(self, candidate, rig):
        return build_seam_anchor_review_decision(
            candidate, rig,
            review={
                "reviewer_id": "test-only-dynamic-seam-gate",
                "notes": "TEST-ONLY mechanics; no human authority",
            },
            decisions=_test_only_rows(candidate),
        ).document

    def test_real_a_allows_only_test_only_static_mechanics(self):
        before = _inventory(self.root)
        self.addCleanup(
            lambda: self.assertEqual(before, _inventory(self.root))
        )
        approved, candidate, rig = self._load("seethrough_output")
        self.assertFalse(_DYNAMIC_AUTHORITY_FIELDS & set(approved))
        self.assertFalse(_DYNAMIC_AUTHORITY_FIELDS & set(approved["source"]))
        decision = self._decision(candidate, rig)
        reviewed = compile_reviewed_seam_anchor_set(
            candidate, decision, rig
        ).document
        self.assertEqual(
            "reviewed_anchor_set_ready_for_compile", decision["status"]
        )
        self.assertIn("test-only", decision["review"]["reviewer_id"])
        self.assertIn("TEST-ONLY", decision["review"]["notes"])
        self.assertFalse(reviewed["claims"]["dynamic_seam_safety"])
        self.assertFalse(reviewed["claims"]["release_authority"])
        self.assertEqual("blocked", reviewed["release_gate"]["status"])

    def test_real_b_four_unobservable_relationships_remain_blocked(self):
        before = _inventory(self.root)
        self.addCleanup(
            lambda: self.assertEqual(before, _inventory(self.root))
        )
        _approved, candidate, rig = self._load("seethrough_output_5")
        decision = self._decision(candidate, rig)
        self.assertEqual("reviewed_anchor_set_blocked", decision["status"])
        self.assertEqual(4, decision["summary"]["unobservable_count"])
        with self.assertRaises(ReviewedSeamAnchorSetCompilerError):
            compile_reviewed_seam_anchor_set(candidate, decision, rig)


if __name__ == "__main__":
    unittest.main()
