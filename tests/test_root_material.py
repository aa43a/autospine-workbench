import unittest
from unittest.mock import patch
from copy import deepcopy
from io import BytesIO
import numpy as np
from PIL import Image
from m4_root_material import split_texture,preserve_padding,apply


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

    def test_preserves_real_atlas_border_instead_of_edge_extrusion(self):
        source=np.full((4,4,4),255,dtype=np.uint8)
        page=np.pad(source,((2,2),(2,2),(0,0)))
        page[:,:,:3]=91;source=page[2:-2,2:-2].copy()
        split=source.copy();split[0,:2,3]=0
        actual=preserve_padding(split,source,page)
        np.testing.assert_array_equal(actual[2:-2,2:-2],split)
        np.testing.assert_array_equal(actual[:,:,:3],page[:,:,:3])
        self.assertEqual(actual[:2,:,3].sum(),0)
        np.testing.assert_array_equal(actual[3:,4:],page[3:,4:])

    def test_rejects_unproven_atlas_layout(self):
        source=np.full((4,4,4),255,dtype=np.uint8)
        with self.assertRaisesRegex(ValueError,'page_layout'):
            preserve_padding(source,source,np.zeros((4,4,4),dtype=np.uint8))

    def test_connection_piece_reuses_original_weighted_tracks_before_clips(self):
        from test_m4_triangle_clip_candidate import fixture
        from m4_triangle_clip_candidate import build
        source,field=fixture();candidate=build(source,field,'arm','body');original=deepcopy(candidate)
        image=np.full((2,2,4),255,dtype=np.uint8);page=np.pad(image,((2,2),(2,2),(0,0)))
        def png(value):
            out=BytesIO();Image.fromarray(value).save(out,format='PNG');return out.getvalue()
        files={'images/arm.png':png(image),'textures/arm.png':png(page),
               'skeleton.atlas':b'textures/arm.png\nsize: 6,6\nfilter: Linear,Linear\npma: false\nrepeat: none\narm\nbounds: 2,2,2,2\n'}
        mask=np.array([[True,False],[False,False]]);root,free,_=split_texture(image,mask)
        with patch('m4_root_material.partition',return_value=(root,free,{})):
            result,output,report=apply(candidate,source,files,'arm','body','root','root')
        self.assertEqual(candidate,original)
        self.assertEqual(result['slots'][0]['name'],'m4-root-material')
        attachments=result['skins'][0]['attachments']
        for side in ('front','back'):
            name=f'm4-tri-{side}-0000';self.assertEqual(attachments[name][name]['path'],'m4-free-material')
        tracks=result['animations']['external-motion']['attachments']['default']
        self.assertEqual(tracks['m4-root-material']['m4-root-material'],
                         source['animations']['external-motion']['attachments']['default']['arm']['arm'])
        self.assertEqual(report['render_parts'],2)
        actual=np.asarray(Image.open(BytesIO(output['textures/m4-free-material.png'])))
        self.assertEqual(actual[:2,:,3].sum(),0)
