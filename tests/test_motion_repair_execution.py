from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
from threading import RLock
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from autospine_workbench.automation import motion_repair_execution as execution
from autospine_workbench.automation.storage_io import canonical_bytes, read_document
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.selected_attachment_repair import build


class SubmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        def folder(job,create=False):
            path=root/job
            if create:path.mkdir(exist_ok=True)
            return path
        self.request=dict(kind='adapt',project_id='alice',character_job_id='character',name='reach',source_job_id='source')
        folder('parent',True).joinpath('request.json').write_bytes(canonical_bytes(self.request))
        self.manager=SimpleNamespace(_lock=RLock(),_closed=False,_jobs={},_cancel={},_pool=Mock(),_execute=Mock(),
            folder=folder,get=lambda _:dict(kind='adapt',status='succeeded'))
        self.row=dict(slot='arm',animation='reach',event=dict(triangle=1,time=.5),action='local_repair',
            artifact_sha256='a'*64,evidence_sha256='b'*64,revision=1)

    def invoke(self,rows=None,**body):
        with patch('autospine_workbench.automation.motion_repair_draft.evidence',return_value=({'artifact_sha256':'a'*64},'b'*64)), \
             patch('autospine_workbench.automation.motion_repair_draft.history',return_value=rows or [self.row]), \
             patch('autospine_workbench.automation.motion_target_jobs.assert_current'):
            return execution.submit(self.manager,'parent',dict(revision=1,draft_sha256=canonical_sha256(self.row),**body))

    def test_frozen_plan_queued_without_mutating_parent(self):
        value=self.invoke();saved=read_document(self.manager.folder(value['job_id'])/'request.json')
        self.assertEqual(saved['repair_execution']['draft'],self.row)
        self.assertEqual(read_document(self.manager.folder('parent')/'request.json'),self.request)
        self.manager._pool.submit.assert_called_once_with(self.manager._execute,value['job_id'])

    def test_withdrawn_plan_and_nested_repair_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'plan_changed'):
            self.invoke(rows=[self.row,dict(self.row,action='withdraw',revision=2)])
        self.request['repair_execution']={'profile':'old'}
        (self.manager.folder('parent')/'request.json').write_bytes(canonical_bytes(self.request))
        with self.assertRaisesRegex(RuntimeError,'nested_execution'):
            self.invoke()

    def test_retry_does_not_fall_back_to_plain_retarget(self):
        request=dict(repair_execution=dict(parent_job_id='parent',draft=self.row,draft_sha256='c'*64))
        with patch.object(execution,'submit',return_value={'job_id':'new'}) as call:
            self.assertEqual(execution.retry(self.manager,request),{'job_id':'new'})
        call.assert_called_once_with(self.manager,'parent',dict(revision=1,draft_sha256='c'*64))

    def test_partition_requires_region_and_freezes_distinct_profile(self):
        self.row['action']='partition'
        with self.assertRaisesRegex(RuntimeError,'region_required'):self.invoke()
        self.row['partition']=dict(mesh_sha256='d'*64,triangles=[0],bone='hand_l')
        value=self.invoke();saved=read_document(self.manager.folder(value['job_id'])/'request.json')
        self.assertEqual(saved['repair_execution']['profile'],execution.PARTITION_PROFILE)
        self.assertEqual(saved['repair_execution']['draft']['partition'],self.row['partition'])

    def test_region_order_requires_selection_and_freezes_distinct_profile(self):
        self.row['action']='region_order'
        with self.assertRaisesRegex(RuntimeError,'region_order_required'):self.invoke()
        self.row['region_order']=dict(mesh_sha256='d'*64,triangles=[0],reference_slot='body',side='after')
        value=self.invoke();saved=read_document(self.manager.folder(value['job_id'])/'request.json')
        self.assertEqual(saved['repair_execution']['profile'],execution.ORDER_PROFILE)
        self.assertEqual(saved['repair_execution']['draft']['region_order'],self.row['region_order'])

    def test_missing_repair_depth_is_readable_but_not_a_pass(self):
        from autospine_workbench.automation.motion_target_jobs import review_file
        with patch('autospine_workbench.automation.motion_target_jobs.context',return_value=({'repair_profile':execution.PROFILE},{})), \
             patch('autospine_workbench.automation.motion_target_jobs.runtime_reader'):
            raw,mime=review_file(None,'job',['depth.html'])
        self.assertIn('尚未重新验证',raw.decode())
        self.assertIn('不表示遮挡通过',raw.decode())
        self.assertIn('text/html',mime)

    def test_interval_order_profile_and_payload_frozen(self):
        self.row['action']='region_order'
        self.row['region_order']=dict(mesh_sha256='d'*64,triangles=[0],reference_slot='body',side='after',interval=[1,2])
        value=self.invoke();saved=read_document(self.manager.folder(value['job_id'])/'request.json')
        self.assertEqual(saved['repair_execution']['profile'],execution.INTERVAL_ORDER_PROFILE)
        self.row['region_order']['interval'][0]=0
        self.assertEqual(saved['repair_execution']['draft']['region_order']['interval'],[1,2])


class SelectedRepairTests(unittest.TestCase):
    def test_only_selected_deform_changes_and_old_depth_not_reissued(self):
        from test_character_affine_repair import fixture
        from autospine_workbench.targets.character43.affine_pose import sample
        doc=fixture();doc['skins'][0]['name']='default'
        mesh=doc['skins'][0]['attachments']['mesh']['mesh'];mesh.update(type='mesh',uvs=[0,0,1,0,0,1])
        doc['slots']=[dict(name='mesh',bone='a',attachment='mesh'),dict(name='other',bone='a',attachment='other')]
        doc['skins'][0]['attachments']['other']={'other':deepcopy(mesh)}
        old={'default':{'other':{'other':{'deform':[dict(time=0,vertices=[0]*10)]}}}}
        doc['animations']['walk']['attachments']=old
        raw=canonical_bytes(doc);digest=sha256(raw).hexdigest()
        setup=sample(dict(doc,animations={'walk':{'bones':{}}}),'walk',0)[0]
        files={'skeleton.json':raw,'rig-setup-reference.json':canonical_bytes(dict(skeleton_sha256=digest,vertices=setup)),
            'numeric-reference.json':canonical_bytes(dict(skeleton_sha256=digest,animations={'walk':[dict(time=0),dict(time=1)]})),
            'motion-review.json':canonical_bytes(dict(reference_length_px=10,issues=[])),
            'motion-contact.json':b'{}','motion-ir.json':b'{}','character-manifest.json':b'{}',
            'deformation.json':b'{"passed":false}','motion-depth.json':b'old depth','images/mesh.png':b'exact'}
        with patch('autospine_workbench.targets.character43.final_motion_contact.recheck',return_value={'status':'unavailable_no_labels'}):
            output,evidence,geometry=build(files,dict(slot='mesh',animation='walk'))
        actual=json.loads(output['skeleton.json'])
        self.assertEqual(actual['animations']['walk']['bones'],doc['animations']['walk']['bones'])
        self.assertEqual(actual['animations']['walk']['attachments']['default']['other'],old['default']['other'])
        self.assertEqual(actual['skins'],doc['skins'])
        self.assertNotIn('motion-depth.json',output)
        self.assertEqual(output['images/mesh.png'],b'exact')
        self.assertEqual(evidence['status'],'needs_changes')
        self.assertGreater(geometry['records'][0]['sample_count'],2)
