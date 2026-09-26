from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from autospine_workbench.automation.storage_io import canonical_bytes, read_document
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43 import final_leg_repair_policy as policy
from autospine_workbench.targets.character43.selected_attachment_repair import build
from autospine_workbench.targets.character43.fixed_area_feasibility import FixedAreaInfeasible
from autospine_workbench.targets.character43.affine_pose import sample


def fixture(fixed=False):
    from test_character_affine_repair import fixture as base
    doc=base();doc['bones'][0]['name']='thigh_l';doc['bones'][1].update(name='calf_l',parent='thigh_l')
    tracks=doc['animations']['walk']['bones'];tracks['thigh_l']=tracks.pop('a')
    doc['skins'][0]['name']='default'
    mesh=doc['skins'][0]['attachments']['mesh']['mesh'];mesh.update(type='mesh',uvs=[0,0,1,0,0,1])
    if fixed:mesh['vertices']=[1,0,0,0,1,1,0,1,0,1,1,1,-10,1,1]
    doc['slots']=[dict(name='mesh',bone='thigh_l',attachment='mesh'),dict(name='other',bone='thigh_l',attachment='other')]
    doc['skins'][0]['attachments']['other']={'other':deepcopy(mesh)}
    doc['animations']['walk']['attachments']={'default':{'other':{'other':{'deform':[dict(time=0,vertices=[0]*10)]}}}}
    raw=canonical_bytes(doc);digest=sha256(raw).hexdigest()
    setup=sample(dict(doc,animations={'walk':{'bones':{}}}),'walk',0)[0]
    return {'skeleton.json':raw,'rig-setup-reference.json':canonical_bytes(dict(skeleton_sha256=digest,vertices=setup)),
        'numeric-reference.json':canonical_bytes(dict(skeleton_sha256=digest,animations={'walk':[dict(time=t) for t in (0,.123,1)]})),
        'motion-review.json':canonical_bytes(dict(reference_length_px=10,issues=[],selected=True,production_authorized=True,
            source_pose_fit=dict(profile='source-absolute-limb-projection-v1'))),
        'motion-contact.json':b'{}','motion-ir.json':b'{}','character-manifest.json':b'{"selected":true}',
        'deformation.json':canonical_bytes(dict(passed=False,records=[dict(slot='mesh',animation='walk',passed=False)])),
        'motion-depth.json':b'old','images/mesh.png':b'exact'}


class PolicyTests(unittest.TestCase):
    def test_actual_influences_and_failed_final_pose_select_without_character_name(self):
        files=fixture();scope=policy.select(files,'mesh','walk')
        self.assertEqual(scope['bones'],['calf_l','thigh_l']);self.assertEqual(scope['profile'],policy.PROFILE)
        self.assertIsNone(policy.select(files,'mesh','other_animation'))
        for changed in ({'motion-review.json':b'{}'},
                        {'deformation.json':b'{"records":[{"slot":"mesh","animation":"walk","passed":true}]}'}):
            self.assertIsNone(policy.select(dict(files,**changed),'mesh','walk'))
        for name in ('calf_r','forearm_l','cloth_l'):
            doc=json.loads(files['skeleton.json']);doc['bones'][1]['name']=name
            self.assertIsNone(policy.select(dict(files,**{'skeleton.json':canonical_bytes(doc)}),'mesh','walk'))

    def test_old_plan_unchanged_and_stale_scope_rejected(self):
        files=fixture();scope=policy.select(files,'mesh','walk')
        self.assertEqual(policy.execution_profile({},'legacy'),'legacy')
        with self.assertRaisesRegex(ValueError,'profile_invalid'):
            policy.execution_profile(dict(action='partition',local_solver=scope),'legacy')
        with self.assertRaisesRegex(ValueError,'scope_changed'):
            policy.verify(files,dict(slot='mesh',animation='walk',local_solver=dict(scope,bones=['guessed'])))
        files['rig-setup-reference.json']=b'{"skeleton_sha256":"changed"}'
        with self.assertRaisesRegex(ValueError,'setup_changed'):policy.select(files,'mesh','walk')

    def test_dual_solver_preserves_other_tracks_and_compares_identical_times(self):
        from autospine_workbench.targets.character43.numeric_reference import read
        files=fixture();files['motion-torso-projection.json']=b'{"test":"unchanged torso driver"}'
        original=deepcopy(files);plan=dict(slot='mesh',animation='walk',local_solver=policy.select(files,'mesh','walk'))
        with patch('autospine_workbench.targets.character43.final_motion_contact.recheck',return_value={'status':'unavailable_no_labels'}):
            output,evidence,geometry=build(files,plan)
        self.assertEqual(files,original)
        before=json.loads(files['skeleton.json']);after=json.loads(output['skeleton.json'])
        self.assertEqual(before['bones'],after['bones']);self.assertEqual(before['skins'],after['skins'])
        self.assertEqual(before['animations']['walk']['bones'],after['animations']['walk']['bones'])
        self.assertEqual(before['animations']['walk']['attachments']['default']['other'],after['animations']['walk']['attachments']['default']['other'])
        summary=json.loads(output['motion-repair.json'])
        self.assertEqual(summary['profile'],policy.PROFILE)
        self.assertTrue(next(r for r in geometry['records'] if r['slot']=='mesh')['passed'])
        self.assertEqual([r['sample_count'] for r in summary['parent_geometry']['records']],
                         [r['sample_count'] for r in geometry['records']])
        self.assertIn(.123,[f['time'] for f in read(output)['animations']['walk']])
        self.assertFalse(evidence['selected']);self.assertFalse(evidence['production_authorized'])
        self.assertFalse(json.loads(output['character-manifest.json'])['selected'])
        self.assertNotIn('motion-depth.json',output)
        self.assertEqual(output['motion-torso-projection.json'],files['motion-torso-projection.json'])
        for t in (0,.5,1):self.assertEqual(sample(before,'walk',t)[0]['mesh'][0],sample(after,'walk',t)[0]['mesh'][0])

    def test_all_fixed_failure_exits_before_local_iterations(self):
        files=fixture(True);plan=dict(slot='mesh',animation='walk',local_solver=policy.select(files,'mesh','walk'))
        with patch('autospine_workbench.targets.character43.affine_area_repair.project') as project:
            with self.assertRaises(FixedAreaInfeasible) as error:build(files,plan)
        project.assert_not_called()
        self.assertTrue(error.exception.report['failures'])

    def test_prior_dense_qa_grid_is_preserved_without_recursive_subdivision(self):
        from autospine_workbench.targets.character43.numeric_reference import read
        files=fixture();reference=json.loads(files['numeric-reference.json'])
        times=[i/3000 for i in range(3001)]
        reference['animations']['walk']=[dict(time=t) for t in times]
        files['numeric-reference.json']=canonical_bytes(reference)
        plan=dict(slot='mesh',animation='walk',local_solver=policy.select(files,'mesh','walk'))
        with patch('autospine_workbench.targets.character43.final_motion_contact.recheck',return_value={'status':'unavailable_no_labels'}):
            output,_,_=build(files,plan)
        actual={f['time'] for f in read(output)['animations']['walk']}
        self.assertLessEqual(len(actual),4097);self.assertTrue(set(times)<=actual)


class FailedReportTests(unittest.TestCase):
    def test_worker_stops_before_capture_and_read_binds_exact_request(self):
        from autospine_workbench.automation.motion_repair_worker import execute
        from autospine_workbench.automation.motion_repair_feasibility import read, REASON
        from autospine_workbench.automation.motion_target_jobs import review_file
        files=fixture(True);plan=dict(action='local_repair',slot='mesh',animation='walk',artifact_sha256='a'*64,
                                     local_solver=policy.select(files,'mesh','walk'))
        request=dict(repair_execution=dict(profile=policy.PROFILE,draft=plan,draft_sha256=canonical_sha256(plan),
            parent_artifact_sha256='a'*64,parent_job_id='parent'))
        worker='autospine_workbench.automation.motion_repair_worker.'
        with TemporaryDirectory() as tmp, patch(worker+'AnimatedStore') as store, patch(worker+'capture') as capture, patch(worker+'progress'):
            folder=Path(tmp);folder.joinpath('request.json').write_bytes(canonical_bytes(request))
            store.return_value.read.return_value=files
            with self.assertRaisesRegex(ValueError,REASON):execute(folder,'state','workspace',request)
            capture.assert_not_called();store.return_value.publish.assert_not_called()
            manager=SimpleNamespace(folder=lambda _:folder,get=lambda _:dict(status='failed',reason_code=REASON))
            raw,mime=review_file(manager,'job',['repair-blocker.json']);report=json.loads(raw)
            self.assertEqual(report['failed_triangles'],1);self.assertFalse(report['candidate_generated'])
            self.assertEqual(len(report['examples']),1);self.assertGreater(report['failure_observations'],1)
            self.assertEqual(mime,'application/json')
            request['repair_execution']['parent_job_id']='changed'
            folder.joinpath('request.json').write_bytes(canonical_bytes(request))
            with self.assertRaisesRegex(RuntimeError,'changed'):read(manager,'job')

    def test_original_successful_feasibility_route_is_preserved(self):
        from autospine_workbench.automation.motion_target_jobs import review_file
        with patch('autospine_workbench.automation.motion_target_jobs.context',return_value=({'artifact_sha256':'a'*64},{})), \
             patch('autospine_workbench.automation.motion_target_jobs.runtime_reader'), \
             patch('autospine_workbench.targets.character43.repair_feasibility.inspect',return_value={'rows':[]}) as inspect:
            raw,_=review_file(None,'job',['repair-feasibility.json'])
        self.assertEqual(json.loads(raw),{'rows':[]});inspect.assert_called_once()
