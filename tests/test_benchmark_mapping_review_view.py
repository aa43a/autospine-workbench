"""Offline review requests require explicit checks and bind the displayed candidate."""

import json
import shutil
import subprocess
import unittest

from tests.test_benchmark_mapping_view import PNG, PageParser, candidate
from autospine_workbench.benchmark.mapping_review_view import REVIEW_SCRIPT, render_review_controls
from autospine_workbench.benchmark.mapping_view import render_mapping_review
from autospine_workbench.resolved_project import canonical_sha256


HARNESS = r'''
const assert = require('node:assert/strict'), vm = require('node:vm');
const nodes = {}; let downloaded;
const ids = ['review-binding','review-choice','reviewer','review-reason','review-status','review-download',
  'review-same-character','review-coordinate-alignment','review-mirror-checked','sx','sy','tx','ty',
  'source','composite','reset'];
for (const id of ids) nodes[id] = {value:'',checked:false,complete:true,naturalWidth:10,listeners:{},
  addEventListener(event,callback){(this.listeners[event] ||= []).push(callback)}};
nodes['review-binding'].dataset = {candidateSha:SHA};
const fields = ['sx','sy','tx','ty'].map(id=>nodes[id]);
[2,2,0,0].forEach((value,index)=>fields[index].value=String(value));
const sandbox = {candidate:INPUT,fields,source:nodes.source,composite:nodes.composite,
  values(){const v=fields.map(field=>Number(field.value));return v.every(Number.isFinite)&&v[0]&&v[1]?v:null},
  document:{getElementById:id=>nodes[id],body:{appendChild(){}},createElement:()=>({click(){},remove(){}})},
  URL:{createObjectURL:blob=>{downloaded=blob;return 'blob:local'},revokeObjectURL(){}},
  Blob:class{constructor(parts){this.text=parts.join('')}},setTimeout:callback=>callback()};
vm.runInNewContext(SCRIPT,sandbox);
function emit(id,event='input'){for(const callback of nodes[id].listeners[event]||[]) callback()}
function ready(){nodes['review-choice'].value='accept';nodes.reviewer.value='测试复核人';
  nodes['review-reason'].value='同一素材，轮廓与镜像已核对';
  for(const id of ['review-same-character','review-coordinate-alignment','review-mirror-checked']) nodes[id].checked=true;
  emit('review-choice');}
'''


class MappingReviewRequestViewTests(unittest.TestCase):
    def run_script(self, assertions):
        if not shutil.which('node'):
            self.skipTest('Node is unavailable')
        prefix = 'const INPUT=' + json.dumps(candidate()) + ';const SHA=' + json.dumps(canonical_sha256(candidate()))
        prefix += ';const SCRIPT=' + json.dumps(REVIEW_SCRIPT) + ';\n'
        result = subprocess.run([shutil.which('node'), '-e', prefix + HARNESS + assertions],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_default_is_no_selection_and_no_request(self):
        self.run_script("""
assert.equal(nodes['review-choice'].value,'');assert.equal(nodes['review-download'].disabled,true);
emit('review-download','click');assert.equal(downloaded,undefined);
""")

    def test_accept_requires_reviewer_reason_and_all_checks(self):
        self.run_script("""
ready();assert.equal(nodes['review-download'].disabled,false);
for(const id of ['review-same-character','review-coordinate-alignment','review-mirror-checked']) {
  nodes[id].checked=false;emit(id);assert.equal(nodes['review-download'].disabled,true);
  nodes[id].checked=true;emit(id);
}
for(const id of ['reviewer','review-reason']) {
  const previous=nodes[id].value;
  for(const bad of ['','   ','invisible\\u200b','control\\u0001']) {
    nodes[id].value=bad;emit(id);assert.equal(nodes['review-download'].disabled,true);
  }
  nodes[id].value=previous;emit(id);
}
assert.equal(nodes['review-download'].disabled,false);
nodes.source.complete=false;emit('source','error');assert.equal(nodes['review-download'].disabled,true);
""")

    def test_source_bound_request_has_no_decision_authority(self):
        self.run_script("""
ready();emit('review-download','click');const request=JSON.parse(downloaded.text);
assert.equal(request.candidate_sha256,SHA);assert.equal(request.action,'accept');
assert.equal(request.authority,'none');assert.equal(request.schema,'autospine.benchmark-mapping-review-request/v1');
assert.deepEqual(request.checks,{same_character:true,coordinate_alignment:true,mirror_checked:true});
assert.equal(Object.hasOwn(request,'decision_source'),false);
""")

    def test_changed_transform_blocks_accept_but_allows_reasoned_reject(self):
        self.run_script("""
ready();nodes.tx.value='30';emit('tx');assert.equal(nodes['review-download'].disabled,true);
emit('review-download','click');assert.equal(downloaded,undefined);
nodes['review-choice'].value='reject';emit('review-choice');assert.equal(nodes['review-download'].disabled,false);
emit('review-download','click');assert.equal(JSON.parse(downloaded.text).action,'reject');
assert.equal(JSON.parse(downloaded.text).candidate_sha256,SHA);
nodes['review-choice'].value='accept';nodes.tx.value='0';emit('reset','click');
assert.equal(nodes['review-download'].disabled,false);
nodes.sy.value='Infinity';emit('sy');assert.equal(nodes['review-download'].disabled,true);
""")

    def test_user_text_is_json_only_and_does_not_reach_html(self):
        self.run_script("""
ready();nodes.reviewer.value='<img src=x onerror=alert(1)>';
nodes['review-reason'].value='</script><script>alert(1)</script>';emit('reviewer');
emit('review-download','click');const request=JSON.parse(downloaded.text);
assert.equal(request.reviewer,nodes.reviewer.value);assert.equal(request.reason,nodes['review-reason'].value);
assert.equal(Object.values(nodes).some(node=>Object.hasOwn(node,'innerHTML')),false);
""")

    def test_markup_uses_exact_digest_and_unselected_checkboxes(self):
        original = candidate()
        controls = render_review_controls(original)
        parser = PageParser(controls)
        self.assertIn(canonical_sha256(original), controls)
        self.assertFalse(any('selected' in attrs or 'checked' in attrs for _, attrs in parser.tags))
        page = render_mapping_review(original, PNG, PNG)
        self.assertNotIn('__REVIEW_', page)
        self.assertIn('下载复核请求', page)
        self.assertIn('修改变换不会重新计算误差', page)


if __name__ == '__main__':
    unittest.main()
