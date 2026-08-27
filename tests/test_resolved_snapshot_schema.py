"""Public JSON Schema checks for complete resolved project v1 documents."""

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

from tests.resolved_snapshot_helpers import (  # noqa: E402
    resolved_snapshot_fixture,
    with_candidate_accept,
)

try:
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import ValidationError
except ImportError:  # pragma: no cover - optional test extra
    Draft202012Validator = None
    ValidationError = Exception


SCHEMA_PATH = ROOT / "schemas" / "resolved-project-v1.schema.json"


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


class ResolvedSnapshotSchemaTests(unittest.TestCase):
    def test_schema_is_parseable_draft_2020_12_with_pinned_identity(self) -> None:
        schema = load_schema()
        self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
        self.assertTrue(schema["$id"].endswith("resolved-project-v1.schema.json"))
        self.assertEqual("autospine.resolved-project/v1", schema["properties"]["schema_version"]["const"])
        self.assertFalse(schema["additionalProperties"])

    @unittest.skipIf(Draft202012Validator is None, "install the 'test' extra for JSON Schema checks")
    def test_complete_manual_and_candidate_snapshots_validate(self) -> None:
        schema = load_schema()
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        validator.validate(resolved_snapshot_fixture())
        validator.validate(with_candidate_accept(resolved_snapshot_fixture()))

    @unittest.skipIf(Draft202012Validator is None, "install the 'test' extra for JSON Schema checks")
    def test_authority_objects_reject_unknown_fields(self) -> None:
        validator = Draft202012Validator(load_schema())
        candidates = []
        for path in (
            ("root",), ("inputs",), ("layer",), ("bbox",), ("metrics",),
            ("skeleton",), ("generation",), ("joint",), ("bone",),
            ("qa",), ("split_decision",), ("split_analysis",),
        ):
            document = resolved_snapshot_fixture()
            name = path[0]
            target = {
                "root": document,
                "inputs": document["inputs"],
                "layer": document["layers"][0],
                "bbox": document["layers"][0]["bbox"],
                "metrics": document["layers"][0]["metrics"],
                "skeleton": document["skeleton"],
                "generation": document["skeleton"]["generation"],
                "joint": document["skeleton"]["joints"][0],
                "bone": document["skeleton"]["bones"][0],
                "qa": document["qa"],
                "split_decision": document["layers"][1]["split_decision"],
                "split_analysis": document["layers"][1]["split_decision"]["analysis"],
            }[name]
            target["spoofed_authority"] = True
            candidates.append((name, document))
        candidate_document = with_candidate_accept(resolved_snapshot_fixture())
        candidate_document["inputs"]["candidate_analyses"][0]["spoofed_authority"] = True
        candidates.append(("candidate_analysis", candidate_document))
        for label, document in candidates:
            with self.subTest(authority=label), self.assertRaises(ValidationError):
                validator.validate(document)

    @unittest.skipIf(Draft202012Validator is None, "install the 'test' extra for JSON Schema checks")
    def test_required_authority_fields_fail_closed(self) -> None:
        validator = Draft202012Validator(load_schema())
        cases = []
        for label, target, field in (
            ("root", lambda item: item, "inputs"),
            ("inputs", lambda item: item["inputs"], "candidate_analyses"),
            ("layer", lambda item: item["layers"][0], "reviewed_fields"),
            ("joint", lambda item: item["skeleton"]["joints"][0], "model_confidence"),
            ("bone", lambda item: item["skeleton"]["bones"][0], "parent_id"),
            ("qa", lambda item: item["qa"], "stale_split_layer_ids"),
        ):
            document = resolved_snapshot_fixture()
            del target(document)[field]
            cases.append((label, document))
        for label, document in cases:
            with self.subTest(authority=label), self.assertRaises(ValidationError):
                validator.validate(document)


if __name__ == "__main__":
    unittest.main()
