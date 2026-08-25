"""Schema contracts for immutable P2 compile and setup-probe artifacts."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64

try:
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import ValidationError
except ImportError:  # pragma: no cover - dependency-free smoke environments
    Draft202012Validator = None
    ValidationError = Exception


def load_schema(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


def compile_run() -> dict:
    return {
        "format": "autospine-rig-compile-run",
        "format_version": 1,
        "project_id": "sample-a",
        "inputs": {
            "layer_manifest_sha256": SHA_A,
            "resolved_project_sha256": SHA_B,
            "override_patch_sha256": SHA_C,
        },
        "compiler": {
            "id": "region-rig-compiler",
            "version": "1.0.0",
            "config": {
                "attachment_profile": "region-only",
                "allow_manual_required": False,
            },
        },
    }


def probe_report() -> dict:
    return {
        "format": "autospine-rig-setup-probes",
        "format_version": 1,
        "project_id": "sample-a",
        "source": {
            "rig_sha256": SHA_A,
            "layer_manifest_sha256": SHA_B,
            "resolved_project_sha256": SHA_C,
        },
        "runner": {"id": "rig-setup-probes", "version": "1.0.0"},
        "status": "passed",
        "checks": [
            {
                "id": "setup-fk",
                "status": "passed",
                "metrics": {"max_endpoint_error_px": 0.0},
            }
        ],
    }


class RigArtifactSchemaTests(unittest.TestCase):
    def test_schema_documents_are_valid_draft_2020_12(self) -> None:
        for name in (
            "rig-compile-run-v1.schema.json",
            "rig-setup-probes-v1.schema.json",
        ):
            schema = load_schema(name)
            self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
            self.assertTrue(schema["$id"].endswith(name))
            if Draft202012Validator is not None:
                Draft202012Validator.check_schema(schema)

    @unittest.skipIf(Draft202012Validator is None, "install the test extra")
    def test_minimum_documents_validate(self) -> None:
        Draft202012Validator(load_schema("rig-compile-run-v1.schema.json")).validate(
            compile_run()
        )
        Draft202012Validator(load_schema("rig-setup-probes-v1.schema.json")).validate(
            probe_report()
        )

    @unittest.skipIf(Draft202012Validator is None, "install the test extra")
    def test_identity_and_status_tokens_fail_closed(self) -> None:
        run = deepcopy(compile_run())
        run["inputs"]["resolved_project_sha256"] = "latest"
        with self.assertRaises(ValidationError):
            Draft202012Validator(load_schema("rig-compile-run-v1.schema.json")).validate(run)
        report = deepcopy(probe_report())
        report["checks"][0]["status"] = "pass"
        with self.assertRaises(ValidationError):
            Draft202012Validator(load_schema("rig-setup-probes-v1.schema.json")).validate(
                report
            )


if __name__ == "__main__":
    unittest.main()
