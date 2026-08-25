"""Approved identity and evidence regression for the two real P3 samples."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.mesh_bundle_reader import VerifiedMeshBundleReader  # noqa: E402


GOLDEN_ROOT = ROOT / "tests" / "goldens" / "p3-mesh"
SOURCE_KEYS = {
    "base_rig_sha256", "base_bundle_sha256", "layer_manifest_sha256",
    "resolved_project_sha256", "rig_sha256", "run_sha256", "probes_sha256",
    "visuals_sha256", "bundle_sha256",
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _contracts() -> list[dict]:
    return [_strict_json(path) for path in sorted(GOLDEN_ROOT.glob("*.approved.json"))]


def _strict_json(path: Path) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate golden key: {key}")
            result[key] = value
        return result

    def nonfinite(value):
        raise ValueError(f"non-finite golden value: {value}")

    value = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=pairs,
        parse_constant=nonfinite,
    )
    if not isinstance(value, dict):
        raise ValueError("P3 golden must be an object")
    return value


def _projection(verified) -> dict:
    rig, probes, visuals = verified.rig, verified.probes, verified.visuals
    meshes = {item["id"]: item for item in rig["attachments"] if item["type"] == "mesh"}
    probe_by_id = {item["attachment_id"]: item for item in probes["attachments"]}
    artifacts_by_id: dict[str, list[dict]] = {}
    for item in visuals["artifacts"]:
        artifacts_by_id.setdefault(item["id"], []).append({
            key: item[key] for key in (
                "kind", "pose", "path", "angle_deg", "width", "height",
                "rgba_sha256", "png_sha256",
            )
        })
    targets = []
    for target in sorted(visuals["targets"], key=lambda item: item["attachment_id"]):
        identifier = target["attachment_id"]
        mesh, probe = meshes[identifier], probe_by_id[identifier]
        bend = probe["action_probe"]["distal_bend"]
        targets.append({
            **target,
            "vertex_count": len(mesh["vertices"]),
            "triangle_count": len(mesh["triangles"]) // 3,
            "continuous_safe_angle_deg": {
                "minimum": -bend["negative"]["max_contiguous_magnitude_deg"],
                "maximum": bend["positive"]["max_contiguous_magnitude_deg"],
            },
            "widest_safe_bend": probe["widest_safe_bend"],
            "artifacts": sorted(
                artifacts_by_id[identifier], key=lambda item: (item["pose"], item["path"])
            ),
        })
    return {
        "format": "autospine-p3-mesh-golden",
        "format_version": 1,
        "project_id": verified.project_id,
        "source": {
            "base_rig_sha256": verified.base_rig_sha256,
            "base_bundle_sha256": verified.base_bundle_sha256,
            "layer_manifest_sha256": verified.layer_manifest_sha256,
            "resolved_project_sha256": verified.resolved_project_sha256,
            "rig_sha256": verified.rig_sha256,
            "run_sha256": verified.run_sha256,
            "probes_sha256": verified.probes_sha256,
            "visuals_sha256": verified.visuals_sha256,
            "bundle_sha256": verified.bundle_sha256,
        },
        "summary": visuals["summary"],
        "totals": {
            "target_count": len(targets),
            "vertex_count": sum(item["vertex_count"] for item in targets),
            "triangle_count": sum(item["triangle_count"] for item in targets),
            "artifact_count": sum(len(item["artifacts"]) for item in targets),
        },
        "targets": targets,
    }


class P3MeshGoldenTests(unittest.TestCase):
    def test_approved_contracts_are_strict_complete_and_semantic(self) -> None:
        contracts = _contracts()
        self.assertEqual(2, len(contracts))
        self.assertEqual(2, len({item["project_id"] for item in contracts}))
        for item in contracts:
            with self.subTest(project=item["project_id"]):
                self.assertEqual({
                    "format", "format_version", "project_id", "source",
                    "summary", "totals", "targets",
                }, set(item))
                self.assertEqual("autospine-p3-mesh-golden", item["format"])
                self.assertEqual(1, item["format_version"])
                self.assertEqual(SOURCE_KEYS, set(item["source"]))
                self.assertTrue(all(SHA256.fullmatch(value) for value in item["source"].values()))
                count = len(item["targets"])
                expected = f"converted={count}" if count else "reviewed-noop"
                self.assertEqual(expected, item["summary"])
                self.assertEqual(count, item["totals"]["target_count"])
                self.assertEqual(count * 3, item["totals"]["artifact_count"])

    @unittest.skipUnless(
        os.environ.get("AUTOSPINE_VERIFY_REAL_P3_GOLDENS") == "1",
        "real P3 golden verification is explicitly enabled",
    )
    def test_real_bundles_reproduce_approved_contracts(self) -> None:
        state_root = ROOT / "workspace"
        for approved in _contracts():
            source = approved["source"]
            with self.subTest(project=approved["project_id"]):
                verified = VerifiedMeshBundleReader(state_root).load(
                    approved["project_id"], source["rig_sha256"], source["bundle_sha256"]
                )
                self.assertEqual(approved, _projection(verified))


if __name__ == "__main__":
    unittest.main()
