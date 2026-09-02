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
from autospine_workbench.spine42_v3_runtime_candidate_contract_v2 import (
    Spine42V3RuntimeCandidateContractV2Error,
    Spine42V3RuntimeCandidateV2,
)
from tests.p10_spine42_v3_runtime_candidate_support import (
    complete, contains_path_key, inputs, sha,
)


class Spine42V3RuntimeCandidateContractV2Tests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = P10Spine42V3JobStoreV2(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def _row(self, **completion):
        row = self.store.create(inputs(), attempt=1, previous_run_id=None)
        return complete(self.store, row, **completion)

    def test_candidate_binds_completion_upstreams_output_and_head(self):
        row = self._row()
        candidate = Spine42V3RuntimeCandidateV2.from_completed_head(row)
        document = candidate.public_document()
        completion = document["completion"]
        self.assertEqual(row.run_id, completion["spine_run_id"])
        self.assertEqual(row.head_sha256,
                         completion["spine_head_event_sha256"])
        self.assertEqual({
            "job_id": sha("1"), "safety_run_id": sha("2"),
            "dynamic_run_id": sha("3"), "motion_run_id": sha("4"),
        }, completion["upstream"])
        self.assertEqual(row.events[-1]["result"], completion["output"])
        self.assertNotEqual(candidate.candidate_id, candidate.entry_sha256)
        self.assertEqual("completed", document["current_head"]["status"])
        self.assertFalse(document["runner_execution_authorized"])
        self.assertFalse(document["publication_authorized"])
        self.assertFalse(contains_path_key(document))
        self.assertNotIn(str(self.root), repr(document))
        self.assertEqual(
            candidate,
            Spine42V3RuntimeCandidateV2.from_document(document),
        )

    def test_output_or_seal_tampering_is_rejected(self):
        candidate = Spine42V3RuntimeCandidateV2.from_completed_head(
            self._row())
        for mutation in (
            "output", "candidate", "entry", "format_version",
            "head_attempt",
        ):
            document = candidate.document
            if mutation == "output":
                document["completion"]["output"]["bundle_sha256"] = sha("b")
            elif mutation == "candidate":
                document["candidate_id"] = sha("c")
            elif mutation == "entry":
                document["entry_sha256"] = sha("d")
            elif mutation == "format_version":
                document["format_version"] = 2.0
            else:
                document["current_head"]["attempt"] = 1.0
            with self.subTest(mutation=mutation), self.assertRaises(
                Spine42V3RuntimeCandidateContractV2Error
            ):
                Spine42V3RuntimeCandidateV2.from_document(document)

    def test_current_head_is_a_separate_exact_eligibility_seal(self):
        candidate = Spine42V3RuntimeCandidateV2.from_completed_head(
            self._row())
        document = candidate.document
        original_candidate_id = document["candidate_id"]
        document["current_head"]["spine_head_event_sha256"] = sha("f")
        self.assertEqual(original_candidate_id, document["candidate_id"])
        with self.assertRaises(Spine42V3RuntimeCandidateContractV2Error):
            Spine42V3RuntimeCandidateV2.from_document(document)

    def test_cross_wired_result_project_is_not_a_candidate(self):
        row = self._row(project="other")
        with self.assertRaises(Spine42V3RuntimeCandidateContractV2Error):
            Spine42V3RuntimeCandidateV2.from_completed_head(row)

    def test_noncompleted_run_is_not_a_candidate(self):
        row = self.store.create(inputs(), attempt=1, previous_run_id=None)
        with self.assertRaises(Spine42V3RuntimeCandidateContractV2Error):
            Spine42V3RuntimeCandidateV2.from_completed_head(row)


if __name__ == "__main__":
    unittest.main()
