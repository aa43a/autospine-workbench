from pathlib import Path
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import patch
import unittest
import test_motion_repair_execution as base
from autospine_workbench.automation import motion_material_execution as execution
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import read_document
from autospine_workbench.resolved_project import canonical_sha256


class MaterialExecutionTests(unittest.TestCase):
    def setUp(self):
        self.fixture=base.SubmissionTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.manager=self.fixture.manager;self.row=dict(self.fixture.row,action='pose_attachment')
        material={'request.json':b'{}','replacement.png':b'fixture'}
        self.digest=AnimatedStore(self.manager.folder('parent')/'material-returns').publish(material)
        self.store=AnimatedStore(Path(self.fixture.temp.name)/'shared')
        self.manager.character_manager=lambda:SimpleNamespace(application=SimpleNamespace(store=self.store))
        self.mapping=dict(revision=1,action='map',material_bundle_sha256=self.digest,artifact_sha256='a'*64,draft_sha256=canonical_sha256(self.row))
        self.receipt=dict(material_bundle_sha256=self.digest,draft_revision=1)

    def invoke(self,rows=None,parent_files=None):
        with patch('autospine_workbench.automation.motion_material_mapping.history',return_value=rows or [self.mapping]), \
             patch('autospine_workbench.automation.motion_material_return.inspect',return_value=dict(returns=[self.receipt])), \
             patch('autospine_workbench.automation.motion_repair_draft.history',return_value=[self.row]), \
             patch('autospine_workbench.automation.motion_repair_material.download'), \
             patch('autospine_workbench.automation.motion_target_jobs.context',return_value=(dict(artifact_sha256='a'*64),parent_files or {})), \
             patch('autospine_workbench.automation.motion_target_jobs.assert_current'):
            return execution.submit(self.manager,'parent',dict(revision=1,mapping_sha256=canonical_sha256(self.mapping)))

    def test_queue_freezes_mapping_and_artwork_without_changing_parent(self):
        result=self.invoke();request=read_document(self.manager.folder(result['job_id'])/'request.json')
        repair=request['repair_execution'];self.assertEqual(repair['material_mapping'],self.mapping)
        self.assertEqual(repair['profile'],execution.PROFILE)
        self.assertEqual(self.store.read(self.digest)['replacement.png'],b'fixture')
        self.assertNotIn('repair_execution',read_document(self.manager.folder('parent')/'request.json'))

    def test_withdrawn_mapping_rejected_before_queue(self):
        with self.assertRaisesRegex(RuntimeError,'mapping_changed'):
            self.invoke([self.mapping,dict(self.mapping,revision=2,action='withdraw')])
        self.manager._pool.submit.assert_not_called()

    def test_material_on_repaired_parent_binds_exact_provenance(self):
        from autospine_workbench.automation.storage_io import canonical_bytes
        parent=self.manager.folder('parent')/'request.json'
        old=read_document(parent);old['repair_execution']={'profile':'prior-partition'}
        parent.write_bytes(canonical_bytes(old));before=parent.read_bytes()
        raw=b'{"profile":"prior-partition","selected":false}'
        result=self.invoke(parent_files={'motion-repair-provenance.json':raw})
        saved=read_document(self.manager.folder(result['job_id'])/'request.json')
        self.assertEqual(saved['repair_execution']['parent_repair_sha256'],sha256(raw).hexdigest())
        self.assertEqual(saved['repair_execution']['parent_artifact_sha256'],'a'*64)
        self.assertEqual(parent.read_bytes(),before)

    def test_retry_keeps_mapping_identity(self):
        from autospine_workbench.automation.motion_repair_execution import retry
        with patch.object(execution,'submit',return_value={'job_id':'new'}) as call:
            result=retry(self.manager,dict(repair_execution=dict(parent_job_id='parent',material_mapping=self.mapping,material_mapping_sha256='x')))
        self.assertEqual(result['job_id'],'new');call.assert_called_once_with(self.manager,'parent',dict(revision=1,mapping_sha256='x'))
