"""Focused exact-address P10 state-tree chain loader tests."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from autospine_workbench.idle_behavior_candidates import (
    compile_idle_behavior_candidates,
)
from autospine_workbench.manifest_bundle import LayerManifestBundleError
from autospine_workbench.mesh_bundle_reader import VerifiedMeshBundleReaderError
from autospine_workbench.motion_retarget_bundle_reader import (
    VerifiedMotionRetargetBundleReaderError,
)
from autospine_workbench.p10_candidate_commands import (
    compile_idle_behavior_candidates_command,
)
from autospine_workbench.p10_exact_chain import (
    P10ExactChainError,
    load_p10_exact_chain,
)
from autospine_workbench.reviewed_motion_bundle_integrity import (
    ReviewedMotionBundleIntegrityError,
)
from autospine_workbench.reviewed_motion_bundle_reader import (
    VerifiedReviewedMotionBundleReaderError,
)
from tests.p10_candidate_helpers import P10PersistedFixture
from tests.p9_v2_helpers import tree


class P10ExactChainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = P10PersistedFixture(Path(cls.temporary.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def load(self, **changes):
        fixture = self.fixture
        values = {**fixture.command_kwargs, **changes}
        return load_p10_exact_chain(
            fixture.state,
            fixture.mesh.project_id,
            **values,
        )

    def test_exact_result_is_deterministic_and_writes_nothing(self):
        fixture = self.fixture
        before = tree(fixture.state)
        first, second = self.load(), self.load()
        self.assertEqual(before, tree(fixture.state))
        self.assertEqual(first, second)
        self.assertEqual(fixture.mesh, first.mesh_bundle)
        self.assertEqual(fixture.retarget, first.retarget_bundle)
        self.assertEqual(fixture.reviewed, first.reviewed_bundle)
        self.assertEqual(fixture.mesh.project_id, first.reviewed_contract.project_id)
        self.assertEqual(
            fixture.reviewed.bundle_sha256,
            first.reviewed_contract.bundle_sha256,
        )
        self.assertEqual(
            (fixture.mesh.project_id, fixture.reviewed.clip_id),
            (first.manifest["project_id"], first.reviewed_contract.clip_id),
        )
        expected_manifest_path = (
            fixture.state / "builds" / fixture.mesh.project_id /
            "layer-manifests" / fixture.layer_manifest_sha256
        )
        self.assertTrue(first.input_paths[0].samefile(expected_manifest_path))
        self.assertEqual((
            fixture.mesh.path,
            fixture.retarget.path,
            fixture.reviewed.path,
        ), first.input_paths[1:])

    def test_each_of_seven_explicit_addresses_rejects_cross_wiring(self):
        values = self.fixture.command_kwargs
        identities = tuple(values.values())
        before = tree(self.fixture.state)
        for field, original in values.items():
            cross_wire = next(value for value in identities if value != original)
            with self.subTest(field=field), self.assertRaises(P10ExactChainError):
                self.load(**{field: cross_wire})
            self.assertEqual(before, tree(self.fixture.state))

    def test_reader_and_replay_errors_share_one_loader_error_boundary(self):
        cases = (
            (
                "LayerManifestBundleReader",
                LayerManifestBundleError("manifest-reader-failure"),
            ),
            (
                "VerifiedMeshBundleReader",
                VerifiedMeshBundleReaderError("mesh-reader-failure"),
            ),
            (
                "VerifiedMotionRetargetBundleReader",
                VerifiedMotionRetargetBundleReaderError(
                    "retarget-reader-failure"
                ),
            ),
            (
                "VerifiedReviewedMotionBundleReader",
                VerifiedReviewedMotionBundleReaderError(
                    "reviewed-reader-failure"
                ),
            ),
        )
        before = tree(self.fixture.state)
        for symbol, error in cases:
            with self.subTest(symbol=symbol), patch(
                f"autospine_workbench.p10_exact_chain.{symbol}"
            ) as reader:
                reader.return_value.load.side_effect = error
                with self.assertRaisesRegex(
                    P10ExactChainError, str(error)
                ) as raised:
                    self.load()
            self.assertIs(error, raised.exception.__cause__)
            self.assertEqual(before, tree(self.fixture.state))

        replay_error = ReviewedMotionBundleIntegrityError("replay-failure")
        with patch(
            "autospine_workbench.p10_exact_chain."
            "replay_verified_reviewed_motion_bundle",
            side_effect=replay_error,
        ), self.assertRaisesRegex(P10ExactChainError, "replay-failure") as raised:
            self.load()
        self.assertIs(replay_error, raised.exception.__cause__)
        self.assertEqual(before, tree(self.fixture.state))

    def test_candidate_command_output_and_hash_match_the_pure_compiler(self):
        fixture = self.fixture
        before = tree(fixture.state)
        chain = self.load()
        expected = compile_idle_behavior_candidates(
            chain.manifest,
            chain.mesh_bundle,
            chain.retarget_bundle,
            chain.reviewed_contract,
        )
        actual = compile_idle_behavior_candidates_command(
            fixture.state,
            fixture.mesh.project_id,
            **fixture.command_kwargs,
        )
        self.assertEqual(expected.document, actual.document)
        self.assertEqual(expected.sha256,
                         actual.idle_behavior_candidates_sha256)
        self.assertEqual(chain.input_paths, actual.input_paths)
        self.assertEqual(before, tree(fixture.state))


if __name__ == "__main__":
    unittest.main()
