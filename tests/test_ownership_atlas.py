"""Owned tiles must match masked references under level-zero linear sampling."""
from copy import deepcopy
from io import BytesIO
import math
import unittest
from unittest.mock import patch
from PIL import Image
from tests.test_shared_partitions import inputs
from autospine_workbench.asset.joints.shared_partitions import combine_layer
from autospine_workbench.asset.joints.ownership_atlas import build,layout
from autospine_workbench.png_rgba import decode_rgba_png


def linear(pixels,w,h,x,y):
    x-=.5;y-=.5;ix=math.floor(x);iy=math.floor(y);fx=x-ix;fy=y-iy
    total=[0.]*4
    for dx,dy,weight in ((0,0,(1-fx)*(1-fy)),(1,0,fx*(1-fy)),(0,1,(1-fx)*fy),(1,1,fx*fy)):
        a,b=ix+dx,iy+dy
        if 0<=a<w and 0<=b<h:
            for k in range(4):total[k]+=pixels[(b*w+a)*4+k]*weight
    return total


class OwnershipAtlasTests(unittest.TestCase):
    def test_exact_sampling_at_boundaries_and_subpixels(self):
        args=inputs();layer=combine_layer(*args);before=deepcopy(layer)
        result,raw=build(args[0],args[1],layer);page=decode_rgba_png(raw);source=decode_rgba_png(args[0])
        with Image.open(BytesIO(args[1])) as im:owners=im.tobytes()
        for tile in result['tiles']:
            code=tile['owner_code'];ox,oy,w,h=tile['rect'];expected=bytearray(w*h*4)
            for i,o in enumerate(owners):
                if o==code:expected[i*4:i*4+4]=source.pixels[i*4:i*4+4]
            for x in (0,.01,.25,.5,1,10.25,11.5,12.75,w-.25,w):
                for y in (0,.01,.25,.5,3.25,h/2,h-.25,h):
                    for a,b in zip(linear(expected,w,h,x,y),linear(page.pixels,page.width,page.height,ox+x,oy+y)):
                        self.assertLessEqual(abs(a-b),1e-9)
        self.assertEqual(layer,before)
        self.assertEqual((result,raw),build(args[0],args[1],layer))
        for old,new in zip(layer['partitions'],result['partitions']):
            for key in ('vertices_xy','triangles','weights'):self.assertEqual(old['geometry'][key],new['geometry'][key])
            self.assertEqual(old['geometry']['uvs'],new['geometry']['source_uvs'])
        self.assertEqual(result['residual'],layer['residual'])

    def test_layout_bounds_and_invalid_uv_or_source(self):
        for bad in (0,-1,True,float('nan')):
            with self.assertRaisesRegex(ValueError,'dimensions_invalid'):layout(bad,20)
        w,h,origins=layout(1000,2000)
        self.assertLessEqual(max(w,h),4096)
        self.assertEqual(len(origins),3)
        with self.assertRaisesRegex(ValueError,'resource_limit'):layout(4096,4096)
        args=inputs();layer=combine_layer(*args);layer['partitions'][0]['geometry']['uvs'][0][0]=1.01
        with self.assertRaisesRegex(ValueError,'uv_invalid'):build(args[0],args[1],layer)
        layer=combine_layer(*args);layer['qa']['source_rgba_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'source_changed'):build(args[0],args[1],layer)

    def test_exact_reader_rejects_tampering(self):
        from autospine_workbench.benchmark.ownership_atlas_cli import read_atlas
        doc={'source_partitions_sha256':'a'*64,'production_authorized':False}
        with patch('autospine_workbench.benchmark.ownership_atlas_cli.read_mesh_report',return_value=dict(doc,production_authorized=True)), \
             patch('autospine_workbench.benchmark.ownership_atlas_cli.compile_report',return_value=(doc,b'',{})):
            with self.assertRaisesRegex(ValueError,'replay_mismatch'):
                read_atlas(None,{'dataset_id':'test'},'b'*64,workspace=None)
