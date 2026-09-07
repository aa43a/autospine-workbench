"""Semantic acceptance requires complete human declarations and exact sources."""
from copy import deepcopy
import unittest

from tests.test_benchmark_semantic_view import candidate
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.benchmark.semantic_draft import build_semantic_draft
from autospine_workbench.benchmark.semantic_decision import (
    CHECKS, REQUEST_SCHEMA, build_semantic_decision, validate_semantic_decision)


def request(value, draft, action="accept"):
    return {"schema": REQUEST_SCHEMA, "authority": "none", "candidate_sha256": canonical_sha256(value),
            "draft_sha256": canonical_sha256(draft), "reviewer": "fixture reviewer", "action": action,
            "reason": "test-only declaration", "checks": dict.fromkeys(CHECKS, True)}


class SemanticDecisionTests(unittest.TestCase):
    def setUp(self):
        self.value = candidate()
        self.draft = build_semantic_draft(self.value)
        self.draft["records"][0].update(semantic="body.arm.lower", side="left", disposition="include")

    def test_accepted_exact_replay_without_input_mutation(self):
        before = deepcopy((self.value, self.draft))
        req = request(self.value, self.draft)
        result = build_semantic_decision(self.value, self.draft, req)
        self.assertEqual(result["semantic_status"], "reviewed_accepted")
        self.assertEqual(result["authority"], "none")
        self.assertEqual(result["scope"], "benchmark_semantics_only")
        self.assertEqual(validate_semantic_decision(self.value, self.draft, req, result), result)
        self.assertEqual((self.value, self.draft), before)
        for field in result:
            changed = deepcopy(result); changed[field] = "tampered"
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_semantic_decision(self.value, self.draft, req, changed)

    def test_acceptance_blocks_incomplete_layers(self):
        for change in ({"semantic": None}, {"side": "unknown"}, {"disposition": "undecided"},
                       {"disposition": "exclude", "notes": "  "}):
            draft = deepcopy(self.draft); draft["records"][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                build_semantic_decision(self.value, draft, request(self.value, draft))

    def test_empty_layer_can_only_be_excluded_with_reason(self):
        self.value["layers"][0]["observed"]["empty"] = True
        self.draft["candidate_sha256"] = canonical_sha256(self.value)
        with self.assertRaisesRegex(ValueError, "empty_layer"):
            build_semantic_decision(self.value, self.draft, request(self.value, self.draft))
        self.draft["records"][0].update(disposition="exclude", notes="Empty source layer")
        self.assertEqual(build_semantic_decision(self.value, self.draft, request(self.value, self.draft))
                         ["semantic_status"], "reviewed_accepted")

    def test_rejection_allows_unfinished_review(self):
        draft = build_semantic_draft(self.value); req = request(self.value, draft, "reject")
        req["checks"] = dict.fromkeys(CHECKS, False)
        self.assertEqual(build_semantic_decision(self.value, draft, req)["semantic_status"], "reviewed_rejected")

    def test_stale_or_invalid_requests_fail_closed(self):
        good = request(self.value, self.draft)
        invalid = [{**good, "draft_sha256": "0" * 64}, {**good, "candidate_sha256": "0" * 64},
                   {**good, "reviewer": " "}, {**good, "reason": "\u200b"},
                   {**good, "authority": "production"}, {**good, "action": "auto"},
                   {**good, "checks": dict.fromkeys(CHECKS, 1)},
                   {**good, "checks": dict.fromkeys(CHECKS, False)}, {**good, "extra": True}]
        for req in invalid:
            with self.subTest(req=req), self.assertRaises(ValueError):
                build_semantic_decision(self.value, self.draft, req)


if __name__ == "__main__":
    unittest.main()
