import math
import unittest
from unittest.mock import patch
from m4_shoulder_interval_repair import solve_interval
from autospine_workbench.targets.character43.deform_addition import value
from autospine_workbench.targets.character43.linear_triangle_interval import signed_area


class IntervalRepairTests(unittest.TestCase):
    def test_shared_correction_repairs_between_endpoints_without_moving_them(self):
        points=[[0.,0.],[1.,0.],[0.,1.]]
        original={};doc={'bones':[{'name':'bone'}],
            'skins':[{'attachments':{'arm':{'arm':{'vertices':[1,0,0,0,1]*3}}}}]}
        row={'slot':'arm','points':points,'triangles':[[0,1,2]]}
        prepared={'free':[0,1,2],'context':{'budget_px':2}}
        def sample(document,name,time):
            height=1 if document is original or name=='setup' else 1-.51*math.sin(math.pi*time)
            return {'arm':[[0.,0.],[1.,0.],[0.,height]],'owner':points},{}
        transforms={'bone':(1,0,0,1,0,0),'chest':(1,0,0,1,0,0)}
        with patch('m4_shoulder_interval_repair.sample',sample),patch('m4_shoulder_interval_repair.matrices',return_value=transforms),patch('m4_shoulder_interval_repair.constraints',return_value=(points,[])):
            keys,evidence=solve_interval(original,doc,row,prepared,'owner',0,1,{0})
        self.assertTrue(evidence['feasible'])
        self.assertEqual(keys[0]['vertices'],[0.]*6)
        self.assertEqual(keys[-1]['vertices'],[0.]*6)
        for time in evidence['sample_times']:
            base=sample(doc,'motion',time)[0]['arm'];offset=value(keys,time,6)
            result=[[p[0]+offset[2*i],p[1]+offset[2*i+1]] for i,p in enumerate(base)]
            self.assertGreaterEqual(signed_area(result)/signed_area(points),.5)


if __name__=='__main__':unittest.main()
