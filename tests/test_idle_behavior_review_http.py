"""Live loopback route/security tests for P10.1 assisted review."""

from __future__ import annotations

import http.client
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

from autospine_workbench.idle_behavior_review_application import (
    IdleBehaviorReviewApplicationUnavailable,
)
from autospine_workbench.idle_behavior_canvas_adjustment_drafts import (
    IdleBehaviorCanvasAdjustmentDraftNotFound,
    IdleBehaviorCanvasAdjustmentDraftStale,
    IdleBehaviorCanvasAdjustmentDraftUnavailable,
)
from tests.motion_policy_preflight_helpers import MotionPolicyHttpFixtureMixin
from tests.test_idle_behavior_review_submission import valid_submission


class IdleBehaviorReviewHttpTests(
    MotionPolicyHttpFixtureMixin,
    unittest.TestCase,
):
    package_id = "a" * 64
    candidate_sha = "b" * 64

    def _request(self, method, suffix="", body=None, headers=None):
        encoded = (
            json.dumps(body, separators=(",", ":")).encode("utf-8")
            if isinstance(body, dict) else body
        )
        request_headers = dict(headers or {})
        if encoded is not None:
            request_headers.setdefault("Content-Type", "application/json")
        connection = http.client.HTTPConnection(
            self.host, self.port, timeout=10,
        )
        connection.request(
            method,
            f"/api/idle-behavior/review-packages{suffix}",
            body=encoded,
            headers=request_headers,
        )
        response = connection.getresponse()
        raw = response.read()
        result = (
            response.status,
            {key.lower(): value for key, value in response.getheaders()},
            raw,
        )
        connection.close()
        return result

    def _headers(self, **changes):
        headers = {
            "Origin": f"http://{self.host}:{self.port}",
            "X-Autospine-Intent": "body-sway-human-review-v1",
            "Sec-Fetch-Site": "same-origin",
        }
        headers.update(changes)
        return headers

    def _inventory(self):
        row = {
            "format": "private-extra",
            "format_version": 99,
            "package_id": self.package_id,
            "project_id": "fixture-project",
            "motion_id": "motion-a",
            "clip_id": "idle",
            "motion_policy_package_id": "c" * 64,
            "p9_decision_sha256": "d" * 64,
            "status": "ready_for_candidate_replay",
        }
        return {
            "format": "autospine-idle-behavior-review-package-list",
            "format_version": 1,
            "count": 1,
            "skipped_count": 0,
            "recommended_package_id": self.package_id,
            "packages": [row],
        }

    def _receipt(self):
        return {
            "format": "autospine-idle-behavior-review-receipt",
            "format_version": 1,
            "status": "recorded",
            "package_id": self.package_id,
            "candidate_sha256": self.candidate_sha,
            "decision_sha256": "e" * 64,
            "revision": 1,
            "action": "adjust",
            "probe_status": "pending_probe",
            "reused": False,
            "history": {
                "current_revision": 1,
                "head_decision_sha256": "e" * 64,
            },
        }

    def test_list_projects_only_the_frozen_seven_summary_fields(self):
        with patch(
            "autospine_workbench.idle_behavior_review_routes."
            "list_idle_behavior_review_packages",
            return_value=self._inventory(),
        ):
            status, headers, raw = self._request("GET")
        self.assertEqual(200, status)
        payload = json.loads(raw)
        self.assertEqual(7, len(payload["packages"][0]))
        self.assertNotIn("format_version", payload["packages"][0])
        self.assertEqual("same-origin", headers["cross-origin-resource-policy"])

    def test_detail_and_receipt_are_returned_without_path_fields(self):
        entry = {
            "format": "autospine-idle-behavior-review-entry",
            "format_version": 1,
            "status": "review_required",
            "package": {"package_id": self.package_id},
            "candidate_sha256": self.candidate_sha,
            "candidate": {}, "suggestion": {}, "preview": {},
            "history": {},
        }
        with patch(
            "autospine_workbench.idle_behavior_review_routes."
            "IdleBehaviorReviewApplication.prepare",
            return_value=entry,
        ):
            status, _, raw = self._request("GET", f"/{self.package_id}")
        self.assertEqual(200, status)
        self.assertEqual(entry, json.loads(raw))

        request = valid_submission(
            package_id=self.package_id,
            candidate_sha256=self.candidate_sha,
        )
        with patch(
            "autospine_workbench.idle_behavior_review_routes."
            "IdleBehaviorReviewApplication.submit",
            return_value=self._receipt(),
        ) as submit:
            status, _, raw = self._request(
                "POST", f"/{self.package_id}/decisions",
                request, self._headers(),
            )
        self.assertEqual(200, status)
        self.assertEqual(self._receipt(), json.loads(raw))
        self.assertTrue(submit.called)
        self.assertNotIn("path", raw.decode("utf-8").lower())

    def test_exact_canvas_adjustment_draft_get_is_path_free(self):
        draft = {
            "format": "autospine-idle-behavior-canvas-adjustment-draft-entry",
            "format_version": 1,
            "status": "unvalidated_draft",
            "entry": {"package": {"package_id": self.package_id}},
            "canvas_adjustment": {
                "candidate_sha256": self.candidate_sha,
                "document": {},
            },
            "proposal": {"authority": "none"},
        }
        suffix = (
            f"/{self.package_id}/canvas-adjustment-drafts/"
            f"{self.candidate_sha}"
        )
        with patch(
            "autospine_workbench.idle_behavior_review_routes."
            "IdleBehaviorCanvasAdjustmentDraftApplication.prepare",
            return_value=draft,
        ) as prepare:
            status, _, raw = self._request("GET", suffix)

        self.assertEqual(200, status)
        self.assertEqual(draft, json.loads(raw))
        prepare.assert_called_once()
        self.assertEqual(self.package_id, prepare.call_args.args[0])
        self.assertEqual(self.candidate_sha, prepare.call_args.args[1])
        self.assertNotIn("path", raw.decode("utf-8").lower())

    def test_canvas_adjustment_draft_failures_are_public_and_fail_closed(self):
        suffix = (
            f"/{self.package_id}/canvas-adjustment-drafts/"
            f"{self.candidate_sha}"
        )
        cases = (
            (
                IdleBehaviorCanvasAdjustmentDraftNotFound("private"),
                404,
                "body_sway_canvas_adjustment_draft_not_found",
            ),
            (
                IdleBehaviorCanvasAdjustmentDraftStale("private"),
                409,
                "body_sway_canvas_adjustment_draft_stale",
            ),
            (
                IdleBehaviorCanvasAdjustmentDraftUnavailable("private"),
                409,
                "body_sway_canvas_adjustment_draft_unavailable",
            ),
        )
        for error, expected_status, expected_code in cases:
            with self.subTest(error=type(error).__name__), patch(
                "autospine_workbench.idle_behavior_review_routes."
                "IdleBehaviorCanvasAdjustmentDraftApplication.prepare",
                side_effect=error,
            ):
                status, _, raw = self._request("GET", suffix)
            payload = json.loads(raw)
            self.assertEqual(expected_status, status)
            self.assertEqual(expected_code, payload["error"])
            self.assertNotIn("private", raw.decode("utf-8"))

    def test_invalid_canvas_adjustment_sha_is_404(self):
        suffix = f"/{self.package_id}/canvas-adjustment-drafts/not-a-sha"
        status, _, raw = self._request("GET", suffix)
        self.assertEqual(404, status)
        self.assertEqual(
            "body_sway_canvas_adjustment_draft_not_found",
            json.loads(raw)["error"],
        )

    def test_mutation_requires_same_origin_and_exact_intent(self):
        request = valid_submission(
            package_id=self.package_id,
            candidate_sha256=self.candidate_sha,
        )
        cases = (
            {},
            self._headers(Origin="http://example.test"),
            self._headers(**{"X-Autospine-Intent": "wrong"}),
        )
        for headers in cases:
            with self.subTest(headers=headers), patch(
                "autospine_workbench.idle_behavior_review_routes."
                "IdleBehaviorReviewApplication.submit",
            ) as submit:
                status, _, raw = self._request(
                    "POST", f"/{self.package_id}/decisions",
                    request, headers,
                )
                self.assertEqual(403, status)
                self.assertFalse(submit.called)
                self.assertTrue(json.loads(raw)["error"].startswith("forbidden_"))

    def test_mutation_methods_are_post_only(self):
        suffix = f"/{self.package_id}/decisions"
        status, headers, raw = self._request("OPTIONS", suffix)
        self.assertEqual(204, status)
        self.assertEqual("POST, OPTIONS", headers["allow"])
        self.assertEqual(b"", raw)
        for method in ("GET", "HEAD", "PUT", "PATCH", "DELETE"):
            with self.subTest(method=method):
                status, headers, raw = self._request(method, suffix)
                self.assertEqual(405, status)
                self.assertEqual("POST, OPTIONS", headers["allow"])
                if method != "HEAD":
                    self.assertEqual("method_not_allowed", json.loads(raw)["error"])

    def test_application_failure_does_not_leak_local_details(self):
        secret = f"private failure at {self.store.state}"
        with patch(
            "autospine_workbench.idle_behavior_review_routes."
            "IdleBehaviorReviewApplication.prepare",
            side_effect=IdleBehaviorReviewApplicationUnavailable(secret),
        ):
            status, _, raw = self._request("GET", f"/{self.package_id}")
        self.assertEqual(409, status)
        self.assertNotIn(secret, raw.decode("utf-8"))
        self.assertNotIn(str(self.store.state), raw.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
