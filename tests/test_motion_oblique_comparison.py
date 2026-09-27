from types import SimpleNamespace
import unittest
from unittest.mock import patch
from autospine_workbench.automation.motion_oblique_comparison import compare,validate_selection


class ObliqueComparisonTests(unittest.TestCase):
    def run_angles(self,passing,torso_rejected=()):
        def compiled(base,vectors,roots,reference,yaw,**kwargs):
            return {},dict(motion_sha256=str(yaw),projection=dict(passed=yaw in passing,
                           records=[dict(role='arm',passed=yaw in passing)]))
        def torso(frames,times,reference):
            import math
            yaw=round(math.degrees(math.atan2(frames[0][0][2],frames[0][0][0])))
            return dict(records=[dict(time=0,reasons=['torso_back_view_requires_artwork']
                                      if yaw in torso_rejected else [])],limits={})
        with patch('autospine_workbench.automation.motion_oblique_comparison.extract',return_value=({},[],1)), \
             patch('autospine_workbench.automation.motion_oblique_comparison.anchors',return_value=([[(1,0,0)]]*2,[0,1000000])), \
             patch('autospine_workbench.automation.motion_oblique_comparison.reference_shapes',side_effect=torso), \
             patch('autospine_workbench.automation.motion_oblique_comparison.compile_candidate',side_effect=compiled):
            return compare(SimpleNamespace(source_kind='bvh',motion={}))

    def test_preserve_zero_or_choose_smallest_qualified_angle(self):
        self.assertEqual(self.run_angles({0,15})['recommended_yaw_degrees'],0)
        self.assertEqual(self.run_angles({-60,-30,45})['recommended_yaw_degrees'],-30)
        self.assertIsNone(self.run_angles(set())['recommended_yaw_degrees'])

    def test_limb_improvement_cannot_override_back_facing_torso(self):
        report=self.run_angles({-75,-30},(-75,))
        self.assertEqual(report['recommended_yaw_degrees'],-30)
        rejected=next(r for r in report['records'] if r['yaw_degrees']==-75)
        self.assertTrue(rejected['limb_projection_passed'])
        self.assertFalse(rejected['passed'])
        self.assertEqual(rejected['torso_failures'][0]['reasons'],['torso_back_view_requires_artwork'])
        self.assertIsNone(self.run_angles({-75},(-75,))['recommended_yaw_degrees'])

    def test_submission_revalidates_digest_and_angle(self):
        report=dict(comparison_sha256='current',recommended_yaw_degrees=-30)
        with patch('autospine_workbench.automation.motion_oblique_comparison.inspect',return_value=report):
            accepted=validate_selection(None,'source',{'comparison_sha256':'current'},{'yaw_degrees':-30})
            self.assertEqual(accepted['source_job_id'],'source')
            for digest,angle in [('old',-30),('current',30)]:
                with self.assertRaisesRegex(ValueError,'changed'):
                    validate_selection(None,'source',{'comparison_sha256':digest},{'yaw_degrees':angle})
            report['recommended_yaw_degrees']=None
            with self.assertRaisesRegex(ValueError,'changed'):
                validate_selection(None,'source',{'comparison_sha256':'current'},{'yaw_degrees':0})

    def test_actual_torso_plane_rejects_back_view_even_when_limbs_pass(self):
        from test_torso_projection import observations
        def compiled(*args,**kwargs):
            return {},dict(motion_sha256='motion',projection=dict(passed=True,records=[]))
        with patch('autospine_workbench.automation.motion_oblique_comparison.extract',return_value=({},[],1)), \
             patch('autospine_workbench.automation.motion_oblique_comparison.anchors',
                   return_value=([observations(0),observations(80)],[0,1000000])), \
             patch('autospine_workbench.automation.motion_oblique_comparison.compile_candidate',side_effect=compiled):
            report=compare(SimpleNamespace(source_kind='bvh',motion={}))
        row=next(r for r in report['records'] if r['yaw_degrees']==30)
        self.assertFalse(row['passed'])
        self.assertTrue(row['limb_projection_passed'])
        self.assertIn('torso_back_view_requires_artwork',row['torso_failures'][-1]['reasons'])
        self.assertEqual(row['torso_failures'][-1]['time'],1)


if __name__=='__main__':unittest.main()
