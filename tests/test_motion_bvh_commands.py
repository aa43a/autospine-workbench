"""Safe service-level compilation and verification for BVH MotionBundles."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.motion_builtin import build_builtin_motion  # noqa: E402
from autospine_workbench.motion_bvh_commands import (  # noqa: E402
    BvhMotionCommandError,
    compile_bvh_motion_bundle,
    verify_bvh_motion_bundle,
)
from autospine_workbench.motion_bundle_store import MotionBundleStore  # noqa: E402
from autospine_workbench.motion_compile_run import (  # noqa: E402
    build_builtin_motion_compile_run,
)
from tests.test_bvh_motion_compile_run import RAW, mapping  # noqa: E402


def canonical(value: dict) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode()


def identity(result) -> tuple:
    return (
        result.clip_id, result.map_id, result.raw_bvh_sha256,
        result.raw_bvh_byte_length, result.bvh_map_sha256,
        result.motion_ir_sha256, result.clip_sha256, result.run_sha256,
        result.bundle_sha256, result.source_kind,
    )


class BvhMotionCommandFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.state = self.root / "state"
        self.raw_path = self.root / "source.bvh"
        self.map_path = self.root / "map.json"
        self.raw_path.write_bytes(RAW)
        self.write_map(mapping())

    def write_map(self, value: dict, *, pretty: bool = True) -> None:
        self.map_path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2 if pretty else None),
            encoding="utf-8",
        )

    def compile(self):
        return compile_bvh_motion_bundle(
            self.state, self.raw_path, self.map_path
        )


class BvhMotionCommandSuccessTests(BvhMotionCommandFixture):
    def test_compile_is_frozen_complete_canonical_reusable_and_read_once(self):
        real_open = Path.open
        counts = {self.raw_path.resolve(): 0, self.map_path.resolve(): 0}

        def tracked(path, *args, **kwargs):
            resolved = path.resolve()
            if resolved in counts:
                counts[resolved] += 1
            return real_open(path, *args, **kwargs)

        with patch.object(Path, "open", autospec=True, side_effect=tracked):
            first = self.compile()
        second = self.compile()

        self.assertEqual({self.raw_path.resolve(): 1, self.map_path.resolve(): 1}, counts)
        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        self.assertEqual(identity(first), identity(second))
        self.assertEqual("bvh", first.source_kind)
        self.assertEqual(first.motion_ir_sha256, first.clip_sha256)
        self.assertEqual(hashlib.sha256(RAW).hexdigest(), first.raw_bvh_sha256)
        self.assertEqual(len(RAW), first.raw_bvh_byte_length)
        self.assertEqual(canonical(mapping()), (first.path / "map.json").read_bytes())
        self.assertEqual(RAW, (first.path / "source.bvh").read_bytes())
        with self.assertRaises(FrozenInstanceError):
            first.reused = True  # type: ignore[misc]

    def test_verify_is_read_only_and_deterministic_across_state_roots(self):
        compiled = self.compile()
        before = _tree(self.state)
        verified = verify_bvh_motion_bundle(
            self.state, compiled.clip_sha256, compiled.bundle_sha256
        )
        self.assertIsNone(verified.reused)
        self.assertEqual(identity(compiled), identity(verified))
        self.assertEqual(before, _tree(self.state))

        other_state = self.root / "other-state"
        other = compile_bvh_motion_bundle(
            other_state, self.raw_path, self.map_path
        )
        self.assertEqual(identity(compiled), identity(other))
        self.assertNotEqual(compiled.path, other.path)

    def test_noncanonical_map_input_is_published_canonically(self):
        value = mapping()
        reversed_value = dict(reversed(list(value.items())))
        self.map_path.write_text(
            "\n  " + json.dumps(reversed_value, indent=4) + "\n",
            encoding="utf-8",
        )
        result = self.compile()
        self.assertNotEqual(self.map_path.read_bytes(), canonical(value))
        self.assertEqual(canonical(value), (result.path / "map.json").read_bytes())

    def test_raw_whitespace_and_map_identity_drift_get_new_exact_bundles(self):
        baseline = self.compile()
        self.raw_path.write_bytes(RAW + b"\n")
        raw_drift = self.compile()
        self.assertEqual(baseline.clip_sha256, raw_drift.clip_sha256)
        self.assertNotEqual(baseline.raw_bvh_sha256, raw_drift.raw_bvh_sha256)
        self.assertNotEqual(baseline.run_sha256, raw_drift.run_sha256)
        self.assertNotEqual(baseline.bundle_sha256, raw_drift.bundle_sha256)

        self.raw_path.write_bytes(RAW)
        changed = mapping()
        changed["map_id"] = "minimal.explicit-v2"
        self.write_map(changed)
        map_drift = self.compile()
        self.assertEqual(baseline.clip_sha256, map_drift.clip_sha256)
        self.assertNotEqual(baseline.bvh_map_sha256, map_drift.bvh_map_sha256)
        self.assertNotEqual(baseline.bundle_sha256, map_drift.bundle_sha256)


class BvhMotionCommandRejectionTests(BvhMotionCommandFixture):
    def test_duplicate_nonfinite_nonobject_and_invalid_utf8_maps_fail_closed(self):
        invalid = (
            b'{"map_id":"a","map_id":"b"}',
            b'{"number":NaN}',
            b"[]",
            b"\xff",
        )
        for data in invalid:
            with self.subTest(data=data):
                self.map_path.write_bytes(data)
                with self.assertRaises(BvhMotionCommandError):
                    self.compile()
                self.assertFalse(self.state.exists())

    def test_oversize_inputs_and_nonregular_files_fail_before_publication(self):
        with patch(
            "autospine_workbench.motion_bvh_commands.MAX_BVH_BYTES", len(RAW) - 1
        ), self.assertRaisesRegex(BvhMotionCommandError, "byte limit"):
            self.compile()
        self.assertFalse(self.state.exists())

        with patch(
            "autospine_workbench.motion_bvh_commands.MAX_BVH_MAP_BYTES", 1
        ), self.assertRaisesRegex(BvhMotionCommandError, "byte limit"):
            self.compile()
        self.raw_path.unlink()
        self.raw_path.mkdir()
        with self.assertRaisesRegex(BvhMotionCommandError, "regular file"):
            self.compile()

    def test_input_symlink_aliases_are_rejected(self):
        for source in (self.raw_path, self.map_path):
            with self.subTest(source=source.name):
                outside = self.root / f"outside-{source.name}"
                outside.write_bytes(source.read_bytes())
                source.unlink()
                try:
                    source.symlink_to(outside)
                except OSError:
                    self.skipTest("File symlinks are unavailable")
                with self.assertRaisesRegex(BvhMotionCommandError, "real regular"):
                    self.compile()
                source.unlink()
                source.write_bytes(outside.read_bytes())
        self.assertFalse(self.state.exists())

    def test_tampered_secure_readback_is_rejected(self):
        compiled = self.compile()
        source = compiled.path / "source.bvh"
        source.write_bytes(source.read_bytes() + b"\n")
        with self.assertRaises(BvhMotionCommandError):
            verify_bvh_motion_bundle(
                self.state, compiled.clip_sha256, compiled.bundle_sha256
            )

    def test_verify_rejects_builtin_reader_source_kind(self):
        motion = build_builtin_motion("idle")
        run = build_builtin_motion_compile_run("idle", motion.document)
        published = MotionBundleStore(self.state).publish(
            motion.document, run.document
        )
        with self.assertRaisesRegex(BvhMotionCommandError, "built-in"):
            verify_bvh_motion_bundle(
                self.state, published.clip_sha256, published.bundle_sha256
            )

    def test_compile_rejects_tampered_reader_source_kind(self):
        result = self.compile()
        from autospine_workbench.motion_bundle_reader import (  # noqa: PLC0415
            VerifiedMotionBundleReader,
        )

        verified = VerifiedMotionBundleReader(self.state).load(
            result.clip_sha256, result.bundle_sha256
        )
        tampered = replace(verified, source_kind="builtin")
        with patch(
            "autospine_workbench.motion_bvh_commands."
            "VerifiedMotionBundleReader.load",
            return_value=tampered,
        ):
            with self.assertRaises(BvhMotionCommandError):
                self.compile()


def _tree(root: Path) -> dict[str, bytes]:
    return {
        item.relative_to(root).as_posix(): item.read_bytes()
        for item in root.rglob("*") if item.is_file()
    }


if __name__ == "__main__":
    unittest.main()
