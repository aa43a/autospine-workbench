from copy import deepcopy
import unittest
from test_area_preservation_sampling import fixture
from test_area_preservation import context
from autospine_workbench.targets.character43.interpolation_area_margin import targets,update,LIMIT
from autospine_workbench.targets.character43.area_projection import project
from autospine_workbench.targets.spine43.continuous_pose import area


class InterpolationMarginTests(unittest.TestCase):
    def test_solver_adds_headroom_without_reducing_acceptance_floor(self):
        ctx=context();ctx['minimum_ratios']=[1.];ctx['solver_margins']=[.002]
        before=deepcopy(ctx);base=[[0,0],[2,0],[1,1]]
        points,report=project(ctx,base)
        self.assertTrue(report['converged'])
        self.assertGreaterEqual(area(points,[0,1,2]),1.002-1e-7)
        self.assertEqual(ctx,before);self.assertEqual(points[:2],base[:2])

    def test_updates_use_worst_midpoint_not_duplicate_accumulation(self):
        row=dict(slot='mesh',at_key=False,preservation_failures=[dict(triangle=0,minimum=1.,ratio=.999)])
        previous={'mesh':[.001]}
        result=update(fixture(),{'failures':[row,row]},previous)
        self.assertAlmostEqual(result['mesh'][0],.003001)
        self.assertEqual(previous,{'mesh':[.001]})
        row['at_key']=True
        self.assertEqual(update(fixture(),{'failures':[row]},previous),previous)

    def test_resource_cap_and_invalid_margin(self):
        row=dict(slot='mesh',at_key=False,preservation_failures=[dict(triangle=0,minimum=1.,ratio=.5)])
        self.assertEqual(update(fixture(),{'failures':[row]},{}),{'mesh':[LIMIT]})
        ctx=context()
        for margin in (-.1,float('nan'),LIMIT+.01):
            ctx['solver_margins']=[margin]
            with self.assertRaisesRegex(ValueError,'margins_invalid'):targets(ctx)
