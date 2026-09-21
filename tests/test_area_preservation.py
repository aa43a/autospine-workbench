import math
import unittest
from autospine_workbench.targets.character43.area_preservation import from_pose
from autospine_workbench.targets.character43.area_preservation import outside_repair_band
from autospine_workbench.targets.character43.area_projection import project
from autospine_workbench.targets.character43.local_area_constraints import refine
from autospine_workbench.targets.spine43.continuous_pose import area


def context(budget=1):
    return dict(row={'triangles':[[0,1,2]]},areas=[1.],edges=[(0,1),(1,2),(0,2)],
                lengths=[2,math.sqrt(2),math.sqrt(2)],free=[False,False,True],
                budget=budget,minimum_ratios=[.9])


class AreaPreservationTests(unittest.TestCase):
    def test_repair_band_is_one_ring_and_retains_distant_healthy_shape(self):
        points=[[0,0],[2,0],[1,.1],[3,1],[4,1],[5,2]]
        triangles=[[0,1,2],[1,3,2],[3,4,5]]
        floors,band=outside_repair_band(points,triangles,[1,.95,.5])
        self.assertEqual(band,[0,1]);self.assertEqual(floors,[.5,.5,1.])

    def test_floor_tracks_healthy_pose_but_does_not_preserve_overexpansion_or_fold(self):
        points=[[0,0],[2,0],[0,.8],[0,2],[0,-1]]
        self.assertEqual(from_pose(points,[[0,1,2],[0,1,3],[0,1,4]],[1]*3),[.8,1.,.5])

    def test_both_solvers_restore_area_lost_by_previous_correction(self):
        base=[[0,0],[2,0],[1,.9]];initial=[[0,0],[2,0],[1,.55]]
        for solver in (lambda c:project(c,base,initial=initial),
                       lambda c:refine(c,base,initial,analytic=True)):
            points,report=solver(context())
            self.assertEqual(points[:2],base[:2])
            self.assertGreaterEqual(area(points,[0,1,2]),.9-1e-7)
            self.assertLessEqual(math.dist(points[2],base[2]),1+1e-7)

    def test_impossible_preservation_is_not_reported_as_success(self):
        base=[[0,0],[2,0],[1,.6]]
        _,report=project(context(.1),base)
        self.assertFalse(report['converged'])
        points,report=refine(context(.1),base,base,analytic=True)
        self.assertEqual(points,base)
        self.assertNotEqual(report['status'],'candidate')

    def test_invalid_floors_are_rejected_by_both_solvers(self):
        base=[[0,0],[2,0],[1,1]]
        for value in ([float('nan')],[],[.4],[1.1]):
            ctx=context();ctx['minimum_ratios']=value
            for solver in (lambda:project(ctx,base),lambda:refine(ctx,base,base)):
                with self.assertRaisesRegex(ValueError,'invalid_floors'):solver()
