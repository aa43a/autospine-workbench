"""Offline FBX distribution boundaries; no native installation in unit tests."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("blender_runtime_builder",
    Path(__file__).resolve().parents[1] / "packaging/prepare_blender_runtime.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class BlenderRuntimeTests(unittest.TestCase):
    def test_windows_paths_reject_aliases_but_accept_original_upstream_names(self):
        for bad in ("../x", "b/./x", "b//x", "b/../x", "C:/x", "b\\x", "b/CON.txt",
                    "b/file:ads", "b/x.", "b/x ", "b/ x", "b/\x00x", "b/a|b"):
            with self.subTest(path=bad), self.assertRaises(ValueError):
                builder.safe_relative(bad)
        for valid in ("b/launcher manifest.xml", "b/script (dev).tmpl", "b/check_normal+y.exr"):
            self.assertEqual(builder.safe_relative(valid), valid)

    def test_untrusted_archive_never_creates_release_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / builder.ZIP_NAME).write_bytes(b"untrusted binary")
            output = root / "release"
            with self.assertRaisesRegex(ValueError, "input verification"):
                builder.prepare(root, output)
            self.assertFalse(output.exists())

    def test_executable_only_is_insufficient_and_unexpected_inventory_is_rejected(self):
        rows = [dict(path="b/blender.exe", **builder.EXE),
                dict(path="provenance.json", bytes=1, sha256="a"*64),
                dict(path="LICENSES/README.md", bytes=1, sha256="b"*64)]
        with self.assertRaisesRegex(ValueError, "software tree"):
            builder.verify_software_inventory(rows)
        changed = [dict(row) for row in rows]
        changed.append(dict(path="b/config.json", bytes=7, sha256="c"*64))
        self.assertNotEqual(builder.tree_identity(rows), builder.tree_identity(changed))

    def test_inventory_is_byte_sensitive_and_root_manifest_alone_is_excluded(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "b").mkdir()
            (root / builder.MANIFEST).write_text("manifest")
            (root / "b" / builder.MANIFEST).write_text("upstream fixture")
            rows = builder.inventory(root)
            self.assertEqual([row["path"] for row in rows], ["b/"+builder.MANIFEST])
            self.assertEqual(rows[0]["sha256"], hashlib.sha256(b"upstream fixture").hexdigest())
            (root / "b" / builder.MANIFEST).write_text("changed")
            self.assertNotEqual(builder.tree_identity(rows), builder.tree_identity(builder.inventory(root)))


if __name__ == "__main__":
    unittest.main()
