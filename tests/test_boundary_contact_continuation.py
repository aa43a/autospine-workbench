import unittest
from unittest.mock import patch
from autospine_workbench.targets.character43.boundary_contact_continuation import solve


class ContactContinuationTests(unittest.TestCase):
    def test_final_constraints_and_budget_are_exact_and_failures_are_not_baked(self):
        world=[[0.,0.],[1.,0.],[0.,1.]];fixed=[[.2,0.],[1.,0.],[0.,1.]]
        regions=[dict(vertex=0,center=[.3,.4],inverse=[[1.,0.],[0.,1.]],radius=.1)]
        calls=[]
        def refined(setup,tri,target,free,origin,seed,budget,**kw):
            calls.append((target,origin,budget,kw['regions']))
            return target,{'status':'feasible_candidate'}
        with patch('autospine_workbench.targets.character43.boundary_contact_continuation.refine',side_effect=refined):
            _,report=solve(world,[[0,1,2]],world,fixed,[0],regions,2,steps=4)
        self.assertEqual(report['status'],'feasible_candidate')
        self.assertIs(calls[-1][0],fixed);self.assertIs(calls[-1][3],regions)
        self.assertTrue(all(origin is world and budget==2 for _,origin,budget,_ in calls))
        with patch('autospine_workbench.targets.character43.boundary_contact_continuation.refine',
                   return_value=([[999,999]]*3,{'status':'no_feasible_candidate_found'})):
            points,report=solve(world,[[0,1,2]],world,fixed,[0],regions,2)
        self.assertEqual(points,world);self.assertEqual(report['status'],'no_feasible_candidate_found')


if __name__=='__main__':unittest.main()
