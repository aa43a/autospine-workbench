"""Live HTTP single-flight regression for P10.5b evidence images."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import http.client
import json
from pathlib import Path
from threading import Barrier, Thread
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench import seam_anchor_review_replay_cache as replay  # noqa: E402
from autospine_workbench.server import create_server  # noqa: E402
from tests.test_seam_anchor_review_http_evidence_e2e import (  # noqa: E402
    _LiveEvidenceFixture,
)


class SeamAnchorReviewReplayCacheHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = _LiveEvidenceFixture()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.fixture.close()

    def test_eighteen_first_image_requests_replay_each_source_once(self):
        status, _, raw = self.fixture.request(
            "GET", f"{self.fixture.base}/candidate"
        )
        self.assertEqual(200, status)
        envelope = json.loads(raw.decode("utf-8"))
        image_url = envelope["attachment_images"][0]["url"]

        store = self.fixture.server.project_store
        # A cold server must acquire the state root's exclusive manager lease.
        # Stop the fixture server before testing a fresh replay cache.
        self.fixture.server.shutdown()
        self.fixture.server.server_close()
        self.fixture.thread.join(timeout=5)
        self.assertFalse(self.fixture.thread.is_alive())
        server = create_server(
            "127.0.0.1", 0, store.workspace_root,
            web_root=ROOT / "web", state_root=self.fixture.state,
        )
        thread = Thread(target=server.serve_forever, daemon=True)
        real_candidate_loader = replay.load_bound_seam_anchor_review_candidate
        real_source_loader = replay.VerifiedMeshSourceReader.load

        def candidate_loader(*arguments):
            return real_candidate_loader(*arguments)

        def source_loader(reader, *arguments):
            return real_source_loader(reader, *arguments)

        try:
            with patch.object(
                replay, "load_bound_seam_anchor_review_candidate",
                side_effect=candidate_loader,
            ) as candidate_replay, patch.object(
                replay.VerifiedMeshSourceReader, "load", autospec=True,
                side_effect=source_loader,
            ) as source_replay:
                thread.start()
                host, port = server.server_address[:2]
                barrier = Barrier(18)

                def request(_index):
                    barrier.wait(timeout=10)
                    connection = http.client.HTTPConnection(
                        host, port, timeout=30
                    )
                    connection.request("GET", image_url)
                    response = connection.getresponse()
                    result = response.status, response.read()
                    connection.close()
                    return result

                with ThreadPoolExecutor(max_workers=18) as pool:
                    results = list(pool.map(request, range(18)))

                self.assertTrue(all(status == 200 for status, _ in results))
                self.assertTrue(all(body == results[0][1]
                                    for _, body in results))
                self.assertEqual(1, candidate_replay.call_count)
                self.assertEqual(1, source_replay.call_count)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
