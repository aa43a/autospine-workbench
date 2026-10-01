"""Portable Python boundary, installed RECORD and payload admission regressions."""
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch
import zipfile

_path = Path(__file__).resolve().parents[1] / "tools/kimodo_portable_python.py"
_spec = importlib.util.spec_from_file_location("kimodo_portable_python", _path)
portable = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(portable)


class PortablePythonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="kimodo-portable-unit-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def installation(self, *, outside=None):
        runtime = self.root / "input"
        sp = runtime / ".venv/Lib/site-packages"
        info = sp / "fixture-1.0.dist-info"
        info.mkdir(parents=True)
        payload = {"fixture/__init__.py": b"answer = 42\n",
                   "fixture/native.pyd": b"native dependency bytes\n",
                   "fixture-1.0.dist-info/LICENSE": b"License required for redistribution\n",
                   "fixture-1.0.dist-info/METADATA": b"Metadata-Version: 2.1\nName: fixture\nVersion: 1.0\nLicense: MIT\n\n"}
        for path, raw in payload.items():
            target = sp / path; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw)
        records = [f"{path},sha256={base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip('=')},{len(raw)}"
                   for path, raw in payload.items()]
        if outside:
            path, raw = outside
            target = sp / path; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw)
            records.append(f"{path},sha256={base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip('=')},{len(raw)}")
        records.append("fixture-1.0.dist-info/RECORD,,")
        (info / "RECORD").write_text("\n".join(records), encoding="utf-8")
        return runtime, sp, info

    def official(self, *, bad_path=None, bad_spdx=False, bad_signature=False):
        downloads = self.root / "downloads"; downloads.mkdir()
        archive = downloads / portable.ARCHIVE
        with zipfile.ZipFile(archive, "w") as writer:
            for name in ("python.exe", "python312.dll", "python3.dll", "python312.zip", "python312._pth", "LICENSE.txt"):
                writer.writestr(name, b"Fixture payload: " + name.encode())
            if bad_path:
                writer.writestr(bad_path, b"path escape")
        sha = hashlib.sha256(archive.read_bytes()).hexdigest()
        spdx = {"packages": [{"packageFileName": portable.ARCHIVE, "downloadLocation": "https://wrong.example" if bad_spdx else portable.OFFICIAL_URL,
                              "checksums": [{"algorithm": "SHA256", "checksumValue": sha}]}]}
        signature = {"mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
                     "messageSignature": {"messageDigest": {"algorithm": "SHA2_256", "digest": base64.b64encode(bytes.fromhex("0" * 64 if bad_signature else sha)).decode()},
                                          "signature": base64.b64encode(b"untrusted fixture").decode()},
                     "verificationMaterial": {"certificate": {"rawBytes": base64.b64encode(b"untrusted fixture").decode()}}}
        spdx_path = downloads / (portable.ARCHIVE + ".spdx.json"); spdx_path.write_text(json.dumps(spdx))
        sig_path = downloads / (portable.ARCHIVE + ".sigstore"); sig_path.write_text(json.dumps(signature))
        self.enterContext(patch.object(portable, "ARCHIVE_SHA256", sha))
        self.enterContext(patch.object(portable, "SPDX_SHA256", hashlib.sha256(spdx_path.read_bytes()).hexdigest()))
        self.enterContext(patch.object(portable, "SIGSTORE_SHA256", hashlib.sha256(sig_path.read_bytes()).hexdigest()))
        return downloads

    def invalid_manifest(self, update=None):
        root = self.root / "stage"; root.mkdir()
        manifest = {"schema": portable.SCHEMA, "scope": portable.SCOPE, "python": {}, "baseline_python_version": "3.12.13",
                    "launch_policy": portable.LAUNCH_POLICY,
                    "dependencies": {}, "source": {}, "inventory": [], "runtime_ready": False, "not_validated": []}
        if update:
            manifest.update(update)
        (root / portable.MANIFEST).write_bytes(portable.canonical(manifest))
        return root

    def test_dependency_inventory_keeps_native_license_and_unknown_code(self):
        runtime, sp, info = self.installation()
        (sp / "other.pth").write_bytes(b"Never silently omit another hook\n")
        plan = portable.dependency_plan(runtime)
        paths = {row["path"] for row in plan["files"]}
        self.assertTrue({"fixture/native.pyd", "fixture-1.0.dist-info/LICENSE", "other.pth"} <= paths)
        self.assertEqual(plan["distributions"][0]["license_files"], ["fixture-1.0.dist-info/LICENSE"])

    def test_only_exact_development_hook_allowlist_removed(self):
        runtime, sp, _ = self.installation()
        for name in portable.INJECTIONS:
            (sp / name).write_bytes(b"declared development artifact")
        (sp / "_virtualenv_extra.py").write_bytes(b"must be retained")
        (sp / "fixture/x.py").write_bytes(b"source for generated cache")
        cache = sp / "fixture/__pycache__"; cache.mkdir(); (cache / "x.cpython-312.pyc").write_bytes(b"cache")
        plan = portable.dependency_plan(runtime)
        self.assertEqual({r["path"] for r in plan["removed_development_hooks"]}, set(portable.INJECTIONS))
        self.assertIn("_virtualenv_extra.py", {r["path"] for r in plan["files"]})
        self.assertEqual(plan["omitted_bytecode"], ["fixture/__pycache__/x.cpython-312.pyc"])

    def test_compiled_only_code_and_cache_directory_license_are_retained(self):
        runtime, sp, _ = self.installation()
        cache = sp / "fixture/__pycache__"; cache.mkdir()
        (cache / "orphan.cpython-312.pyc").write_bytes(b"compiled-only code")
        (cache / "LICENSE").write_bytes(b"must retain license")
        (sp / "compiled_only.pyc").write_bytes(b"compiled-only code")
        paths = {r["path"] for r in portable.dependency_plan(runtime)["files"]}
        self.assertTrue({"fixture/__pycache__/orphan.cpython-312.pyc", "fixture/__pycache__/LICENSE", "compiled_only.pyc"} <= paths)

    def test_record_rejects_changed_native_code(self):
        runtime, sp, _ = self.installation()
        (sp / "fixture/native.pyd").write_bytes(b"altered")
        with self.assertRaisesRegex(ValueError, "RECORD"):
            portable.dependency_plan(runtime)

    def test_record_rejects_missing_payload(self):
        runtime, sp, _ = self.installation()
        (sp / "fixture/native.pyd").unlink()
        with self.assertRaisesRegex(ValueError, "missing"):
            portable.dependency_plan(runtime)

    def test_record_console_launcher_exclusion_is_individual_and_hashed(self):
        runtime, _, _ = self.installation(outside=("../../Scripts/fixture.exe", b"external-base launcher"))
        plan = portable.dependency_plan(runtime)
        self.assertEqual(plan["removed_console_entrypoints"][0]["path"], ".venv/Scripts/fixture.exe")
        self.assertEqual(plan["removed_console_entrypoints"][0]["sha256"], hashlib.sha256(b"external-base launcher").hexdigest())

    def test_record_dependency_share_data_retained(self):
        runtime, _, _ = self.installation(outside=("../../share/man/man1/fixture.1", b"dependency manual"))
        plan = portable.dependency_plan(runtime)
        self.assertEqual(plan["retained_non_site_data"][0]["path"], ".venv/share/man/man1/fixture.1")

    def test_record_cannot_escape_runtime(self):
        runtime, _, _ = self.installation(outside=("../../../untrusted.py", b"external code"))
        with self.assertRaisesRegex(ValueError, "boundary"):
            portable.dependency_plan(runtime)

    def test_private_policy_has_fixed_paths_and_sets_bytecode_before_unpacked_import(self):
        self.assertEqual(portable.PTH.decode().splitlines(), ["python312.zip", ".", "kimodo-policy.zip", "../Lib/site-packages", "../../source", "import site"])
        self.assertLess(portable.POLICY.index(b"sys.dont_write_bytecode = True"), portable.POLICY.index(b"import os"))
        receipt = {"files": [{"path": "kimodo/__init__.py", "byte_length": 0, "sha256": hashlib.sha256(b"").hexdigest()}]}
        with zipfile.ZipFile(portable.io.BytesIO(portable.policy_zip(receipt))) as reader:
            self.assertEqual(reader.namelist(), ["sitecustomize.py", "kimodo-source-guard.json"])
            self.assertEqual(reader.read("sitecustomize.py"), portable.POLICY)
            guard = json.loads(reader.read("kimodo-source-guard.json"))
            self.assertEqual(guard["receipt_sha256"], hashlib.sha256(portable.canonical(receipt)).hexdigest())
        self.assertEqual(portable.policy_zip(receipt), portable.policy_zip(receipt))

    def test_official_digest_bound_without_claiming_verified_trust_chain(self):
        result = portable.inspect_official_archive(self.official())
        self.assertEqual(result["archive"]["sha256"], portable.ARCHIVE_SHA256)
        self.assertIn("trust-chain-not-verified", result["signature_status"])

    def test_changed_official_archive_rejected(self):
        downloads = self.official()
        with (downloads / portable.ARCHIVE).open("ab") as stream:
            stream.write(b"modified")
        with self.assertRaisesRegex(ValueError, "SHA256"):
            portable.inspect_official_archive(downloads)

    def test_archive_path_escape_rejected(self):
        with self.assertRaisesRegex(ValueError, "path"):
            portable.inspect_official_archive(self.official(bad_path="../python.exe"))

    def test_official_spdx_binding_rejected(self):
        with self.assertRaisesRegex(ValueError, "SPDX"):
            portable.inspect_official_archive(self.official(bad_spdx=True))

    def test_signature_digest_binding_rejected(self):
        with self.assertRaisesRegex(ValueError, "signature"):
            portable.inspect_official_archive(self.official(bad_signature=True))

    def test_duplicate_json_and_bad_paths_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            portable.strict_json(b'{"a":1,"a":2}')
        for path in ("../x", "C:/x", "x\\y", "x/../y", "NUL.py", "x."):
            with self.subTest(path=path), self.assertRaises(ValueError):
                portable.safe_path(path)

    def test_partial_component_must_not_claim_ready(self):
        root = self.invalid_manifest({"runtime_ready": True})
        with self.assertRaisesRegex(ValueError, "claim ready"):
            portable.verify_python_stage(root)

    def test_isolated_flags_cannot_be_omitted_from_manifest_contract(self):
        root = self.invalid_manifest({"launch_policy": {"profile": "bare-executable"}})
        with self.assertRaisesRegex(ValueError, "launch policy"):
            portable.verify_python_stage(root)

    def guarded_process(self, *, altered=False, extra=False):
        root = self.root / "guarded"; scripts = root / ".venv/Scripts"; scripts.mkdir(parents=True)
        source = root / "source"; source.mkdir()
        raw = b"No source code is executed by the guard\n"
        receipt = {"files": [{"path": "code.py", "byte_length": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}]}
        (root / portable.SOURCE_RECEIPT).write_bytes(portable.canonical(receipt))
        (source / "code.py").write_bytes(raw + b"changed" if altered else raw)
        if extra:
            (source / "extra.py").write_bytes(b"new code")
        (scripts / "kimodo-policy.zip").write_bytes(portable.policy_zip(receipt))
        # This tests the guard after interpreter initialization. The actual
        # Windows embeddable isolation/driver probe is separate release evidence.
        script = '''import sys,os,site,json,hashlib,stat,zipfile
root=sys.argv[1];base=os.path.join(root,'.venv','Scripts')
sys.executable=os.path.join(base,'python.exe')
sys.path=[os.path.join(base,'python312.zip'),base,os.path.join(base,'kimodo-policy.zip'),os.path.normpath(os.path.join(base,'../Lib/site-packages')),os.path.join(root,'source')]
with zipfile.ZipFile(os.path.join(base,'kimodo-policy.zip')) as z: code=z.read('sitecustomize.py')
exec(compile(code,'guarded-sitecustomize.py','exec'))
print(sys._kimodo_source_guard_verified)
'''
        return subprocess.run([sys.executable, "-I", "-B", "-X", "utf8", "-c", script, str(root)], capture_output=True)

    def test_source_startup_guard_checks_bytes_before_source_execution(self):
        result = self.guarded_process()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), b"True")

    def test_source_startup_guard_rejects_changed_source(self):
        result = self.guarded_process(altered=True)
        self.assertEqual(result.returncode, 79, result.stderr)

    def test_source_startup_guard_rejects_extra_code(self):
        result = self.guarded_process(extra=True)
        self.assertEqual(result.returncode, 79, result.stderr)

    def test_unknown_schema_key_rejected(self):
        root = self.invalid_manifest({"untrusted": True})
        with self.assertRaisesRegex(ValueError, "schema"):
            portable.verify_python_stage(root)

    def test_manifest_digest_receipt_required_when_supplied(self):
        root = self.invalid_manifest()
        with self.assertRaisesRegex(ValueError, "receipt"):
            portable.verify_python_stage(root, expected_manifest_sha256="0" * 64)

    def test_extra_file_rejected_before_any_external_tool(self):
        root = self.invalid_manifest(); (root / "injected.py").write_bytes(b"code")
        with self.assertRaisesRegex(ValueError, "inventory"):
            portable.verify_python_stage(root)

    def test_extra_empty_model_slot_is_not_a_complete_python_component(self):
        root = self.invalid_manifest(); (root / "models").mkdir()
        with self.assertRaisesRegex(ValueError, "directory"):
            portable.verify_python_stage(root)

    def test_symlink_file_not_admitted(self):
        root = self.root / "aliases"; root.mkdir(); target = root / "real.py"; target.write_bytes(b"code")
        alias = root / "alias.py"
        try:
            alias.symlink_to(target)
        except OSError:
            self.skipTest("File symlink creation unavailable")
        with self.assertRaisesRegex(ValueError, "alias"):
            portable._walk(root)


if __name__ == "__main__":
    unittest.main()
