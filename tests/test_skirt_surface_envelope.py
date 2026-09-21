import unittest
from autospine_workbench.targets.character43.skirt_surface_envelope import material_offsets,at

class SurfaceTests(unittest.TestCase):
    def test_scale_and_mirror_and_anchor(self):
        points=[[-2,0],[0,0],[2,0],[-2,2],[0,2],[2,2]]
        triangles=[0,1,3,1,4,3,1,2,4,2,5,4]
        model=material_offsets(points,triangles,2)
        self.assertEqual(model['offsets'][1],[.25,.75])
        self.assertEqual(model['offsets'][0],[0,0])
        scaled=material_offsets([[x*10,y*10] for x,y in points],triangles,20)
        self.assertEqual(model['offsets'],scaled['offsets'])
        mirrored=material_offsets([[-x,y] for x,y in points],triangles,2)
        self.assertEqual(model['offsets'],mirrored['offsets'])
        self.assertEqual(at(model,1,'front')[1],[1.25,1.75])
        self.assertEqual(at(model,1,'back')[1],[.25,.75])
    def test_missing_or_invalid_shape_is_not_guessed(self):
        self.assertEqual(material_offsets([[0,0]],[],1)['offsets'],[None])
        with self.assertRaises(ValueError):material_offsets([[0,0]],[2,2,2],1)
        with self.assertRaises(ValueError):material_offsets([[0,0]],[],1,aspect_range=(.8,.2))

if __name__=='__main__':unittest.main()
