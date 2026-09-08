"""Cross-language mask identity, bounded drafts and protection/erase semantics."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import unittest
from autospine_workbench.benchmark.wing_split_draft import initial,validate,rasterize
from autospine_workbench.benchmark.wing_split_script import CORE


def source():
    return dict(schema='autospine.wing-edge-preview/v1',authority='none',production_authorized=False,
      files={'editor/images/topwear.png':'a'*64},regions=[dict(id='topwear',setup_vertices_xy=[[10,20],[50,20],[50,40],[10,40]])])


class SplitTests(unittest.TestCase):
    def test_draft_source_and_bounds(self):
        s=source();draft=initial(s);draft['strokes']=[dict(mode='remove',radius=2,points=[[0,0],[39,19]])]
        before=deepcopy(draft);self.assertEqual(validate(s,draft),draft);self.assertEqual(before,draft)
        import jsonschema
        jsonschema.validate(draft,json.loads(Path('schemas/wing-split-draft-v1.schema.json').read_text()))
        for change in [lambda d:d.update(production_authorized=0),lambda d:d.update(source_preview_sha256='0'*64),
          lambda d:d['strokes'][0].update(radius=True),lambda d:d['strokes'][0].update(points=[[40,0]]),
          lambda d:d['strokes'][0].update(points=[[float('nan'),0]]),lambda d:d['strokes'][0].update(points=[[0,0]]*4097)]:
            bad=deepcopy(draft);change(bad)
            with self.assertRaises(ValueError):validate(s,bad)

    def test_brush_parity_and_keep_erase_order(self):
        s=source();doc=initial(s);doc['strokes']=[dict(mode='remove',radius=3,points=[[0,0],[20,9],[39,19]]),
          dict(mode='keep',radius=2,points=[[10,5],[20,5]]),dict(mode='erase',radius=1,points=[[15,5]])]
        result=rasterize(s,doc);self.assertEqual(result[5*40+10],2);self.assertEqual(result[5*40+15],0)
        script=CORE+'\nconst base='+json.dumps(initial(s))+';const doc='+json.dumps(doc)+r''';
const assert=require('node:assert/strict');assert.deepEqual(validateSplit(base,doc),doc);
for(const edit of [d=>d.production_authorized=0,d=>d.source_preview_sha256='0'.repeat(64),d=>d.strokes[0].radius=true,d=>d.strokes[0].points=[[40,0]]]){
 const bad=structuredClone(doc);edit(bad);assert.throws(()=>validateSplit(base,bad));}
process.stdout.write(JSON.stringify(Array.from(rasterSplit(doc))));'''
        run=subprocess.run(['node','-'],input=script,text=True,capture_output=True)
        self.assertEqual(run.returncode,0,run.stderr);self.assertEqual(bytes(json.loads(run.stdout)),result)
