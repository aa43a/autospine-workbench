import unittest
from autospine_workbench.targets.character43.material_band_partition import partition


class MaterialBandTests(unittest.TestCase):
    def test_coverage_winding_and_uv_reconstruction(self):
        p=[[0,0],[4,0],[4,4],[0,4]];uv=[[x/4,y/4] for x,y in p]
        parts=partition(p,uv,[[0,1,2],[0,2,3]],[0,2],[0,1],[-.5,.5])
        areas=[]
        for part in parts:
            total=0
            for tri in part['triangles']:
                a,b,c=[part['points'][i] for i in tri]
                area=((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))/2
                self.assertGreater(area,0);total+=area
            areas.append(total)
            for (x,y),(u,v) in zip(part['points'],part['uvs']):
                self.assertAlmostEqual(u,x/4);self.assertAlmostEqual(v,y/4)
        self.assertEqual(areas,[6,4,6])

    def test_cut_on_existing_edge_has_no_duplicate_area(self):
        parts=partition([[0,0],[1,0],[0,1]],[[0,0],[1,0],[0,1]],[[0,1,2]],[0,0],[0,1],[0])
        self.assertEqual(parts[0]['triangles'],[])
        self.assertEqual(len(parts[1]['triangles']),1)

    def test_invalid_cut_order_rejected(self):
        with self.assertRaises(ValueError):partition([[0,0]],[[0,0]],[],[0,0],[1,0],[1,0])

    def test_clockwise_winding_is_preserved(self):
        parts=partition([[0,0],[0,2],[2,0]],[[0,0],[0,1],[1,0]],[[0,1,2]],[0,0],[1,0],[.5])
        total=0
        for part in parts:
            for tri in part['triangles']:
                a,b,c=[part['points'][i] for i in tri]
                signed=((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))/2
                self.assertLess(signed,0);total+=signed
        self.assertAlmostEqual(total,-2)
