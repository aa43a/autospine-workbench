import json
import unittest
from unittest.mock import patch
from autospine_workbench.automation.motion_repair_local_depth import run, PROFILE

MODULE='autospine_workbench.automation.motion_repair_local_depth.'


class RepairLocalDepthTests(unittest.TestCase):
    def test_unrequested_check_does_not_load_or_publish_evidence(self):
        with patch(MODULE+'VerifiedMotionBundleReader') as reader:
            self.assertIsNone(run({},'artifact',{},'root','folder',lambda:None))
        reader.assert_not_called()

    def test_selected_schedule_and_failure_are_published_with_exact_identity(self):
        request=dict(local_depth_profile=PROFILE,job_id='job',motion_identity=dict(clip_sha256='clip',bundle_sha256='bundle'),
            repair_execution=dict(draft=dict(animation='test')))
        files={'skeleton.json':json.dumps(dict(animations={'test':{}})).encode(),
            'motion-depth.json':json.dumps(dict(pairs=[dict(samples=[dict(tick=0),dict(tick=1000000)])])).encode()}
        with (patch(MODULE+'VerifiedMotionBundleReader'),patch(MODULE+'publish',return_value='evidence') as publish,
                patch(MODULE+'analyze',return_value={'report':'fresh'}) as analyze):
            self.assertEqual(run(files,'artifact',request,'root','folder',lambda:None),'evidence')
            self.assertEqual(analyze.call_args.kwargs['sample_times'],[0,.5,1])
            self.assertTrue(analyze.call_args.kwargs['triangle_traces'])
            self.assertEqual(publish.call_args.args[2:],(request,'artifact',{'report':'fresh'}))
            analyze.side_effect=ValueError('unsupported_surface')
            run(files,'artifact',request,'root','folder',lambda:None)
            report=publish.call_args.args[-1]
            self.assertEqual(report['failure'],'unsupported_surface')
            self.assertEqual(report['artifact_sha256'],'artifact')
            self.assertFalse(report['selected'])
