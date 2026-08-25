"""Schema contracts for immutable P2 compile and setup-probe artifacts."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64

from autospine_workbench.rig_artifact_validation import (  # noqa: E402
    RigArtifactValidationError,
    require_compile_run_document,
    require_region_rig_profile,
    require_setup_probe_document,
)

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
                "id": check_id,
                "status": "passed",
                **(
                    {"metrics": {"exact": True}}
                    if check_id == "setup.pixel-reconstruction"
                    else {}
                ),
            }
            for check_id in (
                "source.identity",
                "inputs.reviewed",
                "bones.parent-links",
                "fk.setup-reconstruction",
                "attachments.region-bindings",
                "attachments.pivot-roundtrip",
                "slots.draw-order",
                "setup.pixel-reconstruction",
            )
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


class RigArtifactSemanticTests(unittest.TestCase):
    def test_compile_and_probe_documents_require_the_fixed_P2_profile(self) -> None:
        require_compile_run_document(compile_run())
        require_setup_probe_document(probe_report())

        bad_run = deepcopy(compile_run())
        bad_run["compiler"]["id"] = "latest"
        with self.assertRaises(RigArtifactValidationError):
            require_compile_run_document(bad_run)

        missing = deepcopy(probe_report())
        missing["checks"].pop()
        with self.assertRaisesRegex(RigArtifactValidationError, "missing checks"):
            require_setup_probe_document(missing)

        inexact = deepcopy(probe_report())
        inexact["checks"][-1]["metrics"]["exact"] = False
        with self.assertRaisesRegex(RigArtifactValidationError, "pixel reconstruction"):
            require_setup_probe_document(inexact)

    def test_region_profile_rejects_mesh_animation_or_rejected_qa(self) -> None:
        rig = {
            "capabilities": ["region_attachment", "setup_draw_order"],
            "attachments": [
                {
                    "type": "region",
                    "source_layer_ids": ["layer-a"],
                }
            ],
            "animations": [],
            "qa": {"status": "passed"},
        }
        require_region_rig_profile(rig)
        for field, value in (
            ("capabilities", ["region_attachment", "mesh_attachment"]),
            ("animations", [{"id": "probe"}]),
            ("qa", {"status": "rejected"}),
        ):
            changed = deepcopy(rig)
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(RigArtifactValidationError):
                require_region_rig_profile(changed)


if __name__ == "__main__":
    unittest.main()
