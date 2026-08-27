"""Live-server fixture for exact P10.5b seam-anchor review routes."""

from __future__ import annotations

import http.client
import json
from pathlib import Path
import shutil
import tempfile
import threading

from autospine_workbench.seam_anchor_review_profile import (
    CANDIDATE_NAMESPACE,
    DECISION_NAMESPACE,
)
from autospine_workbench.server import create_server
from tests.p10_candidate_helpers import P10PersistedFixture
from tests.seam_anchor_review_helpers import seam_review_rows
from tests.test_project_store import StoreFixture


ROOT = Path(__file__).resolve().parents[1]


class SeamAnchorReviewHttpFixture:
    """Host one exact persisted P3 chain behind a discovered project."""

    def __init__(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        p10_root = self.root / "p10"
        p10_root.mkdir()
        self.persisted = P10PersistedFixture(p10_root)
        self.project = StoreFixture(self.root / "project")
        self.project_id = self.persisted.mesh.project_id
        target = self.project.audit_dir.parent / self.project_id
        self.project.audit_dir.rename(target)
        self.server = create_server(
            "127.0.0.1", 0, self.project.workspace,
            web_root=ROOT / "web", state_root=self.persisted.state,
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )
        self.thread.start()
        self.host, self.port = self.server.server_address[:2]
        self.base = (
            f"/api/projects/{self.project_id}/seam-anchor-reviews/"
            f"{self.persisted.layer_manifest_sha256}/"
            f"{self.persisted.mesh.rig_sha256}/"
            f"{self.persisted.mesh.bundle_sha256}"
        )

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.temporary.cleanup()

    def reset_reviews(self) -> None:
        project_root = self.persisted.state / "builds" / self.project_id
        for namespace in (CANDIDATE_NAMESPACE, DECISION_NAMESPACE):
            target = project_root / namespace
            if target.exists():
                shutil.rmtree(target)

    def request(
        self,
        method: str,
        path: str,
        body: bytes | dict | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        encoded = json.dumps(body).encode("utf-8") \
            if isinstance(body, dict) else body
        request_headers = dict(headers or {})
        if encoded is not None:
            request_headers.setdefault("Content-Type", "application/json")
        connection = http.client.HTTPConnection(
            self.host, self.port, timeout=15
        )
        connection.request(
            method, path, body=encoded, headers=request_headers
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

    def json_request(self, method, path, body=None, headers=None):
        status, response_headers, raw = self.request(
            method, path, body, headers
        )
        return status, response_headers, json.loads(raw.decode("utf-8"))

    def mutation_headers(self, **changes: str) -> dict[str, str]:
        value = {
            "Origin": f"http://{self.host}:{self.port}",
            "X-Autospine-Intent": "seam-anchor-review",
            "Sec-Fetch-Site": "same-origin",
        }
        value.update(changes)
        return value

    def prepare(self) -> tuple[str, dict]:
        status, _, value = self.json_request(
            "GET", f"{self.base}/candidate"
        )
        if status != 200:
            raise AssertionError(value)
        return value["candidate_sha256"], value["candidate"]

    def submission(self, candidate_sha: str, candidate: dict) -> dict:
        return {
            "base_revision": 0,
            "candidate_sha256": candidate_sha,
            "previous_decision_sha256": None,
            "review": {"reviewer_id": "artist-01", "notes": "full review"},
            "decisions": seam_review_rows(candidate, "accept"),
        }
