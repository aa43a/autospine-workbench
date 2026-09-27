import unittest
import numpy as np
from autospine_workbench.targets.character43.material_exposure_region import inspect,components


class MaterialExposureRegionTests(unittest.TestCase):
    def test_components_keep_disconnected_regions_separate(self):
        self.assertEqual(components([(0,0),(1,0),(2,1)]),[
            dict(points=2,bounds=[0,0,2,1]),dict(points=1,bounds=[2,1,3,2])])

    def test_translation_exposes_area_without_losing_provenance(self):
        mesh=dict(triangles=[0,1,2,2,1,3],uvs=[0,0,1,0,0,1,1,1])
        rest=[[0,0],[4,0],[0,4],[4,4]];posed=[[x+2,y] for x,y in rest]
        alpha=np.full((4,4),255.)
        result=inspect(mesh,rest,posed,alpha,mesh,rest,rest,alpha)
        self.assertEqual(result['summary']['newly_exposed_points'],8)
        self.assertEqual(result['summary']['ambiguous_points'],0)
        self.assertEqual(result['summary']['originally_visible_points'],0)

    def test_originally_visible_is_not_new_exposure(self):
        mesh=dict(triangles=[0,1,2],uvs=[0,0,1,0,0,1])
        rest=[[0,0],[4,0],[0,4]];alpha=np.full((4,4),255.)
        result=inspect(mesh,rest,rest,alpha,mesh,rest,rest,np.zeros((4,4)))
        self.assertEqual(result['summary']['newly_exposed_points'],0)
        self.assertGreater(result['summary']['originally_visible_points'],0)
