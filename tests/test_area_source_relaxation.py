import unittest
from copy import deepcopy
from autospine_workbench.targets.character43.area_source_relaxation import relax
from autospine_workbench.targets.spine43.continuous_pose import area


class RelaxationTests(unittest.TestCase):
    def context(self):
        return dict(row={'triangles':[[0,1,2]]},areas=[2.],minimum_ratios=[.5],
            edges=[(0,1),(1,2),(2,0)],lengths=[2,8**.5,2],budget=2,free=[False,True,True])

    def test_unnecessary_deform_recovers_without_changing_input(self):
        source=[[0,0],[2,0],[0,2]];deformed=[[0,0],[1.5,0],[0,1.5]]
        saved=deepcopy(deformed);result,report=relax(self.context(),source,deformed)
        self.assertEqual(result,source);self.assertEqual(deformed,saved)
        self.assertEqual(report['squared_displacement_after'],0)

    def test_collapsing_source_cannot_break_existing_floor(self):
        source=[[0,0],[2,0],[0,.1]];deformed=[[0,0],[2,0],[0,1.4]]
        context=self.context();context['minimum_ratios']=[.65]
        result,report=relax(context,source,deformed)
        self.assertGreaterEqual(area(result,[0,1,2])/2,.65-1e-9)
        self.assertEqual(result[0],source[0])
        self.assertLessEqual(report['squared_displacement_after'],report['squared_displacement_before'])

    def test_invalid_start_is_preserved_not_declared_repaired(self):
        source=[[0,0],[2,0],[0,2]];bad=[[0,0],[2,0],[0,-1]]
        result,report=relax(self.context(),source,bad)
        self.assertEqual(result,bad);self.assertEqual(report['status'],'initial_constraints_failed')
