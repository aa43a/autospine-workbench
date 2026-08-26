"""Application-service tests for exact-read P10 candidates."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.idle_behavior_candidate_validation import (  # noqa: E402
    idle_behavior_candidates_sha256,
)
from autospine_workbench.p10_candidate_commands import (  # noqa: E402
    P10CandidateCommandError,
    compile_idle_behavior_candidates_command,
)
from tests.p10_candidate_helpers import P10PersistedFixture  # noqa: E402
from tests.p9_v2_helpers import tree  # noqa: E402


class P10CandidatePersistedReaderTests(unittest.TestCase):
    """Exercise every production reader against one persisted exact chain."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = P10PersistedFixture(Path(cls.temporary.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def compile(self, **changes):
        values = {**self.fixture.command_kwargs, **changes}
        return compile_idle_behavior_candidates_command(
            self.fixture.state,
            self.fixture.mesh.project_id,
            **values,
        )

    def test_success_replays_exact_readers_and_writes_nothing(self):
        before = tree(self.fixture.state)
        first = self.compile()
        second = self.compile()
        self.assertEqual(before, tree(self.fixture.state))
        self.assertEqual(first.document, second.document)
        self.assertEqual(
            idle_behavior_candidates_sha256(first.document),
            first.idle_behavior_candidates_sha256,
        )
        self.assertEqual(
            (
                "layer-manifests",
                "mesh-rig-ir",
                "motion-instances",
                "reviewed-motion-instances",
            ),
            tuple(path.parent.name if index == 0 else path.parent.parent.name
                  for index, path in enumerate(first.input_paths)),
        )

    def test_every_cross_wired_sha_fails_closed_without_writes(self):
        values = self.fixture.command_kwargs
        identities = list(values.values())
        before = tree(self.fixture.state)
        for field, original in values.items():
            stale = next(value for value in identities if value != original)
            with self.subTest(field=field), self.assertRaises(
                P10CandidateCommandError
            ):
                self.compile(**{field: stale})
            self.assertEqual(before, tree(self.fixture.state))

    def test_verified_p9_identity_mismatch_fails_replay_boundary(self):
        mismatched = replace(
            self.fixture.reviewed, run_sha256="f" * 64
        )
        before = tree(self.fixture.state)
        with patch(
            "autospine_workbench.p10_candidate_commands."
            "VerifiedReviewedMotionBundleReader"
        ) as reader, self.assertRaisesRegex(
            P10CandidateCommandError, "differs from its P9 replay"
        ):
            reader.return_value.load.return_value = mismatched
            self.compile()
        reader.return_value.load.assert_called_once_with(
            self.fixture.mesh.project_id,
            self.fixture.reviewed.motion_instance_v2_sha256,
            self.fixture.reviewed.bundle_sha256,
            mesh_bundle=unittest.mock.ANY,
            retarget_bundle=unittest.mock.ANY,
        )
        self.assertEqual(before, tree(self.fixture.state))

    def test_verified_p9_document_bytes_mismatch_fails_replay_boundary(self):
        items = list(self.fixture.reviewed._document_items)
        items[0] = (items[0][0], items[0][1] + b" ")
        mismatched = replace(
            self.fixture.reviewed, _document_items=tuple(items)
        )
        before = tree(self.fixture.state)
        with patch(
            "autospine_workbench.p10_candidate_commands."
            "VerifiedReviewedMotionBundleReader"
        ) as reader, self.assertRaisesRegex(
            P10CandidateCommandError, "differs from its P9 replay"
        ):
            reader.return_value.load.return_value = mismatched
            self.compile()
        self.assertEqual(before, tree(self.fixture.state))


if __name__ == "__main__":
    unittest.main()
