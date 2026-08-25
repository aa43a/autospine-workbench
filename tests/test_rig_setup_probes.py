"""Deterministic setup probe coverage for P2 region-only rigs."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from autospine_workbench.rig_fk import compile_setup_bones  # noqa: E402
from autospine_workbench.rig_setup_probes import run_setup_probes  # noqa: E402
from tests.png_helpers import write_rgba  # noqa: E402


IMAGE_SHA = "a" * 64
OVERRIDE_SHA = "b" * 64


def source_skeleton() -> dict:
    return {
        "joints": [
            {"id": "a", "x": 10, "y": 20, "confidence": 0.9, "decision_kind": "manual_absolute"},
            {"id": "b", "x": 10, "y": 30, "confidence": 0.8, "decision_kind": "manual_absolute"},
            {"id": "c", "x": 0, "y": 30, "confidence": 0.7, "decision_kind": "manual_absolute"},
        ],
        "bones": [
            {"id": "child", "parent_id": "parent", "start_joint_id": "b", "end_joint_id": "c"},
            {"id": "parent", "parent_id": None, "start_joint_id": "a", "end_joint_id": "b"},
        ],
    }


def manifest_fixture() -> dict:
    layers = []
    for layer_id, offset, size, pivot, order in (
        ("layer-parent", [5, 6], [4, 5], [12, 25], 3),
        ("layer-child", [1, 2], [6, 7], [3, 30], 7),
    ):
        layers.append(
            {
                "layer_id": layer_id,
                "source": {"visible": True, "opacity": 1.0, "blend_mode": "normal"},
                "raster": {
                    "artifact_path": f"layers/{layer_id}.png",
                    "sha256": IMAGE_SHA,
                    "canvas_size": [100, 200],
                    "canvas_offset_xy": offset,
                    "crop_bbox_xywh": [*offset, *size],
                },
                "semantic": {"mapping_method": "manual"},
                "rig_hint": {
                    "attachment_kind": "region",
                    "candidate_bone": "parent" if layer_id == "layer-parent" else "child",
                    "pivot": {"xy": pivot, "method": "manual", "confidence": 1.0},
                    "setup_draw_order": order,
                },
                "qa": {"status": "passed"},
            }
        )
    return {
        "format": "autospine-layer-manifest",
        "format_version": 1,
        "project_id": "sample",
        "revision": 2,
        "source": {"canvas": [100, 200]},
        "layers": layers,
        "qa": {"status": "passed", "flags": [], "notes": []},
    }


def resolved_fixture() -> dict:
    resolved = {
        "schema_version": "autospine.resolved-project/v1",
        "project_id": "sample",
        "revision": 2,
        "inputs": {"override_sha256": OVERRIDE_SHA},
        "canvas": {"width": 100, "height": 200},
        "skeleton": source_skeleton(),
        "qa": {"status": "ready"},
    }
    resolved["sha256"] = canonical_sha256(resolved)
    return resolved


def rig_fixture(manifest: dict) -> dict:
    bones = compile_setup_bones(source_skeleton())
    slots = []
    attachments = []
    skin: dict[str, list[str]] = {}
    for index, (layer_id, bone_id) in enumerate((("layer-parent", "parent"), ("layer-child", "child"))):
        layer = next(item for item in manifest["layers"] if item["layer_id"] == layer_id)
        raster, hint = layer["raster"], layer["rig_hint"]
        slot_id, attachment_id = f"slot-{index}", f"attachment-{index}"
        slots.append(
            {
                "id": slot_id,
                "bone": bone_id,
                "setup_attachment": attachment_id,
                "setup_draw_order": hint["setup_draw_order"],
                "blend": "normal",
                "color_rgba": "ffffffff",
            }
        )
        attachments.append(
            {
                "id": attachment_id,
                "slot": slot_id,
                "type": "region",
                "image_path": raster["artifact_path"],
                "image_sha256": raster["sha256"],
                "source_layer_ids": [layer_id],
                "canvas_offset_xy": raster["canvas_offset_xy"],
                "pivot_xy": hint["pivot"]["xy"],
                "size": raster["crop_bbox_xywh"][2:4],
            }
        )
        skin[slot_id] = [attachment_id]
    return {
        "format": "autospine-rig-ir",
        "format_version": 1,
        "source": {
            "layer_manifest_sha256": canonical_sha256(manifest),
            "override_patch_sha256": OVERRIDE_SHA,
        },
        "canvas": {"width": 100, "height": 200},
        "capabilities": ["region_attachment", "bone_rotate", "setup_draw_order"],
        "bones": bones,
        "slots": slots,
        "attachments": attachments,
        "skins": {"default": skin},
    }


def report_for(rig: dict, manifest: dict, resolved: dict) -> dict:
    return run_setup_probes(
        rig,
        manifest,
        resolved,
        rig_sha256=canonical_sha256(rig),
    )


def checks_by_id(report: dict) -> dict:
    return {check["id"]: check for check in report["checks"]}


class RigSetupProbeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = manifest_fixture()
        self.resolved = resolved_fixture()
        self.rig = rig_fixture(self.manifest)

    def test_valid_region_rig_passes_deterministically(self) -> None:
        first = report_for(self.rig, self.manifest, self.resolved)
        second = report_for(self.rig, self.manifest, self.resolved)
        self.assertEqual(first, second)
        self.assertEqual("autospine-rig-setup-probes", first["format"])
        self.assertEqual({"id": "rig-setup-probes", "version": "1.1.0"}, first["runner"])
        self.assertEqual("passed", first["status"])
        self.assertTrue(all(check["status"] == "passed" for check in first["checks"]))
        fk = checks_by_id(first)["fk.setup-reconstruction"]["metrics"]
        self.assertLessEqual(fk["max_origin_error_px"], 1e-6)
        self.assertLessEqual(fk["max_endpoint_error_px"], 1e-6)

    def test_wrong_parent_is_reported_by_parent_and_fk_checks(self) -> None:
        rig = deepcopy(self.rig)
        rig["bones"][1]["parent"] = None
        report = report_for(rig, self.manifest, self.resolved)
        checks = checks_by_id(report)
        self.assertEqual("rejected", checks["bones.parent-links"]["status"])
        self.assertEqual("rejected", checks["fk.setup-reconstruction"]["status"])
        self.assertEqual("rejected", report["status"])

    def test_full_local_setup_including_scale_must_match_compiler(self) -> None:
        rig = deepcopy(self.rig)
        rig["bones"][-1]["setup"]["scale_y"] = 2.0
        check = checks_by_id(report_for(rig, self.manifest, self.resolved))[
            "fk.setup-reconstruction"
        ]
        self.assertEqual("rejected", check["status"])
        self.assertEqual(1.0, check["metrics"]["max_local_setup_error"])

    def test_wrong_pivot_and_roundtrip_input_are_rejected(self) -> None:
        rig = deepcopy(self.rig)
        rig["attachments"][0]["pivot_xy"] = [99, 88]
        check = checks_by_id(report_for(rig, self.manifest, self.resolved))[
            "attachments.pivot-roundtrip"
        ]
        self.assertEqual("rejected", check["status"])
        self.assertIn("does not match manifest", check["message"])

    def test_draw_order_must_be_unique_and_preserve_manifest_order(self) -> None:
        reversed_rig = deepcopy(self.rig)
        reversed_rig["slots"][0]["setup_draw_order"] = 1
        reversed_rig["slots"][1]["setup_draw_order"] = 0
        check = checks_by_id(report_for(reversed_rig, self.manifest, self.resolved))[
            "slots.draw-order"
        ]
        self.assertEqual("rejected", check["status"])
        self.assertIn("relative order", check["message"])

        duplicate = deepcopy(self.rig)
        duplicate["slots"][1]["setup_draw_order"] = duplicate["slots"][0]["setup_draw_order"]
        check = checks_by_id(report_for(duplicate, self.manifest, self.resolved))[
            "slots.draw-order"
        ]
        self.assertEqual("rejected", check["status"])
        self.assertIn("duplicate setup draw order", check["message"])

    def test_region_contract_and_source_hash_fail_closed(self) -> None:
        rig = deepcopy(self.rig)
        rig["attachments"][0]["type"] = "mesh"
        binding = checks_by_id(report_for(rig, self.manifest, self.resolved))[
            "attachments.region-bindings"
        ]
        self.assertEqual("rejected", binding["status"])

        wrong_hash = run_setup_probes(
            self.rig,
            self.manifest,
            self.resolved,
            rig_sha256="0" * 64,
        )
        self.assertEqual("rejected", checks_by_id(wrong_hash)["source.identity"]["status"])

    def test_hidden_and_full_canvas_regions_preserve_setup_semantics(self) -> None:
        manifest = deepcopy(self.manifest)
        manifest["layers"][0]["source"]["visible"] = False
        manifest["layers"][1]["raster"]["canvas_offset_xy"] = [0, 0]
        rig = rig_fixture(manifest)
        rig["slots"][0]["setup_attachment"] = None
        rig["attachments"][1]["size"] = [100, 200]
        report = report_for(rig, manifest, self.resolved)
        self.assertEqual("passed", report["status"])
        self.assertEqual(
            "passed",
            checks_by_id(report)["attachments.region-bindings"]["status"],
        )

    def test_unreviewed_inputs_are_manual_required_not_silently_passed(self) -> None:
        manifest = deepcopy(self.manifest)
        manifest["qa"]["status"] = "manual_required"
        manifest["layers"][0]["semantic"]["mapping_method"] = "alias"
        rig = rig_fixture(manifest)
        report = report_for(rig, manifest, self.resolved)
        self.assertEqual("manual_required", report["status"])
        review = checks_by_id(report)["inputs.reviewed"]
        self.assertEqual("manual_required", review["status"])
        self.assertIn("not manual", review["message"])

    def test_review_probe_matches_candidate_binding_and_layer_qa_gate(self) -> None:
        manifest = deepcopy(self.manifest)
        manifest["layers"][0]["rig_hint"]["candidate_bone"] = None
        manifest["layers"][1]["qa"]["status"] = "manual_required"
        rig = rig_fixture(manifest)
        report = report_for(rig, manifest, self.resolved)
        review = checks_by_id(report)["inputs.reviewed"]
        self.assertEqual("manual_required", report["status"])
        self.assertEqual("manual_required", review["status"])
        self.assertIn("bone binding requires review", review["message"])
        self.assertIn("QA requires review", review["message"])

    def test_source_identity_rejects_revision_canvas_and_override_mismatch(self) -> None:
        manifest = deepcopy(self.manifest)
        manifest["revision"] = 3
        report = report_for(rig_fixture(manifest), manifest, self.resolved)
        source = checks_by_id(report)["source.identity"]
        self.assertEqual("rejected", source["status"])
        self.assertIn("revisions do not match", source["message"])

        resolved = deepcopy(self.resolved)
        resolved["canvas"]["width"] = 101
        resolved.pop("sha256")
        resolved["sha256"] = canonical_sha256(resolved)
        source = checks_by_id(report_for(self.rig, self.manifest, resolved))["source.identity"]
        self.assertEqual("rejected", source["status"])
        self.assertIn("canvases do not match", source["message"])

        rig = deepcopy(self.rig)
        rig["source"]["override_patch_sha256"] = "c" * 64
        source = checks_by_id(report_for(rig, self.manifest, self.resolved))["source.identity"]
        self.assertEqual("rejected", source["status"])
        self.assertIn("override binding", source["message"])

    def test_asset_probe_requires_pixel_exact_setup_reconstruction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory)
            (bundle / "layers").mkdir()
            for layer in self.manifest["layers"]:
                width, height = layer["raster"]["crop_bbox_xywh"][2:4]
                rows = [[(30, 80, 120, 200)] * width for _ in range(height)]
                write_rgba(bundle / layer["raster"]["artifact_path"], rows)
            report = run_setup_probes(
                self.rig,
                self.manifest,
                self.resolved,
                rig_sha256=canonical_sha256(self.rig),
                bundle_path=bundle,
            )
            pixel = checks_by_id(report)["setup.pixel-reconstruction"]
            self.assertEqual("passed", pixel["status"])
            self.assertTrue(pixel["metrics"]["exact"])

            changed = deepcopy(self.rig)
            changed["attachments"][0]["canvas_offset_xy"] = [6, 6]
            report = run_setup_probes(
                changed,
                self.manifest,
                self.resolved,
                rig_sha256=canonical_sha256(changed),
                bundle_path=bundle,
            )
            self.assertEqual(
                "rejected",
                checks_by_id(report)["setup.pixel-reconstruction"]["status"],
            )


if __name__ == "__main__":
    unittest.main()
