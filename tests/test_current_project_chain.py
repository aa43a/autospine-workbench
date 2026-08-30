"""Current authoring-chain failure classification tests."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


WORKBENCH_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = WORKBENCH_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


from autospine_workbench.current_project_chain import (
    CurrentProjectChain,
    CurrentProjectChainChangedError,
    CurrentProjectChainUnavailableError,
    rebuild_current_project_chains,
    require_unchanged_current_project_chains,
)
from autospine_workbench.current_project_chain_cache import (
    clear_current_project_chain_cache,
)
from autospine_workbench.layer_manifest import (
    LayerManifestBuilder,
    LayerManifestError,
)
from autospine_workbench.project_store import ProjectStoreError
from tests.test_layer_manifest import project_fixture, write_png


class CurrentProjectChainTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_current_project_chain_cache()
        self.addCleanup(clear_current_project_chain_cache)

    def test_project_store_failure_is_unavailable_not_changed(self) -> None:
        self._assert_rebuild_unavailable(
            ProjectStoreError("persistent project-store failure")
        )

    def test_oserror_is_unavailable_not_changed(self) -> None:
        self._assert_rebuild_unavailable(
            OSError("persistent temporary-storage failure")
        )

    def _assert_rebuild_unavailable(self, failure: Exception) -> None:
        class Store:
            def get_project(self, _project_id):
                raise failure

        with self.assertRaises(CurrentProjectChainUnavailableError) as caught:
            rebuild_current_project_chains(Store(), ["sample-a"])
        self.assertIs(failure, caught.exception.__cause__)
        self.assertNotIsInstance(
            caught.exception, CurrentProjectChainChangedError,
        )

    def test_manifest_failure_is_unavailable_not_changed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            asset = Path(directory) / "arm.png"
            write_png(asset, 30, 40)
            project = project_fixture()

            class Store:
                def get_project(self, _project_id):
                    return project

                def resolve_asset(self, _project_id, _kind, _layer_id):
                    return asset

            failure = LayerManifestError("persistent manifest failure")
            with patch(
                "autospine_workbench.current_project_chain."
                "LayerManifestBuilder.build",
                side_effect=failure,
            ), self.assertRaises(
                CurrentProjectChainUnavailableError,
            ) as caught:
                rebuild_current_project_chains(Store(), [project["id"]])
        self.assertIs(failure, caught.exception.__cause__)
        self.assertNotIsInstance(
            caught.exception, CurrentProjectChainChangedError,
        )

    def test_only_complete_snapshot_difference_is_changed(self) -> None:
        first = CurrentProjectChain("sample-a", "a" * 64, "b" * 64)
        second = CurrentProjectChain("sample-a", "a" * 64, "c" * 64)
        require_unchanged_current_project_chains(
            {"sample-a": first}, {"sample-a": first},
        )
        with self.assertRaises(CurrentProjectChainChangedError):
            require_unchanged_current_project_chains(
                {"sample-a": first}, {"sample-a": second},
            )

    def test_runtime_input_identity_difference_is_changed(self) -> None:
        first = CurrentProjectChain(
            "sample-a", "a" * 64, "b" * 64, "c" * 64,
        )
        second = CurrentProjectChain(
            "sample-a", "a" * 64, "b" * 64, "d" * 64,
        )
        with self.assertRaises(CurrentProjectChainChangedError):
            require_unchanged_current_project_chains(
                {"sample-a": first}, {"sample-a": second},
            )

    def test_warm_rebuild_rehashes_source_but_reuses_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            asset = Path(directory) / "arm.png"
            write_png(asset, 30, 40)
            project = project_fixture()

            class Store:
                get_calls = 0

                def get_project(self, _project_id):
                    self.get_calls += 1
                    return project

                def resolve_asset(self, _project_id, _kind, _layer_id):
                    return asset

            store = Store()
            build_calls = 0
            asset_hashes = 0
            original_build = LayerManifestBuilder.build
            from autospine_workbench import current_project_chain_cache
            original_hash = current_project_chain_cache._sha256_path

            def build(instance, *args, **kwargs):
                nonlocal build_calls
                build_calls += 1
                return original_build(instance, *args, **kwargs)

            def hash_path(path):
                nonlocal asset_hashes
                if Path(path) == asset:
                    asset_hashes += 1
                return original_hash(path)

            with patch.object(
                LayerManifestBuilder, "build", new=build,
            ), patch.object(
                current_project_chain_cache, "_sha256_path", new=hash_path,
            ):
                first = rebuild_current_project_chains(store, [project["id"]])
                second = rebuild_current_project_chains(store, [project["id"]])
        self.assertEqual(first, second)
        self.assertEqual(2, store.get_calls)
        self.assertEqual(1, build_calls)
        self.assertEqual(3, asset_hashes)
        self.assertIsNotNone(first[project["id"]].input_identity_sha256)

    def test_runtime_algorithm_patch_cannot_reuse_cached_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            asset = Path(directory) / "arm.png"
            write_png(asset, 30, 40)
            project = project_fixture()

            class Store:
                def get_project(self, _project_id):
                    return project

                def resolve_asset(self, _project_id, _kind, _layer_id):
                    return asset

            build_calls = 0
            original_build = LayerManifestBuilder.build
            from autospine_workbench import layer_manifest
            original_deform = layer_manifest._deform_class

            def build(instance, *args, **kwargs):
                nonlocal build_calls
                build_calls += 1
                return original_build(instance, *args, **kwargs)

            with patch.object(LayerManifestBuilder, "build", new=build):
                first = rebuild_current_project_chains(Store(), [project["id"]])
                with patch.object(
                    layer_manifest,
                    "_deform_class",
                    side_effect=original_deform,
                ):
                    second = rebuild_current_project_chains(
                        Store(), [project["id"]],
                    )
        first_chain = first[project["id"]]
        second_chain = second[project["id"]]
        self.assertEqual(
            first_chain.layer_manifest_sha256,
            second_chain.layer_manifest_sha256,
        )
        self.assertNotEqual(
            first_chain.input_identity_sha256,
            second_chain.input_identity_sha256,
        )
        self.assertEqual(2, build_calls)

    def test_source_change_during_compile_is_not_cached(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            asset = Path(directory) / "arm.png"
            write_png(asset, 30, 40)
            original_bytes = asset.read_bytes()
            project = project_fixture()

            class Store:
                def get_project(self, _project_id):
                    return project

                def resolve_asset(self, _project_id, _kind, _layer_id):
                    return asset

            build_calls = 0
            original_build = LayerManifestBuilder.build

            def build(instance, *args, **kwargs):
                nonlocal build_calls
                build_calls += 1
                result = original_build(instance, *args, **kwargs)
                if build_calls == 1:
                    asset.write_bytes(b"changed-during-build")
                return result

            with patch.object(LayerManifestBuilder, "build", new=build):
                with self.assertRaises(CurrentProjectChainUnavailableError):
                    rebuild_current_project_chains(Store(), [project["id"]])
                asset.write_bytes(original_bytes)
                result = rebuild_current_project_chains(
                    Store(), [project["id"]],
                )
        self.assertEqual(2, build_calls)
        self.assertEqual(project["id"], result[project["id"]].project_id)


if __name__ == "__main__":
    unittest.main()
