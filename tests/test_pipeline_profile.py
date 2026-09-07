"""Profile contracts reject policy drift and never confer authority."""

import contextlib
import io
import json
from pathlib import Path
import sys
import unittest

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from autospine_workbench.automation.pipeline_profile import (
    PROFILE_NAMES, PipelineProfileError, build_pipeline_profile,
    main, validate_pipeline_profile,
)


class PipelineProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / "schemas/pipeline-profile-v1.schema.json"
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        cls.validator = Draft202012Validator(schema)

    def test_all_profiles_agree_with_schema(self):
        for name in PROFILE_NAMES:
            with self.subTest(name=name):
                document = build_pipeline_profile(name)
                self.validator.validate(document)
                self.assertEqual(document, validate_pipeline_profile(document))
                self.assertEqual("none", document["authority"])

    def test_closed_contract_rejects_every_field_mutation(self):
        for name in PROFILE_NAMES:
            original = build_pipeline_profile(name)
            for field in original:
                for replacement in (None, True, [], {}, "unauthorized"):
                    document = {**original, field: replacement}
                    with self.subTest(name=name, field=field, value=replacement):
                        self.assertFalse(self.validator.is_valid(document))
                        with self.assertRaises(PipelineProfileError):
                            validate_pipeline_profile(document)
                document = dict(original)
                del document[field]
                self.assertFalse(self.validator.is_valid(document))
                with self.assertRaises(PipelineProfileError):
                    validate_pipeline_profile(document)

    def test_unknown_fields_and_policy_splicing_are_rejected(self):
        draft = build_pipeline_profile("draft_auto")
        for document in (
            {**draft, "release_authorized": True},
            {**draft, "export_mode": "qa_gated"},
            {**draft, "profile": "production_review"},
            None, [], "draft_auto",
        ):
            self.assertFalse(self.validator.is_valid(document))
            with self.assertRaises(PipelineProfileError):
                validate_pipeline_profile(document)

    def test_return_values_do_not_mutate_defaults(self):
        document = build_pipeline_profile()
        document["authority"] = "release"
        self.assertEqual("none", build_pipeline_profile()["authority"])
        self.assertEqual("production_review", build_pipeline_profile()["profile"])

    def test_cli_returns_profile_or_structured_failure(self):
        for argv, code in (([], 0), (["manual_review"], 2)):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(code, main(argv))
            document = json.loads(output.getvalue())
            if code:
                self.assertEqual("unsupported_pipeline_profile", document["reason_code"])
            else:
                validate_pipeline_profile(document)
