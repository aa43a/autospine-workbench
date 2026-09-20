from types import SimpleNamespace
import unittest
from unittest.mock import patch
from autospine_workbench.automation.motion_oblique_comparison import compare,validate_selection


class ObliqueComparisonTests(unittest.TestCase):
    def run_angles(self,passing):
        def compiled(base,vectors,roots,reference,yaw,**kwargs):
            return {},dict(motion_sha256=str(yaw),projection=dict(passed=yaw in passing,
                           records=[dict(role='arm',passed=yaw in passing)]))
        with patch('autospine_workbench.automation.motion_oblique_comparison.extract',return_value=({},[],1)), \
             patch('autospine_workbench.automation.motion_oblique_comparison.compile_candidate',side_effect=compiled):
            return compare(SimpleNamespace(source_kind='bvh',motion={}))

    def test_preserve_zero_or_choose_smallest_qualified_angle(self):
        self.assertEqual(self.run_angles({0,15})['recommended_yaw_degrees'],0)
        self.assertEqual(self.run_angles({-60,-30,45})['recommended_yaw_degrees'],-30)
        self.assertIsNone(self.run_angles(set())['recommended_yaw_degrees'])

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


if __name__=='__main__':unittest.main()
