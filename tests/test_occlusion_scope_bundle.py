from copy import deepcopy
from hashlib import sha256
import json
import unittest
from unittest.mock import patch
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from test_region_order_bundle import fixture
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.occlusion_scope_bundle import build
from autospine_workbench.targets.character43.numeric_reference import read
from autospine_workbench.targets.character43.affine_pose import sample


class ScopeBundleTests(unittest.TestCase):
    def test_worker_dispatches_scope_builder_and_keeps_candidate_unaccepted(self):
        from autospine_workbench.automation.motion_repair_worker import execute
        from autospine_workbench.targets.character43.occlusion_scope_bundle import PROFILE
        plan=dict(action='contact_scope',artifact_sha256='a'*64,animation='test')
        request=dict(repair_execution=dict(profile=PROFILE,draft=plan,draft_sha256=canonical_sha256(plan),
                     parent_artifact_sha256='a'*64,parent_job_id='parent'))
        files={'character-manifest.json':b'{"files":{}}'}
        def depth(output,*args):
            output['motion-depth.json']=b'{"selected":false}'
            return {}
        worker='autospine_workbench.automation.motion_repair_worker.'
        with TemporaryDirectory() as tmp,ExitStack() as stack:
            store=stack.enter_context(patch(worker+'AnimatedStore')).return_value
            store.publish.return_value='b'*64
            builder=stack.enter_context(patch('autospine_workbench.targets.character43.occlusion_scope_bundle.build',
                return_value=(files,dict(issues=[dict(stage='repair',reason_code='motion_occlusion_representation_not_repaired')],
                                        contact_status='not_evaluated'),dict(passed=True))))
            stack.enter_context(patch(worker+'capture',return_value={}))
            stack.enter_context(patch(worker+'progress'))
            stack.enter_context(patch('autospine_workbench.automation.motion_repair_lineage.carry',return_value={}))
            stack.enter_context(patch('autospine_workbench.automation.motion_repair_depth.recheck',side_effect=depth))
            execute(Path(tmp),'state','workspace',request)
            result=json.loads((Path(tmp)/'worker-result.json').read_bytes())
        builder.assert_called_once()
        self.assertEqual(result['repair_profile'],PROFILE)
        self.assertEqual(result['character_animation_status'],'needs_changes')
        self.assertFalse(result['production_authorized'])

    def fixture(self):
        files,plan=fixture();doc=json.loads(files['skeleton.json']);meshes=doc['skins'][0]['attachments']
        plan.pop('region_order');plan['contact_scope']=dict(reference_slot='b',
            mesh_sha256=canonical_sha256(meshes['a']['a']),reference_mesh_sha256=canonical_sha256(meshes['b']['b']),
            regions={'occlusion':[0],'free':[2]})
        return files,plan

    @patch('autospine_workbench.targets.character43.final_motion_contact.recheck',return_value={'status':'not_evaluated'})
    def test_complete_bundle_preserves_motion_images_and_old_failures(self,contact):
        files,plan=self.fixture();before=deepcopy(files)
        output,evidence,geometry=build(files,plan)
        doc=json.loads(output['skeleton.json']);report=json.loads(output['motion-repair.json'])['representation']
        self.assertEqual(report['candidate_skeleton_sha256'],canonical_sha256(doc))
        self.assertEqual(read(output)['skeleton_sha256'],sha256(output['skeleton.json']).hexdigest())
        for frame in read(output)['animations']['test']:
            actual=sample(doc,'test',frame['time'])[0]
            for slot,points in frame['vertices'].items():self.assertEqual(points,actual[slot])
        for key in files:
            if key.endswith('.png') or key=='skeleton.atlas':self.assertEqual(files[key],output[key])
        self.assertEqual(files,before)
        self.assertEqual(evidence['status'],'needs_changes')
        self.assertEqual(evidence['runtime_status'],'not_evaluated')
        self.assertIn({'stage':'geometry','reason_code':'old_slot_failure'},evidence['issues'])
        self.assertNotIn('motion-depth.json',output)
        for key,digest in json.loads(output['character-manifest.json'])['files'].items():
            self.assertEqual(sha256(output[key]).hexdigest(),digest)

    def test_old_reference_digest_is_not_reused(self):
        files,plan=self.fixture();files['skeleton.json']+=b' '
        with self.assertRaisesRegex(ValueError,'source_identity'):build(files,plan)


if __name__=='__main__':unittest.main()
