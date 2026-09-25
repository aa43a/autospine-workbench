import unittest
from autospine_workbench.targets.character43.dual_area_floor import floors


class DualAreaTests(unittest.TestCase):
    def test_both_signed_area_references_are_preserved(self):
        for sign in (1,-1):
            result=floors([sign*10,sign*10],[sign*9,sign*20])
            self.assertAlmostEqual(result[0]*9/10,.505)
            self.assertEqual(result[1],.505)

    def test_infeasible_references_are_not_clamped_to_passing_bounds(self):
        for a,b in [([],[]),([1],[1,2]),([0],[1]),([1],[-1]),([1],[float('nan')])]:
            with self.assertRaises(ValueError):floors(a,b)
        with self.assertRaisesRegex(ValueError,'infeasible'):floors([10],[1])
        with self.assertRaisesRegex(ValueError,'infeasible'):floors([1],[10])


if __name__=='__main__':unittest.main()
