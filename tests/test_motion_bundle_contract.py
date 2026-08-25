"""Pure canonical built-in MotionIR bundle contract tests."""

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

from autospine_workbench.motion_builtin import build_builtin_motion  # noqa: E402
from autospine_workbench.motion_bundle_contract import (  # noqa: E402
    BUNDLE_ADDRESS_DOMAIN,
    DOCUMENT_NAMES,
    MotionBundleContractError,
    build_motion_bundle_contract,
    motion_bundle_address_sha256,
)
from autospine_workbench.motion_compile_run import (  # noqa: E402
    build_builtin_motion_compile_run,
)


GOLDEN_BUNDLES = {
    "idle": (
        "e19e0885420378c51e0a6c9cd775b880bb3708bf793ea4c87d53dce44848f85d",
        "685594dd49cd5ff9bb91106babccf2bddb55d2acbed424c82f1ebdba9ef4342a",
        "63c4accf690c361be8ca6146071ef95621897874d436586081c0f3fba08199ec",
    ),
    "wave.left": (
        "d054364dd9d6118814ba7623e5a0716102bfa8610d3d78dbcdabbe396a82c9d1",
        "be0a28ab45077e3f69ad565c6f13230d1d61c8205b86eeb9a2327fe295fe9e05",
        "c9099e7302686df1936f037796194c6055e02a3bbcccc98e151c56aca63c94d1",
    ),
}


def payload(clip_id="idle"):
    motion = build_builtin_motion(clip_id).document
    run = build_builtin_motion_compile_run(clip_id, motion).document
    return motion, run


def reverse_keys(value):
    if isinstance(value, dict):
        return {
            key: reverse_keys(item)
            for key, item in reversed(list(value.items()))
        }
    if isinstance(value, list):
        return [reverse_keys(item) for item in value]
    return value


class MotionBundleContractTests(unittest.TestCase):
    def test_original_builtin_addresses_are_bit_for_bit_golden(self) -> None:
        for clip_id, expected in GOLDEN_BUNDLES.items():
            contract = build_motion_bundle_contract(*payload(clip_id))
            with self.subTest(clip_id=clip_id):
                self.assertEqual(expected, (
                    contract.clip_sha256,
                    contract.run_sha256,
                    contract.bundle_sha256,
                ))
                self.assertEqual("builtin", contract.source_kind)
                self.assertIsNone(contract.raw_bvh)
                self.assertIsNone(contract.bvh_map)

    def test_bundle_is_canonical_deterministic_frozen_and_isolated(self) -> None:
        values = payload()
        before = deepcopy(values)
        first = build_motion_bundle_contract(*values)
        second = build_motion_bundle_contract(*tuple(reverse_keys(v) for v in values))

        self.assertEqual(first, second)
        self.assertEqual(before, values)
        self.assertEqual(DOCUMENT_NAMES, first.inventory)
        self.assertEqual(values[0], first.motion)
        self.assertEqual(values[1], first.run_manifest)
        self.assertEqual(
            hashlib.sha256(first.document_bytes["motion.json"]).hexdigest(),
            first.clip_sha256,
        )
        self.assertEqual(
            hashlib.sha256(first.document_bytes["run-manifest.json"]).hexdigest(),
            first.run_sha256,
        )
        items = tuple((name, first.document_bytes[name]) for name in DOCUMENT_NAMES)
        self.assertEqual(motion_bundle_address_sha256(items), first.bundle_sha256)
        changed_bytes, changed_motion = first.document_bytes, first.motion
        changed_bytes.clear()
        changed_motion.clear()
        self.assertEqual(2, len(first.document_bytes))
        self.assertTrue(first.motion)
        with self.assertRaises(FrozenInstanceError):
            first.bundle_sha256 = "0" * 64  # type: ignore[misc]

    def test_address_binds_domain_filename_order_length_and_bytes(self) -> None:
        contract = build_motion_bundle_contract(*payload())
        items = tuple((name, contract.document_bytes[name]) for name in DOCUMENT_NAMES)
        baseline = motion_bundle_address_sha256(items)
        changed_bytes = (items[0], (items[1][0], items[1][1] + b" "))
        self.assertNotEqual(baseline, motion_bundle_address_sha256(changed_bytes))
        with patch(
            "autospine_workbench.motion_bundle_contract.BUNDLE_ADDRESS_DOMAIN",
            BUNDLE_ADDRESS_DOMAIN + b"/changed",
        ):
            self.assertNotEqual(baseline, motion_bundle_address_sha256(items))
        invalid = (
            tuple(reversed(items)),
            (("motion.json", items[0][1]), ("motion.json", items[1][1])),
            (("Motion.json", items[0][1]), items[1]),
            (("motion.json", bytearray(items[0][1])), items[1]),
        )
        for value in invalid:
            with self.subTest(value=value[0][0]), self.assertRaises(
                MotionBundleContractError
            ):
                motion_bundle_address_sha256(value)  # type: ignore[arg-type]

    def test_motion_run_builtin_and_output_must_be_exactly_cross_bound(self) -> None:
        idle, idle_run = payload("idle")
        _wave, wave_run = payload("wave.left")
        output = deepcopy(idle_run)
        output["output"]["motion_ir_sha256"] = "a" * 64
        source = deepcopy(idle_run)
        source["source"]["builtin_id"] = "wave.left"
        for run in (wave_run, output, source):
            with self.subTest(source=run["source"]), self.assertRaises(
                MotionBundleContractError
            ):
                build_motion_bundle_contract(idle, run)

    def test_algorithm_or_config_change_changes_run_and_bundle_not_clip(self) -> None:
        value = build_builtin_motion("idle").document
        baseline = build_motion_bundle_contract(
            value, build_builtin_motion_compile_run("idle", value).document
        )
        with patch(
            "autospine_workbench.motion_compile_run.COMPILER_VERSION", "1.0.1"
        ):
            run = build_builtin_motion_compile_run("idle", value).document
            changed = build_motion_bundle_contract(value, run)
        self.assertEqual(baseline.clip_sha256, changed.clip_sha256)
        self.assertNotEqual(baseline.run_sha256, changed.run_sha256)
        self.assertNotEqual(baseline.bundle_sha256, changed.bundle_sha256)

    def test_unknown_nonfinite_and_resource_overflow_fail_closed(self) -> None:
        baseline = payload()
        extra_motion = deepcopy(baseline)
        extra_motion[0]["extra"] = True
        nonfinite = deepcopy(baseline)
        nonfinite[0]["tracks"][0]["keys"][0]["value"] = math.nan
        extra_run = deepcopy(baseline)
        extra_run[1]["extra"] = True
        for values in (extra_motion, nonfinite, extra_run):
            with self.assertRaises(MotionBundleContractError):
                build_motion_bundle_contract(*values)
        limits = (
            "MAX_MOTION_BYTES", "MAX_RUN_BYTES", "MAX_TOTAL_DOCUMENT_BYTES",
        )
        for field in limits:
            with (
                self.subTest(field=field),
                patch(f"autospine_workbench.motion_bundle_contract.{field}", 1),
                self.assertRaisesRegex(MotionBundleContractError, "resource limit"),
            ):
                build_motion_bundle_contract(*baseline)


if __name__ == "__main__":
    unittest.main()
