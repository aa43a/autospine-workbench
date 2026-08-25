"""Strict read-only verification tests for immutable built-in motion bundles."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
import io
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

from autospine_workbench.motion_builtin import (  # noqa: E402
    build_builtin_motion,
)
from autospine_workbench.motion_bundle_contract import (  # noqa: E402
    DOCUMENT_NAMES,
    build_motion_bundle_contract,
)
from autospine_workbench.motion_bundle_integrity import (  # noqa: E402
    MotionBundleIntegrityError,
    MotionBundleSnapshot,
    verify_motion_bundle_snapshot,
)
from autospine_workbench import motion_bundle_reader  # noqa: E402
from autospine_workbench.motion_bundle_reader import (  # noqa: E402
    VerifiedMotionBundleReader,
    VerifiedMotionBundleReaderError,
)
from autospine_workbench.motion_compile_run import (  # noqa: E402
    build_builtin_motion_compile_run,
)


class MotionReaderFixture:
    def __init__(self, root: Path, clip_id: str = "idle") -> None:
        self.state = root / "state"
        self.motion = build_builtin_motion(clip_id).document
        self.run = build_builtin_motion_compile_run(clip_id, self.motion).document
        self.contract = build_motion_bundle_contract(self.motion, self.run)
        self.bundle = (
            self.state / "motions" / self.contract.clip_sha256
            / self.contract.bundle_sha256
        )
        self.bundle.mkdir(parents=True)
        for name, data in self.contract.document_bytes.items():
            (self.bundle / name).write_bytes(data)

    def load(self):
        return VerifiedMotionBundleReader(self.state).load(
            self.contract.clip_sha256, self.contract.bundle_sha256
        )


class MotionBundleReaderSuccessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_both_builtins_are_rebuilt_with_frozen_isolated_accessors(self) -> None:
        for clip_id in ("idle", "wave.left"):
            fixture = MotionReaderFixture(self.root / clip_id, clip_id)
            result = fixture.load()
            with self.subTest(clip_id=clip_id):
                self.assertEqual(fixture.bundle.resolve(), result.path)
                self.assertEqual(clip_id, result.clip_id)
                self.assertEqual(fixture.contract.clip_sha256, result.clip_sha256)
                self.assertEqual(fixture.contract.run_sha256, result.run_sha256)
                self.assertEqual(fixture.contract.bundle_sha256, result.bundle_sha256)
                self.assertEqual(DOCUMENT_NAMES, result.inventory)
                self.assertEqual(fixture.motion, result.motion)
                self.assertEqual(fixture.run, result.run_manifest)
                changed_motion = result.motion
                changed_run = result.run_manifest
                changed_bytes = result.document_bytes
                changed_motion.clear()
                changed_run.clear()
                changed_bytes.clear()
                self.assertTrue(result.motion)
                self.assertTrue(result.run_manifest)
                self.assertEqual(2, len(result.document_bytes))
                with self.assertRaises(FrozenInstanceError):
                    result.bundle_sha256 = "0" * 64  # type: ignore[misc]

    def test_each_file_is_read_once_and_loading_does_not_mutate_state(self) -> None:
        fixture = MotionReaderFixture(self.root)
        before = _tree_snapshot(fixture.state)
        original = Path.open
        reads: list[str] = []

        def tracked(path: Path, *args, **kwargs):
            if path.parent == fixture.bundle.resolve():
                reads.append(path.name)
            return original(path, *args, **kwargs)

        with patch.object(Path, "open", tracked):
            fixture.load()
        self.assertEqual(list(DOCUMENT_NAMES), reads)
        self.assertEqual(before, _tree_snapshot(fixture.state))


class MotionBundleReaderFailureTests(unittest.TestCase):
    def fixture(self, clip_id: str = "idle") -> MotionReaderFixture:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        return MotionReaderFixture(Path(temporary.name), clip_id)

    def assert_rejected(self, fixture: MotionReaderFixture) -> None:
        with self.assertRaises(VerifiedMotionBundleReaderError):
            fixture.load()

    def test_wrong_address_latest_path_traversal_and_case_mismatch_fail(self) -> None:
        fixture = self.fixture()
        reader = VerifiedMotionBundleReader(fixture.state)
        cases = (
            ("../escape", fixture.contract.bundle_sha256),
            ("latest", fixture.contract.bundle_sha256),
            ("A" * 64, fixture.contract.bundle_sha256),
            ("0" * 64, fixture.contract.bundle_sha256),
            (fixture.contract.clip_sha256, "latest"),
            (fixture.contract.clip_sha256, "0" * 64),
        )
        for values in cases:
            with self.subTest(values=values), self.assertRaises(
                VerifiedMotionBundleReaderError
            ):
                reader.load(*values)

        motions = fixture.state / "motions"
        temporary = fixture.state / "temporary"
        motions.rename(temporary)
        temporary.rename(fixture.state / "MOTIONS")
        self.assert_rejected(fixture)

    def test_documents_are_exactly_cross_bound_to_run_clip_and_address(self) -> None:
        fixture = self.fixture()
        wave = self.fixture("wave.left")
        (fixture.bundle / "run-manifest.json").write_bytes(
            wave.contract.document_bytes["run-manifest.json"]
        )
        self.assert_rejected(fixture)

        fixture = self.fixture()
        changed = deepcopy(fixture.motion)
        changed["tracks"][0]["keys"][1]["value"] = -2.0
        _canonical_write(fixture.bundle / "motion.json", changed)
        self.assert_rejected(fixture)

        fixture = self.fixture()
        wrong_clip = deepcopy(fixture.motion)
        wrong_clip["clip_id"] = "wave.left"
        _canonical_write(fixture.bundle / "motion.json", wrong_clip)
        self.assert_rejected(fixture)

    def test_wrong_physical_clip_or_bundle_address_fails_integrity(self) -> None:
        fixture = self.fixture()
        wrong_clip = "0" * 64
        changed_clip = fixture.bundle.parent.with_name(wrong_clip)
        fixture.bundle.parent.rename(changed_clip)
        fixture.bundle = changed_clip / fixture.contract.bundle_sha256
        with self.assertRaises(VerifiedMotionBundleReaderError):
            VerifiedMotionBundleReader(fixture.state).load(
                wrong_clip, fixture.contract.bundle_sha256
            )

        fixture = self.fixture()
        wrong_bundle = "0" * 64
        fixture.bundle.rename(fixture.bundle.with_name(wrong_bundle))
        fixture.bundle = fixture.bundle.with_name(wrong_bundle)
        with self.assertRaises(VerifiedMotionBundleReaderError):
            VerifiedMotionBundleReader(fixture.state).load(
                fixture.contract.clip_sha256, wrong_bundle
            )

    def test_missing_extra_nested_case_alias_and_byte_limits_fail(self) -> None:
        mutations = (
            lambda path: (path / "motion.json").unlink(),
            lambda path: (path / "extra.json").write_bytes(b"{}"),
            lambda path: (path / "nested").mkdir(),
        )
        for mutate in mutations:
            fixture = self.fixture()
            mutate(fixture.bundle)
            with self.subTest(mutate=mutate):
                self.assert_rejected(fixture)

        fixture = self.fixture()
        source = fixture.bundle / "motion.json"
        temporary = source.with_name("temporary.json")
        source.rename(temporary)
        temporary.rename(source.with_name("MOTION.JSON"))
        self.assert_rejected(fixture)

        for field in ("MAX_MOTION_BYTES", "MAX_RUN_BYTES", "MAX_TOTAL_DOCUMENT_BYTES"):
            fixture = self.fixture()
            with self.subTest(field=field), patch(
                f"autospine_workbench.motion_bundle_reader.{field}", 1
            ):
                self.assert_rejected(fixture)

    def test_whitespace_duplicate_nonfinite_invalid_utf8_and_array_fail(self) -> None:
        def whitespace(path):
            path.write_bytes(path.read_bytes() + b"\n")

        def duplicate(path):
            raw = path.read_bytes()
            path.write_bytes(b'{"format":"forged",' + raw[1:])

        def nonfinite(path):
            raw = path.read_bytes().replace(
                b'"format_version":1', b'"format_version":NaN'
            )
            path.write_bytes(raw)

        mutations = (
            whitespace,
            duplicate,
            nonfinite,
            lambda path: path.write_bytes(b"\xff"),
            lambda path: path.write_bytes(b"[]"),
        )
        for mutate in mutations:
            fixture = self.fixture()
            mutate(fixture.bundle / "motion.json")
            with self.subTest(mutate=mutate):
                self.assert_rejected(fixture)

    def test_directory_recheck_and_changed_during_read_boundaries_fail(self) -> None:
        fixture = self.fixture()
        real_directory = motion_bundle_reader._real_directory

        def replaced(path, label):
            if label == "Motion bundle directory":
                raise VerifiedMotionBundleReaderError("replaced directory")
            return real_directory(path, label)

        with patch(
            "autospine_workbench.motion_bundle_reader._real_directory",
            side_effect=replaced,
        ) as guard:
            self.assert_rejected(fixture)
        guard.assert_any_call(fixture.bundle.resolve(), "Motion bundle directory")

        fixture = self.fixture()
        original = Path.open

        def changed(path: Path, *args, **kwargs):
            if path.parent == fixture.bundle.resolve() and path.name == "motion.json":
                with original(path, "rb") as handle:
                    return io.BytesIO(handle.read() + b"x")
            return original(path, *args, **kwargs)

        with patch.object(Path, "open", changed):
            self.assert_rejected(fixture)

    def test_symlinked_file_intermediate_and_state_root_fail_when_supported(self) -> None:
        fixture = self.fixture()
        source = fixture.bundle / "motion.json"
        outside = fixture.bundle.parent / "outside.json"
        shutil.copyfile(source, outside)
        source.unlink()
        try:
            source.symlink_to(outside)
        except OSError:
            self.skipTest("file symlinks are unavailable")
        self.assert_rejected(fixture)

        alias = fixture.state.parent / "state-alias"
        try:
            alias.symlink_to(fixture.state, target_is_directory=True)
        except OSError:
            return
        try:
            with self.assertRaises(VerifiedMotionBundleReaderError):
                VerifiedMotionBundleReader(alias).load(
                    fixture.contract.clip_sha256, fixture.contract.bundle_sha256
                )
        finally:
            alias.unlink()

    def test_duplicate_snapshot_inventory_and_noncanonical_path_fail(self) -> None:
        fixture = self.fixture()
        motion = (fixture.bundle / "motion.json").read_bytes()
        snapshot = MotionBundleSnapshot(
            fixture.bundle, (("motion.json", motion), ("motion.json", motion))
        )
        with self.assertRaises(MotionBundleIntegrityError):
            verify_motion_bundle_snapshot(
                snapshot,
                expected_clip_sha256=fixture.contract.clip_sha256,
                expected_bundle_sha256=fixture.contract.bundle_sha256,
            )


def _canonical_write(path: Path, value) -> None:
    path.write_bytes(json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8"))


def _tree_snapshot(root: Path):
    directories = tuple(sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*") if path.is_dir()
    ))
    files = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*") if path.is_file()
    }
    return directories, files


if __name__ == "__main__":
    unittest.main()
