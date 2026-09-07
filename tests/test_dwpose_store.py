"""DWPose publication must reject unsafe destinations before writing evidence."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.runners.pose.dwpose import _publish


class DwposeStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name); self.state = self.root / "state"
        self.document = {"schema": "test-only", "authority": "none", "data": [1, 2, 3]}

    def publish(self):
        return _publish(self.state, "dwpose-raw", "sample", self.document)

    def test_idempotent_exact_publication(self):
        first = self.publish(); raw = first.path.read_bytes()
        second = self.publish()
        self.assertEqual(first, second)
        self.assertEqual(first.sha256, canonical_sha256(self.document))
        self.assertEqual(first.path.read_bytes(), raw)
        self.assertEqual(len(list(self.state.rglob("*.json"))), 1)
        self.assertEqual(first.path.lstat().st_nlink, 1)

    def test_existing_hardlinked_target_rejected_and_unchanged(self):
        first = self.publish(); alias = self.root / "external.json"
        os.link(first.path, alias); original = alias.read_bytes()
        with self.assertRaises((ValueError, RuntimeError)): self.publish()
        self.assertEqual(alias.read_bytes(), original)

    def test_file_at_each_directory_level_rejected(self):
        for depth in range(4):
            with self.subTest(depth=depth), tempfile.TemporaryDirectory() as temp:
                root = Path(temp) / "state"
                parts = [root, root / "analysis", root / "analysis" / "sample",
                         root / "analysis" / "sample" / "dwpose-raw"]
                conflict = parts[depth]; conflict.parent.mkdir(parents=True, exist_ok=True)
                conflict.write_bytes(b"original")
                with self.assertRaises((ValueError, RuntimeError)):
                    _publish(root, "dwpose-raw", "sample", self.document)
                self.assertEqual(conflict.read_bytes(), b"original")
                self.assertFalse(list(Path(temp).rglob("*.json")))

    def test_symlink_at_each_directory_level_rejected_without_external_write(self):
        for depth in range(4):
            with self.subTest(depth=depth), tempfile.TemporaryDirectory() as temp:
                parent = Path(temp); outside = parent / "outside"; outside.mkdir()
                root = parent / "state"
                parts = [root, root / "analysis", root / "analysis" / "sample",
                         root / "analysis" / "sample" / "dwpose-raw"]
                alias = parts[depth]; alias.parent.mkdir(parents=True, exist_ok=True)
                try: alias.symlink_to(outside, target_is_directory=True)
                except OSError as exc: self.skipTest(f"Symlink unavailable: {exc}")
                try:
                    with self.assertRaises((ValueError, RuntimeError)):
                        _publish(root, "dwpose-raw", "sample", self.document)
                    self.assertEqual(list(outside.iterdir()), [])
                finally:
                    alias.unlink()

    def test_symlink_target_rejected_without_touching_external_file(self):
        directory = self.state / "analysis" / "sample" / "dwpose-raw"
        directory.mkdir(parents=True)
        outside = self.root / "external.json"; outside.write_bytes(b"original")
        alias = directory / (canonical_sha256(self.document) + ".json")
        try: alias.symlink_to(outside)
        except OSError as exc: self.skipTest(f"Symlink unavailable: {exc}")
        self.addCleanup(alias.unlink, missing_ok=True)
        with self.assertRaises((ValueError, RuntimeError)): self.publish()
        self.assertEqual(outside.read_bytes(), b"original")


if __name__ == "__main__": unittest.main()
