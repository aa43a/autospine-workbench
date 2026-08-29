"""Live-HTTP contracts for the zero-write P9 preflight boundary."""

from __future__ import annotations

import json
import unittest

from tests.motion_policy_preflight_helpers import (
    MotionPolicyHttpFixtureMixin,
    tree_snapshot,
)

from autospine_workbench.motion_policy_preflight import CANDIDATE_INVENTORY
from autospine_workbench.motion_policy_preflight_routes import (
    MAX_REQUEST_BYTES,
)


class MotionPolicyPreflightHttpTests(
    MotionPolicyHttpFixtureMixin,
    unittest.TestCase,
):
    def test_http_success_is_zero_write_and_errors_are_bounded(self) -> None:
        before = tree_snapshot(self.store.workspace, self.store.state)
        status, headers, value = self._json_request(
            "POST",
            self._policy_request(self.policy),
            self._headers(),
        )
        self.assertEqual(200, status)
        self.assertEqual("passed", value["status"])
        self.assertEqual(
            "same-origin",
            headers["cross-origin-resource-policy"],
        )
        status, _, inventory = self._json_request(
            "POST",
            self._candidate_request(),
            self._headers(),
        )
        self.assertEqual(200, status)
        self.assertEqual(CANDIDATE_INVENTORY, inventory["operation"])
        self.assertEqual(
            before,
            tree_snapshot(self.store.workspace, self.store.state),
        )

        cases = (
            (
                self._headers(**{"X-Autospine-Intent": "wrong"}),
                "forbidden_intent",
            ),
            (
                self._headers(
                    Origin=f"http://{self.host}:{self.port + 1}"
                ),
                "forbidden_origin",
            ),
            (
                self._headers(**{"Sec-Fetch-Site": "cross-site"}),
                "forbidden_fetch_site",
            ),
            (
                self._headers(Host="attacker.example"),
                "forbidden_host",
            ),
        )
        for request_headers, expected in cases:
            with self.subTest(expected=expected):
                status, _, value = self._json_request(
                    "POST",
                    self._policy_request(self.policy),
                    request_headers,
                )
                self.assertEqual(403, status)
                self.assertEqual(expected, value["error"])

    def test_http_limit_options_and_wrong_methods(self) -> None:
        wrong_type = self._headers()
        wrong_type["Content-Type"] = "text/plain"
        status, _, value = self._json_request(
            "POST",
            self._json(self._policy_request(self.policy)).encode(),
            wrong_type,
        )
        self.assertEqual(415, status)
        self.assertEqual("unsupported_media_type", value["error"])

        headers = self._headers()
        headers.update({
            "Content-Type": "application/json",
            "Content-Length": str(MAX_REQUEST_BYTES + 1),
        })
        status, _, value = self._json_request("POST", None, headers)
        self.assertEqual(413, status)
        self.assertEqual("request_too_large", value["error"])

        status, response_headers, raw = self._request(
            "OPTIONS",
            None,
            self._headers(),
        )
        self.assertEqual(204, status)
        self.assertEqual("POST, OPTIONS", response_headers["allow"])
        self.assertEqual(b"", raw)
        for method in ("GET", "HEAD", "PUT", "DELETE"):
            with self.subTest(method=method):
                status, method_headers, raw = self._request(
                    method,
                    None,
                    self._headers(),
                )
                self.assertEqual(405, status)
                self.assertEqual(
                    "POST, OPTIONS",
                    method_headers["allow"],
                )
                if method != "HEAD":
                    self.assertEqual(
                        "method_not_allowed",
                        json.loads(raw.decode("utf-8"))["error"],
                    )


if __name__ == "__main__":
    unittest.main()
