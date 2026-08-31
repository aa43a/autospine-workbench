"""HTTP safety tests for pending P9 draft discovery and policy promotion."""

from __future__ import annotations

import http.client
import json
from pathlib import Path
from types import SimpleNamespace
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

from autospine_workbench.current_project_chain import (  # noqa: E402
    CurrentProjectChain,
)
from autospine_workbench.server import create_server  # noqa: E402
from tests.test_project_store import StoreFixture  # noqa: E402


DRAFT = "a" * 64
PACKAGE = "b" * 64
CURRENT = {
    "sample": CurrentProjectChain("sample", "1" * 64, "2" * 64),
}


class MotionPolicyReviewDraftHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.store = StoreFixture(Path(cls.temporary.name))
        cls.server = create_server(
            "127.0.0.1", 0, cls.store.workspace,
            state_root=cls.store.state,
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

    def request(
        self, method: str, suffix: str = "", body=None,
        *, omit_origin: bool = False, **headers,
    ):
        connection = http.client.HTTPConnection(self.host, self.port, timeout=10)
        encoded = None if body is None else json.dumps(body).encode("utf-8")
        request_headers = {"Sec-Fetch-Site": "same-origin"}
        if not omit_origin:
            request_headers["Origin"] = f"http://{self.host}:{self.port}"
        if encoded is not None:
            request_headers["Content-Type"] = "application/json"
        request_headers.update(headers)
        connection.request(
            method, f"/api/motion-policy/review-drafts{suffix}",
            body=encoded, headers=request_headers,
        )
        response = connection.getresponse()
        raw = response.read()
        result = response.status, {
            key.lower(): value for key, value in response.getheaders()
        }, raw
        connection.close()
        return result

    def test_get_list_detail_and_options_are_path_free(self):
        listing = {
            "format": "autospine-motion-policy-draft-list",
            "format_version": 1,
            "count": 0,
            "skipped_count": 0,
            "recommended_draft_id": None,
            "drafts": [],
        }
        detail = {"format": "test-detail", "draft_id": DRAFT}
        with patch(
            "autospine_workbench.motion_policy_review_draft_routes."
            "rebuild_current_project_chains", return_value=CURRENT,
        ), patch(
            "autospine_workbench.motion_policy_review_draft_routes."
            "list_p9_review_drafts", return_value=listing,
        ), patch(
            "autospine_workbench.motion_policy_review_draft_routes."
            "get_p9_review_draft", return_value=detail,
        ):
            status, headers, raw = self.request("GET")
            self.assertEqual(200, status)
            self.assertEqual(listing, json.loads(raw))
            self.assertEqual("same-origin", headers["cross-origin-resource-policy"])
            status, _, raw = self.request("GET", f"/{DRAFT}")
            self.assertEqual(200, status)
            self.assertEqual(detail, json.loads(raw))
            status, headers, raw = self.request("OPTIONS", f"/{DRAFT}")
            self.assertEqual(204, status)
            self.assertEqual("GET, HEAD, OPTIONS", headers["allow"])
            self.assertEqual(b"", raw)

    def test_explicit_post_runs_prepare_then_double_snapshot_then_publish(self):
        request = {"explicit_confirmation": True}
        prepared = SimpleNamespace(draft_id=DRAFT, project_id="sample")
        receipt = {
            "format": "autospine-depth-policy-draft-adoption-receipt",
            "format_version": 1,
            "status": "passed",
            "draft_id": DRAFT,
            "project_id": "sample",
            "motion_id": "wave-r6-pabcdef",
            "clip_id": "wave-left",
            "reused": False,
            "policy_sha256": "3" * 64,
            "depth_candidates_sha256": "4" * 64,
            "package_id": PACKAGE,
        }
        with patch(
            "autospine_workbench.motion_policy_review_draft_routes."
            "rebuild_current_project_chains", side_effect=[CURRENT, CURRENT],
        ) as snapshots, patch(
            "autospine_workbench.motion_policy_review_draft_routes."
            "prepare_p9_draft_policy_adoption", return_value=prepared,
        ) as prepare, patch(
            "autospine_workbench.motion_policy_review_draft_routes."
            "publish_p9_draft_policy_adoption", return_value=receipt,
        ) as publish:
            status, _, raw = self.request(
                "POST", f"/{DRAFT}/policy-adoptions", request,
                **{"X-Autospine-Intent": "depth-policy-draft-adoption-v1"},
            )
        self.assertEqual(200, status)
        self.assertEqual(receipt, json.loads(raw))
        self.assertEqual(2, snapshots.call_count)
        prepare.assert_called_once()
        publish.assert_called_once()
        self.assertNotIn(str(self.store.state), raw.decode("utf-8"))

    def test_list_scope_hashes_and_reads_only_the_requested_project(self):
        listing = {
            "format": "autospine-motion-policy-draft-list",
            "format_version": 1,
            "count": 0,
            "skipped_count": 0,
            "recommended_draft_id": None,
            "drafts": [],
        }
        current = {"fixture-project": CurrentProjectChain(
            "fixture-project", "1" * 64, "2" * 64,
        )}
        with patch(
            "autospine_workbench.motion_policy_review_draft_routes."
            "rebuild_current_project_chains", return_value=current,
        ) as rebuild, patch(
            "autospine_workbench.motion_policy_review_draft_routes."
            "list_p9_review_drafts", return_value=listing,
        ) as drafts:
            status, _, raw = self.request(
                "GET", "?project_id=fixture-project",
            )
        self.assertEqual(200, status)
        self.assertEqual(listing, json.loads(raw))
        self.assertEqual(2, rebuild.call_count)
        self.assertTrue(all(
            call.args[1] == ("fixture-project",)
            for call in rebuild.call_args_list
        ))
        self.assertEqual(
            frozenset({"fixture-project"}),
            drafts.call_args.kwargs["project_ids"],
        )

        detail = {"format": "test-detail", "draft_id": DRAFT}
        with patch(
            "autospine_workbench.motion_policy_review_draft_routes."
            "rebuild_current_project_chains", return_value=current,
        ), patch(
            "autospine_workbench.motion_policy_review_draft_routes."
            "get_p9_review_draft", return_value=detail,
        ) as exact:
            status, _, raw = self.request(
                "GET", f"/{DRAFT}?project_id=fixture-project",
            )
        self.assertEqual(200, status)
        self.assertEqual(detail, json.loads(raw))
        self.assertEqual(
            frozenset({"fixture-project"}),
            exact.call_args.kwargs["project_ids"],
        )

        status, _, raw = self.request("GET", "?project_id=../bad")
        self.assertEqual(400, status)
        self.assertEqual(
            "invalid_motion_policy_project_scope", json.loads(raw)["error"],
        )

    def test_wrong_intent_is_forbidden_before_prepare(self):
        with patch(
            "autospine_workbench.motion_policy_review_draft_routes."
            "prepare_p9_draft_policy_adoption",
        ) as prepare:
            status, _, raw = self.request(
                "POST", f"/{DRAFT}/policy-adoptions", {},
                **{"X-Autospine-Intent": "wrong"},
            )
        self.assertEqual(403, status)
        self.assertEqual("forbidden_intent", json.loads(raw)["error"])
        prepare.assert_not_called()

    def test_post_security_and_body_limits_fail_before_prepare(self):
        intent = {"X-Autospine-Intent": "depth-policy-draft-adoption-v1"}
        cases = (
            ({"omit_origin": True, **intent}, 403, "forbidden_origin"),
            ({"Origin": "http://127.0.0.1:9", **intent}, 403, "forbidden_origin"),
            ({"Sec-Fetch-Site": "cross-site", **intent}, 403, "forbidden_fetch_site"),
            ({"Content-Type": "text/plain", **intent}, 415, "unsupported_media_type"),
        )
        with patch(
            "autospine_workbench.motion_policy_review_draft_routes."
            "prepare_p9_draft_policy_adoption",
        ) as prepare:
            for headers, expected_status, expected_error in cases:
                with self.subTest(expected_error=expected_error):
                    status, _, raw = self.request(
                        "POST", f"/{DRAFT}/policy-adoptions", {}, **headers,
                    )
                    self.assertEqual(expected_status, status)
                    self.assertEqual(expected_error, json.loads(raw)["error"])
            status, _, raw = self.request(
                "POST", f"/{DRAFT}/policy-adoptions",
                {"padding": "x" * (17 * 1024)}, **intent,
            )
        self.assertEqual(413, status)
        self.assertEqual("request_too_large", json.loads(raw)["error"])
        prepare.assert_not_called()

    def test_changed_chain_prevents_publication(self):
        changed = {
            "sample": CurrentProjectChain("sample", "1" * 64, "f" * 64),
        }
        with patch(
            "autospine_workbench.motion_policy_review_draft_routes."
            "rebuild_current_project_chains", side_effect=[CURRENT, changed],
        ), patch(
            "autospine_workbench.motion_policy_review_draft_routes."
            "prepare_p9_draft_policy_adoption",
            return_value=SimpleNamespace(draft_id=DRAFT, project_id="sample"),
        ), patch(
            "autospine_workbench.motion_policy_review_draft_routes."
            "publish_p9_draft_policy_adoption",
        ) as publish:
            status, _, raw = self.request(
                "POST", f"/{DRAFT}/policy-adoptions", {},
                **{"X-Autospine-Intent": "depth-policy-draft-adoption-v1"},
            )
        self.assertEqual(409, status)
        self.assertEqual("motion_policy_project_chain_changed", json.loads(raw)["error"])
        publish.assert_not_called()


if __name__ == "__main__":
    unittest.main()
