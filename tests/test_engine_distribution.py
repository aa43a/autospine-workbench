"""Release boundaries, reproducibility and corruption detection."""
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

_spec = importlib.util.spec_from_file_location("engine_distribution", Path(__file__).resolve().parents[1] / "packaging/engine_distribution.py")
distribution = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(distribution)


def minimal_payload():
    return {file: (b"" if file.endswith("__init__.py") else b"release source\n") for file in distribution.REQUIRED_FILES}


class EngineDistributionTests(unittest.TestCase):
    def test_policy_excludes_data_models_history_cache_and_tests(self):
        for path in ["workspace/config.json", "tools/model.onnx", "src/autospine_workbench/models/secret.py",
                     "tools/user.psd", "web/m4-fixed-cohort.json", "web/tests/a.js", "web/thing.test.js",
                     "src/autospine_workbench/test_experiment.py", "src/autospine_workbench/__pycache__/x.py",
                     "src/autospine_workbench/node_modules/x.js", "README.md"]:
            with self.subTest(path=path):
                self.assertFalse(distribution.allowed_source_path(path))
        for path in ["src/autospine_workbench/server.py", "src/autospine_workbench/benchmark/player.js",
                     "tools/capture-sleeve-runtime.mjs", "web/modules/project-context.js", "web/workflow-catalog.json"]:
            self.assertTrue(distribution.allowed_source_path(path))

    def test_windows_unsafe_paths_are_rejected(self):
        for path in ["../server.py", "/src/server.py", "engine\\src\\server.py", "engine/src:C/file.py",
                     "engine/src//file.py", "engine/CON.py", "engine/src/file.py.", "engine/src/file.py ",
                     "engine/src/a\n.py", "engine/src/a?.py"]:
            with self.subTest(path=path), self.assertRaises(distribution.DistributionError):
                distribution.safe_path(path)

    def test_hardlinked_artifact_is_not_accepted_as_owned_content(self):
        import os
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "bundle"
            root.mkdir()
            self._publish(root)
            original = root / "engine/src/autospine_workbench/server.py"
            outside = Path(folder) / "other-owned-file.py"
            outside.write_bytes(original.read_bytes())
            original.unlink()
            os.link(outside, original)
            with self.assertRaisesRegex(distribution.DistributionError, "file_invalid"):
                distribution.verify_directory(root)

    def test_verifier_detects_manifest_changing_during_inventory_read(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self._publish(root)
            server = root / "engine/src/autospine_workbench/server.py"
            manifest = root / distribution.MANIFEST_NAME
            original_open = Path.open
            changed = []
            def changing_open(file, *args, **kwargs):
                if file == server and args and args[0] == "rb" and not changed:
                    changed.append(True)
                    with original_open(manifest, "ab") as stream:
                        stream.write(b"\n")
                return original_open(file, *args, **kwargs)
            with patch.object(Path, "open", changing_open):
                with self.assertRaisesRegex(distribution.DistributionError, "changed"):
                    distribution.verify_directory(root)

    def test_manifest_cannot_upgrade_scope_or_claim_bundled_runtime(self):
        manifest = distribution.manifest_for(minimal_payload(), "a" * 40)
        distribution.validate_manifest(manifest)
        bad = copy.deepcopy(manifest)
        bad["scope"] = "full-runtime"
        with self.assertRaises(distribution.DistributionError):
            distribution.validate_manifest(bad)
        bad = copy.deepcopy(manifest)
        bad["runtime_dependencies"][0]["bundled"] = True
        with self.assertRaises(distribution.DistributionError):
            distribution.validate_manifest(bad)
        self.assertFalse(manifest["runtime_dependencies"][0]["bundled"])

    def test_duplicate_required_and_size_records(self):
        manifest = distribution.manifest_for(minimal_payload(), "a" * 40)
        bad = copy.deepcopy(manifest)
        bad["files"].append(dict(bad["files"][0], path=bad["files"][0]["path"].upper()))
        with self.assertRaises(distribution.DistributionError):
            distribution.validate_manifest(bad)
        for size in [-1, True, distribution.MAX_FILE_BYTES + 1]:
            bad = copy.deepcopy(manifest)
            bad["files"][0]["bytes"] = size
            with self.assertRaises(distribution.DistributionError):
                distribution.validate_manifest(bad)
        bad = copy.deepcopy(manifest)
        bad["files"] = [row for row in bad["files"] if row["path"] != "engine/src/autospine_workbench/server.py"]
        with self.assertRaisesRegex(distribution.DistributionError, "required"):
            distribution.validate_manifest(bad)

    def test_archive_links_and_path_traversal_are_rejected(self):
        for path, mode in [("src/autospine_workbench/server.py", stat.S_IFLNK | 0o777), ("../secret.py", stat.S_IFREG | 0o644)]:
            raw = io.BytesIO()
            with zipfile.ZipFile(raw, "w") as archive:
                item = zipfile.ZipInfo(path)
                item.external_attr = mode << 16
                archive.writestr(item, "../../workspace")
            with self.assertRaises(distribution.DistributionError):
                distribution.payload_from_archive(raw.getvalue(), "a" * 40)

    def _publish(self, root):
        payload = minimal_payload()
        manifest = distribution.manifest_for(payload, "a" * 40)
        for name, raw in payload.items():
            file = root / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(raw)
        (root / distribution.MANIFEST_NAME).write_bytes(distribution.canonical_bytes(manifest))
        return manifest

    def test_verifier_rejects_corruption_missing_files_and_unlisted_content(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = self._publish(root)
            summary = distribution.verify_directory(root)
            self.assertEqual(summary["files"], len(manifest["files"]))
            server = root / "engine/src/autospine_workbench/server.py"
            original = server.read_bytes()
            server.write_bytes(b"corrupt")
            with self.assertRaisesRegex(distribution.DistributionError, "hash"):
                distribution.verify_directory(root)
            server.write_bytes(original)
            extra = root / "engine/source.psd"
            extra.write_bytes(b"private")
            with self.assertRaisesRegex(distribution.DistributionError, "extra_file"):
                distribution.verify_directory(root)
            extra.unlink()
            server.unlink()
            with self.assertRaisesRegex(distribution.DistributionError, "missing"):
                distribution.verify_directory(root)

    def test_commit_snapshot_reproducible_and_dirty_files_never_exported(self):
        with tempfile.TemporaryDirectory() as folder:
            parent = Path(folder)
            repo = parent / "repo"
            repo.mkdir()
            files = {name[len("engine/"):]: data for name, data in minimal_payload().items()
                     if name not in {"engine/DEPLOYMENT.md", "engine/DEPENDENCIES.json"}}
            files.update({"tools/worker.py": b"print('worker')\n", "schemas/source.schema.json": b"{}\n",
                          "web/m4-fixed-cohort.json": b'{"private":"old-project"}', "web/tests/private.js": b"test\n",
                          "src/autospine_workbench/model.onnx": b"model excluded"})
            for name, data in files.items():
                file = repo / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(data)
            for args in [["init", "-q"], ["config", "core.autocrlf", "false"], ["add", "."], ["-c", "user.name=Release Test", "-c", "user.email=release-test@example.invalid", "commit", "-qm", "fixture"]]:
                subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
            (repo / "src/autospine_workbench/server.py").write_bytes(b"dirty server MUST NOT SHIP")
            (repo / "tools/untracked.py").write_bytes(b"private untracked")
            first = distribution.package_engine(repo, parent / "release-one")
            second = distribution.package_engine(repo, parent / "release-two")
            self.assertEqual(first["manifest_sha256"], second["manifest_sha256"])
            self.assertEqual(first["archive_sha256"], second["archive_sha256"])
            published = parent / "release-one/engine"
            self.assertEqual((published / "src/autospine_workbench/server.py").read_bytes(), b"release source\n")
            self.assertFalse((published / "tools/untracked.py").exists())
            self.assertFalse((published / "src/autospine_workbench/model.onnx").exists())
            self.assertFalse((published / "web/m4-fixed-cohort.json").exists())
            with self.assertRaisesRegex(distribution.DistributionError, "destination_exists"):
                distribution.package_engine(repo, parent / "release-one")
            self.assertEqual(hashlib.sha256(Path(first["archive"]).read_bytes()).hexdigest(), first["archive_sha256"])
            # Existing verified directories can be archived without rewriting
            # their source, and an existing ZIP is never replaced.
            read_only = distribution.archive_distribution(parent / "release-one", parent / "existing-source.zip")
            self.assertTrue(read_only["source_unchanged"])
            self.assertTrue(read_only["archive_verified"])
            self.assertEqual(read_only["archive_entries"], first["files"] + 1)
            with zipfile.ZipFile(read_only["archive"]) as archive:
                self.assertEqual(archive.read("engine/src/autospine_workbench/server.py"), b"release source\n")
            preserved = Path(read_only["archive"]).read_bytes()
            with self.assertRaisesRegex(distribution.DistributionError, "destination_invalid"):
                distribution.archive_distribution(parent / "release-one", parent / "existing-source.zip")
            self.assertEqual(Path(read_only["archive"]).read_bytes(), preserved)
            with self.assertRaisesRegex(distribution.DistributionError, "destination_invalid"):
                distribution.archive_distribution(parent / "release-one", parent / "release-one/forbidden.zip")


if __name__ == "__main__":
    unittest.main()
