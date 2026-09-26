import json
from unittest.mock import patch
import unittest

from test_motion_readiness import fixture
from autospine_workbench.targets.character43.depth_failure_navigation import build,locations
from autospine_workbench.targets.character43.motion_readiness import build as readiness


class DepthFailureNavigationTests(unittest.TestCase):
    def report(self,failures):
        files,runtime=fixture();depth=json.loads(files['motion-depth.json'])
        depth['order']=dict(status='blocked',failures=failures)
        files['motion-depth.json']=json.dumps(depth).encode()
        return files,runtime

    def test_midpoint_uses_measured_time_and_retains_order_anchor(self):
        failure=dict(time=1,reason_code='visible_depth_straddle',pair=['arm','body'],
                     overlap=dict(time=1.125,overlap_pixels=7))
        files,runtime=self.report([failure]);before=dict(files);old=readiness(files,'a'*64,runtime)
        result=build(files,'a'*64);group=result['groups'][0]
        self.assertEqual(group['samples'],[dict(time=1.125,order_times=[1])])
        self.assertEqual(group['time_source'],'overlap_sample')
        self.assertFalse(result['order_changed']);self.assertEqual(result['authority'],'none')
        self.assertEqual(readiness(files,'a'*64,runtime),old);self.assertEqual(files,before)

    def test_opposing_interval_samples_both_remain_navigable(self):
        failure=dict(time=1,pair=['a','b'],reason_code='visible_depth_order_changes_within_interval',
                     samples=[dict(overlap=dict(time=1)),dict(overlap=dict(time=1.25))])
        files,_=self.report([failure]);result=build(files,'a'*64)
        self.assertEqual(result['diagnostic_records'],1)
        self.assertEqual(result['navigable_samples'],2)
        self.assertEqual([s['time'] for s in result['groups'][0]['samples']],[1,1.25])

    def test_early_exit_does_not_hide_unmeasured_tail_or_limit_to_100(self):
        files,_=self.report([dict(time=i/30,reason_code='visible_depth_straddle',pair=['a','b'])
                            for i in range(150)])
        depth=json.loads(files['motion-depth.json'])
        depth['pairs']=[dict(arm_slot='a',torso_slot='c',samples=[dict(tick=6_000_000,
            overlap=dict(status='unmeasured',reason_code='depth_overlap_pixel_budget'))])]
        files['motion-depth.json']=json.dumps(depth).encode();result=build(files,'a'*64)
        self.assertEqual(result['original_order_records'],150)
        self.assertEqual(result['diagnostic_records'],151)
        self.assertEqual(len(result['groups'][0]['samples']),150)
        self.assertEqual(result['groups'][1]['samples'],[dict(time=6,order_times=[6])])

    def test_cycles_keep_each_actual_pair_time_without_inventing_unsampled_edges(self):
        failure=dict(time=0,reason_code='visible_unmapped_order_conflict',conflict=dict(edges=[
            dict(back='a',front='b',overlap=dict(time=.1),interval_overlaps=[dict(time=.1),dict(time=.2)]),
            dict(back='b',front='c',overlap=dict(time=.2)),dict(back='c',front='a')]))
        files,_=self.report([failure]);result=build(files,'a'*64)
        self.assertEqual(result['navigable_samples'],3)
        self.assertEqual([g['pair'] for g in result['groups']],[['a','b'],['b','c']])
        self.assertEqual([s['time'] for s in result['groups'][0]['samples']],[.1,.2])

    def test_missing_sample_and_budget_times_are_not_mistaken_for_anchor(self):
        for field,value,kind in [('sample_time',.7,'requested_sample'),
                                 ('raster_budget',dict(time=.7,pair=['a','b']),'unmeasured_sample')]:
            with self.subTest(field=field):
                result=locations(dict(time=.5,pair=['a','b'],**{field:value}))
                self.assertEqual(result,[dict(time=.7,pair=['a','b'],order_time=.5,time_source=kind)])

    def test_invalid_explicit_times_cannot_silently_fall_back(self):
        for value in [None,True,-1,float('nan'),float('inf')]:
            with self.subTest(time=value):
                with self.assertRaisesRegex(ValueError,'time_invalid'):
                    locations(dict(time=0,overlap=dict(time=value)))

    def test_readonly_endpoint_and_identity_guard(self):
        from autospine_workbench.automation.motion_target_jobs import review_file
        files,_=self.report([])
        with patch('autospine_workbench.automation.motion_target_jobs.context',
                   return_value=(dict(artifact_sha256='a'*64),files)):
            raw,mime=review_file(None,'job',['depth-navigation.json'])
        self.assertEqual(json.loads(raw)['artifact_sha256'],'a'*64)
        self.assertEqual(mime,'application/json')
        files['skeleton.json']=b'{"changed":true}'
        with self.assertRaisesRegex(ValueError,'identity'):build(files,'a'*64)


if __name__=='__main__':unittest.main()
