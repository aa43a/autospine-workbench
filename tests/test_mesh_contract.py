"""Pinned P3 mesh compile-run and base P2 profile contracts."""

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

from autospine_workbench.mesh_contract import (  # noqa: E402
    MeshContractError,
    build_mesh_compile_run,
    mesh_compile_run_sha256,
    require_base_region_rig,
    require_mesh_compile_run,
)
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from tests.test_region_rig import compile_fixture  # noqa: E402

try:
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import ValidationError
except ImportError:  # pragma: no cover - optional test extra
    Draft202012Validator = None
    ValidationError = Exception


BASE_BUNDLE_SHA = "d" * 64


def base_documents() -> tuple[dict, dict]:
    result = compile_fixture()
    return result.rig, result.run_manifest


def mesh_run() -> dict:
    rig, run = base_documents()
    return build_mesh_compile_run(
        rig,
        run,
        base_bundle_sha256=BASE_BUNDLE_SHA,
    )


class MeshCompileRunSchemaTests(unittest.TestCase):
    def test_schema_is_valid_draft_2020_12_and_accepts_contract(self) -> None:
        schema = json.loads(
            (ROOT / "schemas" / "mesh-rig-compile-run-v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
        self.assertTrue(schema["$id"].endswith("mesh-rig-compile-run-v1.schema.json"))
        if Draft202012Validator is not None:
            Draft202012Validator.check_schema(schema)
            Draft202012Validator(schema).validate(mesh_run())

    @unittest.skipIf(Draft202012Validator is None, "install the test extra")
    def test_schema_rejects_unknown_fields_and_changed_thresholds(self) -> None:
        schema = json.loads(
            (ROOT / "schemas" / "mesh-rig-compile-run-v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        validator = Draft202012Validator(schema)
        for mutate in (
            lambda value: value.update(unexpected=True),
            lambda value: value["compiler"]["config"].update(alpha_threshold=16),
            lambda value: value["compiler"]["config"]["resource_limits"].update(
                attachment_max_vertices=4097
            ),
            lambda value: value["compiler"]["config"]["geometry_contract"].update(
                vertex_space="attachment-local-center-px"
            ),
        ):
            changed = mesh_run()
            mutate(changed)
            with self.subTest(changed=changed), self.assertRaises(ValidationError):
                validator.validate(changed)


class MeshCompileRunContractTests(unittest.TestCase):
    def test_builder_pins_profile_geometry_limits_and_base_identity(self) -> None:
        rig, base_run = base_documents()
        result = build_mesh_compile_run(
            rig,
            base_run,
            base_bundle_sha256=BASE_BUNDLE_SHA,
        )

        require_mesh_compile_run(result, base_rig=rig, base_run=base_run)
        self.assertEqual("autospine-mesh-rig-compile-run", result["format"])
        self.assertEqual(1, result["format_version"])
        self.assertEqual(
            {
                "base_rig_sha256": canonical_sha256(rig),
                "base_bundle_sha256": BASE_BUNDLE_SHA,
                "layer_manifest_sha256": base_run["inputs"]["layer_manifest_sha256"],
                "resolved_project_sha256": base_run["inputs"]["resolved_project_sha256"],
            },
            result["inputs"],
        )
        self.assertEqual(
            {
                "profile": "hinge-alpha-grid-two-bone-v1",
                "strict": True,
                "alpha_threshold": 8,
                "grid_step_px": 8,
                "blend_fraction": 0.20,
                "weight_quantization": "uint16-65535",
                "resource_limits": {
                    "attachment_max_vertices": 4096,
                    "attachment_max_triangles": 8192,
                    "rig_max_vertices": 32768,
                    "rig_max_triangles": 65536,
                },
                "geometry_contract": {
                    "vertex_space": "source-raster-edge-px",
                    "setup_world": "canvas-offset-plus-vertex",
                    "uv_space": "normalized-top-left",
                    "triangle_winding": "clockwise-canvas-y-down",
                    "skinning": "linear-blend-inverse-setup-v1",
                },
            },
            result["compiler"]["config"],
        )

    def test_builder_is_deterministic_non_mutating_and_canonically_addressed(self) -> None:
        rig, base_run = base_documents()
        original_rig, original_run = deepcopy(rig), deepcopy(base_run)

        first = build_mesh_compile_run(rig, base_run, base_bundle_sha256=BASE_BUNDLE_SHA)
        second = build_mesh_compile_run(
            dict(reversed(list(rig.items()))),
            dict(reversed(list(base_run.items()))),
            base_bundle_sha256=BASE_BUNDLE_SHA,
        )

        self.assertEqual(first, second)
        self.assertEqual(canonical_sha256(first), mesh_compile_run_sha256(first))
        self.assertEqual(original_rig, rig)
        self.assertEqual(original_run, base_run)

    def test_hash_fields_thresholds_and_geometry_are_fail_closed(self) -> None:
        rig, base_run = base_documents()
        mutations = (
            lambda value: value["inputs"].update(base_rig_sha256="0" * 64),
            lambda value: value["inputs"].update(base_bundle_sha256="latest"),
            lambda value: value["compiler"].update(version="latest"),
            lambda value: value["compiler"]["config"].update(alpha_threshold=8.0),
            lambda value: value["compiler"]["config"].update(grid_step_px=4),
            lambda value: value["compiler"]["config"].update(blend_fraction=0.21),
            lambda value: value["compiler"]["config"].update(
                weight_quantization="float32"
            ),
            lambda value: value["compiler"]["config"]["resource_limits"].update(
                rig_max_triangles=65535
            ),
            lambda value: value["compiler"]["config"]["geometry_contract"].update(
                vertex_space="attachment-local-center-px"
            ),
            lambda value: value["compiler"]["config"]["geometry_contract"].update(
                setup_world="bone-local"
            ),
            lambda value: value["compiler"]["config"]["geometry_contract"].update(
                uv_space="normalized-bottom-left"
            ),
            lambda value: value["compiler"]["config"]["geometry_contract"].update(
                triangle_winding="counter-clockwise-canvas-y-down"
            ),
            lambda value: value["compiler"]["config"]["geometry_contract"].update(
                skinning="linear-blend-current-world-v1"
            ),
            lambda value: value["compiler"]["config"].update(unexpected=True),
        )
        for mutate in mutations:
            changed = build_mesh_compile_run(
                rig, base_run, base_bundle_sha256=BASE_BUNDLE_SHA
            )
            mutate(changed)
            with self.subTest(changed=changed), self.assertRaises(MeshContractError):
                require_mesh_compile_run(
                    changed,
                    base_rig=rig,
                    base_run=base_run,
                )

    def test_binding_validation_detects_a_different_base(self) -> None:
        rig, base_run = base_documents()
        contract = build_mesh_compile_run(
            rig, base_run, base_bundle_sha256=BASE_BUNDLE_SHA
        )
        changed_rig = deepcopy(rig)
        changed_rig["qa"]["checks"].append(
            {"id": "different", "status": "passed"}
        )
        with self.assertRaisesRegex(MeshContractError, "base RigIR"):
            require_mesh_compile_run(
                contract,
                base_rig=changed_rig,
                base_run=base_run,
            )
        with self.assertRaisesRegex(MeshContractError, "together"):
            require_mesh_compile_run(contract, base_rig=rig)

    def test_optional_bundle_binding_is_independent_and_strict(self) -> None:
        rig, base_run = base_documents()
        contract = build_mesh_compile_run(
            rig, base_run, base_bundle_sha256=BASE_BUNDLE_SHA
        )

        require_mesh_compile_run(
            contract,
            base_bundle_sha256=BASE_BUNDLE_SHA,
        )
        require_mesh_compile_run(
            contract,
            base_rig=rig,
            base_run=base_run,
            base_bundle_sha256=BASE_BUNDLE_SHA,
        )
        require_mesh_compile_run(contract, base_bundle_sha256=None)

        with self.assertRaisesRegex(MeshContractError, "base bundle binding"):
            require_mesh_compile_run(
                contract,
                base_bundle_sha256="e" * 64,
            )
        for invalid in ("latest", 7, True):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(
                MeshContractError, "base bundle SHA-256"
            ):
                require_mesh_compile_run(
                    contract,
                    base_bundle_sha256=invalid,  # type: ignore[arg-type]
                )


class BaseRegionRigProfileTests(unittest.TestCase):
    def test_reviewed_region_only_base_is_accepted(self) -> None:
        rig, run = base_documents()
        identity = require_base_region_rig(rig, run)
        self.assertEqual(canonical_sha256(rig), identity["base_rig_sha256"])
        self.assertEqual(run["inputs"]["layer_manifest_sha256"], identity["layer_manifest_sha256"])
        self.assertEqual(run["inputs"]["resolved_project_sha256"], identity["resolved_project_sha256"])

    def test_non_region_unreviewed_or_unbound_base_is_rejected(self) -> None:
        cases = {
            "capabilities": lambda rig, run: rig.update(
                capabilities=["setup_draw_order", "region_attachment"]
            ),
            "attachments": lambda rig, run: rig["attachments"][0].update(type="mesh"),
            "animations": lambda rig, run: rig.update(
                animations=[{"id": "premature"}]
            ),
            "QA": lambda rig, run: rig["qa"].update(status="manual_required"),
            "manual": lambda rig, run: run["compiler"]["config"].update(
                allow_manual_required=True
            ),
            "compiler": lambda rig, run: run["compiler"].update(id="latest"),
            "run manifest": lambda rig, run: rig["source"].update(
                run_manifest_sha256="0" * 64
            ),
            "layer manifest": lambda rig, run: run["inputs"].update(
                layer_manifest_sha256="e" * 64
            ),
        }
        for message, mutate in cases.items():
            rig, run = base_documents()
            mutate(rig, run)
            with self.subTest(message=message), self.assertRaises(
                MeshContractError,
                msg=message,
            ):
                require_base_region_rig(rig, run)


if __name__ == "__main__":
    unittest.main()
