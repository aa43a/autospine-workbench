"""Publication and filesystem tests for reviewed seam-anchor set bundles."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.reviewed_seam_anchor_set_bundle_contract import (
    DOCUMENT_NAMES,
)
from autospine_workbench.immutable_bundle_fs import ImmutableThreeFileBundleFS
from autospine_workbench.reviewed_seam_anchor_set_bundle_fs import (
    NAMESPACE,
    ReviewedSeamAnchorSetBundleFSError,
    reviewed_seam_anchor_set_bundle_fs,
)
from autospine_workbench.reviewed_seam_anchor_set_bundle_store import (
    ReviewedSeamAnchorSetBundleStore,
    ReviewedSeamAnchorSetBundleStoreError,
)
from autospine_workbench.reviewed_seam_anchor_set_compiler import (
    ReviewedSeamAnchorSet,
)
from autospine_workbench.seam_anchor_review_json import canonical_json_bytes
from autospine_workbench.seam_anchor_candidates import SeamAnchorCandidates
from tests.p9_v2_helpers import tree
from tests.reviewed_seam_anchor_set_bundle_helpers import exact_bundle_values


class ReviewedSeamAnchorSetBundleStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.state = Path(self.temporary.name) / "state"
        self.values = exact_bundle_values()
        self.store = ReviewedSeamAnchorSetBundleStore(self.state)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def publish(self):
        return self.store.publish(*self.values)

    def test_exact_path_inventory_and_identical_reuse(self):
        first = self.publish()
        second = self.publish()
        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        self.assertEqual(first.path, second.path)
        self.assertEqual(
            (
                first.bundle_sha256,
                first.set_sha256,
                NAMESPACE,
                first.project_id,
                "builds",
            ),
            (
                first.path.name,
                first.path.parent.name,
                first.path.parent.parent.name,
                first.path.parent.parent.parent.name,
                first.path.parent.parent.parent.parent.name,
            ),
        )
        self.assertEqual(
            set(DOCUMENT_NAMES), {path.name for path in first.path.iterdir()}
        )
        self.assertEqual(3, len(tuple(first.path.iterdir())))

    def test_identical_concurrent_publishers_converge(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _index: self.publish(), range(4)))
        self.assertEqual(1, sum(not result.reused for result in results))
        self.assertEqual(1, len({result.path for result in results}))
        self.assertEqual(1, len({result.bundle_sha256 for result in results}))
        parent = results[0].path.parent
        self.assertEqual(
            [results[0].bundle_sha256],
            sorted(path.name for path in parent.iterdir()),
        )

    def test_invalid_recompiled_set_is_zero_write(self):
        candidates, decision, rig, reviewed_set = self.values
        changed = deepcopy(reviewed_set.document)
        changed["source"]["seam_anchor_review_decision_sha256"] = "f" * 64
        invalid = ReviewedSeamAnchorSet(
            canonical_json_bytes(changed).decode("utf-8")
        )
        before = tree(self.state)
        with self.assertRaises(ReviewedSeamAnchorSetBundleStoreError):
            self.store.publish(candidates, decision, rig, invalid)
        self.assertEqual(before, tree(self.state))
        self.assertFalse(self.state.exists())

    def test_wrong_value_type_is_zero_write(self):
        candidates, decision, rig, reviewed_set = self.values
        with self.assertRaises(ReviewedSeamAnchorSetBundleStoreError):
            self.store.publish(  # type: ignore[arg-type]
                candidates.document, decision, rig, reviewed_set
            )
        self.assertFalse(self.state.exists())

    def test_malformed_value_object_is_normalized_and_zero_write(self):
        _candidates, decision, rig, reviewed_set = self.values
        with self.assertRaises(ReviewedSeamAnchorSetBundleStoreError):
            self.store.publish(
                SeamAnchorCandidates("{"), decision, rig, reviewed_set
            )
        self.assertFalse(self.state.exists())

    def test_caller_rig_mutation_after_write_cannot_change_readback(self):
        original = ImmutableThreeFileBundleFS.publish
        rig = self.values[2]

        def publish_then_mutate(filesystem, *args, **kwargs):
            published = original(filesystem, *args, **kwargs)
            rig.clear()
            return published

        with patch.object(
            ImmutableThreeFileBundleFS,
            "publish",
            publish_then_mutate,
        ):
            published = self.publish()
        self.assertTrue(published.path.is_dir())
        self.assertEqual(set(DOCUMENT_NAMES), {
            child.name for child in published.path.iterdir()
        })

    def test_unsafe_project_component_is_zero_write(self):
        with self.assertRaises(ReviewedSeamAnchorSetBundleFSError):
            reviewed_seam_anchor_set_bundle_fs(self.state, "../escape")
        self.assertFalse(self.state.exists())


if __name__ == "__main__":
    unittest.main()
