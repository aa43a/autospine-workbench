from __future__ import annotations

from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT, ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.p10_spine42_v3_job_v2 import (
    NAMESPACE, P10Spine42V3JobStoreV2,
)
from autospine_workbench.p10_spine42_v3_job_contract_v2 import request_document
from autospine_workbench.spine42_v3_runtime_candidate_catalog_v2 import (
    Spine42V3RuntimeCandidateCatalogV2Error,
    read_spine42_v3_runtime_candidate_catalog_v2,
    revalidate_spine42_v3_runtime_candidate_entry_v2,
)
from tests.p10_spine42_v3_runtime_candidate_support import (
    complete, contains_path_key, fail_retryable, inputs, sha, tree_snapshot,
    write_request_only,
)


class Spine42V3RuntimeCandidateCatalogV2Tests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = P10Spine42V3JobStoreV2(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def _completed(self, **values):
        source = inputs(**{key: values[key] for key in (
            "upstream", "project", "source") if key in values})
        row = self.store.create(source, attempt=1, previous_run_id=None)
        return complete(
            self.store, row,
            **{key: values[key] for key in (
                "project", "clip", "output") if key in values},
        )

    def test_unique_candidate_is_recommended_but_never_authorized(self):
        row = self._completed()
        before = tree_snapshot(self.root)
        catalog = read_spine42_v3_runtime_candidate_catalog_v2(self.root)
        public = catalog.public_document()
        self.assertEqual("automatic", public["selection"]["mode"])
        self.assertEqual("unique_eligible_candidate",
                         public["selection"]["reason_code"])
        self.assertEqual(row.run_id,
                         public["candidates"][0]["completion"]["spine_run_id"])
        self.assertFalse(public["runner_execution_authorized"])
        self.assertFalse(public["publication_authorized"])
        self.assertFalse(contains_path_key(public))
        self.assertNotIn(str(self.root), repr(public))
        self.assertEqual(before, tree_snapshot(self.root))
        candidate = catalog.candidates[0]
        self.assertEqual(candidate,
                         revalidate_spine42_v3_runtime_candidate_entry_v2(
                             self.root, candidate.candidate_id,
                             candidate.entry_sha256))
        with self.assertRaises(Spine42V3RuntimeCandidateCatalogV2Error):
            revalidate_spine42_v3_runtime_candidate_entry_v2(
                self.root, candidate.candidate_id, sha("f"))

    def test_fresh_revalidation_rejects_a_changed_current_head(self):
        row = self._completed()
        catalog = read_spine42_v3_runtime_candidate_catalog_v2(self.root)
        candidate = catalog.candidates[0]
        self.assertEqual(candidate, revalidate_spine42_v3_runtime_candidate_entry_v2(
            self.root, candidate.candidate_id, candidate.entry_sha256))
        completed_event = self.root / "jobs" / NAMESPACE / row.run_id \
            / "events" / "000007.json"
        completed_event.unlink()
        with self.assertRaises(Spine42V3RuntimeCandidateCatalogV2Error):
            revalidate_spine42_v3_runtime_candidate_entry_v2(
                self.root, candidate.candidate_id, candidate.entry_sha256)

    def test_multiple_candidates_require_selection_but_exact_continuation_wins(self):
        first = self._completed()
        self._completed(
            upstream="abcd", project="other", source="ef", output="5678")
        catalog = read_spine42_v3_runtime_candidate_catalog_v2(self.root)
        self.assertEqual(2, len(catalog.candidates))
        self.assertEqual("selection_required", catalog.selection["mode"])
        self.assertEqual("multiple_candidates", catalog.selection["reason_code"])
        continued = read_spine42_v3_runtime_candidate_catalog_v2(
            self.root, continuation_spine_run_id=first.run_id)
        self.assertEqual("continuation", continued.selection["mode"])
        chosen = revalidate_spine42_v3_runtime_candidate_entry_v2(
            self.root,
            continued.selection["recommended_candidate_id"],
            continued.selection["recommended_entry_sha256"],
        )
        self.assertEqual(first.run_id, chosen.spine_run_id)

    def test_invalid_or_missing_continuation_never_falls_back(self):
        self._completed()
        for continuation, reason in (
            ("not-a-sha", "continuation_invalid"),
            (sha("0"), "continuation_not_found"),
        ):
            with self.subTest(reason=reason):
                catalog = read_spine42_v3_runtime_candidate_catalog_v2(
                    self.root, continuation_spine_run_id=continuation)
                self.assertEqual("blocked", catalog.selection["mode"])
                self.assertEqual(reason, catalog.selection["reason_code"])
                self.assertIsNone(
                    catalog.selection["recommended_candidate_id"])
                if reason == "continuation_invalid":
                    self.assertIsNone(
                        catalog.selection["requested_spine_run_id"])

    def test_a_skipped_head_suppresses_otherwise_unique_auto_selection(self):
        self._completed()
        self.store.create(
            inputs(upstream="abcd", project="other", source="ef"),
            attempt=1, previous_run_id=None,
        )
        catalog = read_spine42_v3_runtime_candidate_catalog_v2(self.root)
        self.assertEqual(1, len(catalog.candidates))
        self.assertEqual(1, len(catalog.skips))
        self.assertEqual("selection_required", catalog.selection["mode"])
        self.assertEqual("unresolved_inventory",
                         catalog.selection["reason_code"])

    def test_source_drift_blocks_family_and_creates_no_candidate(self):
        first = self.store.create(inputs(), attempt=1, previous_run_id=None)
        first = fail_retryable(self.store, first)
        second = self.store.create(
            inputs(source="5b"), attempt=2,
            previous_run_id=first.run_id,
        )
        complete(self.store, second)
        catalog = read_spine42_v3_runtime_candidate_catalog_v2(self.root)
        self.assertEqual((), catalog.candidates)
        self.assertEqual("source_drift", catalog.ambiguities[0]["code"])
        self.assertEqual("blocked", catalog.selection["mode"])

    def test_retry_branch_is_ambiguous_and_continuation_is_blocked(self):
        first = self.store.create(inputs(), attempt=1, previous_run_id=None)
        first = fail_retryable(self.store, first)
        second = self.store.create(
            inputs(), attempt=2, previous_run_id=first.run_id)
        complete(self.store, second)
        with tempfile.TemporaryDirectory() as temporary:
            other_root = Path(temporary)
            other = P10Spine42V3JobStoreV2(other_root)
            same_first = other.create(
                inputs(), attempt=1, previous_run_id=None)
            same_first = fail_retryable(other, same_first)
            branch = other.create(
                inputs(source="5b"), attempt=2,
                previous_run_id=same_first.run_id,
            )
            branch = complete(other, branch)
            shutil.copytree(
                other_root / "jobs" / NAMESPACE / branch.run_id,
                self.root / "jobs" / NAMESPACE / branch.run_id,
            )
        catalog = read_spine42_v3_runtime_candidate_catalog_v2(
            self.root, continuation_spine_run_id=second.run_id)
        self.assertEqual("duplicate_attempt", catalog.ambiguities[0]["code"])
        self.assertEqual("blocked", catalog.selection["mode"])
        self.assertEqual("continuation_ambiguous",
                         catalog.selection["reason_code"])
        self.assertIsNone(catalog.selection["recommended_candidate_id"])

    def test_invalid_run_suppresses_automatic_recommendation(self):
        self._completed()
        (self.root / "jobs" / NAMESPACE / sha("f")).mkdir()
        catalog = read_spine42_v3_runtime_candidate_catalog_v2(self.root)
        self.assertEqual(1, len(catalog.candidates))
        self.assertEqual("invalid_run", catalog.skips[0]["code"])
        self.assertEqual("selection_required", catalog.selection["mode"])
        continued = read_spine42_v3_runtime_candidate_catalog_v2(
            self.root, continuation_spine_run_id=sha("f"))
        self.assertEqual("blocked", continued.selection["mode"])
        self.assertEqual("continuation_invalid",
                         continued.selection["reason_code"])

    def test_mixed_type_tamper_is_path_free_zero_write_and_never_auto_selected(self):
        self._completed()
        document = request_document(inputs(), 1, None)
        document["dynamic_run_id"] = int("3" * 64)
        invalid_id = write_request_only(self.root, document)
        before = tree_snapshot(self.root)
        catalog = read_spine42_v3_runtime_candidate_catalog_v2(self.root)
        public = catalog.public_document()
        self.assertEqual(before, tree_snapshot(self.root))
        self.assertEqual("selection_required", catalog.selection["mode"])
        self.assertEqual(invalid_id, catalog.skips[0]["spine_run_id"])
        self.assertFalse(contains_path_key(public))
        self.assertNotIn(str(self.root), repr(public))

    def test_empty_inventory_has_no_implicit_selection(self):
        catalog = read_spine42_v3_runtime_candidate_catalog_v2(self.root)
        self.assertEqual("none", catalog.selection["mode"])
        self.assertEqual("no_candidates", catalog.selection["reason_code"])


if __name__ == "__main__":
    unittest.main()
