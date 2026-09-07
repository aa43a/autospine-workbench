"""Live-server fixture for exact body-sway visual-review route tests."""

from __future__ import annotations

import http.client
import json
from pathlib import Path
import shutil
import tempfile
import threading

from autospine_workbench.body_sway_visual_review_profile import (
    CANDIDATE_NAMESPACE,
    DECISION_NAMESPACE,
)
from autospine_workbench.server import create_server
from tests.body_sway_runtime_capture_helpers import fake_runtime_profile
from tests.body_sway_visual_review_helpers import (
    BodySwayVisualReviewFixture,
    review_rows,
)
from tests.test_project_store import StoreFixture
from tests.filesystem_snapshot import snapshot_file


ROOT = Path(__file__).resolve().parents[1]


class VisualReviewHttpFixture:
    """Host one published capture behind a matching discovered project."""

    def __init__(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.visual = BodySwayVisualReviewFixture(
            self.root / "visual", distinct_images=True
        )
        self.project = StoreFixture(self.root / "project")
        self.project_id, self.preview_sha, self.bundle_sha, self.artifact_sha = \
            self.visual.address
        target = self.project.audit_dir.parent / self.project_id
        self.project.audit_dir.rename(target)
        self.server = create_server(
            "127.0.0.1", 0, self.project.workspace,
            web_root=ROOT / "web",
            state_root=self.visual.state_root,
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )
        self.thread.start()
        self.host, self.port = self.server.server_address[:2]
        self.base = (
            f"/api/projects/{self.project_id}/body-sway-runtime-captures/"
            f"{self.preview_sha}/{self.bundle_sha}/{self.artifact_sha}/"
            "visual-review"
        )

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.temporary.cleanup()

    def reset_reviews(self) -> None:
        project_root = self.visual.state_root / "builds" / self.project_id
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
            self.host, self.port, timeout=10
        )
        with fake_runtime_profile():
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
            "X-Autospine-Intent": "body-sway-visual-review",
            "Sec-Fetch-Site": "same-origin",
        }
        value.update(changes)
        return value

    def prepare(self) -> tuple[str, dict]:
        status, _, value = self.json_request("GET", f"{self.base}/candidate")
        if status != 200:
            raise AssertionError(value)
        return value["candidate_sha256"], value["candidate"]

    def submission(self, candidate_sha: str, candidate: dict) -> dict:
        return {
            "base_revision": 0,
            "candidate_sha256": candidate_sha,
            "previous_decision_sha256": None,
            "review": {"reviewer_id": "artist-01", "notes": "full review"},
            "decisions": review_rows(candidate),
        }


def complete_tree(root: Path) -> tuple:
    rows = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        rows.append((relative, "directory", b"")) if path.is_dir() \
            else rows.append((relative, "file", snapshot_file(root, path)))
    return tuple(rows)
