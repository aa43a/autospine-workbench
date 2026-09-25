import unittest
import numpy as np
from PIL import Image
from autospine_workbench.targets.character43.sliding_material_support import nearest,targets


class SlidingMaterialTests(unittest.TestCase):
    def test_fixed_waist_is_never_unlocked_to_reach_support(self):
        points=[[0,0],[2,0],[0,2]]
        result=targets(points,[0,1,2],[.5,.25,.25],{0},[1,0])
        self.assertNotIn(0,result)
        self.assertEqual(result,{1:[4.,0.],2:[2.,2.]})
        with self.assertRaises(ValueError):targets(points,[0,1,2],[.5,.25,.25],{0},[5,0])
        with self.assertRaises(ValueError):targets(points,[0,1,2],[.5,.25,.25],{0,1,2},[1,0])

    def test_uses_nearby_opaque_material_without_source_point_lock(self):
        mesh={'uvs':[0,0,1,0,0,1],'triangles':[0,1,2]};points=[[0,0],[12,0],[0,12]]
        image=Image.new('RGBA',(12,12),(255,255,255,255))
        result=nearest(mesh,points,image,np.asarray([3.,3.]))
        self.assertIsNotNone(result);self.assertLess(result['distance_px'],1)
        self.assertEqual(result['triangle'],0)

    def test_transparent_or_outside_material_is_not_support(self):
        mesh={'uvs':[0,0,1,0,0,1],'triangles':[0,1,2]};points=[[0,0],[12,0],[0,12]]
        image=Image.new('RGBA',(12,12),(255,255,255,0))
        self.assertIsNone(nearest(mesh,points,image,np.asarray([3.,3.])))
        image=Image.new('RGBA',(12,12),(255,255,255,255))
        self.assertIsNone(nearest(mesh,points,image,np.asarray([20.,20.])))


if __name__=='__main__':unittest.main()
