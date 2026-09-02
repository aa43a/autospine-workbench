from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT, ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.p10_spine42_v3_completion_inventory_v2 import (
    P10Spine42V3CompletionInventoryV2Error,
    read_p10_spine42_v3_completion_inventory_v2,
)
from autospine_workbench.p10_spine42_v3_job_v2 import (
    NAMESPACE, P10Spine42V3JobStoreV2,
)
from autospine_workbench.p10_spine42_v3_job_contract_v2 import request_document
from tests.p10_spine42_v3_runtime_candidate_support import (
    complete, fail_retryable, inputs, sha, tree_snapshot, write_request_only,
)

MODULE = "autospine_workbench.p10_spine42_v3_completion_inventory_v2."


class P10Spine42V3CompletionInventoryV2Tests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = P10Spine42V3JobStoreV2(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def test_exact_attempt_numbers_and_predecessors_choose_the_head(self):
        first = self.store.create(
            inputs(), attempt=1, previous_run_id=None)
        first = fail_retryable(self.store, first)
        second = self.store.create(
            inputs(), attempt=2, previous_run_id=first.run_id)
        second = complete(self.store, second)
        run_root = self.root / "jobs" / NAMESPACE
        first_path, second_path = run_root / first.run_id, run_root / second.run_id
        newer = second_path.stat().st_mtime_ns + 10_000_000_000
        os.utime(first_path, ns=(newer, newer))
        self.assertGreater(first_path.stat().st_mtime_ns,
                           second_path.stat().st_mtime_ns)
        inventory = read_p10_spine42_v3_completion_inventory_v2(self.root)
        self.assertEqual(1, len(inventory.families))
        family = inventory.families[0]
        self.assertIsNone(family.issue_code)
        self.assertEqual([1, 2], [row.request["attempt"]
                                  for row in family.runs])
        self.assertLess(second.run_id, first.run_id)
        self.assertEqual(second.run_id, family.head.run_id)
        self.assertEqual((), inventory.skipped)

    def test_source_change_inside_one_attempt_chain_is_ambiguous(self):
        first = self.store.create(
            inputs(), attempt=1, previous_run_id=None)
        first = fail_retryable(self.store, first)
        second = self.store.create(
            inputs(source="5b"), attempt=2,
            previous_run_id=first.run_id,
        )
        complete(self.store, second)
        inventory = read_p10_spine42_v3_completion_inventory_v2(self.root)
        self.assertEqual("source_drift", inventory.families[0].issue_code)
        self.assertIsNone(inventory.families[0].head)

    def test_unreadable_run_is_a_skip_not_an_implicit_candidate(self):
        row = complete(self.store, self.store.create(
            inputs(), attempt=1, previous_run_id=None))
        invalid = self.root / "jobs" / NAMESPACE / sha("f")
        invalid.mkdir()
        inventory = read_p10_spine42_v3_completion_inventory_v2(self.root)
        self.assertEqual((row.run_id, sha("f")),
                         tuple(sorted(inventory.enumerated_run_ids)))
        self.assertEqual("invalid_run", inventory.skipped[0].code)
        self.assertEqual(sha("f"), inventory.skipped[0].spine_run_id)

    def test_inventory_is_zero_write_and_never_uses_latest_or_run_ids(self):
        complete(self.store, self.store.create(
            inputs(), attempt=1, previous_run_id=None))
        before = tree_snapshot(self.root)
        with patch.object(
            P10Spine42V3JobStoreV2, "latest",
            side_effect=AssertionError("latest must not be used"),
        ), patch.object(
            P10Spine42V3JobStoreV2, "_run_ids",
            side_effect=AssertionError("writing enumerator must not be used"),
        ):
            inventory = read_p10_spine42_v3_completion_inventory_v2(
                self.root)
        self.assertEqual(1, len(inventory.families))
        self.assertEqual(before, tree_snapshot(self.root))

    def test_empty_store_is_zero_write(self):
        before = tree_snapshot(self.root)
        inventory = read_p10_spine42_v3_completion_inventory_v2(self.root)
        self.assertEqual((), inventory.enumerated_run_ids)
        self.assertEqual(before, tree_snapshot(self.root))

    def test_alias_and_wrong_case_entries_fail_the_entire_inventory(self):
        family = self.root / "jobs" / NAMESPACE
        family.mkdir(parents=True)
        target = self.root / "real-run"
        target.mkdir()
        alias = family / sha("a")
        try:
            os.symlink(target, alias, target_is_directory=True)
        except (NotImplementedError, OSError):
            self.skipTest("Directory symlinks are unavailable")
        with self.assertRaises(P10Spine42V3CompletionInventoryV2Error):
            read_p10_spine42_v3_completion_inventory_v2(self.root)
        alias.unlink()
        (family / sha("A")).mkdir()
        with self.assertRaises(P10Spine42V3CompletionInventoryV2Error):
            read_p10_spine42_v3_completion_inventory_v2(self.root)

    def test_bound_is_checked_before_any_run_is_loaded(self):
        family = self.root / "jobs" / NAMESPACE
        family.mkdir(parents=True)
        (family / sha("a")).mkdir()
        (family / sha("b")).mkdir()
        with patch(MODULE + "MAX_RUNS", 1), patch.object(
            P10Spine42V3JobStoreV2, "load",
            side_effect=AssertionError("load must not run past the bound"),
        ), self.assertRaises(P10Spine42V3CompletionInventoryV2Error):
            read_p10_spine42_v3_completion_inventory_v2(self.root)

    def test_integer_shas_are_skipped_before_mixed_type_grouping(self):
        complete(self.store, self.store.create(
            inputs(), attempt=1, previous_run_id=None))
        documents = []
        upstream = request_document(inputs(), 1, None)
        upstream["job_id"] = int("1" * 64)
        documents.append(upstream)
        source = request_document(inputs(upstream="bcde"), 1, None)
        source["motion_instance_v3_sha256"] = int("5" * 64)
        documents.append(source)
        previous = request_document(
            inputs(upstream="cdef"), 2, sha("9"))
        previous["previous_run_id"] = int("9" * 64)
        documents.append(previous)
        invalid_ids = tuple(
            write_request_only(self.root, document) for document in documents)
        before = tree_snapshot(self.root)
        inventory = read_p10_spine42_v3_completion_inventory_v2(self.root)
        self.assertEqual(before, tree_snapshot(self.root))
        self.assertEqual(
            set(invalid_ids), {row.spine_run_id for row in inventory.skipped})
        self.assertEqual(
            {"invalid_run"}, {row.code for row in inventory.skipped})
        self.assertEqual(1, len(inventory.families))


if __name__ == "__main__":
    unittest.main()
