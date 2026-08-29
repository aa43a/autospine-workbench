"""Live HTTP boundaries for exact P9-to-seam review entries."""

from __future__ import annotations

import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from autospine_workbench.motion_policy_seam_review_entry import (
    MotionPolicySeamReviewEntryError,
)
from autospine_workbench.server import create_server
from tests.motion_policy_preflight_helpers import tree_snapshot
from tests.motion_policy_seam_review_entry_helpers import (
    MotionPolicySeamReviewEntryFixture,
)
from tests.test_project_store import StoreFixture


class MotionPolicySeamReviewEntryHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.fixture = MotionPolicySeamReviewEntryFixture(cls.root / "exact")
        cls.store = StoreFixture(cls.root / "server")
        cls.server = create_server(
            "127.0.0.1", 0, cls.store.workspace,
            state_root=cls.fixture.state,
        )
        cls.thread = threading.Thread(
            target=cls.server.serve_forever, daemon=True,
        )
        cls.thread.start()
        cls.host, cls.port = cls.server.server_address[:2]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls.temporary.cleanup()

    def _path(self, motion_id="motion-a", package_id=None):
        identifier = package_id or self.fixture.package_ids[motion_id]
        return (
            f"/api/motion-policy/review-packages/{identifier}/"
            "seam-review-entry"
        )

    def _request(self, method, path=None):
        connection = http.client.HTTPConnection(
            self.host, self.port, timeout=15,
        )
        connection.request(method, path or self._path())
        response = connection.getresponse()
        raw = response.read()
        result = (
            response.status,
            {key.lower(): value for key, value in response.getheaders()},
            raw,
        )
        connection.close()
        return result

    def test_get_head_and_options_are_the_only_methods(self):
        before = tree_snapshot(self.fixture.state)
        status, headers, raw = self._request("GET")
        self.assertEqual(200, status)
        self.assertEqual("same-origin", headers["cross-origin-resource-policy"])
        self.assertEqual("manual_review_required", json.loads(raw)["status"])
        head_status, head_headers, head_raw = self._request("HEAD")
        self.assertEqual(200, head_status)
        self.assertEqual(headers["content-length"], head_headers["content-length"])
        self.assertEqual(b"", head_raw)
        option_status, option_headers, option_raw = self._request("OPTIONS")
        self.assertEqual(204, option_status)
        self.assertEqual("GET, HEAD, OPTIONS", option_headers["allow"])
        self.assertEqual(b"", option_raw)
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            with self.subTest(method=method):
                denied, denied_headers, _ = self._request(method)
                self.assertEqual(405, denied)
                self.assertEqual(
                    "GET, HEAD, OPTIONS", denied_headers["allow"]
                )
        self.assertEqual(before, tree_snapshot(self.fixture.state))

    def test_b_and_errors_are_path_free_and_sanitized(self):
        status, _, raw = self._request("GET", self._path("motion-b"))
        self.assertEqual(200, status)
        decoded = raw.decode("utf-8")
        self.assertEqual("blocked_unobservable", json.loads(decoded)["status"])
        self.assertNotIn(str(self.root), decoded)
        missing, _, missing_raw = self._request(
            "GET", self._path(package_id="f" * 64),
        )
        self.assertEqual(404, missing)
        self.assertEqual(
            "motion_policy_package_not_found",
            json.loads(missing_raw)["error"],
        )
        private = str(self.root / "private-source")
        with patch(
            "autospine_workbench.motion_policy_seam_review_entry_routes."
            "build_motion_policy_seam_review_entry",
            side_effect=MotionPolicySeamReviewEntryError(private),
        ):
            failed, _, failed_raw = self._request("GET")
        self.assertEqual(409, failed)
        self.assertNotIn(private, failed_raw.decode("utf-8"))
        self.assertEqual(
            "motion_policy_seam_review_entry_unavailable",
            json.loads(failed_raw)["error"],
        )


if __name__ == "__main__":
    unittest.main()
