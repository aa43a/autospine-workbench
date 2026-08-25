"""Offline command integration tests."""

from __future__ import annotations

from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from autospine_workbench.cli import _analyze_joints  # noqa: E402
from autospine_workbench.artifact_store import (  # noqa: E402
    ArtifactStoreError,
    ImmutableJsonArtifactStore,
)
from autospine_workbench.pose_geometry_limb_provider import (  # noqa: E402
    PoseGeometryLimbProvider,
)
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from tests.png_helpers import write_rgba  # noqa: E402
from tests.test_project_store import StoreFixture  # noqa: E402


TRANSPARENT = (0, 0, 0, 0)
VISIBLE = (50, 60, 70, 255)


class JointAnalysisCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.fixture = StoreFixture(Path(self.directory.name))
        self.fixture.audit["canvas"] = [100, 100]
        layer = self.fixture.audit["layers"][0]
        layer["name"] = "hand-l"
        layer["bbox"] = [10, 20, 30, 40]
        layer["width"] = 20
        layer["height"] = 20
        self.fixture.write_audit()
        write_rgba(self.fixture.composite, [[VISIBLE]])
        write_rgba(self.fixture.embedded, [[VISIBLE]])
        rows = [[TRANSPARENT for _ in range(20)] for _ in range(20)]
        for y in range(4, 16):
            for x in range(2, 12):
                rows[y][x] = VISIBLE
        write_rgba(self.fixture.layer_image, rows)
        self.pose_path = Path(self.directory.name) / "pose.json"
        self.pose_path.write_text(json.dumps(self._pose_document()), encoding="utf-8")

    def tearDown(self) -> None:
        self.directory.cleanup()

    def _pose_document(self) -> dict:
        composite_sha = hashlib.sha256(self.fixture.composite.read_bytes()).hexdigest()
        return {
            "format": "autospine-pose-observations",
            "format_version": 1,
            "project_id": "fixture-project",
            "source": {
                "image_kind": "composite",
                "image_sha256": composite_sha,
                "canvas_size": [100, 100],
            },
            "detector": {
                "id": "fixture-pose",
                "version": "1",
                "model_revision": "fixture-model-revision",
                "config_sha256": "d" * 64,
                "runtime": "unittest",
            },
            "subject": {
                "detected_count": 1,
                "selected_index": 0,
                "selection_method": "single",
            },
            "coordinate_system": {
                "origin": "top_left",
                "x_axis": "right",
                "y_axis": "down",
                "units": "pixel",
                "side_naming": "character_side",
            },
            "joints": {
                "elbow.left": {
                    "xy": [8, 25],
                    "detector_score": 0.8,
                    "visibility": "visible",
                }
            },
        }

    def test_pose_alpha_cli_publishes_a_valid_content_addressed_artifact(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            status = _analyze_joints(
                "fixture-project",
                self.fixture.workspace,
                self.fixture.state,
                provider_name="pose-alpha",
                pose_path=self.pose_path,
                alpha_threshold=8,
            )
        response = json.loads(output.getvalue())
        self.assertEqual(0, status)
        self.assertTrue(response["ok"])
        self.assertEqual("pose-alpha-limb-fusion", response["provider"])
        artifact = Path(response["artifact_path"])
        pose_artifact = Path(response["pose_artifact_path"])
        self.assertTrue(artifact.is_file())
        self.assertTrue(pose_artifact.is_file())
        self.assertEqual(response["artifact_sha256"], artifact.stem)
        self.assertEqual(response["pose_artifact_sha256"], pose_artifact.stem)

    def test_pose_geometry_publishes_three_bound_artifacts_in_provenance_order(self) -> None:
        status, response = self._analyze("pose-geometry")

        self.assertEqual(0, status)
        self.assertEqual("pose-alpha-geometry-limb", response["provider"])
        self.assertEqual(
            ["pose_observations", "alpha_geometry_evidence", "joint_candidates"],
            list(response["artifacts"]),
        )
        for identity in response["artifacts"].values():
            path = Path(identity["path"])
            self.assertTrue(path.is_file())
            self.assertEqual(identity["sha256"], path.stem)

        geometry_sha = response["geometry_artifact_sha256"]
        candidates = json.loads(
            Path(response["joint_candidate_artifact_path"]).read_text(encoding="utf-8")
        )
        geometry_refs = [
            evidence["source_ref"]
            for joint in candidates["joints"].values()
            for candidate in joint["candidates"]
            for evidence in candidate["evidence"]
            if evidence["kind"]
            in {"layer_alpha", "contact_geometry", "kinematic_residual"}
        ]
        self.assertTrue(geometry_refs)
        self.assertTrue(all(
            ref.startswith(f"alpha-geometry-evidence:{geometry_sha}#")
            for ref in geometry_refs
        ))

    def test_pose_geometry_rejects_missing_or_invalid_detector_without_publication(self) -> None:
        with self.subTest("missing pose input"):
            status, response = self._analyze("pose-geometry", pose_path=None)
            self.assertEqual(2, status)
            self.assertIn("requires --pose-observations", response["error"])
            self.assertFalse((self.fixture.state / "analysis").exists())

        document = self._pose_document()
        document.pop("detector")
        self.pose_path.write_text(json.dumps(document), encoding="utf-8")
        with self.subTest("invalid detector contract"):
            status, response = self._analyze("pose-geometry")
            self.assertEqual(2, status)
            self.assertIn("missing required fields", response["error"])
            self.assertFalse((self.fixture.state / "analysis").exists())

    def test_geometry_publication_failure_keeps_upstream_and_blocks_downstream(self) -> None:
        published_kinds: list[str] = []
        original_publish = ImmutableJsonArtifactStore.publish

        def publish_until_geometry(store, kind, project_id, document):
            published_kinds.append(kind)
            if kind == "alpha-geometry-evidence":
                raise ArtifactStoreError("injected geometry publication failure")
            return original_publish(store, kind, project_id, document)

        with patch.object(ImmutableJsonArtifactStore, "publish", new=publish_until_geometry):
            status, response = self._analyze("pose-geometry")

        self.assertEqual(2, status)
        self.assertIn("injected geometry publication failure", response["error"])
        self.assertEqual(
            ["pose-observations", "alpha-geometry-evidence"], published_kinds
        )
        analysis = self.fixture.state / "analysis" / "fixture-project"
        self.assertEqual(1, len(list((analysis / "pose-observations").glob("*.json"))))
        self.assertFalse((analysis / "alpha-geometry-evidence").exists())
        self.assertFalse((analysis / "joint-candidates").exists())

    def test_candidate_publication_failure_keeps_both_validated_inputs(self) -> None:
        published_kinds: list[str] = []
        original_publish = ImmutableJsonArtifactStore.publish

        def publish_until_candidates(store, kind, project_id, document):
            published_kinds.append(kind)
            if kind == "joint-candidates":
                raise ArtifactStoreError("injected candidate publication failure")
            return original_publish(store, kind, project_id, document)

        with patch.object(
            ImmutableJsonArtifactStore, "publish", new=publish_until_candidates
        ):
            status, response = self._analyze("pose-geometry")

        self.assertEqual(2, status)
        self.assertIn("injected candidate publication failure", response["error"])
        self.assertEqual(
            ["pose-observations", "alpha-geometry-evidence", "joint-candidates"],
            published_kinds,
        )
        analysis = self.fixture.state / "analysis" / "fixture-project"
        for kind in ("pose-observations", "alpha-geometry-evidence"):
            self.assertEqual(1, len(list((analysis / kind).glob("*.json"))))
        self.assertFalse((analysis / "joint-candidates").exists())

    def test_invalid_geometry_fragments_are_rejected_before_any_publication(self) -> None:
        original_analyze = PoseGeometryLimbProvider.analyze
        cases = (
            ("wrong sha", "layer_alpha", f"alpha-geometry-evidence:{'f' * 64}#layers/stale"),
            ("wrong path", "layer_alpha", "{prefix}paths/missing"),
            ("wrong contact", "contact_geometry", "{prefix}contacts/missing"),
            (
                "wrong component",
                "layer_alpha",
                "{prefix}layers/{layer_id}/components/999999",
            ),
        )
        for label, kind, reference_template in cases:
            def analyze_with_invalid_reference(
                provider, project, *, evidence_kind=kind, template=reference_template
            ):
                bundle = original_analyze(provider, project)
                target = next(
                    evidence
                    for joint in bundle.joint_candidate_document["joints"].values()
                    for candidate in joint["candidates"]
                    for evidence in candidate["evidence"]
                    if evidence["kind"] == "layer_alpha"
                )
                digest = canonical_sha256(bundle.geometry_document)
                target["kind"] = evidence_kind
                target["source_ref"] = template.format(
                    prefix=f"alpha-geometry-evidence:{digest}#",
                    layer_id=bundle.geometry_document["layers"][0]["layer_id"],
                )
                return bundle

            with self.subTest(label), patch.object(
                PoseGeometryLimbProvider,
                "analyze",
                new=analyze_with_invalid_reference,
            ):
                status, response = self._analyze("pose-geometry")
                self.assertEqual(2, status)
                self.assertIn("geometry", response["error"].lower())
        self.assertFalse((self.fixture.state / "analysis").exists())

    def test_provider_specific_arguments_fail_without_publishing(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            status = _analyze_joints(
                "fixture-project",
                self.fixture.workspace,
                self.fixture.state,
                provider_name="pose-alpha",
            )
        self.assertEqual(2, status)
        self.assertFalse(json.loads(output.getvalue())["ok"])

    def _analyze(
        self, provider: str, *, pose_path: Path | None | object = ...
    ) -> tuple[int, dict]:
        selected_pose = self.pose_path if pose_path is ... else pose_path
        output = io.StringIO()
        with redirect_stdout(output):
            status = _analyze_joints(
                "fixture-project",
                self.fixture.workspace,
                self.fixture.state,
                provider_name=provider,
                pose_path=selected_pose,
                alpha_threshold=8,
            )
        return status, json.loads(output.getvalue())


if __name__ == "__main__":
    unittest.main()
