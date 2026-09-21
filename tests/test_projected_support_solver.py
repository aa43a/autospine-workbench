import math
import unittest
from autospine_workbench.targets.character43.projected_support_solver import solve


class ProjectedSupportTests(unittest.TestCase):
    def test_bilateral_contact_preserves_each_bend_direction(self):
        rows=[dict(hip=[-10,0],knee=[-5,-30],ankle=[-10,-60],target=[-10,-65]),
              dict(hip=[10,0],knee=[5,-35],ankle=[10,-70],target=[10,-65])]
        result=solve(rows,100)
        self.assertEqual(result['status'],'candidate')
        for original,actual in zip(rows,result['chains']):
            self.assertLess(actual['error_px'],.01)
            for a,b in [('hip','knee'),('knee','ankle')]:
                old=[original[b][j]-original[a][j] for j in (0,1)]
                new=[actual[b][j]-actual[a][j] for j in (0,1)]
                self.assertAlmostEqual(old[0]*new[1]-old[1]*new[0],0)
                self.assertGreater(sum(x*y for x,y in zip(old,new)),0)

    def test_unreachable_contact_keeps_failed_status_and_budgets(self):
        result=solve([dict(hip=[0,0],knee=[1,-5],ankle=[0,-10],target=[100,100])],10)
        self.assertEqual(result['status'],'no_bounded_solution_found')
        self.assertLessEqual(math.hypot(*result['root_shift']),1.500000001)
        self.assertTrue(.85<=result['chains'][0]['factor']<=1.15)

    def test_collapsed_chain_is_not_given_an_invented_direction(self):
        with self.assertRaisesRegex(ValueError,'collapsed'):
            solve([dict(hip=[0,0],knee=[1,0],ankle=[0,0],target=[1,1])],10)
