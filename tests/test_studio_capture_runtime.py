from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

MODULE = Path(__file__).resolve().parents[1] / "packaging/prepare_capture_runtime.py"
SPEC = importlib.util.spec_from_file_location("capture_runtime_builder", MODULE)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class CaptureDistributionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def zip_input(self, records):
        file = self.root / "input.zip"
        with zipfile.ZipFile(file, "x") as output:
            for name, data in records:
                output.writestr(name, data)
        return file

    def test_relative_path_rejects_windows_aliases_and_traversal(self):
        for value in ["../escape", "x/../escape", "x//a", "x/./a", "/escape", "C:/x", "x\\a",
                      "node/node.exe:ads", "browser/CON.txt", "browser/a.", "browser/a "]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                builder.safe_relative(value)
        self.assertEqual(builder.safe_relative("dependencies/node_modules/@esotericsoftware/spine-webgl/LICENSE"),
                         "dependencies/node_modules/@esotericsoftware/spine-webgl/LICENSE")

    def test_official_zip_root_directory_and_selected_payload(self):
        file = self.zip_input([("official/", b""), ("official/node.exe", b"node"),
                               ("official/LICENSE", b"terms"), ("official/npm/unused", b"not shipped")])
        destination = self.root / "out"
        builder.extract_zip(file, destination, "official", selected={"node.exe", "LICENSE"})
        self.assertEqual(sorted(row["path"] for row in builder.inventory(destination)), ["LICENSE", "node.exe"])

    def test_wrong_zip_root_and_symlink_are_rejected(self):
        file = self.zip_input([("other/thing", b"x")])
        with self.assertRaises(ValueError):
            builder.extract_zip(file, self.root / "out", "official")
        link = self.root / "link.zip"
        info = zipfile.ZipInfo("official/link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        with zipfile.ZipFile(link, "x") as output:
            output.writestr(info, "../outside")
        with self.assertRaises(ValueError):
            builder.extract_zip(link, self.root / "link-out", "official")

    def test_zip_case_alias_is_rejected_without_overwriting(self):
        file = self.zip_input([("official/a.txt", b"first"), ("official/A.txt", b"second")])
        destination = self.root / "out"
        with self.assertRaises(ValueError):
            builder.extract_zip(file, destination, "official")
        self.assertEqual((destination / "a.txt").read_bytes(), b"first")

    def test_zip_missing_required_entry_rejects(self):
        file = self.zip_input([("official/node.exe", b"node")])
        with self.assertRaises(ValueError):
            builder.extract_zip(file, self.root / "out", "official", selected={"node.exe", "LICENSE"})

    def test_tar_links_and_outside_package_reject(self):
        for index, (name, kind) in enumerate([("package/linked", tarfile.SYMTYPE),
                                            ("package/hard", tarfile.LNKTYPE), ("outside/x", tarfile.REGTYPE)]):
            file = self.root / f"tar-{index}.tgz"
            with tarfile.open(file, "w:gz") as output:
                info = tarfile.TarInfo(name)
                info.type = kind
                info.linkname = "../escape"
                output.addfile(info, io.BytesIO(b""))
            with self.subTest(name=name), self.assertRaises(ValueError):
                builder.extract_tar(file, self.root / f"out-{index}")

    def test_copy_declared_size_and_exclusive_destination(self):
        destination = self.root / "out"
        with self.assertRaises(ValueError):
            builder.record_file(destination, "a", io.BytesIO(b"too long"), 1, seen=set())
        self.assertEqual((destination / "a").read_bytes(), b"")
        with self.assertRaises(FileExistsError):
            builder.record_file(destination, "a", io.BytesIO(b"new"), 3, seen=set())

    def test_wrong_official_input_hash_fails_before_creating_output(self):
        inputs = self.root / "inputs"
        inputs.mkdir()
        (inputs / next(iter(builder.INPUTS))).write_bytes(b"tampered")
        output = self.root / "new-release"
        with self.assertRaisesRegex(ValueError, "verification failed"):
            builder.prepare(inputs, output)
        self.assertFalse(output.exists())

    def test_tree_identity_is_order_independent_and_content_bound(self):
        row = lambda name, raw: dict(path=name, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        rows = [row("browser/b", b"two"), row("browser/a", b"one"), row("other/a", b"outside")]
        self.assertEqual(builder.tree_identity(rows, "browser/"), builder.tree_identity(list(reversed(rows)), "browser/"))
        changed = rows + [row("browser/debug.log", b"mutable")]
        self.assertNotEqual(builder.tree_identity(rows, "browser/")["sha256"], builder.tree_identity(changed, "browser/")["sha256"])

    def test_archive_rejects_changed_manifest_and_keeps_output_absent(self):
        source = self.root / "source"
        source.mkdir()
        (source / "provenance.json").write_text("{}")
        rows = builder.inventory(source)
        manifest = builder.distribution_manifest(rows)
        manifest["browser_version"] = "another"
        (source / builder.MANIFEST).write_text(json.dumps(manifest))
        destination = self.root / "archive.zip"
        with self.assertRaises(ValueError):
            builder.archive(source, destination)
        self.assertFalse(destination.exists())

    def test_inventory_excludes_only_the_root_manifest(self):
        source = self.root / "source"
        source.mkdir()
        (source / builder.MANIFEST).write_bytes(b"root manifest")
        names = [f"browser/{builder.MANIFEST}", f"node/{builder.MANIFEST}",
                 f"dependencies/node_modules/playwright-core/{builder.MANIFEST}"]
        payload = b"nested payload must remain inventoried"
        for name in names:
            file = source / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(payload)
        rows = builder.inventory(source)
        self.assertEqual({row["path"] for row in rows}, set(names))
        for row in rows:
            self.assertEqual(row["bytes"], len(payload))
            self.assertEqual(row["sha256"], hashlib.sha256(payload).hexdigest())

    def test_archive_rejects_nested_manifest_added_after_inventory(self):
        source = self.root / "source"
        source.mkdir()
        (source / "provenance.json").write_text("{}")
        (source / builder.MANIFEST).write_text(json.dumps(
            builder.distribution_manifest(builder.inventory(source))))
        nested = source / "browser" / builder.MANIFEST
        nested.parent.mkdir()
        nested.write_bytes(b"unrecorded extra file")
        destination = self.root / "archive.zip"
        with self.assertRaisesRegex(ValueError, "inventory changed before archive"):
            builder.archive(source, destination)
        self.assertFalse(destination.exists())

    def test_archive_rejects_self_consistent_changed_software(self):
        source = self.root / "source"
        source.mkdir()
        (source / "provenance.json").write_text("{}")
        (source / builder.MANIFEST).write_text(json.dumps(builder.distribution_manifest(builder.inventory(source))))
        with self.assertRaisesRegex(ValueError, "software tree differs"):
            builder.archive(source, self.root / "archive.zip")

    def test_inventory_rejects_hardlink_payload(self):
        source = self.root / "source"
        source.mkdir()
        (source / "a").write_bytes(b"file")
        try:
            os.link(source / "a", source / "b")
        except OSError:
            self.skipTest("hardlinks unavailable")
        with self.assertRaises(ValueError):
            builder.inventory(source)


if __name__ == "__main__":
    unittest.main()
