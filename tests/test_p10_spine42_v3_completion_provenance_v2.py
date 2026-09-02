from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT, ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.p10_spine42_v3_job_v2 import P10Spine42V3JobStoreV2
from autospine_workbench.spine42_v3_runtime_candidate_catalog_v2 import (
    read_spine42_v3_runtime_candidate_catalog_v2,
)
from tests.p10_spine42_v3_runtime_candidate_support import (
    complete, inputs, result, rewrite_run, tree_snapshot,
)


class P10Spine42V3CompletionProvenanceV2Tests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = P10Spine42V3JobStoreV2(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def _new(self):
        return self.store.create(inputs(), attempt=1, previous_run_id=None)

    def _running(self, row, stage, *, current=0, total=1):
        return self.store.append(
            row.run_id, "running", stage,
            expected_previous=row.head_sha256,
            current=current, total=total,
        )

    def _finish(self, row, stages):
        for stage, current, total in stages:
            row = self._running(
                row, stage, current=current, total=total)
        return self.store.append(
            row.run_id, "completed", "completed",
            expected_previous=row.head_sha256, current=1, total=1,
            result=result(),
        )

    def _assert_invalid_provenance(self):
        before = tree_snapshot(self.root)
        catalog = read_spine42_v3_runtime_candidate_catalog_v2(self.root)
        self.assertEqual(before, tree_snapshot(self.root))
        self.assertEqual((), catalog.candidates)
        self.assertEqual("invalid_provenance", catalog.skips[0]["code"])
        self.assertEqual("blocked", catalog.selection["mode"])

    def test_queued_directly_to_completed_is_not_trusted(self):
        row = self._new()
        self.store.append(
            row.run_id, "completed", "completed",
            expected_previous=row.head_sha256, current=1, total=1,
            result=result(),
        )
        self._assert_invalid_provenance()

    def test_repeated_stage_is_not_the_real_manager_success_trace(self):
        row = self._running(self._new(), "exact_motion_instance")
        row = self._running(row, "exact_motion_instance")
        self._finish(row, (
            ("source_adapter", 0, 1), ("spine_adapter", 0, 1),
            ("publication", 1, 1), ("parent_exact_readback", 0, 1),
        ))
        self._assert_invalid_provenance()

    def test_non_manager_progress_is_not_trusted(self):
        self._finish(self._new(), (
            ("exact_motion_instance", 0, 2), ("source_adapter", 0, 1),
            ("spine_adapter", 0, 1), ("publication", 1, 1),
            ("parent_exact_readback", 0, 1),
        ))
        self._assert_invalid_provenance()

    def test_request_float_format_version_passes_old_loader_but_not_inventory(self):
        row = complete(self.store, self._new())
        identifier = rewrite_run(
            self.root, row,
            request_change=lambda request: request.__setitem__(
                "format_version", 2.0),
        )
        self.assertEqual("completed", self.store.load(identifier).status)
        catalog = read_spine42_v3_runtime_candidate_catalog_v2(self.root)
        self.assertEqual((), catalog.candidates)
        self.assertEqual("invalid_run", catalog.skips[0]["code"])

    def test_event_float_format_version_is_rejected_after_exact_rehash(self):
        row = complete(self.store, self._new())
        rewrite_run(
            self.root, row,
            event_change=lambda event, position: event.__setitem__(
                "format_version", 2.0) if position == 4 else None,
        )
        self.assertEqual("completed", self.store.load(row.run_id).status)
        catalog = read_spine42_v3_runtime_candidate_catalog_v2(self.root)
        self.assertEqual("invalid_run", catalog.skips[0]["code"])

    def test_boolean_event_sequence_is_rejected_after_exact_rehash(self):
        row = complete(self.store, self._new())
        rewrite_run(
            self.root, row,
            event_change=lambda event, position: event.__setitem__(
                "sequence", True) if position == 1 else None,
        )
        self.assertEqual("completed", self.store.load(row.run_id).status)
        catalog = read_spine42_v3_runtime_candidate_catalog_v2(self.root)
        self.assertEqual("invalid_run", catalog.skips[0]["code"])


if __name__ == "__main__":
    unittest.main()
