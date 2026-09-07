"""Pinned historical identities and isolated 4.3.26 run histories."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tests.test_pipeline_run import ADDRESSES, ROOT, new_run
from autospine_workbench.automation.pipeline_run import (
    PipelineRunError, create_run, request_identity, seal, transition, validate_transition,
)
from autospine_workbench.automation.pipeline_run_store import PipelineRunStore
from autospine_workbench.automation.pipeline_run_validation import validate_run
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.automation.target_version import (
    DEFAULT_TARGET_VERSION, engine_for_target, require_target_version, target_from_run,
)


class PipelineTargetVersionTests(unittest.TestCase):
    def test_legacy_default_keeps_exact_pre_change_identity_and_document_bytes(self):
        old = new_run()
        explicit = create_run("sample-a", "production_review", ADDRESSES, target_version="4.2")
        self.assertEqual(DEFAULT_TARGET_VERSION, "4.3.26")
        self.assertEqual(old, explicit)
        self.assertEqual(old["run_id"],
                         "run-1da17e62b0a11923f4bf44ccc1aac815f1c0b81468b78e86b87b083aed804f6b")
        self.assertEqual(old["state_sha256"],
                         "2a427cfddcb524d9cd9e13d648bdce3416e93ddad209717e11d77dbe248a1e72")
        self.assertEqual(hashlib.sha256(canonical_bytes(old)).hexdigest(),
                         "e231a0bea4255a6333f7cc7bc46ab4cae33a0a101d00bff1c81e61db73e7ff6f")
        self.assertEqual(request_identity("sample-a", "production_review", ADDRESSES),
                         request_identity("sample-a", "production_review", ADDRESSES,
                                          target_version="4.2"))
        self.assertEqual(target_from_run(old), "4.2")

    def test_target_is_bound_to_engine_and_new_run_identity_without_new_fields(self):
        old = new_run()
        new = create_run("sample-a", "production_review", ADDRESSES, target_version="4.3.26")
        self.assertEqual(set(new), set(old))
        self.assertEqual(new["engine"], "region-spine-preview-spine43-4.3.26-v1")
        self.assertNotEqual(new["run_id"], old["run_id"])
        self.assertEqual(target_from_run(new), "4.3.26")
        running = transition(new, "start")
        validate_transition(new, running)
        self.assertEqual(target_from_run(running), "4.3.26")
        for original, engine in ((old, new["engine"]), (new, old["engine"])):
            with self.subTest(engine=engine), self.assertRaises(PipelineRunError):
                validate_run(seal({**original, "engine": engine}))
        with self.assertRaises(PipelineRunError):
            validate_transition(old, running)

    def test_strict_versions_fail_without_coercion_or_creating_storage(self):
        for version in (None, True, 4.2, [], {}, "4.3", "4.3.25", "4.3.26 ", "4.2\n"):
            with self.subTest(version=version):
                for operation in (
                    lambda: require_target_version(version),
                    lambda: engine_for_target(version),
                    lambda: create_run("sample-a", "production_review", ADDRESSES,
                                       target_version=version),
                ):
                    with self.assertRaises(PipelineRunError) as caught:
                        operation()
                    self.assertEqual(caught.exception.reason_code, "unsupported_target_version")
        for run in (None, [], {}, {"engine": "unknown"}, {"engine": []}):
            with self.subTest(run=run), self.assertRaises(PipelineRunError):
                target_from_run(run)
        with tempfile.TemporaryDirectory() as directory:
            store = PipelineRunStore(directory)
            with self.assertRaises(PipelineRunError):
                store.create("sample-a", "production_review", ADDRESSES, target_version="4.3")
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_store_reopens_both_targets_and_new_progress_does_not_change_old_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PipelineRunStore(directory)
            old = store.create("sample-a", "production_review", ADDRESSES)
            old_path = store.root / old["run_id"] / "events" / "000000.json"
            before = old_path.read_bytes()
            new = store.create("sample-a", "production_review", ADDRESSES, target_version="4.3.26")
            running = store.append(new["run_id"], new["state_sha256"], "start")
            reopened = PipelineRunStore(directory)
            self.assertEqual(reopened.load(old["run_id"]), old)
            self.assertEqual(reopened.load(new["run_id"]), running)
            self.assertEqual(reopened.create("sample-a", "production_review", ADDRESSES,
                                             target_version="4.3.26"), running)
            self.assertEqual(reopened.create("sample-a", "production_review", ADDRESSES), old)
            self.assertEqual(old_path.read_bytes(), before)

    def test_schema_and_validator_accept_both_pinned_engines_and_reject_unknowns(self):
        from jsonschema import Draft202012Validator

        schema = json.loads((ROOT / "schemas/pipeline-run-v1.schema.json").read_text())
        validator = Draft202012Validator(schema)
        for version in ("4.2", "4.3.26"):
            document = create_run("sample-a", "production_review", ADDRESSES, target_version=version)
            validator.validate(document)
            validate_run(document)
        malformed = seal({**new_run(), "engine": "region-spine-preview-spine43-v1"})
        self.assertFalse(validator.is_valid(malformed))
        with self.assertRaises(PipelineRunError):
            validate_run(malformed)
