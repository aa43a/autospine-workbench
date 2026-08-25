"""HTTP contract tests for read-only candidate artifact routes."""

from __future__ import annotations

import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.artifact_store import ImmutableJsonArtifactStore  # noqa: E402
from autospine_workbench.joint_candidates import AuditBBoxHeuristicProvider  # noqa: E402
from autospine_workbench.server import create_server  # noqa: E402
from tests.test_project_store import StoreFixture  # noqa: E402


class CandidateArtifactHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.fixture = StoreFixture(self.root)
        project = self.fixture.store().get_project("fixture-project")
        self.document = AuditBBoxHeuristicProvider().analyze(project)
        self.published = ImmutableJsonArtifactStore(self.fixture.state).publish(
            "joint-candidates", "fixture-project", self.document
        )
        self.server = create_server(
            "127.0.0.1",
            0,
            self.fixture.workspace,
            state_root=self.fixture.state,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address[:2]

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.temp_dir.cleanup()

    def request(self, path: str, *, method: str = "GET") -> tuple[int, dict, bytes]:
        connection = http.client.HTTPConnection(self.host, self.port, timeout=5)
        connection.request(method, path)
        response = connection.getresponse()
        raw = response.read()
        headers = {key.lower(): value for key, value in response.getheaders()}
        connection.close()
        return response.status, headers, raw

    def json_request(self, path: str) -> tuple[int, dict, bytes]:
        status, headers, raw = self.request(path)
        self.assertEqual("application/json; charset=utf-8", headers["content-type"])
        return status, json.loads(raw.decode("utf-8")), raw

    def test_lists_project_candidates_and_reads_one_by_sha(self) -> None:
        base = "/api/projects/fixture-project/candidate-artifacts"
        status, index, _ = self.json_request(base)
        self.assertEqual(200, status)
        self.assertEqual("fixture-project", index["project_id"])
        self.assertEqual("joint-candidates", index["kind"])
        self.assertEqual(1, index["count"])
        self.assertEqual(self.published.sha256, index["items"][0]["artifact_sha256"])

        status, artifact, _ = self.json_request(f"{base}/{self.published.sha256}")
        self.assertEqual(200, status)
        self.assertEqual(self.document, artifact)

        status, headers, raw = self.request(base, method="HEAD")
        self.assertEqual(200, status)
        self.assertEqual(b"", raw)
        self.assertGreater(int(headers["content-length"]), 0)

    def test_unknown_or_malformed_sha_returns_safe_not_found(self) -> None:
        base = "/api/projects/fixture-project/candidate-artifacts"
        for digest in ("0" * 64, "not-a-sha"):
            status, error, raw = self.json_request(f"{base}/{digest}")
            self.assertEqual(404, status)
            self.assertEqual("candidate_artifact_not_found", error["error"])
            self.assertNotIn(str(self.root).encode(), raw)

    def test_corrupt_artifact_returns_safe_internal_error(self) -> None:
        self.published.path.write_text("{not strict JSON", encoding="utf-8")
        path = (
            "/api/projects/fixture-project/candidate-artifacts/"
            f"{self.published.sha256}"
        )
        status, error, raw = self.json_request(path)
        self.assertEqual(500, status)
        self.assertEqual("analysis_repository_error", error["error"])
        self.assertNotIn(str(self.root).encode(), raw)


if __name__ == "__main__":
    unittest.main()
