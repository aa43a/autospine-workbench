"""Live HTTP contract tests for exact P10.5b seam-anchor review."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.seam_anchor_review_application import (  # noqa: E402
    SeamAnchorReviewApplicationError,
)
from autospine_workbench.seam_anchor_review_profile import (  # noqa: E402
    MAX_SEAM_ANCHOR_REVIEW_DOCUMENT_BYTES,
)
from tests.p9_v2_helpers import tree  # noqa: E402
from tests.seam_anchor_review_http_helpers import (  # noqa: E402
    SeamAnchorReviewHttpFixture,
)


class SeamAnchorReviewHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = SeamAnchorReviewHttpFixture()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.fixture.close()

    def setUp(self) -> None:
        self.fixture.reset_reviews()

    def test_candidate_get_is_zero_write_path_free_and_head_exact(self):
        before = tree(self.fixture.persisted.state)
        status, headers, value = self.fixture.json_request(
            "GET", f"{self.fixture.base}/candidate"
        )
        self.assertEqual(200, status)
        self.assertEqual(
            "same-origin", headers["cross-origin-resource-policy"]
        )
        self.assertEqual(64, len(value["candidate_sha256"]))
        self.assertEqual("manual_review_required", value["candidate"][
            "summary"
        ]["status"])
        self.assertEqual([], value["attachment_images"])
        encoded = json.dumps(value, ensure_ascii=False)
        self.assertNotIn(str(self.fixture.root), encoded)
        self.assertNotIn('"path"', encoded)
        self.assertEqual(before, tree(self.fixture.persisted.state))

        get_status, get_headers, raw = self.fixture.request(
            "GET", f"{self.fixture.base}/candidate"
        )
        head_status, head_headers, head_raw = self.fixture.request(
            "HEAD", f"{self.fixture.base}/candidate"
        )
        self.assertEqual((200, 200), (get_status, head_status))
        self.assertEqual(
            get_headers["content-length"], head_headers["content-length"]
        )
        self.assertTrue(raw)
        self.assertEqual(b"", head_raw)

    def test_post_history_exact_retry_and_conflict(self):
        candidate_sha, candidate = self.fixture.prepare()
        submission = self.fixture.submission(candidate_sha, candidate)
        endpoint = f"{self.fixture.base}/candidates/{candidate_sha}/decisions"
        headers = self.fixture.mutation_headers()

        status, _, created = self.fixture.json_request(
            "POST", endpoint, submission, headers
        )
        self.assertEqual(201, status)
        self.assertFalse(created["reused"])
        self.assertEqual("blocked", created["release_gate"]["status"])
        self.assertEqual(6, created["summary"]["relationship_count"])
        status, _, retried = self.fixture.json_request(
            "POST", endpoint, submission, headers
        )
        self.assertEqual(200, status)
        self.assertTrue(retried["reused"])
        self.assertEqual(
            created["decision_sha256"], retried["decision_sha256"]
        )

        history_path = f"{self.fixture.base}/candidates/{candidate_sha}/history"
        status, _, history = self.fixture.json_request("GET", history_path)
        self.assertEqual(200, status)
        self.assertEqual(1, history["current_revision"])
        self.assertEqual(
            created["decision_sha256"], history["head_decision_sha256"]
        )
        exact_path = (
            f"{history_path}/1/{created['decision_sha256']}"
        )
        status, _, exact = self.fixture.json_request("GET", exact_path)
        self.assertEqual(200, status)
        self.assertEqual(1, exact["revision"])
        self.assertEqual(1, exact["decision"]["review"]["revision"])

        stale = deepcopy(submission)
        stale["review"]["notes"] = "different stale write"
        status, _, conflict = self.fixture.json_request(
            "POST", endpoint, stale, headers
        )
        self.assertEqual(409, status)
        self.assertEqual(
            "seam_anchor_review_revision_conflict", conflict["error"]
        )
        self.assertEqual((1, 1), (
            conflict["requested_revision"], conflict["current_revision"]
        ))
        self.assertEqual(
            created["decision_sha256"],
            conflict["current_head_decision_sha256"],
        )

    def test_post_requires_origin_intent_and_strict_bounded_json(self):
        candidate_sha, candidate = self.fixture.prepare()
        endpoint = f"{self.fixture.base}/candidates/{candidate_sha}/decisions"
        submission = self.fixture.submission(candidate_sha, candidate)
        cases = (
            ({"Origin": f"http://{self.fixture.host}:{self.fixture.port}"},
             "forbidden_intent"),
            (self.fixture.mutation_headers(
                Origin=f"http://{self.fixture.host}:{self.fixture.port + 1}"
            ), "forbidden_origin"),
        )
        for headers, expected in cases:
            with self.subTest(expected=expected):
                status, response_headers, value = self.fixture.json_request(
                    "POST", endpoint, submission, headers
                )
                self.assertEqual(403, status)
                self.assertEqual(expected, value["error"])
                if expected == "forbidden_origin":
                    self.assertNotIn(
                        "access-control-allow-origin", response_headers
                    )

        invalid_values = (
            b'{"base_revision":0,"base_revision":0}',
            b'{"base_revision":NaN}',
            b'{"base_revision":Infinity}',
        )
        for raw in invalid_values:
            with self.subTest(raw=raw):
                status, _, value = self.fixture.json_request(
                    "POST", endpoint, raw, self.fixture.mutation_headers()
                )
                self.assertEqual(400, status)
                self.assertEqual("invalid_json", value["error"])

        oversized_headers = self.fixture.mutation_headers()
        oversized_headers.update({
            "Content-Type": "application/json",
            "Content-Length": str(
                MAX_SEAM_ANCHOR_REVIEW_DOCUMENT_BYTES + 1
            ),
        })
        status, _, value = self.fixture.json_request(
            "POST", endpoint, headers=oversized_headers
        )
        self.assertEqual(413, status)
        self.assertEqual("request_too_large", value["error"])

        transfer_headers = self.fixture.mutation_headers()
        transfer_headers.update({
            "Content-Type": "application/json",
            "Transfer-Encoding": "chunked",
        })
        status, _, value = self.fixture.json_request(
            "POST", endpoint, b"0\r\n\r\n", transfer_headers
        )
        self.assertEqual(400, status)
        self.assertEqual("unsupported_transfer_encoding", value["error"])

    def test_candidate_and_evidence_identities_cannot_crosswire(self):
        candidate_sha, candidate = self.fixture.prepare()
        endpoint = f"{self.fixture.base}/candidates/{candidate_sha}/decisions"
        submission = self.fixture.submission(candidate_sha, candidate)
        headers = self.fixture.mutation_headers()

        mismatched = deepcopy(submission)
        current = mismatched["decisions"][0][
            "relationship_evidence_sha256"
        ]
        mismatched["decisions"][0]["relationship_evidence_sha256"] = (
            "a" * 64 if current != "a" * 64 else "b" * 64
        )
        status, _, value = self.fixture.json_request(
            "POST", endpoint, mismatched, headers
        )
        self.assertEqual(400, status)
        self.assertEqual("invalid_seam_anchor_review_submission", value["error"])

        wrong = "a" * 64 if candidate_sha != "a" * 64 else "b" * 64
        status, _, value = self.fixture.json_request(
            "POST", endpoint.replace(candidate_sha, wrong), submission, headers
        )
        self.assertEqual(400, status)
        self.assertEqual("invalid_seam_anchor_review_submission", value["error"])
        status, _, value = self.fixture.json_request(
            "GET", f"{self.fixture.base}/candidates/{wrong}/history"
        )
        self.assertEqual(404, status)
        self.assertEqual("seam_anchor_review_not_found", value["error"])

        bad_image = (
            f"{self.fixture.base}/candidates/{candidate_sha}/options/"
            f"not-an-option/attachments/not-an-attachment/images/{wrong}"
        )
        status, _, value = self.fixture.json_request("GET", bad_image)
        self.assertEqual(404, status)
        self.assertEqual("seam_anchor_review_not_found", value["error"])

    def test_invalid_addresses_and_internal_failures_are_sanitized(self):
        candidate_sha, _ = self.fixture.prepare()
        status, _, value = self.fixture.json_request(
            "GET", f"{self.fixture.base}/candidates/not-a-sha/history"
        )
        self.assertEqual(400, status)
        self.assertEqual("invalid_seam_anchor_review_address", value["error"])

        private = r"C:\Users\private\source.png"
        with patch(
            "autospine_workbench.seam_anchor_review_routes."
            "SeamAnchorReviewApplication.prepare",
            side_effect=SeamAnchorReviewApplicationError(private),
        ):
            status, headers, raw = self.fixture.request(
                "GET", f"{self.fixture.base}/candidate"
            )
        self.assertEqual(500, status)
        self.assertEqual(
            "same-origin", headers["cross-origin-resource-policy"]
        )
        self.assertNotIn(private, raw.decode("utf-8"))
        self.assertEqual("seam_anchor_review_error", json.loads(raw)["error"])

        wrong = "a" * 64 if candidate_sha != "a" * 64 else "b" * 64
        status, _, value = self.fixture.json_request(
            "GET", self.fixture.base.replace(
                self.fixture.persisted.mesh.bundle_sha256, wrong
            ) + "/candidate"
        )
        self.assertEqual(500, status)
        self.assertEqual("seam_anchor_review_error", value["error"])


if __name__ == "__main__":
    unittest.main()
