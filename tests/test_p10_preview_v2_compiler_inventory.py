"""Static Preview v2 compiler-closure identity tests."""

from __future__ import annotations

from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.p10_preview_v2_compiler_inventory import (  # noqa: E402
    P10PreviewV2CompilerInventoryError,
    preview_v2_compiler_inventory_sha256,
)


class P10PreviewV2CompilerInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "preview_test_package"
        self.root.mkdir()
        self._write("__init__.py", '"""Test package."""\n')
        self._write("p10_preview_v2_service.py", (
            "from .dependency import VALUE\n"
            "from . import sibling\n"
            "import preview_test_package.absolute as absolute\n"
            "RESULT = VALUE + sibling.VALUE + absolute.VALUE\n"
        ))
        self._write("dependency.py", "VALUE = 1\n")
        self._write("sibling.py", "VALUE = 2\n")
        self._write("absolute.py", "VALUE = 3\n")
        self._write("unrelated.py", "VALUE = 4\n")

    def tearDown(self):
        self.temporary.cleanup()

    def test_digest_is_deterministic_hex_and_contains_no_path(self):
        first = self._digest()
        second = self._digest()
        self.assertEqual(first, second)
        self.assertRegex(first, re.compile(r"^[0-9a-f]{64}$"))
        self.assertNotIn(str(self.root), first)
        with tempfile.TemporaryDirectory() as temporary:
            mirror = Path(temporary) / self.root.name
            shutil.copytree(self.root, mirror)
            self.assertEqual(
                first, preview_v2_compiler_inventory_sha256(mirror),
            )

    def test_every_supported_local_import_enters_closure(self):
        baseline = self._digest()
        for name in ("dependency.py", "sibling.py", "absolute.py"):
            with self.subTest(name=name):
                original = (self.root / name).read_text(encoding="utf-8")
                self._write(name, original + "CHANGED = True\n")
                self.assertNotEqual(baseline, self._digest())
                self._write(name, original)

    def test_unrelated_package_module_does_not_change_digest(self):
        baseline = self._digest()
        self._write("unrelated.py", "VALUE = 999\n")
        self.assertEqual(baseline, self._digest())

    def test_missing_local_dependency_fails_closed(self):
        self._write(
            "p10_preview_v2_service.py",
            "from .missing import VALUE\n",
        )
        with self.assertRaises(P10PreviewV2CompilerInventoryError):
            self._digest()

    def test_missing_from_dot_import_fails_closed(self):
        self._write(
            "p10_preview_v2_service.py",
            "from . import missing\n",
        )
        with self.assertRaises(P10PreviewV2CompilerInventoryError):
            self._digest()

    def test_invalid_local_source_fails_without_absolute_path(self):
        self._write("dependency.py", "def broken(:\n")
        with self.assertRaises(P10PreviewV2CompilerInventoryError) as raised:
            self._digest()
        self.assertNotIn(str(self.root), str(raised.exception))

    def _digest(self):
        return preview_v2_compiler_inventory_sha256(self.root)

    def _write(self, relative: str, text: str):
        (self.root / relative).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
