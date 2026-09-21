import json
import unittest
from unittest.mock import patch
from test_motion_readiness import fixture
from autospine_workbench.targets.character43.motion_depth_status import build
from autospine_workbench.targets.character43.motion_readiness import build as readiness


class DepthStatusTests(unittest.TestCase):
    def test_regional_midpoint_limits_are_localizable_despite_early_conflicts(self):
        files,_=self.report([dict(time=0,reason_code='visible_depth_straddle',pair=['a','b'])])
        depth=json.loads(files['motion-depth.json'])
        check=dict(time=.5,status='unmeasured',reason_code='depth_overlap_pixel_budget')
        depth['regional']=dict(refinement=dict(rows=[dict(pair=['a','c'],checks=[check])]),
            cloth_constraints=dict(pairs=[dict(arm='a',cloth='c',rows=[dict(checks=[check])])]),
            limb_constraints=dict(pairs=[dict(arm='a',leg='d',rows=[dict(checks=[dict(check,time=.75)])])]))
        files['motion-depth.json']=json.dumps(depth).encode();before=dict(files)
        result=build(files,'a'*64)
        self.assertEqual(result['failure_record_counts'],{'depth_conflict':1,'resource_limit':2})
        limits=result['records_by_category']['resource_limit']
        self.assertEqual([(r['time'],r['pair']) for r in limits],[(.5,['a','c']),(.75,['a','d'])])
        self.assertEqual(files,before)

    def test_unmeasured_regional_time_must_not_be_invented(self):
        files,_=self.report([]);depth=json.loads(files['motion-depth.json'])
        depth['regional']=dict(refinement=dict(rows=[dict(pair=['a','b'],checks=[dict(status='unmeasured')])]))
        files['motion-depth.json']=json.dumps(depth).encode()
        with self.assertRaisesRegex(ValueError,'time'):
            build(files,'a'*64)

    def test_early_order_conflicts_do_not_hide_unmeasured_samples(self):
        files,_=self.report([dict(time=i/30,reason_code='visible_depth_straddle') for i in range(120)])
        depth=json.loads(files['motion-depth.json'])
        depth['pairs']=[dict(arm_slot='arm',torso_slot='body',samples=[dict(tick=4_000_000,
            overlap=dict(status='unmeasured',reason_code='depth_overlap_pixel_budget'))])]
        files['motion-depth.json']=json.dumps(depth).encode()
        before=dict(files); result=build(files,'a'*64)
        self.assertEqual(result['failure_record_counts'],{'depth_conflict':120,'resource_limit':1})
        self.assertEqual(result['records_by_category']['resource_limit'][0]['time'],4)
        self.assertTrue(result['category_records_truncated']['depth_conflict'])
        self.assertFalse(result['category_records_truncated']['resource_limit'])
        self.assertEqual(files,before)

    def test_overlap_failure_already_recorded_by_order_is_not_counted_twice(self):
        failure=dict(time=1,reason_code='depth_overlap_pixel_budget',pair=['arm','body'])
        files,_=self.report([failure]);depth=json.loads(files['motion-depth.json'])
        depth['pairs']=[dict(arm_slot='arm',torso_slot='body',samples=[dict(tick=1_000_000,
            overlap=dict(status='unmeasured',reason_code='depth_overlap_pixel_budget'))])]
        files['motion-depth.json']=json.dumps(depth).encode()
        result=build(files,'a'*64)
        self.assertEqual(result['failure_record_counts'],{'resource_limit':1})

    def report(self,failures):
        files,runtime=fixture(); depth=json.loads(files['motion-depth.json'])
        depth['order']=dict(status='blocked',failures=failures)
        files['motion-depth.json']=json.dumps(depth).encode()
        return files,runtime

    def test_resource_failure_is_incomplete_not_measured_conflict(self):
        files,_=self.report([dict(time=.1,reason_code='depth_overlap_pixel_budget')])
        report=build(files,'a'*64)
        self.assertEqual(report['status'],'evidence_incomplete')
        self.assertEqual(report['failure_record_counts'],{'resource_limit':1})
        self.assertTrue(report['has_incomplete_checks'])

    def test_mixed_failures_keep_both_categories_and_time(self):
        files,_=self.report([dict(time=.1,reason_code='visible_depth_straddle'),
                            dict(time=.2,reason_code='depth_overlap_tile_limit')])
        report=build(files,'a'*64)
        self.assertEqual(report['status'],'needs_changes')
        self.assertEqual(report['records'][1]['time'],.2)
        self.assertTrue(report['has_incomplete_checks'])

    def test_new_read_does_not_change_stage_evidence(self):
        files,runtime=fixture(); before=dict(files); old=readiness(files,'a'*64,runtime)
        report=build(files,'a'*64)
        self.assertEqual(report['status'],'sampled_no_change')
        self.assertEqual(readiness(files,'a'*64,runtime),old)
        self.assertEqual(files,before)
        self.assertFalse(report['production_authorized'])

    def test_endpoint_is_read_only_and_checks_candidate_identity(self):
        from autospine_workbench.automation.motion_target_jobs import review_file
        files,_=fixture()
        with patch('autospine_workbench.automation.motion_target_jobs.context',return_value=(dict(artifact_sha256='a'*64),files)):
            raw,kind=review_file(None,'test',['depth-status.json'])
        self.assertEqual(json.loads(raw)['artifact_sha256'],'a'*64)
        self.assertEqual(kind,'application/json')
        files['skeleton.json']=b'{"changed":true}'
        with self.assertRaisesRegex(ValueError,'identity'): build(files,'a'*64)

    def test_unknown_reason_and_missing_evidence_do_not_pass(self):
        files,_=self.report([dict(time=.1,reason_code='future_check_unsupported')])
        self.assertEqual(build(files,'a'*64)['status'],'evidence_incomplete')
        del files['motion-depth.json']
        self.assertEqual(build(files,'a'*64)['status'],'evidence_incomplete')


if __name__=='__main__': unittest.main()
