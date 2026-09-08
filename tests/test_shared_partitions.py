"""Source texture reuse must not swallow residuals or lose exact coordinates."""
from copy import deepcopy
import hashlib
import unittest
from unittest.mock import patch
from tests.test_partition_mesh import fixture
from autospine_workbench.asset.joints.partition_pixels import png
from autospine_workbench.asset.joints.partition_mesh import build_region
from autospine_workbench.asset.joints.shared_partitions import combine_layer
from autospine_workbench.png_rgba import decode_rgba_png


def inputs():
    raw,source,_,_,skeleton=fixture();image=decode_rgba_png(raw)
    pixels=bytearray(image.pixels);pixels[:4]=bytes([17,32,99,0])
    raw=png('RGBA',(image.width,image.height),pixels)
    owners=bytes(1 if i%24<11 else 2 if i%24>12 else 3 for i in range(24*80))
    rows=[];images={}
    for code,side in ((1,'l'),(2,'r')):
        selected=bytearray(len(pixels))
        for i,o in enumerate(owners):
            if o==code:selected[i*4:i*4+4]=pixels[i*4:i*4+4]
        part=png('RGBA',(24,80),selected);bones=deepcopy(skeleton)
        if side=='r':
            for bone in bones['bones']:
                bone['id']=bone['id'].replace('_l','_r');bone['parent_id']=bone['parent_id'].replace('_l','_r')
        row=build_region(part,source,side,[b['id'] for b in bones['bones']],bones)
        rows.append(row);images[row['layer_id']]=part
    metadata={'layer_id':source['layer_id'],'bbox':source['bbox'],'source_image_sha256':hashlib.sha256(raw).hexdigest()}
    return raw,png('L',(24,80),owners),metadata,rows,images


class SharedPartitionsTests(unittest.TestCase):
    def test_exact_rgba_shared_uv_and_residual(self):
        args=inputs();before=deepcopy(args);result=combine_layer(*args)
        self.assertEqual(args,before)
        self.assertEqual(result,combine_layer(*args))
        self.assertTrue(result['qa']['rgba_reconstruction_exact'])
        self.assertEqual(result['qa']['source_rgba_sha256'],result['qa']['reconstructed_rgba_sha256'])
        self.assertGreater(result['residual']['visible_pixels'],0)
        self.assertEqual(result['residual']['bone_ids'],[])
        self.assertEqual(len({p['texture_ref'] for p in result['partitions']}),1)
        self.assertTrue(all(p['qa']['source_uv_max_error_px']<1e-7 for p in result['partitions']))
        self.assertEqual(result['target_gate']['status'],'blocked')
        for row,part in zip(args[3],result['partitions']):
            self.assertEqual(row['weights'],part['geometry']['weights'])

    def test_rejects_wrong_mask_uv_texture_and_region(self):
        args=list(inputs());args[1]=png('L',(24,80),bytes(24*80))
        with self.assertRaisesRegex(ValueError,'owner_invalid'):combine_layer(*args)
        args=list(inputs());args[3][0]['uvs'][0][0]+=.1
        with self.assertRaisesRegex(ValueError,'uv_mismatch'):combine_layer(*args)
        args=list(inputs());args[2]['source_image_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'source_changed'):combine_layer(*args)
        args=list(inputs());args[4][args[3][0]['layer_id']]=args[4][args[3][1]['layer_id']]
        with self.assertRaisesRegex(ValueError,'region_changed'):combine_layer(*args)

    def test_reader_rejects_changed_policy(self):
        from autospine_workbench.benchmark.shared_partition_cli import read_shared
        doc={'source_mesh_sha256':'a'*64,'residual_policy':'retain_original'}
        with patch('autospine_workbench.benchmark.shared_partition_cli.read_mesh_report',return_value=dict(doc,residual_policy='nearest')), \
             patch('autospine_workbench.benchmark.shared_partition_cli.compile_report',return_value=(doc,b'',{})):
            with self.assertRaisesRegex(ValueError,'replay_mismatch'):
                read_shared(None,{'dataset_id':'test'},'b'*64,workspace=None)
