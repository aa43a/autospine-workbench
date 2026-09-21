from unittest.mock import patch
import unittest
from autospine_workbench.targets.character43.projected_area_adaptive import build


class AdaptiveAreaTests(unittest.TestCase):
    def test_refinement_uses_original_not_accumulated_deformation(self):
        original={'original':True};calls=[]
        def solve(document,*args,**kwargs):
            self.assertIs(document,original)
            calls.append(kwargs['extra_times'])
            return {'attempt':len(calls)},dict(records=[{'slot':'arm'}])
        checks=[dict(failures=[dict(time=.25,at_key=False)]),dict(failures=[])]
        with patch('autospine_workbench.targets.character43.projected_area_adaptive.repair',side_effect=solve), patch(
                'autospine_workbench.targets.character43.projected_area_adaptive.inspect',side_effect=checks):
            result,report=build(original,'motion',{})
        self.assertEqual(calls,[[],[.25]])
        self.assertEqual(result,{'attempt':2})
        self.assertEqual(len(report['refinement']),2)

    def test_failed_solved_key_does_not_trigger_endless_refinement(self):
        with patch('autospine_workbench.targets.character43.projected_area_adaptive.repair',return_value=({},dict(records=[]))) as solve, patch(
                'autospine_workbench.targets.character43.projected_area_adaptive.inspect',return_value=dict(failures=[dict(time=0,at_key=True)])):
            _,report=build({},'motion',{})
        self.assertEqual(solve.call_count,1)
        self.assertEqual(len(report['refinement'][0]['check']['failures']),1)
