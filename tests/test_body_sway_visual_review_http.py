"""HTTP contract tests for exact P10.3c human visual review."""

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

from autospine_workbench.body_sway_visual_review_application import (  # noqa: E402
    BodySwayVisualReviewApplicationError,
)
from tests.body_sway_visual_review_http_helpers import (  # noqa: E402
    VisualReviewHttpFixture,
    complete_tree,
)


class BodySwayVisualReviewHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = VisualReviewHttpFixture()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.fixture.close()

    def setUp(self) -> None:
        self.fixture.reset_reviews()

    def test_candidate_get_is_zero_write_path_free_and_exact(self) -> None:
        before = complete_tree(self.fixture.visual.state_root)
        status, headers, value = self.fixture.json_request(
            "GET", f"{self.fixture.base}/candidate"
        )
        self.assertEqual(200, status)
        self.assertEqual("same-origin", headers[
            "cross-origin-resource-policy"
        ])
        self.assertEqual(64, len(value["candidate_sha256"]))
        self.assertEqual("candidate_only", value["candidate"]["status"])
        for row in value["candidate"]["cases"]:
            self.assertNotIn("path", row["image"])
            self.assertEqual(64, len(row["image"]["png_sha256"]))
        status, _, value = self.fixture.json_request("GET", self.fixture.base)
        self.assertEqual(404, status)
        self.assertEqual("visual_review_not_found", value["error"])
        self.assertEqual(before, complete_tree(self.fixture.visual.state_root))

    def test_png_and_head_use_authoritative_identity_and_metadata(self) -> None:
        candidate_sha, candidate = self.fixture.prepare()
        row = candidate["cases"][0]
        image_path = (
            f"{self.fixture.base}/candidates/{candidate_sha}/cases/"
            f"{row['case_id']}/image/{row['image']['png_sha256']}"
        )
        status, headers, raw = self.fixture.request("GET", image_path)
        self.assertEqual(200, status)
        self.assertEqual("image/png", headers["content-type"])
        self.assertEqual(
            f'"{row["image"]["png_sha256"]}"', headers["etag"]
        )
        self.assertEqual(row["image"]["size_bytes"], len(raw))
        status, head_headers, raw = self.fixture.request("HEAD", image_path)
        self.assertEqual(200, status)
        self.assertEqual(str(row["image"]["size_bytes"]),
                         head_headers["content-length"])
        self.assertEqual(b"", raw)

        status, get_headers, raw = self.fixture.request(
            "GET", f"{self.fixture.base}/candidate"
        )
        status_head, head_headers, head_raw = self.fixture.request(
            "HEAD", f"{self.fixture.base}/candidate"
        )
        self.assertEqual((status, status_head), (200, 200))
        self.assertEqual(get_headers["content-length"],
                         head_headers["content-length"])
        self.assertTrue(raw)
        self.assertEqual(b"", head_raw)

    def test_history_exact_revision_new_retry_and_conflict(self) -> None:
        candidate_sha, candidate = self.fixture.prepare()
        submission = self.fixture.submission(candidate_sha, candidate)
        endpoint = (
            f"{self.fixture.base}/candidates/{candidate_sha}/decisions"
        )
        headers = self.fixture.mutation_headers()
        status, _, created = self.fixture.json_request(
            "PUT", endpoint, submission, headers
        )
        self.assertEqual(201, status)
        self.assertFalse(created["reused"])
        self.assertEqual("blocked", created["release_gate"]["status"])
        status, _, retried = self.fixture.json_request(
            "PUT", endpoint, submission, headers
        )
        self.assertEqual(200, status)
        self.assertTrue(retried["reused"])
        self.assertEqual(created["decision_sha256"],
                         retried["decision_sha256"])

        history_path = f"{self.fixture.base}/candidates/{candidate_sha}/history"
        status, _, history = self.fixture.json_request("GET", history_path)
        self.assertEqual(200, status)
        self.assertEqual(1, history["current_revision"])
        self.assertEqual(created["decision_sha256"],
                         history["head_decision_sha256"])
        self.assertEqual([1], [row["revision"] for row in history["items"]])

        exact_path = (
            f"{history_path}/1/{created['decision_sha256']}"
        )
        status, _, exact = self.fixture.json_request("GET", exact_path)
        self.assertEqual(200, status)
        self.assertEqual(created["decision_sha256"],
                         exact["decision_sha256"])
        self.assertEqual(1, exact["decision"]["review"]["revision"])

        stale = deepcopy(submission)
        stale["review"]["notes"] = "different stale write"
        status, _, conflict = self.fixture.json_request(
            "PUT", endpoint, stale, headers
        )
        self.assertEqual(409, status)
        self.assertEqual(
            "body_sway_visual_review_revision_conflict", conflict["error"]
        )
        self.assertEqual((1, 1), (
            conflict["requested_revision"], conflict["current_revision"]
        ))
        self.assertEqual(created["decision_sha256"],
                         conflict["current_head_decision_sha256"])

    def test_mutation_requires_exact_origin_intent_and_strict_json(self) -> None:
        candidate_sha, candidate = self.fixture.prepare()
        endpoint = f"{self.fixture.base}/candidates/{candidate_sha}/decisions"
        submission = self.fixture.submission(candidate_sha, candidate)
        cases = [
            ({"Origin": f"http://{self.fixture.host}:{self.fixture.port}"},
             "forbidden_intent"),
            (self.fixture.mutation_headers(
                Origin=f"http://{self.fixture.host}:{self.fixture.port + 1}"
            ), "forbidden_origin"),
        ]
        for headers, expected in cases:
            with self.subTest(expected=expected):
                status, response_headers, value = self.fixture.json_request(
                    "PUT", endpoint, submission, headers
                )
                self.assertEqual(403, status)
                self.assertEqual(expected, value["error"])
                if expected == "forbidden_origin":
                    self.assertNotIn("access-control-allow-origin",
                                     response_headers)

        duplicate = b'{"base_revision":0,"base_revision":0}'
        status, _, value = self.fixture.json_request(
            "PUT", endpoint, duplicate, self.fixture.mutation_headers()
        )
        self.assertEqual(400, status)
        self.assertEqual("invalid_json", value["error"])

        mismatched = deepcopy(submission)
        current = mismatched["decisions"][0]["evidence_sha256"]
        mismatched["decisions"][0]["evidence_sha256"] = \
            "a" * 64 if current != "a" * 64 else "b" * 64
        status, _, value = self.fixture.json_request(
            "PUT", endpoint, mismatched, self.fixture.mutation_headers()
        )
        self.assertEqual(400, status)
        self.assertEqual("invalid_visual_review_submission", value["error"])

        wrong_endpoint = endpoint.replace(candidate_sha, "a" * 64)
        status, _, value = self.fixture.json_request(
            "PUT", wrong_endpoint, submission, self.fixture.mutation_headers()
        )
        self.assertEqual(400, status)
        self.assertEqual("invalid_visual_review_submission", value["error"])

        wrong_candidate = deepcopy(submission)
        wrong_candidate["candidate_sha256"] = "a" * 64
        status, _, value = self.fixture.json_request(
            "PUT", endpoint, wrong_candidate, self.fixture.mutation_headers()
        )
        self.assertEqual(400, status)
        self.assertEqual("invalid_visual_review_submission", value["error"])

    def test_visual_options_never_reflects_cross_port_origin(self) -> None:
        candidate_sha, _ = self.fixture.prepare()
        endpoint = f"{self.fixture.base}/candidates/{candidate_sha}/decisions"
        same = self.fixture.mutation_headers()
        status, headers, raw = self.fixture.request("OPTIONS", endpoint,
                                                    headers=same)
        self.assertEqual(204, status)
        self.assertEqual(same["Origin"], headers["access-control-allow-origin"])
        self.assertEqual("PUT, OPTIONS", headers["allow"])
        self.assertIn("X-Autospine-Intent",
                      headers["access-control-allow-headers"])
        self.assertEqual(b"", raw)

        foreign = self.fixture.mutation_headers(
            Origin=f"http://{self.fixture.host}:{self.fixture.port + 1}"
        )
        status, headers, _ = self.fixture.request(
            "OPTIONS", endpoint, headers=foreign
        )
        self.assertEqual(204, status)
        self.assertNotIn("access-control-allow-origin", headers)
        status, headers, _ = self.fixture.request(
            "GET", f"{self.fixture.base}/candidate", headers=foreign
        )
        self.assertEqual(200, status)
        self.assertNotIn("access-control-allow-origin", headers)
        self.assertEqual("same-origin", headers[
            "cross-origin-resource-policy"
        ])

    def test_wrong_sha_revision_and_capture_address_are_exact_404s(self) -> None:
        candidate_sha, candidate = self.fixture.prepare()
        row = candidate["cases"][0]
        wrong = "a" * 64 if candidate_sha != "a" * 64 else "b" * 64
        paths = [
            f"{self.fixture.base}/candidates/{wrong}/history",
            (
                f"{self.fixture.base}/candidates/{wrong}/cases/"
                f"{row['case_id']}/image/{row['image']['png_sha256']}"
            ),
            f"{self.fixture.base}/candidates/{candidate_sha}/history/1/{wrong}",
            self.fixture.base.replace(
                self.fixture.bundle_sha, wrong
            ) + "/candidate",
        ]
        for path in paths:
            with self.subTest(path=path):
                status, _, value = self.fixture.json_request("GET", path)
                self.assertEqual(404, status)
                self.assertEqual("visual_review_not_found", value["error"])

        status, _, value = self.fixture.json_request(
            "GET", self.fixture.base.replace(
                self.fixture.artifact_sha, wrong
            ) + "/candidate"
        )
        self.assertEqual(500, status)
        self.assertEqual("visual_review_error", value["error"])

        status, _, value = self.fixture.json_request(
            "GET", f"{self.fixture.base}/candidates/not-a-sha/history"
        )
        self.assertEqual(400, status)
        self.assertEqual("invalid_visual_review_address", value["error"])

    def test_internal_failures_are_sanitized_and_keep_visual_headers(self) -> None:
        private = r"C:\Users\private\capture.png"
        with patch(
            "autospine_workbench.body_sway_visual_review_routes."
            "BodySwayVisualReviewApplication.prepare",
            side_effect=BodySwayVisualReviewApplicationError(private),
        ):
            status, headers, raw = self.fixture.request(
                "GET", f"{self.fixture.base}/candidate"
            )
        self.assertEqual(500, status)
        self.assertEqual("same-origin", headers[
            "cross-origin-resource-policy"
        ])
        self.assertNotIn(private, raw.decode("utf-8"))
        self.assertEqual("visual_review_error", json.loads(raw)["error"])

    def test_review_page_has_dedicated_csp_without_changing_index(self) -> None:
        for page in ("body-sway-review.html", "idle-behavior-review.html"):
            with self.subTest(page=page):
                status, headers, raw = self.fixture.request(
                    "GET", f"/{page}"
                )
                self.assertEqual(200, status)
                self.assertTrue(raw)
                policy = headers["content-security-policy"]
                for directive in (
                    "default-src 'self'", "object-src 'none'",
                    "base-uri 'none'", "frame-ancestors 'none'",
                    "connect-src 'self'", "img-src 'self' data:",
                    "script-src 'self'", "style-src 'self'",
                ):
                    self.assertIn(directive, policy)
        status, headers, raw = self.fixture.request("GET", "/")
        self.assertEqual(200, status)
        self.assertTrue(raw)
        self.assertNotIn("content-security-policy", headers)

    def test_workflow_hub_has_the_same_locked_down_csp(self) -> None:
        status, headers, raw = self.fixture.request(
            "GET", "/workflow-hub.html"
        )
        self.assertEqual(200, status)
        self.assertTrue(raw)
        policy = headers["content-security-policy"]
        self.assertIn("default-src 'self'", policy)
        self.assertIn("script-src 'self'", policy)
        self.assertIn("object-src 'none'", policy)

        resources = {
            "/document-viewer.css": "text/css",
            "/modules/document-viewer.js": "text/javascript",
            "/motion-policy-review.html": "text/html",
            "/motion-policy-review.css": "text/css",
            "/motion-policy-visual-review.css": "text/css",
            "/motion-policy-auto.css": "text/css",
            "/modules/motion-policy-review-app.js": "text/javascript",
            "/modules/motion-policy-decision-controller.js": "text/javascript",
            "/modules/motion-policy-assist-controller.js": "text/javascript",
            "/modules/motion-policy-assist-model.js": "text/javascript",
            "/modules/motion-policy-auto-api.js": "text/javascript",
            "/modules/motion-policy-auto-controller.js": "text/javascript",
            "/modules/motion-policy-evidence-model.js": "text/javascript",
            "/modules/motion-policy-evidence-view.js": "text/javascript",
            "/modules/motion-policy-batch-model.js": "text/javascript",
            "/modules/motion-policy-batch-controller.js": "text/javascript",
            "/modules/motion-policy-batch-view.js": "text/javascript",
            "/workflow-hub.css": "text/css",
            "/workflow-catalog.json": "application/json",
            "/modules/workflow-hub-app.js": "text/javascript",
            "/modules/workflow-hub-model.js": "text/javascript",
            "/modules/workflow-hub-view.js": "text/javascript",
        }
        for path, content_type in resources.items():
            with self.subTest(path=path):
                status, headers, raw = self.fixture.request("GET", path)
                self.assertEqual(200, status)
                self.assertIn(content_type, headers["content-type"])
                self.assertTrue(raw)

        status, headers, raw = self.fixture.request(
            "GET", "/document-viewer.html?doc=docs/architecture.md"
        )
        self.assertEqual(200, status)
        self.assertIn("default-src 'self'", headers["content-security-policy"])
        self.assertTrue(raw)

    def test_documentation_is_available_read_only_under_docs(self) -> None:
        status, headers, raw = self.fixture.request(
            "GET", "/docs/architecture.md"
        )
        self.assertEqual(200, status)
        self.assertIn("text/markdown", headers["content-type"])
        self.assertIn(b"#", raw)

        status, headers, raw = self.fixture.request(
            "GET", "/docs/pilots/kimodo-wave-left-v1.md"
        )
        self.assertEqual(200, status)
        self.assertIn("text/markdown", headers["content-type"])
        self.assertIn(b"# Kimodo `wave-left-v1` Pilot Handoff", raw)

        status, _, raw = self.fixture.request(
            "GET", "/docs/../README.md"
        )
        self.assertIn(status, {400, 404})
        self.assertNotIn(b"AutoSpine Workbench", raw)


if __name__ == "__main__":
    unittest.main()
