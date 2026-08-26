"""Request-metadata tests for body-sway visual-review mutations."""

from __future__ import annotations

from email.message import Message
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.body_sway_visual_review_http_security import (  # noqa: E402
    BodySwayVisualReviewHttpSecurityError,
    require_visual_review_mutation_headers,
    visual_review_cors_origin,
)


def request_headers(**overrides: str | None) -> Message:
    values = {
        "Host": "127.0.0.1:8765",
        "Origin": "http://127.0.0.1:8765",
        "X-Autospine-Intent": "body-sway-visual-review",
        "Sec-Fetch-Site": "same-origin",
    }
    values.update(overrides)
    headers = Message()
    for name, value in values.items():
        if value is not None:
            headers[name] = value
    return headers


class BodySwayVisualReviewHttpSecurityTests(unittest.TestCase):
    def test_accepts_exact_ipv4_localhost_and_ipv6_authorities(self) -> None:
        for host in ("127.0.0.1:8765", "localhost:8765", "[::1]:8765"):
            with self.subTest(host=host):
                headers = request_headers(
                    Host=host, Origin=f"http://{host}",
                    **{"Sec-Fetch-Site": "none"},
                )
                require_visual_review_mutation_headers(headers)
                self.assertEqual(
                    f"http://{host}", visual_review_cors_origin(headers)
                )

    def test_rejects_missing_cross_port_and_foreign_authority(self) -> None:
        cases = (
            request_headers(Origin=None),
            request_headers(Origin="http://127.0.0.1:8766"),
            request_headers(Host="attacker.example", Origin="http://attacker.example"),
            request_headers(Host="user@127.0.0.1:8765", Origin="http://user@127.0.0.1:8765"),
        )
        for headers in cases:
            with self.subTest(headers=list(headers.items())), self.assertRaises(
                BodySwayVisualReviewHttpSecurityError
            ):
                require_visual_review_mutation_headers(headers)
            self.assertIsNone(visual_review_cors_origin(headers))

    def test_rejects_wrong_intent_fetch_site_and_duplicate_headers(self) -> None:
        wrong_intent = request_headers(
            **{"X-Autospine-Intent": "override-review"}
        )
        cross_site = request_headers(**{"Sec-Fetch-Site": "cross-site"})
        duplicate = request_headers()
        duplicate["Origin"] = "http://127.0.0.1:8765"
        for headers in (wrong_intent, cross_site, duplicate):
            with self.subTest(headers=list(headers.items())), self.assertRaises(
                BodySwayVisualReviewHttpSecurityError
            ):
                require_visual_review_mutation_headers(headers)

    def test_cors_never_reflects_an_unpaired_loopback_origin(self) -> None:
        headers = request_headers(Origin="http://localhost:9999")
        self.assertIsNone(visual_review_cors_origin(headers))
        headers = request_headers(Origin=None)
        self.assertIsNone(visual_review_cors_origin(headers))


if __name__ == "__main__":
    unittest.main()
