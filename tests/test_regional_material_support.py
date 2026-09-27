import unittest
import numpy as np
from PIL import Image
from autospine_workbench.targets.character43.regional_material_support import candidates,assign,solve
from autospine_workbench.targets.character43.sliding_material_support import nearest


class RegionalSupportTests(unittest.TestCase):
    def setUp(self):
        self.points=[[0,0],[10,0],[10,10],[0,10]]
        self.mesh=dict(uvs=[0,0,1,0,1,1,0,1],triangles=[0,1,2,0,2,3])
        self.texture=Image.new('RGBA',(10,10))
        for x in range(6,10):
            for y in range(0,5):self.texture.putpixel((x,y),(200,200,200,255))

    def test_adjacent_triangle_support_without_increasing_world_budget(self):
        query=[4,6]
        self.assertIsNone(nearest(self.mesh,self.points,self.texture,query))
        options=candidates(self.mesh,self.points,self.texture,query)
        self.assertTrue(options)
        self.assertTrue(all(r['distance_px']<=8 and r['triangle']==0 for r in options))
        self.assertEqual(candidates(self.mesh,self.points,self.texture,[-20,-20]),[])
        self.assertEqual(candidates(self.mesh,self.points,Image.new('RGBA',(10,10)),query),[])

    def test_assignment_does_not_reuse_same_texel(self):
        a=dict(pixel=[1,1],distance_px=1);b=dict(pixel=[2,1],distance_px=2)
        assigned=assign([[a,b],[a,b]])
        self.assertEqual(len({tuple(r['pixel']) for r in assigned}),2)
        with self.assertRaisesRegex(ValueError,'assignment_conflict'):assign([[a],[a]])
        with self.assertRaisesRegex(ValueError,'missing'):assign([[]])

    def test_joint_field_preserves_fixed_vertices_and_limits_infeasible_target(self):
        supports=[dict(vertices=[0,1,2],weights=[0,0,1])]
        tri=[[0,1,2],[0,2,3]]
        result,report=solve(self.points,self.points,tri,supports,[[11,10]],[0,1])
        self.assertEqual(result[:2],self.points[:2])
        self.assertLess(report['maximum_target_error_px'],.001)
        self.assertLessEqual(report['maximum_displacement_px'],8)
        self.assertGreater(np.linalg.norm(np.asarray(result[3])-self.points[3]),0)
        result,report=solve(self.points,self.points,tri,supports,[[30,10]],[0,1])
        self.assertIsNotNone(result)
        self.assertLessEqual(report['maximum_displacement_px'],8+1e-7)
        self.assertGreater(report['maximum_target_error_px'],11.9)
        self.assertEqual(result[:2],self.points[:2])
