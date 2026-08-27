from __future__ import annotations

import http.client
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path


WORKBENCH_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = WORKBENCH_ROOT / "src"
for candidate in (WORKBENCH_ROOT, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.server import create_server  # noqa: E402

try:  # Supports both unittest discovery and package-qualified execution.
    from tests.test_project_store import StoreFixture  # type: ignore  # noqa: E402
except ModuleNotFoundError:  # pragma: no cover - depends on discovery invocation
    from test_project_store import StoreFixture  # type: ignore  # noqa: E402


class WorkbenchHttpContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.fixture = StoreFixture(Path(self.temp_dir.name))
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

    def request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        connection = http.client.HTTPConnection(self.host, self.port, timeout=5)
        encoded = None if body is None else json.dumps(body).encode("utf-8")
        request_headers = dict(headers or {})
        if encoded is not None:
            request_headers.setdefault("Content-Type", "application/json")
        connection.request(method, path, body=encoded, headers=request_headers)
        response = connection.getresponse()
        data = response.read()
        result = (response.status, {key.lower(): value for key, value in response.getheaders()}, data)
        connection.close()
        return result

    def json_request(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
        status, headers, raw = self.request(method, path, body)
        self.assertEqual(headers["content-type"], "application/json; charset=utf-8")
        return status, json.loads(raw.decode("utf-8"))

    def test_health_projects_project_asset_and_validation_routes(self) -> None:
        status, health = self.json_request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(health["status"], "ok")
        self.assertEqual(health["project_count"], 1)

        status, project_list = self.json_request("GET", "/api/projects")
        self.assertEqual(status, 200)
        self.assertEqual(project_list["schema_version"], "autospine-workbench.project-list/v1")
        self.assertEqual(project_list["count"], 1)

        status, project = self.json_request("GET", "/api/projects/fixture-project")
        self.assertEqual(status, 200)
        self.assertEqual(project["id"], "fixture-project")
        self.assertEqual(project["overrides"]["revision"], 0)

        status, headers, image = self.request(
            "GET", "/api/projects/fixture-project/composite"
        )
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], "image/png")
        self.assertEqual(image, PNG_SIGNATURE)

        layer_id = project["layers"][0]["id"]
        status, _, image = self.request(
            "GET", f"/api/projects/fixture-project/layers/{layer_id}/image"
        )
        self.assertEqual(status, 200)
        self.assertEqual(image, PNG_SIGNATURE)

        status, validation = self.json_request(
            "GET", "/api/projects/fixture-project/validate"
        )
        self.assertEqual(status, 200)
        self.assertTrue(validation["valid"])
        self.assertIn(validation["status"], {"valid", "needs_review"})

        status, validation_list = self.json_request("GET", "/api/validate")
        self.assertEqual(status, 200)
        self.assertEqual(len(validation_list["reports"]), 1)

    def test_put_override_and_stale_revision_conflict(self) -> None:
        payload = {
            "base_revision": 0,
            "joint_overrides": {},
            "layer_overrides": {},
            "notes": "reviewed through HTTP",
        }
        status, saved = self.json_request(
            "PUT", "/api/projects/fixture-project/overrides", payload
        )
        self.assertEqual(status, 200)
        self.assertEqual(saved["revision"], 1)

        status, conflict = self.json_request(
            "PUT", "/api/projects/fixture-project/overrides", payload
        )
        self.assertEqual(status, 409)
        self.assertEqual(conflict["error"], "revision_conflict")
        self.assertEqual(conflict["current_revision"], 1)

    def test_http_path_and_host_guards(self) -> None:
        status, result = self.json_request("GET", "/api/projects/%2e%2e")
        self.assertEqual(status, 400)
        self.assertEqual(result["error"], "invalid_path")

        for path in ("/api//health", "/api/health/"):
            with self.subTest(path=path):
                status, result = self.json_request("GET", path)
                self.assertEqual(status, 400)
                self.assertEqual(result["error"], "invalid_path")

        status, _, raw = self.request(
            "GET", "/api/health", headers={"Host": "attacker.example"}
        )
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(raw.decode("utf-8"))["error"], "forbidden_host")

    def test_server_refuses_non_loopback_binding(self) -> None:
        with self.assertRaises(ValueError):
            create_server("0.0.0.0", 0, self.fixture.workspace, state_root=self.fixture.state)


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


if __name__ == "__main__":
    unittest.main()
