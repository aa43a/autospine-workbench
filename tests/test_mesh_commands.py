"""P3 mesh compile and exact-address verification command tests."""

from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
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

from autospine_workbench.mesh_bundle_store import MeshBundleStoreError  # noqa: E402
from autospine_workbench.mesh_bundle_reader import (  # noqa: E402
    VerifiedMeshBundleReaderError,
)
from autospine_workbench.mesh_commands import (  # noqa: E402
    compile_mesh_rig_command,
    verify_mesh_bundle_command,
)
from autospine_workbench.mesh_pipeline import VerifiedMeshPipelineError  # noqa: E402
from tests.test_mesh_bundle_integrity import MeshReaderFixture  # noqa: E402


PROJECT = "sample-a"
BASE_RIG = "a" * 64
BASE_BUNDLE = "b" * 64
RIG = "c" * 64
RUN = "d" * 64
PROBES = "e" * 64
VISUALS = "f" * 64
BUNDLE = "1" * 64


def fake_pipeline(*, summary="converted=2", pngs=None):
    return SimpleNamespace(
        project_id=PROJECT,
        summary=summary,
        rig={"document": "rig"},
        run_manifest={"document": "run"},
        probes={"document": "probes"},
        visuals={"document": "visuals"},
        pngs={"weights/leg-left.png": b"png"} if pngs is None else pngs,
        input_sha256s={
            "base_rig_sha256": BASE_RIG,
            "base_bundle_sha256": BASE_BUNDLE,
            "layer_manifest_sha256": "2" * 64,
            "resolved_project_sha256": "3" * 64,
        },
        output_sha256s={
            "rig_sha256": RIG,
            "run_manifest_sha256": RUN,
            "probes_sha256": PROBES,
            "visuals_sha256": VISUALS,
            "png_sha256_by_path": {},
        },
    )


def fake_verified(state_root: Path):
    return SimpleNamespace(
        path=state_root / "builds" / PROJECT / "mesh-rig-ir" / RIG / BUNDLE,
        project_id=PROJECT,
        base_rig_sha256=BASE_RIG,
        base_bundle_sha256=BASE_BUNDLE,
        layer_manifest_sha256="2" * 64,
        resolved_project_sha256="3" * 64,
        rig_sha256=RIG,
        run_sha256=RUN,
        probes_sha256=PROBES,
        visuals_sha256=VISUALS,
        bundle_sha256=BUNDLE,
        visuals={"summary": "converted=2"},
    )


def invoke(function, *args, **kwargs):
    output = io.StringIO()
    with redirect_stdout(output):
        status = function(*args, **kwargs)
    return status, json.loads(output.getvalue())


class CompileMeshRigCommandTests(unittest.TestCase):
    def setUp(self):
        self.state = Path("exact-state")
        self.pipeline = fake_pipeline()
        self.verified = fake_verified(self.state)
        self.published = SimpleNamespace(
            path=self.verified.path,
            rig_sha256=RIG,
            bundle_sha256=BUNDLE,
        )

    def run_success(self, pipeline=None):
        pipeline = pipeline or self.pipeline
        self.verified.visuals = {"summary": pipeline.summary}
        with (
            patch("autospine_workbench.mesh_commands.VerifiedMeshPipeline") as builder,
            patch("autospine_workbench.mesh_commands.MeshBundleStore") as store,
            patch("autospine_workbench.mesh_commands._load_verified_bundle",
                  return_value=self.verified) as load,
        ):
            builder.return_value.build.return_value = pipeline
            store.return_value.publish.return_value = self.published
            result = invoke(
                compile_mesh_rig_command,
                PROJECT,
                self.state,
                base_rig_sha256=BASE_RIG,
                base_bundle_sha256=BASE_BUNDLE,
            )
        return result, builder, store, load

    def test_success_runs_exact_pipeline_publish_and_full_readback(self):
        (status, response), builder, store, load = self.run_success()
        self.assertEqual(0, status)
        self.assertEqual({
            "ok": True, "status": "passed", "summary": "converted=2",
            "project_id": PROJECT,
            "base_rig_sha256": BASE_RIG, "base_bundle_sha256": BASE_BUNDLE,
            "layer_manifest_sha256": "2" * 64,
            "resolved_project_sha256": "3" * 64,
            "rig_sha256": RIG, "run_manifest_sha256": RUN,
            "probes_sha256": PROBES, "visuals_sha256": VISUALS,
            "bundle_sha256": BUNDLE, "bundle_path": str(self.verified.path),
        }, response)
        builder.assert_called_once_with(self.state)
        builder.return_value.build.assert_called_once_with(PROJECT, BASE_RIG, BASE_BUNDLE)
        store.assert_called_once_with(self.state)
        store.return_value.publish.assert_called_once_with(
            PROJECT, self.pipeline.rig, self.pipeline.run_manifest,
            self.pipeline.probes, self.pipeline.visuals, self.pipeline.pngs,
        )
        load.assert_called_once_with(self.state, PROJECT, RIG, BUNDLE)

    def test_noop_publishes_empty_png_inventory_and_keeps_reviewed_status(self):
        pipeline = fake_pipeline(summary="reviewed-noop", pngs={})
        (status, response), _builder, store, _load = self.run_success(pipeline)
        self.assertEqual(0, status)
        self.assertEqual("reviewed-noop", response["summary"])
        self.assertEqual({}, store.return_value.publish.call_args.args[-1])

    def test_pipeline_store_and_integrity_errors_return_two_and_stop_downstream(self):
        stages = ("pipeline", "store", "integrity")
        for stage in stages:
            with (
                self.subTest(stage=stage),
                patch("autospine_workbench.mesh_commands.VerifiedMeshPipeline") as builder,
                patch("autospine_workbench.mesh_commands.MeshBundleStore") as store,
                patch("autospine_workbench.mesh_commands._load_verified_bundle") as load,
            ):
                builder.return_value.build.return_value = self.pipeline
                store.return_value.publish.return_value = self.published
                load.return_value = self.verified
                if stage == "pipeline":
                    builder.return_value.build.side_effect = VerifiedMeshPipelineError("bad pipeline")
                elif stage == "store":
                    store.return_value.publish.side_effect = MeshBundleStoreError("bad store")
                else:
                    load.side_effect = VerifiedMeshBundleReaderError("bad integrity")
                status, response = invoke(
                    compile_mesh_rig_command, PROJECT, self.state,
                    base_rig_sha256=BASE_RIG, base_bundle_sha256=BASE_BUNDLE,
                )
                self.assertEqual(2, status)
                self.assertFalse(response["ok"])
                self.assertEqual("error", response["status"])
                if stage == "pipeline":
                    store.assert_not_called()
                    load.assert_not_called()
                elif stage == "store":
                    load.assert_not_called()

    def test_changed_baseline_or_readback_identity_is_never_published_as_success(self):
        changed = fake_pipeline()
        changed.input_sha256s = deepcopy(changed.input_sha256s)
        changed.input_sha256s["base_rig_sha256"] = "9" * 64
        with (
            patch("autospine_workbench.mesh_commands.VerifiedMeshPipeline") as builder,
            patch("autospine_workbench.mesh_commands.MeshBundleStore") as store,
        ):
            builder.return_value.build.return_value = changed
            status, response = invoke(
                compile_mesh_rig_command, PROJECT, self.state,
                base_rig_sha256=BASE_RIG, base_bundle_sha256=BASE_BUNDLE,
            )
        self.assertEqual(2, status)
        self.assertIn("input identity", response["error"])
        store.assert_not_called()

        mutations = {
            "base_bundle_sha256": "8" * 64,
            "layer_manifest_sha256": "8" * 64,
            "resolved_project_sha256": "8" * 64,
            "rig_sha256": "8" * 64,
            "run_sha256": "8" * 64,
            "probes_sha256": "8" * 64,
            "visuals_sha256": "8" * 64,
            "path": self.verified.path.parent / ("8" * 64),
        }
        for field, value in mutations.items():
            wrong = fake_verified(self.state)
            setattr(wrong, field, value)
            with (
                self.subTest(field=field),
                patch("autospine_workbench.mesh_commands.VerifiedMeshPipeline") as builder,
                patch("autospine_workbench.mesh_commands.MeshBundleStore") as store,
                patch("autospine_workbench.mesh_commands._load_verified_bundle",
                      return_value=wrong),
            ):
                builder.return_value.build.return_value = self.pipeline
                store.return_value.publish.return_value = self.published
                status, response = invoke(
                    compile_mesh_rig_command, PROJECT, self.state,
                    base_rig_sha256=BASE_RIG, base_bundle_sha256=BASE_BUNDLE,
                )
            self.assertEqual(2, status)
            self.assertIn(field, response["error"])


class VerifyMeshBundleCommandTests(unittest.TestCase):
    def test_verify_is_read_only_and_passes_only_the_exact_address(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            marker = state / "owner.txt"
            marker.write_bytes(b"unchanged")
            before = {item.relative_to(state).as_posix(): item.read_bytes()
                      for item in state.rglob("*") if item.is_file()}
            verified = fake_verified(state)
            with patch("autospine_workbench.mesh_commands._load_verified_bundle",
                       return_value=verified) as load:
                status, response = invoke(
                    verify_mesh_bundle_command, PROJECT, state,
                    rig_sha256=RIG, bundle_sha256=BUNDLE,
                )
            after = {item.relative_to(state).as_posix(): item.read_bytes()
                     for item in state.rglob("*") if item.is_file()}
        self.assertEqual(0, status)
        self.assertTrue(response["ok"])
        self.assertEqual("passed", response["status"])
        self.assertEqual("converted=2", response["summary"])
        self.assertEqual(str(verified.path), response["bundle_path"])
        self.assertEqual(before, after)
        load.assert_called_once_with(state, PROJECT, RIG, BUNDLE)

    def test_verify_error_is_domain_json_and_exit_two(self):
        with patch("autospine_workbench.mesh_commands._load_verified_bundle",
                   side_effect=VerifiedMeshBundleReaderError("tampered bundle")):
            status, response = invoke(
                verify_mesh_bundle_command, PROJECT, Path("state"),
                rig_sha256=RIG, bundle_sha256=BUNDLE,
            )
        self.assertEqual(2, status)
        self.assertEqual({"ok": False, "status": "error",
                          "error": "tampered bundle"}, response)


class MeshCommandEndToEndTests(unittest.TestCase):
    def test_real_noop_compile_and_verify_use_the_same_exact_address(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = MeshReaderFixture(Path(directory), with_targets=False)
            status, compiled = invoke(
                compile_mesh_rig_command, fixture.project_id, fixture.state,
                base_rig_sha256=fixture.base_rig_sha,
                base_bundle_sha256=fixture.base_bundle_sha,
            )
            self.assertEqual(0, status)
            self.assertEqual("reviewed-noop", compiled["summary"])
            self.assertEqual(fixture.base_rig_sha, compiled["base_rig_sha256"])
            self.assertEqual(fixture.base_bundle_sha, compiled["base_bundle_sha256"])
            before = {item.relative_to(fixture.state).as_posix(): item.read_bytes()
                      for item in fixture.state.rglob("*") if item.is_file()}
            status, verified = invoke(
                verify_mesh_bundle_command, fixture.project_id, fixture.state,
                rig_sha256=compiled["rig_sha256"],
                bundle_sha256=compiled["bundle_sha256"],
            )
            after = {item.relative_to(fixture.state).as_posix(): item.read_bytes()
                     for item in fixture.state.rglob("*") if item.is_file()}
        self.assertEqual(0, status)
        self.assertEqual("passed", verified["status"])
        self.assertEqual("reviewed-noop", verified["summary"])
        self.assertEqual(compiled["bundle_path"], verified["bundle_path"])
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
