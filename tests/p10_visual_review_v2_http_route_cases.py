"""Reusable live-HTTP cases for P10.3c v2 route boundaries."""

import json

from autospine_workbench.body_sway_visual_review_errors_v2 import (
    BodySwayVisualReviewRevisionV2Conflict,
)


class P10VisualReviewV2RouteHttpCases:
    """Exercise errors, method routing, and page security headers."""

    def test_wrong_intent_is_zero_replay_and_v1_intent_is_rejected(self):
        endpoint = f"{self.base}/candidates/{self.candidate_sha}/decisions"
        for intent in ("body-sway-visual-review",
                       "p10-official-runtime-capture-v2"):
            with self.subTest(intent=intent):
                status, _, value = self.json_request(
                    "PUT", endpoint,
                    {"candidate_sha256": self.candidate_sha},
                    self.mutation_headers(intent),
                )
                self.assertEqual(403, status)
                self.assertEqual("forbidden_intent", value["error"])
        self.manager.get.assert_not_called()
        self.service.submit.assert_not_called()

    def test_incomplete_or_changed_source_returns_actionable_409(self):
        self.manager.get.return_value = {
            **self.snapshot, "status": "capturing",
            "terminal": False, "addresses": None,
        }
        status, _, value = self.json_request("GET", f"{self.base}/candidate")
        self.assertEqual(409, status)
        self.assertEqual("runtime_capture_job_not_completed", value["error"])

        self.manager.get.return_value = self.snapshot
        self.preview.temporary_preview_v2_sha256 = "0" * 64
        status, _, value = self.json_request("GET", f"{self.base}/candidate")
        self.assertEqual(409, status)
        self.assertEqual("visual_review_v2_source_changed", value["error"])

    def test_revision_conflict_is_409_and_does_not_leak_private_error(self):
        private = r"C:\Users\private\decision.json"
        self.service.submit.side_effect = BodySwayVisualReviewRevisionV2Conflict(
            private, requested_revision=1, current_revision=2,
            requested_head=None, current_head=self.decision_sha,
        )
        endpoint = f"{self.base}/candidates/{self.candidate_sha}/decisions"
        status, _, value = self.json_request(
            "PUT", endpoint, {"candidate_sha256": self.candidate_sha},
            self.mutation_headers(),
        )
        self.assertEqual(409, status)
        self.assertEqual("body_sway_visual_review_v2_revision_conflict",
                         value["error"])
        self.assertNotIn(private, json.dumps(value))

    def test_options_wrong_methods_and_page_csp_are_version_aware(self):
        endpoint = f"{self.base}/candidates/{self.candidate_sha}/decisions"
        status, headers, raw = self.request(
            "OPTIONS", endpoint, headers=self.mutation_headers(),
        )
        self.assertEqual((204, b""), (status, raw))
        self.assertEqual("PUT, OPTIONS", headers["allow"])
        for method in ("POST", "PATCH", "DELETE"):
            with self.subTest(method=method):
                status, headers, value = self.json_request(method, endpoint, {})
                self.assertEqual(405, status)
                self.assertEqual("PUT, OPTIONS", headers["allow"])
                self.assertEqual("method_not_allowed", value["error"])

        status, headers, raw = self.request("GET", "/body-sway-review-v2.html")
        self.assertEqual(200, status)
        self.assertTrue(raw)
        self.assertIn("default-src 'self'", headers["content-security-policy"])


__all__ = ["P10VisualReviewV2RouteHttpCases"]
