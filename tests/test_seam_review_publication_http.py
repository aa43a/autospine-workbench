"""Live HTTP safety for package-bound P10.5c publication."""

from __future__ import annotations

import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest

from autospine_workbench.server import create_server
from autospine_workbench.seam_review_publication import INTENT_VALUE
from tests.seam_review_publication_helpers import (
    SeamReviewPublicationFixture,
)
from tests.test_project_store import StoreFixture


class SeamReviewPublicationHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        root = Path(cls.temporary.name)
        cls.fixture = SeamReviewPublicationFixture(root / "exact")
        store = StoreFixture(root / "server")
        cls.server = create_server(
            "127.0.0.1", 0, store.workspace,
            state_root=cls.fixture.state,
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

    def path(self):
        return (
            "/api/motion-policy/review-packages/"
            f"{self.fixture.package_a}/seam-publications"
        )

    def request(self, method, *, payload=None, headers=None):
        connection = http.client.HTTPConnection(
            self.host, self.port, timeout=30,
        )
        body = None if payload is None else json.dumps(payload).encode()
        connection.request(method, self.path(), body=body, headers=headers or {})
        response = connection.getresponse()
        raw = response.read()
        result = response.status, {
            key.lower(): value for key, value in response.getheaders()
        }, raw
        connection.close()
        return result

    def mutation_headers(self, **changes):
        values = {
            "Host": f"{self.host}:{self.port}",
            "Origin": f"http://{self.host}:{self.port}",
            "Content-Type": "application/json",
            "X-Autospine-Intent": INTENT_VALUE,
        }
        values.update(changes)
        return values

    def test_post_options_and_wrong_methods_are_narrow(self):
        status, headers, raw = self.request(
            "POST", payload=self.fixture.request(),
            headers=self.mutation_headers(),
        )
        self.assertEqual(200, status)
        self.assertEqual("passed", json.loads(raw)["status"])
        self.assertEqual("same-origin", headers[
            "cross-origin-resource-policy"
        ])
        option, option_headers, option_raw = self.request("OPTIONS")
        self.assertEqual(204, option)
        self.assertEqual("POST, OPTIONS", option_headers["allow"])
        self.assertEqual(b"", option_raw)
        for method in ("GET", "HEAD", "PUT", "PATCH", "DELETE"):
            denied, denied_headers, _raw = self.request(method)
            self.assertEqual(405, denied, method)
            self.assertEqual("POST, OPTIONS", denied_headers["allow"])

    def test_origin_intent_and_payload_are_strict(self):
        cases = (
            ({"Content-Type": "application/json"}, "forbidden_origin"),
            (self.mutation_headers(**{
                "X-Autospine-Intent": "wrong",
            }), "forbidden_intent"),
        )
        for headers, code in cases:
            status, _, raw = self.request(
                "POST", payload=self.fixture.request(), headers=headers,
            )
            self.assertEqual(403, status)
            self.assertEqual(code, json.loads(raw)["error"])
        status, _, raw = self.request(
            "POST", payload=self.fixture.request() | {"extra": True},
            headers=self.mutation_headers(),
        )
        self.assertEqual(400, status)
        self.assertEqual(
            "invalid_seam_review_publication_request",
            json.loads(raw)["error"],
        )


if __name__ == "__main__":
    unittest.main()
