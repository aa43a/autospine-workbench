import unittest
from autospine_workbench.targets.character43.depth_clip_contour import extract


class ContourTests(unittest.TestCase):
    def test_cut_crosses_triangle_interior_and_cancels_internal_edges(self):
        r=extract([[0,0],[2,0],[2,2],[0,2]],[0,1,2,0,2,3],[-1,1,1,-1])
        self.assertEqual(len(r['loops']),1)
        self.assertAlmostEqual(r['loops'][0]['signed_area'],2)
        self.assertTrue(all(p[0]>=1 for p in r['loops'][0]['points']))

    def test_reversed_winding_preserved(self):
        self.assertEqual(extract([[0,0],[2,0],[0,2]],[2,1,0],[1,1,1])['loops'][0]['signed_area'],-2)

    def test_unknown_is_not_silently_cut_out(self):
        with self.assertRaisesRegex(ValueError,'unknown'):extract([[0,0],[1,0],[0,1]],[0,1,2],[1,None,1])

    def test_empty_and_vertex_crossing(self):
        p=[[0,0],[1,0],[0,1]]
        self.assertEqual(extract(p,[0,1,2],[-1,-1,-1])['loops'],[])
        self.assertEqual(len(extract(p,[0,1,2],[0,1,1])['loops']),1)
