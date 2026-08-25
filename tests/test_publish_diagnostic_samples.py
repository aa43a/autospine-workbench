"""Fixture coverage for resolved-setup diagnostic publication."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest


from tests.png_helpers import write_rgba
from tests.test_project_store import StoreFixture
from tools.publish_diagnostic_samples import (
    LIMB_JOINT_IDS,
    build_diagnostic_pose,
    publish_diagnostic_project,
)


TRANSPARENT = (0, 0, 0, 0)
VISIBLE = (50, 60, 70, 255)


class DiagnosticSamplePublicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.fixture = StoreFixture(Path(self.directory.name))
        self.fixture.audit["canvas"] = [100, 100]
        layer = self.fixture.audit["layers"][0]
        layer.update({
            "name": "hand-l",
            "bbox": [10, 20, 30, 40],
            "width": 20,
            "height": 20,
        })
        self.fixture.write_audit()
        write_rgba(self.fixture.composite, [[VISIBLE]])
        write_rgba(self.fixture.embedded, [[VISIBLE]])
        rows = [[TRANSPARENT for _ in range(20)] for _ in range(20)]
        for y in range(4, 16):
            for x in range(2, 12):
                rows[y][x] = VISIBLE
        write_rgba(self.fixture.layer_image, rows)

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_pose_is_explicitly_a_zero_score_resolved_setup_prior(self) -> None:
        pose = build_diagnostic_pose(self.fixture.store(), "fixture-project")

        self.assertEqual(1, pose["format_version"])
        self.assertEqual("resolved-setup-prior", pose["detector"]["id"])
        self.assertEqual("diagnostic-only", pose["detector"]["runtime"])
        self.assertEqual(
            "resolved-setup-prior/diagnostic-only",
            pose["detector"]["model_revision"],
        )
        self.assertEqual(set(LIMB_JOINT_IDS), set(pose["joints"]))
        self.assertTrue(all(
            joint["detector_score"] == 0.0 and joint["visibility"] == "unknown"
            for joint in pose["joints"].values()
        ))

    def test_repeat_publication_is_stable_and_does_not_change_revision(self) -> None:
        store = self.fixture.store()
        revision_before = store.get_project("fixture-project")["overrides"]["revision"]

        first = publish_diagnostic_project(
            self.fixture.workspace, self.fixture.state, "fixture-project"
        )
        second = publish_diagnostic_project(
            self.fixture.workspace, self.fixture.state, "fixture-project"
        )

        self.assertTrue(first["diagnostic_only"])
        self.assertTrue(first["not_model_accuracy"])
        self.assertEqual(first["pose_document_sha256"], second["pose_document_sha256"])
        self.assertEqual(
            {key: value["sha256"] for key, value in first["artifacts"].items()},
            {key: value["sha256"] for key, value in second["artifacts"].items()},
        )
        self.assertEqual(
            ["pose_observations", "alpha_geometry_evidence", "joint_candidates"],
            list(first["artifacts"]),
        )
        for identity in first["artifacts"].values():
            path = Path(identity["path"])
            self.assertTrue(path.is_file())
            self.assertEqual(identity["sha256"], path.stem)
            json.loads(path.read_text(encoding="utf-8"))
        revision_after = store.get_project("fixture-project")["overrides"]["revision"]
        self.assertEqual(revision_before, revision_after)
        self.assertFalse((self.fixture.state / "overrides").exists())


if __name__ == "__main__":
    unittest.main()
