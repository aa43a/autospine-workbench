"""Live loopback route and zero-write tests for P10.2 probes."""

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


from autospine_workbench.body_sway_probe_application import (
    BodySwayProbeApplicationError,
    BodySwayProbeApplicationHeadChanged,
    BodySwayProbeApplicationNotFound,
    BodySwayProbeApplicationUnavailable,
)
from autospine_workbench.current_project_chain import (
    CurrentProjectChainUnavailableError,
)
from tests.motion_policy_preflight_helpers import (
    MotionPolicyHttpFixtureMixin,
    tree_snapshot,
)


class BodySwayProbeHttpTests(
    MotionPolicyHttpFixtureMixin,
    unittest.TestCase,
):
    package_id = "a" * 64
    candidate_sha = "b" * 64
    decision_sha = "c" * 64
    report_sha = "d" * 64
    p9_decision_sha = "e" * 64
    base = "/api/idle-behavior/structural-probes"

    def _probe_request(self, method, suffix="", headers=None, body=None):
        connection = http.client.HTTPConnection(
            self.host, self.port, timeout=10,
        )
        connection.request(
            method, f"{self.base}{suffix}", body=body,
            headers=dict(headers or {}),
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

    def _list(self):
        row = {
            "package_id": self.package_id,
            "project_id": "fixture-project",
            "motion_id": "wave-left-v1",
            "clip_id": "kimodo.wave-left.semantic.front",
            "status": "probe_ready",
            "current_revision": 1,
            "action": "adjust",
            "probe_status": "pending_probe",
            "candidate_sha256": self.candidate_sha,
            "decision_sha256": self.decision_sha,
        }
        return {
            "format": "autospine-body-sway-probe-package-list",
            "format_version": 1,
            "count": 1,
            "ready_count": 1,
            "not_applicable_count": 0,
            "review_required_count": 0,
            "skipped_count": 0,
            "recommended_package_id": self.package_id,
            "packages": [row],
        }

    def _detail(self):
        return {
            "format": "autospine-body-sway-probe-entry",
            "format_version": 1,
            "status": "manual_visual_required",
            "probeability": "probe_ready",
            "package": {
                "package_id": self.package_id,
                "motion_policy_package_id": "f" * 64,
                "project_id": "fixture-project",
                "motion_id": "wave-left-v1",
                "clip_id": "kimodo.wave-left.semantic.front",
                "motion_instance_v2_sha256": "1" * 64,
                "reviewed_motion_bundle_sha256": "2" * 64,
                "p9_decision_sha256": self.p9_decision_sha,
            },
            "candidate_sha256": self.candidate_sha,
            "history": {
                "current_revision": 1,
                "head_decision_sha256": self.decision_sha,
                "action": "adjust",
                "probe_status": "pending_probe",
            },
            "report_sha256": self.report_sha,
            "result": {
                "status": "manual_visual_required",
                "release_gate": {"status": "blocked", "reason_codes": []},
                "schedule": {"first_tick": 0, "last_tick": 1, "sample_count": 2},
                "checks": [],
                "summary": {"schedule_sample_count": 2, "check_count": 7},
            },
            "preview": {
                "kind": "sampled-structural-witness-preview",
                "authority": "none",
                "witnesses": [],
                "canvas": {"width": 400, "height": 400},
                "composite_url": "/api/projects/fixture-project/composite",
            },
            "technical": {"report": {
                "format": "autospine-body-sway-probe-report",
                "format_version": 1,
                "status": "manual_visual_required",
            }, "semantics": {"diagnostic_only": True}},
        }

    def test_list_and_detail_are_path_free_zero_write_gets(self):
        before = tree_snapshot(self.store.state)
        current = {"fixture-project": object()}
        with patch(
            "autospine_workbench.body_sway_probe_routes."
            "BodySwayProbeApplication.list_packages",
            return_value=self._list(),
        ) as listed, patch(
            "autospine_workbench.body_sway_probe_routes."
            "rebuild_current_project_chains",
            return_value=current,
        ):
            status, headers, raw = self._probe_request("GET")
        self.assertEqual(200, status)
        self.assertEqual(self._list(), json.loads(raw))
        self.assertEqual("same-origin", headers[
            "cross-origin-resource-policy"
        ])
        listed.assert_called_once_with(
            project_ids=("fixture-project",),
            current_project_chains=current,
        )

        with patch(
            "autospine_workbench.body_sway_probe_routes."
            "BodySwayProbeApplication.prepare",
            return_value=self._detail(),
        ) as prepared:
            status, _, raw = self._probe_request(
                "GET", f"/{self.package_id}",
            )
        self.assertEqual(200, status)
        self.assertEqual(self._detail(), json.loads(raw))
        prepared.assert_called_once_with(
            self.package_id, project_ids=("fixture-project",),
        )
        self.assertNotIn("path", raw.decode("utf-8").lower())
        self.assertEqual(before, tree_snapshot(self.store.state))

    def test_empty_real_inventory_uses_the_application_without_writes(self):
        before = tree_snapshot(self.store.state)
        with patch(
            "autospine_workbench.body_sway_probe_routes."
            "rebuild_current_project_chains",
            return_value={"fixture-project": object()},
        ):
            status, _, raw = self._probe_request("GET")
        payload = json.loads(raw)
        self.assertEqual(200, status)
        self.assertEqual(
            "autospine-body-sway-probe-package-list", payload["format"],
        )
        self.assertEqual((0, []), (payload["count"], payload["packages"]))
        self.assertEqual(before, tree_snapshot(self.store.state))

    def test_current_project_drift_rejects_completed_inventory(self):
        before = {"fixture-project": object()}
        after = {"fixture-project": object()}
        with patch(
            "autospine_workbench.body_sway_probe_routes."
            "BodySwayProbeApplication.list_packages",
            return_value=self._list(),
        ), patch(
            "autospine_workbench.body_sway_probe_routes."
            "rebuild_current_project_chains",
            side_effect=(before, after),
        ):
            status, _, raw = self._probe_request("GET")
        self.assertEqual(409, status)
        self.assertEqual(
            "body_sway_project_chain_changed", json.loads(raw)["error"],
        )

    def test_chain_rebuild_unavailable_is_500_and_zero_write(self):
        before = tree_snapshot(self.store.state)
        private = f"persistent project store at {self.store.state}"
        with patch(
            "autospine_workbench.body_sway_probe_routes."
            "rebuild_current_project_chains",
            side_effect=CurrentProjectChainUnavailableError(private),
        ), patch(
            "autospine_workbench.body_sway_probe_routes."
            "BodySwayProbeApplication.list_packages",
        ) as listed:
            status, _, raw = self._probe_request("GET")
        self.assertEqual(500, status)
        self.assertEqual(
            "body_sway_project_chain_unavailable",
            json.loads(raw)["error"],
        )
        listed.assert_not_called()
        self.assertNotIn(private, raw.decode("utf-8"))
        self.assertNotIn(str(self.store.state), raw.decode("utf-8"))
        self.assertEqual(before, tree_snapshot(self.store.state))

    def test_head_matches_get_metadata_without_a_body(self):
        with patch(
            "autospine_workbench.body_sway_probe_routes."
            "BodySwayProbeApplication.prepare",
            return_value=self._detail(),
        ):
            get_status, get_headers, get_raw = self._probe_request(
                "GET", f"/{self.package_id}",
            )
            head_status, head_headers, head_raw = self._probe_request(
                "HEAD", f"/{self.package_id}",
            )
        self.assertEqual((get_status, head_status), (200, 200))
        self.assertEqual(
            get_headers["content-length"], head_headers["content-length"],
        )
        self.assertTrue(get_raw)
        self.assertEqual(b"", head_raw)

    def test_options_and_mutation_methods_are_read_only(self):
        status, headers, raw = self._probe_request("OPTIONS")
        self.assertEqual(204, status)
        self.assertEqual("GET, HEAD, OPTIONS", headers["allow"])
        self.assertEqual("GET, HEAD, OPTIONS", headers[
            "access-control-allow-methods"
        ])
        self.assertEqual(b"", raw)
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            with self.subTest(method=method):
                status, headers, raw = self._probe_request(
                    method, f"/{self.package_id}",
                )
                self.assertEqual(405, status)
                self.assertEqual("GET, HEAD, OPTIONS", headers["allow"])
                self.assertEqual(
                    "method_not_allowed", json.loads(raw)["error"],
                )

    def test_nonlocal_host_is_rejected_before_application_dispatch(self):
        with patch(
            "autospine_workbench.body_sway_probe_routes."
            "BodySwayProbeApplication.list_packages",
        ) as listed:
            status, _, raw = self._probe_request(
                "GET", headers={"Host": "example.test"},
            )
        self.assertEqual(403, status)
        self.assertEqual("forbidden_host", json.loads(raw)["error"])
        listed.assert_not_called()

    def test_application_failures_are_sanitized_and_status_specific(self):
        private = f"private failure at {self.store.state}"
        cases = (
            (BodySwayProbeApplicationNotFound(private), 404,
             "body_sway_probe_not_found"),
            (BodySwayProbeApplicationHeadChanged(private), 409,
             "body_sway_probe_head_changed"),
            (BodySwayProbeApplicationUnavailable(private), 409,
             "body_sway_probe_unavailable"),
            (BodySwayProbeApplicationError(private), 500,
             "body_sway_probe_error"),
        )
        for exception, expected_status, expected_code in cases:
            with self.subTest(expected_code=expected_code), patch(
                "autospine_workbench.body_sway_probe_routes."
                "BodySwayProbeApplication.prepare",
                side_effect=exception,
            ):
                status, _, raw = self._probe_request(
                    "GET", f"/{self.package_id}",
                )
            self.assertEqual(expected_status, status)
            self.assertEqual(expected_code, json.loads(raw)["error"])
            self.assertNotIn(private, raw.decode("utf-8"))
            self.assertNotIn(str(self.store.state), raw.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
