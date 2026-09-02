"""Live HTTP routing tests for completed-job P10.3c v2 review."""

from __future__ import annotations

import http.client
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.body_sway_visual_review_application_v2 import (  # noqa: E402
    BodySwayVisualReviewApplicationV2Error,
)
from autospine_workbench.p10_capture_job_contract import (  # noqa: E402
    P10CaptureJobEvent, P10CaptureJobRequest,
)
from autospine_workbench.p10_capture_job_store import (  # noqa: E402
    P10CaptureJobSnapshot,
)
from autospine_workbench.p10_completed_job_snapshot import (  # noqa: E402
    verified_completed_p10_capture_job,
)
from autospine_workbench.p10_preview_v2_commands import (  # noqa: E402
    P10PreviewV2CommandError,
)
from autospine_workbench.body_sway_visual_review_application_models_v2 import (  # noqa: E402
    BodySwayVisualReviewImageV2,
)
from autospine_workbench.body_sway_visual_review_address_v2 import (  # noqa: E402
    ExactVisualReviewAddressV2,
)
from autospine_workbench.p10_visual_review_v2_context import (  # noqa: E402
    P10VisualReviewV2Context,
    P10VisualReviewV2JobIncomplete,
    P10VisualReviewV2SourceChanged,
)
from autospine_workbench.server import create_server  # noqa: E402
from tests.p10_visual_review_v2_http_session_cases import (  # noqa: E402
    P10VisualReviewV2ImageSessionHttpCases,
)
from tests.p10_visual_review_v2_http_route_cases import (  # noqa: E402
    P10VisualReviewV2RouteHttpCases,
)
from tests.p10_review_admission_v2_http_cases import (  # noqa: E402
    P10ReviewAdmissionV2HttpCases,
)
from tests.test_project_store import StoreFixture  # noqa: E402


SHA = lambda value: value * 64


class P10VisualReviewV2HttpTests(
    P10VisualReviewV2ImageSessionHttpCases, P10VisualReviewV2RouteHttpCases,
    P10ReviewAdmissionV2HttpCases,
    unittest.TestCase,
):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.fixture = StoreFixture(Path(self.temporary.name))
        self.p10 = {
            "candidate_sha256": SHA("1"),
            "decision_sha256": SHA("2"), "revision": 1,
        }
        self.framing = {
            "candidate_sha256": SHA("3"),
            "decision_sha256": SHA("4"), "revision": 1,
        }
        request = P10CaptureJobRequest.from_payload({
            "package_id": SHA("5"), "client_request_id": "review-http-1",
            "expected_p10_1": self.p10,
            "expected_framing": self.framing,
            "explicit_runtime_license_confirmation": True,
            "explicit_run_confirmation": True,
        })
        self.job_id = request.job_id
        self.addresses = {
            "project": "fixture-project", "preview": SHA("6"),
            "execution_bundle": SHA("7"), "artifact": SHA("8"),
        }
        self.snapshot = _completed_snapshot(request, self.addresses)
        self.manager = Mock()
        self.manager.get.return_value = self.snapshot
        self.manager.close = Mock()
        self.preview = SimpleNamespace(
            package_id=SHA("5"), project_id="fixture-project",
            clip_id="wave-left-v1", temporary_preview_v2_sha256=SHA("6"),
            capture_framing_candidate_sha256=SHA("3"),
            capture_framing_decision_sha256=SHA("4"),
            capture_framing_revision=1, case_count=3,
            document={"source": {"current_p10_1_head": self.p10}},
        )
        self.address = ExactVisualReviewAddressV2(
            self.addresses["project"], self.addresses["preview"],
            self.addresses["execution_bundle"], self.addresses["artifact"],
        )
        self.mount = SimpleNamespace(result=self.preview)
        completed_job = verified_completed_p10_capture_job(
            self.snapshot, self.job_id,
        )
        self.context = P10VisualReviewV2Context(
            self.job_id, SHA("5"), self.address, self.mount,
            completed_job.terminal_event_sha256,
            completed_job.terminal_sequence, completed_job,
        )
        self.resolve_acceleration = []

        def resolve_context(manager, _store, job_id, *,
                            allow_acceleration=True):
            self.resolve_acceleration.append(allow_acceleration)
            snapshot = manager.get(job_id)
            if snapshot.get("status") != "completed" \
                    or snapshot.get("terminal") is not True:
                raise P10VisualReviewV2JobIncomplete(
                    "Runtime capture job has not completed"
                )
            if self.preview.temporary_preview_v2_sha256 \
                    != self.address.temporary_preview_v2_sha256:
                raise P10VisualReviewV2SourceChanged(
                    "Current source differs from the completed job"
                )
            return self.context

        self.resolve_context = Mock(side_effect=resolve_context)
        self.candidate_sha = SHA("9")
        self.png_sha = hashlib.sha256(b"PNG").hexdigest()
        self.decision_sha = SHA("a")
        self.candidate = {
            "format_version": 2, "project_id": "fixture-project",
            "clip_id": "wave-left-v1", "status": "candidate_only",
            "source": {}, "cases": [],
            "release_gate": {"status": "blocked", "reason_codes": []},
        }
        history = SimpleNamespace(
            current_revision=1, head_decision_sha256=self.decision_sha,
            rows=(SimpleNamespace(
                revision=1, decision_sha256=self.decision_sha,
                status="sampled_visual_approved",
            ),),
        )
        self.prepared = SimpleNamespace(
            candidate_sha256=self.candidate_sha,
            candidate_document=self.candidate, history=history,
        )
        self.service = Mock()
        self.service.prepare.return_value = self.prepared
        self.service.prepare_image_snapshot.return_value = (
            BodySwayVisualReviewImageV2(
                self.candidate_sha, "case-1", SHA("c"), self.png_sha,
                3, 640, 640, b"PNG",
            ),
        )
        self.service.exact_decision.return_value = SimpleNamespace(
            candidate_sha256=self.candidate_sha,
            decision_sha256=self.decision_sha,
            decision_document={
                "review": {"revision": 1},
                "summary": {"approve_count": 3, "reject_count": 0,
                            "unobservable_count": 0},
                "status": "sampled_visual_approved",
            },
        )
        self.service.submit.return_value = SimpleNamespace(
            candidate_sha256=self.candidate_sha,
            decision_sha256=self.decision_sha, revision=2,
            status="sampled_visual_approved", release_gate_status="blocked",
            release_gate_reason_codes=("safe_range_unproven",),
            case_count=3, approve_count=3, reject_count=0,
            unobservable_count=0, reused=False,
        )
        self.patches = [
            patch("autospine_workbench.server.P10CaptureJobManager",
                  return_value=self.manager),
            patch(
                "autospine_workbench.p10_visual_review_v2_routes."
                "resolve_p10_visual_review_v2_context",
                self.resolve_context,
            ),
            patch(
                "autospine_workbench.p10_visual_review_v2_routes."
                "BodySwayVisualReviewApplicationV2",
                return_value=self.service,
            ),
        ]
        self.configure_review_admission_v2_http()
        for value in self.patches:
            value.start()
        self.server = create_server(
            "127.0.0.1", 0, self.fixture.workspace,
            web_root=ROOT / "web", state_root=self.fixture.state,
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True,
        )
        self.thread.start()
        self.host, self.port = self.server.server_address[:2]
        self.base = (
            f"/api/p10/runtime-capture/jobs/{self.job_id}/visual-review-v2"
        )

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()
        for value in reversed(self.patches):
            value.stop()
        self.temporary.cleanup()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection(self.host, self.port, timeout=5)
        encoded = json.dumps(body).encode("utf-8") \
            if isinstance(body, dict) else body
        actual = dict(headers or {})
        if encoded is not None:
            actual.setdefault("Content-Type", "application/json")
        connection.request(method, path, body=encoded, headers=actual)
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
            method, path, body, headers,
        )
        return status, response_headers, json.loads(raw.decode("utf-8"))

    def test_candidate_history_image_decision_and_submit_recheck_job(self):
        status, _, candidate = self.json_request(
            "GET", f"{self.base}/candidate",
        )
        self.assertEqual(200, status)
        self.assertEqual(self.job_id, candidate["job"]["job_id"])
        self.assertEqual(self.job_id, candidate["history"]["job_id"])
        self.assertEqual("read_only_snapshot",
                         candidate["image_session"]["authority"])
        self.assertNotIn("path", json.dumps(candidate).lower())

        paths = (
            f"{self.base}/candidates/{self.candidate_sha}/history",
            f"{self.base}/candidates/{self.candidate_sha}/history/1/{self.decision_sha}",
        )
        for path in paths:
            status, _, _ = self.json_request("GET", path)
            self.assertEqual(200, status)
        image = (
            f"{self.base}/candidates/{self.candidate_sha}/cases/case-1/"
            f"image/{self.png_sha}?session="
            f"{candidate['image_session']['token']}"
        )
        status, headers, raw = self.request("GET", image)
        self.assertEqual((200, b"PNG"), (status, raw))
        self.assertEqual(f'"{self.png_sha}"', headers["etag"])
        status, _, repeated = self.request("GET", image)
        self.assertEqual((200, b"PNG"), (status, repeated))
        self.service.prepare_image_snapshot.assert_called_once()

        endpoint = f"{self.base}/candidates/{self.candidate_sha}/decisions"
        status, _, result = self.json_request(
            "PUT", endpoint,
            {"candidate_sha256": self.candidate_sha},
            self.mutation_headers(),
        )
        self.assertEqual(201, status)
        self.assertEqual(self.job_id, result["job_id"])
        self.service.submit.return_value.reused = True
        status, _, retried = self.json_request(
            "PUT", endpoint,
            {"candidate_sha256": self.candidate_sha},
            self.mutation_headers(),
        )
        self.assertEqual(200, status)
        self.assertTrue(retried["reused"])
        self.assertEqual(5, self.manager.get.call_count)
        self.assertEqual(
            [True, True, True, False, False],
            self.resolve_acceleration,
        )

    def test_cache_hit_still_rejects_current_source_drift(self):
        image = (
            f"{self.base}/candidates/{self.candidate_sha}/cases/case-1/"
            f"image/{self.png_sha}"
        )
        status, _, raw = self.request("GET", image)
        self.assertEqual((200, b"PNG"), (status, raw))
        self.preview.temporary_preview_v2_sha256 = SHA("0")
        status, _, value = self.json_request("GET", image)
        self.assertEqual(409, status)
        self.assertEqual("visual_review_v2_source_changed", value["error"])
        self.service.prepare_image_snapshot.assert_called_once()

    def test_mount_time_head_drift_is_409_and_zero_write(self):
        before = _tree(self.fixture.state)

        def drift(*_args, **_kwargs):
            try:
                raise P10PreviewV2CommandError("current head changed")
            except P10PreviewV2CommandError as exc:
                raise BodySwayVisualReviewApplicationV2Error(
                    r"C:\private\head.json"
                ) from exc

        self.service.submit.side_effect = drift
        endpoint = f"{self.base}/candidates/{self.candidate_sha}/decisions"
        status, _, value = self.json_request(
            "PUT", endpoint, {"candidate_sha256": self.candidate_sha},
            self.mutation_headers(),
        )
        self.assertEqual(409, status)
        self.assertEqual("visual_review_v2_source_changed", value["error"])
        self.assertEqual(before, _tree(self.fixture.state))

def _completed_snapshot(request, addresses):
    rows = (
        ("queued", {}), ("exact_replay", {}),
        ("preview_compiled", {}), ("runtime_verified", {}),
        ("capturing", {"current": 1, "total": 1}),
        ("sealing", {}), ("completed", {"addresses": addresses}),
    )
    events = []
    previous = None
    for sequence, (status, payload) in enumerate(rows, 1):
        event = P10CaptureJobEvent.build(
            request.job_id, sequence, status,
            previous.event_sha if previous else None, **payload,
        )
        events.append(event)
        previous = event
    return P10CaptureJobSnapshot(request, tuple(events)).public_document()


def _tree(root):
    return tuple(
        (path.relative_to(root).as_posix(), path.is_dir(),
         b"" if path.is_dir() else path.read_bytes())
        for path in sorted(root.rglob("*"))
    )


if __name__ == "__main__":
    unittest.main()
