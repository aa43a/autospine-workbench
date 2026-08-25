"""Pure, atomic P3 mesh pipeline orchestration tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
import hashlib
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.mesh_pipeline import (  # noqa: E402
    VerifiedMeshPipeline,
    VerifiedMeshPipelineError,
)
from autospine_workbench.png_rgba import encode_rgba_png  # noqa: E402
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from tests.test_mesh_probe_report import noop_inputs  # noqa: E402
from tests.test_mesh_visual_artifacts import renderable_a  # noqa: E402


TARGET_FIELDS = (
    "attachment_id", "source_layer_id", "side",
    "proximal_bone_id", "distal_bone_id",
)


class FakeCompilation:
    def __init__(self, rig, run, targets, images) -> None:
        self.project_id = run["project_id"]
        self.base_rig_sha256 = run["inputs"]["base_rig_sha256"]
        self.base_bundle_sha256 = run["inputs"]["base_bundle_sha256"]
        self.manifest_sha256 = run["inputs"]["layer_manifest_sha256"]
        self.status = f"converted={len(targets)}" if targets else "reviewed-noop"
        self._rig = deepcopy(rig)
        self._run = deepcopy(run)
        self._targets = [
            {field: getattr(target, field) for field in TARGET_FIELDS}
            for target in targets
        ]
        self._images = dict(images)
        self._source_pngs = {
            key: encode_rgba_png(value) for key, value in images.items()
        }
        self.image_reads = 0

    @property
    def rig(self):
        return deepcopy(self._rig)

    @property
    def run_manifest(self):
        return deepcopy(self._run)

    @property
    def targets(self):
        return deepcopy(self._targets)

    @property
    def target_images(self):
        self.image_reads += 1
        if self.image_reads > 1:
            raise AssertionError("target_images was read more than once")
        return dict(self._images)

    @property
    def target_png_bytes(self):
        return dict(self._source_pngs)


def fake_a() -> FakeCompilation:
    rig, run, _probes, targets, images = renderable_a()
    return FakeCompilation(rig, run, targets, images)


def fake_b() -> FakeCompilation:
    rig, run, targets = noop_inputs()
    return FakeCompilation(rig, run, targets, {})


def build(fake: FakeCompilation, state_root: Path | None = None):
    state_root = state_root or Path("unused-state")
    pipeline = VerifiedMeshPipeline(state_root)
    with patch(
        "autospine_workbench.mesh_pipeline.VerifiedMeshCompiler"
    ) as compiler:
        compiler.return_value.compile.return_value = fake
        result = pipeline.build(
            fake.project_id, fake.base_rig_sha256, fake.base_bundle_sha256
        )
    compiler.assert_called_once_with(state_root)
    compiler.return_value.compile.assert_called_once_with(
        fake.project_id, fake.base_rig_sha256, fake.base_bundle_sha256
    )
    return pipeline, result


class VerifiedMeshPipelineSuccessTests(unittest.TestCase):
    def test_a_like_build_returns_all_documents_pngs_and_sha_identities(self) -> None:
        fake = fake_a()
        before = deepcopy((fake._rig, fake._run, fake._targets, fake._images))
        _pipeline, result = build(fake)

        self.assertEqual("converted=2", result.summary)
        self.assertEqual(6, len(result.pngs))
        self.assertEqual(before, (fake._rig, fake._run, fake._targets, fake._images))
        self.assertEqual(1, fake.image_reads)
        outputs = result.output_sha256s
        self.assertEqual(canonical_sha256(result.rig), outputs["rig_sha256"])
        self.assertEqual(
            canonical_sha256(result.run_manifest), outputs["run_manifest_sha256"]
        )
        self.assertEqual(canonical_sha256(result.probes), outputs["probes_sha256"])
        self.assertEqual(canonical_sha256(result.visuals), outputs["visuals_sha256"])
        self.assertEqual(
            {key: hashlib.sha256(value).hexdigest()
             for key, value in result.pngs.items()},
            outputs["png_sha256_by_path"],
        )
        inputs = result.input_sha256s
        self.assertEqual(fake.base_rig_sha256, inputs["base_rig_sha256"])
        self.assertEqual(fake.base_bundle_sha256, inputs["base_bundle_sha256"])
        self.assertEqual(fake.manifest_sha256, inputs["layer_manifest_sha256"])
        self.assertEqual(
            {item["id"]: item["rgba_sha256"]
             for item in result.visuals["images"]},
            inputs["target_rgba_sha256_by_attachment"],
        )

    def test_b_noop_is_deterministic_and_has_empty_image_identities(self) -> None:
        first_fake, second_fake = fake_b(), fake_b()
        _pipeline, first = build(first_fake)
        _pipeline, second = build(second_fake)

        self.assertEqual(first, second)
        self.assertEqual("reviewed-noop", first.summary)
        self.assertEqual({}, first.pngs)
        self.assertEqual([], first.probes["attachments"])
        self.assertEqual([], first.visuals["artifacts"])
        self.assertEqual({}, first.input_sha256s["target_png_sha256_by_attachment"])
        self.assertEqual({}, first.output_sha256s["png_sha256_by_path"])

    def test_result_and_pipeline_are_frozen_and_accessors_are_isolated(self) -> None:
        pipeline, result = build(fake_a())
        changed_values = (
            (result.rig, "source"),
            (result.run_manifest, "inputs"),
            (result.probes, "source"),
            (result.visuals, "source"),
            (result.input_sha256s, "target_png_sha256_by_attachment"),
            (result.output_sha256s, "png_sha256_by_path"),
        )
        for changed, key in changed_values:
            changed[key] = {}
        changed_pngs = result.pngs
        first_path = next(iter(changed_pngs))
        changed_pngs[first_path] += b"tamper"

        self.assertTrue(result.rig["source"])
        self.assertTrue(result.probes["source"])
        self.assertNotEqual(changed_pngs[first_path], result.pngs[first_path])
        with self.assertRaises(FrozenInstanceError):
            result.summary = "forged"  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            pipeline.state_root = Path("other")  # type: ignore[misc]

    def test_pipeline_itself_does_not_create_state_or_follow_latest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            missing = Path(temporary) / "does-not-exist"
            build(fake_b(), missing)
            self.assertFalse(missing.exists())


class VerifiedMeshPipelineFailureTests(unittest.TestCase):
    def test_rejected_probe_stops_before_images_and_visual_generation(self) -> None:
        fake = fake_a()
        rejected = SimpleNamespace(document={
            "status": "rejected", "summary": fake.status,
        })
        with (
            patch("autospine_workbench.mesh_pipeline.VerifiedMeshCompiler") as compiler,
            patch(
                "autospine_workbench.mesh_pipeline.build_mesh_probe_report",
                return_value=rejected,
            ),
            patch(
                "autospine_workbench.mesh_pipeline.build_mesh_visual_artifacts"
            ) as visuals,
        ):
            compiler.return_value.compile.return_value = fake
            with self.assertRaisesRegex(
                VerifiedMeshPipelineError, "probes did not pass"
            ):
                VerifiedMeshPipeline(Path("unused")).build(
                    fake.project_id, fake.base_rig_sha256, fake.base_bundle_sha256
                )
        visuals.assert_not_called()
        self.assertEqual(0, fake.image_reads)

    def test_target_json_extra_missing_duplicate_and_profile_tamper_fail_early(self) -> None:
        mutations = (
            lambda items: items[0].update(extra=True),
            lambda items: items[0].pop("side"),
            lambda items: items.append(deepcopy(items[0])),
            lambda items: items[0].update(side="right"),
            lambda items: items[0].update(attachment_id="../unsafe"),
            lambda items: items[0].update(source_layer_id="another-source"),
        )
        for mutate in mutations:
            fake = fake_a()
            mutate(fake._targets)
            with (
                self.subTest(targets=fake._targets),
                patch(
                    "autospine_workbench.mesh_pipeline.VerifiedMeshCompiler"
                ) as compiler,
                patch(
                    "autospine_workbench.mesh_pipeline.build_mesh_probe_report"
                ) as probes,
            ):
                compiler.return_value.compile.return_value = fake
                with self.assertRaises(VerifiedMeshPipelineError):
                    VerifiedMeshPipeline(Path("unused")).build(
                        fake.project_id, fake.base_rig_sha256,
                        fake.base_bundle_sha256,
                    )
                probes.assert_not_called()

    def test_compiler_probe_and_visual_exceptions_share_the_pipeline_error(self) -> None:
        fake = fake_a()
        stages = ("compiler", "probes", "visuals")
        for stage in stages:
            with (
                self.subTest(stage=stage),
                patch(
                    "autospine_workbench.mesh_pipeline.VerifiedMeshCompiler"
                ) as compiler,
                patch(
                    "autospine_workbench.mesh_pipeline.build_mesh_probe_report"
                ) as probes,
                patch(
                    "autospine_workbench.mesh_pipeline.build_mesh_visual_artifacts"
                ) as visuals,
            ):
                compiler.return_value.compile.return_value = fake
                probes.return_value = SimpleNamespace(document={
                    "status": "passed", "summary": fake.status,
                })
                if stage == "compiler":
                    compiler.return_value.compile.side_effect = ValueError("boom")
                elif stage == "probes":
                    probes.side_effect = ValueError("boom")
                else:
                    visuals.side_effect = ValueError("boom")
                with self.assertRaises(VerifiedMeshPipelineError) as caught:
                    VerifiedMeshPipeline(Path("unused")).build(
                        fake.project_id, fake.base_rig_sha256,
                        fake.base_bundle_sha256,
                    )
                self.assertIsInstance(caught.exception.__cause__, ValueError)


if __name__ == "__main__":
    unittest.main()
