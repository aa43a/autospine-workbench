"""Draft 2020-12 coverage for P10.7c request and report documents."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

try:
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import ValidationError
except ImportError:  # pragma: no cover - optional developer dependency
    Draft202012Validator = None
    ValidationError = Exception

from autospine_workbench.spine42_v3_setup_regression_report import (  # noqa: E402
    build_spine42_v3_setup_regression_report,
)
from tests.test_spine42_v3_setup_regression import (  # noqa: E402
    Spine42V3SetupRegressionTests,
)


@unittest.skipIf(Draft202012Validator is None, "jsonschema is not installed")
class Spine42V3SetupRegressionSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.request_schema = json.loads((
            ROOT / "schemas" /
            "spine42-v3-setup-regression-request-v1.schema.json"
        ).read_text(encoding="utf-8"))
        cls.report_schema = json.loads((
            ROOT / "schemas" /
            "spine42-v3-setup-regression-report-v1.schema.json"
        ).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(cls.request_schema)
        Draft202012Validator.check_schema(cls.report_schema)
        cls.request_validator = Draft202012Validator(cls.request_schema)
        cls.report_validator = Draft202012Validator(cls.report_schema)

    @staticmethod
    def documents():
        request, row = Spine42V3SetupRegressionTests().compare()
        return request, build_spine42_v3_setup_regression_report(request, [row])

    def test_actual_request_and_report_validate(self):
        request, report = self.documents()
        self.request_validator.validate(request)
        self.report_validator.validate(report)

    def test_extra_fields_and_authority_forgery_are_rejected(self):
        request, report = self.documents()
        bad_request = deepcopy(request)
        bad_request["samples"][0]["extra"] = None
        bad_report = deepcopy(report)
        bad_report["authority"]["release"] = True
        with self.assertRaises(ValidationError):
            self.request_validator.validate(bad_request)
        with self.assertRaises(ValidationError):
            self.report_validator.validate(bad_report)

    def test_descriptions_delegate_semantic_hash_invariants(self):
        for schema in (self.request_schema, self.report_schema):
            description = schema["description"]
            self.assertIn("semantic validator", description)
        self.assertIn("Canonical", self.request_schema["description"])
        self.assertIn("self-hash", self.report_schema["description"])


if __name__ == "__main__":
    unittest.main()
