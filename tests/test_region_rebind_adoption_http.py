"""HTTP security and server wiring for region rebind adoption."""

from __future__ import annotations

import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.region_rebind_adoption import (  # noqa: E402
    RegionRebindAdoptionHistorical,
    RegionRebindAdoptionHeadChanged,
)
from autospine_workbench.region_rebind_revision_provenance import (  # noqa: E402
    INTENT,
)
from autospine_workbench.server import create_server  # noqa: E402
from tests.test_project_store import StoreFixture  # noqa: E402


PACKAGE = "a" * 64
CANDIDATE = "b" * 64
PATH = (
    f"/api/idle-behavior/structural-probes/{PACKAGE}"
    f"/rebind-adoptions/{CANDIDATE}"
)
REQUEST = {
    "project_id": "fixture-project",
    "layer_id": "layer-000-topwear",
    "from_bone_id": "forearm.left",
    "to_bone_id": "upper-arm.left",
    "candidate_sha256": CANDIDATE,
    "base_revision": 1,
    "overrides": {
        "revision": 1,
        "joint_overrides": {},
        "joint_decisions": {},
        "split_decisions": {},
        "layer_overrides": {},
        "notes": "",
    },
}
RECEIPT = {
    "format": "autospine-region-rebind-adoption-receipt",
    "format_version": 1,
    "status": "adopted",
    "project_id": "fixture-project",
    "revision": 2,
    "package_id": PACKAGE,
    "candidate_sha256": CANDIDATE,
    "layer_id": "layer-000-topwear",
    "from_bone_id": "forearm.left",
    "to_bone_id": "upper-arm.left",
    "provenance_sha256": "c" * 64,
    "provenance": {},
    "overrides": {"revision": 2},
}


class RegionRebindAdoptionHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.fixture = StoreFixture(Path(self.temporary.name))
        self.server = create_server(
            "127.0.0.1", 0, self.fixture.workspace,
            state_root=self.fixture.state,
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True,
        )
        self.thread.start()
        self.host, self.port = self.server.server_address[:2]
        self.authority = f"{self.host}:{self.port}"
        self.origin = f"http://{self.authority}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.temporary.cleanup()

    def _headers(self, **overrides):
        headers = {
            "Host": self.authority,
            "Origin": self.origin,
            "Content-Type": "application/json",
            "X-Autospine-Intent": INTENT,
            "Sec-Fetch-Site": "same-origin",
        }
        headers.update(overrides)
        return headers

    def _request(self, method, *, body=REQUEST, headers=None):
        connection = http.client.HTTPConnection(
            self.host, self.port, timeout=5,
        )
        raw = None if body is None else json.dumps(body).encode("utf-8")
        connection.request(method, PATH, body=raw, headers=headers or {})
        response = connection.getresponse()
        data = response.read()
        result = (
            response.status,
            {key.lower(): value for key, value in response.getheaders()},
            json.loads(data.decode("utf-8")) if data else None,
        )
        connection.close()
        return result

    def test_post_is_same_origin_intent_bound_and_path_free(self):
        target = (
            "autospine_workbench.region_rebind_adoption_routes."
            "RegionRebindAdoptionApplication.adopt"
        )
        with patch(target, return_value=RECEIPT) as adopt:
            status, headers, result = self._request(
                "POST", headers=self._headers(),
            )
        self.assertEqual(200, status)
        self.assertEqual(RECEIPT, result)
        self.assertEqual(self.origin, headers["access-control-allow-origin"])
        self.assertEqual("same-origin", headers["cross-origin-resource-policy"])
        adopt.assert_called_once_with(PACKAGE, CANDIDATE, REQUEST)
        self.assertNotIn(str(self.fixture.state), json.dumps(result))

    def test_missing_origin_wrong_intent_and_cross_site_never_reach_app(self):
        cases = [
            {"Host": self.authority, "Content-Type": "application/json",
             "X-Autospine-Intent": INTENT},
            self._headers(**{"X-Autospine-Intent": "wrong"}),
            self._headers(**{"Sec-Fetch-Site": "cross-site"}),
        ]
        target = (
            "autospine_workbench.region_rebind_adoption_routes."
            "RegionRebindAdoptionApplication.adopt"
        )
        with patch(target, return_value=RECEIPT) as adopt:
            for headers in cases:
                with self.subTest(headers=headers):
                    status, _response_headers, result = self._request(
                        "POST", headers=headers,
                    )
                    self.assertEqual(403, status)
                    self.assertTrue(result["error"].startswith("forbidden_"))
        adopt.assert_not_called()

    def test_historical_error_is_public_read_only_conflict(self):
        target = (
            "autospine_workbench.region_rebind_adoption_routes."
            "RegionRebindAdoptionApplication.adopt"
        )
        with patch(
            target, side_effect=RegionRebindAdoptionHistorical("old"),
        ):
            status, _headers, result = self._request(
                "POST", headers=self._headers(),
            )
        self.assertEqual(409, status)
        self.assertEqual(
            "region_rebind_adoption_historical_read_only", result["error"],
        )

    def test_last_moment_p10_head_change_is_public_conflict(self):
        target = (
            "autospine_workbench.region_rebind_adoption_routes."
            "RegionRebindAdoptionApplication.adopt"
        )
        with patch(
            target, side_effect=RegionRebindAdoptionHeadChanged("changed"),
        ):
            status, _headers, result = self._request(
                "POST", headers=self._headers(),
            )
        self.assertEqual(409, status)
        self.assertEqual("region_rebind_p10_head_changed", result["error"])

    def test_options_and_other_methods_publish_exact_allow_contract(self):
        status, headers, result = self._request(
            "OPTIONS", body=None,
            headers={"Host": self.authority, "Origin": self.origin},
        )
        self.assertEqual(204, status)
        self.assertIsNone(result)
        self.assertEqual("POST, OPTIONS", headers["allow"])
        self.assertEqual(
            "Content-Type, X-Autospine-Intent",
            headers["access-control-allow-headers"],
        )
        for method in ("GET", "PUT", "PATCH", "DELETE"):
            with self.subTest(method=method):
                status, response_headers, result = self._request(
                    method, body=None,
                    headers={"Host": self.authority, "Origin": self.origin},
                )
                self.assertEqual(405, status)
                self.assertEqual("POST, OPTIONS", response_headers["allow"])
                self.assertEqual("method_not_allowed", result["error"])


if __name__ == "__main__":
    unittest.main()
