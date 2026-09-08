import math
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import unittest
from PIL import Image,ImageDraw
from autospine_workbench.asset.planning.wing_pendants import analyze
from autospine_workbench.asset.planning.wing_edge_ownership import encode,decode
from autospine_workbench.benchmark.wing_spine_preview import encode as document
from autospine_workbench.benchmark.wing_pendant_preview import build,verify
from autospine_workbench.targets.spine43.continuous_pose import world


def assets():
    donor=Image.new('RGBA',(50,60),(255,255,255,255));ImageDraw.Draw(donor).rectangle((10,20,21,43),fill=(70,130,220,255));donor.putpixel((16,30),(255,255,255,255))
    wing=Image.new('RGBA',donor.size);wing.putpixel((16,19),(20,30,40,255))
    return encode(donor),encode(wing)


class PendantTests(unittest.TestCase):
    def test_background_white_highlight_and_unique_mount(self):
        donor,wing=assets();inputs=(donor,[0,0],{'wing-c0':wing},{'wing-c0':[0,0]});before=deepcopy(inputs)
        images,residual,report=analyze(*inputs);row=report['rows'][0]
        self.assertEqual(inputs,before);self.assertEqual(row['visible_pixels'],288)
        self.assertEqual(row['mount_candidates'][0]['distance_px'],1);self.assertEqual(row['parent'],'wing-c0')
        self.assertEqual(decode(images[row['id']]).getpixel((6,10)),(255,255,255,255))
        self.assertEqual(report['residual_visible_pixels'],3000-288)
        rebuilt=decode(residual);rebuilt.alpha_composite(decode(images[row['id']]),(10,20))
        self.assertEqual(rebuilt.tobytes(),decode(donor).tobytes())
        self.assertEqual(analyze(*inputs),(images,residual,report))

    def test_mount_tie_and_distant_tip_block(self):
        donor,wing=assets()
        _,_,report=analyze(donor,[0,0],{'a':wing,'b':wing},{'a':[0,0],'b':[0,0]})
        self.assertIsNone(report['rows'][0]['parent']);self.assertEqual(report['rows'][0]['status'],'blocked')
        _,_,report=analyze(donor,[0,0],{'a':wing},{'a':[100,0]})
        self.assertIsNone(report['rows'][0]['parent'])

    def test_new_child_pivot_existing_motion_and_bundle_identity(self):
        donor,wing=assets();bones=[dict(name='root',x=0,y=0,rotation=0),dict(name='wing-c0',parent='root',x=0,y=0,rotation=0)]
        attachments={};slots=[];regions=[]
        for name,index in [('wing-c0',1),('topwear',0)]:
            points=[[0,0],[50,0],[50,60],[0,60]];vertices=[]
            for x,y in points:vertices.extend([1,index,x,-y,1])
            attachments[name]={name:dict(type='mesh',path=name,uvs=[0,0,1,0,1,1,0,1],triangles=[0,1,2,0,2,3],vertices=vertices,width=50,height=60)}
            slots.append(dict(name=name,bone=bones[index]['name'],attachment=name));regions.append(dict(id=name,setup_vertices_xy=points))
        doc=dict(skeleton={'spine':'4.3.26'},bones=bones,slots=slots,skins=[dict(name='default',attachments=attachments)],animations={'wing-root-inspection':{'bones':{'wing-c0':{'rotate':[dict(time=i*.5,value=v) for i,v in enumerate([0,-10,0,10,0])]}}}})
        files={'skeleton.json':document(doc),'editor/skeleton.json':document(doc),'skeleton.atlas':b'',
          'editor/images/wing-c0.png':wing,'editor/images/topwear.png':wing,'color/unassigned.png':donor,'README.txt':b''}
        source=dict(schema='autospine.wing-color-preview/v1',authority='none',production_authorized=False,regions=regions,files={n:sha256(raw).hexdigest() for n,raw in files.items()})
        report,outputs=build(source,files);result=json.loads(outputs['skeleton.json']);self.assertEqual(report['mounted_pendants'],['pendant-0'])
        self.assertEqual(outputs['editor/images/wing-c0.png'],wing)
        self.assertEqual([s['name'] for s in result['slots']],['wing-c0','pendant-0','topwear'])
        points=world(result,.5)['pendant-0'];pivot=[(a+b)/2 for a,b in zip(points[0],points[1])];r=math.radians(-10)
        expected=[16*math.cos(r)+20*math.sin(r),16*math.sin(r)-20*math.cos(r)]
        for a,b in zip(pivot,expected):self.assertAlmostEqual(a,b,places=8)
        self.assertEqual(verify(report,source,files),report)
        import jsonschema
        jsonschema.validate(report,json.loads(Path('schemas/wing-pendant-preview-v1.schema.json').read_text()))
        bad=deepcopy(report);bad['mounted_pendants']=[]
        with self.assertRaises(ValueError):verify(bad,source,files)
