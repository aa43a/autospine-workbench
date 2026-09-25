"""A preserved draw order must not hide a known occlusion failure in job status."""
import json
import unittest
from unittest.mock import patch

from autospine_workbench.automation.motion_target_worker import build_candidate
from test_motion_target_intake import inputs


class DepthBuildStatusTests(unittest.TestCase):
    def build(self, failures, ambiguous=0):
        files,motion,bvh,mapping=inputs()
        document=json.loads(files['skeleton.json'])
        document['slots']=[dict(name='point',attachment='point',bone='root')]
        files['skeleton.json']=json.dumps(document).encode()
        depth=dict(status='depth_review',pairs=[],target_overlap=dict(
            ambiguous_visible_pair_samples=ambiguous,unmeasured_pair_samples=0))
        order=dict(status='blocked' if failures else 'no_visible_order_change',failures=failures,frames=[])
        with patch('autospine_workbench.targets.character43.motion_depth.build',return_value=depth), \
             patch('autospine_workbench.targets.character43.motion_depth_overlap.inspect',return_value=(depth,None)), \
             patch('autospine_workbench.targets.character43.motion_depth_order.build',return_value=(None,order)):
            return build_candidate(files,motion,bvh,mapping,character_digest='a'*64,motion_digest='b'*64,
                depth_review_profile='external-arm-torso-depth-overlap-v2')

    def test_failed_order_surfaces_without_changing_animation(self):
        failures=[dict(time=.5,reason_code='visible_unmapped_order_conflict')]
        files,evidence,_=self.build(failures)
        before,_,_=self.build([])
        self.assertEqual(files['skeleton.json'],before['skeleton.json'])
        self.assertEqual(evidence['status'],'needs_changes')
        self.assertIn(dict(stage='depth',reason_code='motion_visible_depth_needs_changes'),evidence['issues'])
        self.assertEqual(json.loads(files['motion-depth.json'])['order']['failures'],failures)

    def test_ambiguous_visibility_is_not_hidden_and_clean_order_has_no_depth_issue(self):
        _,ambiguous,_=self.build([],ambiguous=1)
        self.assertTrue(any(i['stage']=='depth' for i in ambiguous['issues']))
        _,clean,_=self.build([])
        self.assertFalse(any(i['stage']=='depth' for i in clean['issues']))


if __name__=='__main__':unittest.main()
