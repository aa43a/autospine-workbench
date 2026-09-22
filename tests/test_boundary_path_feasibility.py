import unittest
from autospine_workbench.targets.character43.boundary_path_feasibility import inspect


class PathTests(unittest.TestCase):
    def test_path_detects_conflict_without_fixed_edge(self):
        setup=[[0,0],[1,0],[1,1],[2,0]];triangles=[[0,1,2],[1,3,2]]
        fixed=[[0,0],[1,0],[1,1],[5,0]]
        result=inspect(setup,triangles,fixed,[1,2])
        self.assertEqual(result['status'],'fixed_boundary_path_conflict')
        self.assertEqual(result['witnesses'][0]['path'],[0,1,3])
        self.assertEqual(result['witnesses'][0]['maximum_distance_px'],4)

    def test_rigid_motion_and_scale_do_not_create_conflict(self):
        setup=[[0,0],[1,0],[1,1],[2,0]];triangles=[[0,1,2],[1,3,2]]
        for scale in (1,7):
            a=[[x*scale,y*scale] for x,y in setup]
            b=[[8-y*scale,-3+x*scale] for x,y in setup]
            self.assertEqual(inspect(a,triangles,b,[1,2])['status'],'no_path_counterexample')
