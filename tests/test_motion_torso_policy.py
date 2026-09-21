import json
import unittest
from unittest.mock import patch
from test_motion_target_intake import inputs
from autospine_workbench.automation.motion_torso_policy import select,PROFILE
from autospine_workbench.automation.motion_target_worker import build_candidate
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.motion_readiness import build as readiness
from test_motion_readiness import fixture


class TorsoPolicyTests(unittest.TestCase):
    def test_legacy_default_and_explicit_strategy(self):
        overlap='external-arm-torso-depth-overlap-v2'
        self.assertIsNone(select({},overlap))
        self.assertEqual(select(dict(torso_projection_profile=PROFILE),overlap),PROFILE)
        self.assertEqual(select(dict(torso_projection_profile=PROFILE),
            'external-arm-torso-depth-sparse-v1-experiment'),PROFILE)
        for value in ('wrong',None,True):
            with self.assertRaisesRegex(Exception,'profile_unsupported'):
                select(dict(torso_projection_profile=value),overlap)
        with self.assertRaisesRegex(Exception,'requires_overlap_depth'):
            select(dict(torso_projection_profile=PROFILE),'external-regional-depth-order-v1')

    def test_failed_surface_check_cannot_inherit_contact_pass(self):
        files,motion,bvh,mapping=inputs();doc=json.loads(files['skeleton.json'])
        doc['slots']=[dict(name='point',attachment='point',bone='root')]
        files['skeleton.json']=canonical_bytes(doc)
        receipt=dict(applied=True,contact_preservation=dict(status='foot_surface_changed'))
        def apply(document,*args):return document,receipt,'motion_torso_contact_needs_review'
        with patch('autospine_workbench.targets.character43.torso_projection_profile.apply',side_effect=apply), \
                patch('autospine_workbench.targets.character43.motion_depth_overlap.inspect',side_effect=lambda d,f,a,depth:(depth,None)), \
                patch('autospine_workbench.targets.character43.motion_depth_order.build',return_value=(None,dict(frames=[],failures=[]))):
            result,evidence,_=build_candidate(files,motion,bvh,mapping,character_digest='a'*64,motion_digest='b'*64,
                depth_review_profile='external-arm-torso-depth-overlap-v2',torso_projection={})
        self.assertEqual(evidence['contact_status'],'needs_changes')
        self.assertIn('motion-torso-projection.json',result)
        self.assertTrue(any(r['reason_code']=='motion_torso_contact_needs_review' for r in evidence['issues']))

    def test_torso_evidence_is_bound_to_actual_skeleton(self):
        files,runtime=fixture();base=readiness(files,'a'*64,runtime)
        files['motion-torso-projection.json']=canonical_bytes(dict(applied=False,skeleton_sha256=base['skeleton_sha256']))
        result=readiness(files,'a'*64,runtime)
        self.assertEqual(next(r for r in result['stages'] if r['stage']=='躯干投影')['status'],'needs_changes')
        files['motion-torso-projection.json']=canonical_bytes(dict(applied=True,skeleton_sha256='stale'))
        with self.assertRaisesRegex(ValueError,'torso_identity_mismatch'):readiness(files,'a'*64,runtime)
