import math
import unittest
from autospine_workbench.asset.planning.cloth_anchor_solver import solve
from autospine_workbench.asset.planning.cloth_anchor_correction import interpolate,build


class ClothAnchorTests(unittest.TestCase):
    def test_inversion_repair_preserves_anchor_and_other_region(self):
        setup=[[0.,0.],[2.,0.],[0.,2.],[4.,4.]]
        points=[[0.,0.],[2.,0.],[0.,-.1],[4.,4.]]
        result,e=solve(setup,[[0,1,2]],points,[1,2],[1],3.)
        self.assertEqual(result[0],points[0]);self.assertEqual(result[1],points[1]);self.assertEqual(result[3],points[3])
        self.assertEqual(e['qa']['inversions'],0)
        self.assertLessEqual(e['max_offset'],3.)
        self.assertEqual(solve(setup,[[0,1,2]],points,[1,2],[1],3.)[0],result)

    def test_similarity_and_budget(self):
        p=[[0.,0.],[2.,0.],[0.,2.]];q=[[0.,0.],[2.,0.],[0.,-.1]]
        transform=lambda rows:[[30-3*x,20+3*y] for x,y in rows]
        a,_=solve(p,[[0,1,2]],q,[2],[0,1],.5)
        b,_=solve(transform(p),[[0,1,2]],transform(q),[2],[0,1],1.5)
        for x,y in zip(transform(a),b):self.assertLess(math.dist(x,y),1e-9)
        self.assertLessEqual(math.dist(a[2],q[2]),.5+1e-9)

    def test_setup_noop_and_interpolation_endpoints(self):
        p=[[0.,0.],[2.,0.],[0.,2.]]
        self.assertEqual(solve(p,[[0,1,2]],p,[2],[0,1],1.)[0],p)
        keys=[[[float(i),-float(i)]] for i in range(33)]
        self.assertEqual(interpolate(keys,0),keys[0]);self.assertEqual(interpolate(keys,128),keys[-1])
        self.assertEqual(interpolate(keys,3),[[.75,-.75]])
        with self.assertRaises(ValueError):build({}, {'bones':[]})
        with self.assertRaises(ValueError):solve(p,[[0,1,2]],p,[2],[],float('nan'))
