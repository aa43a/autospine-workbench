"""Exact source, algorithm, validation, and output provenance tests for P7."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.kimodo_npz_compile_run import (  # noqa: E402
    KimodoNpzCompileRunError,
    build_kimodo_npz_compile_run,
    require_kimodo_npz_compile_run,
)
from autospine_workbench.kimodo_npz_compiler import (  # noqa: E402
    compile_kimodo_npz_motion,
)
from tests.fixtures.kimodo_npz_archive import (  # noqa: E402
    build_npz,
    motion_member_bytes,
)
from tests.kimodo_npz_helpers import map_document, source_document  # noqa: E402

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional test extra
    Draft202012Validator = None


def fixture(*, inventory="complete-v1"):
    raw = build_npz(motion_member_bytes(inventory=inventory))
    source = source_document(raw, inventory=inventory)
    mapping = map_document()
    motion = compile_kimodo_npz_motion(raw, source, mapping).document
    return raw, source, mapping, motion


class KimodoNpzCompileRunTests(unittest.TestCase):
    def test_schema_and_semantics_pin_every_exact_input(self):
        raw, source, mapping, motion = fixture()
        run = build_kimodo_npz_compile_run(raw, source, mapping, motion)
        require_kimodo_npz_compile_run(
            run.document, raw_npz=raw, source=source,
            mapping=mapping, motion_ir=motion,
        )
        schema = json.loads((
            ROOT / "schemas" / "kimodo-npz-motion-compile-run-v1.schema.json"
        ).read_text(encoding="utf-8"))
        if Draft202012Validator is not None:
            Draft202012Validator.check_schema(schema)
            Draft202012Validator(schema).validate(run.document)
        self.assertEqual("kimodo_npz", run.document["source"]["kind"])
        self.assertEqual(5, run.document["compiler"]["config"]["decimal_places"])

    def test_same_motion_different_exact_source_has_different_run(self):
        complete = fixture(inventory="complete-v1")
        core = fixture(inventory="core-v1")
        self.assertEqual(complete[3], core[3])
        complete_run = build_kimodo_npz_compile_run(*complete)
        core_run = build_kimodo_npz_compile_run(*core)
        self.assertNotEqual(complete_run.sha256, core_run.sha256)
        self.assertNotEqual(
            complete_run.document["source"]["array_inventory_sha256"],
            core_run.document["source"]["array_inventory_sha256"],
        )

    def test_sidecar_claim_drift_changes_run_even_when_motion_is_unchanged(self):
        raw, source, mapping, motion = fixture()
        baseline = build_kimodo_npz_compile_run(raw, source, mapping, motion)
        changed = deepcopy(source)
        changed["producer"]["reason_code"] = "legacy_export"
        self.assertEqual(
            motion, compile_kimodo_npz_motion(raw, changed, mapping).document
        )
        rebuilt = build_kimodo_npz_compile_run(raw, changed, mapping, motion)
        self.assertNotEqual(baseline.sha256, rebuilt.sha256)
        with self.assertRaisesRegex(KimodoNpzCompileRunError, "cross-inputs"):
            require_kimodo_npz_compile_run(
                baseline.document, raw_npz=raw, source=changed,
                mapping=mapping, motion_ir=motion,
            )

    def test_partial_cross_inputs_unknown_fields_and_metrics_fail_closed(self):
        raw, source, mapping, motion = fixture()
        baseline = build_kimodo_npz_compile_run(
            raw, source, mapping, motion
        ).document
        with self.assertRaisesRegex(KimodoNpzCompileRunError, "together"):
            require_kimodo_npz_compile_run(baseline, raw_npz=raw)
        mutations = (
            lambda value: value.update(extra=True),
            lambda value: value["source"].update(extra=True),
            lambda value: value["source"].update(kind="bvh"),
            lambda value: value["source"].update(raw_npz_sha256="A" * 64),
            lambda value: value["source"].update(raw_npz_byte_length=True),
            lambda value: value["validation"].update(
                max_position_error_meters=1.0
            ),
            lambda value: value["validation"].update(
                max_heading_norm_error=float("nan")
            ),
            lambda value: value["output"].update(motion_ir_sha256="A" * 64),
        )
        for mutate in mutations:
            candidate = deepcopy(baseline)
            mutate(candidate)
            with self.subTest(candidate=candidate), self.assertRaises(
                KimodoNpzCompileRunError
            ):
                require_kimodo_npz_compile_run(candidate)

    def test_compiler_identity_change_revokes_old_run(self):
        raw, source, mapping, motion = fixture()
        baseline = build_kimodo_npz_compile_run(raw, source, mapping, motion)
        for field, changed in (
            ("COMPILER_VERSION", "1.0.1"),
            ("PROJECTION_PROFILE", "changed-v2"),
        ):
            with self.subTest(field=field), patch(
                f"autospine_workbench.kimodo_npz_compiler.{field}", changed
            ):
                rebuilt = build_kimodo_npz_compile_run(raw, source, mapping, motion)
                self.assertNotEqual(baseline.sha256, rebuilt.sha256)
                with self.assertRaises(KimodoNpzCompileRunError):
                    require_kimodo_npz_compile_run(baseline.document)

    def test_canonical_motion_body_not_only_digest_is_required(self):
        raw, source, mapping, motion = fixture()
        changed = deepcopy(motion)
        changed["tracks"][0]["keys"][1]["value"] = 1.0
        with patch(
            "autospine_workbench.kimodo_npz_compile_run.motion_ir_sha256",
            return_value=compile_kimodo_npz_motion(raw, source, mapping).sha256,
        ), self.assertRaisesRegex(KimodoNpzCompileRunError, "canonical bytes"):
            build_kimodo_npz_compile_run(raw, source, mapping, changed)


if __name__ == "__main__":
    unittest.main()
