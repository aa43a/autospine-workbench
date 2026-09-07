"""Raw detector documents stay immutable, source-bound, and unapproved."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest

from tests.test_pose_observations import observation_fixture
from autospine_workbench.benchmark.pose_source import KIND, ingest_pose, read_pose
from autospine_workbench.resolved_project import canonical_sha256


def candidate():
    return {"schema": "autospine.benchmark-semantic-candidates/v1", "authority": "none",
            "character_id": "sample-a", "composite_sha256": "a"*64, "canvas": [100, 200]}


class PoseSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.state = self.root / "state"
        self.path = self.root / "pose.json"

    def write(self, value):
        self.path.write_text(json.dumps(value), encoding="utf-8")
        return self.path

    def test_v1_ingest_preserves_document_and_idempotent_exact_read(self):
        value = observation_fixture(); self.write(value)
        raw = self.path.read_bytes()
        result = ingest_pose(self.state, candidate(), self.path)
        self.assertEqual(result.document, value)
        self.assertEqual(self.path.read_bytes(), raw)
        self.assertNotIn("authority", result.document)
        self.assertEqual(result.document_sha256, canonical_sha256(value))
        second = ingest_pose(self.state, candidate(), self.path)
        self.assertEqual(second, result)
        self.assertEqual(read_pose(self.state, candidate(), result.document_sha256), result)
        self.assertEqual(len(list(self.state.rglob("*.json"))), 1)

    def test_v2_adapter_is_preserved(self):
        value = observation_fixture(); value["format_version"] = 2
        value["adapter"] = {"id": "coco17-limb-adapter", "version": "1",
                            "input_format": "autospine-coco17-detections/v1",
                            "input_document_sha256": "d"*64, "input_side_naming": "coco_character_side",
                            "coordinate_transform": "identity", "side_mapping": "as_reported",
                            "view_orientation": "front", "mirror_state": "not_mirrored",
                            "float_precision_decimals": 6}
        result = ingest_pose(self.state, candidate(), self.write(value))
        self.assertEqual(result.document, value)
        self.assertEqual(result.adapter, value["adapter"])

    def test_binding_invalid_numbers_and_unknown_authority_fail_before_publish(self):
        mutations = [lambda v: v.update(project_id="another"),
                     lambda v: v.update(format_version=True),
                     lambda v: v["source"].update(image_sha256="b"*64),
                     lambda v: v["source"].update(canvas_size=[100, 201]),
                     lambda v: v.update(authority="human"),
                     lambda v: v["joints"]["elbow.left"].update(xy=[10**1000, 0]),
                     lambda v: v["joints"]["elbow.left"].update(detector_score=float("nan")),
                     lambda v: v["joints"]["elbow.left"].update(xy=[True, 0])]
        for mutate in mutations:
            value = observation_fixture(); mutate(value)
            with self.subTest(mutate=mutate), self.assertRaisesRegex(ValueError, "benchmark_pose_"):
                ingest_pose(self.state, candidate(), self.write(value))
        self.assertFalse(self.state.exists())

    def test_duplicate_keys_size_limit_and_bad_candidate(self):
        for raw in ('{"format":1,"format":2}', " " * 1_000_001):
            self.path.write_text(raw, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "benchmark_pose_"):
                ingest_pose(self.state, candidate(), self.path)
        self.write(observation_fixture())
        bad = candidate(); bad["canvas"] = [10**1000, 200]
        with self.assertRaisesRegex(ValueError, "benchmark_pose_"):
            ingest_pose(self.state, bad, self.path)

    def test_hardlinked_input_and_stored_artifact_rejected(self):
        self.write(observation_fixture()); alias = self.root / "alias.json"
        os.link(self.path, alias)
        with self.assertRaisesRegex(ValueError, "benchmark_pose_"):
            ingest_pose(self.state, candidate(), self.path)
        alias.unlink()
        result = ingest_pose(self.state, candidate(), self.path)
        stored = self.state / "analysis" / "sample-a" / KIND / (result.document_sha256 + ".json")
        os.link(stored, alias)
        for action in (lambda: read_pose(self.state, candidate(), result.document_sha256),
                       lambda: ingest_pose(self.state, candidate(), self.path)):
            with self.assertRaisesRegex(ValueError, "benchmark_pose_"): action()

    def test_tampered_exact_artifact_rejected(self):
        result = ingest_pose(self.state, candidate(), self.write(observation_fixture()))
        stored = self.state / "analysis" / "sample-a" / KIND / (result.document_sha256 + ".json")
        modified = deepcopy(result.document); modified["joints"]["elbow.left"]["xy"] = [30, 50]
        stored.write_text(json.dumps(modified), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "benchmark_pose_"):
            read_pose(self.state, candidate(), result.document_sha256)

    def test_alias_directory_and_file_rejected(self):
        self.write(observation_fixture()); alias = self.root / "linked-pose.json"
        try: alias.symlink_to(self.path)
        except OSError as exc: self.skipTest(f"Symlink unavailable: {exc}")
        self.addCleanup(alias.unlink, missing_ok=True)
        with self.assertRaisesRegex(ValueError, "benchmark_pose_"):
            ingest_pose(self.state, candidate(), alias)
        destination = self.root / "other"; destination.mkdir()
        self.state.symlink_to(destination, target_is_directory=True)
        self.addCleanup(self.state.unlink, missing_ok=True)
        with self.assertRaisesRegex(ValueError, "benchmark_pose_"):
            ingest_pose(self.state, candidate(), self.path)


if __name__ == "__main__":
    unittest.main()
