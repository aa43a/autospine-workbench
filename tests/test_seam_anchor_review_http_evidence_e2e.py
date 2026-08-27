"""Live persisted-P3 evidence path for P10.5b seam-anchor review."""

from __future__ import annotations

import hashlib
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

from autospine_workbench.layer_manifest import LayerManifestBundleStore
from autospine_workbench.mesh_bundle_reader import VerifiedMeshBundleReader
from autospine_workbench.mesh_bundle_store import MeshBundleStore
from autospine_workbench.mesh_pipeline import VerifiedMeshPipeline
from autospine_workbench.region_rig import compile_region_rig
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.rig_bundle import RigBundleStore
from autospine_workbench.server import create_server
from tests.p10_candidate_helpers import PROJECT, _resolved_for_project
from tests.seam_anchor_candidate_helpers import opaque_png
from tests.test_project_store import StoreFixture
from tests.test_verified_mesh_compiler import _probes


_SPECS = (
    ("torso", "body.torso", "center", (20, 10), (20, 20), "spine-chest"),
    ("pelvis", "body.pelvis", "bilateral", (20, 27), (20, 10), "root-pelvis"),
    ("arm.left", "body.arm.upper", "left", (10, 15), (15, 6), "upper-arm.left"),
    ("arm.right", "body.arm.upper", "right", (35, 15), (15, 6), "upper-arm.right"),
    ("leg.left", "body.leg", "left", (21, 33), (6, 16), "thigh.left"),
    ("leg.right", "body.leg", "right", (33, 33), (6, 16), "thigh.right"),
    ("foot.left", "body.foot", "left", (18, 45), (10, 6), "calf.left"),
    ("foot.right", "body.foot", "right", (32, 45), (10, 6), "calf.right"),
)


class _LiveEvidenceFixture:
    def __init__(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.state = self.root / "state"
        manifest, assets, sizes = _manifest_and_assets(self.root / "assets")
        compiled = compile_region_rig(
            manifest,
            _resolved_for_project(),
            layer_manifest_sha256=canonical_sha256(manifest),
            image_sizes=sizes,
        )
        layers, self.manifest_sha = LayerManifestBundleStore(
            self.state
        ).publish(PROJECT, manifest, assets)
        rig_path, rig_sha = RigBundleStore(self.state).publish(
            PROJECT, compiled.rig, compiled.run_manifest,
            _probes(PROJECT, compiled.rig, compiled.run_manifest), layers,
        )
        result = VerifiedMeshPipeline(self.state).build(
            PROJECT, rig_sha, rig_path.name
        )
        address = MeshBundleStore(self.state).publish(
            PROJECT, result.rig, result.run_manifest, result.probes,
            result.visuals, result.pngs,
        )
        self.mesh = VerifiedMeshBundleReader(self.state).load(
            PROJECT, address.rig_sha256, address.bundle_sha256
        )
        project = StoreFixture(self.root / "project")
        project.audit_dir.rename(project.audit_dir.parent / PROJECT)
        self.server = create_server(
            "127.0.0.1", 0, project.workspace,
            web_root=ROOT / "web", state_root=self.state,
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )
        self.thread.start()
        self.host, self.port = self.server.server_address[:2]
        self.base = (
            f"/api/projects/{PROJECT}/seam-anchor-reviews/{self.manifest_sha}/"
            f"{self.mesh.rig_sha256}/{self.mesh.bundle_sha256}"
        )

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.temporary.cleanup()

    def request(self, method: str, path: str):
        connection = http.client.HTTPConnection(
            self.host, self.port, timeout=15
        )
        connection.request(method, path)
        response = connection.getresponse()
        raw = response.read()
        result = (
            response.status,
            {key.lower(): value for key, value in response.getheaders()},
            raw,
        )
        connection.close()
        return result


class SeamAnchorReviewHttpEvidenceEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = _LiveEvidenceFixture()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.fixture.close()

    def test_candidate_option_serves_exact_p3_png_and_rejects_crosswires(self):
        status, _, raw_candidate = self.fixture.request(
            "GET", f"{self.fixture.base}/candidate"
        )
        self.assertEqual(200, status)
        envelope = json.loads(raw_candidate.decode("utf-8"))
        self.assertTrue(envelope["attachment_images"])
        self.assertGreater(
            envelope["candidate"]["summary"]["candidate_option_count"], 0
        )
        self.assertNotIn(str(self.fixture.root), raw_candidate.decode("utf-8"))
        self.assertNotIn('"path"', raw_candidate.decode("utf-8"))

        options = [
            option
            for relationship in envelope["candidate"]["relationships"]
            for option in relationship["options"]
        ]
        option = next(row for row in options if row["status"] == "candidate")
        ref = next(
            row for row in envelope["attachment_images"]
            if row["option_id"] == option["option_id"]
        )
        self.assertIn(ref["attachment_role"], {"parent", "child"})
        self.assertEqual(
            option[f"{ref['attachment_role']}_attachment_id"],
            ref["attachment_id"],
        )

        get_status, get_headers, png = self.fixture.request("GET", ref["url"])
        self.assertEqual(200, get_status)
        self.assertEqual("image/png", get_headers["content-type"])
        self.assertEqual(f'"{ref["image_sha256"]}"', get_headers["etag"])
        self.assertEqual(len(png), int(get_headers["content-length"]))
        self.assertEqual(ref["image_sha256"], hashlib.sha256(png).hexdigest())

        head_status, head_headers, head_body = self.fixture.request(
            "HEAD", ref["url"]
        )
        self.assertEqual(200, head_status)
        self.assertEqual(b"", head_body)
        self.assertEqual(get_headers["etag"], head_headers["etag"])
        self.assertEqual(
            get_headers["content-length"], head_headers["content-length"]
        )

        wrong_sha = "a" * 64 \
            if ref["image_sha256"] != "a" * 64 else "b" * 64
        attacks = (
            ref["url"].replace(
                f"/options/{ref['option_id']}/",
                "/options/not-an-option/",
            ),
            ref["url"][:-64] + wrong_sha,
        )
        for path in attacks:
            with self.subTest(path=path):
                bad_status, _, bad_raw = self.fixture.request("GET", path)
                self.assertEqual(404, bad_status)
                error = json.loads(bad_raw.decode("utf-8"))
                self.assertEqual("seam_anchor_review_not_found", error["error"])
                self.assertNotIn(str(self.fixture.root), bad_raw.decode("utf-8"))


def _manifest_and_assets(directory: Path):
    directory.mkdir()
    assets, sizes, layers = {}, {}, []
    for order, (identifier, role, side, offset, size, bone) in enumerate(_SPECS):
        path = directory / f"{identifier}.png"
        raw = opaque_png(*size)
        path.write_bytes(raw)
        digest = hashlib.sha256(raw).hexdigest()
        assets[identifier] = path
        sizes[identifier] = size
        layers.append(_layer(
            identifier, role, side, offset, size, bone, order, digest
        ))
    return {
        "format": "autospine-layer-manifest", "format_version": 1,
        "project_id": PROJECT, "revision": 1,
        "source": {
            "psd_sha256": "a" * 64, "audit_sha256": "b" * 64,
            "canvas": [400, 400],
            "coordinate_system": {
                "origin": "top_left", "x_axis": "right", "y_axis": "down",
                "units": "pixel", "side_naming": "character_side",
                "view_orientation": "front", "mirror_state": "not_mirrored",
            },
        },
        "layers": layers,
        "qa": {"status": "passed", "flags": [], "notes": []},
    }, assets, sizes


def _layer(identifier, role, side, offset, size, bone, order, digest):
    width, height = size
    return {
        "layer_id": identifier,
        "source": {
            "name": identifier, "index": order, "group_path": [],
            "visible": True, "opacity": 1.0, "blend_mode": "normal",
        },
        "raster": {
            "artifact_path": f"layers/{identifier}.png", "sha256": digest,
            "canvas_size": [400, 400],
            "crop_bbox_xywh": [offset[0], offset[1], width, height],
            "canvas_offset_xy": list(offset), "channels": "RGBA",
            "alpha_mode": "straight", "color_space": "srgb",
            "alpha_nonzero": width * height,
        },
        "semantic": {
            "source_tag": identifier, "canonical_role": role, "side": side,
            "stratum": "front", "instance": 0,
            "mapping_method": "manual", "confidence": 1.0,
        },
        "derivation": {"operation": "source", "parent_layer_ids": []},
        "rig_hint": {
            "attachment_kind": "region", "deform_class": "rigid",
            "candidate_bone": bone,
            "pivot": {
                "xy": [offset[0] + width / 2, offset[1] + height / 2],
                "method": "manual", "confidence": 1.0,
            },
            "setup_draw_order": order,
        },
        "qa": {"status": "passed", "flags": [], "notes": []},
    }


if __name__ == "__main__":
    unittest.main()
