"""Review downloads require explicit declarations for the frozen visible draft."""
from copy import deepcopy
import json
import re
import shutil
import subprocess
import unittest

from tests.test_benchmark_semantic_view import candidate, PNG, Parser
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.benchmark.semantic_draft import build_semantic_draft
from autospine_workbench.benchmark.semantic_view import render_semantic_review


class SemanticReviewViewTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node required for UI state transitions")
    def test_frozen_reverse_order_unicode_draft_review_and_invalidation(self):
        value = candidate()
        second = deepcopy(value["layers"][0]); second["layer_id"] = "layer-001"
        value["layers"].append(second)
        draft = build_semantic_draft(value)
        for row in draft["records"]:
            row.update(semantic="body.arm.lower", side="left", disposition="include", notes="待复核角色😀")
        draft["records"].reverse()
        page = render_semantic_review(value, PNG, {row["layer_id"]: PNG for row in value["layers"]}, draft=draft)
        data = json.loads(Parser(page).data)
        script = re.findall(r'<script>(.*?)</script>', page, re.S)[0]
        harness = r'''
const assert=require('node:assert/strict'), vm=require('node:vm');
const nodes={}; let downloaded;
function node(id){return nodes[id] || (nodes[id]={value:'',checked:false,files:[],listeners:{},dataset:{},
  addEventListener(name,fn){(this.listeners[name] ||= []).push(fn)},
  dispatchEvent(event){for(const fn of this.listeners[event.type] || [])fn(event)}})}
async function emit(id,name){for(const fn of node(id).listeners[name] || [])await fn({type:name})}
node('semantic-data').textContent=JSON.stringify(INPUT);
node('semantic-review-binding').dataset.draftSha=SHA;
const images=[{complete:true,naturalWidth:100,addEventListener(){}}];
const sandbox={document:{getElementById:node,querySelectorAll:()=>images,body:{appendChild(){}},
  createElement:()=>({click(){},remove(){}})},Event:class{constructor(type){this.type=type}},
  URL:{createObjectURL:blob=>{downloaded=blob;return 'blob:local'},revokeObjectURL(){}},
  Blob:class{constructor(parts){this.text=parts.join('')}},setTimeout:fn=>fn()};
vm.runInNewContext(SCRIPT,sandbox);
(async()=>{
  assert.equal(node('semantic-review-download').disabled,true);
  node('semantic-choice').value='accept'; node('semantic-reviewer').value='人工';
  node('semantic-reason').value='逐层检查测试';
  for(const id of ['identity','semantics','sides'])node('semantic-check-'+id).checked=true;
  await emit('semantic-choice','input'); assert.equal(node('semantic-review-download').disabled,false);
  await emit('semantic-review-download','click');
  const result=JSON.parse(downloaded.text);assert.equal(result.draft_sha256,SHA);
  assert.equal(result.candidate_sha256,INPUT.candidate_sha256);assert.equal(result.authority,'none');
  node('notes-0').value='修改'; await emit('notes-0','input');
  assert.equal(node('semantic-review-download').disabled,true);
  node('semantic-choice').value='reject'; await emit('semantic-choice','input');
  assert.equal(node('semantic-review-download').disabled,true);
  node('restore').files=[{size:1000,text:async()=>JSON.stringify(INPUT.draft)}];
  await emit('restore','change');assert.equal(node('semantic-review-download').disabled,false);
  node('semantic-choice').value='accept';images[0].naturalWidth=0;await emit('semantic-choice','input');
  assert.equal(node('semantic-review-download').disabled,true);
  images[0].naturalWidth=100;node('semantic-check-sides').checked=false;await emit('semantic-choice','input');
  assert.equal(node('semantic-review-download').disabled,true);
})().catch(error=>{console.error(error);process.exitCode=1});
'''
        prefix = 'const INPUT=' + json.dumps(data) + ';const SHA=' + json.dumps(canonical_sha256(draft)) \
            + ';const SCRIPT=' + json.dumps(script) + ';'
        result = subprocess.run([shutil.which("node"), "-e", prefix + harness],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
