from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from autospine_workbench.p10_dynamic_seam_auto_inputs_v2 import (
    P10DynamicSeamAutoInputsV2Error,
    resolve_p10_dynamic_seam_auto_inputs_v2,
)


class AutoInputsV2Tests(unittest.TestCase):
    def test_resolves_exact_completed_safety_and_current_publication(self):
        with _patched():
            value = resolve_p10_dynamic_seam_auto_inputs_v2(
                "state", "1" * 64, "2" * 64,
            )
        self.assertEqual(value.continuous_proof_sha256, "3" * 64)
        self.assertEqual(value.reviewed_set_sha256, "6" * 64)
        self.assertEqual(value.reviewed_set_bundle_sha256, "7" * 64)
        self.assertEqual(value.review_revision, 1)

    def test_historical_publication_fails_closed(self):
        verified = _verified()
        verified.review_revision = 0
        with _patched(verified=verified), self.assertRaises(
            P10DynamicSeamAutoInputsV2Error
        ):
            resolve_p10_dynamic_seam_auto_inputs_v2(
                "state", "1" * 64, "2" * 64,
            )


def _patched(*, verified=None):
    return _Patches(verified or _verified())


class _Patches:
    def __init__(self, verified):
        self.verified = verified
        self.items = []

    def __enter__(self):
        safety = SimpleNamespace(
            status="completed",
            request=SimpleNamespace(document={
                "job_id": "1" * 64, "package_id": "package-a",
            }),
            events=(SimpleNamespace(document={
                "result": {"continuous_sha256": "3" * 64},
            }),),
        )
        store = SimpleNamespace(
            load=lambda _run: safety,
            read_result=lambda _run: ({}, {"format_version": 2}),
        )
        history = SimpleNamespace(
            revision_count=1, current_revision=1,
            head_decision_sha256="5" * 64,
        )
        prepared = SimpleNamespace(
            history=history, candidate_sha256="4" * 64,
        )
        values = (
            (_MODULE + "P10SafetyAnalysisJobStoreV2", lambda _root: store),
            (_MODULE + "build_motion_policy_seam_review_entry", lambda *_: {
                "status": "manual_review_required", "blocking_relationships": [],
                "candidate_sha256": "4" * 64, "project_id": "project-a",
                "address": {"project_id": "project-a",
                    "layer_manifest_sha256": "8" * 64,
                    "p3_rig_sha256": "9" * 64,
                    "p3_bundle_sha256": "a" * 64},
            }),
            (_MODULE + "SeamAnchorReviewApplication",
             lambda _root: SimpleNamespace(prepare=lambda _address: prepared)),
            (_MODULE + "load_seam_review_publication_record", lambda *_: {
                "status": "passed", "source": {"project_id": "project-a"},
                "address": {"project_id": "project-a",
                    "reviewed_set_sha256": "6" * 64,
                    "bundle_sha256": "7" * 64},
            }),
            (_MODULE + "verify_reviewed_seam_anchor_set_command",
             lambda *_args, **_kwargs: self.verified),
        )
        self.items = [patch(name, side_effect=value) for name, value in values]
        for item in self.items:
            item.start()
        return self

    def __exit__(self, *_):
        for item in reversed(self.items):
            item.stop()


def _verified():
    return SimpleNamespace(candidate_sha256="4" * 64,
                           review_revision=1,
                           decision_sha256="5" * 64)


_MODULE = "autospine_workbench.p10_dynamic_seam_auto_inputs_v2."


if __name__ == "__main__":
    unittest.main()
