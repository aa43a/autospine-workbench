import json
import unittest
from unittest.mock import patch
from test_motion_readiness import fixture
from autospine_workbench.targets.character43.motion_depth_status import build
from autospine_workbench.targets.character43.motion_readiness import build as readiness


class DepthStatusTests(unittest.TestCase):
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
