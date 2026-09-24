import unittest
from autospine_workbench.targets.character43.surface_exception_regions import summarize


class ExceptionRegionsTests(unittest.TestCase):
    def report(self,points,tri):
        return summarize(points,tri,['front']*len(tri),{'triangles':[
            dict(triangle=i,intrinsic_gate_passed=False) for i in range(len(tri))]},
            [[(0,1.)]]*len(points),['calf'])

    def test_area_invariant_under_refinement(self):
        p=[[0,0,0],[2,0,0],[0,2,0]]
        a=self.report(p,[[0,1,2]])
        b=self.report(p+[[2/3,2/3,0]],[[0,1,3],[1,2,3],[2,0,3]])
        self.assertEqual(len(b['regions']),1)
        self.assertAlmostEqual(a['regions'][0]['rest_area'],b['regions'][0]['rest_area'])
        self.assertEqual(b['regions'][0]['fraction_of_role_area'],1)
        self.assertFalse(b['accepted']);self.assertIsNone(b['regions'][0]['visible'])

    def test_disconnected_regions_remain_separate(self):
        r=self.report([[0,0,0],[1,0,0],[0,1,0],[3,0,0],[4,0,0],[3,1,0]],[[0,1,2],[3,4,5]])
        self.assertEqual(len(r['regions']),2)

    def test_mismatched_evidence_rejected(self):
        with self.assertRaises(ValueError):
            summarize([[0,0,0],[1,0,0],[0,1,0]],[[0,1,2]],['front'],{'triangles':[]},[[]]*3,[])
