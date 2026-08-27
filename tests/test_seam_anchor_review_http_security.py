"""Request-metadata tests for P10.5b seam-review mutations."""

from __future__ import annotations

from email.message import Message
from io import BytesIO
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.seam_anchor_review_http_security import (  # noqa: E402
    SeamAnchorReviewHttpSecurityError,
    require_seam_anchor_review_mutation_headers,
    seam_anchor_review_cors_origin,
)
from autospine_workbench.http_json_request import (  # noqa: E402
    HttpJsonRequestError,
    drain_bounded_request_body,
    read_json_object_request,
)
from tests.seam_anchor_review_http_helpers import (  # noqa: E402
    SeamAnchorReviewHttpFixture,
)


def request_headers(**overrides: str | None) -> Message:
    values = {
        "Host": "127.0.0.1:8765",
        "Origin": "http://127.0.0.1:8765",
        "X-Autospine-Intent": "seam-anchor-review",
        "Sec-Fetch-Site": "same-origin",
    }
    values.update(overrides)
    headers = Message()
    for name, value in values.items():
        if value is not None:
            headers[name] = value
    return headers


class _TimeoutConnection:
    def __init__(self) -> None:
        self.timeout = 10.0

    def gettimeout(self):
        return self.timeout

    def settimeout(self, value):
        self.timeout = value


def drain_handler(headers, raw):
    return type("Handler", (), {
        "headers": headers,
        "rfile": BytesIO(raw),
        "connection": _TimeoutConnection(),
        "close_connection": False,
    })()


class SeamAnchorReviewHttpSecurityTests(unittest.TestCase):
    def test_accepts_exact_ipv4_localhost_and_ipv6_authorities(self):
        for host in ("127.0.0.1:8765", "localhost:8765", "[::1]:8765"):
            with self.subTest(host=host):
                headers = request_headers(
                    Host=host, Origin=f"http://{host}",
                    **{"Sec-Fetch-Site": "none"},
                )
                require_seam_anchor_review_mutation_headers(headers)
                self.assertEqual(
                    f"http://{host}", seam_anchor_review_cors_origin(headers)
                )

    def test_rejects_missing_cross_port_foreign_and_userinfo(self):
        cases = (
            request_headers(Origin=None),
            request_headers(Origin="http://127.0.0.1:8766"),
            request_headers(
                Host="attacker.example", Origin="http://attacker.example"
            ),
            request_headers(
                Host="user@127.0.0.1:8765",
                Origin="http://user@127.0.0.1:8765",
            ),
        )
        for headers in cases:
            with self.subTest(headers=list(headers.items())), \
                    self.assertRaises(SeamAnchorReviewHttpSecurityError):
                require_seam_anchor_review_mutation_headers(headers)
            self.assertIsNone(seam_anchor_review_cors_origin(headers))

    def test_rejects_wrong_intent_fetch_site_and_duplicate_headers(self):
        wrong_intent = request_headers(
            **{"X-Autospine-Intent": "body-sway-visual-review"}
        )
        cross_site = request_headers(**{"Sec-Fetch-Site": "cross-site"})
        duplicate = request_headers()
        duplicate["Origin"] = "http://127.0.0.1:8765"
        for headers in (wrong_intent, cross_site, duplicate):
            with self.subTest(headers=list(headers.items())), \
                    self.assertRaises(SeamAnchorReviewHttpSecurityError):
                require_seam_anchor_review_mutation_headers(headers)

    def test_cors_never_reflects_unpaired_loopback_origin(self):
        self.assertIsNone(seam_anchor_review_cors_origin(
            request_headers(Origin="http://localhost:9999")
        ))
        self.assertIsNone(seam_anchor_review_cors_origin(
            request_headers(Origin=None)
        ))


class SeamAnchorReviewStaticSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = SeamAnchorReviewHttpFixture()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.fixture.close()

    def test_review_page_has_a_locked_down_content_security_policy(self):
        status, headers, raw = self.fixture.request(
            "GET", "/seam-anchor-review.html"
        )
        self.assertEqual(200, status)
        self.assertTrue(raw)
        policy = headers["content-security-policy"]
        for directive in (
            "default-src 'self'", "object-src 'none'", "base-uri 'none'",
            "frame-ancestors 'none'", "connect-src 'self'",
            "img-src 'self' data:", "script-src 'self'", "style-src 'self'",
            "form-action 'self'",
        ):
            self.assertIn(directive, policy)

    def test_options_cors_and_wrong_methods_are_narrow(self):
        candidate_sha, _ = self.fixture.prepare()
        endpoint = f"{self.fixture.base}/candidates/{candidate_sha}/decisions"
        same = self.fixture.mutation_headers()
        status, headers, raw = self.fixture.request(
            "OPTIONS", endpoint, headers=same
        )
        self.assertEqual(204, status)
        self.assertEqual("POST, OPTIONS", headers["allow"])
        self.assertEqual(
            same["Origin"], headers["access-control-allow-origin"]
        )
        self.assertIn(
            "X-Autospine-Intent", headers["access-control-allow-headers"]
        )
        self.assertEqual(b"", raw)

        for method, resource, allow in (
            ("PUT", endpoint, "POST, OPTIONS"),
            ("GET", endpoint, "POST, OPTIONS"),
            ("POST", f"{self.fixture.base}/candidate", "GET, HEAD, OPTIONS"),
        ):
            with self.subTest(method=method):
                status, headers, value = self.fixture.json_request(
                    method, resource
                )
                self.assertEqual(405, status)
                self.assertEqual(allow, headers["allow"])
                self.assertEqual("method_not_allowed", value["error"])

        foreign = self.fixture.mutation_headers(
            Origin=f"http://{self.fixture.host}:{self.fixture.port + 1}"
        )
        status, headers, _ = self.fixture.request(
            "OPTIONS", endpoint, headers=foreign
        )
        self.assertEqual(204, status)
        self.assertNotIn("access-control-allow-origin", headers)

        status, _, value = self.fixture.json_request(
            "OPTIONS", f"{self.fixture.base}/unknown-resource"
        )
        self.assertEqual(404, status)
        self.assertEqual("seam_anchor_review_not_found", value["error"])


class StrictJsonRequestMetadataTests(unittest.TestCase):
    def test_rejected_body_drain_consumes_only_one_safe_finite_body(self):
        headers = Message()
        headers["Content-Length"] = "2"
        handler = drain_handler(headers, b"{}next")
        self.assertTrue(drain_bounded_request_body(handler, maximum_bytes=2))
        self.assertEqual(b"next", handler.rfile.read())
        self.assertFalse(handler.close_connection)
        self.assertEqual(10.0, handler.connection.timeout)

    def test_rejected_body_drain_never_guesses_ambiguous_framing(self):
        cases = []
        duplicate = Message()
        duplicate["Content-Length"] = "2"
        duplicate["Content-Length"] = "2"
        cases.append(duplicate)
        chunked = Message()
        chunked["Transfer-Encoding"] = "chunked"
        chunked["Content-Length"] = "2"
        cases.append(chunked)
        invalid = Message()
        invalid["Content-Length"] = " 2"
        cases.append(invalid)
        oversized = Message()
        oversized["Content-Length"] = "3"
        cases.append(oversized)
        for index, headers in enumerate(cases):
            handler = drain_handler(headers, b"{}")
            with self.subTest(index=index):
                self.assertFalse(drain_bounded_request_body(
                    handler, maximum_bytes=2
                ))
                self.assertEqual(0, handler.rfile.tell())
                self.assertTrue(handler.close_connection)

    def test_rejected_body_drain_short_body_fails_closed(self):
        headers = Message()
        headers["Content-Length"] = "3"
        handler = drain_handler(headers, b"{}")
        self.assertFalse(drain_bounded_request_body(
            handler, maximum_bytes=3
        ))
        self.assertTrue(handler.close_connection)
        self.assertEqual(10.0, handler.connection.timeout)

    def test_rejects_duplicate_content_headers(self):
        for name, value in (
            ("Content-Type", "application/json"),
            ("Content-Length", "2"),
        ):
            headers = Message()
            headers["Content-Type"] = "application/json"
            headers["Content-Length"] = "2"
            headers[name] = value
            handler = type("Handler", (), {
                "headers": headers, "rfile": BytesIO(b"{}"),
            })()
            with self.subTest(name=name), self.assertRaises(
                HttpJsonRequestError
            ):
                read_json_object_request(handler)

    def test_rejects_noncanonical_content_length(self):
        headers = Message()
        headers["Content-Type"] = "application/json"
        headers["Content-Length"] = " 2"
        handler = type("Handler", (), {
            "headers": headers, "rfile": BytesIO(b"{}"),
        })()
        with self.assertRaises(HttpJsonRequestError) as raised:
            read_json_object_request(handler)
        self.assertEqual("length_required", raised.exception.code)

    def test_deep_json_is_a_stable_invalid_request(self):
        raw = b"[" * 2000 + b"]" * 2000
        headers = Message()
        headers["Content-Type"] = "application/json"
        headers["Content-Length"] = str(len(raw))
        handler = type("Handler", (), {
            "headers": headers, "rfile": BytesIO(raw),
        })()
        with self.assertRaises(HttpJsonRequestError) as raised:
            read_json_object_request(handler)
        self.assertEqual("invalid_json", raised.exception.code)

    def test_finite_syntax_that_overflows_float_is_rejected(self):
        raw = b'{"value":1e9999}'
        headers = Message()
        headers["Content-Type"] = "application/json"
        headers["Content-Length"] = str(len(raw))
        handler = type("Handler", (), {
            "headers": headers, "rfile": BytesIO(raw),
        })()
        with self.assertRaises(HttpJsonRequestError) as raised:
            read_json_object_request(handler)
        self.assertEqual("invalid_json", raised.exception.code)


if __name__ == "__main__":
    unittest.main()
