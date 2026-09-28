from copy import deepcopy
import math
import unittest
from autospine_workbench.targets.character43.motion_layer_edits import apply, validate, warp, PROFILE
from autospine_workbench.targets.character43.affine_pose import sample
from test_torso_projection import fixture as base


def fixture():
    doc=base()
    doc['slots']=[dict(name=s,bone='root',attachment=s) for s in doc['skins'][0]['attachments']]
    for choices in doc['skins'][0]['attachments'].values():
        for a in choices.values():a.update(type='mesh',uvs=[0,0,1,0,0,1])
    # A vertex controlled by two bones, under animated rotation and axial scaling.
    doc['skins'][0]['attachments']['arm']['arm']['vertices']=[2,1,1,0,.4,4,1,0,.6,1,4,0,1,1,1,4,1,1,1]
    doc['animations']['move']['bones']['root']={'rotate':[dict(time=0,value=0),dict(time=1,value=45)],
        'scale':[dict(time=0,x=1,y=1),dict(time=1,x=1.2,y=.9)]}
    doc['animations']['move']['attachments']={'default':{'arm':{'arm':{'deform':[
        dict(time=0,vertices=[0]*8),dict(time=1,vertices=[.1]*8)]}}}}
    return doc


def edits():
    return dict(profile=PROFILE,transforms=[dict(slot='arm',dx=5,dy=-3,rotation=35,scaleX=1.1,scaleY=.8)],draw_order=[])


class LayerEditsTests(unittest.TestCase):
    def test_weighted_transform_preserves_others_rig_and_existing_deform(self):
        doc=fixture();original=deepcopy(doc);e=edits()
        result,report,times=apply(doc,'move',e,[0,.5,1])
        self.assertEqual(doc,original)
        self.assertEqual(result['bones'],doc['bones']);self.assertEqual(result['skins'],doc['skins'])
        pivot=report['pivots']['arm']
        for t in [0,.123,.5,.789,1]:
            before=sample(doc,'move',t)[0];after=sample(result,'move',t)[0]
            for p,q in zip(before['arm'],after['arm']):
                self.assertLess(math.dist(warp(p,e['transforms'][0],pivot),q),.01)
            for slot in ['head','leg','torso']:self.assertEqual(before[slot],after[slot])
        self.assertLess(report['interpolation_max_error_px'],.01)

    def test_order_overrides_animation_only(self):
        doc=fixture();e=edits();e['transforms']=[]
        slots=[s['name'] for s in doc['slots']];e['draw_order']=slots[::-1]
        result,_,_=apply(doc,'move',e,[0,1])
        self.assertEqual(result['slots'],doc['slots'])
        self.assertEqual(result['animations']['move']['drawOrder'][0]['offsets'],
                         [dict(slot=s,offset=len(slots)-1-2*i) for i,s in enumerate(slots)])

    def test_validation_rejects_mismatch_nonfinite_duplicate_and_unknown(self):
        doc=fixture()
        cases=[]
        e=edits();e['transforms'][0]['dx']=float('nan');cases.append(e)
        e=edits();e['transforms'][0]['scaleX']=0;cases.append(e)
        e=edits();e['transforms'][0]['slot']='absent';cases.append(e)
        e=edits();e['transforms']*=2;cases.append(e)
        e=edits();e['draw_order']=['arm'];cases.append(e)
        e=edits();e['silent']=True;cases.append(e)
        for value in cases:
            with self.assertRaises(ValueError):validate(value,doc)

    def test_region_rejected_explicitly(self):
        doc=fixture();doc['skins'][0]['attachments']['arm']['arm']['type']='region'
        with self.assertRaisesRegex(ValueError,'attachment_unsupported'):apply(doc,'move',edits(),[0,1])

    def test_submission_freezes_edits_and_rejects_wrong_slot_before_enqueue(self):
        import json
        import tempfile
        from pathlib import Path
        from io import BytesIO
        from types import SimpleNamespace
        from unittest.mock import patch
        from test_mixamo_map import source
        from autospine_workbench.automation.motion_intake_jobs import MotionIntakeJobs
        from autospine_workbench.automation.motion_intake_worker import compile_source
        from autospine_workbench.automation.motion_target_jobs import submit
        from autospine_workbench.automation.storage_io import read_document
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);manager=MotionIntakeJobs(SimpleNamespace(state_root=root,workspace_root=root))
            self.addCleanup(manager.close)
            with patch.object(manager._pool,'submit'),patch('autospine_workbench.automation.animated_store.AnimatedStore.read',return_value={'skeleton.json':json.dumps(fixture()).encode()}):
                raw=source();queued=manager.upload(BytesIO(raw),len(raw),'source.bvh','front')
                result=compile_source(raw,'front',manager.folder(queued['job_id']),root)
                manager._jobs[queued['job_id']].update(status='succeeded',step='complete',result=result)
                character=dict(status='needs_review',artifact_sha256='b'*64)
                manager.character_manager=lambda:SimpleNamespace(verified_snapshot=lambda *_:(dict(character),{}),get=lambda *_:character)
                body=dict(project_id='alice',character_job_id='job-'+'c'*32,layer_edits=edits())
                queued_target=submit(manager,queued['job_id'],body)
                frozen=read_document(manager.folder(queued_target['job_id'])/'request.json')
                body['layer_edits']['transforms'][0]['slot']='missing'
                before=set(manager._jobs)
                with self.assertRaisesRegex(Exception,'target_mismatch'):submit(manager,queued['job_id'],body)
                self.assertEqual(set(manager._jobs),before)
                self.assertEqual(frozen['layer_edits']['transforms'][0]['slot'],'arm')

    def test_readiness_does_not_reuse_pre_edit_depth_or_surface_contact(self):
        import json
        from hashlib import sha256
        from test_motion_readiness import fixture as evidence_fixture
        from autospine_workbench.targets.character43.motion_readiness import build
        files,runtime=evidence_fixture()
        depth=json.loads(files['motion-depth.json']);depth['status']='manual_layer_edits_require_depth_review'
        files['motion-depth.json']=json.dumps(depth).encode()
        files['motion-contact.json']=json.dumps(dict(status='ankle_proxy_passed',layer_surface_status='unverified')).encode()
        files['motion-layer-edits.json']=json.dumps(dict(skeleton_sha256=sha256(files['skeleton.json']).hexdigest(),edits=edits())).encode()
        report=build(files,'a'*64,runtime);stages={r['stage']:r['status'] for r in report['stages']}
        self.assertEqual(stages['遮挡'],'unmeasured')
        self.assertEqual(stages['接触'],'unmeasured')
        self.assertEqual(stages['图层校正'],'unmeasured')
