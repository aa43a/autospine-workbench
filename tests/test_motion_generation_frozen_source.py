"""Real Git builder fixtures, adversarial receipts and metadata-free replay.

The tiny fixture commits are explicitly substituted for the production pins;
none of these tests pretend that synthetic code is an official Kimodo release.
"""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from autospine_workbench.automation import motion_generation_frozen_source as frozen
from autospine_workbench.automation import motion_generation_provenance as provenance
from autospine_workbench.automation import motion_generation_runtime_plan as runtime_plan
from autospine_workbench.automation.storage_io import canonical_bytes


class FrozenSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runtime = self.root / 'runtime'
        self.source = self.runtime / 'source'
        self.source.mkdir(parents=True)
        self.git = shutil.which('git')
        if not self.git:
            self.skipTest('The opt-in build fixture requires Git; runtime does not.')
        self.git = str(Path(self.git).absolute())
        for relative in frozen.REQUIRED_SOURCE:
            path = self.source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'# synthetic fixture, not Kimodo\n')
        (self.source / 'kimodo/__init__.py').write_bytes(b'# fixture\n')
        self.run_git('init', '-q')
        self.run_git('config', 'core.autocrlf', 'false')
        self.run_git('add', '.')
        self.run_git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                     'commit', '-qm', 'Synthetic upstream')
        upstream = self.run_git('rev-parse', 'HEAD').strip().decode('ascii')
        (self.source / 'kimodo/model/llm2vec/llm2vec.py').write_bytes(b'# synthetic local fix\n')
        self.run_git('add', '.')
        self.run_git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                     'commit', '-qm', 'Synthetic pinned local fix')
        loader = self.run_git('rev-parse', 'HEAD').strip().decode('ascii')
        for name, value in [('UPSTREAM_REVISION', upstream), ('PINNED_REVISION', loader)]:
            manager = patch.object(frozen, name, value)
            manager.start()
            self.addCleanup(manager.stop)
        self.upstream, self.loader = upstream, loader

    def run_git(self, *args):
        return subprocess.check_output([self.git, '-c', f'safe.directory={self.source.as_posix()}',
                                         '-C', str(self.source), *args],
                                        env=dict(os.environ, GIT_CONFIG_NOSYSTEM='1',
                                                 GIT_CONFIG_GLOBAL=os.devnull),
                                        stdin=subprocess.DEVNULL, stderr=subprocess.PIPE)

    def build(self, **kwargs):
        return frozen.build_frozen_source_plan(self.runtime, git_executable=self.git, **kwargs)

    def install(self, plan=None):
        plan = self.build() if plan is None else plan
        destination = self.root / 'installed'
        destination.mkdir()
        for relative in plan['copy_source_paths']:
            source, target = self.source / relative, destination / 'source' / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        self.save_receipt(destination, plan['receipt'])
        return destination, deepcopy(plan['receipt'])

    @staticmethod
    def save_receipt(root, value):
        (root / frozen.RECEIPT).write_bytes(canonical_bytes(value))

    def test_real_git_objects_replay_without_git_or_metadata_and_hash_actual_files(self):
        plan = self.build()
        installed, _ = self.install(plan)
        self.assertFalse((installed / 'source/.git').exists())
        with patch('subprocess.check_output', side_effect=AssertionError('Runtime must not invoke Git')), \
                patch.dict(os.environ, {'PATH': ''}):
            result = frozen.verify_frozen_source(installed)
            self.assertEqual(provenance.code_revision(installed), self.loader)
        self.assertEqual(result['upstream_revision'], self.upstream)
        self.assertFalse(result['upstream_content_unchanged'])
        self.assertEqual(len(result['committed_local_changes']), 1)
        self.assertEqual(result['local_changes'], [])
        self.assertFalse(plan['runtime_ready'])
        before = result['source_inventory_sha256']
        (installed / 'source/kimodo/scripts/generate.py').write_bytes(b'# changed after build\n')
        with self.assertRaisesRegex(ValueError, 'frozen_source_changed'):
            frozen.verify_frozen_source(installed)
        self.assertEqual(before, plan['receipt']['source_inventory_sha256'])

    def test_revision_string_or_rehashed_tree_cannot_forge_the_pinned_commit(self):
        installed, receipt = self.install()
        receipt['repository']['loader_tree'][0]['blob_sha1'] = 'f' * 40
        self.save_receipt(installed, receipt)
        with self.assertRaisesRegex(ValueError, 'frozen_commit_mismatch'):
            frozen.verify_frozen_source(installed)
        receipt['repository']['loader_revision'] = 'a' * 40
        self.save_receipt(installed, receipt)
        with self.assertRaisesRegex(ValueError, 'loader_changed'):
            frozen.verify_frozen_source(installed)

    def test_windows_crlf_checkout_is_explicit_and_reverified(self):
        path = self.source / 'kimodo/scripts/generate.py'
        path.write_bytes(path.read_bytes().replace(b'\n', b'\r\n'))
        plan = self.build()
        self.assertEqual(plan['receipt']['local_changes'][0]['kind'], 'crlf-checkout')
        installed, receipt = self.install(plan)
        frozen.verify_frozen_source(installed)
        receipt['local_changes'][0]['declaration'] = 'Pretend official'
        self.save_receipt(installed, receipt)
        with self.assertRaises(ValueError):
            frozen.verify_frozen_source(installed)

    def test_local_patch_requires_declaration_and_is_not_upstream(self):
        path = self.source / 'kimodo/scripts/generate.py'
        path.write_bytes(b'# deliberate new local byte patch\n')
        with self.assertRaisesRegex(ValueError, 'undeclared_source_patch'):
            self.build()
        plan = self.build(declared_patches={'kimodo/scripts/generate.py': 'Synthetic deliberate patch.'})
        installed, receipt = self.install(plan)
        result = frozen.verify_frozen_source(installed)
        self.assertEqual(result['local_changes'][0]['kind'], 'modified')
        self.assertFalse(result['upstream_content_unchanged'])
        receipt['local_changes'] = []
        self.save_receipt(installed, receipt)
        with self.assertRaisesRegex(ValueError, 'undeclared_source_patch'):
            frozen.verify_frozen_source(installed)

    def test_self_hashed_arbitrary_source_without_patch_admission_is_rejected(self):
        installed, receipt = self.install()
        path = installed / 'source/kimodo/scripts/generate.py'
        path.write_bytes(b'# arbitrary replacement\n')
        row, _ = frozen._record(path, 'kimodo/scripts/generate.py')
        receipt['files'] = [row if r['path'] == row['path'] else r for r in receipt['files']]
        receipt['source_inventory_sha256'] = sha256(canonical_bytes(receipt['files'])).hexdigest()
        self.save_receipt(installed, receipt)
        with self.assertRaisesRegex(ValueError, 'undeclared_source_patch'):
            frozen.verify_frozen_source(installed)

    def test_required_code_cannot_be_deleted_even_with_a_declared_patch(self):
        (self.source / 'kimodo/scripts/generate.py').unlink()
        with self.assertRaisesRegex(ValueError, 'source_unavailable'):
            self.build(declared_patches={'kimodo/scripts/generate.py': 'Deleted fixture.'})

    def test_build_excludes_known_generated_files_but_runtime_rejects_extra_code_and_metadata(self):
        cache = self.source / 'kimodo/__pycache__'
        cache.mkdir()
        (cache / 'fixture.pyc').write_bytes(b'fixture bytecode')
        metadata = self.source / 'kimodo.egg-info'
        metadata.mkdir()
        (metadata / 'not-zip-safe').write_bytes(b'\n\n')
        plan = self.build()
        self.assertIn('kimodo/__pycache__/fixture.pyc', plan['omitted_build_artifacts'])
        self.assertIn('kimodo.egg-info/not-zip-safe', plan['omitted_build_artifacts'])
        installed, _ = self.install(plan)
        frozen.verify_frozen_source(installed)
        (installed / 'source/extra.py').write_bytes(b'# extra code\n')
        with self.assertRaisesRegex(ValueError, 'frozen_source_changed'):
            frozen.verify_frozen_source(installed)
        (installed / 'source/extra.py').unlink()
        (installed / 'source/.git').mkdir()
        with self.assertRaisesRegex(ValueError, 'frozen_source_unsafe'):
            frozen.verify_frozen_source(installed)
        (cache / 'hidden.py').write_bytes(b'# cannot hide code in an ignored directory\n')
        with self.assertRaisesRegex(ValueError, 'undeclared_source_patch'):
            self.build()

    def test_strict_receipt_keys_duplicates_paths_and_wrong_types_never_fall_back(self):
        installed, original = self.install()
        variants = []
        extra = deepcopy(original)
        extra['command'] = 'not accepted'
        variants.append(extra)
        wrong = deepcopy(original)
        wrong['files'][0]['byte_length'] = True
        variants.append(wrong)
        escape = deepcopy(original)
        escape['files'][0]['path'] = '../outside.py'
        variants.append(escape)
        case = deepcopy(original)
        case['files'].append(dict(case['files'][0], path=case['files'][0]['path'].upper()))
        variants.append(case)
        for value in variants:
            self.save_receipt(installed, value)
            with self.subTest(value=value), \
                    patch('subprocess.check_output', side_effect=AssertionError('No Git fallback')), \
                    self.assertRaises(ValueError):
                provenance.code_revision(installed)
        raw = canonical_bytes(original).replace(b'"schema":', b'"schema":"duplicate","schema":', 1)
        (installed / frozen.RECEIPT).write_bytes(raw)
        with self.assertRaisesRegex(ValueError, 'frozen_source_invalid'):
            provenance.code_revision(installed)

    def test_aliases_are_rejected_at_source_file_directory_and_receipt(self):
        installed, _ = self.install()
        path = installed / 'source/kimodo/scripts/generate.py'
        outside = self.root / 'outside.py'
        outside.write_bytes(path.read_bytes())
        path.unlink()
        try:
            path.symlink_to(outside)
        except OSError:
            self.skipTest('Symlink creation is unavailable.')
        with self.assertRaisesRegex(ValueError, 'frozen_source_invalid'):
            frozen.verify_frozen_source(installed)
        path.unlink()
        shutil.copyfile(outside, path)
        receipt = installed / frozen.RECEIPT
        target = self.root / 'receipt.json'
        target.write_bytes(receipt.read_bytes())
        receipt.unlink()
        receipt.symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'frozen_source_invalid'):
            provenance.code_revision(installed)
        receipt.unlink()
        shutil.copyfile(target, receipt)
        scripts = installed / 'source/kimodo/scripts'
        outside_scripts = self.root / 'outside-scripts'
        scripts.rename(outside_scripts)
        scripts.symlink_to(outside_scripts, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'frozen_source_unsafe'):
            frozen.verify_frozen_source(installed)

    def test_unreadable_or_dangling_receipts_cannot_trigger_legacy_git(self):
        receipt = self.runtime / frozen.RECEIPT
        with patch.object(Path, 'lstat', side_effect=PermissionError('fixture')):
            with self.assertRaisesRegex(ValueError, 'source_unavailable'):
                provenance.code_revision(self.runtime)
        try:
            receipt.symlink_to(self.root / 'missing-receipt.json')
        except OSError:
            self.skipTest('Symlink creation is unavailable.')
        try:
            with patch('subprocess.check_output', side_effect=AssertionError('No Git fallback')), \
                    self.assertRaisesRegex(ValueError, 'frozen_source_invalid'):
                provenance.code_revision(self.runtime)
        finally:
            # This sandbox's Windows reparse implementation cannot unlink a
            # dangling file link until its target exists again.
            (self.root / 'missing-receipt.json').write_bytes(b'cleanup fixture')
            receipt.unlink()

    def test_legacy_git_path_and_environment_remain_unchanged_without_a_receipt(self):
        with patch.object(provenance.subprocess, 'check_output', side_effect=[provenance.REVISION, '']) as call:
            self.assertEqual(provenance.code_revision(self.runtime), provenance.REVISION)
        self.assertEqual(call.call_args_list[0].args[0][0], 'git')
        self.assertEqual(call.call_count, 2)

    def test_new_receipt_is_bound_into_generation_environment_and_producer_digest(self):
        installed, _ = self.install()
        def fake_identity(path):
            return dict(byte_length=1, sha256=provenance.WEIGHTS if path.name == 'model.safetensors'
                        else '905664ad05779b0e28c391b85dc81c9de166418bd5f471ef605f75ab746ce391'
                        if path.name == 'config.yaml' else 'a' * 64)
        with patch.object(provenance, 'identity', side_effect=fake_identity), \
                patch('subprocess.check_output', side_effect=AssertionError('No Git')):
            environment = provenance.inspect(installed)
        self.assertEqual(environment['frozen_source']['repository_revision'], self.loader)
        producer = provenance.producer(environment, dict(seed=42))
        self.assertEqual(producer['checkpoint_manifest_sha256'], sha256(canonical_bytes(environment)).hexdigest())


    def test_plan_closes_required_payload_and_preserves_external_python_cuda_and_model_limits(self):
        manifest = dict(schema_version='modelscope-file-manifest/v1', model_id='LLM-Research/Meta-Llama-3-8B-Instruct',
                        files=[dict(path='weights.safetensors', bytes=6, sha256=sha256(b'weight').hexdigest()),
                               dict(path='model.safetensors.index.json', bytes=0, sha256='')])
        index = canonical_bytes(dict(weight_map={'fixture': 'weights.safetensors'}))
        manifest['files'][1].update(bytes=len(index), sha256=sha256(index).hexdigest())
        raw = canonical_bytes(manifest)
        (self.runtime / runtime_plan.BASE_MANIFEST).write_bytes(raw)
        required = {'tools/modelscope_text_encoder.py': b'# safe fixture\n',
                    runtime_plan.CHECKPOINT + '/LICENSE': b'Synthetic license',
                    runtime_plan.MNTP + '/adapter_model.safetensors': b'weight'}
        for relative, content in {**required, runtime_plan.BASE_MODEL + '/weights.safetensors': b'weight',
                                  runtime_plan.BASE_MODEL + '/model.safetensors.index.json': index,
                                  '.venv/Scripts/python.exe': b'not executed',
                                  '.venv/pyvenv.cfg': b'home = C:\\external\\python\n'}.items():
            path = self.runtime / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        pins = {path: (len(raw), sha256(raw).hexdigest()) for path, raw in required.items()}
        with patch.object(runtime_plan, 'FIXED_FILES', pins), \
                patch.object(runtime_plan, 'BASE_MANIFEST_SHA256', sha256(raw).hexdigest()):
            plan = runtime_plan.build_runtime_integrity_plan(self.runtime, git_executable=self.git)
            self.assertFalse(plan['runtime_ready'])
            self.assertFalse(plan['all_required_model_bytes_verified'])
            self.assertTrue(plan['interpreter']['external_base_required'])
            self.assertIn('cuda_not_checked', plan['blockers'])
            full = runtime_plan.build_runtime_integrity_plan(self.runtime, git_executable=self.git, verify_weight_bytes=True)
            self.assertTrue(full['all_required_model_bytes_verified'])
            self.assertFalse(full['runtime_ready'])
            weights = self.runtime / runtime_plan.BASE_MODEL / 'weights.safetensors'
            weights.write_bytes(b'tamper')
            with self.assertRaisesRegex(ValueError, 'runtime_payload_changed'):
                runtime_plan.build_runtime_integrity_plan(self.runtime, git_executable=self.git, verify_weight_bytes=True)
            weights.write_bytes(b'weight')
            (self.runtime / 'tools/modelscope_text_encoder.py').write_bytes(b'# evil fixture\n')
            with self.assertRaisesRegex(ValueError, 'runtime_payload_changed'):
                runtime_plan.build_runtime_integrity_plan(self.runtime, git_executable=self.git)


if __name__ == '__main__':
    unittest.main()
