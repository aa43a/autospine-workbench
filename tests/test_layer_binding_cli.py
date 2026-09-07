"""V2 source replay, editable chain selections and v1 compatibility."""
import json
import shutil
import subprocess
import unittest

from tests import test_region_binding_cli as fixtures
from tests.test_layer_binding import fixture
from autospine_workbench.asset.joints.layer_binding import build_layer_bindings
from autospine_workbench.benchmark.layer_binding_draft import build_layer_binding_draft
from autospine_workbench.benchmark.layer_binding_controls import SCRIPT
from autospine_workbench.benchmark.layer_binding_cli import read_layer_bindings, read_layer_binding_draft
from autospine_workbench.benchmark.__main__ import parser, _execute
from autospine_workbench.resolved_project import canonical_sha256


class LayerBindingCliTests(unittest.TestCase):
    def test_replay_draft_restore_and_source_tamper(self):
        f=fixtures.RegionBindingCliTests(); f.setUp(); self.addCleanup(f.doCleanups)
        old=f.build()[0]
        args=['--state-root',f.f.state,'build-layer-bindings','--manifest',f.f.root/'manifest.json',
              '--workspace',f.f.root,'--skeleton',f.f.root/'skeleton.json','--html',f.f.root/'v2.html',
              '--draft-output',f.f.root/'v2-draft.json']
        parsed=parser().parse_args(list(map(str,args)))
        result=_execute(parsed); self.assertEqual(_execute(parsed),result)
        doc=result[0]
        self.assertEqual(read_layer_bindings(f.f.state,f.f.manifest,canonical_sha256(doc),workspace=f.f.root),doc)
        draft=json.loads((f.f.root/'v2-draft.json').read_text('utf-8'))
        draft['records'][0].update(action='semantic_review',notes='Synthetic review')
        source=f.f.root/'edited-v2.json';source.write_text(json.dumps(draft),encoding='utf-8')
        parsed.draft=source;parsed.html=f.f.root/'restored-v2.html';parsed.draft_output=None
        self.assertEqual(_execute(parsed)[0],doc)
        self.assertEqual(read_layer_binding_draft(f.f.state,f.f.manifest,canonical_sha256(draft),workspace=f.f.root),draft)
        from autospine_workbench.benchmark.region_binding_cli import read_region_bindings
        self.assertEqual(read_region_bindings(f.f.state,f.f.manifest,canonical_sha256(old),workspace=f.f.root),old)
        (f.f.root/'layer-0.png').write_bytes(b'changed')
        with self.assertRaises(ValueError):
            read_layer_binding_draft(f.f.state,f.f.manifest,canonical_sha256(draft),workspace=f.f.root)

    def test_browser_chain_selection_validation(self):
        node=shutil.which('node')
        if not node:self.skipTest('node unavailable')
        doc=build_layer_bindings(*fixture());base=build_layer_binding_draft(doc)
        program=SCRIPT+'\nconst bindings='+json.dumps(doc)+';const base='+json.dumps(base)+r''';
const assert=require('node:assert/strict');
const d=structuredClone(base);
const i=bindings.bindings.findIndex(r=>r.options.some(o=>o.mode==='mesh_chain'));
assert.ok(i>=0);
const option=bindings.bindings[i].options.find(o=>o.mode==='mesh_chain');
d.records[i].action='bind';d.records[i].option_id=option.id;
assert.equal(validateLayerDraft(bindings,base,d).records[i].option_id,option.id);
assert.equal(option.bone_ids.length,3);
for(const mutate of [v=>v.records[i].option_id='unknown',v=>v.schema='autospine.region-binding-draft/v1',
v=>v.records[i].weights=[1],v=>v.source_bindings_sha256='0'.repeat(64)]) {
const bad=structuredClone(d);mutate(bad);assert.throws(()=>validateLayerDraft(bindings,base,bad));}
assert.ok(base.records.every(r=>r.action==='pending'));
'''
        result=subprocess.run([node,'-'],input=program,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
