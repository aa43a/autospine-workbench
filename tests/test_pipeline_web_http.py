"""Live HTTP product preview routes using reviewed P2 assets and real ZIPs."""

import http.client
from io import BytesIO
import json
from threading import Event, Thread
import time
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from tests import test_rig_commands as rig_commands
from autospine_workbench.server import create_server
from autospine_workbench.automation.project_snapshot import observe_project
from autospine_workbench.automation.storage_io import publish_document


class PipelineWebHttpTests(unittest.TestCase):
    def setUp(self):
        self.fixture = rig_commands.RigCommandIntegrationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        source = self.fixture.fixture
        self.server = create_server("127.0.0.1", 0, source.workspace, state_root=source.state)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)
        self.host, self.port = self.server.server_address
        self.origin = f"http://{self.host}:{self.port}"
        self.base = "/api/projects/fixture-project/automation"
        self.manager = self.server.automation_manager
        self.request_body = {
            "profile": "production_review", "resume": True,
            "expected_resolved_sha256": source.store().get_project("fixture-project")["resolved"]["sha256"],
        }

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=10)
        self.assertFalse(self.thread.is_alive())

    def request(self, method, suffix="", body=None, headers=None, *, project=None):
        base = self.base if project is None else f"/api/projects/{project}/automation"
        values = {"Origin": self.origin, "X-Autospine-Intent": "pipeline-preview"}
        if headers:
            values.update(headers)
        values = {key: value for key, value in values.items() if value is not None}
        if isinstance(body, dict):
            body = json.dumps(body).encode()
            values.setdefault("Content-Type", "application/json")
        connection = http.client.HTTPConnection(self.host, self.port, timeout=3)
        try:
            connection.request(method, base + suffix, body=body, headers=values)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def document(self, method, suffix="", body=None, **kwargs):
        status, headers, raw = self.request(method, suffix, body, **kwargs)
        result = json.loads(raw)
        self.assertNotIn(str(self.fixture.fixture.state), raw.decode())
        return status, result

    def submit(self, **changes):
        status, job = self.document("POST", "/preview", {**self.request_body, **changes})
        self.assertEqual(status, 202, job)
        return job

    def terminal(self, job):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            status, result = self.document("GET", f"/jobs/{job['job_id']}")
            self.assertEqual(status, 200, result)
            if result["status"] not in {"pending", "running"}:
                return result
            Event().wait(0.05)
        self.fail("HTTP preview worker did not finish")

    def test_capabilities_and_review_queue_are_readable_without_release_authority(self):
        status, result = self.document("GET")
        self.assertEqual(status, 200, result)
        self.assertTrue(result["capabilities"]["can_build_spine_preview"])
        self.assertFalse(result["capabilities"]["can_export_spine"])
        self.assertEqual(result["capabilities"]["authority"], "none")
        self.assertIn("review_queue", result)
        self.assertFalse(self.manager.root.exists())

    def test_reviewed_project_builds_real_zip_and_cross_project_access_is_denied(self):
        completed = self.terminal(self.submit())
        self.assertEqual(completed["status"], "succeeded", completed)
        self.assertEqual(completed["authority"], "none")
        self.assertEqual(completed["target_version"], "4.3.26")
        job_id = completed["job_id"]
        status, headers, raw = self.request("GET", f"/jobs/{job_id}/download")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "application/zip")
        with ZipFile(BytesIO(raw)) as archive:
            self.assertEqual(set(archive.namelist()), {
                "skeleton.json", "skeleton.atlas", "skeleton.png", "qa.json", "source.json",
            })
            self.assertTrue(archive.read("skeleton.png").startswith(b"\x89PNG"))
            self.assertEqual(json.loads(archive.read("skeleton.json"))["skeleton"]["spine"], "4.3.26")
            qa = json.loads(archive.read("qa.json"))
            self.assertEqual(qa["runtime_status"], "not_run")
            self.assertEqual(qa["authority"], "none")
        self.assertEqual(self.request("HEAD", f"/jobs/{job_id}/download")[2], b"")
        for method, suffix, body in (
            ("GET", f"/jobs/{job_id}", None),
            ("GET", f"/jobs/{job_id}/download", None),
            ("POST", f"/jobs/{job_id}/cancel", {}),
        ):
            with self.subTest(method=method, suffix=suffix):
                status, denied = self.document(method, suffix, body, project="other-project")
                self.assertEqual(status, 404, denied)

    def test_mutations_require_exact_origin_and_intent_and_bounded_json(self):
        for headers in (
            {"Origin": None}, {"Origin": "https://evil.example"},
            {"Origin": self.origin + "/"}, {"X-Autospine-Intent": None},
            {"X-Autospine-Intent": "other"}, {"Sec-Fetch-Site": "cross-site"},
        ):
            with self.subTest(headers=headers):
                status, result = self.document("POST", "/preview", self.request_body, headers=headers)
                self.assertEqual(status, 403, result)
        for body, headers, expected in (
            (b"x" * 2049, {"Content-Type": "application/json"}, 413),
            (b"{}", {"Content-Type": "text/plain"}, 415),
            (b"[]", {"Content-Type": "application/json"}, 400),
            ({**self.request_body, "unexpected": True}, {}, 400),
            ({**self.request_body, "resume": "yes"}, {}, 400),
            ({**self.request_body, "target_version": "4.4"}, {}, 400),
            ({**self.request_body, "target_version": None}, {}, 400),
        ):
            with self.subTest(expected=expected, body=str(body)[:50]):
                self.assertEqual(self.request("POST", "/preview", body, headers)[0], expected)
        self.assertFalse(self.manager.root.exists())

    def test_explicit_legacy_target_uses_its_own_run_and_download(self):
        completed = self.terminal(self.submit(target_version="4.2"))
        self.assertEqual(completed["status"], "succeeded", completed)
        self.assertEqual(completed["target_version"], "4.2")
        self.assertEqual(completed["run"]["engine"], "region-spine-preview-v1")
        status, _, raw = self.request("GET", f"/jobs/{completed['job_id']}/download")
        self.assertEqual(status, 200)
        with ZipFile(BytesIO(raw)) as archive:
            self.assertEqual(json.loads(archive.read("skeleton.json"))["skeleton"]["spine"], "4.2")

    def test_methods_and_unknown_routes_are_bounded(self):
        for suffix, allow, denied in (
            ("", "GET, HEAD, OPTIONS", "POST"),
            ("/preview", "POST, OPTIONS", "GET"),
            ("/jobs/job-" + "a" * 32, "GET, HEAD, OPTIONS", "PUT"),
            ("/jobs/job-" + "a" * 32 + "/cancel", "POST, OPTIONS", "GET"),
            ("/jobs/job-" + "a" * 32 + "/download", "GET, HEAD, OPTIONS", "POST"),
        ):
            with self.subTest(suffix=suffix):
                status, headers, _ = self.request("OPTIONS", suffix)
                self.assertEqual((status, headers["Allow"]), (204, allow))
                self.assertEqual(self.request(denied, suffix)[0], 405)
        self.assertEqual(self.request("GET", "/unknown")[0], 404)

    def test_duplicate_authorization_headers_are_rejected_before_job_creation(self):
        raw = json.dumps(self.request_body).encode()
        for duplicate in ("Host", "Origin", "X-Autospine-Intent"):
            with self.subTest(duplicate=duplicate):
                connection = http.client.HTTPConnection(self.host, self.port, timeout=3)
                try:
                    connection.putrequest("POST", self.base + "/preview", skip_host=True)
                    for name, value in (
                        ("Host", f"{self.host}:{self.port}"), ("Origin", self.origin),
                        ("X-Autospine-Intent", "pipeline-preview"),
                        ("Content-Type", "application/json"), ("Content-Length", str(len(raw))),
                    ):
                        connection.putheader(name, value)
                        if name == duplicate:
                            connection.putheader(name, value)
                    connection.endheaders(raw)
                    response = connection.getresponse()
                    self.assertEqual(response.status, 403)
                    response.read()
                finally:
                    connection.close()
        self.assertFalse(self.manager.root.exists())

    def test_slow_worker_does_not_block_http_and_cancel_wins(self):
        entered, release = Event(), Event()
        original = self.manager.application.preview

        def slow(*args, **kwargs):
            entered.set()
            if not release.wait(10):
                raise AssertionError("test worker was not released")
            return original(*args, **kwargs)

        with patch.object(self.manager.application, "preview", side_effect=slow):
            try:
                job = self.submit()
                self.assertTrue(entered.wait(3))
                self.assertEqual(self.document("GET")[0], 200)
                duplicate = self.submit()
                self.assertEqual(duplicate["job_id"], job["job_id"])
                status, canceled = self.document("POST", f"/jobs/{job['job_id']}/cancel", {})
                self.assertEqual(status, 202, canceled)
                self.assertTrue(canceled["cancel_requested"])
            finally:
                release.set()
            completed = self.terminal(job)
        self.assertEqual(completed["status"], "canceled", completed)
        self.assertEqual(self.request("GET", f"/jobs/{job['job_id']}/download")[0], 409)

    def test_resume_continues_interrupted_run_and_stale_project_is_rejected(self):
        app = self.manager.application
        with observe_project(app.projects, "fixture-project") as snapshot:
            run = app.runs.create("fixture-project", "production_review", snapshot.source_addresses,
                                  target_version="4.3.26")
        run = app.runs.append(run["run_id"], run["state_sha256"], "start")
        pending = self.terminal(self.submit(resume=False))
        self.assertEqual(pending["status"], "blocked", pending)
        self.assertEqual(pending["reason_code"], "pipeline_resume_required")
        self.assertEqual(app.runs.load(run["run_id"])["state_sha256"], run["state_sha256"])
        resumed = self.terminal(self.submit(resume=True))
        self.assertEqual(resumed["status"], "succeeded", resumed)
        stale = self.terminal(self.submit(expected_resolved_sha256="f" * 64))
        self.assertNotEqual(stale["status"], "succeeded")
        self.assertEqual(stale["reason_code"], "project_changed_during_snapshot")

    def test_request_left_by_crashed_server_is_blocked_and_cannot_download(self):
        job_id = "job-" + "d" * 32
        path = self.manager._path(job_id, create=True)
        request = {"project_id": "fixture-project", **self.request_body}
        publish_document(path / "request.json", request, staging=path / "staging")
        status, result = self.document("GET", f"/jobs/{job_id}")
        self.assertEqual(status, 200, result)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason_code"], "pipeline_interrupted")
        self.assertEqual(self.request("GET", f"/jobs/{job_id}/download")[0], 409)
        self.assertEqual(self.request("POST", f"/jobs/{job_id}/cancel", {"extra": True})[0], 400)
