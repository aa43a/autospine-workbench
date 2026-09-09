import copy
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from PIL import Image
from referencing import Registry, Resource
from jsonschema import Draft202012Validator
from autospine_workbench.asset.planning.component_partitions import build as partition
from autospine_workbench.asset.planning.component_ownership import template
from autospine_workbench.asset.planning.component_mesh import build, validate, isolated_png
from autospine_workbench.asset.planning.component_mesh_review import render
from autospine_workbench.benchmark.mesh_storage import publish_mesh_report, read_mesh_report


def fixture():
    im = Image.new('RGBA', (24,24), (12,34,56,0))
    for y in range(2,22):
        for x in range(2,11): im.putpixel((x,y),(12,34,56,255))
        for x in range(14,22): im.putpixel((x,y),(12,34,56,255))
    im.putpixel((12,12),(12,34,56,7))
    buffer = BytesIO(); im.save(buffer, format='PNG'); raw=buffer.getvalue()
    layer=dict(layer_id='foot', name='footwear', bbox=[100,200,124,224], image_sha256=sha256(raw).hexdigest())
    candidate=partition(layer,raw); entries=[(layer,raw,candidate,'a'*64)]
    skeleton=dict(bones=[dict(id='foot_l',parent_id='calf_l',head_xy=[106,204],tail_xy=[106,220],world_rotation_degrees=90)])
    draft=template('fixture',entries,{},'b'*64,['foot_l'])
    draft['records'][0].update(status='assigned',semantic='body.foot',side='left',bone_ids=['foot_l'])
    return entries,skeleton,draft,{},'b'*64


class ComponentMeshTests(unittest.TestCase):
    def test_exact_region_mask_rgb_and_no_cross_region_alpha(self):
        entries,*_=fixture(); layer,raw,candidate,_=entries[0]
        isolated=Image.open(BytesIO(isolated_png(raw,candidate['components'][0])))
        original=Image.open(BytesIO(raw))
        self.assertEqual(isolated.convert('RGB').tobytes(),original.convert('RGB').tobytes())
        self.assertEqual(isolated.getpixel((5,5))[3],255)
        self.assertEqual(isolated.getpixel((17,5))[3],0)
        self.assertEqual(isolated.getpixel((12,12))[3],0)

    def test_mesh_coverage_uv_setup_and_storage_roundtrip(self):
        args=fixture(); before=copy.deepcopy(args); doc=build(*args)
        self.assertEqual(args,before)
        mesh=doc['records'][0]['mesh']
        self.assertTrue(mesh['qa']['passed'])
        self.assertEqual(mesh['raster_qa']['uncovered_alpha_pixels'],0)
        for p,uv in zip(mesh['vertices_xy'],mesh['uvs']):
            self.assertAlmostEqual(uv[0],(p[0]-100)/24)
            self.assertAlmostEqual(uv[1],(p[1]-200)/24)
        self.assertIsNone(doc['records'][1]['mesh'])
        self.assertIsNone(doc['records'][2]['mesh'])
        with tempfile.TemporaryDirectory() as root:
            digest=publish_mesh_report(root,'fixture',doc)
            self.assertEqual(validate(read_mesh_report(root,'fixture',digest),*args),doc)
        schema=json.loads(Path('schemas/component-mesh-candidates-v1.schema.json').read_text())
        base=json.loads(Path('schemas/partition-mesh-v1.schema.json').read_text())
        registry=Registry().with_resource('partition-mesh-v1.schema.json',Resource.from_contents(base))
        Draft202012Validator(schema,registry=registry).validate(doc)

    def test_stale_mask_and_mesh_mutations_rejected(self):
        args=fixture(); doc=build(*args)
        changed=copy.deepcopy(doc); changed['records'][0]['mesh']['uvs'][0][0]=999
        with self.assertRaises(ValueError): validate(changed,*args)
        args[0][0][2]['components'][0]['runs']=[]
        with self.assertRaises(ValueError): build(*args)

    def test_semantic_conflict_and_escaped_review(self):
        args=fixture(); args[2]['records'][0]['semantic']='body.leg'
        self.assertIsNone(build(*args)['records'][0]['mesh'])
        args=fixture(); doc=build(*args); doc['project_id']='<script>bad()</script>'
        page=render(doc,args[1])
        self.assertNotIn('<script>bad()',page)
        self.assertIn('foot_l_-90',page)
