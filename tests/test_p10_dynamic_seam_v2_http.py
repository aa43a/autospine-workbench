from __future__ import annotations

from email.message import Message
from io import BytesIO
from types import SimpleNamespace
import unittest

from autospine_workbench.p10_dynamic_seam_v2_routes import (
    dispatch_p10_dynamic_seam_v2_get,
    dispatch_p10_dynamic_seam_v2_post,
    is_p10_dynamic_seam_v2_path,
    p10_dynamic_seam_v2_allow_methods,
)


class DynamicSeamV2HttpTests(unittest.TestCase):
    def setUp(self):
        self.base = [
            "api", "p10", "runtime-capture", "jobs", "a" * 64,
            "visual-review-v2", "safety-analysis-v2", "runs", "b" * 64,
            "dynamic-seam-v2",
        ]

    def test_specific_route_and_options_policy(self):
        self.assertTrue(is_p10_dynamic_seam_v2_path(self.base))
        self.assertEqual(p10_dynamic_seam_v2_allow_methods(self.base),
                         "GET, HEAD, OPTIONS")
        self.assertEqual(p10_dynamic_seam_v2_allow_methods(self.base + ["runs"]),
                         "POST, OPTIONS")
        self.assertEqual(p10_dynamic_seam_v2_allow_methods(
            self.base + ["runs", "c" * 64, "result"]
        ), "GET, OPTIONS")

    def test_get_entry_and_poll_bind_both_upstream_ids(self):
        manager, handler = _Manager(), _Handler(_headers(read=True))
        self.assertTrue(dispatch_p10_dynamic_seam_v2_get(
            self.base, manager, handler,
        ))
        self.assertEqual(manager.calls[0], ("entry", "a" * 64, "b" * 64))
        dispatch_p10_dynamic_seam_v2_get(
            self.base + ["runs", "c" * 64], manager, handler,
        )
        self.assertEqual(manager.calls[-1],
                         ("get", "a" * 64, "b" * 64, "c" * 64))

    def test_post_requires_same_origin_and_exact_intent(self):
        manager = _Manager()
        sent = []
        handler = _Handler(_headers())
        self.assertTrue(dispatch_p10_dynamic_seam_v2_post(
            self.base + ["runs"], handler, manager,
            lambda status, body: sent.append((status, body)),
        ))
        self.assertEqual(sent[0][0], 202)
        self.assertEqual(manager.calls[-1],
                         ("submit", "a" * 64, "b" * 64))
        denied = _Handler(_headers(origin="http://evil.invalid"))
        sent.clear()
        dispatch_p10_dynamic_seam_v2_post(
            self.base + ["runs"], denied, manager,
            lambda status, body: sent.append((status, body)),
        )
        self.assertEqual(sent[0][0], 403)

    def test_cross_site_read_and_wrong_method_are_rejected(self):
        headers = _headers(read=True)
        headers.replace_header("Sec-Fetch-Site", "cross-site")
        handler = _Handler(headers)
        dispatch_p10_dynamic_seam_v2_get(self.base, _Manager(), handler)
        self.assertEqual(handler.sent[-1][0], 403)
        self.assertEqual(p10_dynamic_seam_v2_allow_methods(self.base + ["runs"]),
                         "POST, OPTIONS")

    def test_duplicate_intent_userinfo_and_whitespace_fail_closed(self):
        cases = []
        duplicate = _headers()
        duplicate["X-Autospine-Intent"] = "p10-body-sway-dynamic-seam-v2"
        cases.append(duplicate)
        userinfo = _headers()
        userinfo.replace_header("Host", "user@127.0.0.1:8765")
        cases.append(userinfo)
        whitespace = _headers()
        whitespace.replace_header("X-Autospine-Intent",
                                  " p10-body-sway-dynamic-seam-v2")
        cases.append(whitespace)
        for headers in cases:
            sent = []
            dispatch_p10_dynamic_seam_v2_post(
                self.base + ["runs"], _Handler(headers), _Manager(),
                lambda status, body: sent.append((status, body)),
            )
            self.assertEqual(sent[0][0], 403)


class _Manager:
    def __init__(self):
        self.calls = []

    def entry(self, job, safety):
        self.calls.append(("entry", job, safety))
        return {"ok": True, "status": "ready"}

    def submit(self, job, safety):
        self.calls.append(("submit", job, safety))
        return {"ok": True, "status": "queued"}

    def get(self, job, safety, run):
        self.calls.append(("get", job, safety, run))
        return {"ok": True, "status": "running"}

    def result(self, job, safety, run):
        return {"ok": True, "status": "completed"}


class _Handler:
    def __init__(self, headers):
        self.headers, self.command = headers, "GET"
        self.rfile, self.sent = BytesIO(b"{}"), []

    def _send_visual_json(self, status, body):
        self.sent.append((status, body))

    def _send_bytes(self, status, *_args, **_kwargs):
        self.sent.append((status, {}))


def _headers(*, read=False, origin="http://127.0.0.1:8765"):
    headers = Message()
    headers["Host"] = "127.0.0.1:8765"
    headers["Sec-Fetch-Site"] = "same-origin"
    if not read:
        headers["Origin"] = origin
        headers["X-Autospine-Intent"] = "p10-body-sway-dynamic-seam-v2"
        headers["Content-Type"] = "application/json"
        headers["Content-Length"] = "2"
    return headers


if __name__ == "__main__":
    unittest.main()
