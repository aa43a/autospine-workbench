"""Replay validation for bundled bilateral split provenance."""

from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.alpha_bilateral_split import split_alpha_bilateral  # noqa: E402
from autospine_workbench.layer_manifest import sha256_file  # noqa: E402
from autospine_workbench.png_rgba import RgbaImage, write_rgba_png  # noqa: E402
from autospine_workbench.split_bundle_validation import (  # noqa: E402
    SplitBundleValidationError,
    validate_split_bundle,
)
from autospine_workbench.split_derivation_contract import (  # noqa: E402
    SPLIT_ALGORITHM_ID,
    SPLIT_ALGORITHM_VERSION,
    build_split_derivation,
)


def layer(layer_id, path, *, side, kind, derivation, alpha_nonzero):
    return {
        "layer_id": layer_id,
        "source": {"visible": kind == "region"},
        "raster": {
            "artifact_path": f"layers/{path.name}",
            "sha256": sha256_file(path),
            "crop_bbox_xywh": [10, 20, 3, 1],
            "canvas_offset_xy": [10, 20],
            "alpha_nonzero": alpha_nonzero,
        },
        "semantic": {"canonical_role": "body.foot", "side": side},
        "derivation": derivation,
        "rig_hint": {"attachment_kind": kind},
    }


class SplitBundleValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        source = RgbaImage(
            3,
            1,
            bytes([10, 20, 30, 255, 40, 50, 60, 128, 70, 80, 90, 255]),
        )
        split = split_alpha_bilateral(
            source,
            canvas_offset_xy=(10, 20),
            left_polyline_xy=((10, 19), (10, 21)),
            right_polyline_xy=((12, 19), (12, 21)),
        )
        self.paths = {
            "parent": root / "parent.png",
            "parent--left": root / "left.png",
            "parent--right": root / "right.png",
        }
        write_rgba_png(self.paths["parent"], source)
        write_rgba_png(self.paths["parent--left"], split.left)
        write_rgba_png(self.paths["parent--right"], split.right)
        config = {
            "format": "autospine-bilateral-alpha-split",
            "format_version": 1,
            "algorithm": {
                "id": SPLIT_ALGORITHM_ID,
                "version": SPLIT_ALGORITHM_VERSION,
            },
            "source_layer_id": "parent",
            "source_raster_sha256": sha256_file(self.paths["parent"]),
            "source_rgba_sha256": hashlib.sha256(source.pixels).hexdigest(),
            "output_rgba_sha256": {
                "left": hashlib.sha256(split.left.pixels).hexdigest(),
                "right": hashlib.sha256(split.right.pixels).hexdigest(),
            },
            "canvas_offset_xy": [10, 20],
            "guide_anchors": {
                "left": [
                    self.resolved_anchor("knee.left", [10, 19]),
                    self.resolved_anchor("ankle.left", [10, 21]),
                ],
                "right": [
                    self.resolved_anchor("knee.right", [12, 19]),
                    self.resolved_anchor("ankle.right", [12, 21]),
                ],
            },
            "tie_break": "left",
            "exact_partition": True,
        }
        derivation = build_split_derivation(config)
        self.manifest = {
            "layers": [
                layer(
                    "parent",
                    self.paths["parent"],
                    side="bilateral",
                    kind="excluded",
                    derivation={"operation": "source", "parent_layer_ids": []},
                    alpha_nonzero=3,
                ),
                layer(
                    "parent--left",
                    self.paths["parent--left"],
                    side="left",
                    kind="region",
                    derivation=derivation,
                    alpha_nonzero=2,
                ),
                layer(
                    "parent--right",
                    self.paths["parent--right"],
                    side="right",
                    kind="region",
                    derivation=derivation,
                    alpha_nonzero=1,
                ),
            ]
        }

    @staticmethod
    def resolved_anchor(joint_id, xy):
        return {
            "kind": "resolved_joint",
            "joint_id": joint_id,
            "xy": xy,
            "review_state": "manual_adjusted",
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_replays_exact_children_from_bundled_parent(self) -> None:
        validate_split_bundle(self.manifest, self.paths)

    def test_replay_uses_manual_proxy_anchor_coordinates(self) -> None:
        manifest = deepcopy(self.manifest)
        config = deepcopy(manifest["layers"][1]["derivation"]["operation_config"])
        config["guide_anchors"]["left"] = [
            {
                "kind": "manual_proxy",
                "proxy_id": "shoe-upper.left",
                "xy": [10, 19],
                "proxy_for_joint_id": "knee.left",
                "label": "shoe opening upper",
                "reason": "leg joint is hidden",
            },
            {
                "kind": "manual_proxy",
                "proxy_id": "shoe-lower.left",
                "xy": [10, 21],
                "label": "shoe opening lower",
                "reason": "ankle joint is hidden",
            },
        ]
        changed = build_split_derivation(config)
        manifest["layers"][1]["derivation"] = changed
        manifest["layers"][2]["derivation"] = changed
        validate_split_bundle(manifest, self.paths)

    def test_missing_or_nonexcluded_parent_fails_closed(self) -> None:
        for mutation in ("missing", "region"):
            manifest = deepcopy(self.manifest)
            if mutation == "missing":
                manifest["layers"].pop(0)
            else:
                manifest["layers"][0]["rig_hint"]["attachment_kind"] = "region"
            with self.subTest(mutation=mutation), self.assertRaises(
                SplitBundleValidationError
            ):
                validate_split_bundle(manifest, self.paths)

    def test_duplicate_side_or_swapped_pixels_fails_closed(self) -> None:
        duplicate = deepcopy(self.manifest)
        duplicate["layers"][2]["semantic"]["side"] = "left"
        with self.assertRaisesRegex(SplitBundleValidationError, "one child per side"):
            validate_split_bundle(duplicate, self.paths)
        swapped_paths = dict(self.paths)
        swapped_paths["parent--left"] = self.paths["parent--right"]
        swapped_paths["parent--right"] = self.paths["parent--left"]
        with self.assertRaisesRegex(SplitBundleValidationError, "pixels differ"):
            validate_split_bundle(self.manifest, swapped_paths)

    def test_child_ids_are_stable_from_parent_and_side(self) -> None:
        manifest = deepcopy(self.manifest)
        manifest["layers"][1]["layer_id"] = "renamed-left"
        paths = dict(self.paths)
        paths["renamed-left"] = paths.pop("parent--left")

        with self.assertRaisesRegex(SplitBundleValidationError, "id is not stable"):
            validate_split_bundle(manifest, paths)

    def test_output_hash_and_alpha_metrics_are_verified(self) -> None:
        manifest = deepcopy(self.manifest)
        derivation = manifest["layers"][1]["derivation"]
        config = deepcopy(derivation["operation_config"])
        config["output_rgba_sha256"]["left"] = "f" * 64
        changed = build_split_derivation(config)
        manifest["layers"][1]["derivation"] = changed
        manifest["layers"][2]["derivation"] = changed
        with self.assertRaisesRegex(SplitBundleValidationError, "RGBA hash"):
            validate_split_bundle(manifest, self.paths)
        manifest = deepcopy(self.manifest)
        manifest["layers"][1]["raster"]["alpha_nonzero"] = 1
        with self.assertRaisesRegex(SplitBundleValidationError, "alpha count"):
            validate_split_bundle(manifest, self.paths)


if __name__ == "__main__":
    unittest.main()
