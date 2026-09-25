import copy
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from autospine_workbench.automation import motion_repair_draft as draft
from autospine_workbench.automation.motion_contact_scope import validate
from autospine_workbench.resolved_project import canonical_sha256


class ContactScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.manager=SimpleNamespace(_lock=threading.RLock(),folder=lambda _:Path(self.temp.name))
        mesh=dict(type='mesh',uvs=[0,0,1,0,1,1,0,1],triangles=[0,1,2,0,2,3])
        doc=dict(bones=[dict(name='chest')],slots=[dict(name='arm'),dict(name='body')],
                 skins=[dict(attachments={'arm':{'arm':mesh},'body':{'body':mesh}})])
        self.files={'skeleton.json':json.dumps(doc).encode()}
        self.report=dict(artifact_sha256='a'*64,rows=[dict(slot='arm',animation='reach',details=[dict(triangle=0,time=.5)])])
        for target,value in [('autospine_workbench.automation.motion_target_jobs.context',({'artifact_sha256':'a'*64},self.files)),
                             ('autospine_workbench.automation.motion_repair_draft.evidence',(self.report,canonical_sha256(self.report)))]:
            p=patch(target,return_value=value); p.start(); self.addCleanup(p.stop)
        self.body=dict(artifact_sha256='a'*64,evidence_sha256=canonical_sha256(self.report),expected_revision=0,
                       action='contact_scope',notes='fixture, not human acceptance',slot='arm',animation='reach',triangle=0,time=.5,
                       contact_scope=dict(mesh_sha256=canonical_sha256(mesh),reference_slot='body',regions=dict(fixed=[0],sliding=[],free=[])))

    def test_save_restore_withdraw_retains_unknown_and_no_acceptance(self):
        state=draft.save(self.manager,'job',self.body)
        scope=state['history'][0]['contact_scope']
        self.assertEqual(scope['unclassified_triangles'],1)
        self.assertEqual(scope['status'],'proposed_contact_scope_not_solved')
        self.assertFalse(state['repair_executed'])
        self.assertEqual(draft.inspect(self.manager,'job')['history'][0]['contact_scope'],scope)
        body=copy.deepcopy(self.body);body.pop('contact_scope');body.update(action='withdraw',expected_revision=1)
        result=draft.save(self.manager,'job',body)
        self.assertEqual(result['history'][0],state['history'][0])
        self.assertEqual(result['history'][1]['action'],'withdraw')
        self.assertFalse((Path(self.temp.name)/'stage-reviews').exists())

    def test_overlap_range_bool_and_empty_rejected(self):
        for regions in [dict(fixed=[0],sliding=[0],free=[]),dict(fixed=[2],sliding=[],free=[]),
                        dict(fixed=[True],sliding=[],free=[]),dict(fixed=[],sliding=[],free=[])]:
            body=copy.deepcopy(self.body);body['contact_scope']['regions']=regions
            with self.subTest(regions=regions),self.assertRaises(RuntimeError):validate(self.manager,'job',body)

    def test_wrong_mesh_reference_or_action_rejected(self):
        for field,value in [('mesh_sha256','old'),('reference_slot','arm'),('reference_slot','missing')]:
            body=copy.deepcopy(self.body);body['contact_scope'][field]=value
            with self.subTest(field=field),self.assertRaises(RuntimeError):validate(self.manager,'job',body)
        body=copy.deepcopy(self.body);body['action']='local_repair'
        with self.assertRaises(RuntimeError):validate(self.manager,'job',body)
        body=copy.deepcopy(self.body);body.pop('contact_scope')
        with self.assertRaises(RuntimeError):validate(self.manager,'job',body)

    def test_stale_revision_does_not_replace_scope(self):
        draft.save(self.manager,'job',self.body)
        body=copy.deepcopy(self.body);body['contact_scope']['regions']=dict(fixed=[],sliding=[0],free=[1])
        with self.assertRaisesRegex(RuntimeError,'revision_changed'):draft.save(self.manager,'job',body)
        self.assertEqual(draft.inspect(self.manager,'job')['history'][0]['contact_scope']['regions']['fixed'],[0])

    def test_transition_save_restore_and_overlap_rejection(self):
        body=copy.deepcopy(self.body)
        body['contact_scope']['regions']['transition']=[1]
        state=draft.save(self.manager,'job',body)
        stored=draft.inspect(self.manager,'job')
        self.assertEqual(stored['history'][0]['contact_scope']['regions']['transition'],[1])
        self.assertEqual(stored['history'][0]['contact_scope']['unclassified_triangles'],0)
        self.assertEqual(stored['draft_sha256s'],state['draft_sha256s'])
        body['contact_scope']['regions']['transition']=[0]
        with self.assertRaisesRegex(RuntimeError,'regions_invalid'):validate(self.manager,'job',body)

    def test_preflight_bound_to_saved_revision_and_withdrawal(self):
        from autospine_workbench.automation.motion_contact_preflight import read
        state=draft.save(self.manager,'job',self.body)
        rest=[[0,0],[2,0],[2,2],[0,2]]; moved=[[3,0],[5,0],[5,2],[3,2]]
        pose=dict(attachments={'arm':'arm','body':'body'},setup_vertices={'arm':rest,'body':rest},
                  vertices={'arm':rest,'body':moved},triangles={'arm':[0,1,2,0,2,3],'body':[0,1,2,0,2,3]})
        with patch('autospine_workbench.targets.character43.active_mesh_pose.sample_active',return_value=pose):
            raw,_=read(self.manager,'job',['contact-scope','1.json'],{'artifact_sha256':'a'*64},self.files)
            report=json.loads(raw)
            self.assertEqual(report['draft_sha256'],state['draft_sha256s'][0])
            self.assertEqual(len(report['conflicts']),2)
            pose['attachments']['arm']='other'
            with self.assertRaisesRegex(RuntimeError,'active_attachment_unsupported'):
                read(self.manager,'job',['contact-scope','1.json'],{'artifact_sha256':'a'*64},self.files)
        body=copy.deepcopy(self.body);body.pop('contact_scope');body.update(action='withdraw',expected_revision=1)
        draft.save(self.manager,'job',body)
        with self.assertRaisesRegex(RuntimeError,'plan_changed'):
            read(self.manager,'job',['contact-scope','1.json'],{'artifact_sha256':'a'*64},self.files)
