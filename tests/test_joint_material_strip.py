import math
import unittest
from autospine_workbench.targets.character43.joint_material_strip import map_points,jacobian_samples


class JointStripTests(unittest.TestCase):
    def test_jacobian_distinguishes_continuum_fold_from_coarse_mesh(self):
        m=(1,0,0,1,0,0)
        straight=jacobian_samples([[0,0],[0,2]],[0,0],[1,0],2,m,m)
        self.assertTrue(all(abs(r['determinants'][0]-1)<1e-8 for r in straight))
        # Crossing fixed endpoints forces this Hermite centerline to reverse.
        folded=jacobian_samples([[0,0]],[0,0],[1,0],2,m,(1,0,0,1,-8,0))
        self.assertTrue(folded[0]['negative_at_both_steps'])

    def test_setup_reconstruction(self):
        points=[[-4,2],[-1,-2],[0,3],[1,2],[4,-3]];m=(1,0,0,1,0,0)
        actual=map_points(points,[0,0],[1,0],2,m,m)
        for a,b in zip(points,actual):
            for x,y in zip(a,b):self.assertAlmostEqual(x,y)

    def test_affine_endpoints_and_derivative_continuity(self):
        a=(1,0,0,1,0,0);angle=.6;c,s=math.cos(angle),math.sin(angle);b=(c,-s,s,c,1,2)
        eps=1e-5
        for boundary,frame in [(-2,a),(2,b)]:
            points=map_points([[boundary-eps,.4],[boundary,.4],[boundary+eps,.4]],[0,0],[1,0],2,a,b)
            for k in (0,1):
                self.assertAlmostEqual((points[1][k]-points[0][k])/eps,(points[2][k]-points[1][k])/eps,places=4)
            aa,bb,cc,dd,x,y=frame
            for got,want in zip(points[1],[aa*boundary+bb*.4+x,cc*boundary+dd*.4+y]):self.assertAlmostEqual(got,want)

    def test_rejects_singular_and_half_turn(self):
        for b in [(0,0,0,1,0,0),(-1,0,0,-1,0,0)]:
            with self.assertRaises(ValueError):map_points([[0,0]],[0,0],[1,0],2,(1,0,0,1,0,0),b)

    def test_follow_curve_setup_and_join_continuity(self):
        m=(1,0,0,1,0,0)
        actual=map_points([[-1,2],[0,1],[1,-2]],[0,0],[1,0],2,m,m,follow_curve=True)
        for a,b in zip(actual,[[-1,2],[0,1],[1,-2]]):
            for x,y in zip(a,b):self.assertAlmostEqual(x,y)
        b=(math.cos(.6),-math.sin(.6),math.sin(.6),math.cos(.6),1,2)
        for boundary in (-2,2):
            eps=1e-5
            points=map_points([[boundary-eps,.4],[boundary,.4],[boundary+eps,.4]],
                [0,0],[1,0],2,m,b,follow_curve=True)
            for k in (0,1):
                self.assertAlmostEqual((points[1][k]-points[0][k])/eps,(points[2][k]-points[1][k])/eps,places=4)
