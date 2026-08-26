"""Strict read-only application-command tests for P10.4a admission."""

from __future__ import annotations

from dataclasses import replace
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

from autospine_workbench.p10_review_admission_commands import (  # noqa: E402
    P10ReviewAdmissionCommandError,
    compile_body_sway_review_admission_command,
)
from tests.body_sway_runtime_capture_helpers import (  # noqa: E402
    fake_runtime_profile,
)
from tests.p10_review_admission_helpers import (  # noqa: E402
    P10ReviewAdmissionFixture,
)
from tests.p9_v2_helpers import tree  # noqa: E402


class P10ReviewAdmissionCommandTests(unittest.TestCase):
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
            return compile_body_sway_review_admission_command(
                *current.command_args, **kwargs
            )

    def test_exact_command_is_deterministic_ordered_and_zero_write(self):
        service = self.fixture.application
        real_prepare = service.prepare
        real_exact = service.exact_decision
        calls = []

        def prepare(*args, **kwargs):
            calls.append("history")
            return real_prepare(*args, **kwargs)

        def exact(*args, **kwargs):
            calls.append("decision")
            return real_exact(*args, **kwargs)

        before = tree(self.root)
        with patch(
            "autospine_workbench.p10_review_admission_commands."
            "BodySwayVisualReviewApplication",
            return_value=service,
        ), patch.object(service, "prepare", side_effect=prepare), patch.object(
            service, "exact_decision", side_effect=exact,
        ):
            first = self.compile()
        repeated = self.compile()
        self.assertEqual(before, tree(self.root))
        self.assertEqual(["history", "decision", "history"], calls)
        self.assertEqual(first.admission_sha256, repeated.admission_sha256)
        self.assertEqual(first.document, repeated.document)
        self.assertEqual(8, len(first.input_paths))
        self.assertEqual("admitted_for_safety_analysis", first.document["status"])
        self.assertEqual("blocked", first.document["release_gate"]["status"])
        self.assertEqual({
            "method": "double_snapshot",
            "scope": "compile_time",
            "revision": 1,
            "head_decision_sha256": first.visual_decision_sha256,
            "permanent_authority_claimed": False,
        }, first.document["head_observation"])

    def test_crosswired_exact_addresses_fail_closed_without_writes(self):
        wrong = {
            "p3_rig_sha256":
                self.fixture.command_kwargs["p3_bundle_sha256"],
            "temporary_preview_sha256": "a" * 64,
            "visual_candidate_sha256": "b" * 64,
            "visual_revision": 2,
            "visual_decision_sha256": "c" * 64,
        }
        for field, value in wrong.items():
            before = tree(self.root)
            with self.subTest(field=field), self.assertRaises(
                P10ReviewAdmissionCommandError
            ):
                self.compile(**{field: value})
            self.assertEqual(before, tree(self.root))

    def test_old_approval_rejected_after_reject_and_unobservable_heads(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = P10ReviewAdmissionFixture(Path(temporary))
            approved_address = dict(fixture.command_kwargs)
            rejected = fixture.append("reject")
            before = tree(fixture.root)
            with self.assertRaises(P10ReviewAdmissionCommandError):
                self.compile(fixture, **approved_address)
            self.assertEqual(before, tree(fixture.root))
            with self.assertRaises(P10ReviewAdmissionCommandError):
                self.compile(
                    fixture,
                    visual_revision=rejected.revision,
                    visual_decision_sha256=rejected.decision_sha256,
                )
            self.assertEqual(before, tree(fixture.root))
            unobservable = fixture.append("unobservable")
            before = tree(fixture.root)
            with self.assertRaises(P10ReviewAdmissionCommandError):
                self.compile(
                    fixture,
                    visual_revision=unobservable.revision,
                    visual_decision_sha256=unobservable.decision_sha256,
                )
            self.assertEqual(before, tree(fixture.root))

    def test_head_change_between_snapshots_is_rejected(self):
        service = self.fixture.application
        with fake_runtime_profile():
            prepared = service.prepare(self.fixture.address)
            exact = service.exact_decision(
                self.fixture.address,
                candidate_sha256=prepared.candidate_sha256,
                revision=self.fixture.approved.revision,
                decision_sha256=self.fixture.approved.decision_sha256,
            )
        changed = replace(
            prepared,
            history=replace(
                prepared.history, head_decision_sha256="d" * 64
            ),
        )
        before = tree(self.root)
        with patch(
            "autospine_workbench.p10_review_admission_commands."
            "BodySwayVisualReviewApplication",
            return_value=service,
        ), patch.object(
            service, "prepare", side_effect=[prepared, changed]
        ), patch.object(
            service, "exact_decision", return_value=exact
        ), self.assertRaises(P10ReviewAdmissionCommandError):
            self.compile()
        self.assertEqual(before, tree(self.root))

    def test_tampered_evidence_file_fails_closed_without_extra_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = P10ReviewAdmissionFixture(Path(temporary))
            changed = fixture.candidates_path.read_text(encoding="utf-8")
            fixture.candidates_path.write_text(
                changed.replace(
                    '"project_id":"p10-persisted"',
                    '"project_id":"crosswired-project"',
                    1,
                ),
                encoding="utf-8",
            )
            before = tree(fixture.root)
            with self.assertRaises(P10ReviewAdmissionCommandError):
                self.compile(fixture)
            self.assertEqual(before, tree(fixture.root))

    def test_command_source_has_no_discovery_or_mutation_boundary(self):
        source = (
            SRC / "autospine_workbench" /
            "p10_review_admission_commands.py"
        ).read_text(encoding="utf-8")
        for forbidden in (".glob(", ".rglob(", "publish_", "write_"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
