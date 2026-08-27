"""Exact-address and zero-write tests for P10.5a seam commands."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from autospine_workbench.manifest_bundle import (
    LayerManifestBundleError,
    LayerManifestBundleReader,
)
from autospine_workbench.mesh_bundle_reader import (
    VerifiedMeshBundleReaderError,
)
from autospine_workbench.seam_anchor_candidate_commands import (
    SeamAnchorCandidateCommandError,
    compile_seam_anchor_candidates_command,
)
from autospine_workbench.seam_anchor_candidates import (
    compile_seam_anchor_candidates,
)
from tests.p10_candidate_helpers import P10PersistedFixture
from tests.p9_v2_helpers import tree


class SeamAnchorCandidateCommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = P10PersistedFixture(Path(cls.temporary.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def compile(self, **changes):
        fixture = self.fixture
        values = {
            "layer_manifest_sha256": fixture.layer_manifest_sha256,
            "p3_rig_sha256": fixture.mesh.rig_sha256,
            "p3_bundle_sha256": fixture.mesh.bundle_sha256,
            **changes,
        }
        return compile_seam_anchor_candidates_command(
            fixture.state, fixture.mesh.project_id, **values
        )

    def test_exact_replay_matches_pure_compiler_and_writes_nothing(self):
        fixture = self.fixture
        manifest = LayerManifestBundleReader(fixture.state).load(
            fixture.mesh.project_id, fixture.layer_manifest_sha256
        )
        expected = compile_seam_anchor_candidates(
            manifest.manifest, fixture.mesh
        )
        before = tree(fixture.state)
        first, second = self.compile(), self.compile()
        self.assertEqual(before, tree(fixture.state))
        self.assertEqual(first, second)
        self.assertEqual(expected.sha256,
                         first.seam_anchor_candidates_sha256)
        self.assertEqual(expected.document, first.document)
        self.assertEqual((manifest.path, fixture.mesh.path),
                         first.input_paths)

        isolated = first.document
        isolated.clear()
        self.assertEqual(expected.document, first.document)

    def test_each_exact_address_rejects_cross_wiring_without_writes(self):
        before = tree(self.fixture.state)
        for field in (
            "layer_manifest_sha256", "p3_rig_sha256",
            "p3_bundle_sha256",
        ):
            with self.subTest(field=field), self.assertRaises(
                SeamAnchorCandidateCommandError
            ):
                self.compile(**{field: "f" * 64})
            self.assertEqual(before, tree(self.fixture.state))

    def test_reader_failures_share_one_command_boundary(self):
        errors = (
            (
                "LayerManifestBundleReader",
                LayerManifestBundleError(r"C:\private\manifest"),
            ),
            (
                "VerifiedMeshBundleReader",
                VerifiedMeshBundleReaderError(r"C:\private\mesh"),
            ),
        )
        for reader_name, error in errors:
            with self.subTest(reader=reader_name), patch(
                "autospine_workbench.seam_anchor_candidate_commands."
                + reader_name
            ) as reader, self.assertRaisesRegex(
                SeamAnchorCandidateCommandError,
                "Seam-anchor candidate command failed",
            ) as raised:
                reader.return_value.load.side_effect = error
                self.compile()
            self.assertIs(error, raised.exception.__cause__)
            self.assertNotIn("private", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
