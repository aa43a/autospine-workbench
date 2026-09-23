from contextlib import ExitStack
from copy import deepcopy
from hashlib import sha256
import json
from types import SimpleNamespace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from test_motion_depth_overlap import fixture
from test_motion_depth import fixture as depth_fixture
from autospine_workbench.automation.motion_repair_depth import recheck
from autospine_workbench.automation.storage_io import canonical_bytes

MODULE = 'autospine_workbench.automation.motion_repair_depth.'


class RepairDepthTests(unittest.TestCase):
    def test_worker_packages_fresh_evidence_without_marking_depth_passed(self):
        from autospine_workbench.automation.motion_repair_worker import execute
        from autospine_workbench.automation.motion_repair_execution import PROFILE
        from autospine_workbench.resolved_project import canonical_sha256
        plan=dict(action='local_repair',artifact_sha256='a'*64,animation='test')
        request=dict(repair_execution=dict(profile=PROFILE,draft=plan,draft_sha256=canonical_sha256(plan),
            parent_artifact_sha256='a'*64,parent_job_id='parent'))
        files={'character-manifest.json':b'{"files":{}}'}
        def checked(output,*args):
            output['motion-depth.json']=b'{"selected":false}'
            return dict(target_overlap=dict(unmeasured_pair_samples=0))
        worker='autospine_workbench.automation.motion_repair_worker.'
        with TemporaryDirectory() as tmp, ExitStack() as stack:
            store=stack.enter_context(patch(worker+'AnimatedStore')).return_value
            store.publish.return_value='b'*64
            stack.enter_context(patch(worker+'build',return_value=(files,dict(issues=[],contact_status='needs_changes'),dict(passed=False))))
            stack.enter_context(patch(worker+'capture',return_value={}))
            stack.enter_context(patch(worker+'progress'))
            stack.enter_context(patch('autospine_workbench.automation.motion_repair_lineage.carry',return_value={}))
            stack.enter_context(patch(MODULE+'recheck',side_effect=checked))
            execute(Path(tmp),'state','workspace',request)
            result=json.loads((Path(tmp)/'worker-result.json').read_bytes())
        self.assertEqual(result['depth_order_status'],'not_evaluated')
        self.assertEqual(result['repair_depth_overlap']['unmeasured_pair_samples'],0)
        packed=store.publish.call_args.args[0]
        self.assertEqual(json.loads(packed['character-manifest.json'])['files']['motion-depth.json'],
            sha256(packed['motion-depth.json']).hexdigest())

    def inputs(self):
        doc, files = fixture()
        doc['bones'][0]['name'] = 'upperarm_l'
        doc['bones'].append(dict(name='chest', x=0, y=0, rotation=0))
        doc['slots'][0]['bone'] = 'upperarm_l'
        doc['slots'][1]['bone'] = 'chest'
        vertices = doc['skins'][0]['attachments']['b']['b']['vertices']
        doc['skins'][0]['attachments']['b']['b']['vertices'] = [1 if i%5==1 else v for i,v in enumerate(vertices)]
        doc['slots'].append(dict(name='replacement', bone='upperarm_l', attachment='replacement', color='ffffff00'))
        doc['skins'][0]['attachments']['replacement'] = {'replacement': deepcopy(doc['skins'][0]['attachments']['a']['a'])}
        files['images/replacement.png'] = files['images/a.png']
        doc['animations']['test']['slots'] = {
            'a': {'alpha': [dict(time=0, value=1, curve='stepped'),dict(time=1, value=0, curve='stepped')]},
            'replacement': {'alpha': [dict(time=0, value=0, curve='stepped'),dict(time=1, value=1, curve='stepped')]}}
        files['skeleton.json'] = canonical_bytes(doc)
        files['motion-depth.json'] = b'{"selected":true,"stale":true}'
        request = dict(motion_identity=dict(clip_sha256='a'*64,bundle_sha256='b'*64),
            character_sha256='c'*64,repair_execution=dict(draft=dict(animation='test')))
        return files, request

    def test_rebuilds_regions_and_overlap_without_inheriting_parent_acceptance(self):
        files, request = self.inputs()
        bundle = SimpleNamespace(source_kind='bvh',raw_bvh=b'fake',bvh_map=depth_fixture()[1])
        frames = [(t,dict(torso=0,shoulder=.1,elbow=.1,wrist=.1)) for t in (0,1000000)]
        with ExitStack() as stack:
            stack.enter_context(patch(MODULE+'VerifiedMotionBundleReader')).return_value.load.return_value = bundle
            stack.enter_context(patch(MODULE+'verify_source'))
            stack.enter_context(patch(MODULE+'parse_bvh',return_value=None))
            stack.enter_context(patch(MODULE+'bvh_frame_ticks',return_value=[0,1000000]))
            stack.enter_context(patch('autospine_workbench.targets.character43.motion_depth._source',return_value=(frames,1,'d'*64)))
            report = recheck(files,request,'unused')
        self.assertEqual(report['groups']['left'],['a','replacement'])
        self.assertFalse(report['selected'])
        self.assertNotIn('stale',report)
        self.assertEqual(report['skeleton_sha256'],sha256(files['skeleton.json']).hexdigest())
        counts = {p['arm_slot']:[s['overlap']['overlap_pixels'] for s in p['samples']] for p in report['pairs']}
        self.assertEqual(counts,dict(a=[4,0],replacement=[0,4]))
        self.assertEqual(json.loads(files['motion-depth.json']),report)

    def test_source_identity_failure_preserves_files(self):
        files,request = self.inputs();before=deepcopy(files)
        with patch(MODULE+'VerifiedMotionBundleReader'), patch(MODULE+'verify_source',side_effect=ValueError('identity_mismatch')):
            with self.assertRaisesRegex(ValueError,'identity_mismatch'):
                recheck(files,request,'unused')
        self.assertEqual(files,before)
