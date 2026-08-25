"""Exact BVH MotionIR compile provenance schema and semantic tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
import hashlib
import json
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.bvh_motion_compile_run import (  # noqa: E402
    BvhMotionCompileRunError,
    build_bvh_motion_compile_run,
    require_bvh_motion_compile_run,
)
from autospine_workbench.bvh_motion_compiler import (  # noqa: E402
    CompiledBvhMotion,
    compile_bvh_motion,
)

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional test extra
    Draft202012Validator = None


RAW = (ROOT / "tests" / "fixtures" / "minimal_motion.bvh").read_bytes()


def mapping() -> dict:
    return {
        "format": "autospine-bvh-map",
        "format_version": 1,
        "map_id": "minimal.explicit-v1",
        "clip": {"clip_id": "minimal.motion", "loop": False},
        "basis": {
            "screen_x": "+X", "screen_y": "+Y", "depth": "+Z",
            "rotation_convention": "bvh_declared_channel_postmultiply",
        },
        "root": {
            "joint_name": "Hips",
            "reference_length_source_units": 100.0,
            "translation_policy":
                "projected_frame0_delta_normalized_reference_length",
        },
        "bones": [
            {
                "role": "humanoid.root", "joint_name": "Hips",
                "aim": {"kind": "joint", "joint_name": "Chest"},
                "rotation_policy": "projected_setup_local_delta",
            },
            {
                "role": "humanoid.spine.lower", "joint_name": "Chest",
                "aim": {"kind": "end_site"},
                "rotation_policy": "projected_setup_local_delta",
            },
        ],
        "contact": {
            "enabled": False, "mode": "annotation_only", "interval": "half_open",
        },
    }


def motion(value=None) -> dict:
    return compile_bvh_motion(RAW, value or mapping()).document


def reverse_keys(value):
    if isinstance(value, dict):
        return {key: reverse_keys(item) for key, item in reversed(list(value.items()))}
    if isinstance(value, list):
        return [reverse_keys(item) for item in value]
    return value


class BvhMotionCompileRunTests(unittest.TestCase):
    def test_schema_and_semantics_pin_all_exact_inputs(self):
        schema = json.loads(
            (ROOT / "schemas" / "bvh-motion-compile-run-v1.schema.json").read_text()
        )
        if Draft202012Validator is not None:
            Draft202012Validator.check_schema(schema)
        explicit_map = mapping()
        value = motion(explicit_map)
        run = build_bvh_motion_compile_run(RAW, explicit_map, value)

        require_bvh_motion_compile_run(
            run.document, raw_bvh=RAW, bvh_map=explicit_map, motion_ir=value
        )
        source = run.document["source"]
        canonical_map = json.dumps(
            explicit_map, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode()
        self.assertEqual(hashlib.sha256(RAW).hexdigest(), run.raw_bvh_sha256)
        self.assertEqual(hashlib.sha256(canonical_map).hexdigest(), run.bvh_map_sha256)
        self.assertEqual(len(RAW), source["raw_bvh_byte_length"])
        self.assertEqual(compile_bvh_motion(RAW, explicit_map).sha256,
                         run.motion_ir_sha256)
        self.assertEqual(
            json.dumps(run.document, ensure_ascii=False, allow_nan=False,
                       sort_keys=True, separators=(",", ":")),
            run.canonical_json,
        )
        if Draft202012Validator is not None:
            Draft202012Validator(schema).validate(run.document)

    def test_deterministic_frozen_isolated_and_non_mutating(self):
        explicit_map, value = mapping(), motion()
        map_before, motion_before = deepcopy(explicit_map), deepcopy(value)
        first = build_bvh_motion_compile_run(RAW, explicit_map, value)
        second = build_bvh_motion_compile_run(
            RAW, reverse_keys(explicit_map), reverse_keys(value)
        )

        self.assertEqual(first, second)
        self.assertEqual(map_before, explicit_map)
        self.assertEqual(motion_before, value)
        changed = first.document
        changed["compiler"]["config"].clear()
        self.assertTrue(first.document["compiler"]["config"])
        with self.assertRaises(FrozenInstanceError):
            first._canonical_json = "{}"  # type: ignore[misc]

    def test_builder_requires_exact_map_motion_and_parser_semantics(self):
        explicit_map, value = mapping(), motion()
        changed_map = deepcopy(explicit_map)
        changed_map["root"]["reference_length_source_units"] = 50.0
        changed_motion = deepcopy(value)
        changed_motion["tracks"][0]["keys"][1]["value"] = 2.0
        nonfinite = deepcopy(value)
        nonfinite["tracks"][0]["keys"][1]["value"] = math.nan
        duplicate_map = deepcopy(explicit_map)
        duplicate_map["bones"].append(deepcopy(duplicate_map["bones"][0]))
        duplicate_raw = RAW.replace(b"JOINT Chest", b"JOINT Hips")
        cases = (
            (RAW, changed_map, value),
            (RAW, explicit_map, changed_motion),
            (RAW, explicit_map, nonfinite),
            (RAW, duplicate_map, value),
            (duplicate_raw, explicit_map, value),
        )
        for raw, candidate_map, candidate_motion in cases:
            with self.subTest(candidate_map=candidate_map), self.assertRaises(
                BvhMotionCompileRunError
            ):
                build_bvh_motion_compile_run(raw, candidate_map, candidate_motion)

    def test_cross_inputs_reject_source_drift_even_when_motion_is_unchanged(self):
        explicit_map, value = mapping(), motion()
        run = build_bvh_motion_compile_run(RAW, explicit_map, value)
        whitespace_variant = RAW + b"\n"
        self.assertEqual(
            compile_bvh_motion(RAW, explicit_map).canonical_bytes,
            compile_bvh_motion(whitespace_variant, explicit_map).canonical_bytes,
        )

        with self.assertRaisesRegex(BvhMotionCompileRunError, "cross-inputs"):
            require_bvh_motion_compile_run(run.document, raw_bvh=RAW)
        with self.assertRaisesRegex(BvhMotionCompileRunError, "cross-inputs"):
            require_bvh_motion_compile_run(run.document, bvh_map=explicit_map)
        with self.assertRaisesRegex(BvhMotionCompileRunError, "source differs"):
            require_bvh_motion_compile_run(
                run.document, raw_bvh=whitespace_variant,
                bvh_map=explicit_map, motion_ir=value,
            )
        require_bvh_motion_compile_run(run.document)
        require_bvh_motion_compile_run(run.document, motion_ir=value)

    def test_unknown_types_identity_and_output_drift_fail_closed(self):
        explicit_map, value = mapping(), motion()
        baseline = build_bvh_motion_compile_run(RAW, explicit_map, value).document
        mutations = (
            lambda run: run.update(extra=True),
            lambda run: run["source"].update(extra=True),
            lambda run: run["source"].update(kind="builtin"),
            lambda run: run["source"].update(raw_bvh_sha256="A" * 64),
            lambda run: run["source"].update(raw_bvh_sha256="a" * 64),
            lambda run: run["source"].update(raw_bvh_byte_length=True),
            lambda run: run["source"].update(raw_bvh_byte_length=math.nan),
            lambda run: run["source"].update(bvh_map_sha256="b" * 64),
            lambda run: run["source"].update(map_id="other"),
            lambda run: run["source"].update(clip_id="other"),
            lambda run: run["compiler"].update(id="other"),
            lambda run: run["compiler"].update(version="1.0.1"),
            lambda run: run["compiler"]["config"].update(extra=True),
            lambda run: run["compiler"]["config"].update(ticks_per_second=1e6),
            lambda run: run["output"].update(motion_ir_sha256="c" * 64),
            lambda run: run.update(format_version=True),
        )
        for mutate in mutations:
            candidate = deepcopy(baseline)
            mutate(candidate)
            with self.subTest(candidate=candidate), self.assertRaises(
                BvhMotionCompileRunError
            ):
                require_bvh_motion_compile_run(
                    candidate, raw_bvh=RAW, bvh_map=explicit_map, motion_ir=value
                )

    def test_compiler_identity_or_algorithm_output_change_revokes_old_run(self):
        explicit_map, original = mapping(), motion()
        baseline = build_bvh_motion_compile_run(RAW, explicit_map, original)
        for field, changed in (
            ("COMPILER_VERSION", "1.0.1"),
            ("FK_PROFILE", "declared-channel-postmultiply-3d-affine-v2"),
        ):
            with self.subTest(field=field), patch(
                f"autospine_workbench.bvh_motion_compiler.{field}", changed
            ):
                rebuilt = build_bvh_motion_compile_run(RAW, explicit_map, original)
                self.assertNotEqual(baseline.sha256, rebuilt.sha256)
                with self.assertRaises(BvhMotionCompileRunError):
                    require_bvh_motion_compile_run(baseline.document)

        altered = deepcopy(original)
        altered["tracks"][0]["keys"][1]["value"] = 2.0
        encoded = json.dumps(
            altered, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        )
        changed_output = CompiledBvhMotion(encoded)
        with patch(
            "autospine_workbench.bvh_motion_compile_run.compiler_impl."
            "compile_bvh_motion",
            return_value=changed_output,
        ):
            rebuilt = build_bvh_motion_compile_run(RAW, explicit_map, altered)
            with self.assertRaises(BvhMotionCompileRunError):
                require_bvh_motion_compile_run(
                    baseline.document, raw_bvh=RAW, bvh_map=explicit_map,
                    motion_ir=original,
                )
        self.assertNotEqual(baseline.motion_ir_sha256, rebuilt.motion_ir_sha256)

    def test_canonical_body_comparison_is_not_digest_only(self):
        explicit_map, expected = mapping(), motion()
        altered = deepcopy(expected)
        altered["tracks"][0]["keys"][1]["value"] = 2.0
        digest = compile_bvh_motion(RAW, explicit_map).sha256
        with patch(
            "autospine_workbench.bvh_motion_compile_run.motion_ir_sha256",
            return_value=digest,
        ), self.assertRaisesRegex(BvhMotionCompileRunError, "canonical bytes"):
            build_bvh_motion_compile_run(RAW, explicit_map, altered)

    def test_run_byte_limit_is_enforced(self):
        explicit_map, value = mapping(), motion()
        run = build_bvh_motion_compile_run(RAW, explicit_map, value).document
        with patch(
            "autospine_workbench.bvh_motion_compile_run.MAX_RUN_BYTES", 1
        ), self.assertRaisesRegex(BvhMotionCompileRunError, "resource limit"):
            require_bvh_motion_compile_run(run)


if __name__ == "__main__":
    unittest.main()
