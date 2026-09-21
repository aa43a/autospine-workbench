import unittest
import numpy as np
from test_motion_depth_overlap import fixture
from autospine_workbench.targets.character43.depth_group_raster import raster
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.spine43.seam_raster import mask,texture


class GroupRasterTests(unittest.TestCase):
    def test_crop_preserves_mask_on_all_common_pixels(self):
        rng=np.random.default_rng(12)
        for angle in (-170,-41,0,53,130):
            doc,files=fixture();doc['bones'][0].update(x=-3.2,y=2.6,rotation=angle,scaleX=12,scaleY=3)
            vertices=sample(doc,'test',0)[0]['a']
            mesh=doc['skins'][0]['attachments']['a']['a'];alpha=texture(files['images/a.png'])
            for indices in ([0,1,2],[0,2,3],[0,1,2,0,2,3]):
                group=dict(mesh,triangles=indices);common=rng.random((64,64))>.5
                common[:20]=False;common[:,40:]=False
                charges=[];rect=[-32,-32,64,64]
                actual=raster(group,vertices,alpha,rect,common,charges.append)&common
                expected=(mask(group,vertices,alpha,rect)>=8)&common
                np.testing.assert_array_equal(actual,expected)
                self.assertLess(sum(charges),64*64)

    def test_no_common_pixels_consumes_no_budget(self):
        doc,files=fixture();mesh=doc['skins'][0]['attachments']['a']['a'];charges=[]
        result=raster(mesh,sample(doc,'test',0)[0]['a'],texture(files['images/a.png']),
            [0,0,2,2],np.zeros((2,2),dtype=bool),charges.append)
        self.assertFalse(result.any());self.assertEqual(charges,[])

    def test_budget_refusal_is_propagated(self):
        doc,files=fixture();mesh=doc['skins'][0]['attachments']['a']['a']
        def fail(_):raise ValueError('budget')
        with self.assertRaisesRegex(ValueError,'budget'):
            raster(mesh,sample(doc,'test',0)[0]['a'],texture(files['images/a.png']),
                [0,-2,2,2],np.ones((2,2),dtype=bool),fail)
