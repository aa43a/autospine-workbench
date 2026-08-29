"""Live HTTP tests for exact automatic motion-policy package selection."""

from __future__ import annotations

import http.client
import json
import shutil
import unittest
from unittest.mock import patch

from tests.motion_policy_preflight_helpers import MotionPolicyHttpFixtureMixin
from tests.motion_policy_review_package_helpers import write_review_package

from autospine_workbench.motion_policy_review_packages import (
    MotionPolicyReviewPackageError,
    list_motion_policy_review_packages,
)


class MotionPolicyReviewPackageHttpTests(
    MotionPolicyHttpFixtureMixin,
    unittest.TestCase,
):
    def setUp(self) -> None:
        write_review_package(
            self.store.state, self.policy, self.foot, self.depth,
        )
        listing = list_motion_policy_review_packages(self.store.state)
        self.package_id = listing["recommended_package_id"]

    def tearDown(self) -> None:
        shutil.rmtree(self.store.state / "reviews", ignore_errors=True)

    def _package_request(self, method: str, suffix: str = ""):
        connection = http.client.HTTPConnection(
            self.host, self.port, timeout=10,
        )
        body = b"{}" if method in {"POST", "PUT"} else None
        headers = {"Origin": f"http://{self.host}:{self.port}"}
        connection.request(
            method, f"/api/motion-policy/review-packages{suffix}",
            body=body, headers=headers,
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

    def test_get_list_head_and_exact_detail(self):
        status, headers, raw = self._package_request("GET")
        self.assertEqual(200, status)
        listing = json.loads(raw.decode("utf-8"))
        self.assertEqual(1, listing["count"])
        self.assertEqual(self.package_id, listing["recommended_package_id"])
        self.assertEqual("same-origin", headers["cross-origin-resource-policy"])

        status, _, raw = self._package_request("GET", f"/{self.package_id}")
        self.assertEqual(200, status)
        detail = json.loads(raw.decode("utf-8"))
        self.assertEqual(self.package_id, detail["package_id"])
        encoded = json.dumps(detail)
        self.assertNotIn("private-package-root", encoded)
        self.assertNotIn(str(self.store.state), encoded)

        status, headers, raw = self._package_request(
            "HEAD", f"/{self.package_id}",
        )
        self.assertEqual(200, status)
        self.assertEqual(b"", raw)
        self.assertGreater(int(headers["content-length"]), 0)

    def test_options_and_write_methods_are_read_only(self):
        for suffix in ("", f"/{self.package_id}"):
            with self.subTest(method="OPTIONS", suffix=suffix):
                status, headers, raw = self._package_request("OPTIONS", suffix)
                self.assertEqual(204, status)
                self.assertEqual("GET, HEAD, OPTIONS", headers["allow"])
                self.assertEqual(b"", raw)
            for method in ("POST", "PUT", "PATCH", "DELETE"):
                with self.subTest(method=method, suffix=suffix):
                    status, headers, raw = self._package_request(method, suffix)
                    self.assertEqual(405, status)
                    self.assertEqual("GET, HEAD, OPTIONS", headers["allow"])
                    self.assertEqual(
                        "method_not_allowed",
                        json.loads(raw.decode("utf-8"))["error"],
                    )

    def test_errors_are_public_and_do_not_leak_internal_paths(self):
        status, _, raw = self._package_request("GET", "/not-a-sha")
        self.assertEqual(404, status)
        self.assertNotIn(str(self.store.state), raw.decode("utf-8"))

        secret = f"private failure at {self.store.state}"
        with patch(
            "autospine_workbench.motion_policy_review_package_routes."
            "list_motion_policy_review_packages",
            side_effect=MotionPolicyReviewPackageError(secret),
        ):
            status, _, raw = self._package_request("GET")
        self.assertEqual(500, status)
        decoded = raw.decode("utf-8")
        self.assertNotIn("private failure", decoded)
        self.assertNotIn(str(self.store.state), decoded)


if __name__ == "__main__":
    unittest.main()
