"""Synthetic release-input guards; no fixture is claimed to be usable Python."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile

_spec = importlib.util.spec_from_file_location("prepare_core_runtime", Path(__file__).resolve().parents[1] / "packaging/prepare_core_runtime.py")
core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(core)
_source_spec = importlib.util.spec_from_file_location("test_source_distribution", Path(__file__).resolve().parents[1] / "packaging/engine_distribution.py")
source_distribution = importlib.util.module_from_spec(_source_spec)
_source_spec.loader.exec_module(source_distribution)


def lock_document():
    wheels = []
    for package, version in core.VERSIONS.items():
        name = package.replace("-", "_") + "-" + version + "-py3-none-any.whl"
        wheels.append(dict(package=package, version=version, filename=name, sha256="a" * 64,
                           url="https://files.pythonhosted.org/packages/test/" + name,
                           metadata_url=f"https://pypi.org/pypi/{package}/{version}/json"))
    return dict(schema="autospine.core-runtime-wheel-lock/v1", wheels=wheels)


class StudioCoreRuntimeTests(unittest.TestCase):
    def test_rejects_archive_windows_alias_and_traversal_paths(self):
        for name in ["../python.exe", "/python.exe", "C:/python.exe", "python\\x.dll", "a//b.dll",
                     "a/./b.dll", "CON.dll", "a/b.dll.", "a/b.dll ", "a/naïve.dll", "a/evil?.py"]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                core.safe_relative(name)

    def test_verified_file_requires_exact_hash_and_regular_ownership(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "artifact.zip"
            file.write_bytes(b"authored fixture, never executed")
            digest = hashlib.sha256(file.read_bytes()).hexdigest()
            core.verified_file(file, digest)
            with self.assertRaisesRegex(ValueError, "verification"):
                core.verified_file(file, "0" * 64)
            file.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "verification"):
                core.verified_file(file, digest)

    def test_fixed_wheel_versions_hashes_origin_and_platform(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "lock.json"
            document = lock_document()
            file.write_text(json.dumps(document), encoding="utf-8")
            self.assertEqual(len(core.wheel_lock(file)), len(core.VERSIONS))
            for key, value in [("version", "99.0.0"), ("sha256", "bad"), ("url", "https://attacker.invalid/fake.whl"),
                               ("metadata_url", "https://pypi.org/pypi/unpinned/latest/json"),
                               ("filename", "numpy-2.4.6-cp314-cp314-linux_x86_64.whl")]:
                with self.subTest(key=key):
                    bad = copy.deepcopy(document)
                    bad["wheels"][0][key] = value
                    file.write_text(json.dumps(bad), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        core.wheel_lock(file)

    def test_duplicate_wheel_and_unexpected_declaration_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "lock.json"
            for mutate in [lambda doc: doc["wheels"].__setitem__(1, copy.deepcopy(doc["wheels"][0])),
                           lambda doc: doc["wheels"][0].__setitem__("install_command", "arbitrary")]:
                bad = lock_document()
                mutate(bad)
                file.write_text(json.dumps(bad), encoding="utf-8")
                with self.assertRaises(ValueError):
                    core.wheel_lock(file)

    def test_archive_links_duplicates_and_unknown_roots_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for ordinal, entries in enumerate([
                [("numpy/a.py", stat.S_IFLNK | 0o777), ("numpy/b.py", stat.S_IFREG | 0o644)],
                [("numpy/a.py", stat.S_IFREG | 0o644), ("numpy/A.py", stat.S_IFREG | 0o644)],
                [("user_models/secret.onnx", stat.S_IFREG | 0o644)],
                [("../secret.py", stat.S_IFREG | 0o644)],
            ]):
                archive = root / f"input-{ordinal}.whl"
                with zipfile.ZipFile(archive, "w") as stream:
                    for name, mode in entries:
                        item = zipfile.ZipInfo(name)
                        item.external_attr = mode << 16
                        stream.writestr(item, b"fixture")
                with self.assertRaises(ValueError):
                    core.extract(archive, root / f"output-{ordinal}")
            self.assertFalse((root / "secret.py").exists())

    def test_tests_and_nested_wheel_not_extracted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "wheel.whl"
            with zipfile.ZipFile(archive, "w") as stream:
                stream.writestr("numpy/runtime.py", b"runtime fixture")
                stream.writestr("numpy/tests/private.py", b"do not copy tests")
                stream.writestr("scipy/nested.whl", b"not an installed module")
            target = root / "installed"
            core.extract(archive, target)
            self.assertEqual((target / "numpy/runtime.py").read_bytes(), b"runtime fixture")
            self.assertFalse((target / "numpy/tests/private.py").exists())
            self.assertFalse((target / "scipy/nested.whl").exists())

    def test_existing_output_preserved_before_any_input_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "previous"
            target.mkdir()
            sentinel = target / "human-project.psd"
            sentinel.write_bytes(b"preserve")
            with self.assertRaisesRegex(ValueError, "destination already exists"):
                core.prepare(root / "missing-source", root / "missing.zip", root / "missing-wheels", root / "missing-lock", target)
            self.assertEqual(sentinel.read_bytes(), b"preserve")

    def test_expansion_failure_keeps_partial_new_artifact_without_touching_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source_file = source / "engine/src/autospine_workbench/server.py"
            payload = {name: b"authored source fixture" for name in source_distribution.REQUIRED_FILES}
            for name, data in payload.items():
                file = source / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(data)
            manifest = source_distribution.manifest_for(payload, "a" * 40)
            (source / "engine-distribution.json").write_bytes(source_distribution.canonical_bytes(manifest))
            python_zip = root / "python.zip"
            # Deliberately incomplete Python ZIP; fixture contents are never run.
            with zipfile.ZipFile(python_zip, "w") as stream:
                stream.writestr("python.exe", b"not a usable executable")
            wheels = root / "wheels"
            wheels.mkdir()
            lock = lock_document()
            for item in lock["wheels"]:
                wheel = wheels / item["filename"]
                wheel.write_bytes(b"never extracted because Python is incomplete")
                item["sha256"] = hashlib.sha256(wheel.read_bytes()).hexdigest()
            lock_file = root / "lock.json"
            lock_file.write_text(json.dumps(lock), encoding="utf-8")
            target = root / "failed-new-version"
            with patch.object(core, "PYTHON_SHA256", hashlib.sha256(python_zip.read_bytes()).hexdigest()):
                with self.assertRaisesRegex(ValueError, "incomplete"):
                    core.prepare(source, python_zip, wheels, lock_file, target)
            self.assertEqual(source_file.read_bytes(), b"authored source fixture")
            self.assertEqual((target / "engine/src/autospine_workbench/server.py").read_bytes(), b"authored source fixture")
            self.assertEqual((target / "runtime/python/python.exe").read_bytes(), b"not a usable executable")
            self.assertFalse((target / "engine-distribution.json").exists())


if __name__ == "__main__":
    unittest.main()
