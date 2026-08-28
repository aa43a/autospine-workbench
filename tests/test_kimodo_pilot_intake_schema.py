"""JSON Schema coverage for the real Kimodo pilot intake report."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.kimodo_pilot_intake import (  # noqa: E402
    audit_kimodo_pilot_intake,
)
from tests.kimodo_pilot_intake_helpers import KimodoPilotInputs  # noqa: E402

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional test dependency
    Draft202012Validator = None


@unittest.skipIf(Draft202012Validator is None, "jsonschema is unavailable")
class KimodoPilotIntakeSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads((
            ROOT / "schemas" / "kimodo-pilot-intake-report-v1.schema.json"
        ).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(cls.schema)
        cls.validator = Draft202012Validator(cls.schema)

    def test_generated_report_satisfies_schema(self):
        inputs = KimodoPilotInputs()
        report = audit_kimodo_pilot_intake(*inputs.arguments())
        self.validator.validate(report)

    def test_schema_rejects_authority_and_integer_boolean_aliases(self):
        inputs = KimodoPilotInputs()
        report = audit_kimodo_pilot_intake(*inputs.arguments())
        changed = deepcopy(report)
        changed["authority"]["publish"] = True
        self.assertTrue(list(self.validator.iter_errors(changed)))
        changed = deepcopy(report)
        changed["producer"]["sample_index"] = False
        self.assertTrue(list(self.validator.iter_errors(changed)))


if __name__ == "__main__":
    unittest.main()
