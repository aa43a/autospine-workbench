"""Focused HTTP boundary tests for automatic P10.7b v2 execution."""

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

from autospine_workbench.p10_spine42_v3_runtime_http_security_v2 import (  # noqa: E402
    INTENT,
)
from autospine_workbench.p10_spine42_v3_runtime_manager_v2 import (  # noqa: E402
    P10Spine42V3RuntimeManagerV2Error,
)
from autospine_workbench.p10_spine42_v3_runtime_routes_v2 import (  # noqa: E402
    MAX_REQUEST_BYTES, dispatch_p10_spine42_v3_runtime_v2_get,
    dispatch_p10_spine42_v3_runtime_v2_post,
    is_p10_spine42_v3_runtime_v2_path,
    p10_spine42_v3_runtime_v2_allow_methods,
    send_p10_spine42_v3_runtime_v2_method_not_allowed,
)


SHA_A, SHA_B, SHA_C = (character * 64 for character in "abc")
BASE = ["api", "p10", "spine42-v3-runtime-v2"]


class P10Spine42V3RuntimeV2HttpTests(unittest.TestCase):
    def test_exact_routes_methods_and_zero_write_read_delegation(self):
        candidates, jobs, job = BASE + ["candidates"], BASE + ["jobs"], \
            BASE + ["jobs", SHA_C]
        self.assertTrue(is_p10_spine42_v3_runtime_v2_path(candidates))
        self.assertEqual("GET, HEAD, OPTIONS",
                         p10_spine42_v3_runtime_v2_allow_methods(candidates))
        self.assertEqual("POST, OPTIONS",
                         p10_spine42_v3_runtime_v2_allow_methods(jobs))
        self.assertEqual("GET, HEAD, OPTIONS",
                         p10_spine42_v3_runtime_v2_allow_methods(job))
        manager = _Manager()
        handler = _Handler("/api/p10/spine42-v3-runtime-v2/candidates")
        dispatch_p10_spine42_v3_runtime_v2_get(
            candidates, manager, handler,
        )
        handler.path += f"?spine_run_id={SHA_C}"
        dispatch_p10_spine42_v3_runtime_v2_get(
            candidates, manager, handler,
        )
        handler.path = f"/api/p10/spine42-v3-runtime-v2/jobs/{SHA_C}"
        dispatch_p10_spine42_v3_runtime_v2_get(job, manager, handler)
        self.assertEqual([
            ("catalog", None), ("catalog", SHA_C), ("get", SHA_C),
        ], manager.calls)

    def test_query_is_single_lowercase_sha_and_never_reaches_manager(self):
        for query in (
            "?spine_run_id=", f"?spine_run_id={SHA_A}&x=1",
            f"?x={SHA_A}", f"?spine_run_id={SHA_A.upper()}",
        ):
            with self.subTest(query=query):
                manager = _Manager()
                handler = _Handler(
                    "/api/p10/spine42-v3-runtime-v2/candidates" + query,
                )
                dispatch_p10_spine42_v3_runtime_v2_get(
                    BASE + ["candidates"], manager, handler,
                )
                self.assertEqual(400, handler.sent[-1][0])
                self.assertEqual([], manager.calls)
        manager = _Manager()
        handler = _Handler(
            f"/api/p10/spine42-v3-runtime-v2/jobs/{SHA_C}?x=1",
        )
        dispatch_p10_spine42_v3_runtime_v2_get(
            BASE + ["jobs", SHA_C], manager, handler,
        )
        self.assertEqual(400, handler.sent[-1][0])
        self.assertEqual([], manager.calls)

    def test_post_derives_automatic_only_for_exact_current_recommendation(self):
        for candidate, entry, expected in (
            (SHA_A, SHA_B, "automatic"),
            (SHA_C, SHA_B, "explicit"),
            (SHA_A, SHA_C, "explicit"),
        ):
            with self.subTest(expected=expected, candidate=candidate):
                payload = _payload(candidate=candidate, entry=entry)
                handler = _post_handler(payload)
                manager, sent = _Manager(), []
                dispatch_p10_spine42_v3_runtime_v2_post(
                    BASE + ["jobs"], handler, manager,
                    lambda status, value: sent.append((status, value)),
                )
                self.assertEqual(202, sent[-1][0])
                self.assertEqual(("catalog", None), manager.calls[0])
                self.assertEqual(
                    ("submit", payload, expected), manager.calls[1],
                )

    def test_post_rejects_headers_payload_and_oversize_before_submit(self):
        cases = []
        no_site = _post_handler(_payload())
        del no_site.headers["Sec-Fetch-Site"]
        cases.append((no_site, 403))
        wrong_origin = _post_handler(_payload())
        wrong_origin.headers.replace_header("Origin", "http://evil.invalid")
        cases.append((wrong_origin, 403))
        extra = _payload(); extra["selection_source"] = "automatic"
        cases.append((_post_handler(extra), 400))
        false_confirmation = _payload()
        false_confirmation["explicit_run_confirmation"] = False
        cases.append((_post_handler(false_confirmation), 400))
        too_large = _post_handler(_payload())
        too_large.headers.replace_header(
            "Content-Length", str(MAX_REQUEST_BYTES + 1),
        )
        cases.append((too_large, 413))
        for handler, expected in cases:
            with self.subTest(expected=expected):
                manager, sent = _Manager(), []
                dispatch_p10_spine42_v3_runtime_v2_post(
                    BASE + ["jobs"], handler, manager,
                    lambda status, value: sent.append((status, value)),
                )
                self.assertEqual(expected, sent[-1][0])
                self.assertEqual([], manager.calls)

    def test_failures_have_exact_path_free_statuses(self):
        handler = _Handler("/api/p10/spine42-v3-runtime-v2/unknown")
        dispatch_p10_spine42_v3_runtime_v2_get(
            BASE + ["unknown"], _Manager(), handler,
        )
        self.assertEqual((404, "runtime_v2_not_found"), _last(handler))

        for operation, expected in (("catalog", 409), ("get", 404)):
            manager = _Manager(failure=operation)
            parts = BASE + (["candidates"] if operation == "catalog" else
                            ["jobs", SHA_C])
            path = "/" + "/".join(parts)
            handler = _Handler(path)
            dispatch_p10_spine42_v3_runtime_v2_get(parts, manager, handler)
            self.assertEqual(expected, handler.sent[-1][0])
            self.assertNotIn(str(ROOT), repr(handler.sent[-1][1]))

        manager, sent = _Manager(failure="submit"), []
        dispatch_p10_spine42_v3_runtime_v2_post(
            BASE + ["jobs"], _post_handler(_payload()), manager,
            lambda status, value: sent.append((status, value)),
        )
        self.assertEqual(409, sent[-1][0])
        self.assertNotIn(str(ROOT), repr(sent[-1][1]))

    def test_wrong_method_publishes_exact_allow(self):
        handler = _Handler("/api/p10/spine42-v3-runtime-v2/jobs")
        send_p10_spine42_v3_runtime_v2_method_not_allowed(
            BASE + ["jobs"], handler,
        )
        self.assertEqual(405, handler.sent[-1][0])
        self.assertEqual("POST, OPTIONS", handler.sent[-1][2]["Allow"])


class _Manager:
    def __init__(self, *, failure=None):
        self.calls, self.failure = [], failure

    def catalog(self, continuation):
        self.calls.append(("catalog", continuation))
        if self.failure == "catalog":
            raise P10Spine42V3RuntimeManagerV2Error("private path")
        return {"selection": {
            "mode": "automatic", "recommended_candidate_id": SHA_A,
            "recommended_entry_sha256": SHA_B,
        }, "candidates": []}

    def get(self, job_id):
        self.calls.append(("get", job_id))
        if self.failure == "get":
            raise P10Spine42V3RuntimeManagerV2Error("private path")
        return {"job_id": job_id, "status": "running"}

    def submit(self, payload, *, selection_source):
        self.calls.append(("submit", payload, selection_source))
        if self.failure == "submit":
            raise P10Spine42V3RuntimeManagerV2Error("private path")
        return {"job_id": SHA_C, "status": "queued"}


class _Connection:
    def __init__(self):
        self.timeout = 10

    def gettimeout(self):
        return self.timeout

    def settimeout(self, value):
        self.timeout = value


class _Handler:
    def __init__(self, path, body=b"", headers=None):
        self.path, self.command = path, "GET"
        self.headers = headers or _headers(read=True)
        self.rfile, self.connection = BytesIO(body), _Connection()
        self.sent, self.close_connection = [], False

    def _send_visual_json(self, status, value):
        self.sent.append((status, value, {}))

    def _send_bytes(self, status, _body, _kind, **kwargs):
        self.sent.append((status, {}, kwargs.get("extra_headers", {})))


def _post_handler(payload):
    import json
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    handler = _Handler(
        "/api/p10/spine42-v3-runtime-v2/jobs", body,
        _headers(length=str(len(body))),
    )
    handler.command = "POST"
    return handler


def _headers(*, read=False, length="0"):
    headers = Message()
    headers["Host"] = "127.0.0.1:8765"
    headers["Sec-Fetch-Site"] = "same-origin"
    if not read:
        headers["Origin"] = "http://127.0.0.1:8765"
        headers["X-Autospine-Intent"] = INTENT
        headers["Content-Type"] = "application/json"
        headers["Content-Length"] = length
    return headers


def _payload(*, candidate=SHA_A, entry=SHA_B):
    return {
        "candidate_id": candidate, "entry_sha256": entry,
        "authorization_id": "auth-http-0001", "retry_of_job_id": None,
        "explicit_runtime_license_confirmation": True,
        "explicit_run_confirmation": True,
    }


def _last(handler):
    status, body, _headers = handler.sent[-1]
    return status, body["error"]


if __name__ == "__main__":
    unittest.main()
