"""Real asset coexistence and lifecycle persistence across fresh service instances."""
import importlib.util
from io import BytesIO
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from autospine_workbench.automation.asset_library import AssetLibrary
from autospine_workbench.automation.psd_import_jobs import PsdImportJobs
from autospine_workbench.automation.storage_io import publish_document
from autospine_workbench.project_store import ProjectStore


OPTIONAL = bool(importlib.util.find_spec('psd_tools') and importlib.util.find_spec('PIL'))


def tree(path):
    return {p.relative_to(path).as_posix(): p.read_bytes() for p in path.rglob('*') if p.is_file()}


class AssetIntakeLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.projects = self.new_store()

    def new_store(self):
        return ProjectStore(self.root, self.root/'state', measure_composite_quality=False)

    def manager(self, store=None):
        manager = PsdImportJobs(store or self.projects)
        self.addCleanup(manager.close)
        return manager

    def upload(self, payload, name='same-name.psd'):
        manager = self.manager()
        queued = manager.upload(BytesIO(payload), len(payload), name)
        manager.close()
        return manager.get(queued['job_id'])

    def psd(self, color):
        from PIL import Image
        from psd_tools import PSDImage
        from psd_tools.api.layers import PixelLayer
        psd = PSDImage.new('RGBA', (24, 24))
        PixelLayer.frompil(Image.new('RGBA', (7, 9), color), psd, name='handwear-l', left=6, top=8)
        output = BytesIO(); psd.save(output)
        return output.getvalue()

    @unittest.skipUnless(OPTIONAL, 'optional real PSD decoder unavailable')
    def test_same_name_different_content_coexists_without_overwriting_first(self):
        first = self.upload(self.psd((255, 0, 0, 255)))
        self.assertEqual(first['status'], 'succeeded', first)
        folder = self.projects.audit_root/first['project_id']; original = tree(folder)
        second = self.upload(self.psd((0, 255, 0, 255)))
        self.assertEqual(second['status'], 'succeeded', second)
        self.assertNotEqual(first['project_id'], second['project_id'])
        fresh = self.new_store()
        self.assertEqual({p['id'] for p in fresh.list_projects()}, {first['project_id'], second['project_id']})
        self.assertEqual([p['name'] for p in AssetLibrary(fresh).list()], ['same-name', 'same-name'])
        self.assertEqual(tree(folder), original)
        self.assertNotEqual(fresh.resolve_asset(first['project_id'], 'composite').read_bytes(),
                            fresh.resolve_asset(second['project_id'], 'composite').read_bytes())

    def test_partial_decoder_failure_never_publishes_project_after_restart(self):
        header = struct.pack('>4sH6sHIIHH', b'8BPS', 1, bytes(6), 4, 24, 24, 8, 3)
        partial = []
        def fail(command, **kwargs):
            output = Path(command[command.index('--output')+1]); output.mkdir()
            (output/'layer-000.png').write_bytes(b'partial image bytes')
            partial.append(output)
            return subprocess.CompletedProcess(command, 1, b'{"reason_code":"psd_decode_failed"}', b'')
        with patch('autospine_workbench.automation.psd_import_jobs.subprocess.run', side_effect=fail):
            result = self.upload(header)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['reason_code'], 'psd_decode_failed')
        self.assertTrue((partial[0]/'layer-000.png').exists())
        fresh = self.new_store(); restarted = self.manager(fresh)
        self.assertEqual(fresh.list_projects(), [])
        self.assertEqual(list(fresh.audit_root.glob('imported-*')), [])
        self.assertEqual(restarted.get(result['job_id']), result)

    @unittest.skipUnless(OPTIONAL, 'optional real PSD decoder unavailable')
    def test_fresh_store_and_manager_restore_success_and_interrupted_job(self):
        result = self.upload(self.psd((12, 34, 56, 255)))
        self.assertEqual(result['status'], 'succeeded', result)
        interrupted = 'import-'+'d'*32
        previous = self.manager(); folder = previous.folder(interrupted, create=True)
        publish_document(folder/'request.json', dict(job_id=interrupted, name='interrupted.psd', source_sha256='f'*64),
                         staging=folder/'staging')
        previous.close()
        fresh = self.new_store(); restarted = self.manager(fresh)
        self.assertEqual(restarted.get(result['job_id']), result)
        self.assertEqual(restarted.get(interrupted)['reason_code'], 'psd_import_interrupted')
        self.assertEqual([p['id'] for p in fresh.list_projects()], [result['project_id']])
        self.assertTrue(fresh.resolve_asset(result['project_id'], 'layer', 'layer-000-handwear-l').is_file())

    @unittest.skipUnless(OPTIONAL, 'optional real PSD decoder unavailable')
    def test_soft_delete_restore_preserves_source_audit_images_and_corrections(self):
        payload = self.psd((20, 70, 90, 255)); result = self.upload(payload)
        self.assertEqual(result['status'], 'succeeded', result)
        project = result['project_id']
        self.projects.save_overrides(project, dict(base_revision=0, joint_overrides={}, layer_overrides={}, notes='reviewed'))
        audit = self.projects.audit_root/project; overrides = self.projects.state_root/'overrides'/project
        before_audit, before_overrides = tree(audit), tree(overrides)
        self.assertTrue(before_overrides)
        source = self.projects.state_root/'jobs'/'psd-import-v1'/result['job_id']/'source.psd'
        self.assertEqual(source.read_bytes(), payload)
        library = AssetLibrary(self.projects)
        library.change(project, dict(action='trash', expected_revision=1))
        fresh = self.new_store(); restored = AssetLibrary(fresh)
        self.assertEqual(restored.metadata(project)['lifecycle'], 'trashed')
        self.assertEqual(restored.change(project, dict(action='restore', expected_revision=2))['lifecycle'], 'active')
        self.assertEqual(tree(audit), before_audit)
        self.assertEqual(tree(overrides), before_overrides)
        self.assertEqual(source.read_bytes(), payload)
        self.assertEqual(fresh.get_project(project)['overrides']['notes'], 'reviewed')


if __name__ == '__main__': unittest.main()
