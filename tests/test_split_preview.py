"""Contract, builder, and strict-reader tests for split previews."""

from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.artifact_store import ImmutableJsonArtifactStore  # noqa: E402
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from autospine_workbench.split_derivation_contract import (  # noqa: E402
    SPLIT_ALGORITHM_ID,
    SPLIT_ALGORITHM_VERSION,
    SPLIT_TIE_BREAK,
    build_split_derivation,
)
from autospine_workbench.split_preview import (  # noqa: E402
    SplitPreviewError,
    build_split_preview,
)
from autospine_workbench.split_preview_contract import (  # noqa: E402
    SplitPreviewContractError,
    require_valid_split_preview,
)
from autospine_workbench.split_preview_reader import (  # noqa: E402
    SplitPreviewReader,
    SplitPreviewReaderError,
)


PROJECT_ID = "split-fixture"
PARENT_ID = "layer-legs"
SHA = {key: key * 64 for key in "abcdef"}


def split_spec() -> dict:
    return {
        "parts": {
            side: {
                "guide": [
                    {"kind": "joint", "joint_id": f"{name}.{side}"}
                    for name in ("hip", "knee", "ankle")
                ],
                "pivot": {"kind": "joint", "joint_id": f"hip.{side}"},
                "candidate_bone": f"thigh.{side}",
            }
            for side in ("left", "right")
        }
    }


def fixture() -> tuple[dict, list[dict], dict, str]:
    coordinates = {
        "left": ((20.0, 20.0), (22.0, 50.0), (24.0, 80.0)),
        "right": ((80.0, 20.0), (78.0, 50.0), (76.0, 80.0)),
    }
    joints = [
        {
            "id": f"{name}.{side}",
            "x": xy[0],
            "y": xy[1],
            "review_state": "candidate_accepted",
        }
        for side in ("left", "right")
        for name, xy in zip(("hip", "knee", "ankle"), coordinates[side])
    ]
    parent = {
        "id": PARENT_ID,
        "canonical_role": "body.leg",
        "side": "bilateral",
        "disposition": "split_left_right",
        "split_spec": split_spec(),
        "z_index": 0,
    }
    resolved = {
        "schema_version": "autospine.resolved-project/v1",
        "project_id": PROJECT_ID,
        "revision": 7,
        "inputs": {"base_project_sha256": SHA["e"], "override_sha256": SHA["f"]},
        "canvas": {"width": 100, "height": 100},
        "layers": [deepcopy(parent)],
        "skeleton": {
            "joints": joints,
            "bones": [{"id": "thigh.left"}, {"id": "thigh.right"}],
        },
        "qa": {"status": "needs_review"},
    }
    resolved["sha256"] = canonical_sha256(resolved)
    project = {"id": PROJECT_ID, "resolved": resolved}
    guide_anchors = {
        side: [
            {
                "kind": "resolved_joint",
                "joint_id": f"{name}.{side}",
                "xy": list(xy),
                "review_state": "candidate_accepted",
            }
            for name, xy in zip(("hip", "knee", "ankle"), coordinates[side])
        ]
        for side in ("left", "right")
    }
    config = {
        "format": "autospine-bilateral-alpha-split",
        "format_version": 1,
        "algorithm": {"id": SPLIT_ALGORITHM_ID, "version": SPLIT_ALGORITHM_VERSION},
        "source_layer_id": PARENT_ID,
        "source_raster_sha256": SHA["a"],
        "source_rgba_sha256": SHA["b"],
        "output_rgba_sha256": {"left": SHA["c"], "right": SHA["d"]},
        "canvas_offset_xy": [0, 0],
        "guide_anchors": guide_anchors,
        "tie_break": SPLIT_TIE_BREAK,
        "exact_partition": True,
    }
    derivation = build_split_derivation(config)
    overlay_parent = {**deepcopy(parent), "disposition": "exclude"}
    overlay = [overlay_parent]
    manifest_layers = [
        {
            "layer_id": PARENT_ID,
            "raster": {"sha256": SHA["a"]},
            "semantic": {"canonical_role": "body.leg", "side": "bilateral"},
            "derivation": {"operation": "source", "parent_layer_ids": []},
            "rig_hint": {"attachment_kind": "excluded"},
        }
    ]
    for order, side in enumerate(("left", "right"), start=1):
        child_id = f"{PARENT_ID}--{side}"
        pivot = list(coordinates[side][0])
        overlay.append(
            {
                "id": child_id,
                "canonical_role": "body.leg",
                "side": side,
                "disposition": "keep",
                "pivot_xy": pivot,
                "proposed_candidate_bone": f"thigh.{side}",
                "review_state": "unreviewed",
                "reviewed_fields": [],
                "z_index": order,
                "derivation": deepcopy(derivation),
            }
        )
        manifest_layers.append(
            {
                "layer_id": child_id,
                "raster": {"sha256": SHA["e"] if side == "left" else SHA["f"]},
                "semantic": {
                    "canonical_role": "body.leg",
                    "side": side,
                    "mapping_method": "alias",
                },
                "derivation": deepcopy(derivation),
                "rig_hint": {
                    "attachment_kind": "region",
                    "pivot": {"xy": pivot, "method": "unknown"},
                    "candidate_bone": f"thigh.{side}",
                    "setup_draw_order": order,
                },
                "qa": {
                    "status": "manual_required",
                    "flags": [
                        "BONE_BINDING_REVIEW_REQUIRED",
                        "PIVOT_REVIEW_REQUIRED",
                        "SEMANTIC_REVIEW_REQUIRED",
                    ],
                },
            }
        )
    manifest = {
        "format": "autospine-layer-manifest",
        "format_version": 1,
        "project_id": PROJECT_ID,
        "revision": 7,
        "layers": manifest_layers,
    }
    return project, overlay, manifest, canonical_sha256(manifest)


def preview() -> dict:
    project, overlay, manifest, digest = fixture()
    return build_split_preview(
        project,
        overlay,
        manifest,
        layer_manifest_sha256=digest,
        parent_layer_id=PARENT_ID,
    )


class SplitPreviewBuilderTests(unittest.TestCase):
    def test_builds_deterministic_full_review_target_without_mutation(self) -> None:
        project, overlay, manifest, digest = fixture()
        before = deepcopy((project, overlay, manifest))
        first = build_split_preview(
            project,
            overlay,
            manifest,
            layer_manifest_sha256=digest,
            parent_layer_id=PARENT_ID,
        )
        second = build_split_preview(
            project,
            overlay,
            manifest,
            layer_manifest_sha256=digest,
            parent_layer_id=PARENT_ID,
        )

        self.assertEqual(before, (project, overlay, manifest))
        self.assertEqual(first, second)
        self.assertEqual("autospine-split-preview/v1", first["format"])
        self.assertEqual(project["resolved"]["sha256"], first["resolved_snapshot_sha256"])
        self.assertEqual(digest, first["layer_manifest_sha256"])
        self.assertEqual(split_spec(), first["split_spec"])
        target = first["review_target"]
        self.assertEqual(
            {
                "layer_id": PARENT_ID,
                "canonical_role": "body.leg",
                "raster_sha256": SHA["a"],
                "rgba_sha256": SHA["b"],
            },
            target["source"],
        )
        self.assertEqual(first["operation_config_sha256"], target["operation"]["config_sha256"])
        self.assertEqual([20.0, 20.0], target["parts"]["left"]["pivot_xy"])
        self.assertEqual("thigh.right", target["parts"]["right"]["candidate_bone"])
        self.assertEqual(2, target["parts"]["right"]["setup_draw_order"])
        self.assertEqual(canonical_sha256(target), first["review_target_sha256"])
        require_valid_split_preview(first)

    def test_builder_fails_on_stale_snapshot_manifest_guide_pivot_bone_and_order(self) -> None:
        cases = []
        project, overlay, manifest, digest = fixture()
        project["resolved"]["revision"] += 1
        cases.append((project, overlay, manifest, digest, "snapshot"))
        project, overlay, manifest, digest = fixture()
        cases.append((project, overlay, manifest, "f" * 64, "digest"))
        project, overlay, manifest, digest = fixture()
        overlay[1]["derivation"]["operation_config"]["guide_anchors"]["left"][0]["xy"] = [21.0, 20.0]
        cases.append((project, overlay, manifest, digest, "derivation"))
        project, overlay, manifest, digest = fixture()
        manifest["layers"][1]["rig_hint"]["pivot"]["xy"] = [21.0, 20.0]
        cases.append((project, overlay, manifest, canonical_sha256(manifest), "pivot"))
        project, overlay, manifest, digest = fixture()
        manifest["layers"][1]["rig_hint"]["candidate_bone"] = "calf.left"
        cases.append((project, overlay, manifest, canonical_sha256(manifest), "bone"))
        project, overlay, manifest, digest = fixture()
        manifest["layers"][1]["rig_hint"]["setup_draw_order"] = 9
        cases.append((project, overlay, manifest, canonical_sha256(manifest), "order"))

        for project, overlay, manifest, digest, label in cases:
            with self.subTest(label=label), self.assertRaises(SplitPreviewError):
                build_split_preview(
                    project,
                    overlay,
                    manifest,
                    layer_manifest_sha256=digest,
                    parent_layer_id=PARENT_ID,
                )

    def test_same_joint_coordinates_with_different_review_state_are_stale(self) -> None:
        project, overlay, manifest, _digest = fixture()
        config = deepcopy(overlay[1]["derivation"]["operation_config"])
        config["guide_anchors"]["left"][0]["review_state"] = "manual_adjusted"
        changed_derivation = build_split_derivation(config)
        for child in overlay[1:]:
            child["derivation"] = deepcopy(changed_derivation)
        for child in manifest["layers"][1:]:
            child["derivation"] = deepcopy(changed_derivation)

        with self.assertRaisesRegex(SplitPreviewError, "resolved split_spec"):
            build_split_preview(
                project,
                overlay,
                manifest,
                layer_manifest_sha256=canonical_sha256(manifest),
                parent_layer_id=PARENT_ID,
            )

    def test_unaccepted_pivot_joint_fails_even_when_its_coordinates_match(self) -> None:
        project, overlay, manifest, _digest = fixture()
        project["resolved"]["skeleton"]["joints"].append(
            {
                "id": "pivot.left",
                "x": 30.0,
                "y": 30.0,
                "review_state": "unobservable",
            }
        )
        authored_pivot = {"kind": "joint", "joint_id": "pivot.left"}
        project["resolved"]["layers"][0]["split_spec"]["parts"]["left"][
            "pivot"
        ] = authored_pivot
        overlay[0]["split_spec"]["parts"]["left"]["pivot"] = deepcopy(
            authored_pivot
        )
        overlay[1]["pivot_xy"] = [30.0, 30.0]
        manifest["layers"][1]["rig_hint"]["pivot"]["xy"] = [30.0, 30.0]
        resolved = project["resolved"]
        resolved["sha256"] = canonical_sha256(
            {key: value for key, value in resolved.items() if key != "sha256"}
        )

        with self.assertRaisesRegex(SplitPreviewError, "manual_proxy"):
            build_split_preview(
                project,
                overlay,
                manifest,
                layer_manifest_sha256=canonical_sha256(manifest),
                parent_layer_id=PARENT_ID,
            )


class SplitPreviewContractTests(unittest.TestCase):
    def test_review_hash_binds_every_required_review_dimension(self) -> None:
        original = preview()
        mutations = {
            "source role": lambda value: value["review_target"]["source"].__setitem__("canonical_role", "body.leg.lower"),
            "source raster": lambda value: value["review_target"]["source"].__setitem__("raster_sha256", SHA["f"]),
            "source rgba": lambda value: value["review_target"]["source"].__setitem__("rgba_sha256", SHA["f"]),
            "algorithm version": lambda value: value["review_target"]["operation"]["algorithm"].__setitem__("version", "9.0.0"),
            "algorithm config": lambda value: value["review_target"]["operation"].__setitem__("config_sha256", SHA["f"]),
            "output rgba": lambda value: value["review_target"]["operation"]["output_rgba_sha256"].__setitem__("left", SHA["f"]),
            "pivot": lambda value: value["review_target"]["parts"]["left"].__setitem__("pivot_xy", [21.0, 20.0]),
            "bone": lambda value: value["review_target"]["parts"]["left"].__setitem__("candidate_bone", "calf.left"),
            "draw order": lambda value: value["review_target"]["parts"]["left"].__setitem__("setup_draw_order", 9),
            "child raster": lambda value: value["review_target"]["parts"]["left"].__setitem__("raster_sha256", SHA["f"]),
        }
        for label, mutate in mutations.items():
            changed = deepcopy(original)
            mutate(changed)
            with self.subTest(label=label), self.assertRaises(SplitPreviewContractError):
                require_valid_split_preview(changed)

    def test_unknown_fields_and_unstable_child_cross_references_fail_closed(self) -> None:
        unknown = preview()
        unknown["review_target"]["source"]["extra"] = True
        unknown["review_target_sha256"] = canonical_sha256(unknown["review_target"])
        with self.assertRaisesRegex(SplitPreviewContractError, "unsupported"):
            require_valid_split_preview(unknown)

        wrong_child = preview()
        wrong_child["review_target"]["parts"]["left"]["layer_id"] = "other--left"
        wrong_child["review_target_sha256"] = canonical_sha256(wrong_child["review_target"])
        with self.assertRaisesRegex(SplitPreviewContractError, "identity"):
            require_valid_split_preview(wrong_child)

        duplicate_order = preview()
        duplicate_order["review_target"]["parts"]["right"]["setup_draw_order"] = 1
        duplicate_order["review_target_sha256"] = canonical_sha256(duplicate_order["review_target"])
        with self.assertRaisesRegex(SplitPreviewContractError, "distinct"):
            require_valid_split_preview(duplicate_order)

    def test_full_split_spec_is_content_addressed(self) -> None:
        original = preview()
        changed = deepcopy(original)
        changed["split_spec"]["parts"]["left"]["pivot"] = {
            "kind": "joint",
            "joint_id": "knee.left",
        }
        require_valid_split_preview(changed)
        self.assertNotEqual(canonical_sha256(original), canonical_sha256(changed))

    def test_historical_algorithm_identity_remains_readable(self) -> None:
        changed = preview()
        changed["review_target"]["operation"]["algorithm"]["version"] = "0.9.0"
        changed["review_target_sha256"] = canonical_sha256(changed["review_target"])
        require_valid_split_preview(changed)


class SplitPreviewReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.state = Path(self.temp.name)
        self.document = preview()
        self.published = ImmutableJsonArtifactStore(self.state).publish(
            "split-previews", PROJECT_ID, self.document
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_reads_published_artifact_and_returns_exact_content_address(self) -> None:
        loaded = SplitPreviewReader(self.state).load(PROJECT_ID, self.published.sha256)
        self.assertEqual(self.document, loaded.document)
        self.assertEqual(self.published.sha256, loaded.sha256)
        self.assertEqual(self.published.path.resolve(), loaded.path)

    def test_duplicate_key_tamper_and_wrong_project_fail_closed(self) -> None:
        encoded = json.dumps(self.document, ensure_ascii=False, sort_keys=True)
        duplicate = encoded.replace(
            '"format": "autospine-split-preview/v1"',
            '"format": "autospine-split-preview/v1", "format": "autospine-split-preview/v1"',
            1,
        )
        self.published.path.write_text(duplicate, encoding="utf-8")
        with self.assertRaisesRegex(SplitPreviewReaderError, "repeats"):
            SplitPreviewReader(self.state).load(PROJECT_ID, self.published.sha256)

        self.published.path.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(SplitPreviewReaderError, "content address"):
            SplitPreviewReader(self.state).load(PROJECT_ID, self.published.sha256)

        other = self.state / "analysis" / "other-project" / "split-previews"
        other.mkdir(parents=True)
        target = other / f"{canonical_sha256(self.document)}.json"
        target.write_text(json.dumps(self.document), encoding="utf-8")
        with self.assertRaisesRegex(SplitPreviewReaderError, "another project"):
            SplitPreviewReader(self.state).load("other-project", target.stem)

    def test_size_identity_and_symlink_boundaries_fail_closed(self) -> None:
        self.published.path.write_bytes(b" " * (2 * 1024 * 1024 + 1))
        with self.assertRaisesRegex(SplitPreviewReaderError, "2 MiB"):
            SplitPreviewReader(self.state).load(PROJECT_ID, self.published.sha256)
        for project_id, digest in (("../escape", self.published.sha256), (PROJECT_ID, "F" * 64)):
            with self.subTest(project_id=project_id, digest=digest), self.assertRaisesRegex(
                SplitPreviewReaderError, "identity"
            ):
                SplitPreviewReader(self.state).load(project_id, digest)

        link_project = self.state / "analysis" / "linked-project"
        try:
            os.symlink(
                self.state / "analysis" / PROJECT_ID,
                link_project,
                target_is_directory=True,
            )
        except (OSError, NotImplementedError):
            return
        try:
            with self.assertRaisesRegex(SplitPreviewReaderError, "unsafe"):
                SplitPreviewReader(self.state).load(
                    "linked-project", self.published.sha256
                )
        finally:
            link_project.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
