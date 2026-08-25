"""Trusted, read-only orchestration tests for exact P3 compilation inputs."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.layer_manifest import LayerManifestBundleStore  # noqa: E402
from autospine_workbench.manifest_bundle import LayerManifestBundleReader  # noqa: E402
from autospine_workbench.png_rgba import (  # noqa: E402
    RgbaImage,
    decode_rgba_png,
    write_rgba_png,
)
from autospine_workbench.region_rig import compile_region_rig  # noqa: E402
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from autospine_workbench.rig_bundle import RigBundleStore  # noqa: E402
from autospine_workbench.verified_mesh_compiler import (  # noqa: E402
    VerifiedMeshCompilation,
    VerifiedMeshCompiler,
    VerifiedMeshCompilerError,
)
from tests.test_mesh_rig import manifest_a, resolved_a, solid  # noqa: E402
from tests.test_region_rig import manifest_fixture, resolved_fixture  # noqa: E402


def _probes(project_id: str, rig: dict, run: dict) -> dict:
    return {
        "format": "autospine-rig-setup-probes", "format_version": 1,
        "project_id": project_id,
        "source": {
            "rig_sha256": canonical_sha256(rig),
            "layer_manifest_sha256": run["inputs"]["layer_manifest_sha256"],
            "resolved_project_sha256": run["inputs"]["resolved_project_sha256"],
        },
        "runner": {"id": "rig-setup-probes", "version": "1.0.0"},
        "status": "passed",
        "checks": [{
            "id": check_id,
            "status": "passed",
            **({"metrics": {"exact": True}}
               if check_id == "setup.pixel-reconstruction" else {}),
        } for check_id in (
            "source.identity", "inputs.reviewed", "bones.parent-links",
            "fk.setup-reconstruction", "attachments.region-bindings",
            "attachments.pivot-roundtrip", "slots.draw-order",
            "setup.pixel-reconstruction",
        )],
    }


class PublishedFixture:
    def __init__(self, root: Path, *, with_targets: bool) -> None:
        self.state = root / "state"
        self.assets = root / "assets"
        self.assets.mkdir()
        if with_targets:
            self.manifest, resolved = manifest_a(), resolved_a()
            sizes = {"torso": (16, 64), "leg-left": (32, 80), "leg-right": (32, 80)}
        else:
            self.manifest, resolved = manifest_fixture(), resolved_fixture()
            sizes = {"layer-001-torso": (30, 40)}
        self.project_id = self.manifest["project_id"]
        self.asset_paths: dict[str, Path] = {}
        for layer in self.manifest["layers"]:
            layer_id = layer["layer_id"]
            width, height = sizes[layer_id]
            path = self.assets / f"{layer_id}.png"
            write_rgba_png(path, solid(width, height))
            layer["raster"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            self.asset_paths[layer_id] = path
        compiled = compile_region_rig(
            self.manifest,
            resolved,
            layer_manifest_sha256=canonical_sha256(self.manifest),
            image_sizes=sizes,
        )
        self.layer_bundle, self.manifest_sha = LayerManifestBundleStore(
            self.state
        ).publish(self.project_id, self.manifest, self.asset_paths)
        self.rig, self.run = compiled.rig, compiled.run_manifest
        self.rig_bundle, self.rig_sha = RigBundleStore(self.state).publish(
            self.project_id,
            self.rig,
            self.run,
            _probes(self.project_id, self.rig, self.run),
            self.layer_bundle,
        )
        self.bundle_sha = self.rig_bundle.name

    def compile(self) -> VerifiedMeshCompilation:
        return VerifiedMeshCompiler(self.state).compile(
            self.project_id, self.rig_sha, self.bundle_sha
        )


def _files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*")) if path.is_file()
    }


class VerifiedMeshCompilerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_exact_a_like_bundle_is_deterministic_frozen_and_read_only(self) -> None:
        fixture = PublishedFixture(self.root, with_targets=True)
        before = _files(fixture.state)
        first, second = fixture.compile(), fixture.compile()

        self.assertEqual(first, second)
        self.assertEqual(fixture.rig_sha, first.base_rig_sha256)
        self.assertEqual(fixture.bundle_sha, first.base_bundle_sha256)
        self.assertEqual(fixture.manifest_sha, first.manifest_sha256)
        self.assertEqual("converted=2", first.status)
        self.assertEqual(["leg-left", "leg-right"], [
            item["attachment_id"] for item in first.target_image_snapshots
        ])
        for summary in first.target_image_snapshots:
            attachment_id = summary["attachment_id"]
            raw = first.target_png_bytes[attachment_id]
            image = first.target_images[attachment_id]
            self.assertEqual(summary["sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(summary["byte_length"], len(raw))
            self.assertEqual(
                (summary["width"], summary["height"]),
                (image.width, image.height),
            )
            self.assertEqual(image, decode_rgba_png(raw))
        self.assertEqual(2, sum(
            item["type"] == "mesh" for item in first.rig["attachments"]
        ))
        changed = first.compilation
        changed["rig"].clear()
        self.assertTrue(first.rig)
        snapshots = first.target_image_snapshots
        snapshots[0].clear()
        self.assertTrue(first.target_image_snapshots[0])
        images, png_bytes = first.target_images, first.target_png_bytes
        images.clear()
        png_bytes.clear()
        self.assertEqual({"leg-left", "leg-right"}, set(first.target_images))
        self.assertEqual({"leg-left", "leg-right"}, set(first.target_png_bytes))
        self.assertNotIn("target_images", first.to_dict())
        self.assertNotIn("target_png_bytes", first.to_dict())
        with self.assertRaises(FrozenInstanceError):
            first.manifest_sha256 = "0" * 64  # type: ignore[misc]
        self.assertEqual(before, _files(fixture.state))

    def test_only_target_manifest_pngs_get_one_snapshot_read(self) -> None:
        fixture = PublishedFixture(self.root, with_targets=True)
        original = Path.read_bytes
        calls: list[Path] = []

        def tracked(path: Path) -> bytes:
            calls.append(path)
            return original(path)

        with patch.object(Path, "read_bytes", tracked):
            fixture.compile()
        manifest_reads = [
            path.resolve() for path in calls
            if fixture.layer_bundle.resolve() in path.resolve().parents
            and path.suffix == ".png"
        ]
        self.assertEqual([
            (fixture.layer_bundle / "layers" / "leg-left.png").resolve(),
            (fixture.layer_bundle / "layers" / "leg-right.png").resolve(),
        ], sorted(manifest_reads))

    def test_reviewed_noop_does_not_decode_or_snapshot_a_target_png(self) -> None:
        fixture = PublishedFixture(self.root, with_targets=False)
        with patch(
            "autospine_workbench.verified_mesh_compiler.decode_rgba_png",
            side_effect=AssertionError("no target decode allowed"),
        ):
            result = fixture.compile()
        self.assertEqual("reviewed-noop", result.status)
        self.assertEqual([], result.targets)
        self.assertEqual([], result.target_image_snapshots)
        self.assertEqual({}, result.target_images)
        self.assertEqual({}, result.target_png_bytes)

    def test_exact_identities_reject_wrong_project_hashes_and_latest(self) -> None:
        fixture = PublishedFixture(self.root, with_targets=False)
        compiler = VerifiedMeshCompiler(fixture.state)
        cases = (
            ("other-project", fixture.rig_sha, fixture.bundle_sha),
            (fixture.project_id, "e" * 64, fixture.bundle_sha),
            (fixture.project_id, fixture.rig_sha, "e" * 64),
            (fixture.project_id, "latest", fixture.bundle_sha),
            (fixture.project_id, fixture.rig_sha, "latest"),
        )
        for values in cases:
            with self.subTest(values=values), self.assertRaises(VerifiedMeshCompilerError):
                compiler.compile(*values)

    def test_manifest_base_bundle_png_and_path_tamper_fail_uniformly(self) -> None:
        mutations = (
            lambda f: (f.layer_bundle / "manifest.json").write_text(
                "{}\n", encoding="utf-8"
            ),
            lambda f: (f.rig_bundle / "rig.json").write_text("{}\n", encoding="utf-8"),
            lambda f: (f.rig_bundle / "unexpected.txt").write_text("x", encoding="utf-8"),
            lambda f: (f.layer_bundle / "layers" / "leg-left.png").write_bytes(b"bad png"),
            lambda f: _tamper_manifest_path(f),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as directory:
                fixture = PublishedFixture(Path(directory), with_targets=True)
                mutate(fixture)
                with self.assertRaises(VerifiedMeshCompilerError):
                    fixture.compile()

    def test_post_reader_hash_change_and_decoded_size_change_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = PublishedFixture(Path(directory), with_targets=True)
            original_load = LayerManifestBundleReader.load

            def load_then_change(reader, *args):
                loaded = original_load(reader, *args)
                target = loaded.path / "layers" / "leg-left.png"
                write_rgba_png(target, RgbaImage(32, 80, bytes((1, 2, 3, 255)) * 32 * 80))
                return loaded

            with patch(
                "autospine_workbench.verified_mesh_compiler.LayerManifestBundleReader.load",
                load_then_change,
            ), self.assertRaisesRegex(VerifiedMeshCompilerError, "hash changed"):
                fixture.compile()

        fixture = PublishedFixture(self.root, with_targets=True)

        def wrong_size(data: bytes, *, source_name: str):
            image = decode_rgba_png(data, source_name=source_name)
            return RgbaImage(image.width + 1, image.height, image.pixels)

        with patch(
            "autospine_workbench.verified_mesh_compiler.decode_rgba_png",
            wrong_size,
        ), self.assertRaisesRegex(VerifiedMeshCompilerError, "size changed"):
            fixture.compile()


def _tamper_manifest_path(fixture: PublishedFixture) -> None:
    path = fixture.layer_bundle / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["layers"][0]["raster"]["artifact_path"] = "../escape.png"
    path.write_text(json.dumps(manifest), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
