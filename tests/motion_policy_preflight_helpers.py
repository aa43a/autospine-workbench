"""Shared fixtures for P9 motion-policy preflight tests."""

from __future__ import annotations

import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.depth_order_candidate_validation import (
    depth_order_candidates_sha256,
)
from autospine_workbench.depth_order_inputs import require_depth_order_inputs
from autospine_workbench.depth_pair_policy import depth_pair_policy_sha256
from autospine_workbench.foot_lock_candidate_validation import (
    foot_lock_candidates_sha256,
)
from autospine_workbench.motion_policy_preflight import (
    CANDIDATE_INVENTORY,
    POLICY_IDENTITY,
    REQUEST_FORMAT,
)
from autospine_workbench.server import create_server
from tests.motion_policy_decision_helpers import MotionPolicyDecisionFixture
from tests.test_project_store import StoreFixture
from tests.filesystem_snapshot import snapshot_file


class MotionPolicyFixtureMixin:
    """Build canonical policy/candidate inputs without becoming a test case."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.chain = MotionPolicyDecisionFixture(cls.root / "chain")
        inputs = require_depth_order_inputs(
            cls.chain.upstream.projected,
            cls.chain.upstream.retarget,
            cls.chain.upstream.mesh,
        )
        cls.policy = cls.chain.upstream.policy(inputs)
        cls.foot = cls.chain.foot
        cls.depth = cls.chain.depth

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()
        super().tearDownClass()

    def _policy_request(self, policy):
        return {
            "format": REQUEST_FORMAT,
            "format_version": 1,
            "operation": POLICY_IDENTITY,
            "policy_json": self._json(policy),
        }

    def _candidate_request(self):
        return {
            "format": REQUEST_FORMAT,
            "format_version": 1,
            "operation": CANDIDATE_INVENTORY,
            "policy_json": self._json(self.policy),
            "foot_candidates_json": self._json(self.foot),
            "depth_candidates_json": self._json(self.depth),
            "declared": {
                "policy_sha256": depth_pair_policy_sha256(self.policy),
                "foot_candidates_sha256": foot_lock_candidates_sha256(
                    self.foot
                ),
                "depth_candidates_sha256": depth_order_candidates_sha256(
                    self.depth
                ),
            },
        }

    @staticmethod
    def _json(value) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )


class MotionPolicyHttpFixtureMixin(MotionPolicyFixtureMixin):
    """Add a loopback server and HTTP helpers to the canonical fixture."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.store = StoreFixture(cls.root / "server")
        cls.server = create_server(
            "127.0.0.1",
            0,
            cls.store.workspace,
            state_root=cls.store.state,
        )
        cls.thread = threading.Thread(
            target=cls.server.serve_forever,
            daemon=True,
        )
        cls.thread.start()
        cls.host, cls.port = cls.server.server_address[:2]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        super().tearDownClass()

    def _headers(self, **changes):
        headers = {
            "Origin": f"http://{self.host}:{self.port}",
            "X-Autospine-Intent": "motion-policy-preflight-v1",
            "Sec-Fetch-Site": "same-origin",
        }
        headers.update(changes)
        return headers

    def _request(self, method, body, headers):
        encoded = (
            self._json(body).encode("utf-8")
            if isinstance(body, dict)
            else body
        )
        request_headers = dict(headers)
        if encoded is not None:
            request_headers.setdefault("Content-Type", "application/json")
        connection = http.client.HTTPConnection(
            self.host,
            self.port,
            timeout=10,
        )
        connection.request(
            method,
            "/api/motion-policy/preflight",
            body=encoded,
            headers=request_headers,
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

    def _json_request(self, method, body, headers):
        status, response_headers, raw = self._request(method, body, headers)
        return status, response_headers, json.loads(raw.decode("utf-8"))


def tree_snapshot(*roots: Path):
    rows = []
    for root in roots:
        for path in sorted(root.rglob("*")):
            relative = f"{root.name}/{path.relative_to(root).as_posix()}"
            rows.append((
                relative,
                path.is_dir(),
                b"" if path.is_dir() else snapshot_file(root, path),
            ))
    return tuple(rows)
