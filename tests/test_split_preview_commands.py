"""Offline CLI coverage for immutable split-preview publication."""

from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
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

from autospine_workbench.artifact_store import (  # noqa: E402
    ArtifactStoreError,
    ImmutableJsonArtifactStore,
)
from autospine_workbench.cli import main as cli_main  # noqa: E402
from autospine_workbench.manifest_bundle import LayerManifestBundleReader  # noqa: E402
from autospine_workbench.split_preview_reader import SplitPreviewReader  # noqa: E402
from tests.png_helpers import write_rgba  # noqa: E402
from tests.test_project_store import StoreFixture  # noqa: E402


VISIBLE = (40, 90, 160, 220)


def authored_spec() -> dict:
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


class SplitPreviewCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.fixture = StoreFixture(Path(self.temp.name))

    def _configure_layers(self, count: int) -> None:
        self.fixture.audit["canvas"] = [8, 4]
        source = self.fixture.audit["layers"][0]
        source.update(
            name="legwear-a",
            bbox=[1, 0, 7, 4],
            width=6,
            height=4,
            alpha_nonzero=24,
            alpha_perceptible=24,
            alpha_opaque=0,
            component_count=1,
            component_areas_top5=[24],
        )
        layers = [source]
        paths = [self.fixture.layer_image]
        if count == 2:
            second_path = self.fixture.layer_dir / "01_legwear_b.png"
            second = deepcopy(source)
            second.update(
                traversal_index=1,
                index=1,
                name="legwear-b",
                crop_path=str(second_path),
            )
            layers.append(second)
            paths.append(second_path)
        self.fixture.audit["layers"] = layers
        self.fixture.audit.update(
            top_level_layers=count,
            pixel_layers=count,
            visible_pixel_layers=count,
        )
        self.fixture.write_audit()
        pixels = [[VISIBLE for _ in range(6)] for _ in range(4)]
        for path in paths:
            write_rgba(path, pixels)

    def _author_splits(self, count: int) -> list[str]:
        self._configure_layers(count)
        store = self.fixture.store()
        project = store.get_project("fixture-project")
        layer_ids = [layer["id"] for layer in project["layers"]]
        positions = {
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
                    joint_id: {"x": xy[0], "y": xy[1], "reason": "split preview"}
                    for joint_id, xy in positions.items()
                },
                "layer_overrides": {
                    layer_id: {
                        "canonical_role": "body.leg",
                        "side": "bilateral",
                        "disposition": "split_left_right",
                        "split_spec": authored_spec(),
                        "visible": True,
                        "notes": "authored split preview",
                    }
                    for layer_id in layer_ids
                },
                "notes": "publish split previews",
            },
        )
        return sorted(layer_ids)

    def _run(self) -> tuple[int, dict]:
        output = io.StringIO()
        arguments = [
            "publish-split-previews",
            "fixture-project",
            "--workspace",
            str(self.fixture.workspace),
            "--state-root",
            str(self.fixture.state),
        ]
        with redirect_stdout(output):
            status = cli_main(arguments)
        return status, json.loads(output.getvalue())

    def test_two_layer_publication_is_sorted_content_addressed_and_idempotent(self) -> None:
        expected_ids = self._author_splits(2)
        first_status, first = self._run()
        second_status, second = self._run()

        self.assertEqual((0, 0), (first_status, second_status))
        self.assertEqual(first, second)
        self.assertTrue(first["ok"])
        self.assertEqual(
            expected_ids,
            [item["layer_id"] for item in first["previews"]],
        )
        loaded_manifest = LayerManifestBundleReader(self.fixture.state).load(
            "fixture-project", first["manifest_sha256"]
        )
        self.assertEqual(first["manifest_sha256"], loaded_manifest.sha256)
        reader = SplitPreviewReader(self.fixture.state)
        for item in first["previews"]:
            loaded = reader.load(
                "fixture-project", item["split_artifact_sha256"]
            )
            self.assertEqual(item["layer_id"], loaded.document["layer_id"])
            self.assertEqual(first["manifest_sha256"], loaded.document["layer_manifest_sha256"])

    def test_no_authored_split_fails_before_publication(self) -> None:
        self._configure_layers(1)
        store = self.fixture.store()
        layer_id = store.get_project("fixture-project")["layers"][0]["id"]
        store.save_overrides(
            "fixture-project",
            {
                "base_revision": 0,
                "joint_overrides": {},
                "layer_overrides": {
                    layer_id: {
                        "canonical_role": "body.leg",
                        "side": "bilateral",
                        "disposition": "split_left_right",
                        "visible": True,
                        "notes": "split intent without authored specification",
                    }
                },
                "notes": "missing split_spec",
            },
        )
        status, response = self._run()

        self.assertEqual(2, status)
        self.assertFalse(response["ok"])
        self.assertIn("not a canonical authored split", response["error"].lower())
        self.assertFalse((self.fixture.state / "builds").exists())
        self.assertFalse((self.fixture.state / "analysis").exists())

    def test_partial_artifact_publication_never_claims_success(self) -> None:
        self._author_splits(2)
        original_publish = ImmutableJsonArtifactStore.publish
        calls = 0

        def fail_second(store, kind, project_id, document):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise ArtifactStoreError("injected preview publication failure")
            return original_publish(store, kind, project_id, document)

        with patch.object(ImmutableJsonArtifactStore, "publish", new=fail_second):
            status, response = self._run()

        self.assertEqual(2, status)
        self.assertEqual(False, response["ok"])
        self.assertIn("injected preview publication failure", response["error"])
        self.assertNotIn("manifest_sha256", response)
        self.assertNotIn("previews", response)
        self.assertTrue((self.fixture.state / "builds" / "fixture-project").is_dir())
        artifacts = list(
            (
                self.fixture.state
                / "analysis"
                / "fixture-project"
                / "split-previews"
            ).glob("*.json")
        )
        self.assertEqual(1, len(artifacts))


if __name__ == "__main__":
    unittest.main()
