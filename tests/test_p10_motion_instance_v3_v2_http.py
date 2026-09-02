from __future__ import annotations

from email.message import Message
from io import BytesIO
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
for item in (ROOT, ROOT / "src"):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.p10_motion_instance_v3_v2_routes import (
    dispatch_p10_motion_instance_v3_v2_get,
    dispatch_p10_motion_instance_v3_v2_post,
    is_p10_motion_instance_v3_v2_path,
    p10_motion_instance_v3_v2_allow_methods,
)


class MotionInstanceV3V2HttpTests(unittest.TestCase):
    def setUp(self):
        self.base = [
            "api", "p10", "runtime-capture", "jobs", "a" * 64,
            "visual-review-v2", "safety-analysis-v2", "runs", "b" * 64,
            "dynamic-seam-v2", "runs", "c" * 64,
            "motion-instance-v3-v2",
        ]

    def test_routes_bind_all_three_upstreams_and_methods(self):
        self.assertTrue(is_p10_motion_instance_v3_v2_path(self.base))
        self.assertEqual("GET, HEAD, OPTIONS",
                         p10_motion_instance_v3_v2_allow_methods(self.base))
        self.assertEqual("POST, OPTIONS",
                         p10_motion_instance_v3_v2_allow_methods(
                             self.base + ["runs"]
                         ))
        self.assertEqual("GET, OPTIONS",
                         p10_motion_instance_v3_v2_allow_methods(
                             self.base + ["runs", "d" * 64, "result"]
                         ))
        manager, handler = _Manager(), _Handler(_headers(read=True))
        dispatch_p10_motion_instance_v3_v2_get(
            self.base, manager, handler,
        )
        self.assertEqual(("entry", "a" * 64, "b" * 64, "c" * 64),
                         manager.calls[-1])
        dispatch_p10_motion_instance_v3_v2_get(
            self.base + ["runs", "d" * 64], manager, handler,
        )
        self.assertEqual(("get", "a" * 64, "b" * 64, "c" * 64,
                          "d" * 64), manager.calls[-1])

    def test_empty_post_is_automatic_and_nonempty_is_rejected(self):
        manager, sent = _Manager(), []
        dispatch_p10_motion_instance_v3_v2_post(
            self.base + ["runs"], _Handler(_headers()), manager,
            lambda status, body: sent.append((status, body)),
        )
        self.assertEqual(202, sent[-1][0])
        self.assertEqual(("submit", "a" * 64, "b" * 64, "c" * 64),
                         manager.calls[-1])
        handler = _Handler(_headers(length="13"), b'{"sha":"x"}')
        dispatch_p10_motion_instance_v3_v2_post(
            self.base + ["runs"], handler, manager,
            lambda status, body: sent.append((status, body)),
        )
        self.assertEqual(400, sent[-1][0])

    def test_cross_site_origin_duplicate_intent_and_userinfo_fail(self):
        cases = []
        cross = _headers(read=True)
        cross.replace_header("Sec-Fetch-Site", "cross-site")
        read_handler = _Handler(cross)
        dispatch_p10_motion_instance_v3_v2_get(
            self.base, _Manager(), read_handler,
        )
        self.assertEqual(403, read_handler.sent[-1][0])
        origin = _headers()
        origin.replace_header("Origin", "http://evil.invalid")
        cases.append(origin)
        duplicate = _headers()
        duplicate["X-Autospine-Intent"] = (
            "p10-body-sway-motion-instance-v3-v2"
        )
        cases.append(duplicate)
        userinfo = _headers()
        userinfo.replace_header("Host", "user@127.0.0.1:8765")
        cases.append(userinfo)
        for headers in cases:
            sent = []
            dispatch_p10_motion_instance_v3_v2_post(
                self.base + ["runs"], _Handler(headers), _Manager(),
                lambda status, body: sent.append((status, body)),
            )
            self.assertEqual(403, sent[0][0])


class _Manager:
    def __init__(self):
        self.calls = []

    def entry(self, job, safety, dynamic):
        self.calls.append(("entry", job, safety, dynamic))
        return {"ok": True, "status": "ready"}

    def submit(self, job, safety, dynamic):
        self.calls.append(("submit", job, safety, dynamic))
        return {"ok": True, "status": "queued"}

    def get(self, job, safety, dynamic, run):
        self.calls.append(("get", job, safety, dynamic, run))
        return {"ok": True, "status": "running"}

    def result(self, job, safety, dynamic, run):
        self.calls.append(("result", job, safety, dynamic, run))
        return {"ok": True, "status": "completed"}


class _Handler:
    def __init__(self, headers, body=b"{}"):
        self.headers, self.command = headers, "GET"
        self.rfile, self.sent = BytesIO(body), []

    def _send_visual_json(self, status, body):
        self.sent.append((status, body))

    def _send_bytes(self, status, *_args, **_kwargs):
        self.sent.append((status, {}))


def _headers(*, read=False, length="2"):
    headers = Message()
    headers["Host"] = "127.0.0.1:8765"
    headers["Sec-Fetch-Site"] = "same-origin"
    if not read:
        headers["Origin"] = "http://127.0.0.1:8765"
        headers["X-Autospine-Intent"] = (
            "p10-body-sway-motion-instance-v3-v2"
        )
        headers["Content-Type"] = "application/json"
        headers["Content-Length"] = length
    return headers


if __name__ == "__main__":
    unittest.main()
