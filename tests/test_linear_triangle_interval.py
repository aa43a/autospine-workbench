import unittest
from autospine_workbench.targets.character43.linear_triangle_interval import extrema


class LinearTriangleIntervalTests(unittest.TestCase):
    def test_good_endpoints_can_collapse_between_them(self):
        setup=[[0,0],[1,0],[0,1]]
        end=[[0,0],[-1,0],[0,-1]]
        result=extrema(setup,setup,end)
        self.assertEqual(result['maximum']['area_ratio'],1)
        self.assertEqual(result['minimum'],{'u':.5,'area_ratio':0})

    def test_translation_preserves_area_with_reversed_winding(self):
        setup=[[0,0],[0,1],[1,0]]
        end=[[x+100,y-20] for x,y in setup]
        result=extrema(setup,setup,end)
        self.assertEqual(result['minimum']['area_ratio'],1)
        self.assertEqual(result['maximum']['area_ratio'],1)

    def test_degenerate_and_nonfinite_are_rejected(self):
        setup=[[0,0],[1,0],[0,1]]
        with self.assertRaises(ValueError):extrema([[0,0]]*3,setup,setup)
        with self.assertRaises(ValueError):extrema(setup,setup,[[0,0],[1,0],[0,float('nan')]])


if __name__=='__main__':unittest.main()
