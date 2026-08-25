"""Pinned provenance tests for deterministic bilateral alpha splits."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from autospine_workbench.split_derivation_contract import (  # noqa: E402
    SPLIT_ALGORITHM_ID,
    SPLIT_ALGORITHM_VERSION,
    SplitDerivationError,
    build_split_derivation,
    normalize_derivation,
)
from tests.test_contracts import valid_layer_manifest  # noqa: E402

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional test extra
    Draft202012Validator = None


def split_config() -> dict:
    return {
        "format": "autospine-bilateral-alpha-split",
        "format_version": 1,
        "algorithm": {
            "id": SPLIT_ALGORITHM_ID,
            "version": SPLIT_ALGORITHM_VERSION,
        },
        "source_layer_id": "layer-001-footwear",
        "source_raster_sha256": "a" * 64,
        "source_rgba_sha256": "b" * 64,
        "output_rgba_sha256": {"left": "c" * 64, "right": "d" * 64},
        "canvas_offset_xy": [10, 20],
        "guide_anchors": {
            "left": [
                resolved_anchor("knee.left", [50.5, 100], "candidate_accepted"),
                resolved_anchor("ankle.left", [51, 140], "manual_adjusted"),
            ],
            "right": [
                resolved_anchor("knee.right", [20.5, 100], "unreviewed"),
                resolved_anchor("ankle.right", [21, 140], "unobservable"),
            ],
        },
        "tie_break": "left",
        "exact_partition": True,
    }


def resolved_anchor(joint_id: str, xy: list, review_state: str) -> dict:
    return {
        "kind": "resolved_joint",
        "joint_id": joint_id,
        "xy": xy,
        "review_state": review_state,
    }


def manual_proxy(
    proxy_id: str, xy: list, *, proxy_for_joint_id: str | None = None
) -> dict:
    value = {
        "kind": "manual_proxy",
        "proxy_id": proxy_id,
        "xy": xy,
        "label": "shoe opening",
        "reason": "ankle is occluded by the costume",
    }
    if proxy_for_joint_id is not None:
        value["proxy_for_joint_id"] = proxy_for_joint_id
    return value


class SplitDerivationContractTests(unittest.TestCase):
    def test_builder_pins_config_hash_without_mutating_input(self) -> None:
        config = split_config()
        original = deepcopy(config)
        first = build_split_derivation(config)
        second = build_split_derivation(config)

        self.assertEqual(original, config)
        self.assertEqual(first, second)
        self.assertEqual(canonical_sha256(config), first["operation_config_sha256"])
        self.assertEqual(first, normalize_derivation("child-left", first))

    def test_source_is_exact_and_missing_value_normalizes(self) -> None:
        expected = {"operation": "source", "parent_layer_ids": []}
        self.assertEqual(expected, normalize_derivation("source", None))
        self.assertEqual(expected, normalize_derivation("source", expected))
        with self.assertRaises(SplitDerivationError):
            normalize_derivation("source", {**expected, "operation_config": {}})

    def test_hash_algorithm_guides_and_tie_rule_fail_closed(self) -> None:
        baseline = build_split_derivation(split_config())
        mutations = (
            lambda item: item.update(operation_config_sha256="0" * 64),
            lambda item: item["operation_config"]["algorithm"].update(version="bad version"),
            lambda item: item["operation_config"].update(tie_break="right"),
            lambda item: item["operation_config"]["guide_anchors"].update(
                left=[item["operation_config"]["guide_anchors"]["left"][0]]
            ),
            lambda item: item["operation_config"]["guide_anchors"]["left"][1].update(
                xy=[50.5, 100]
            ),
            lambda item: item["operation_config"]["guide_anchors"]["left"][0].update(
                joint_id="knee.right"
            ),
            lambda item: item["operation_config"]["guide_anchors"]["left"][0].update(
                unexpected=True
            ),
        )
        for mutate in mutations:
            value = deepcopy(baseline)
            mutate(value)
            if value["operation_config_sha256"] != "0" * 64:
                value["operation_config_sha256"] = canonical_sha256(
                    value["operation_config"]
                )
            with self.subTest(value=value), self.assertRaises(SplitDerivationError):
                normalize_derivation("child-left", value)

    def test_historical_algorithm_is_readable_but_cannot_be_newly_built(self) -> None:
        baseline = build_split_derivation(split_config())
        baseline["operation_config"]["algorithm"]["version"] = "0.9.0"
        baseline["operation_config_sha256"] = canonical_sha256(
            baseline["operation_config"]
        )
        self.assertEqual(baseline, normalize_derivation("child-left", baseline))
        with self.assertRaisesRegex(SplitDerivationError, "current algorithm"):
            build_split_derivation(baseline["operation_config"])

    def test_config_requires_distinct_side_polylines(self) -> None:
        config = split_config()
        left_points = [anchor["xy"] for anchor in config["guide_anchors"]["left"]]
        for anchor, point in zip(
            config["guide_anchors"]["right"], reversed(left_points)
        ):
            anchor["xy"] = point
        with self.assertRaisesRegex(SplitDerivationError, "identical"):
            build_split_derivation(config)

    def test_config_caps_each_guide_at_eight_anchors(self) -> None:
        config = split_config()
        config["guide_anchors"]["left"] = [
            resolved_anchor(
                f"guide-{index}.left",
                [50 + index, 100 + index],
                "manual_adjusted",
            )
            for index in range(9)
        ]

        with self.assertRaisesRegex(SplitDerivationError, "2 to 8"):
            build_split_derivation(config)

    def test_manual_proxy_pins_human_provenance_and_side(self) -> None:
        config = split_config()
        config["guide_anchors"]["left"] = [
            manual_proxy(
                "shoe-opening-upper.left",
                [50.5, 100],
                proxy_for_joint_id="knee.left",
            ),
            manual_proxy(
                "shoe-opening-lower.left",
                [51, 140],
                proxy_for_joint_id="ankle.left",
            ),
        ]
        self.assertEqual(
            config,
            build_split_derivation(config)["operation_config"],
        )
        for mutate in (
            lambda anchor: anchor.update(reason="   "),
            lambda anchor: anchor.update(proxy_id="shoe-opening.right"),
            lambda anchor: anchor.update(proxy_for_joint_id="ankle.right"),
            lambda anchor: anchor.update(proxy_for_joint_id=None),
            lambda anchor: anchor.update(unknown=True),
        ):
            invalid = deepcopy(config)
            mutate(invalid["guide_anchors"]["left"][0])
            with self.subTest(anchor=invalid), self.assertRaises(SplitDerivationError):
                build_split_derivation(invalid)

    def test_duplicate_anchor_ids_and_points_fail_closed(self) -> None:
        for mutate in (
            lambda anchors: anchors[1].update(joint_id=anchors[0]["joint_id"]),
            lambda anchors: anchors.append(
                resolved_anchor("hip.left", anchors[0]["xy"], "unreviewed")
            ),
        ):
            config = split_config()
            mutate(config["guide_anchors"]["left"])
            with self.subTest(config=config), self.assertRaises(SplitDerivationError):
                build_split_derivation(config)

    @unittest.skipIf(Draft202012Validator is None, "install the test extra")
    def test_config_is_accepted_by_layer_manifest_schema(self) -> None:
        schema = json.loads(
            (ROOT / "schemas" / "layer-manifest-v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        validator = Draft202012Validator(schema)
        configs = [split_config()]
        proxy_config = split_config()
        proxy_config["guide_anchors"]["left"] = [
            manual_proxy("shoe-upper.left", [50.5, 100]),
            manual_proxy("shoe-lower.left", [51, 140]),
        ]
        configs.append(proxy_config)
        for config in configs:
            document = valid_layer_manifest()
            document["layers"][0]["derivation"] = build_split_derivation(config)
            with self.subTest(config=config):
                validator.validate(document)

    @unittest.skipIf(Draft202012Validator is None, "install the test extra")
    def test_anchor_schema_one_of_rejects_mixed_or_unknown_shapes(self) -> None:
        schema = json.loads(
            (ROOT / "schemas" / "layer-manifest-v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        validator = Draft202012Validator(schema)
        baseline = valid_layer_manifest()
        derivation = build_split_derivation(split_config())
        mutations = (
            lambda anchor: anchor.update(proxy_id="mixed.left"),
            lambda anchor: anchor.update(unexpected=True),
            lambda anchor: anchor.pop("review_state"),
        )
        for mutate in mutations:
            document = deepcopy(baseline)
            invalid = deepcopy(derivation)
            mutate(invalid["operation_config"]["guide_anchors"]["left"][0])
            document["layers"][0]["derivation"] = invalid
            with self.subTest(document=document):
                self.assertTrue(list(validator.iter_errors(document)))


if __name__ == "__main__":
    unittest.main()
