"""Pinned pipeline state-machine, identity and contract regression tests."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")) if str(ROOT / "src") not in sys.path else None

from autospine_workbench.automation.pipeline_run import (
    OUTPUTS, SOURCES, PipelineRunError, create_run, seal, transition, validate_transition,
)
from autospine_workbench.automation.pipeline_run_validation import validate_run

ADDRESSES = {key: str(index + 1) * 64 for index, key in enumerate(SOURCES)}


def new_run():
    return create_run("sample-a", "production_review", ADDRESSES)


def complete_steps(run, count=3):
    for index in range(count):
        run = transition(run, "start")
        outputs = ADDRESSES if index == 0 else {key: "a" * 64 for key in OUTPUTS[index]}
        run = transition(run, "succeed", outputs=outputs)
    return run


class PipelineRunTests(unittest.TestCase):
    def test_malformed_public_transition_arguments_have_structured_errors(self):
        with self.assertRaises(PipelineRunError):
            transition(new_run(), [])
        with self.assertRaises(PipelineRunError):
            validate_transition({}, new_run())

    def test_identity_idempotence_and_input_profile_invalidation(self):
        first = new_run()
        self.assertEqual(first, new_run())
        changed = {**ADDRESSES, SOURCES[0]: "e" * 64}
        self.assertNotEqual(first["run_id"], create_run("sample-a", "production_review", changed)["run_id"])
        self.assertNotEqual(first["run_id"], create_run("sample-a", "draft_auto", ADDRESSES)["run_id"])
        self.assertEqual(first["authority"], "none")

    def test_start_succeed_preserves_history_and_does_not_mutate_inputs(self):
        original = new_run()
        before = deepcopy(original)
        running = transition(original, "start")
        validate_transition(original, running)
        self.assertEqual(original, before)
        self.assertEqual(running["previous_sha256"], original["state_sha256"])
        self.assertEqual(running["revision"], 1)
        outputs = deepcopy(ADDRESSES)
        first_done = transition(running, "succeed", outputs=outputs)
        outputs[SOURCES[0]] = "e" * 64
        self.assertEqual(first_done["steps"][0]["outputs"], ADDRESSES)
        self.assertEqual(first_done["status"], "pending")
        self.assertEqual(first_done["steps"][1]["status"], "pending")

    def test_all_three_steps_reach_terminal_success(self):
        result = complete_steps(new_run())
        self.assertEqual(result["revision"], 6)
        self.assertEqual(result["status"], "succeeded")
        for action in ("start", "resume", "cancel", "fail", "succeed"):
            with self.subTest(action=action), self.assertRaises(PipelineRunError):
                transition(result, action)

    def test_block_review_fail_resume_keep_successful_upstream(self):
        first_done = complete_steps(new_run(), 1)
        for action, expected in (("block", "blocked"), ("review", "needs_review"), ("fail", "failed")):
            for starting in (first_done, transition(first_done, "start")):
                with self.subTest(action=action, starting=starting["status"]):
                    stopped = transition(starting, action, reason_code="project_review_required")
                    self.assertEqual(stopped["status"], expected)
                    resumed = transition(stopped, "resume")
                    validate_transition(stopped, resumed)
                    self.assertEqual(resumed["steps"][0], first_done["steps"][0])
                    self.assertEqual(resumed["steps"][1]["reason_code"], None)
                    self.assertEqual(resumed["status"], "pending")

    def test_running_is_resumable_after_worker_interruption(self):
        pending = new_run()
        resumed = transition(transition(pending, "start"), "resume")
        self.assertEqual(resumed["steps"], pending["steps"])
        self.assertEqual(resumed["revision"], 2)

    def test_cancel_is_terminal_and_only_changes_current_step(self):
        first_done = complete_steps(new_run(), 1)
        canceled = transition(first_done, "cancel")
        self.assertEqual(canceled["steps"][0], first_done["steps"][0])
        self.assertEqual(canceled["steps"][1]["reason_code"], "pipeline_canceled")
        self.assertEqual(canceled["status"], "canceled")
        with self.assertRaises(PipelineRunError):
            transition(canceled, "resume")

    def test_reject_invalid_actions_outputs_and_reason_arguments(self):
        pending, running = new_run(), transition(new_run(), "start")
        cases = [
            (pending, "succeed", {"outputs": ADDRESSES}), (pending, "resume", {}),
            (running, "start", {}), (pending, "invented", {}),
            (pending, "start", {"outputs": {}}),
            (pending, "start", {"reason_code": "unexpected"}),
            (pending, "block", {"reason_code": "C:/private/path"}),
            (pending, "review", {}), (running, "succeed", {"outputs": {}}),
            (running, "succeed", {"outputs": {**ADDRESSES, SOURCES[0]: "f" * 64}}),
        ]
        for source, action, kwargs in cases:
            with self.subTest(action=action, kwargs=kwargs), self.assertRaises(PipelineRunError):
                transition(source, action, **kwargs)

    def test_tamper_and_resealed_illegal_history_are_rejected(self):
        pending = new_run()
        invalid = deepcopy(pending)
        invalid["authority"] = "release"
        with self.assertRaises(PipelineRunError):
            validate_run(seal(invalid))
        invalid = deepcopy(pending)
        invalid["state_sha256"] = "f" * 64
        with self.assertRaises(PipelineRunError):
            validate_run(invalid)
        running = transition(pending, "start")
        invalid = seal({**running, "action": "resume"})
        validate_run(invalid)  # A snapshot alone cannot prove its predecessor.
        with self.assertRaises(PipelineRunError):
            validate_transition(pending, invalid)

    def test_revision_ceiling_and_strict_integer_are_enforced(self):
        running = transition(new_run(), "start")
        for revision in (True, 1.0, -1, 1025):
            with self.subTest(revision=revision), self.assertRaises(PipelineRunError):
                validate_run(seal({**running, "revision": revision}))
        full = seal({**running, "revision": 1024})
        validate_run(full)
        with self.assertRaises(PipelineRunError):
            transition(full, "resume")

    def test_schema_accepts_all_emitted_states_and_rejects_structural_drift(self):
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest("jsonschema unavailable")
        schema = json.loads((ROOT / "schemas/pipeline-run-v1.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        pending = new_run()
        valid = [complete_steps(pending)]
        for count in range(3):
            source = complete_steps(pending, count)
            valid.extend((source, transition(source, "start"), transition(source, "cancel")))
            for action in ("block", "review", "fail"):
                stopped = transition(source, action, reason_code="review_required")
                valid.extend((stopped, transition(stopped, "resume")))
        for document in valid:
            validator.validate(document)
            validate_run(document)
        mutations = [
            {"authority": "release"}, {"operation": "motion"}, {"revision": True},
            {"project_id": "CON.txt"}, {"project_id": "sample."},
            {"project_id": "sample-a\n"}, {"run_id": pending["run_id"] + "\n"},
            {"source_addresses": {}}, {"steps": []}, {"status": "succeeded"},
            {"previous_sha256": "a" * 64}, {"action": "start"}, {"state_root": "private"},
        ]
        for mutation in mutations:
            invalid = seal({**pending, **mutation})
            with self.subTest(mutation=mutation):
                self.assertTrue(list(validator.iter_errors(invalid)))
                with self.assertRaises(PipelineRunError):
                    validate_run(invalid)
        for index in range(3):
            for field, value in (("outputs", {"unexpected": "a" * 64}),
                                 ("reason_code", "not_allowed"), ("id", "wrong-step")):
                invalid = deepcopy(pending)
                invalid["steps"][index][field] = value
                invalid = seal(invalid)
                with self.subTest(index=index, field=field):
                    self.assertTrue(list(validator.iter_errors(invalid)))
                    with self.assertRaises(PipelineRunError):
                        validate_run(invalid)


if __name__ == "__main__":
    unittest.main()
