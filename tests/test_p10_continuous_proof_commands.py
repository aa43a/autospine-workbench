"""Exact-command and concurrency tests for P10.4b2 continuous proof."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.body_sway_continuous_proof import (  # noqa: E402
    compile_body_sway_continuous_preview_proof,
)
from autospine_workbench.p10_continuous_proof_commands import (  # noqa: E402
    P10ContinuousProofCommandError,
    compile_body_sway_continuous_proof_command,
)
from tests.body_sway_runtime_capture_helpers import (  # noqa: E402
    fake_runtime_profile,
)
from tests.p10_review_admission_helpers import (  # noqa: E402
    P10ReviewAdmissionFixture,
)
from tests.p9_v2_helpers import tree  # noqa: E402


class P10ContinuousProofCommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.fixture = P10ReviewAdmissionFixture(cls.root)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def compile(self, fixture=None, **changes):
        current = fixture or self.fixture
        kwargs = {**current.command_kwargs, **changes}
        with fake_runtime_profile():
            return compile_body_sway_continuous_proof_command(
                *current.command_args, **kwargs
            )

    def test_command_is_deterministic_zero_write_and_path_free(self):
        before = tree(self.root)
        first = self.compile()
        second = self.compile()
        self.assertEqual(before, tree(self.root))
        self.assertEqual(first.continuous_proof_sha256,
                         second.continuous_proof_sha256)
        self.assertEqual(first.document, second.document)
        self.assertEqual(8, len(first.input_paths))
        self.assertNotIn("path", first.document)
        self.assertNotIn("path", _recursive_keys(first.document["problem"]))
        self.assertNotIn("path", _recursive_keys(first.document["segments"]))
        encoded = str(first.document)
        self.assertNotIn(str(self.root), encoded)
        self.assertNotIn("C:\\", encoded)
        self.assertEqual(
            first.amplitude_envelope_sha256,
            first.document["source"][
                "amplitude_envelope_candidate_sha256"
            ],
        )
        self.assertEqual("blocked", first.document["release_gate"]["status"])

    def test_head_change_during_proof_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = P10ReviewAdmissionFixture(Path(temporary))
            real_compile = compile_body_sway_continuous_preview_proof

            def compile_then_advance(inputs):
                value = real_compile(inputs)
                fixture.append("reject")
                return value

            with patch(
                "autospine_workbench.p10_continuous_proof_commands."
                "compile_body_sway_continuous_preview_proof",
                side_effect=compile_then_advance,
            ), self.assertRaises(P10ContinuousProofCommandError):
                self.compile(fixture)

    def test_crosswired_exact_address_fails_without_writes(self):
        before = tree(self.root)
        with self.assertRaises(P10ContinuousProofCommandError):
            self.compile(visual_decision_sha256="a" * 64)
        self.assertEqual(before, tree(self.root))

    def test_command_source_has_no_discovery_or_mutation_boundary(self):
        source = (
            SRC / "autospine_workbench" / "p10_continuous_proof_commands.py"
        ).read_text(encoding="utf-8")
        for forbidden in (".glob(", ".rglob(", "publish_", "write_"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


def _recursive_keys(value) -> set[str]:
    if type(value) is dict:
        return set(value).union(*(
            _recursive_keys(item) for item in value.values()
        ))
    if type(value) is list:
        return set().union(*(_recursive_keys(item) for item in value))
    return set()


if __name__ == "__main__":
    unittest.main()
