"""P3 reproducible mesh visual artifact contract tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
import hashlib
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.mesh_probe_report import (  # noqa: E402
    build_mesh_probe_report,
)
from autospine_workbench.mesh_visual_artifacts import (  # noqa: E402
    MeshVisualArtifactsError,
    build_mesh_visual_artifacts,
    renderer_identities,
    require_mesh_visual_artifacts,
)
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from tests.test_mesh_action_probe import early_failure_attachment  # noqa: E402
from tests.test_mesh_probe_report import (  # noqa: E402
    noop_inputs,
    reverse_keys,
    synthetic_inputs,
)
from tests.test_mesh_rig import compile_a, images_a  # noqa: E402

try:
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import ValidationError
except ImportError:  # pragma: no cover - optional test extra
    Draft202012Validator = None
    ValidationError = Exception


def renderable_a():
    """Move compile_a away from canvas edges without changing its mesh shape."""

    compiled = compile_a()
    rig = deepcopy(compiled.rig)
    rig["canvas"].update(width=360, height=300)
    for bone in rig["bones"]:
        # Translate the rig in world space.  Limbs may have rotated connector
        # parents, so changing their local setup coordinates is not equivalent
        # to the matching canvas-space attachment translation below.
        if bone["parent"] is None:
            bone["setup"]["x"] += 100
            bone["setup"]["y"] += 100
    for attachment in rig["attachments"]:
        if attachment["type"] == "mesh":
            x, y = attachment["canvas_offset_xy"]
            attachment["canvas_offset_xy"] = [x + 100, y + 100]
    probes = build_mesh_probe_report(
        rig, compiled.run_manifest, compiled.targets
    ).document
    return rig, compiled.run_manifest, probes, compiled.targets, images_a()


def build_a():
    inputs = renderable_a()
    return inputs, build_mesh_visual_artifacts(*inputs)


class MeshVisualArtifactSchemaTests(unittest.TestCase):
    def schema(self):
        return json.loads(
            (ROOT / "schemas" / "mesh-visual-artifacts-v1.schema.json").read_text(
                encoding="utf-8"
            )
        )

    def test_schema_is_draft_2020_12_and_accepts_a_like_and_noop(self) -> None:
        schema = self.schema()
        self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
        self.assertTrue(schema["$id"].endswith("mesh-visual-artifacts-v1.schema.json"))
        if Draft202012Validator is None:
            return
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        validator.validate(build_a()[1].document)
        rig, run, targets = noop_inputs()
        probes = build_mesh_probe_report(rig, run, targets).document
        validator.validate(
            build_mesh_visual_artifacts(rig, run, probes, targets, {}).document
        )

    @unittest.skipIf(Draft202012Validator is None, "install the test extra")
    def test_schema_rejects_unknown_renderer_and_nonportable_path(self) -> None:
        validator = Draft202012Validator(self.schema())
        mutations = (
            lambda value: value.update(extra=True),
            lambda value: value["renderers"]["pose"].update(sampling="linear"),
            lambda value: value["artifacts"][1].update(
                path="poses/leg-left.widest-safe-+70.png"
            ),
        )
        for mutate in mutations:
            document = build_a()[1].document
            mutate(document)
            with self.subTest(document=document), self.assertRaises(ValidationError):
                validator.validate(document)


class MeshVisualArtifactBuildTests(unittest.TestCase):
    def test_a_like_build_is_bound_sorted_and_contains_three_images_per_target(self) -> None:
        (rig, run, probes, targets, images), result = build_a()
        document = result.document
        expected_paths = [
            "poses/leg-left.setup.png",
            "poses/leg-left.widest-safe-p070.png",
            "poses/leg-right.setup.png",
            "poses/leg-right.widest-safe-p070.png",
            "weights/leg-left.png",
            "weights/leg-right.png",
        ]

        self.assertEqual("autospine-mesh-visual-artifacts", document["format"])
        self.assertEqual(1, document["format_version"])
        self.assertEqual("mesh-a", document["project_id"])
        self.assertEqual("passed", document["status"])
        self.assertEqual("converted=2", document["summary"])
        self.assertEqual(renderer_identities(), document["renderers"])
        self.assertEqual(expected_paths, [item["path"] for item in document["artifacts"]])
        self.assertEqual(expected_paths, list(result.png_by_path))
        self.assertEqual(
            ["leg-left", "leg-right"], [item["id"] for item in document["images"]]
        )
        self.assertEqual(
            ["leg-left", "leg-right"],
            [item["attachment_id"] for item in document["targets"]],
        )
        self.assertEqual({
            "rig_sha256": canonical_sha256(rig),
            "run_manifest_sha256": canonical_sha256(run),
            "probes_sha256": canonical_sha256(probes),
        }, document["source"])
        for artifact in document["artifacts"]:
            png = result.png_by_path[artifact["path"]]
            self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertEqual(hashlib.sha256(png).hexdigest(), artifact["png_sha256"])
            if artifact["pose"] == "weights":
                self.assertEqual((32, 80), (artifact["width"], artifact["height"]))
                self.assertIsNone(artifact["angle_deg"])
            else:
                self.assertEqual((360, 300), (artifact["width"], artifact["height"]))
        widest = [item for item in document["artifacts"] if item["pose"] == "widest-safe"]
        self.assertTrue(all(item["angle_deg"] == 70 for item in widest))
        self.assertTrue(all(item["bone"].startswith("calf.") for item in widest))
        require_mesh_visual_artifacts(
            document, result.png_by_path, rig=rig, run=run, probes=probes,
            targets=targets, target_images=images,
        )

    def test_noop_has_no_inputs_targets_artifacts_or_pngs(self) -> None:
        rig, run, targets = noop_inputs()
        probes = build_mesh_probe_report(rig, run, targets).document
        result = build_mesh_visual_artifacts(rig, run, probes, targets, {})
        self.assertEqual("reviewed-noop", result.document["summary"])
        self.assertEqual([], result.document["images"])
        self.assertEqual([], result.document["targets"])
        self.assertEqual([], result.document["artifacts"])
        self.assertEqual({}, dict(result.png_by_path))
        require_mesh_visual_artifacts(
            result.document, result.png_by_path, rig=rig, run=run,
            probes=probes, targets=targets, target_images={},
        )

    def test_order_is_deterministic_and_all_inputs_remain_unchanged(self) -> None:
        rig, run, probes, targets, images = renderable_a()
        before = deepcopy((rig, run, probes, targets, images))
        first = build_mesh_visual_artifacts(rig, run, probes, targets, images)
        self.assertEqual(before, (rig, run, probes, targets, images))

        changed = (
            reverse_keys(rig), reverse_keys(run), reverse_keys(probes),
            tuple(reversed(targets)), dict(reversed(list(images.items()))),
        )
        changed_before = deepcopy(changed)
        second = build_mesh_visual_artifacts(*changed)
        self.assertEqual(first, second)
        self.assertEqual(changed_before, changed)

    def test_result_accessors_are_frozen_and_isolated(self) -> None:
        _inputs, result = build_a()
        changed = result.document
        changed["source"].clear()
        self.assertTrue(result.document["source"])
        with self.assertRaises(TypeError):
            result.png_by_path["new.png"] = b"x"  # type: ignore[index]
        with self.assertRaises(FrozenInstanceError):
            result._json = "{}"  # type: ignore[misc]


class MeshVisualArtifactTamperTests(unittest.TestCase):
    def test_rejected_probe_report_cannot_produce_visual_pass(self) -> None:
        rig, run, targets = synthetic_inputs(early_failure_attachment())
        probes = build_mesh_probe_report(rig, run, targets).document
        self.assertEqual("rejected", probes["status"])
        with self.assertRaisesRegex(MeshVisualArtifactsError, "rejected mesh probes"):
            build_mesh_visual_artifacts(rig, run, probes, targets, {})

    def test_target_image_keys_are_exact(self) -> None:
        rig, run, probes, targets, images = renderable_a()
        missing = dict(images)
        missing.pop("leg-left")
        extra = dict(images, unexpected=next(iter(images.values())))
        for changed in (missing, extra):
            with self.subTest(keys=set(changed)), self.assertRaisesRegex(
                MeshVisualArtifactsError, "image keys"
            ):
                build_mesh_visual_artifacts(rig, run, probes, targets, changed)

    def test_probe_source_and_metrics_tampering_are_recomputed(self) -> None:
        rig, run, probes, targets, images = renderable_a()
        changed_source = deepcopy(probes)
        changed_source["source"]["rig_sha256"] = "0" * 64
        changed_metrics = deepcopy(probes)
        changed_metrics["attachments"][0]["action_probe"]["setup"]["metrics"][
            "maximum_edge_stretch"
        ] = 1.25
        for changed in (changed_source, changed_metrics):
            with self.subTest(source=changed["source"]), self.assertRaises(
                MeshVisualArtifactsError
            ):
                build_mesh_visual_artifacts(rig, run, changed, targets, images)

    def test_document_source_path_and_png_bytes_tampering_fail(self) -> None:
        (rig, run, probes, targets, images), result = build_a()
        kwargs = dict(
            rig=rig, run=run, probes=probes, targets=targets, target_images=images
        )
        changed_source = result.document
        changed_source["source"]["probes_sha256"] = "0" * 64
        with self.assertRaisesRegex(MeshVisualArtifactsError, "recomputed evidence"):
            require_mesh_visual_artifacts(changed_source, result.png_by_path, **kwargs)

        changed_path = result.document
        changed_path["artifacts"][0]["path"] = "../escape.png"
        with self.assertRaises(MeshVisualArtifactsError):
            require_mesh_visual_artifacts(changed_path, result.png_by_path, **kwargs)

        changed_png = dict(result.png_by_path)
        first = next(iter(changed_png))
        changed_png[first] += b"tamper"
        with self.assertRaisesRegex(MeshVisualArtifactsError, "PNG bytes"):
            require_mesh_visual_artifacts(result.document, changed_png, **kwargs)

    def test_png_paths_must_be_safe_and_case_unique(self) -> None:
        (rig, run, probes, targets, images), result = build_a()
        kwargs = dict(
            rig=rig, run=run, probes=probes, targets=targets, target_images=images
        )
        unsafe = dict(result.png_by_path)
        unsafe["../escape.png"] = b"x"
        with self.assertRaisesRegex(MeshVisualArtifactsError, "unsafe"):
            require_mesh_visual_artifacts(result.document, unsafe, **kwargs)

        collision = dict(result.png_by_path)
        path = next(iter(collision))
        collision[path.upper()] = collision[path]
        with self.assertRaisesRegex(MeshVisualArtifactsError, "case-unique"):
            require_mesh_visual_artifacts(result.document, collision, **kwargs)


if __name__ == "__main__":
    unittest.main()
