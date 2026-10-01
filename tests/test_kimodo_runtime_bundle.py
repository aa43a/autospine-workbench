"""A full local addon never trusts an addressed file or an old verification."""
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
spec = importlib.util.spec_from_file_location("_kimodo_addon_builder_test", TOOLS / "kimodo_runtime_bundle.py")
bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)


class KimodoRuntimeBundleTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.files = {".venv/Scripts/python.exe": b"test interpreter, never executed",
                      "source/module.py": b"fixed source",
                      "checkpoints/model.safetensors": b"test weight bytes"}
        python = {"inventory": [{"path": name, "byte_length": len(raw), "sha256": sha256(raw).hexdigest()}
                                for name, raw in self.files.items() if not name.startswith("checkpoints/")]}
        self.files[bundle.PYTHON_MANIFEST] = bundle.canonical(python)
        self.files[bundle.PROVENANCE] = b'{"runtime_ready":false}'
        for name, raw in self.files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        self.manifest = dict(schema=bundle.SCHEMA, component="kimodo-runtime", platform="windows-x64",
                             generation_profile=bundle.PROFILE, python_path=".venv/Scripts/python.exe",
                             provenance_path=bundle.PROVENANCE,
                             python_manifest_sha256=sha256(self.files[bundle.PYTHON_MANIFEST]).hexdigest(),
                             files=[dict(path=name, bytes=len(raw), sha256=sha256(raw).hexdigest())
                                    for name, raw in sorted(self.files.items())])
        self.save_manifest()

    def save_manifest(self):
        raw = bundle.canonical(self.manifest)
        (self.root / bundle.MANIFEST).write_bytes(raw)
        self.digest = sha256(raw).hexdigest()

    def verify(self):
        return bundle.verify(self.root, expected_manifest_sha256=self.digest)

    def test_complete_bytes_match_and_never_claim_runtime_readiness(self):
        report = self.verify()
        self.assertTrue(report["integrity_verified"])
        self.assertFalse(report["runtime_ready"])
        self.assertFalse(report["inference_performed"])
        self.assertEqual(report["scope"], "caller-addressed-byte-inventory-only")
        self.assertFalse(report["fixed_profile_admitted"])
        self.assertEqual(report["files"], len(self.files))

    def test_supervised_adapter_notice_is_required_and_independently_pinned(self):
        name = next(iter(bundle.ADDITIONAL_NOTICES))
        target = self.root / name
        target.parent.mkdir(parents=True)
        raw = b"license: mit\nSupervised adapter notice\n"
        target.write_bytes(raw)
        digest = sha256(raw).hexdigest()
        with patch.object(bundle, "ADDITIONAL_NOTICES", {name: (len(raw), digest)}):
            self.assertEqual(bundle.additional_notices(self.root), [
                dict(path=name, byte_length=len(raw), sha256=digest)])
            target.write_bytes(b"changed notice")
            with self.assertRaisesRegex(ValueError, "digest_mismatch"):
                bundle.additional_notices(self.root)
            target.unlink()
            with self.assertRaises(FileNotFoundError):
                bundle.additional_notices(self.root)

    def test_next_read_rejects_an_unused_changed_weight(self):
        self.verify()
        (self.root / "checkpoints/model.safetensors").write_bytes(b"wrong weight bytes")
        with self.assertRaisesRegex(ValueError, "digest_mismatch"):
            self.verify()

    def test_hardlinks_and_extra_files_fail_even_if_declared_bytes_are_valid(self):
        outside = self.root.parent / (self.root.name + "-alias")
        outside.hardlink_to(self.root / "source/module.py")
        try:
            with self.assertRaisesRegex(ValueError, "file_unsafe"):
                self.verify()
        finally:
            outside.unlink()
        (self.root / "extra.dat").write_bytes(b"extra")
        with self.assertRaisesRegex(ValueError, "undeclared_file"):
            self.verify()

    def test_undeclared_empty_directory_is_rejected(self):
        (self.root / "empty").mkdir()
        with self.assertRaisesRegex(ValueError, "extra_directory"):
            self.verify()

    def test_relative_paths_and_case_collisions_are_rejected(self):
        self.manifest["files"].append(dict(self.manifest["files"][0], path="../external.exe"))
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "unsafe|relative"):
            self.verify()
        self.manifest["files"].pop()
        self.manifest["files"].append(dict(self.manifest["files"][0], path=self.manifest["files"][0]["path"].upper()))
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "record_invalid"):
            self.verify()

    def test_manifest_replacement_during_verification_is_rejected(self):
        original = bundle.streamed
        changed = False

        def read(*args, **kwargs):
            nonlocal changed
            result = original(*args, **kwargs)
            if not changed:
                changed = True
                (self.root / bundle.MANIFEST).write_bytes(b"changed")
            return result

        with patch.object(bundle, "streamed", side_effect=read):
            with self.assertRaisesRegex(ValueError, "changed"):
                self.verify()

    def test_python_component_inventory_must_match_full_addon(self):
        self.manifest["python_manifest_sha256"] = "a" * 64
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "python_pair_changed"):
            self.verify()

    def test_streamed_copy_checks_original_and_actual_destination_bytes(self):
        src, dst = self.root / "source/module.py", self.root / "copy-owned.dat"
        expected = dict(byte_length=len(self.files["source/module.py"]), sha256=sha256(self.files["source/module.py"]).hexdigest())
        self.assertEqual(bundle.streamed(src, output=dst, expected=expected), expected)
        self.assertEqual(dst.read_bytes(), src.read_bytes())
        with self.assertRaises(FileExistsError):
            bundle.streamed(src, output=dst, expected=expected)


if __name__ == "__main__":
    unittest.main()
