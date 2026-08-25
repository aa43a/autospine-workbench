"""HTTP contracts for read-only split-preview artifacts and child images."""

from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
import http.client
import io
import json
from pathlib import Path
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

from autospine_workbench.artifact_store import ImmutableJsonArtifactStore  # noqa: E402
from autospine_workbench.manifest_bundle import LayerManifestBundleReader  # noqa: E402
from autospine_workbench.server import create_server  # noqa: E402
from autospine_workbench.split_preview_commands import (  # noqa: E402
    publish_split_previews_command,
)
from autospine_workbench.split_preview_repository import (  # noqa: E402
    SplitPreviewRepository,
)
from tests.png_helpers import write_rgba  # noqa: E402
from tests.test_project_store import StoreFixture  # noqa: E402
from tests.test_split_preview_commands import VISIBLE, authored_spec  # noqa: E402


def publish_fixture(fixture: StoreFixture) -> dict:
    fixture.audit["canvas"] = [8, 4]
    layer = fixture.audit["layers"][0]
    layer.update(
        name="legwear",
        bbox=[1, 0, 7, 4],
        width=6,
        height=4,
        alpha_nonzero=24,
        alpha_perceptible=24,
        alpha_opaque=0,
        component_count=1,
        component_areas_top5=[24],
    )
    fixture.write_audit()
    write_rgba(
        fixture.layer_image,
        [[VISIBLE for _ in range(6)] for _ in range(4)],
    )
    store = fixture.store()
    layer_id = store.get_project("fixture-project")["layers"][0]["id"]
    positions = {
        "hip.left": (2, 0),
        "knee.left": (2, 2),
        "ankle.left": (2, 3),
        "hip.right": (5, 0),
        "knee.right": (5, 2),
        "ankle.right": (5, 3),
    }
    store.save_overrides(
        "fixture-project",
        {
            "base_revision": 0,
            "joint_overrides": {
                joint_id: {"x": xy[0], "y": xy[1], "reason": "HTTP preview"}
                for joint_id, xy in positions.items()
            },
            "layer_overrides": {
                layer_id: {
                    "canonical_role": "body.leg",
                    "side": "bilateral",
                    "disposition": "split_left_right",
                    "split_spec": authored_spec(),
                    "visible": True,
                    "notes": "HTTP preview fixture",
                }
            },
            "notes": "publish HTTP preview fixture",
        },
    )
    output = io.StringIO()
    with redirect_stdout(output):
        status = publish_split_previews_command(
            "fixture-project", fixture.workspace, fixture.state
        )
    if status != 0:
        raise AssertionError(output.getvalue())
    return json.loads(output.getvalue())


class SplitPreviewHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.fixture = StoreFixture(self.root)
        self.publication = publish_fixture(self.fixture)
        self.item = self.publication["previews"][0]
        self.digest = self.item["split_artifact_sha256"]
        self.base = "/api/projects/fixture-project/split-previews"
        self.artifact_path = (
            self.fixture.state
            / "analysis"
            / "fixture-project"
            / "split-previews"
            / f"{self.digest}.json"
        )
        self.document = json.loads(self.artifact_path.read_text(encoding="utf-8"))
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
        self.temp.cleanup()

    def request(self, path: str, *, method: str = "GET") -> tuple[int, dict, bytes]:
        connection = http.client.HTTPConnection(self.host, self.port, timeout=5)
        connection.request(method, path)
        response = connection.getresponse()
        raw = response.read()
        headers = {key.lower(): value for key, value in response.getheaders()}
        connection.close()
        return response.status, headers, raw

    def json_request(self, path: str, *, method: str = "GET") -> tuple[int, dict, bytes]:
        status, headers, raw = self.request(path, method=method)
        self.assertEqual("application/json; charset=utf-8", headers["content-type"])
        value = json.loads(raw.decode("utf-8")) if raw else {}
        return status, value, raw

    def test_lists_reads_and_serves_manifest_bound_part_images(self) -> None:
        status, index, _ = self.json_request(self.base)
        self.assertEqual(200, status)
        self.assertEqual("autospine-split-preview-index/v1", index["format"])
        self.assertEqual(1, index["count"])
        self.assertEqual(self.digest, index["items"][0]["artifact_sha256"])

        status, artifact, _ = self.json_request(f"{self.base}/{self.digest}")
        self.assertEqual(200, status)
        self.assertEqual(self.document, artifact)

        image_url = f"{self.base}/{self.digest}/parts/left/image"
        status, headers, image = self.request(image_url)
        expected = SplitPreviewRepository(self.fixture.state).child_image(
            "fixture-project", self.digest, "left"
        )
        self.assertEqual(200, status)
        self.assertEqual("image/png", headers["content-type"])
        self.assertEqual(expected.read_bytes(), image)

        for path in (self.base, f"{self.base}/{self.digest}", image_url):
            status, headers, raw = self.request(path, method="HEAD")
            self.assertEqual(200, status)
            self.assertEqual(b"", raw)
            self.assertGreater(int(headers["content-length"]), 0)

    def test_missing_malformed_tampered_and_unsafe_side_fail_safely(self) -> None:
        for digest in ("0" * 64, "not-a-sha"):
            status, error, raw = self.json_request(f"{self.base}/{digest}")
            self.assertEqual(404, status)
            self.assertEqual("split_preview_not_found", error["error"])
            self.assertNotIn(str(self.root).encode(), raw)

        path = f"{self.base}/{self.digest}/parts/up/image"
        status, error, _ = self.json_request(path)
        self.assertEqual(400, status)
        self.assertEqual("invalid_split_side", error["error"])
        status, error, _ = self.json_request(
            f"{self.base}/{self.digest}/parts/%2e%2e/image"
        )
        self.assertEqual(400, status)
        self.assertEqual("invalid_path", error["error"])

        self.artifact_path.write_text("{}", encoding="utf-8")
        status, error, raw = self.json_request(f"{self.base}/{self.digest}")
        self.assertEqual(500, status)
        self.assertEqual("split_preview_repository_error", error["error"])
        self.assertNotIn(str(self.root).encode(), raw)

    def test_wrong_project_artifact_and_corrupt_bundle_are_safe_errors(self) -> None:
        wrong = deepcopy(self.document)
        wrong["project_id"] = "other-project"
        published = ImmutableJsonArtifactStore(self.fixture.state).publish(
            "split-previews", "fixture-project", wrong
        )
        status, error, raw = self.json_request(f"{self.base}/{published.sha256}")
        self.assertEqual(500, status)
        self.assertEqual("split_preview_repository_error", error["error"])
        self.assertNotIn(str(self.root).encode(), raw)

        bundle = LayerManifestBundleReader(self.fixture.state).load(
            "fixture-project", self.publication["manifest_sha256"]
        )
        child_id = self.document["review_target"]["parts"]["left"]["layer_id"]
        child_path = bundle.path / "layers" / f"{child_id}.png"
        child_path.write_bytes(b"not a PNG")
        image_url = f"{self.base}/{self.digest}/parts/left/image"
        status, error, raw = self.json_request(image_url)
        self.assertEqual(500, status)
        self.assertEqual("split_preview_repository_error", error["error"])
        self.assertNotIn(str(self.root).encode(), raw)

    def test_index_caps_total_bytes_and_unsafe_entries_fail_closed(self) -> None:
        with patch(
            "autospine_workbench.split_preview_repository._MAX_ITEMS", 0
        ):
            status, error, _ = self.json_request(self.base)
        self.assertEqual(500, status)
        self.assertEqual("split_preview_repository_error", error["error"])

        with patch(
            "autospine_workbench.split_preview_repository._MAX_LIST_BYTES", 1
        ):
            status, error, _ = self.json_request(self.base)
        self.assertEqual(500, status)
        self.assertEqual("split_preview_repository_error", error["error"])

        unsafe = self.artifact_path.parent / "not-content-addressed.json"
        unsafe.write_text("{}", encoding="utf-8")
        status, error, raw = self.json_request(self.base)
        self.assertEqual(500, status)
        self.assertEqual("split_preview_repository_error", error["error"])
        self.assertNotIn(str(self.root).encode(), raw)


if __name__ == "__main__":
    unittest.main()
