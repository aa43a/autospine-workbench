import unittest
from autospine_workbench.automation.character_motion_metrics import motion_rows


class MotionMetricsTests(unittest.TestCase):
    def test_names_and_green_summary_without_samples_do_not_pass(self):
        rows=motion_rows({'animations':['idle']},{'passed':True},['idle','walk'])
        self.assertEqual([r['status'] for r in rows],['unmeasured','missing'])

    def test_actual_samples_and_failed_capture(self):
        report={'passed':True,'results':[dict(animation='walk',index=i,time=i/30) for i in range(4)]}
        row=motion_rows({'animations':['walk']},report,['walk'])[0]
        self.assertEqual(row['status'],'passed');self.assertEqual(row['sampled_frames'],4)
        self.assertEqual(row['duration_seconds'],.1)
        report['passed']=False
        self.assertEqual(motion_rows({'animations':['walk']},report,['walk'])[0]['status'],'failed')

    def test_missing_duplicate_or_nonfinite_samples_cannot_pass(self):
        for indices,times in [([0,2],[0,.1]),([0,0],[0,.1]),([0,1],[0,float('nan')]),([0,1],[0,0])]:
            report={'passed':True,'results':[dict(animation='walk',index=i,time=t) for i,t in zip(indices,times)]}
            self.assertEqual(motion_rows({'animations':['walk']},report,['walk'])[0]['status'],'unmeasured')
