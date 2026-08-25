"""P6 tests for exact P3-to-original-image loading."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import hashlib
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

from autospine_workbench.mesh_bundle_reader import (  # noqa: E402
    VerifiedMeshBundleReader,
)
from autospine_workbench.mesh_source_images import (  # noqa: E402
    VerifiedMeshSourceReader,
    VerifiedMeshSourceReaderError,
)
from autospine_workbench.png_rgba import (  # noqa: E402
    RgbaImage,
    encode_rgba_png,
)
from autospine_workbench.verified_base_rig import (  # noqa: E402
    VerifiedBaseRigReader,
)
from autospine_workbench.verified_mesh_compiler import (  # noqa: E402
    VerifiedMeshCompiler,
)
from tests.test_mesh_bundle_integrity import MeshReaderFixture  # noqa: E402


class MeshSourceFixture:
    def __init__(self, root: Path, *, with_targets: bool = True) -> None:
        self.bundle = MeshReaderFixture(root, with_targets=with_targets)
        self.verified = VerifiedMeshBundleReader(self.bundle.state).load(
            self.bundle.project_id,
            self.bundle.published.rig_sha256,
            self.bundle.published.bundle_sha256,
        )
        self.reader = VerifiedMeshSourceReader(self.bundle.state)

    def load(self):
        return self.reader.load(
            self.bundle.project_id,
            self.bundle.published.rig_sha256,
            self.bundle.published.bundle_sha256,
        )

    def load_forged(self, verified):
        with patch(
            "autospine_workbench.mesh_source_images.VerifiedMeshBundleReader"
        ) as reader:
            reader.return_value.load.return_value = verified
            return self.load()

    def with_rig(self, mutate):
        rig = deepcopy(self.verified.rig)
        mutate(rig)
        documents = dict(self.verified._document_json_items)
        documents["rig.json"] = _canonical(rig)
        items = tuple(
            (name, documents[name])
            for name, _value in self.verified._document_json_items
        )
        return replace(self.verified, _document_json_items=items)

    def with_source_pngs(self, pngs):
        return replace(
            self.verified,
            _source_png_items=tuple(sorted(pngs.items())),
        )


class MeshSourceReaderSuccessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.fixture = MeshSourceFixture(Path(self.temporary.name))

    def test_real_p3_shape_returns_full_address_and_original_rgba_pngs(self) -> None:
        result = self.fixture.load()

        self.assertEqual(
            (
                self.fixture.bundle.project_id,
                self.fixture.bundle.published.rig_sha256,
                self.fixture.bundle.published.bundle_sha256,
            ),
            result.p3_address,
        )
        self.assertEqual(self.fixture.verified.path, result.path)
        self.assertEqual(self.fixture.bundle.base_rig_sha, result.base_rig_sha256)
        self.assertEqual(self.fixture.bundle.base_bundle_sha, result.base_bundle_sha256)
        self.assertEqual(
            sorted(item["id"] for item in self.fixture.verified.rig["attachments"]),
            [item.attachment_id for item in result.images],
        )
        self.assertEqual(set(result.image_by_attachment), set(result.png_by_attachment))
        for item in result.images:
            self.assertEqual(
                item.image_sha256, hashlib.sha256(item.png_bytes).hexdigest()
            )
            self.assertGreater(item.width, 0)
            self.assertGreater(item.height, 0)

    def test_snapshot_propagates_through_existing_p2_and_p3_boundaries(self) -> None:
        base = VerifiedBaseRigReader(self.fixture.bundle.state).load(
            self.fixture.bundle.project_id,
            self.fixture.bundle.base_rig_sha,
            self.fixture.bundle.base_bundle_sha,
        )
        compiled = VerifiedMeshCompiler(self.fixture.bundle.state).compile(
            self.fixture.bundle.project_id,
            self.fixture.bundle.base_rig_sha,
            self.fixture.bundle.base_bundle_sha,
        )
        self.assertEqual(base.region_pngs, compiled.source_png_bytes)
        self.assertEqual(base.region_pngs, self.fixture.verified.source_pngs)
        self.assertTrue(all(path.startswith("layers/") for path in base.region_pngs))
        self.assertTrue(all(
            path.startswith(("weights/", "poses/"))
            for path in self.fixture.verified.pngs
        ))
        self.assertTrue(set(base.region_pngs).isdisjoint(self.fixture.verified.pngs))

        isolated = base.region_pngs
        isolated.clear()
        self.assertTrue(base.region_pngs)
        isolated = self.fixture.verified.source_pngs
        isolated.clear()
        self.assertTrue(self.fixture.verified.source_pngs)

    def test_result_is_frozen_copy_isolated_deterministic_and_read_only(self) -> None:
        before = _tree_snapshot(self.fixture.bundle.state)
        first = self.fixture.load()
        second = self.fixture.load()

        self.assertEqual(first, second)
        self.assertEqual(before, _tree_snapshot(self.fixture.bundle.state))
        changed_rig = first.rig
        changed_rig.clear()
        changed_pngs = first.png_by_attachment
        changed_pngs.clear()
        self.assertTrue(first.rig)
        self.assertTrue(first.png_by_attachment)
        with self.assertRaises(FrozenInstanceError):
            first.project_id = "changed"  # type: ignore[misc]

    def test_region_only_reviewed_noop_shape_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = MeshSourceFixture(Path(directory), with_targets=False)
            result = fixture.load()
        self.assertTrue(result.images)
        self.assertTrue(all(item["type"] == "region" for item in result.rig["attachments"]))

    def test_adapter_boundary_does_not_scan_to_complete_a_verified_snapshot(self) -> None:
        with (
            patch.object(Path, "iterdir", side_effect=AssertionError("scan")),
            patch.object(Path, "rglob", side_effect=AssertionError("scan")),
        ):
            result = self.fixture.load_forged(self.fixture.verified)
        self.assertEqual(set(result.png_by_attachment), {
            item["id"] for item in self.fixture.verified.rig["attachments"]
        })


class MeshSourceReaderTamperTests(unittest.TestCase):
    def fixture(self) -> MeshSourceFixture:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        return MeshSourceFixture(Path(temporary.name))

    def assert_forged_rejected(self, fixture, verified) -> None:
        with self.assertRaises(VerifiedMeshSourceReaderError):
            fixture.load_forged(verified)

    def test_hash_path_and_region_size_tamper_are_rejected(self) -> None:
        fixture = self.fixture()
        mutations = (
            lambda rig: rig["attachments"][0].update(image_sha256="f" * 64),
            lambda rig: rig["attachments"][0].update(image_path="C:/outside.png"),
            lambda rig: _region(rig).update(size=[1, 1]),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self.assert_forged_rejected(fixture, fixture.with_rig(mutate))

    def test_mesh_vertex_uv_and_canvas_raster_bounds_are_rejected(self) -> None:
        fixture = self.fixture()

        def vertex(rig):
            mesh = _mesh(rig)
            mesh["vertices"][0][0] = 100_000

        def uv(rig):
            _mesh(rig)["uvs"][0][0] = 1.01

        def canvas(rig):
            rig["attachments"][0]["canvas_offset_xy"] = [-1, 0]

        for mutate in (vertex, uv, canvas):
            with self.subTest(mutate=mutate):
                self.assert_forged_rejected(fixture, fixture.with_rig(mutate))

    def test_png_profile_and_decoded_dimension_tamper_are_rejected(self) -> None:
        fixture = self.fixture()
        region = _region(fixture.verified.rig)
        path = region["image_path"]
        tiny = encode_rgba_png(RgbaImage(1, 1, b"\0\0\0\0"))

        changed = fixture.with_rig(
            lambda rig: _region(rig).update(
                image_sha256=hashlib.sha256(tiny).hexdigest()
            )
        )
        pngs = changed.source_pngs
        pngs[path] = tiny
        self.assert_forged_rejected(
            fixture, replace(changed, _source_png_items=tuple(sorted(pngs.items())))
        )

        invalid = fixture.verified.source_pngs
        invalid[path] = b"not-a-png"
        changed = fixture.with_rig(
            lambda rig: _region(rig).update(
                image_sha256=hashlib.sha256(invalid[path]).hexdigest()
            )
        )
        self.assert_forged_rejected(
            fixture, replace(changed, _source_png_items=tuple(sorted(invalid.items())))
        )

    def test_missing_extra_and_case_alias_snapshot_inventory_are_rejected(self) -> None:
        fixture = self.fixture()
        original = fixture.verified.source_pngs
        first = next(iter(original))
        cases = []
        missing = dict(original)
        missing.pop(first)
        cases.append(missing)
        cases.append({**original, "layers/unclaimed.png": original[first]})
        cases.append({**original, first.upper(): original[first]})
        for pngs in cases:
            with self.subTest(paths=sorted(pngs)):
                self.assert_forged_rejected(fixture, fixture.with_source_pngs(pngs))

    def test_unsafe_attachment_aliases_and_explicit_identity_aliases_are_rejected(self) -> None:
        fixture = self.fixture()
        path_mutations = (
            lambda rig: rig["attachments"][0].update(image_path="../escape.png"),
            lambda rig: rig["attachments"][0].update(image_path="layers\\escape.png"),
            lambda rig: rig["attachments"][0].update(
                image_path=rig["attachments"][0]["image_path"].upper()
            ),
            lambda rig: rig["attachments"][1].update(
                source_layer_ids=rig["attachments"][0]["source_layer_ids"],
                image_path=rig["attachments"][0]["image_path"],
            ),
        )
        for mutate in path_mutations:
            with self.subTest(mutate=mutate):
                self.assert_forged_rejected(fixture, fixture.with_rig(mutate))

        for values in (
            ("../project", fixture.verified.rig_sha256, fixture.verified.bundle_sha256),
            (fixture.bundle.project_id, "latest", fixture.verified.bundle_sha256),
            (fixture.bundle.project_id, fixture.verified.rig_sha256, "latest"),
        ):
            with self.subTest(values=values), self.assertRaises(
                VerifiedMeshSourceReaderError
            ):
                fixture.reader.load(*values)

    def test_state_root_symlink_alias_is_rejected_when_supported(self) -> None:
        fixture = self.fixture()
        alias = fixture.bundle.state.parent / "state-alias"
        try:
            alias.symlink_to(fixture.bundle.state, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"directory symlink unavailable: {exc}")
        try:
            with self.assertRaises(VerifiedMeshSourceReaderError):
                VerifiedMeshSourceReader(alias).load(
                    fixture.bundle.project_id,
                    fixture.verified.rig_sha256,
                    fixture.verified.bundle_sha256,
                )
        finally:
            if alias.exists() or alias.is_symlink():
                alias.unlink()

    def test_opened_source_file_identity_drift_is_rejected(self) -> None:
        fixture = self.fixture()
        from autospine_workbench import rig_bundle_integrity

        original = rig_bundle_integrity.os.fstat
        calls = 0

        def drifting(file_descriptor):
            nonlocal calls
            calls += 1
            value = original(file_descriptor)
            if calls != 2:
                return value
            return SimpleNamespace(
                st_mode=value.st_mode,
                st_size=value.st_size,
                st_mtime_ns=value.st_mtime_ns,
                st_dev=value.st_dev,
                st_ino=value.st_ino + 1,
            )

        with (
            patch.object(rig_bundle_integrity.os, "fstat", side_effect=drifting),
            self.assertRaises(VerifiedMeshSourceReaderError),
        ):
            fixture.load()


def _region(rig):
    return next(item for item in rig["attachments"] if item["type"] == "region")


def _mesh(rig):
    return next(item for item in rig["attachments"] if item["type"] == "mesh")


def _canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":"))


def _tree_snapshot(root: Path):
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


if __name__ == "__main__":
    unittest.main()
