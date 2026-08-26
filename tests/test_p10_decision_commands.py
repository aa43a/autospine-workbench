"""Safe file-boundary tests for P10 idle-behavior decisions."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.idle_behavior_candidate_validation import (  # noqa: E402
    MAX_DOCUMENT_BYTES as MAX_CANDIDATE_BYTES,
    idle_behavior_candidates_sha256,
)
from autospine_workbench.idle_behavior_decision_validation import (  # noqa: E402
    MAX_DOCUMENT_BYTES as MAX_REVIEW_BYTES,
    idle_behavior_decision_sha256,
)
from autospine_workbench.p10_decision_commands import (  # noqa: E402
    P10DecisionCommandError,
    compile_idle_behavior_decision_command,
)
from tests.p10_decision_command_helpers import (  # noqa: E402
    candidate_document,
    review_input,
    write_json,
)
from tests.p9_v2_helpers import tree  # noqa: E402


class P10DecisionCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.candidates = candidate_document()
        self.review = review_input(self.candidates)
        self.candidate_path = write_json(
            self.root / "candidates.json", self.candidates
        )
        self.review_path = write_json(
            self.root / "review.json", self.review
        )

    def compile(self, candidates=None, review=None):
        return compile_idle_behavior_decision_command(
            self.candidate_path if candidates is None else candidates,
            self.review_path if review is None else review,
        )

    def test_success_is_deterministic_canonical_and_zero_write(self):
        before = tree(self.root)
        first = self.compile()
        second = self.compile()
        self.assertEqual(before, tree(self.root))
        self.assertEqual(first.document, second.document)
        self.assertEqual(first.input_paths, (
            self.candidate_path, self.review_path,
        ))
        self.assertEqual(
            idle_behavior_candidates_sha256(self.candidates),
            first.idle_behavior_candidates_sha256,
        )
        self.assertEqual(
            idle_behavior_decision_sha256(first.document),
            first.idle_behavior_decision_sha256,
        )

    def test_review_input_top_level_fields_are_exact(self):
        cases = (
            {"review": self.review["review"]},
            {**self.review, "ignored": True},
        )
        for index, value in enumerate(cases):
            path = write_json(self.root / f"fields-{index}.json", value)
            before = tree(self.root)
            with self.subTest(value=value), self.assertRaisesRegex(
                P10DecisionCommandError, "fields are unsupported"
            ):
                self.compile(review=path)
            self.assertEqual(before, tree(self.root))

    def test_duplicate_keys_and_nonfinite_numbers_fail_for_both_files(self):
        bad_candidate = self.root / "duplicate-candidates.json"
        bad_candidate.write_text(
            '{"format":"a","format":"b"}', encoding="utf-8"
        )
        nan_candidate = self.root / "nan-candidates.json"
        nan_candidate.write_text('{"value":NaN}', encoding="utf-8")
        bad_review = self.root / "duplicate-review.json"
        bad_review.write_text(
            '{"review":{},"review":{},"decisions":[]}',
            encoding="utf-8",
        )
        nan_review = self.root / "nan-review.json"
        nan_review.write_text(
            '{"review":{"revision":NaN},"decisions":[]}',
            encoding="utf-8",
        )
        for candidates, review in (
            (bad_candidate, self.review_path),
            (nan_candidate, self.review_path),
            (self.candidate_path, bad_review),
            (self.candidate_path, nan_review),
        ):
            with self.subTest(path=candidates), self.assertRaises(
                P10DecisionCommandError
            ):
                self.compile(candidates=candidates, review=review)

    def test_directory_inputs_are_not_real_files(self):
        directory = self.root / "directory-input"
        directory.mkdir()
        for candidates, review in (
            (directory, self.review_path),
            (self.candidate_path, directory),
        ):
            with self.subTest(path=directory), self.assertRaisesRegex(
                P10DecisionCommandError, "real regular file"
            ):
                self.compile(candidates=candidates, review=review)

    def test_symlink_aliases_are_rejected_when_supported(self):
        candidate_alias = self.root / "candidate-alias.json"
        review_alias = self.root / "review-alias.json"
        try:
            candidate_alias.symlink_to(self.candidate_path)
            review_alias.symlink_to(self.review_path)
        except OSError as exc:
            self.skipTest(f"file symlinks unavailable: {exc}")
        for candidates, review in (
            (candidate_alias, self.review_path),
            (self.candidate_path, review_alias),
        ):
            with self.subTest(path=candidates), self.assertRaisesRegex(
                P10DecisionCommandError, "real regular file"
            ):
                self.compile(candidates=candidates, review=review)

    def test_each_input_has_an_independent_64_mib_limit(self):
        large_candidate = self.root / "large-candidates.json"
        large_review = self.root / "large-review.json"
        with large_candidate.open("wb") as handle:
            handle.truncate(MAX_CANDIDATE_BYTES + 1)
        with large_review.open("wb") as handle:
            handle.truncate(MAX_REVIEW_BYTES + 1)
        for candidates, review in (
            (large_candidate, self.review_path),
            (self.candidate_path, large_review),
        ):
            with self.subTest(path=candidates), self.assertRaisesRegex(
                P10DecisionCommandError, "byte limit"
            ):
                self.compile(candidates=candidates, review=review)

    def test_builder_propagates_incomplete_and_stale_candidate_choices(self):
        incomplete = deepcopy(self.review)
        incomplete["decisions"] = []
        stale = deepcopy(self.review)
        stale["decisions"][0]["candidate_id"] = "body-sway-" + "f" * 64
        for name, value in (("incomplete", incomplete), ("stale", stale)):
            path = write_json(self.root / f"{name}.json", value)
            with self.subTest(name=name), self.assertRaisesRegex(
                P10DecisionCommandError, "not exhaustive"
            ):
                self.compile(review=path)


if __name__ == "__main__":
    unittest.main()
