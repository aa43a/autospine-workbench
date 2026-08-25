"""HTTP contracts for read-only, exact-address P3 mesh bundle evidence."""

from __future__ import annotations

import hashlib
import http.client
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.mesh_bundle_reader import (  # noqa: E402
    VerifiedMeshBundleReaderError,
)
from autospine_workbench.server import create_server  # noqa: E402
from tests.test_project_store import StoreFixture  # noqa: E402


RIG_SHA = "a" * 64
BUNDLE_SHA = "b" * 64
RUN_SHA = "c" * 64
PROBES_SHA = "d" * 64
VISUALS_SHA = "e" * 64
BASE_RIG_SHA = "1" * 64
BASE_BUNDLE_SHA = "2" * 64
LAYER_MANIFEST_SHA = "6" * 64
RESOLVED_PROJECT_SHA = "7" * 64
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def artifact(path, pose, data, *, angle, bone):
    return {
        "kind": "weight_heatmap" if pose == "weights" else "pose",
        "id": "leg-left",
        "pose": pose,
        "bone": bone,
        "angle_deg": angle,
        "width": 32 if pose == "weights" else 160,
        "height": 80 if pose == "weights" else 100,
        "rgba_sha256": "f" * 64,
        "png_sha256": hashlib.sha256(data).hexdigest(),
        "path": path,
    }


def verified_fixture():
    pngs = {
        "weights/leg-left.png": PNG_SIGNATURE + b"weight",
        "poses/leg-left.setup.png": PNG_SIGNATURE + b"setup",
        "poses/leg-left.widest-safe-p060.png": PNG_SIGNATURE + b"pose",
    }
    artifacts = [
        artifact("weights/leg-left.png", "weights", pngs["weights/leg-left.png"],
                 angle=None, bone="calf.left"),
        artifact("poses/leg-left.setup.png", "setup",
                 pngs["poses/leg-left.setup.png"], angle=0, bone=None),
        artifact("poses/leg-left.widest-safe-p060.png", "widest-safe",
                 pngs["poses/leg-left.widest-safe-p060.png"],
                 angle=60, bone="calf.left"),
    ]
    return SimpleNamespace(
        project_id="fixture-project",
        rig_sha256=RIG_SHA,
        bundle_sha256=BUNDLE_SHA,
        run_sha256=RUN_SHA,
        probes_sha256=PROBES_SHA,
        visuals_sha256=VISUALS_SHA,
        base_rig_sha256=BASE_RIG_SHA,
        base_bundle_sha256=BASE_BUNDLE_SHA,
        layer_manifest_sha256=LAYER_MANIFEST_SHA,
        resolved_project_sha256=RESOLVED_PROJECT_SHA,
        rig={"attachments": [{
            "id": "leg-left", "vertices": [[0, 0], [1, 0], [0, 1]],
            "triangles": [0, 1, 2],
        }]},
        probes={"attachments": [{
            "attachment_id": "leg-left",
            "action_probe": {"distal_bend": {
                "negative": {"max_contiguous_magnitude_deg": 40},
                "positive": {"max_contiguous_magnitude_deg": 60},
            }},
        }]},
        visuals={
            "summary": "converted=1",
            "targets": [{
                "attachment_id": "leg-left",
                "source_layer_id": "leg-left",
                "side": "left",
                "proximal_bone_id": "thigh.left",
                "distal_bone_id": "calf.left",
            }],
            "artifacts": artifacts,
        },
        pngs=pngs,
    )


class MeshBundleHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.fixture = StoreFixture(Path(self.temp.name))
        self.bundle = (
            self.fixture.state / "builds" / "fixture-project" /
            "mesh-rig-ir" / RIG_SHA / BUNDLE_SHA
        )
        self.bundle.mkdir(parents=True)
        self.marker = self.fixture.state / "read-only.marker"
        self.marker.write_bytes(b"unchanged")
        self.verified = verified_fixture()
        self.reader_patch = patch(
            "autospine_workbench.mesh_bundle_evidence.VerifiedMeshBundleReader"
        )
        reader = self.reader_patch.start()
        self.reader = reader.return_value
        self.reader.load.return_value = self.verified
        self.addCleanup(self.reader_patch.stop)
        self.server = create_server(
            "127.0.0.1", 0, self.fixture.workspace,
            state_root=self.fixture.state,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address[:2]
        self.base = "/api/projects/fixture-project/mesh-bundles"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.temp.cleanup()

    def request(self, path: str, *, method: str = "GET"):
        connection = http.client.HTTPConnection(self.host, self.port, timeout=5)
        connection.request(method, path)
        response = connection.getresponse()
        raw = response.read()
        headers = {key.lower(): value for key, value in response.getheaders()}
        connection.close()
        return response.status, headers, raw

    def json_request(self, path: str, *, method: str = "GET"):
        status, headers, raw = self.request(path, method=method)
        self.assertEqual("application/json; charset=utf-8", headers["content-type"])
        return status, headers, json.loads(raw.decode("utf-8")) if raw else {}

    def test_discovers_then_reads_only_an_explicit_double_sha(self) -> None:
        status, _, index = self.json_request(self.base)
        self.assertEqual(200, status)
        self.assertEqual("autospine-mesh-bundle-evidence-index", index["format"])
        self.assertEqual([{
            "rig_sha256": RIG_SHA, "bundle_sha256": BUNDLE_SHA,
        }], index["items"])
        self.assertNotIn("latest", json.dumps(index))
        self.reader.load.assert_not_called()

        status, _, detail = self.json_request(f"{self.base}/{RIG_SHA}/{BUNDLE_SHA}")
        self.assertEqual(200, status)
        self.assertEqual("converted", detail["status"])
        self.assertEqual("converted=1", detail["summary"])
        self.assertEqual(BASE_RIG_SHA, detail["source"]["base_rig_sha256"])
        self.assertEqual(BASE_BUNDLE_SHA, detail["source"]["base_bundle_sha256"])
        self.assertEqual(LAYER_MANIFEST_SHA, detail["source"]["layer_manifest_sha256"])
        self.assertEqual(RESOLVED_PROJECT_SHA, detail["source"]["resolved_project_sha256"])
        self.assertEqual(RUN_SHA, detail["source"]["run_sha256"])
        self.assertEqual(PROBES_SHA, detail["source"]["probes_sha256"])
        self.assertEqual(VISUALS_SHA, detail["source"]["visuals_sha256"])
        hinge = detail["hinges"][0]
        self.assertEqual((3, 1), (hinge["vertex_count"], hinge["triangle_count"]))
        self.assertEqual(
            {"minimum": -40, "maximum": 60},
            hinge["continuous_safe_angle_deg"],
        )
        self.assertEqual(60, hinge["images"]["widest_safe"]["angle_deg"])
        self.reader.load.assert_called_with("fixture-project", RIG_SHA, BUNDLE_SHA)
        self.assertEqual(b"unchanged", self.marker.read_bytes())

    def test_verified_png_has_exact_mime_and_head_is_bodyless(self) -> None:
        detail = self.json_request(f"{self.base}/{RIG_SHA}/{BUNDLE_SHA}")[2]
        image = detail["hinges"][0]["images"]["heatmap"]
        status, headers, body = self.request(image["url"])
        self.assertEqual(200, status)
        self.assertEqual("image/png", headers["content-type"])
        self.assertEqual(self.verified.pngs[image["path"]], body)
        self.assertEqual("nosniff", headers["x-content-type-options"])

        status, headers, body = self.request(image["url"], method="HEAD")
        self.assertEqual(200, status)
        self.assertEqual("image/png", headers["content-type"])
        self.assertEqual(b"", body)
        self.assertGreater(int(headers["content-length"]), 0)

    def test_verified_noop_is_explicit_and_has_no_hinges(self) -> None:
        self.verified.rig = {"attachments": []}
        self.verified.probes = {"attachments": []}
        self.verified.visuals = {
            "summary": "reviewed-noop", "targets": [], "artifacts": [],
        }
        self.verified.pngs = {}
        status, _, detail = self.json_request(f"{self.base}/{RIG_SHA}/{BUNDLE_SHA}")
        self.assertEqual(200, status)
        self.assertEqual("reviewed-noop", detail["status"])
        self.assertEqual("reviewed-noop", detail["summary"])
        self.assertEqual([], detail["hinges"])

    def test_bad_hash_traversal_and_failed_verification_fail_closed(self) -> None:
        bad_paths = (
            f"{self.base}/bad/{BUNDLE_SHA}",
            f"{self.base}/{RIG_SHA}/{'0' * 64}",
            f"{self.base}/{RIG_SHA}/{BUNDLE_SHA}/images/bad",
        )
        for path in bad_paths:
            with self.subTest(path=path):
                status, _, error = self.json_request(path)
                self.assertEqual(404, status)
                self.assertEqual("mesh_bundle_evidence_not_found", error["error"])
        status, _, error = self.json_request(
            f"{self.base}/{RIG_SHA}/{BUNDLE_SHA}/images/%2e%2e"
        )
        self.assertEqual(400, status)
        self.assertEqual("invalid_path", error["error"])

        self.reader.load.side_effect = VerifiedMeshBundleReaderError("corrupt")
        try:
            status, _, error = self.json_request(f"{self.base}/{RIG_SHA}/{BUNDLE_SHA}")
        finally:
            self.reader.load.side_effect = None
        self.assertEqual(500, status)
        self.assertEqual("mesh_bundle_evidence_error", error["error"])

    def test_mesh_bundle_endpoints_are_read_only(self) -> None:
        before = self.marker.read_bytes()
        for method in ("PUT", "POST", "PATCH", "DELETE"):
            with self.subTest(method=method):
                status, headers, _ = self.request(
                    f"{self.base}/{RIG_SHA}/{BUNDLE_SHA}", method=method
                )
                self.assertEqual(405, status)
                self.assertEqual("GET, HEAD, OPTIONS", headers["allow"])
        status, headers, body = self.request(
            f"{self.base}/{RIG_SHA}/{BUNDLE_SHA}", method="OPTIONS"
        )
        self.assertEqual(204, status)
        self.assertEqual(b"", body)
        self.assertEqual("GET, HEAD, OPTIONS", headers["allow"])
        self.assertEqual("GET, HEAD, OPTIONS", headers["access-control-allow-methods"])
        self.assertEqual(before, self.marker.read_bytes())


if __name__ == "__main__":
    unittest.main()
