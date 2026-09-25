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
    def test_visual_editor_reads_texture_from_verified_candidate_not_capture_folder(self):
        from autospine_workbench.automation.motion_target_jobs import review_file
        self.files['images/arm.png']=b'exact candidate texture'
        with patch('autospine_workbench.automation.motion_target_jobs.runtime_reader') as runtime:
            raw,mime=review_file(self.manager,'job',['images','arm.png'])
        self.assertEqual(raw,b'exact candidate texture');self.assertEqual(mime,'image/png')
        runtime.return_value.assert_not_called()
        for parts in (['images','missing.png'],['images','..','skeleton.json']):
            with self.assertRaises(RuntimeError):review_file(self.manager,'job',parts)

    def test_visual_scope_saved_without_fabricating_geometry_failure(self):
        doc=json.loads(self.files['skeleton.json'])
        doc['animations']={'reach':{'bones':{'chest':{'rotate':[dict(time=1,value=0)]}}}}
        self.files['skeleton.json']=json.dumps(doc).encode()
        before=copy.deepcopy(self.report)
        body=copy.deepcopy(self.body);body.update(visual_inspection=True,triangle=-1,time=.25)
        state=draft.save(self.manager,'job',body)
        self.assertEqual(state['history'][0]['event'],dict(triangle=-1,time=.25,reason='user_visual_inspection',detected_failure=False))
        self.assertEqual(self.report,before)
        self.assertEqual(state['evidence_sha256'],body['evidence_sha256'])
        withdrawn=copy.deepcopy(body);withdrawn.pop('contact_scope');withdrawn.update(action='withdraw',expected_revision=1)
        result=draft.save(self.manager,'job',withdrawn)
        self.assertEqual(result['history'][0],state['history'][0])
        self.assertEqual(result['history'][1]['action'],'withdraw')

    def test_visual_scope_invalid_times_and_detected_event_collision_rejected(self):
        doc=json.loads(self.files['skeleton.json']);doc['animations']={'reach':{}}
        self.files['skeleton.json']=json.dumps(doc).encode()
        for changes in [dict(time=float('nan')),dict(time=1),dict(triangle=0),dict(visual_inspection=False),dict(animation='missing')]:
            body=copy.deepcopy(self.body);body.update(visual_inspection=True,triangle=-1,time=0);body.update(changes)
            with self.subTest(changes=changes),self.assertRaises(RuntimeError):draft.save(self.manager,'job',body)

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

    def test_coverage_intent_retained_without_reinterpreting_old_sliding(self):
        body=copy.deepcopy(self.body)
        body['contact_scope']['regions']=dict(fixed=[],sliding=[0],free=[])
        first=draft.save(self.manager,'job',body)['history'][0]
        self.assertEqual(first['contact_scope']['regions']['occlusion'],[])
        body['expected_revision']=1
        body['contact_scope']['regions']=dict(fixed=[],sliding=[],free=[],occlusion=[0])
        state=draft.save(self.manager,'job',body)
        self.assertEqual(state['history'][0],first)
        self.assertEqual(state['history'][1]['contact_scope']['regions']['sliding'],[])
        self.assertEqual(state['history'][1]['contact_scope']['regions']['occlusion'],[0])
        self.assertFalse(state['repair_executed'])
        self.assertEqual(draft.inspect(self.manager,'job')['history'],state['history'])

    def test_coverage_scope_rejects_overlaps_and_unrecognized_roles(self):
        for regions in [dict(fixed=[0],sliding=[],free=[],occlusion=[0]),
                        dict(fixed=[],sliding=[],free=[],occlusion=[9]),
                        dict(fixed=[],sliding=[],free=[],occlusion=[0],invented=[])]:
            body=copy.deepcopy(self.body);body['contact_scope']['regions']=regions
            with self.subTest(regions=regions),self.assertRaises(RuntimeError):
                validate(self.manager,'job',body)

    def test_preflight_reports_cover_reference_behind_at_event(self):
        from autospine_workbench.automation.motion_contact_preflight import read
        doc=json.loads(self.files['skeleton.json'])
        doc['animations']={'reach':{'drawOrder':[dict(time=.25,offsets=[dict(slot='arm',offset=1)])]}}
        self.files['skeleton.json']=json.dumps(doc).encode()
        body=copy.deepcopy(self.body)
        body['contact_scope']['regions']=dict(fixed=[],sliding=[],free=[],occlusion=[0])
        saved=draft.save(self.manager,'job',body)
        rest=[[0,0],[2,0],[2,2],[0,2]]
        pose=dict(attachments={'arm':'arm','body':'body'},setup_vertices={'arm':rest,'body':rest},
                  vertices={'arm':rest,'body':rest},triangles={'arm':[0,1,2,0,2,3],'body':[0,1,2,0,2,3]})
        with patch('autospine_workbench.targets.character43.active_mesh_pose.sample_active',return_value=pose):
            raw,_=read(self.manager,'job',['contact-scope','1.json'],{'artifact_sha256':'a'*64},self.files)
        report=json.loads(raw)
        self.assertIn('occlusion_reference_behind',report['reasons'])
        self.assertEqual(report['status'],'requires_changes')
        self.assertEqual(report['occlusion_review']['draw_order']['order'],['body','arm'])
        self.assertEqual(report['occlusion_review']['order_timeline']['status'],'measured')
        self.assertFalse(report['occlusion_review']['order_timeline']['endpoint']['reference_can_cover_in_order'])
        self.assertEqual(report['occlusion_review']['render_partition']['status'],'unavailable')
        self.assertEqual(report['fixed_targets'],[])
        self.assertEqual(saved['history'],draft.inspect(self.manager,'job')['history'])
