"""Pure contract tests for the M1 real Kimodo pilot intake audit."""

from __future__ import annotations

from copy import deepcopy
import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.kimodo_npz_compile_run import (  # noqa: E402
    compile_kimodo_npz_motion_run,
)
from autospine_workbench.kimodo_pilot_intake import (  # noqa: E402
    KimodoPilotIntakeError,
    MAX_EXTERNAL_PROVENANCE_BYTES,
    audit_kimodo_pilot_intake,
)
from autospine_workbench.kimodo_pilot_intake_validation import (  # noqa: E402
    AUTHORITY,
    CLAIMS,
    KimodoPilotIntakeValidationError,
    require_kimodo_pilot_intake_report,
)
from tests.kimodo_pilot_intake_helpers import KimodoPilotInputs  # noqa: E402


class KimodoPilotIntakeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.inputs = KimodoPilotInputs()

    def audit(self) -> dict:
        return audit_kimodo_pilot_intake(*self.inputs.arguments())

    def test_is_deterministic_path_free_and_matches_p7_pure_compile(self):
        first = self.audit()
        second = self.audit()
        compiled, run = compile_kimodo_npz_motion_run(
            self.inputs.raw, self.inputs.source, self.inputs.mapping
        )

        self.assertEqual(first, second)
        require_kimodo_pilot_intake_report(first)
        self.assertEqual(compiled.sha256, first["p7_preview"]["motion_ir_sha256"])
        self.assertEqual(run.sha256, first["p7_preview"]["compile_run_sha256"])
        self.assertEqual(
            compiled.array_inventory_sha256,
            first["p7_preview"]["array_inventory_sha256"],
        )
        self.assertEqual("eligible_for_p7_p8_compile", first["status"])
        self.assertNotIn("path", repr(first).lower())
        self.assertTrue(
            first["claims"][
                "raw_npz_and_external_provenance_bytes_bound"
            ]
        )
        self.assertTrue(
            first["claims"]["canonical_json_input_identities_bound"]
        )
        self.assertFalse(first["claims"]["motion_quality_approved"])
        self.assertTrue(all(value is False for value in first["authority"].values()))

    def test_external_provenance_bytes_must_match_recorded_digests(self):
        cases = (
            (b"changed checkpoint", self.inputs.request, "checkpoint manifest"),
            (self.inputs.checkpoint, b"changed request", "generation request"),
            (b"", self.inputs.request, "checkpoint manifest bytes"),
            (
                b"x" * (MAX_EXTERNAL_PROVENANCE_BYTES + 1),
                self.inputs.request,
                "checkpoint manifest bytes",
            ),
        )
        for checkpoint, request, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(
                KimodoPilotIntakeError, message
            ):
                audit_kimodo_pilot_intake(
                    self.inputs.raw, self.inputs.source, self.inputs.mapping,
                    self.inputs.camera, checkpoint, request,
                )

    def test_unavailable_producer_and_camera_cross_wire_are_rejected(self):
        unavailable = deepcopy(self.inputs.source)
        unavailable["producer"] = {
            "status": "unavailable",
            "implementation": "nv-tlabs/kimodo",
            "reason_code": "external_export",
        }
        with self.assertRaisesRegex(
            KimodoPilotIntakeError, "requires recorded"
        ):
            audit_kimodo_pilot_intake(
                self.inputs.raw, unavailable, self.inputs.mapping,
                self.inputs.camera, self.inputs.checkpoint, self.inputs.request,
            )

        camera = deepcopy(self.inputs.camera)
        camera["reference_length_meters"] = 2.0
        with self.assertRaisesRegex(KimodoPilotIntakeError, "reference length"):
            audit_kimodo_pilot_intake(
                self.inputs.raw, self.inputs.source, self.inputs.mapping,
                camera, self.inputs.checkpoint, self.inputs.request,
            )

    def test_validator_rejects_self_hash_authority_and_bool_integer_aliases(self):
        report = self.audit()
        mutations = []
        changed = deepcopy(report)
        changed["claims"]["release_authority"] = True
        mutations.append(changed)
        changed = deepcopy(report)
        changed["authority"]["publish"] = 0
        mutations.append(changed)
        changed = deepcopy(report)
        changed["producer"]["sample_index"] = False
        mutations.append(changed)
        changed = deepcopy(report)
        changed["intake_report_sha256"] = "0" * 64
        mutations.append(changed)
        changed = deepcopy(report)
        changed["claims"] = type("ForgedClaims", (dict,), {})(
            changed["claims"]
        )
        mutations.append(changed)

        for candidate in mutations:
            with self.subTest(candidate=candidate), self.assertRaises(
                KimodoPilotIntakeValidationError
            ):
                require_kimodo_pilot_intake_report(candidate)

        with self.assertRaises(KimodoPilotIntakeValidationError):
            require_kimodo_pilot_intake_report(type("Forged", (dict,), {})(report))

        recursive: dict = {}
        recursive["nested"] = recursive
        changed = deepcopy(report)
        changed["claims"] = recursive
        with self.assertRaises(KimodoPilotIntakeValidationError):
            require_kimodo_pilot_intake_report(changed)

    def test_derived_templates_are_immutable_and_cannot_elevate_audit(self):
        with self.assertRaises(TypeError):
            CLAIMS["release_authority"] = True
        with self.assertRaises(TypeError):
            AUTHORITY["release"] = True

        report = self.audit()
        self.assertFalse(report["claims"]["release_authority"])
        self.assertFalse(report["authority"]["release"])


if __name__ == "__main__":
    unittest.main()
