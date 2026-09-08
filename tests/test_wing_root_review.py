"""Source-exact reversible drafts and rigid preview transforms."""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from PIL import Image
from autospine_workbench.benchmark.wing_root_draft import initial,validate
from autospine_workbench.benchmark.wing_preview_parts import partition
from autospine_workbench.benchmark.wing_root_review_script import SCRIPT


def roots():
    return {'authority':'none','production_authorized':False,'rows':[{'components':[
      {'component_id':0,'roots':[{'source_xy':[10,0]},{'source_xy':[12,0]}]},
      {'component_id':1,'roots':[]}]}]}


class ReviewTests(unittest.TestCase):
    def test_full_draft_schema_and_unknown_choices(self):
        source=roots();doc=initial(source);before=deepcopy(source)
        doc['records'][0]['root_index']=1
        self.assertEqual(validate(source,doc),doc);self.assertEqual(source,before)
        import jsonschema
        jsonschema.validate(doc,json.loads(Path('schemas/wing-root-draft-v1.schema.json').read_text('utf-8')))
        for change in (lambda d:d.update(production_authorized=0),lambda d:d['records'][0].update(root_index=True),
          lambda d:d['records'][1].update(root_index=0),lambda d:d['records'].pop(),
          lambda d:d.update(source_roots_sha256='0'*64),lambda d:d['records'][0].update(component_id=False)):
            bad=deepcopy(doc);change(bad)
            with self.assertRaises(ValueError):validate(source,bad)

    def test_setup_keeps_low_alpha_and_component_pixels(self):
        image=Image.new('RGBA',(4,4),(20,30,40,255));image.putpixel((0,0),(80,90,100,4))
        out=BytesIO();image.save(out,format='PNG');raw=out.getvalue()
        layer={'bbox':[0,0,4,4],'image_sha256':sha256(raw).hexdigest()}
        parts,residual=partition(layer,raw,[{'component_id':0,'area_pixels':15,'roots':[{}]}])
        with Image.open(BytesIO(residual)) as r,Image.open(BytesIO(parts[0])) as p:
            self.assertEqual(Image.alpha_composite(r,p).tobytes(),image.tobytes())
            self.assertEqual(r.getpixel((0,0)),image.getpixel((0,0)))
            self.assertEqual(p.getpixel((0,0))[3],0)

    def test_javascript_draft_guard_and_nested_pivot(self):
        node=shutil.which('node')
        if not node:self.skipTest('Node unavailable')
        code=SCRIPT+'\nconst roots='+json.dumps(roots())+';const base='+json.dumps(initial(roots()))+r''';
const assert=require('node:assert/strict');
const close=(a,b)=>a.forEach((v,i)=>assert.ok(Math.abs(v-b[i])<1e-8));
close(wingPoint([12,0],[10,0],[0,0],0,0),[12,0]);
close(wingPoint([10,0],[10,0],[0,0],30,90),[0,10]);
close(wingPoint([12,0],[10,0],[0,0],90,90),[-2,10]);
const doc=structuredClone(base);doc.records[0].root_index=1;
assert.deepEqual(validateWingDraft(roots,base,doc),doc);
for(const mutate of [d=>d.records[0].root_index=8,d=>d.records[1].root_index=0,
 d=>d.records[0].component_id=false,d=>d.production_authorized=true]){
 const bad=structuredClone(doc);mutate(bad);assert.throws(()=>validateWingDraft(roots,base,bad));}
'''
        result=subprocess.run([node,'-'],input=code,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
