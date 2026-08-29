"""Live HTTP security and publication tests for P9 package adoption."""

from __future__ import annotations

from copy import deepcopy
import http.client
import json
import shutil
import unittest
from unittest.mock import patch

from tests.motion_policy_decision_helpers import approved_review
from tests.motion_policy_preflight_helpers import MotionPolicyHttpFixtureMixin
from tests.motion_policy_review_package_helpers import write_review_package

from autospine_workbench.motion_policy_adoption import (
    INTENT_VALUE,
    REQUEST_FORMAT,
)
from autospine_workbench.motion_policy_review_packages import (
    list_motion_policy_review_packages,
)


class MotionPolicyAdoptionHttpTests(
    MotionPolicyHttpFixtureMixin,
    unittest.TestCase,
):
    def setUp(self) -> None:
        write_review_package(
            self.store.state, self.policy, self.foot, self.depth,
        )
        self.package_id = list_motion_policy_review_packages(
            self.store.state,
        )["recommended_package_id"]
        self.body = {
            "format": REQUEST_FORMAT,
            "format_version": 1,
            "intent": INTENT_VALUE,
            "package_id": self.package_id,
            "review_input": {
                "review": approved_review(),
                "decisions": self.chain.accept_all(),
                "root_release_keys": [],
                "draw_order_loop_reset": {
                    "mode": "explicit", "approved": False,
                },
            },
        }

    def tearDown(self) -> None:
        shutil.rmtree(self.store.state / "reviews", ignore_errors=True)
        shutil.rmtree(self._p9_root(), ignore_errors=True)

    def _p9_root(self):
        return (
            self.store.state / "builds" / self.policy["project_id"]
            / "reviewed-motion-instances"
        )

    def _adoption_headers(self, **changes):
        headers = {
            "Origin": f"http://{self.host}:{self.port}",
            "X-Autospine-Intent": INTENT_VALUE,
            "Sec-Fetch-Site": "same-origin",
        }
        headers.update(changes)
        return headers

    def _adoption_request(
        self, method="POST", body=None, headers=None, package_id=None,
    ):
        value = self.body if body is None and method == "POST" else body
        encoded = (
            json.dumps(value, separators=(",", ":")).encode("utf-8")
            if isinstance(value, dict) else value
        )
        request_headers = dict(
            self._adoption_headers() if headers is None else headers
        )
        if encoded is not None:
            request_headers.setdefault("Content-Type", "application/json")
        connection = http.client.HTTPConnection(
            self.host, self.port, timeout=10,
        )
        target_id = package_id or self.package_id
        connection.request(
            method,
            f"/api/motion-policy/review-packages/{target_id}/adoptions",
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

    def _with_upstreams(self, callback):
        upstream = self.chain.upstream
        with patch(
            "autospine_workbench.motion_policy_adoption."
            "VerifiedMeshBundleReader"
        ) as mesh_reader, patch(
            "autospine_workbench.motion_policy_adoption."
            "VerifiedMotionRetargetBundleReader"
        ) as retarget_reader:
            mesh_reader.return_value.load.return_value = upstream.mesh
            retarget_reader.return_value.load.return_value = upstream.retarget
            return callback()

    def test_post_publishes_then_reuses_path_free_exact_receipt(self):
        first = self._with_upstreams(self._adoption_request)
        second = self._with_upstreams(self._adoption_request)
        self.assertEqual(200, first[0])
        self.assertEqual(200, second[0])
        receipt = json.loads(first[2].decode("utf-8"))
        reused = json.loads(second[2].decode("utf-8"))
        self.assertFalse(receipt["reused"])
        self.assertTrue(reused["reused"])
        self.assertEqual(receipt["address"], reused["address"])
        self.assertEqual("passed", receipt["verification"]["status"])
        self.assertEqual(
            "same-origin", first[1]["cross-origin-resource-policy"],
        )
        encoded = json.dumps(receipt)
        self.assertNotIn(str(self.store.state), encoded)
        self.assertNotIn("path", encoded.lower())

    def test_options_and_other_methods_expose_only_post(self):
        status, headers, raw = self._adoption_request(
            method="OPTIONS", body=None,
        )
        self.assertEqual(204, status)
        self.assertEqual("POST, OPTIONS", headers["allow"])
        self.assertEqual(b"", raw)
        for method in ("GET", "HEAD", "PUT", "PATCH", "DELETE"):
            with self.subTest(method=method):
                status, headers, raw = self._adoption_request(
                    method=method, body=None,
                )
                self.assertEqual(405, status)
                self.assertEqual("POST, OPTIONS", headers["allow"])
                if method != "HEAD":
                    self.assertEqual(
                        "method_not_allowed",
                        json.loads(raw.decode("utf-8"))["error"],
                    )

    def test_same_origin_intent_and_content_type_fail_before_writes(self):
        cases = (
            ({"X-Autospine-Intent": INTENT_VALUE}, 403),
            (self._adoption_headers(Origin="http://example.test"), 403),
            (self._adoption_headers(
                **{"X-Autospine-Intent": "wrong"}
            ), 403),
            (self._adoption_headers(**{"Sec-Fetch-Site": "cross-site"}), 403),
            (self._adoption_headers(**{"Content-Type": "text/plain"}), 415),
        )
        for headers, expected in cases:
            with self.subTest(expected=expected, headers=headers):
                status, _, _ = self._adoption_request(headers=headers)
                self.assertEqual(expected, status)
                self.assertFalse(self._p9_root().exists())

    def test_bad_contract_crosswire_and_stale_id_make_zero_publication(self):
        extra = deepcopy(self.body)
        extra["automatic"] = True
        status, _, raw = self._adoption_request(body=extra)
        self.assertEqual(400, status)
        self.assertEqual(
            "invalid_motion_policy_adoption_request",
            json.loads(raw.decode("utf-8"))["error"],
        )

        crosswired = deepcopy(self.body)
        crosswired["review_input"]["decisions"][0][
            "candidate_id"
        ] = "foot-" + "0" * 64
        status, _, _ = self._adoption_request(body=crosswired)
        self.assertEqual(400, status)

        stale = deepcopy(self.body)
        stale["package_id"] = "f" * 64
        status, _, _ = self._adoption_request(
            body=stale, package_id="f" * 64,
        )
        self.assertEqual(404, status)
        self.assertFalse(self._p9_root().exists())

    def test_upstream_failure_is_public_conflict_without_publication(self):
        with patch(
            "autospine_workbench.motion_policy_adoption."
            "VerifiedMeshBundleReader"
        ) as reader:
            reader.return_value.load.side_effect = ValueError(
                f"private at {self.store.state}"
            )
            status, _, raw = self._adoption_request()
        self.assertEqual(409, status)
        decoded = raw.decode("utf-8")
        self.assertNotIn(str(self.store.state), decoded)
        self.assertNotIn("private", decoded)
        self.assertFalse(self._p9_root().exists())


if __name__ == "__main__":
    unittest.main()
