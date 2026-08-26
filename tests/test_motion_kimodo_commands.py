"""Filesystem service-boundary tests for formal Kimodo compile/verify."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.motion_kimodo_commands import (  # noqa: E402
    KimodoMotionCommandError,
    compile_kimodo_motion_bundle,
    verify_kimodo_motion_bundle,
)
from autospine_workbench import kimodo_npz_compiler as compiler_impl  # noqa: E402
from autospine_workbench.safe_input_files import read_real_file  # noqa: E402
from tests.fixtures.kimodo_npz_archive import (  # noqa: E402
    build_npz,
    motion_member_bytes,
)
from tests.kimodo_npz_helpers import map_document, source_document  # noqa: E402


class KimodoCommandFixture:
    def __init__(self, root: Path):
        root.mkdir(parents=True, exist_ok=True)
        self.state = root / "state"
        self.raw = build_npz(motion_member_bytes())
        self.source = source_document(self.raw)
        self.mapping = map_document()
        self.raw_path = root / "motion.npz"
        self.source_path = root / "motion.source.json"
        self.map_path = root / "motion.map.json"
        self.raw_path.write_bytes(self.raw)
        self.source_path.write_text(
            json.dumps(self.source, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self.map_path.write_text(
            json.dumps(self.mapping, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def compile(self):
        return compile_kimodo_motion_bundle(
            self.state, self.raw_path, self.source_path, self.map_path
        )


class KimodoMotionCommandTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.fixture = KimodoCommandFixture(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def test_compile_is_complete_reusable_and_reads_each_input_once(self):
        calls = []

        def tracked(path, maximum, label):
            calls.append(Path(path))
            return read_real_file(path, maximum, label)

        with patch(
            "autospine_workbench.motion_kimodo_commands.read_real_file",
            side_effect=tracked,
        ), patch.object(
            compiler_impl,
            "compile_kimodo_npz_motion",
            wraps=compiler_impl.compile_kimodo_npz_motion,
        ) as compile_call:
            first = self.fixture.compile()
        self.assertEqual(3, compile_call.call_count)
        second = self.fixture.compile()
        self.assertEqual([
            self.fixture.raw_path,
            self.fixture.source_path,
            self.fixture.map_path,
        ], calls)
        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        self.assertEqual(first.path, second.path)
        self.assertEqual("kimodo_npz", first.source_kind)
        self.assertEqual(self.fixture.source["source_id"], first.source_id)
        self.assertEqual(self.fixture.mapping["map_id"], first.map_id)
        for value in (
            first.raw_npz_sha256, first.source_sha256, first.map_sha256,
            first.array_inventory_sha256, first.motion_ir_sha256,
            first.clip_sha256, first.run_sha256, first.bundle_sha256,
        ):
            self.assertEqual(64, len(value))

    def test_verify_is_read_only_and_rejects_other_source_kinds(self):
        compiled = self.fixture.compile()
        before = sorted(path.relative_to(self.fixture.state)
                        for path in self.fixture.state.rglob("*"))
        verified = verify_kimodo_motion_bundle(
            self.fixture.state, compiled.clip_sha256, compiled.bundle_sha256
        )
        after = sorted(path.relative_to(self.fixture.state)
                       for path in self.fixture.state.rglob("*"))
        self.assertEqual(before, after)
        self.assertIsNone(verified.reused)
        self.assertEqual(compiled.bundle_sha256, verified.bundle_sha256)

        with patch(
            "autospine_workbench.motion_kimodo_commands."
            "VerifiedMotionBundleReader.load",
            return_value=SimpleNamespace(source_kind="bvh"),
        ), self.assertRaisesRegex(KimodoMotionCommandError, "non-Kimodo"):
            verify_kimodo_motion_bundle(self.fixture.state, "a" * 64, "b" * 64)

    def test_duplicate_nonfinite_nonobject_and_invalid_utf8_json_fail(self):
        mutations = (
            (self.fixture.source_path, b'{"format":"x",' +
             self.fixture.source_path.read_bytes()[1:]),
            (self.fixture.map_path, self.fixture.map_path.read_bytes().replace(
                b'"format_version": 1', b'"format_version": NaN'
            )),
            (self.fixture.source_path, b"[]"),
            (self.fixture.map_path, b"\xff"),
        )
        for index, (path, data) in enumerate(mutations):
            fixture = KimodoCommandFixture(self.root / f"bad-{index}")
            target = fixture.source_path if path.name.endswith("source.json") \
                else fixture.map_path
            target.write_bytes(data)
            with self.subTest(index=index), self.assertRaises(
                KimodoMotionCommandError
            ):
                fixture.compile()
            self.assertFalse(fixture.state.exists())

    def test_oversize_or_incomplete_inputs_fail_before_publication(self):
        cases = (
            ("MAX_RAW_NPZ_BYTES", self.fixture.raw_path),
            ("MAX_SOURCE_DOCUMENT_BYTES", self.fixture.source_path),
            ("MAX_KIMODO_MAP_BYTES", self.fixture.map_path),
        )
        for field, _path in cases:
            with self.subTest(field=field), patch(
                f"autospine_workbench.motion_kimodo_commands.{field}", 1
            ), self.assertRaises(KimodoMotionCommandError):
                self.fixture.compile()
        self.assertFalse(self.fixture.state.exists())

        incomplete = source_document(self.fixture.raw)
        incomplete.pop("array_profile")
        self.fixture.source_path.write_text(json.dumps(incomplete), encoding="utf-8")
        with self.assertRaises(KimodoMotionCommandError):
            self.fixture.compile()
        self.assertFalse(self.fixture.state.exists())

    def test_tampered_secure_readback_is_not_reported_as_success(self):
        with patch(
            "autospine_workbench.motion_kimodo_commands."
            "VerifiedMotionBundleReader.load",
            return_value=SimpleNamespace(source_kind="bvh"),
        ), self.assertRaises(KimodoMotionCommandError):
            self.fixture.compile()


if __name__ == "__main__":
    unittest.main()
