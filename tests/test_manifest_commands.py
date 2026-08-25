"""End-to-end CLI coverage for Layer Manifest materialization."""

from __future__ import annotations

from contextlib import redirect_stdout
import io
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

from autospine_workbench import manifest_commands  # noqa: E402
from autospine_workbench.cli import main as cli_main  # noqa: E402
from autospine_workbench.layer_split_materializer import (  # noqa: E402
    LayerSplitMaterializationError,
)
from autospine_workbench.manifest_bundle import LayerManifestBundleReader  # noqa: E402
from tests.png_helpers import write_rgba  # noqa: E402
from tests.test_project_store import StoreFixture  # noqa: E402


VISIBLE = (40, 90, 160, 220)


class ManifestCommandIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.fixture = StoreFixture(Path(self.temp.name))
        self._configure_audit("topwear")

    def _configure_audit(self, name: str) -> None:
        self.fixture.audit["canvas"] = [8, 4]
        layer = self.fixture.audit["layers"][0]
        layer.update(
            name=name,
            bbox=[1, 0, 7, 4],
            width=6,
            height=4,
            alpha_nonzero=24,
            alpha_perceptible=24,
            alpha_opaque=0,
            component_count=1,
            component_areas_top5=[24],
        )
        self.fixture.write_audit()
        write_rgba(
            self.fixture.layer_image,
            [[VISIBLE for _ in range(6)] for _ in range(4)],
        )

    def _run(self) -> tuple[int, dict]:
        output = io.StringIO()
        arguments = [
            "materialize-manifest",
            "fixture-project",
            "--workspace",
            str(self.fixture.workspace),
            "--state-root",
            str(self.fixture.state),
        ]
        with redirect_stdout(output):
            status = cli_main(arguments)
        return status, json.loads(output.getvalue())

    def _review_split(self) -> str:
        self._configure_audit("legwear")
        store = self.fixture.store()
        project = store.get_project("fixture-project")
        layer_id = project["layers"][0]["id"]
        joint_positions = {
            "hip.left": (2, 0),
            "knee.left": (2, 2),
            "ankle.left": (2, 3),
            "hip.right": (5, 0),
            "knee.right": (5, 2),
            "ankle.right": (5, 3),
        }
        store.save_overrides(
            "fixture-project",
            {
                "base_revision": 0,
                "joint_overrides": {
                    joint_id: {"x": xy[0], "y": xy[1], "reason": "split fixture"}
                    for joint_id, xy in joint_positions.items()
                },
                "layer_overrides": {
                    layer_id: {
                        "canonical_role": "body.leg",
                        "side": "bilateral",
                        "disposition": "split_left_right",
                        "visible": True,
                        "notes": "reviewed split fixture",
                    }
                },
                "notes": "materialize split fixture",
            },
        )
        return layer_id

    def test_unsplit_publication_is_content_addressed_and_idempotent(self) -> None:
        first_status, first = self._run()
        second_status, second = self._run()

        self.assertEqual((0, 0), (first_status, second_status))
        self.assertTrue(first["ok"])
        self.assertEqual(first["manifest_sha256"], second["manifest_sha256"])
        self.assertEqual(first["bundle_path"], second["bundle_path"])
        loaded = LayerManifestBundleReader(self.fixture.state).load(
            "fixture-project", first["manifest_sha256"]
        )
        self.assertEqual(1, len(loaded.manifest["layers"]))

    def test_split_bundle_replays_after_temporary_assets_are_cleaned(self) -> None:
        parent_id = self._review_split()
        temporary_assets: list[Path] = []
        original = manifest_commands.materialize_bilateral_splits

        def capture_assets(project, assets, output_dir):
            result = original(project, assets, output_dir)
            temporary_assets.extend(
                path for layer_id, path in result.assets.items() if layer_id != parent_id
            )
            self.assertTrue(all(path.is_file() for path in temporary_assets))
            return result

        with patch.object(
            manifest_commands,
            "materialize_bilateral_splits",
            side_effect=capture_assets,
        ):
            status, response = self._run()

        self.assertEqual(0, status)
        self.assertTrue(temporary_assets)
        self.assertTrue(all(not path.exists() for path in temporary_assets))
        loaded = LayerManifestBundleReader(self.fixture.state).load(
            "fixture-project", response["manifest_sha256"]
        )
        expected = {parent_id, f"{parent_id}--left", f"{parent_id}--right"}
        self.assertEqual(expected, set(loaded.image_sizes))
        self.assertTrue(all(
            (loaded.path / "layers" / f"{item}.png").is_file()
            for item in expected
        ))

    def test_materializer_failure_returns_two_without_visible_bundle(self) -> None:
        temporary_roots: list[Path] = []

        def fail_materialization(_project, _assets, output_dir):
            temporary_roots.append(Path(output_dir))
            raise LayerSplitMaterializationError("injected split failure")

        with patch.object(
            manifest_commands,
            "materialize_bilateral_splits",
            side_effect=fail_materialization,
        ):
            status, response = self._run()

        self.assertEqual(2, status)
        self.assertFalse(response["ok"])
        self.assertIn("injected split failure", response["error"])
        self.assertTrue(all(not path.exists() for path in temporary_roots))
        self.assertFalse((self.fixture.state / "builds").exists())


if __name__ == "__main__":
    unittest.main()
