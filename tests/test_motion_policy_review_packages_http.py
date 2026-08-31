"""Live HTTP tests for exact automatic motion-policy package selection."""

from __future__ import annotations

import http.client
import json
import shutil
import unittest
from unittest.mock import patch

from tests.motion_policy_preflight_helpers import MotionPolicyHttpFixtureMixin
from tests.motion_policy_review_package_helpers import write_review_package

from autospine_workbench.current_project_chain import (
    CurrentProjectChain,
    CurrentProjectChainUnavailableError,
)
from autospine_workbench.motion_policy_review_packages import (
    MotionPolicyReviewPackageError,
    list_motion_policy_review_packages,
)
from autospine_workbench.project_store import ProjectStoreError


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
        p3 = self.policy["source"]["p3"]
        self.current = {
            self.policy["project_id"]: CurrentProjectChain(
                self.policy["project_id"],
                p3["resolved_project_sha256"],
                p3["layer_manifest_sha256"],
            ),
        }
        current_patch = patch(
            "autospine_workbench.motion_policy_review_package_routes."
            "rebuild_current_project_chains",
            return_value=self.current,
        )
        current_patch.start()
        self.addCleanup(current_patch.stop)

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
        self.assertEqual(2, listing["format_version"])
        self.assertEqual(2, listing["packages"][0]["format_version"])
        self.assertEqual(1, listing["count"])
        self.assertEqual(self.package_id, listing["recommended_package_id"])
        self.assertEqual(
            "current", listing["packages"][0]["authoring_alignment"],
        )
        self.assertEqual("same-origin", headers["cross-origin-resource-policy"])

        status, _, raw = self._package_request("GET", f"/{self.package_id}")
        self.assertEqual(200, status)
        detail = json.loads(raw.decode("utf-8"))
        self.assertEqual(2, detail["format_version"])
        self.assertEqual(self.package_id, detail["package_id"])
        self.assertEqual("current", detail["authoring_alignment"])
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

    def test_historical_package_is_readable_but_not_recommended(self):
        project_id = self.policy["project_id"]
        historical = {
            project_id: CurrentProjectChain(
                project_id,
                self.current[project_id].resolved_project_sha256,
                "f" * 64,
            ),
        }
        with patch(
            "autospine_workbench.motion_policy_review_package_routes."
            "rebuild_current_project_chains",
            return_value=historical,
        ):
            status, _, raw = self._package_request("GET")
            self.assertEqual(200, status)
            listing = json.loads(raw.decode("utf-8"))
            self.assertIsNone(listing["recommended_package_id"])
            self.assertEqual(
                "historical", listing["packages"][0]["authoring_alignment"],
            )
            status, _, raw = self._package_request(
                "GET", f"/{self.package_id}",
            )
            self.assertEqual(200, status)
            self.assertEqual(
                "historical",
                json.loads(raw.decode("utf-8"))["authoring_alignment"],
            )

    def test_authoring_drift_and_store_failure_are_path_free(self):
        project_id = self.policy["project_id"]
        changed = {
            project_id: CurrentProjectChain(
                project_id,
                self.current[project_id].resolved_project_sha256,
                "e" * 64,
            ),
        }
        with patch(
            "autospine_workbench.motion_policy_review_package_routes."
            "rebuild_current_project_chains",
            side_effect=[self.current, changed],
        ):
            status, _, raw = self._package_request("GET")
        self.assertEqual(409, status)
        self.assertEqual(
            "motion_policy_project_chain_changed",
            json.loads(raw.decode("utf-8"))["error"],
        )

        with patch(
            "autospine_workbench.motion_policy_review_package_routes."
            "resolve_motion_policy_project_scope",
            side_effect=ProjectStoreError(f"private {self.store.state}"),
        ):
            status, _, raw = self._package_request("GET")
        self.assertEqual(500, status)
        decoded = raw.decode("utf-8")
        self.assertNotIn("private", decoded)
        self.assertNotIn(str(self.store.state), decoded)

    def test_list_project_scope_filters_inventory_and_rejects_bad_queries(self):
        project_id = self.policy["project_id"]
        status, _, raw = self._package_request(
            "GET", f"?project_id={project_id}",
        )
        self.assertEqual(200, status)
        self.assertEqual(1, json.loads(raw)["count"])

        status, _, raw = self._package_request(
            "GET", f"/{self.package_id}?project_id={project_id}",
        )
        self.assertEqual(200, status)
        self.assertEqual(self.package_id, json.loads(raw)["package_id"])

        status, _, raw = self._package_request(
            "GET", "?project_id=unrelated-project",
        )
        self.assertEqual(200, status)
        self.assertEqual(0, json.loads(raw)["count"])

        status, _, _ = self._package_request(
            "GET", f"/{self.package_id}?project_id=unrelated-project",
        )
        self.assertEqual(404, status)

        status, _, raw = self._package_request("GET", "?project_id=../bad")
        self.assertEqual(400, status)
        self.assertEqual(
            "invalid_motion_policy_project_scope", json.loads(raw)["error"],
        )

    def test_rebuild_unavailable_is_500_not_authoring_drift(self):
        private = f"persistent project store at {self.store.state}"
        for suffix in ("", f"/{self.package_id}"):
            with self.subTest(suffix=suffix), patch(
                "autospine_workbench.motion_policy_review_package_routes."
                "rebuild_current_project_chains",
                side_effect=CurrentProjectChainUnavailableError(private),
            ):
                status, _, raw = self._package_request("GET", suffix)
            self.assertEqual(500, status)
            self.assertEqual(
                "motion_policy_project_chain_unavailable",
                json.loads(raw.decode("utf-8"))["error"],
            )
            self.assertNotIn("changed", raw.decode("utf-8"))
            self.assertNotIn(private, raw.decode("utf-8"))
            self.assertNotIn(str(self.store.state), raw.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
