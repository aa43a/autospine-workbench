from copy import deepcopy
import unittest
from test_m4_motion_cohort import module

report=module('m4_view_comparison_report')


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.plan=dict(motions=[dict(id='walk',sha256='raw',view='front')],
                       characters=[dict(id='alice',sha256='rig')])
        self.state=dict(plan_sha256=report.digest(self.plan),sources={},cells={})

    def test_missing_and_unmeasured_do_not_become_success(self):
        other=deepcopy(self.plan);other['motions']=[];other['baseline_plan_sha256']=report.digest(self.plan)
        state=dict(plan_sha256=report.digest(other),sources={},cells={})
        result=report.compare(self.plan,[('front',self.plan,self.state),('side',other,state)])
        cells=result['cells']['walk/alice']
        self.assertEqual(cells[0]['result']['geometry'],None)
        self.assertEqual(cells[1]['status'],'not_planned')
        self.assertEqual(result['counts']['front']['captured'],0)

    def test_different_source_and_character_cannot_be_compared(self):
        for field in ('motions','characters'):
            other=deepcopy(self.plan);other[field][0]['sha256']='changed'
            other['baseline_plan_sha256']=report.digest(self.plan)
            with self.assertRaisesRegex(ValueError,'mismatch'):
                report.compare(self.plan,[('variant',other,self.state)])

    def test_wrong_target_angle_rejected(self):
        self.plan['motions'][0]['projection']=dict(profile='constant-yaw-source-motion-v1',yaw_degrees=30)
        self.state['plan_sha256']=report.digest(self.plan)
        self.state['cells']['walk/alice']=dict(job_id='job',status='succeeded',result={})
        with self.assertRaisesRegex(ValueError,'projection_mismatch'):
            report.compare(self.plan,[('oblique',self.plan,self.state)])

    def test_report_escapes_labels(self):
        result=report.compare(self.plan,[('<front>',self.plan,self.state)])
        html=report.render(result)
        self.assertIn('&lt;front&gt;',html)
        self.assertNotIn('<th><front>',html)


if __name__=='__main__':unittest.main()
