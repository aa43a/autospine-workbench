"""Fast orchestration tests for the job-centric P10.4a v2 command."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.body_sway_review_admission_inputs_v2 import (  # noqa: E402
    BodySwayReviewAdmissionInputV2Error,
)
from autospine_workbench.body_sway_visual_review_history_snapshot_v2 import (  # noqa: E402
    BodySwayVisualReviewHistoryRowV2,
)
from autospine_workbench.p10_review_admission_v2_commands import (  # noqa: E402
    P10ReviewAdmissionV2CommandError,
    compile_body_sway_review_admission_v2_for_job,
)
from tests.p10_review_admission_v2_helpers import (  # noqa: E402
    shared_p10_review_admission_v2_fixture,
)


COMMAND_MODULE = "autospine_workbench.p10_review_admission_v2_commands"


class P10ReviewAdmissionV2CommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = shared_p10_review_admission_v2_fixture()

    def harness(
        self, *, contexts=None, prepared=None,
        build_result=None, build_error=None,
    ):
        fixture = self.fixture
        service = Mock(spec_set=["prepare", "exact_decision"])
        service.prepare.return_value = prepared or fixture.before
        service.exact_decision.return_value = fixture.exact
        resolver = patch(
            COMMAND_MODULE + ".resolve_p10_visual_review_v2_context",
            return_value=fixture.context,
            side_effect=contexts,
        )
        application = patch(
            COMMAND_MODULE + ".BodySwayVisualReviewApplicationV2",
            return_value=service,
        )
        builder = patch(
            COMMAND_MODULE + ".build_body_sway_review_admission_input_v2",
            return_value=build_result or fixture.inputs,
            side_effect=build_error,
        )
        compiler = patch(
            COMMAND_MODULE + ".compile_body_sway_review_admission_v2",
            return_value=fixture.admission,
        )
        return _Harness(resolver, application, builder, compiler, service)

    def compile(self, **pins):
        return compile_body_sway_review_admission_v2_for_job(
            Mock(spec_set=["get"]), self.fixture.store,
            self.fixture.context.job_id, **pins,
        )

    def test_automatic_current_head_is_deterministic_and_resolved_twice(self):
        with self.harness() as rig:
            first = self.compile()
        with self.harness() as repeated_rig:
            repeated = self.compile()
        self.assertEqual(first.admission_sha256,
                         repeated.admission_sha256)
        self.assertEqual(self.fixture.approved.candidate_sha256,
                         first.visual_candidate_sha256)
        self.assertEqual(self.fixture.approved.revision,
                         first.visual_revision)
        self.assertEqual(self.fixture.approved.decision_sha256,
                         first.visual_decision_sha256)
        self.assertEqual(self.fixture.context.job_head_event_sha256,
                         first.terminal_event_sha256)
        self.assertEqual(self.fixture.context.job_event_count,
                         first.terminal_sequence)
        for current in (rig, repeated_rig):
            self.assertEqual(2, current.resolve.call_count)
            for call in current.resolve.call_args_list:
                self.assertIs(False, call.kwargs["allow_acceleration"])
            self.assertEqual(2, current.service.prepare.call_count)
            current.service.exact_decision.assert_called_once()
            current.build.assert_called_once()
            current.compile.assert_called_once()

    def test_all_or_none_head_pins_and_exact_current_pins(self):
        approved = self.fixture.approved
        complete = {
            "expected_candidate_sha256": approved.candidate_sha256,
            "expected_visual_revision": approved.revision,
            "expected_decision_sha256": approved.decision_sha256,
        }
        with self.harness():
            result = self.compile(**complete)
        self.assertEqual(approved.decision_sha256,
                         result.visual_decision_sha256)

        combinations = (
            {"expected_candidate_sha256": approved.candidate_sha256},
            {"expected_visual_revision": approved.revision},
            {"expected_decision_sha256": approved.decision_sha256},
            {"expected_candidate_sha256": approved.candidate_sha256,
             "expected_visual_revision": approved.revision},
            {"expected_candidate_sha256": approved.candidate_sha256,
             "expected_decision_sha256": approved.decision_sha256},
            {"expected_visual_revision": approved.revision,
             "expected_decision_sha256": approved.decision_sha256},
        )
        for partial in combinations:
            with self.subTest(partial=partial), self.harness() as rig, \
                    self.assertRaises(P10ReviewAdmissionV2CommandError):
                self.compile(**partial)
            rig.resolve.assert_not_called()
            rig.service.prepare.assert_not_called()

    def test_old_approved_pin_is_rejected_before_exact_decision_replay(self):
        current = _new_head(self.fixture, "sampled_visual_rejected")
        old = self.fixture.approved
        with self.harness(prepared=current) as rig, self.assertRaises(
            P10ReviewAdmissionV2CommandError
        ):
            self.compile(
                expected_candidate_sha256=old.candidate_sha256,
                expected_visual_revision=old.revision,
                expected_decision_sha256=old.decision_sha256,
            )
        rig.service.exact_decision.assert_not_called()
        rig.build.assert_not_called()

    def test_rejected_and_unobservable_current_heads_reach_fail_closed_builder(self):
        for reason in ("rejected", "unobservable"):
            prepared = _new_head(
                self.fixture, "sampled_visual_rejected",
                digest_character="6" if reason == "rejected" else "7",
            )
            failure = BodySwayReviewAdmissionInputV2Error(
                f"current head is {reason}",
            )
            with self.subTest(reason=reason), self.harness(
                prepared=prepared, build_error=failure,
            ) as rig, self.assertRaises(P10ReviewAdmissionV2CommandError):
                self.compile()
            rig.service.exact_decision.assert_called_once()
            rig.build.assert_called_once()
            rig.compile.assert_not_called()

    def test_context_a_b_drift_is_forwarded_to_core_and_wrapped(self):
        context = self.fixture.context
        variants = (
            replace(context, job_head_event_sha256="1" * 64),
            replace(context, job_event_count=context.job_event_count + 1),
            replace(context, package_id="other-package"),
            replace(context, address=replace(
                context.address, project_id="other-project",
            )),
            replace(context, preview=Mock(name="changed-preview")),
            replace(context, preview=Mock(name="changed-execution-mount")),
        )
        for changed in variants:
            failure = BodySwayReviewAdmissionInputV2Error("A/B drift")
            with self.subTest(changed=changed), self.harness(
                contexts=[context, changed], build_error=failure,
            ) as rig, self.assertRaises(P10ReviewAdmissionV2CommandError):
                self.compile()
            self.assertEqual(2, rig.resolve.call_count)
            call = rig.build.call_args
            self.assertIs(context, call.args[0])
            self.assertIs(changed, call.args[3])

    def test_invalid_job_and_wrong_complete_pins_fail_before_compile(self):
        with self.harness() as rig, self.assertRaises(
            P10ReviewAdmissionV2CommandError
        ):
            compile_body_sway_review_admission_v2_for_job(
                Mock(spec_set=["get"]), self.fixture.store, "not-a-sha",
            )
        rig.resolve.assert_not_called()
        with self.harness() as rig, self.assertRaises(
            P10ReviewAdmissionV2CommandError
        ):
            self.compile(
                expected_candidate_sha256="0" * 64,
                expected_visual_revision=1,
                expected_decision_sha256="1" * 64,
            )
        rig.service.exact_decision.assert_not_called()
        rig.build.assert_not_called()


class _Harness:
    def __init__(self, resolver, application, builder, compiler, service):
        self._patches = (resolver, application, builder, compiler)
        self.service = service

    def __enter__(self):
        self.resolve, self.application, self.build, self.compile = (
            item.start() for item in self._patches
        )
        return self

    def __exit__(self, *args):
        for item in reversed(self._patches):
            item.stop()


def _new_head(fixture, status, *, digest_character="6"):
    history = fixture.before.history
    decision_sha = digest_character * 64
    row = BodySwayVisualReviewHistoryRowV2(
        history.current_revision + 1, decision_sha, status,
    )
    changed = replace(
        history, revision_count=history.revision_count + 1,
        current_revision=history.current_revision + 1,
        head_decision_sha256=decision_sha, rows=history.rows + (row,),
    )
    return replace(fixture.before, history=changed)


if __name__ == "__main__":
    unittest.main()
