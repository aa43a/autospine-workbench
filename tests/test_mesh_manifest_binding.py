"""Exact reviewed Layer Manifest to verified P2 base binding tests."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.mesh_manifest_binding import (  # noqa: E402
    MeshManifestBindingError,
    require_manifest_matches_base,
)
from autospine_workbench.region_rig import compile_region_rig  # noqa: E402
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from tests.test_region_rig import (  # noqa: E402
    layer_fixture,
    manifest_fixture,
    resolved_fixture,
)


REGION_ID = "layer-001-torso"
EXCLUDED_ID = "layer-002-empty"


def binding_fixture() -> tuple[dict, dict, dict, dict[str, tuple[int, int]]]:
    manifest = manifest_fixture()
    excluded = layer_fixture(EXCLUDED_ID, 8)
    excluded["source"].update(name="empty", index=2, visible=False)
    excluded["raster"].update(
        artifact_path=f"layers/{EXCLUDED_ID}.png",
        sha256="3" * 64,
        alpha_nonzero=0,
    )
    excluded["semantic"].update(
        source_tag="empty",
        canonical_role="unknown.empty",
        mapping_method="exact",
    )
    excluded["rig_hint"].update(
        attachment_kind="excluded",
        candidate_bone=None,
        pivot=None,
    )
    manifest["layers"].append(excluded)
    sizes = {REGION_ID: (30, 40), EXCLUDED_ID: (30, 40)}
    compiled = compile_region_rig(
        manifest,
        resolved_fixture(),
        layer_manifest_sha256=canonical_sha256(manifest),
        image_sizes=sizes,
    )
    return manifest, compiled.rig, compiled.run_manifest, sizes


def rebind(manifest: dict, rig: dict, run: dict) -> None:
    digest = canonical_sha256(manifest)
    run["inputs"]["layer_manifest_sha256"] = digest
    rig["source"]["layer_manifest_sha256"] = digest
    rig["source"]["run_manifest_sha256"] = canonical_sha256(run)


def assert_rejected(
    testcase: unittest.TestCase,
    manifest: dict,
    rig: dict,
    run: dict,
    sizes: dict,
    message: str | None = None,
) -> None:
    context = (
        testcase.assertRaisesRegex(MeshManifestBindingError, message)
        if message
        else testcase.assertRaises(MeshManifestBindingError)
    )
    with context:
        require_manifest_matches_base(manifest, rig, run, sizes)


class MeshManifestBindingTests(unittest.TestCase):
    def test_exact_binding_is_deterministic_and_does_not_mutate_inputs(self) -> None:
        manifest, rig, run, sizes = binding_fixture()
        originals = tuple(deepcopy(item) for item in (manifest, rig, run, sizes))

        self.assertIsNone(require_manifest_matches_base(manifest, rig, run, sizes))
        self.assertIsNone(require_manifest_matches_base(manifest, rig, run, sizes))
        self.assertEqual(originals, (manifest, rig, run, sizes))

        reversed_manifest = deepcopy(manifest)
        reversed_manifest["layers"].reverse()
        rebind(reversed_manifest, rig, run)
        self.assertIsNone(
            require_manifest_matches_base(reversed_manifest, rig, run, sizes)
        )

    def test_content_addresses_and_project_must_match_both_base_documents(self) -> None:
        manifest, rig, run, sizes = binding_fixture()
        changed = deepcopy(manifest)
        changed["revision"] += 1
        assert_rejected(self, changed, rig, run, sizes, "content address")

        changed, changed_rig, changed_run, changed_sizes = binding_fixture()
        changed["project_id"] = "sample-b"
        rebind(changed, changed_rig, changed_run)
        assert_rejected(
            self, changed, changed_rig, changed_run, changed_sizes, "project differs"
        )

        for target in ("rig", "run"):
            manifest, rig, run, sizes = binding_fixture()
            if target == "rig":
                rig["source"]["layer_manifest_sha256"] = "9" * 64
            else:
                run["inputs"]["layer_manifest_sha256"] = "9" * 64
                rig["source"]["run_manifest_sha256"] = canonical_sha256(run)
            with self.subTest(target=target):
                assert_rejected(self, manifest, rig, run, sizes)

    def test_revision_is_not_compared_to_latest_or_an_external_snapshot(self) -> None:
        manifest, rig, run, sizes = binding_fixture()
        manifest["revision"] = 999_999
        rebind(manifest, rig, run)

        self.assertIsNone(require_manifest_matches_base(manifest, rig, run, sizes))

    def test_manifest_and_each_layer_qa_must_be_passed(self) -> None:
        for target in ("manifest", "region", "excluded"):
            manifest, rig, run, sizes = binding_fixture()
            if target == "manifest":
                manifest["qa"]["status"] = "manual_required"
            else:
                index = 0 if target == "region" else 1
                manifest["layers"][index]["qa"]["status"] = "manual_required"
            rebind(manifest, rig, run)
            with self.subTest(target=target):
                assert_rejected(self, manifest, rig, run, sizes, "QA must be passed")

    def test_canvas_and_coordinate_contract_must_equal_base_exactly(self) -> None:
        mutations = (
            lambda manifest: manifest["source"].update(canvas=[101, 200]),
            lambda manifest: manifest["source"]["coordinate_system"].update(
                x_axis="left"
            ),
        )
        for mutate in mutations:
            manifest, rig, run, sizes = binding_fixture()
            mutate(manifest)
            rebind(manifest, rig, run)
            with self.subTest(mutation=mutate):
                assert_rejected(self, manifest, rig, run, sizes, "canvas|coordinate")

        manifest, rig, run, sizes = binding_fixture()
        rig["canvas"] = {**rig["canvas"], "width": 101}
        assert_rejected(self, manifest, rig, run, sizes)

    def test_all_materialized_layer_image_sizes_are_exact(self) -> None:
        cases = (
            {REGION_ID: (30, 40)},
            {REGION_ID: (30, 40), EXCLUDED_ID: (30, 40), "extra": (1, 1)},
            {REGION_ID: (31, 40), EXCLUDED_ID: (30, 40)},
            {REGION_ID: (30, 40), EXCLUDED_ID: (0, 40)},
        )
        for sizes in cases:
            manifest, rig, run, _ = binding_fixture()
            with self.subTest(sizes=sizes):
                assert_rejected(self, manifest, rig, run, sizes)

    def test_layer_identity_path_hash_canvas_and_raster_profile_are_exact(self) -> None:
        def change_id(manifest: dict) -> None:
            layer = manifest["layers"][0]
            layer["layer_id"] = "layer-009-torso"
            layer["raster"]["artifact_path"] = "layers/layer-009-torso.png"

        cases = (
            (change_id, {"layer-009-torso": (30, 40), EXCLUDED_ID: (30, 40)}),
            (lambda m: m["layers"][0]["raster"].update(
                artifact_path="layers/not-canonical.png"
            ), None),
            (lambda m: m["layers"][0]["raster"].update(sha256="4" * 64), None),
            (lambda m: m["layers"][0]["raster"].update(canvas_size=[101, 200]), None),
            (lambda m: m["layers"][0]["raster"].update(channels="RGB"), None),
        )
        for mutate, replacement_sizes in cases:
            manifest, rig, run, sizes = binding_fixture()
            mutate(manifest)
            if replacement_sizes is not None:
                sizes = replacement_sizes
            rebind(manifest, rig, run)
            with self.subTest(mutation=mutate):
                assert_rejected(self, manifest, rig, run, sizes)

    def test_every_region_geometry_and_slot_field_is_cross_bound(self) -> None:
        def offset(layer: dict) -> None:
            layer["raster"].update(
                crop_bbox_xywh=[11, 20, 30, 40], canvas_offset_xy=[11, 20]
            )

        cases = (
            offset,
            lambda layer: layer["rig_hint"]["pivot"].update(xy=[21, 25]),
            lambda layer: layer["rig_hint"]["pivot"].update(xy=[True, 25]),
            lambda layer: layer["rig_hint"].update(candidate_bone="root-pelvis"),
            lambda layer: layer["rig_hint"].update(setup_draw_order=9),
            lambda layer: layer["rig_hint"].update(setup_draw_order=True),
            lambda layer: layer["source"].update(visible=False),
            lambda layer: layer["source"].update(blend_mode="multiply"),
            lambda layer: layer["source"].update(opacity=0.25),
        )
        for mutate in cases:
            manifest, rig, run, sizes = binding_fixture()
            mutate(manifest["layers"][0])
            rebind(manifest, rig, run)
            with self.subTest(mutation=mutate):
                assert_rejected(self, manifest, rig, run, sizes)

    def test_attachments_slots_source_sets_and_default_skin_are_exact(self) -> None:
        mutations = (
            lambda rig: rig["attachments"][0].update(id="attachment-alias"),
            lambda rig: rig["attachments"][0].update(
                source_layer_ids=[EXCLUDED_ID]
            ),
            lambda rig: rig["attachments"][0].update(size=[31, 40]),
            lambda rig: rig["attachments"][0].update(unexpected=True),
            lambda rig: rig["slots"][0].update(id="slot-alias"),
            lambda rig: rig["slots"][0].update(unexpected=True),
            lambda rig: rig["skins"]["default"].update({REGION_ID: []}),
            lambda rig: rig["skins"].update(extra={REGION_ID: [REGION_ID]}),
        )
        for mutate in mutations:
            manifest, rig, run, sizes = binding_fixture()
            mutate(rig)
            with self.subTest(mutation=mutate):
                assert_rejected(self, manifest, rig, run, sizes)

        manifest, rig, run, sizes = binding_fixture()
        manifest["layers"][1]["rig_hint"]["attachment_kind"] = "region"
        manifest["layers"][1]["rig_hint"].update(
            candidate_bone="pelvis-chest",
            pivot={"xy": [20, 25], "method": "manual", "confidence": 1.0},
        )
        rebind(manifest, rig, run)
        assert_rejected(self, manifest, rig, run, sizes, "exactly match")

        manifest, rig, run, sizes = binding_fixture()
        excluded_attachment = deepcopy(rig["attachments"][0])
        excluded_attachment.update(
            id=EXCLUDED_ID,
            slot=EXCLUDED_ID,
            image_path=f"layers/{EXCLUDED_ID}.png",
            image_sha256="3" * 64,
            source_layer_ids=[EXCLUDED_ID],
        )
        excluded_slot = deepcopy(rig["slots"][0])
        excluded_slot.update(id=EXCLUDED_ID, setup_attachment=None, setup_draw_order=8)
        rig["attachments"].append(excluded_attachment)
        rig["slots"].append(excluded_slot)
        rig["skins"]["default"][EXCLUDED_ID] = [EXCLUDED_ID]
        assert_rejected(self, manifest, rig, run, sizes, "Excluded layer")

    def test_unsupported_or_malformed_shapes_fail_closed(self) -> None:
        mutations = (
            lambda m: m.update(format_version=True),
            lambda m: m.update(layers={}),
            lambda m: m["layers"][1]["rig_hint"].update(
                attachment_kind="unknown"
            ),
            lambda m: m["layers"].append(deepcopy(m["layers"][0])),
        )
        for mutate in mutations:
            manifest, rig, run, sizes = binding_fixture()
            mutate(manifest)
            rebind(manifest, rig, run)
            with self.subTest(mutation=mutate):
                assert_rejected(self, manifest, rig, run, sizes)


if __name__ == "__main__":
    unittest.main()
