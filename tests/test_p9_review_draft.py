"""Exact-chain tests for automated, non-authoritative P9 draft preparation."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.p9_review_draft import (  # noqa: E402
    P9ReviewDraftError,
    prepare_p9_review_draft,
)
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402


SHA = {
    name: character * 64
    for name, character in zip(
        ("p3r", "p3b", "p4p", "p4b", "p5i", "p5b",
         "p7m", "p7b", "p8m", "p8b", "p7run"),
        "abcdefghijk",
        strict=True,
    )
}


class _Reader:
    value = None

    def __init__(self, _state):
        pass

    def load(self, *_args, **_kwargs):
        return self.value


class P9ReviewDraftTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.state = Path(temporary.name) / "state"
        self.state.mkdir()
        self.p3 = SimpleNamespace(
            rig_sha256=SHA["p3r"], bundle_sha256=SHA["p3b"],
        )
        self.p4 = SimpleNamespace(
            profile_sha256=SHA["p4p"], bundle_sha256=SHA["p4b"],
            p3_rig_sha256=SHA["p3r"], p3_bundle_sha256=SHA["p3b"],
        )
        self.p5 = SimpleNamespace(
            instance_sha256=SHA["p5i"], bundle_sha256=SHA["p5b"],
            path=Path("C:/private/p5"),
            source_addresses={
                "p3_rig_sha256": SHA["p3r"],
                "p3_bundle_sha256": SHA["p3b"],
                "p4_profile_sha256": SHA["p4p"],
                "p4_bundle_sha256": SHA["p4b"],
                "motion_clip_sha256": SHA["p7m"],
                "motion_bundle_sha256": SHA["p7b"],
            },
        )
        self.p7 = SimpleNamespace(
            clip_sha256=SHA["p7m"], bundle_sha256=SHA["p7b"],
        )
        self.p8 = SimpleNamespace(
            projected_motion_sha256=SHA["p8m"],
            bundle_sha256=SHA["p8b"], clip_id="wave.left",
            p7_motion_sha256=SHA["p7m"], p7_bundle_sha256=SHA["p7b"],
            path=Path("C:/private/p8"),
        )
        self.evidence_sha256 = canonical_sha256({"format": "evidence"})

    def prepare(self):
        readers = (
            self.p3, self.p4, self.p5, self.p7, self.p8,
        )
        reader_names = (
            "VerifiedMeshBundleReader", "VerifiedIkBundleReader",
            "VerifiedMotionRetargetBundleReader", "VerifiedMotionBundleReader",
            "VerifiedProjectedMotionBundleReader",
        )
        patches = []
        for name, value in zip(reader_names, readers, strict=True):
            reader = type(f"{name}Fake", (_Reader,), {"value": value})
            patches.append(patch(
                f"autospine_workbench.p9_review_draft.{name}", reader
            ))
        evidence_document = {"format": "evidence"}
        evidence = SimpleNamespace(
            document=evidence_document,
            sha256=self.evidence_sha256,
        )
        foot_document = {"format": "foot"}
        foot = SimpleNamespace(
            document=foot_document,
            sha256=canonical_sha256(foot_document),
        )
        proposal = {"format": "proposal", "review": {"status": "pending"}}
        patches.extend((
            patch(
                "autospine_workbench.p9_review_draft."
                "compile_kimodo_policy_evidence", return_value=evidence,
            ),
            patch(
                "autospine_workbench.p9_review_draft."
                "compile_foot_lock_candidates", return_value=foot,
            ),
            patch(
                "autospine_workbench.p9_review_draft."
                "require_depth_order_inputs", return_value=object(),
            ),
            patch(
                "autospine_workbench.p9_review_draft."
                "compile_depth_pair_policy_proposal", return_value=proposal,
            ),
        ))
        with patches[0], patches[1], patches[2], patches[3], patches[4], \
                patches[5], patches[6], patches[7], patches[8]:
            return prepare_p9_review_draft(
                self.state, "sample", "wave-left-r15-draft",
                p3_rig_sha256=SHA["p3r"],
                p3_bundle_sha256=SHA["p3b"],
                p4_profile_sha256=SHA["p4p"],
                p4_bundle_sha256=SHA["p4b"],
                motion_instance_sha256=SHA["p5i"],
                motion_retarget_bundle_sha256=SHA["p5b"],
                p7_motion_sha256=SHA["p7m"],
                p7_bundle_sha256=SHA["p7b"],
                p8_motion_sha256=SHA["p8m"],
                p8_bundle_sha256=SHA["p8b"],
                first_slot_id="moving", second_slot_id="face",
                pair_id="moving-vs-face",
            )

    def test_publishes_path_free_pending_inventory_and_reuses_it(self):
        first = self.prepare()
        second = self.prepare()
        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        root = self.state / "reviews" / "wave-left-r15-draft"
        paths = sorted(
            path.relative_to(root).as_posix()
            for path in root.rglob("*") if path.is_file()
        )
        self.assertEqual([
            "sample/depth-pair-policy.proposal.json",
            "sample/draft-manifest.json",
            "sample/foot-lock-candidates.json",
            "shared/kimodo-policy-evidence.json",
        ], paths)
        payload = b"".join((root / path).read_bytes() for path in paths)
        self.assertNotIn(b"C:/private", payload)
        manifest = json.loads(
            (root / "sample" / "draft-manifest.json").read_text("utf-8")
        )
        self.assertEqual("pending_human_depth_policy_review", manifest["status"])
        self.assertEqual(first.manifest_sha256, canonical_sha256(manifest))
        self.assertFalse(manifest["authority"]["approved_depth_policy"])
        self.assertFalse(manifest["authority"]["p9_adoption_emitted"])

    def test_cross_wired_chain_fails_before_creating_review_root(self):
        self.p5.source_addresses = dict(self.p5.source_addresses)
        self.p5.source_addresses["p4_bundle_sha256"] = "0" * 64
        with self.assertRaises(P9ReviewDraftError):
            self.prepare()
        self.assertFalse((self.state / "reviews").exists())

    def test_compiler_identity_mismatch_fails_before_publication(self):
        self.evidence_sha256 = "0" * 64
        with self.assertRaises(P9ReviewDraftError):
            self.prepare()
        self.assertFalse((self.state / "reviews").exists())


if __name__ == "__main__":
    unittest.main()
