"""Built-in MotionIR compile provenance schema and semantic tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
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

from autospine_workbench.motion_builtin import (  # noqa: E402
    BuiltinMotion,
    build_builtin_motion,
)
from autospine_workbench.motion_compile_run import (  # noqa: E402
    MotionCompileRunError,
    build_builtin_motion_compile_run,
    require_motion_compile_run,
)

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional test extra
    Draft202012Validator = None


def motion(clip_id="idle"):
    return build_builtin_motion(clip_id).document


def reverse_keys(value):
    if isinstance(value, dict):
        return {
            key: reverse_keys(item)
            for key, item in reversed(list(value.items()))
        }
    if isinstance(value, list):
        return [reverse_keys(item) for item in value]
    return value


class MotionCompileRunTests(unittest.TestCase):
    def test_schema_and_semantics_pin_the_exact_builtin_provenance(self) -> None:
        schema = json.loads(
            (ROOT / "schemas" / "motion-compile-run-v1.schema.json").read_text()
        )
        if Draft202012Validator is not None:
            Draft202012Validator.check_schema(schema)
        for clip_id in ("idle", "wave.left"):
            value = motion(clip_id)
            run = build_builtin_motion_compile_run(clip_id, value)
            with self.subTest(clip_id=clip_id):
                require_motion_compile_run(run.document, motion_ir=value)
                self.assertEqual(clip_id, run.builtin_id)
                self.assertEqual(
                    build_builtin_motion(clip_id).sha256,
                    run.motion_ir_sha256,
                )
                self.assertEqual(
                    run.canonical_json,
                    json.dumps(
                        run.document, ensure_ascii=False, allow_nan=False,
                        sort_keys=True, separators=(",", ":"),
                    ),
                )
                if Draft202012Validator is not None:
                    Draft202012Validator(schema).validate(run.document)

    def test_deterministic_frozen_isolated_and_non_mutating(self) -> None:
        value = motion()
        before = deepcopy(value)
        first = build_builtin_motion_compile_run("idle", value)
        second = build_builtin_motion_compile_run("idle", reverse_keys(value))

        self.assertEqual(first, second)
        self.assertEqual(before, value)
        changed = first.document
        changed["compiler"]["config"].clear()
        self.assertTrue(first.document["compiler"]["config"])
        with self.assertRaises(FrozenInstanceError):
            first._canonical_json = "{}"  # type: ignore[misc]

    def test_motion_body_or_builtin_identity_drift_cannot_issue_a_run(self) -> None:
        altered = motion()
        altered["tracks"][0]["keys"][1]["value"] = -2.0
        nonfinite = motion()
        nonfinite["tracks"][0]["keys"][0]["value"] = math.nan
        cases = (
            ("idle", altered),
            ("wave.left", motion("idle")),
            ("unknown", motion("idle")),
            ("idle", nonfinite),
        )
        for values in cases:
            with self.subTest(values=values[0]), self.assertRaises(
                MotionCompileRunError
            ):
                build_builtin_motion_compile_run(*values)

    def test_unknown_duplicate_semantics_and_output_drift_fail_closed(self) -> None:
        baseline = build_builtin_motion_compile_run("idle", motion()).document
        mutations = (
            lambda value: value.update(extra=True),
            lambda value: value["source"].update(extra=True),
            lambda value: value["source"].update(kind="bvh"),
            lambda value: value["source"].update(builtin_id="wave.left"),
            lambda value: value["compiler"].update(id="other"),
            lambda value: value["compiler"].update(version="1.0.1"),
            lambda value: value["compiler"]["config"].update(profile="other"),
            lambda value: value["output"].update(motion_ir_sha256="A" * 64),
            lambda value: value["output"].update(motion_ir_sha256="a" * 64),
            lambda value: value.update(format_version=True),
        )
        for mutate in mutations:
            value = deepcopy(baseline)
            mutate(value)
            with self.subTest(value=value), self.assertRaises(MotionCompileRunError):
                require_motion_compile_run(value, motion_ir=motion())

    def test_algorithm_or_config_change_changes_sha_and_revokes_old_run(self) -> None:
        value = motion()
        baseline = build_builtin_motion_compile_run("idle", value)
        targets = (
            ("COMPILER_VERSION", "1.0.1"),
            ("BUILTIN_PROFILE", "autospine-builtins-v2"),
        )
        for field, changed in targets:
            with self.subTest(field=field), patch(
                f"autospine_workbench.motion_compile_run.{field}", changed
            ):
                rebuilt = build_builtin_motion_compile_run("idle", value)
                self.assertNotEqual(baseline.sha256, rebuilt.sha256)
                with self.assertRaises(MotionCompileRunError):
                    require_motion_compile_run(baseline.document, motion_ir=value)

    def test_changed_builtin_output_is_rebuilt_and_revokes_old_provenance(self) -> None:
        original = motion()
        baseline = build_builtin_motion_compile_run("idle", original)
        changed = motion()
        changed["tracks"][0]["keys"][1]["value"] = -2.0
        encoded = json.dumps(
            changed, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        )
        rebuilt_builtin = BuiltinMotion(encoded)

        with patch(
            "autospine_workbench.motion_compile_run.build_builtin_motion",
            return_value=rebuilt_builtin,
        ):
            rebuilt = build_builtin_motion_compile_run("idle", changed)
            with self.assertRaises(MotionCompileRunError):
                require_motion_compile_run(baseline.document, motion_ir=original)
        self.assertNotEqual(baseline.sha256, rebuilt.sha256)

    def test_run_byte_limit_is_enforced(self) -> None:
        run = build_builtin_motion_compile_run("idle", motion()).document
        with patch("autospine_workbench.motion_compile_run.MAX_RUN_BYTES", 1):
            with self.assertRaisesRegex(MotionCompileRunError, "resource limit"):
                require_motion_compile_run(run, motion_ir=motion())


if __name__ == "__main__":
    unittest.main()
