import unittest
import numpy as np
from m4_root_material import split_texture


class RootMaterialTests(unittest.TestCase):
    def test_guard_only_inside_opaque_source_and_no_pixel_loss(self):
        source=np.full((5,5,4),255,dtype=np.uint8);source[:,:,0]=123
        source[0,:,3]=0;source[1,2,3]=100
        mask=np.zeros((5,5),bool);mask[2,2]=True
        root,free,count=split_texture(source,mask)
        self.assertEqual(count,7)
        self.assertEqual(root[1,2,3],0)
        self.assertEqual(free[1,2,3],100)
        self.assertEqual(root[0,:,3].sum(),0)
        np.testing.assert_array_equal(np.maximum(root[:,:,3],free[:,:,3]),source[:,:,3])
        np.testing.assert_array_equal(root[:,:,:3],source[:,:,:3])
        np.testing.assert_array_equal(free[:,:,:3],source[:,:,:3])
        self.assertEqual(root[4,4,3],0)
        self.assertEqual(free[4,4,3],255)

    def test_no_guard_at_transparent_outer_edge(self):
        source=np.zeros((3,3,4),dtype=np.uint8);source[1,1]=[80,90,100,255]
        mask=np.zeros((3,3),bool);mask[1,1]=True
        root,free,count=split_texture(source,mask)
        np.testing.assert_array_equal(root,source)
        self.assertEqual(count,0);self.assertEqual(free[:,:,3].sum(),0)

    def test_nonbinary_mask_rejected(self):
        with self.assertRaisesRegex(ValueError,'mask_shape'):
            split_texture(np.zeros((2,2,4)),np.ones((2,2)))
