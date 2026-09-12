import importlib.util
from io import BytesIO
import json
import unittest
from autospine_workbench.targets.character43.residual_mesh_support import inspect


@unittest.skipUnless(importlib.util.find_spec('PIL'), 'optional image analysis')
class ResidualSupportTests(unittest.TestCase):
    def fixture(self,duplicate=False):
        from PIL import Image
        def mesh(points):
            return dict(type='mesh',uvs=[0,0,1,0,1,1,0,1],triangles=[0,1,2,0,2,3],
                        vertices=[v for x,y in points for v in (1,0,x,y,1)])
        attachments={'rest':{'rest':mesh([[10,20],[12,20],[12,22],[10,22]])},
                     'bound':{'bound':mesh([[10,20],[11,20],[11,22],[10,22]])}}
        regions=[dict(region_id='rest',state='static_reference'),dict(region_id='bound',state='weighted_candidate')]
        if duplicate:
            attachments['other']={'other':attachments['bound']['bound']}
            regions.append(dict(region_id='other',state='weighted_candidate'))
        doc=dict(bones=[dict(name='root',x=30,y=40,rotation=25)],skins=[dict(attachments=attachments)],
                 animations={'move':{'bones':{'root':{'rotate':[{'time':0,'value':90}]}}}})
        stream=BytesIO();Image.new('RGBA',(2,2),(100,50,20,3)).save(stream,format='PNG')
        return {'skeleton.json':json.dumps(doc).encode(),
                'character-manifest.json':json.dumps({'layers':[dict(layer_id='source',regions=regions)]}).encode(),
                'images/rest.png':stream.getvalue()}

    def test_canvas_offset_and_rotation_do_not_change_pixel_support(self):
        files=self.fixture();report=inspect(files)
        self.assertEqual(report['rows'][0]['counts'],dict(unique_mesh_support=2,ambiguous_mesh_support=0,outside_mesh=2))
        self.assertEqual(report['rows'][0]['records'][0]['pixel_xy'],[0,0])
        self.assertFalse(report['selected'])
        doc=json.loads(files['skeleton.json']);doc['bones'][0].update(x=-100,y=-300,rotation=-80)
        doc['animations']['move']={};files['skeleton.json']=json.dumps(doc).encode()
        self.assertEqual(inspect(files)['rows'],report['rows'])

    def test_multiple_owners_and_unsupported_uv_remain_explicit(self):
        files=self.fixture(True);report=inspect(files)
        self.assertEqual(report['rows'][0]['counts']['ambiguous_mesh_support'],2)
        doc=json.loads(files['skeleton.json']);doc['skins'][0]['attachments']['rest']['rest']['uvs'][0]=.1
        files['skeleton.json']=json.dumps(doc).encode()
        with self.assertRaisesRegex(ValueError,'quad_required'):inspect(files)
