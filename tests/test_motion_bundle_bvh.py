"""Immutable MotionBundle coverage for exact, explicitly mapped BVH sources."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.bvh_motion_compile_run import (  # noqa: E402
    build_bvh_motion_compile_run,
)
from autospine_workbench.bvh_motion_compiler import compile_bvh_motion  # noqa: E402
from autospine_workbench.motion_bundle_contract import (  # noqa: E402
    BVH_DOCUMENT_NAMES,
    MotionBundleContractError,
    build_motion_bundle_contract,
)
from autospine_workbench.motion_bundle_integrity import (  # noqa: E402
    MotionBundleIntegrityError,
    MotionBundleSnapshot,
    verify_motion_bundle_snapshot,
)
from autospine_workbench.motion_bundle_reader import (  # noqa: E402
    VerifiedMotionBundleReader,
    VerifiedMotionBundleReaderError,
)
from autospine_workbench.motion_bundle_store import (  # noqa: E402
    MotionBundleStore,
    MotionBundleStoreError,
)
from tests.test_bvh_motion_compile_run import (  # noqa: E402
    RAW,
    mapping,
    reverse_keys,
)


class BvhBundleFixture:
    def __init__(self, root: Path, raw: bytes = RAW, explicit_map=None) -> None:
        self.state = root / "state"
        self.raw = raw
        self.mapping = deepcopy(explicit_map or mapping())
        self.motion = compile_bvh_motion(raw, self.mapping).document
        self.run = build_bvh_motion_compile_run(
            raw, self.mapping, self.motion,
        ).document
        self.contract = build_motion_bundle_contract(
            self.motion, self.run, raw_bvh=raw, bvh_map=self.mapping,
        )
        self.store = MotionBundleStore(self.state)

    def publish(self):
        return self.store.publish(
            self.motion, self.run, raw_bvh=self.raw, bvh_map=self.mapping,
        )

    def load(self):
        return VerifiedMotionBundleReader(self.state).load(
            self.contract.clip_sha256, self.contract.bundle_sha256,
        )


class MotionBundleBvhTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_bvh_contract_is_canonical_cross_bound_and_isolated(self):
        fixture = BvhBundleFixture(self.root)
        reordered = build_motion_bundle_contract(
            reverse_keys(fixture.motion), reverse_keys(fixture.run),
            raw_bvh=fixture.raw, bvh_map=reverse_keys(fixture.mapping),
        )
        self.assertEqual(fixture.contract, reordered)
        self.assertEqual(BVH_DOCUMENT_NAMES, fixture.contract.inventory)
        self.assertEqual("bvh", fixture.contract.source_kind)
        self.assertEqual(RAW, fixture.contract.raw_bvh)
        self.assertEqual(fixture.mapping, fixture.contract.bvh_map)
        self.assertEqual(fixture.motion, fixture.contract.motion)
        changed = fixture.contract.bvh_map
        changed.clear()
        self.assertTrue(fixture.contract.bvh_map)
        with self.assertRaises(FrozenInstanceError):
            fixture.contract.source_kind = "builtin"  # type: ignore[misc]

        with self.assertRaisesRegex(MotionBundleContractError, "together"):
            build_motion_bundle_contract(
                fixture.motion, fixture.run, raw_bvh=fixture.raw,
            )
        with self.assertRaisesRegex(MotionBundleContractError, "immutable bytes"):
            build_motion_bundle_contract(
                fixture.motion, fixture.run,
                raw_bvh=bytearray(fixture.raw),  # type: ignore[arg-type]
                bvh_map=fixture.mapping,
            )

        limits = (
            ("MAX_BVH_BYTES", len(fixture.raw) - 1),
            ("MAX_BVH_MAP_BYTES", 1),
            ("MAX_BVH_TOTAL_DOCUMENT_BYTES", 1),
        )
        for field, limit in limits:
            with self.subTest(field=field), patch(
                f"autospine_workbench.motion_bundle_contract.{field}", limit,
            ), self.assertRaisesRegex(MotionBundleContractError, "resource limit"):
                build_motion_bundle_contract(
                    fixture.motion, fixture.run,
                    raw_bvh=fixture.raw, bvh_map=fixture.mapping,
                )

    def test_publish_read_and_reuse_preserve_all_four_exact_documents(self):
        fixture = BvhBundleFixture(self.root)
        first = fixture.publish()
        second = fixture.store.publish(
            reverse_keys(fixture.motion), reverse_keys(fixture.run),
            raw_bvh=fixture.raw, bvh_map=reverse_keys(fixture.mapping),
        )
        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        self.assertEqual(first.path, second.path)
        self.assertEqual(
            self.root / "state" / "motions" / fixture.contract.clip_sha256
            / fixture.contract.bundle_sha256,
            first.path,
        )
        self.assertEqual(
            fixture.contract.document_bytes,
            {path.name: path.read_bytes() for path in first.path.iterdir()},
        )

        verified = fixture.load()
        self.assertEqual("bvh", verified.source_kind)
        self.assertEqual(BVH_DOCUMENT_NAMES, verified.inventory)
        self.assertEqual(fixture.raw, verified.raw_bvh)
        self.assertEqual(fixture.mapping, verified.bvh_map)
        self.assertEqual(fixture.motion, verified.motion)
        self.assertEqual(fixture.run, verified.run_manifest)
        changed = verified.bvh_map
        changed.clear()
        self.assertTrue(verified.bvh_map)

    def test_each_document_tamper_and_whitespace_drift_fail_closed(self):
        mutations = {
            "source.bvh": lambda data: data + b"\n",
            "map.json": lambda data: data + b"\n",
            "motion.json": lambda data: data + b"\n",
            "run-manifest.json": lambda data: data + b"\n",
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                fixture = BvhBundleFixture(Path(directory))
                path = fixture.publish().path / name
                path.write_bytes(mutate(path.read_bytes()))
                with self.assertRaises(VerifiedMotionBundleReaderError):
                    fixture.load()
                with self.assertRaises(MotionBundleStoreError):
                    fixture.publish()

    def test_raw_and_map_drift_require_recompile_and_new_bundle_address(self):
        baseline = BvhBundleFixture(self.root / "baseline")
        raw_variant = RAW + b"\n"
        self.assertEqual(
            baseline.motion,
            compile_bvh_motion(raw_variant, baseline.mapping).document,
        )
        with self.assertRaises(MotionBundleContractError):
            build_motion_bundle_contract(
                baseline.motion, baseline.run,
                raw_bvh=raw_variant, bvh_map=baseline.mapping,
            )
        raw_recompiled = BvhBundleFixture(
            self.root / "raw-variant", raw=raw_variant,
        )
        self.assertEqual(baseline.contract.clip_sha256,
                         raw_recompiled.contract.clip_sha256)
        self.assertNotEqual(baseline.contract.run_sha256,
                            raw_recompiled.contract.run_sha256)
        self.assertNotEqual(baseline.contract.bundle_sha256,
                            raw_recompiled.contract.bundle_sha256)

        changed_map = deepcopy(baseline.mapping)
        changed_map["map_id"] = "minimal.explicit-v2"
        self.assertEqual(
            baseline.motion, compile_bvh_motion(RAW, changed_map).document,
        )
        with self.assertRaises(MotionBundleContractError):
            build_motion_bundle_contract(
                baseline.motion, baseline.run,
                raw_bvh=RAW, bvh_map=changed_map,
            )
        map_recompiled = BvhBundleFixture(
            self.root / "map-variant", explicit_map=changed_map,
        )
        self.assertEqual(baseline.contract.clip_sha256,
                         map_recompiled.contract.clip_sha256)
        self.assertNotEqual(baseline.contract.bundle_sha256,
                            map_recompiled.contract.bundle_sha256)

    def test_mixed_extra_missing_case_and_alias_inventory_are_rejected(self):
        mutations = (
            lambda root: (root / "extra.json").write_bytes(b"{}"),
            lambda root: (root / "map.json").unlink(),
            _case_source,
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate), tempfile.TemporaryDirectory() as directory:
                fixture = BvhBundleFixture(Path(directory))
                mutate(fixture.publish().path)
                with self.assertRaises(VerifiedMotionBundleReaderError):
                    fixture.load()

        fixture = BvhBundleFixture(self.root / "alias")
        bundle = fixture.publish().path
        source, outside = bundle / "source.bvh", bundle.parent / "outside.bvh"
        shutil.copyfile(source, outside)
        source.unlink()
        try:
            source.symlink_to(outside)
        except OSError:
            return
        with self.assertRaises(VerifiedMotionBundleReaderError):
            fixture.load()

    def test_direct_snapshot_rejects_cross_inventory_and_order_aliases(self):
        fixture = BvhBundleFixture(self.root)
        bundle = fixture.publish().path
        items = tuple(
            (name, (bundle / name).read_bytes()) for name in BVH_DOCUMENT_NAMES
        )
        invalid = (
            tuple(reversed(items)),
            items[1:],
            (("source.bvh", items[0][1]),) + (
                ("motion.json", items[2][1]),
                ("run-manifest.json", items[3][1]),
            ),
        )
        for value in invalid:
            with self.subTest(names=tuple(name for name, _ in value)), \
                    self.assertRaises(MotionBundleIntegrityError):
                verify_motion_bundle_snapshot(
                    MotionBundleSnapshot(bundle, value),
                    expected_clip_sha256=fixture.contract.clip_sha256,
                    expected_bundle_sha256=fixture.contract.bundle_sha256,
                )


def _case_source(root: Path) -> None:
    source = root / "source.bvh"
    temporary = root / "temporary"
    source.rename(temporary)
    temporary.rename(root / "SOURCE.BVH")


if __name__ == "__main__":
    unittest.main()
