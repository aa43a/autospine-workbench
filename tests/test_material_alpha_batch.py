import unittest
import numpy as np
from PIL import Image
from autospine_workbench.targets.character43.material_alpha_batch import sample
from m4_cloth_limb_coupling_probe import coverage


class MaterialAlphaBatchTests(unittest.TestCase):
    def test_matches_scalar_with_overlap_reverse_winding_and_degeneracy(self):
        mesh=dict(triangles=[0,1,2,2,1,3,0,0,1,0,2,1],uvs=[0,0,1,0,0,1,1,1])
        points=[[0,0],[3,0],[0,3],[3,3]]
        image=Image.new('RGBA',(4,4));rng=np.random.default_rng(7)
        image.putdata([tuple(map(int,p)) for p in rng.integers(0,256,(16,4))])
        queries=rng.uniform(-1,4,(100,2)).tolist()+[[0,0],[1.5,1.5],[3,3]]
        actual=sample(mesh,points,np.asarray(image.getchannel('A'),float),queries)
        expected=[coverage(mesh,points,image,q) for q in queries]
        np.testing.assert_allclose(actual,expected,atol=1e-10)

    def test_empty(self):
        self.assertEqual(sample(dict(triangles=[],uvs=[]),[],np.zeros((2,2)),[[0,0]]),[0.])
