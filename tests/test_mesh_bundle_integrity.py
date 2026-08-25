"""Read-only full P3 mesh bundle verification tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.layer_manifest import LayerManifestBundleStore  # noqa: E402
from autospine_workbench.mesh_bundle_reader import (  # noqa: E402
    VerifiedMeshBundleReader,
    VerifiedMeshBundleReaderError,
)
from autospine_workbench.mesh_bundle_store import MeshBundleStore  # noqa: E402
from autospine_workbench.mesh_pipeline import VerifiedMeshPipeline  # noqa: E402
from autospine_workbench.png_rgba import write_rgba_png  # noqa: E402
from autospine_workbench.region_rig import compile_region_rig  # noqa: E402
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from autospine_workbench.rig_bundle import RigBundleStore  # noqa: E402
from autospine_workbench.verified_mesh_compiler import VerifiedMeshCompiler  # noqa: E402
from tests.test_mesh_rig import manifest_a, resolved_a, solid  # noqa: E402
from tests.test_verified_mesh_compiler import PublishedFixture, _probes  # noqa: E402


class MeshReaderFixture:
    def __init__(self, root: Path, *, with_targets: bool) -> None:
        if with_targets:
            self._build_renderable_a(root)
        else:
            base = PublishedFixture(root, with_targets=False)
            self.state = base.state
            self.project_id = base.project_id
            self.base_rig_sha = base.rig_sha
            self.base_bundle_sha = base.bundle_sha
            self.layer_bundle = base.layer_bundle
        result = VerifiedMeshPipeline(self.state).build(
            self.project_id, self.base_rig_sha, self.base_bundle_sha
        )
        self.pipeline_result = result
        self.published = MeshBundleStore(self.state).publish(
            self.project_id, result.rig, result.run_manifest,
            result.probes, result.visuals, result.pngs,
        )

    def _build_renderable_a(self, root: Path) -> None:
        self.state, assets = root / "state", root / "assets"
        assets.mkdir()
        manifest, resolved = manifest_a(), resolved_a()
        manifest["source"]["canvas"] = [360, 300]
        for layer in manifest["layers"]:
            raster = layer["raster"]
            raster["canvas_size"] = [360, 300]
            raster["canvas_offset_xy"] = [
                raster["canvas_offset_xy"][0] + 100,
                raster["canvas_offset_xy"][1] + 100,
            ]
            raster["crop_bbox_xywh"][0] += 100
            raster["crop_bbox_xywh"][1] += 100
        resolved["canvas"] = {"width": 360, "height": 300}
        for joint in resolved["skeleton"]["joints"]:
            joint["x"] += 100
            joint["y"] += 100
        resolved.pop("sha256")
        resolved["sha256"] = canonical_sha256(resolved)
        sizes = {"torso": (16, 64), "leg-left": (32, 80), "leg-right": (32, 80)}
        paths = {}
        for layer in manifest["layers"]:
            layer_id = layer["layer_id"]
            path = assets / f"{layer_id}.png"
            write_rgba_png(path, solid(*sizes[layer_id]))
            layer["raster"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            paths[layer_id] = path
        compiled = compile_region_rig(
            manifest, resolved,
            layer_manifest_sha256=canonical_sha256(manifest),
            image_sizes=sizes,
        )
        self.project_id = manifest["project_id"]
        self.layer_bundle, _manifest_sha = LayerManifestBundleStore(
            self.state
        ).publish(self.project_id, manifest, paths)
        base_path, self.base_rig_sha = RigBundleStore(self.state).publish(
            self.project_id, compiled.rig, compiled.run_manifest,
            _probes(self.project_id, compiled.rig, compiled.run_manifest),
            self.layer_bundle,
        )
        self.base_bundle_sha = base_path.name

    @property
    def bundle(self) -> Path:
        return self.published.path

    def load(self):
        return VerifiedMeshBundleReader(self.state).load(
            self.project_id,
            self.published.rig_sha256,
            self.published.bundle_sha256,
        )


class MeshBundleReaderSuccessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_a_like_bundle_is_fully_reproduced_with_isolated_frozen_accessors(self) -> None:
        fixture = MeshReaderFixture(self.root, with_targets=True)
        result = fixture.load()

        self.assertEqual(fixture.bundle.resolve(), result.path)
        self.assertEqual(fixture.project_id, result.project_id)
        self.assertEqual(fixture.published.rig_sha256, result.rig_sha256)
        self.assertEqual(fixture.published.bundle_sha256, result.bundle_sha256)
        self.assertEqual(fixture.base_rig_sha, result.base_rig_sha256)
        self.assertEqual(fixture.base_bundle_sha, result.base_bundle_sha256)
        self.assertEqual(
            result.run_manifest["inputs"]["layer_manifest_sha256"],
            result.layer_manifest_sha256,
        )
        self.assertEqual(
            result.run_manifest["inputs"]["resolved_project_sha256"],
            result.resolved_project_sha256,
        )
        self.assertEqual(6, len(result.pngs))
        self.assertEqual("passed", result.probes["status"])
        self.assertEqual("passed", result.visuals["status"])
        self.assertEqual(set(result.inventory), {
            path.relative_to(fixture.bundle).as_posix()
            for path in fixture.bundle.rglob("*") if path.is_file()
        })
        changed_rig, changed_pngs = result.rig, result.pngs
        changed_rig.clear()
        first = next(iter(changed_pngs))
        changed_pngs[first] += b"tamper"
        self.assertTrue(result.rig)
        self.assertNotEqual(changed_pngs[first], result.pngs[first])
        with self.assertRaises(FrozenInstanceError):
            result.bundle_sha256 = "0" * 64  # type: ignore[misc]

    def test_noop_bundle_is_valid_without_artifact_directories(self) -> None:
        fixture = MeshReaderFixture(self.root, with_targets=False)
        result = fixture.load()

        self.assertEqual("reviewed-noop", result.visuals["summary"])
        self.assertEqual({}, result.pngs)
        self.assertEqual(
            {"rig.json", "run-manifest.json", "probes.json", "visuals.json"},
            set(result.inventory),
        )

    def test_each_mesh_bundle_file_is_opened_once_from_one_snapshot(self) -> None:
        fixture = MeshReaderFixture(self.root, with_targets=True)
        before = _tree_snapshot(fixture.state)
        original = Path.open
        reads: list[str] = []

        def tracked(path: Path, *args, **kwargs):
            try:
                relative = path.resolve().relative_to(
                    fixture.bundle.resolve()
                ).as_posix()
            except ValueError:
                relative = ""
            if relative:
                reads.append(relative)
            return original(path, *args, **kwargs)

        with patch.object(Path, "open", tracked):
            fixture.load()
        self.assertEqual(sorted(set(reads)), sorted(reads))
        self.assertEqual(set(fixture.pipeline_result.pngs) | {
            "rig.json", "run-manifest.json", "probes.json", "visuals.json"
        }, set(reads))
        self.assertEqual(before, _tree_snapshot(fixture.state))


class MeshBundleReaderTamperTests(unittest.TestCase):
    def fixture(self, *, with_targets=True) -> MeshReaderFixture:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        return MeshReaderFixture(Path(temporary.name), with_targets=with_targets)

    def assert_rejected(self, fixture: MeshReaderFixture) -> None:
        with self.assertRaises(VerifiedMeshBundleReaderError):
            fixture.load()

    def test_wrong_requested_identity_latest_and_case_mismatch_are_rejected(self) -> None:
        fixture = self.fixture(with_targets=False)
        reader = VerifiedMeshBundleReader(fixture.state)
        cases = (
            ("other-project", fixture.published.rig_sha256, fixture.published.bundle_sha256),
            (fixture.project_id, "0" * 64, fixture.published.bundle_sha256),
            (fixture.project_id, fixture.published.rig_sha256, "0" * 64),
            (fixture.project_id, "latest", fixture.published.bundle_sha256),
            (fixture.project_id, fixture.published.rig_sha256, "latest"),
        )
        for values in cases:
            with self.subTest(values=values), self.assertRaises(
                VerifiedMeshBundleReaderError
            ):
                reader.load(*values)

        mesh_root = fixture.bundle.parent.parent
        intermediate = mesh_root.parent / "rename"
        mesh_root.rename(intermediate)
        intermediate.rename(mesh_root.parent / "MESH-RIG-IR")
        self.assert_rejected(fixture)

    def test_artifact_filename_case_change_and_resource_limits_are_rejected(self) -> None:
        fixture = self.fixture()
        image = next((fixture.bundle / "weights").iterdir())
        intermediate = image.with_name("temporary-name.png")
        changed = image.with_name(image.stem.upper() + ".png")
        image.rename(intermediate)
        intermediate.rename(changed)
        self.assert_rejected(fixture)

        fixture = self.fixture()
        with patch(
            "autospine_workbench.mesh_bundle_reader.MAX_DOCUMENT_BYTES", 1
        ):
            self.assert_rejected(fixture)
        with patch("autospine_workbench.mesh_bundle_reader.MAX_ARTIFACTS", 1):
            self.assert_rejected(fixture)

    def test_missing_extra_empty_nested_and_non_png_inventory_are_rejected(self) -> None:
        mutations = (
            lambda bundle: (bundle / "probes.json").unlink(),
            lambda bundle: (bundle / "extra.json").write_bytes(b"{}"),
            lambda bundle: (bundle / "empty").mkdir(),
            lambda bundle: (bundle / "weights" / "nested").mkdir(),
            lambda bundle: (bundle / "weights" / "extra.txt").write_bytes(b"x"),
        )
        for mutate in mutations:
            fixture = self.fixture()
            mutate(fixture.bundle)
            with self.subTest(mutate=mutate):
                self.assert_rejected(fixture)

        noop = self.fixture(with_targets=False)
        (noop.bundle / "weights").mkdir()
        self.assert_rejected(noop)

    def test_whitespace_duplicate_nonfinite_and_invalid_utf8_json_are_rejected(self) -> None:
        def whitespace(path):
            path.write_bytes(path.read_bytes() + b"\n")

        def duplicate(path):
            raw = path.read_bytes()
            path.write_bytes(b'{"format":"forged",' + raw[1:])

        def nonfinite(path):
            raw = path.read_bytes().replace(b'"format_version":1', b'"format_version":NaN')
            path.write_bytes(raw)

        mutations = (whitespace, duplicate, nonfinite, lambda path: path.write_bytes(b"\xff"))
        for mutate in mutations:
            fixture = self.fixture()
            mutate(fixture.bundle / "visuals.json")
            with self.subTest(mutate=mutate):
                self.assert_rejected(fixture)

    def test_png_probe_metrics_visual_path_and_rig_bytes_tamper_are_rejected(self) -> None:
        def png(fixture):
            path = next((fixture.bundle / "weights").iterdir())
            path.write_bytes(path.read_bytes() + b"tamper")

        def probe(fixture):
            path = fixture.bundle / "probes.json"
            value = json.loads(path.read_bytes())
            value["attachments"][0]["action_probe"]["setup"]["metrics"][
                "maximum_edge_stretch"
            ] = 9
            _canonical_write(path, value)

        def visual(fixture):
            path = fixture.bundle / "visuals.json"
            value = json.loads(path.read_bytes())
            value["artifacts"][0]["path"] = "../escape.png"
            _canonical_write(path, value)

        def rig(fixture):
            path = fixture.bundle / "rig.json"
            value = json.loads(path.read_bytes())
            value["qa"]["checks"][0]["status"] = "rejected"
            _canonical_write(path, value)

        for mutate in (png, probe, visual, rig):
            fixture = self.fixture()
            mutate(fixture)
            with self.subTest(mutate=mutate):
                self.assert_rejected(fixture)

    def test_base_manifest_png_and_base_bundle_dependency_changes_are_rejected(self) -> None:
        mutations = (
            lambda fixture: (fixture.layer_bundle / "manifest.json").write_bytes(b"{}"),
            lambda fixture: (
                fixture.layer_bundle / "layers" / "leg-left.png"
            ).write_bytes(b"bad"),
            lambda fixture: (
                fixture.state / "builds" / fixture.project_id / "rig-ir" /
                fixture.base_rig_sha / fixture.base_bundle_sha / "rig.json"
            ).write_bytes(b"{}"),
        )
        for mutate in mutations:
            fixture = self.fixture()
            mutate(fixture)
            with self.subTest(mutate=mutate):
                self.assert_rejected(fixture)

    def test_compiler_target_extra_duplicate_and_profile_tamper_are_rejected(self) -> None:
        mutations = (
            lambda items: items[0].update(extra=True),
            lambda items: items.append(deepcopy(items[0])),
            lambda items: items[0].update(side="right"),
        )
        for mutate in mutations:
            fixture = self.fixture()
            compiled = VerifiedMeshCompiler(fixture.state).compile(
                fixture.project_id, fixture.base_rig_sha, fixture.base_bundle_sha
            )
            targets = compiled.targets
            mutate(targets)
            forged = SimpleNamespace(
                project_id=compiled.project_id,
                base_rig_sha256=compiled.base_rig_sha256,
                base_bundle_sha256=compiled.base_bundle_sha256,
                manifest_sha256=compiled.manifest_sha256,
                rig=compiled.rig,
                run_manifest=compiled.run_manifest,
                targets=targets,
                status=compiled.status,
                target_images=compiled.target_images,
            )
            with (
                self.subTest(mutate=mutate),
                patch(
                    "autospine_workbench.mesh_bundle_integrity.VerifiedMeshCompiler"
                ) as compiler,
            ):
                compiler.return_value.compile.return_value = forged
                self.assert_rejected(fixture)

    def test_changed_compiler_rig_or_run_output_cannot_reuse_the_old_bundle(self) -> None:
        for document in ("rig", "run"):
            fixture = self.fixture()
            compiled = VerifiedMeshCompiler(fixture.state).compile(
                fixture.project_id, fixture.base_rig_sha, fixture.base_bundle_sha
            )
            changed_rig, changed_run = compiled.rig, compiled.run_manifest
            if document == "rig":
                changed_rig["canvas"]["width"] += 1
            else:
                changed_run["compiler"]["version"] = "2.0.0"
            forged = SimpleNamespace(
                project_id=compiled.project_id,
                base_rig_sha256=compiled.base_rig_sha256,
                base_bundle_sha256=compiled.base_bundle_sha256,
                manifest_sha256=compiled.manifest_sha256,
                rig=changed_rig,
                run_manifest=changed_run,
                targets=compiled.targets,
                status=compiled.status,
                target_images=compiled.target_images,
            )
            with (
                self.subTest(document=document),
                patch(
                    "autospine_workbench.mesh_bundle_integrity.VerifiedMeshCompiler"
                ) as compiler,
            ):
                compiler.return_value.compile.return_value = forged
                self.assert_rejected(fixture)

    def test_symlinked_artifact_and_state_root_are_rejected_when_supported(self) -> None:
        fixture = self.fixture()
        source = next((fixture.bundle / "weights").iterdir())
        outside = fixture.bundle.parent / "outside.png"
        shutil.copyfile(source, outside)
        source.unlink()
        try:
            source.symlink_to(outside)
        except OSError:
            self.skipTest("file symlinks are unavailable")
        self.assert_rejected(fixture)

        alias = fixture.state.parent / "state-alias"
        try:
            alias.symlink_to(fixture.state, target_is_directory=True)
        except OSError:
            return
        try:
            with self.assertRaises(VerifiedMeshBundleReaderError):
                VerifiedMeshBundleReader(alias).load(
                    fixture.project_id,
                    fixture.published.rig_sha256,
                    fixture.published.bundle_sha256,
                )
        finally:
            alias.unlink()


def _canonical_write(path: Path, value) -> None:
    path.write_bytes(json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8"))


def _tree_snapshot(root: Path):
    directories = tuple(sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*") if path.is_dir()
    ))
    files = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*") if path.is_file()
    }
    return directories, files


if __name__ == "__main__":
    unittest.main()
