"""Selected hinges preserve setup, parent transforms, source identity and loop."""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
import math
from pathlib import Path
import unittest
from PIL import Image
from autospine_workbench.benchmark.wing_root_draft import initial
from autospine_workbench.benchmark.wing_spine_preview import build,verify_report
from autospine_workbench.targets.spine43.continuous_pose import world


class WingSpineTests(unittest.TestCase):
    def fixture(self):
        image=Image.new('RGBA',(4,4),(80,100,120,255));out=BytesIO();image.save(out,format='PNG')
        raw=out.getvalue();layers=[dict(layer_id=n,bbox=[10,20,14,24],image_sha256=sha256(raw).hexdigest()) for n in ['wing','shirt']]
        roots=dict(authority='none',production_authorized=False,rows=[dict(layer_id='wing',target_layer_id='shirt',
          anchor_xy=[0,0],components=[dict(component_id=0,area_pixels=16,roots=[dict(source_xy=[10,20]),dict(source_xy=[14,24])])])])
        draft=initial(roots);draft['records'][0]['root_index']=0
        return roots,dict(layers=layers),{'wing':raw,'shirt':raw},draft

    def test_selected_root_parent_follow_and_loop(self):
        args=self.fixture();before=deepcopy(args);report,files=build(*args)
        self.assertEqual(args,before)
        doc=json.loads(files['skeleton.json']);setup=world(doc,0)
        self.assertEqual(setup['wing-c0'],[[10,-20],[14,-20],[14,-24],[10,-24]])
        # The top-left vertex coincides with the selected hinge: local flap must not move it.
        actual=world(doc,.5)['wing-c0'][0];angle=math.radians(-10)
        expected=[10*math.cos(angle)+20*math.sin(angle),10*math.sin(angle)-20*math.cos(angle)]
        for a,b in zip(actual,expected):self.assertAlmostEqual(a,b,places=9)
        self.assertEqual(world(doc,2),setup)
        self.assertTrue(all(r['passed'] for r in report['geometry']['regions'].values()))
        self.assertFalse(report['production_authorized'])
        for name,digest in report['files'].items():self.assertEqual(sha256(files[name]).hexdigest(),digest)
        self.assertEqual(build(*args)[1],files)
        import jsonschema
        jsonschema.validate(report,json.loads(Path('schemas/wing-spine-preview-v1.schema.json').read_text()))
        self.assertEqual(verify_report(report,*args),report)
        bad=deepcopy(report);bad['production_authorized']=True
        with self.assertRaises(ValueError):verify_report(bad,*args)

    def test_unselected_has_no_local_bone_and_tampering_fails(self):
        roots,candidate,images,draft=self.fixture();draft['records'][0]['root_index']=None
        report,files=build(roots,candidate,images,draft)
        self.assertEqual(report['selected_roots'],[])
        self.assertEqual(len(json.loads(files['skeleton.json'])['bones']),2)
        changed=deepcopy(draft);changed['source_roots_sha256']='0'*64
        with self.assertRaises(ValueError):build(roots,candidate,images,changed)
        images['shirt']=b'changed'
        with self.assertRaises(ValueError):build(roots,candidate,images,draft)
