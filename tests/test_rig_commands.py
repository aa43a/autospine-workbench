"""End-to-end CLI coverage for P2 compile, probe, and bundle publication."""

from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.cli import main as cli_main  # noqa: E402
from autospine_workbench.layer_manifest import (  # noqa: E402
    LayerManifestBuilder,
    LayerManifestBundleStore,
)
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from tests.png_helpers import write_rgba  # noqa: E402
from tests.test_project_store import StoreFixture  # noqa: E402


VISIBLE = (40, 90, 160, 220)


class RigCommandIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.fixture = StoreFixture(Path(self.temp.name))
        self.fixture.audit["canvas"] = [100, 100]
        layer = self.fixture.audit["layers"][0]
        layer["bbox"] = [10, 20, 30, 40]
        layer["width"] = 20
        layer["height"] = 20
        layer["alpha_nonzero"] = 400
        layer["alpha_perceptible"] = 400
        layer["alpha_opaque"] = 0
        layer["component_areas_top5"] = [400]
        self.fixture.write_audit()
        write_rgba(self.fixture.composite, [[VISIBLE]])
        write_rgba(self.fixture.embedded, [[VISIBLE]])
        write_rgba(self.fixture.layer_image, [[VISIBLE] * 20 for _ in range(20)])
        self._review_project()
        self.manifest_sha = self._publish_manifest()

    def _review_project(self) -> None:
        store = self.fixture.store()
        project = store.get_project("fixture-project")
        layer = project["layers"][0]
        store.save_overrides(
            "fixture-project",
            {
                "base_revision": 0,
                "joint_overrides": {
                    joint["id"]: {
                        "x": joint["x"],
                        "y": joint["y"],
                        "reason": "reviewed P2 fixture setup",
                    }
                    for joint in project["skeleton"]["joints"]
                },
                "layer_overrides": {
                    layer["id"]: {
                        "canonical_role": "body.torso",
                        "side": "center",
                        "disposition": "keep",
                        "visible": True,
                        "pivot_xy": layer["pivot_xy"],
                        "notes": "reviewed region fixture",
                    }
                },
                "notes": "P2 fixture review",
            },
        )
        reviewed = self.fixture.store().get_project("fixture-project")
        self.assertEqual("ready", reviewed["resolved"]["qa"]["status"])

    def _publish_manifest(self) -> str:
        store = self.fixture.store()
        project = store.get_project("fixture-project")
        assets = {
            layer["id"]: store.resolve_asset("fixture-project", "layer", layer["id"])
            for layer in project["layers"]
        }
        manifest = LayerManifestBuilder().build(project, assets)
        self.assertEqual("passed", manifest["qa"]["status"])
        _, digest = LayerManifestBundleStore(self.fixture.state).publish(
            "fixture-project", manifest, assets
        )
        return digest

    def _run(self, *arguments: str) -> tuple[int, dict]:
        output = io.StringIO()
        with redirect_stdout(output):
            status = cli_main(list(arguments))
        return status, json.loads(output.getvalue())

    def test_compile_is_idempotent_and_publishes_all_passing_probes(self) -> None:
        arguments = (
            "compile-rig",
            "fixture-project",
            "--layer-manifest-sha256",
            self.manifest_sha,
            "--workspace",
            str(self.fixture.workspace),
            "--state-root",
            str(self.fixture.state),
        )
        first_status, first = self._run(*arguments)
        second_status, second = self._run(*arguments)
        self.assertEqual((0, 0), (first_status, second_status))
        self.assertTrue(first["ok"])
        self.assertEqual("passed", first["probe_status"])
        self.assertEqual(first["rig_sha256"], second["rig_sha256"])
        self.assertEqual(first["bundle_sha256"], second["bundle_sha256"])
        self.assertEqual(first["bundle_path"], second["bundle_path"])

        bundle = Path(first["bundle_path"])
        self.assertEqual(first["bundle_sha256"], bundle.name)
        self.assertEqual(first["rig_sha256"], bundle.parent.name)
        setup = json.loads((bundle / "setup-render.json").read_text(encoding="utf-8"))
        self.assertEqual(first["setup_render_sha256"], canonical_sha256(setup))
        self.assertEqual(first["setup_png_sha256"], setup["image"]["png_sha256"])
        self.assertEqual(first["setup_rgba_sha256"], setup["image"]["rgba_sha256"])
        report = json.loads((bundle / "probes.json").read_text(encoding="utf-8"))
        checks = {check["id"]: check for check in report["checks"]}
        self.assertTrue(checks["setup.pixel-reconstruction"]["metrics"]["exact"])
        self.assertLessEqual(
            checks["fk.setup-reconstruction"]["metrics"]["max_endpoint_error_px"],
            1e-6,
        )

    def test_run_probes_reports_a_tampered_setup_without_publishing_it(self) -> None:
        status, compiled = self._run(
            "compile-rig",
            "fixture-project",
            "--layer-manifest-sha256",
            self.manifest_sha,
            "--workspace",
            str(self.fixture.workspace),
            "--state-root",
            str(self.fixture.state),
        )
        self.assertEqual(0, status)
        rig = json.loads(
            (Path(compiled["bundle_path"]) / "rig.json").read_text(encoding="utf-8")
        )
        rig["attachments"][0]["canvas_offset_xy"][0] += 1
        tampered = Path(self.temp.name) / "tampered-rig.json"
        tampered.write_text(json.dumps(rig), encoding="utf-8")
        status, report = self._run(
            "run-probes",
            "fixture-project",
            str(tampered),
            "--layer-manifest-sha256",
            self.manifest_sha,
            "--workspace",
            str(self.fixture.workspace),
            "--state-root",
            str(self.fixture.state),
        )
        self.assertEqual(2, status)
        self.assertEqual("rejected", report["status"])
        checks = {check["id"]: check for check in report["checks"]}
        self.assertEqual("rejected", checks["setup.pixel-reconstruction"]["status"])


if __name__ == "__main__":
    unittest.main()
