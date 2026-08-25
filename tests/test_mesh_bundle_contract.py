"""Immutable P3 mesh bundle contract tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.mesh_bundle_contract import (  # noqa: E402
    BUNDLE_ADDRESS_DOMAIN,
    MeshBundleContractError,
    build_mesh_bundle_contract,
    mesh_bundle_address_sha256,
)
from autospine_workbench.mesh_probe_report import build_mesh_probe_report  # noqa: E402
from autospine_workbench.mesh_rig import compile_mesh_rig  # noqa: E402
from autospine_workbench.mesh_visual_artifacts import renderer_identities  # noqa: E402
from autospine_workbench.png_rgba import RgbaImage, encode_rgba_png  # noqa: E402
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from tests.test_mesh_rig import BASE_BUNDLE_SHA, compile_a, images_a  # noqa: E402
from tests.test_region_rig import compile_fixture, manifest_fixture  # noqa: E402


def _artifact(path, kind, identifier, pose, bone, angle, png, image):
    return {
        "kind": kind, "id": identifier, "pose": pose, "bone": bone,
        "angle_deg": angle, "width": image.width, "height": image.height,
        "rgba_sha256": hashlib.sha256(image.pixels).hexdigest(),
        "png_sha256": hashlib.sha256(png).hexdigest(), "path": path,
    }


def _visuals(rig, run, probes, targets, target_images):
    image = RgbaImage(2, 2, bytes((10, 20, 30, 255)) * 4)
    png = encode_rgba_png(image)
    artifacts, pngs = [], {}
    for target in targets:
        identifier, bone = target.attachment_id, target.distal_bone_id
        entries = (
            _artifact(f"weights/{identifier}.png", "weight_heatmap", identifier,
                      "weights", bone, None, png, image),
            _artifact(f"poses/{identifier}.setup.png", "pose", identifier,
                      "setup", None, 0, png, image),
            _artifact(f"poses/{identifier}.widest-safe-p005.png", "pose", identifier,
                      "widest-safe", bone, 5, png, image),
        )
        for entry in entries:
            artifacts.append(entry)
            pngs[entry["path"]] = png
    artifacts.sort(key=lambda item: item["path"])
    ordered = sorted(targets, key=lambda item: item.attachment_id)
    document = {
        "format": "autospine-mesh-visual-artifacts", "format_version": 1,
        "project_id": run["project_id"],
        "source": {"rig_sha256": canonical_sha256(rig),
                   "run_manifest_sha256": canonical_sha256(run),
                   "probes_sha256": canonical_sha256(probes)},
        "renderers": renderer_identities(), "status": "passed",
        "summary": f"converted={len(ordered)}" if ordered else "reviewed-noop",
        "images": [{"id": item.attachment_id,
                    "width": target_images[item.attachment_id].width,
                    "height": target_images[item.attachment_id].height,
                    "rgba_sha256": hashlib.sha256(
                        target_images[item.attachment_id].pixels).hexdigest()}
                   for item in ordered],
        "targets": [{name: getattr(item, name) for name in (
            "attachment_id", "source_layer_id", "side",
            "proximal_bone_id", "distal_bone_id")}
            for item in ordered],
        "artifacts": artifacts,
    }
    return document, dict(sorted(pngs.items()))


def payload_a():
    compiled = compile_a()
    rig, run, targets = compiled.rig, compiled.run_manifest, compiled.targets
    probes = build_mesh_probe_report(rig, run, targets).document
    visuals, pngs = _visuals(rig, run, probes, targets, images_a())
    return run["project_id"], rig, run, probes, visuals, pngs


def payload_noop():
    base = compile_fixture()
    compiled = compile_mesh_rig(
        base.rig, base.run_manifest, manifest_fixture(), {},
        base_bundle_sha256=BASE_BUNDLE_SHA,
    )
    rig, run, targets = compiled.rig, compiled.run_manifest, compiled.targets
    probes = build_mesh_probe_report(rig, run, targets).document
    visuals, pngs = _visuals(rig, run, probes, targets, {})
    return run["project_id"], rig, run, probes, visuals, pngs


def reverse_keys(value):
    if isinstance(value, dict):
        return {key: reverse_keys(item) for key, item in reversed(list(value.items()))}
    if isinstance(value, list):
        return [reverse_keys(item) for item in value]
    return value


class MeshBundleContractTests(unittest.TestCase):
    def test_build_is_deterministic_canonical_frozen_and_non_mutating(self):
        values = payload_a()
        before = deepcopy(values)
        first = build_mesh_bundle_contract(*values)
        changed = (values[0], *(reverse_keys(item) for item in values[1:5]),
                   dict(reversed(list(values[5].items()))))
        second = build_mesh_bundle_contract(*changed)
        self.assertEqual(first, second)
        self.assertEqual(before, values)
        self.assertEqual(
            json.dumps(values[1], ensure_ascii=False, allow_nan=False,
                       sort_keys=True, separators=(",", ":")).encode(),
            first.document_bytes["rig.json"],
        )
        documents = first.document_bytes
        documents.clear()
        pngs = first.png_bytes_by_path
        pngs.clear()
        self.assertTrue(first.document_bytes)
        self.assertTrue(first.png_bytes_by_path)
        with self.assertRaises(FrozenInstanceError):
            first.bundle_sha256 = "0" * 64  # type: ignore[misc]

    def test_address_domain_binds_all_documents_paths_and_pngs(self):
        baseline = mesh_bundle_address_sha256(
            "a" * 64, "b" * 64, "c" * 64, "d" * 64,
            {"weights/a.png": "e" * 64, "poses/a.setup.png": "f" * 64},
        )
        reordered = mesh_bundle_address_sha256(
            "a" * 64, "b" * 64, "c" * 64, "d" * 64,
            {"poses/a.setup.png": "f" * 64, "weights/a.png": "e" * 64},
        )
        self.assertEqual(baseline, reordered)
        self.assertEqual("autospine-mesh-rig-bundle-address/v1", BUNDLE_ADDRESS_DOMAIN)
        for args in (
            ("0" * 64, "b" * 64, "c" * 64, "d" * 64,
             {"weights/a.png": "e" * 64}),
            ("a" * 64, "b" * 64, "c" * 64, "d" * 64,
             {"weights/b.png": "e" * 64}),
            ("a" * 64, "b" * 64, "c" * 64, "d" * 64,
             {"weights/a.png": "0" * 64}),
        ):
            self.assertNotEqual(baseline, mesh_bundle_address_sha256(*args))

    def test_cross_bindings_project_status_and_renderer_fail_closed(self):
        for location, key, value in (
            (2, "project_id", "other"), (3, "status", "rejected"),
            (4, "status", "rejected"),
        ):
            values = list(deepcopy(payload_a()))
            values[location][key] = value
            with self.subTest(location=location, key=key), self.assertRaises(MeshBundleContractError):
                build_mesh_bundle_contract(*values)
        values = list(deepcopy(payload_a()))
        values[4]["renderers"]["pose"]["sampling"] = "linear"
        with self.assertRaises(MeshBundleContractError):
            build_mesh_bundle_contract(*values)

    def test_source_binding_and_unknown_fields_fail_closed(self):
        for document, key in ((1, "run_manifest_sha256"), (3, "rig_sha256"),
                              (4, "probes_sha256")):
            values = list(deepcopy(payload_a()))
            values[document]["source"][key] = "0" * 64
            with self.subTest(document=document), self.assertRaises(MeshBundleContractError):
                build_mesh_bundle_contract(*values)
        values = list(deepcopy(payload_a()))
        values[4]["extra"] = True
        with self.assertRaises(MeshBundleContractError):
            build_mesh_bundle_contract(*values)

    def test_sorted_targets_images_summary_and_artifact_semantics_are_strict(self):
        mutations = (
            lambda doc: doc["targets"].reverse(),
            lambda doc: doc["images"].reverse(),
            lambda doc: doc.update(summary="converted=3"),
            lambda doc: doc["artifacts"][0].update(kind="weight_heatmap"),
            lambda doc: doc["artifacts"][0].update(angle_deg=7),
            lambda doc: doc["artifacts"][0].update(path="poses/../escape.png"),
        )
        for mutate in mutations:
            values = list(deepcopy(payload_a()))
            mutate(values[4])
            with self.subTest(mutate=mutate), self.assertRaises(MeshBundleContractError):
                build_mesh_bundle_contract(*values)

    def test_png_inventory_case_alias_metadata_and_bytes_are_strict(self):
        cases = []
        missing = list(deepcopy(payload_a()))
        missing[5].pop(next(iter(missing[5])))
        cases.append(missing)
        extra = list(deepcopy(payload_a()))
        extra[5]["weights/extra.png"] = next(iter(extra[5].values()))
        cases.append(extra)
        metadata = list(deepcopy(payload_a()))
        metadata[4]["artifacts"][0]["png_sha256"] = "0" * 64
        cases.append(metadata)
        truncated = list(deepcopy(payload_a()))
        path = next(iter(truncated[5]))
        truncated[5][path] = truncated[5][path][:-1]
        cases.append(truncated)
        for values in cases:
            with self.subTest(paths=set(values[5])), self.assertRaises(MeshBundleContractError):
                build_mesh_bundle_contract(*values)
        with self.assertRaises(MeshBundleContractError):
            mesh_bundle_address_sha256("a" * 64, "b" * 64, "c" * 64, "d" * 64,
                                       {"weights/A.png": "e" * 64,
                                        "weights/a.png": "f" * 64})

    def test_each_png_is_decoded_once_and_resource_limits_apply(self):
        values = payload_a()
        from autospine_workbench import mesh_bundle_contract as module
        with patch.object(module, "decode_rgba_png", wraps=module.decode_rgba_png) as decode:
            build_mesh_bundle_contract(*values)
        self.assertEqual(len(values[5]), decode.call_count)
        with patch.object(module, "MAX_TOTAL_PNG_BYTES", 1):
            with self.assertRaisesRegex(MeshBundleContractError, "resource limit"):
                build_mesh_bundle_contract(*values)

    def test_noop_bundle_has_no_pngs_and_unsafe_project_is_rejected(self):
        contract = build_mesh_bundle_contract(*payload_noop())
        self.assertEqual({}, contract.png_bytes_by_path)
        self.assertEqual(tuple(contract.document_bytes), contract.inventory)
        values = list(payload_noop())
        values[0] = "../escape"
        with self.assertRaises(MeshBundleContractError):
            build_mesh_bundle_contract(*values)


if __name__ == "__main__":
    unittest.main()
