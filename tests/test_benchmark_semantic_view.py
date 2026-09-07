"""Offline layer drafts preserve evidence identity and never adopt suggestions."""
from copy import deepcopy
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from autospine_workbench.benchmark.semantic_draft import build_semantic_draft
from autospine_workbench.benchmark.semantic_view import render_semantic_review

PNG = bytes.fromhex('89504e470d0a1a0a') + b'page-only-fixture-not-a-raster-test'
SHA = hashlib.sha256(PNG).hexdigest()


def candidate():
    return {"schema": "autospine.benchmark-semantic-candidates/v1", "authority": "none", "review_required": True,
            "canvas": [100, 100], "composite_sha256": SHA, "layers": [
                {"layer_id": "layer-000", "name": "forearm-l", "bbox": [10, 20, 30, 50],
                 "image_sha256": SHA, "image": {"byte_size": len(PNG)}, "semantic": "body.arm.lower",
                 "raw_name_side": "l", "review_required": True,
                 "observed": {"empty": False, "visible": True, "alpha_nonzero": 100},
                 "reason_codes": ["exact_name_alias", "canonical_side_requires_review"]}]}


class Parser(HTMLParser):
    def __init__(self, page):
        super().__init__()
        self.tags = []
        self.data = ''
        self.in_data = False
        self.feed(page)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags.append((tag, attrs))
        if tag == 'script':
            self.in_data = attrs.get('id') == 'semantic-data'

    def handle_endtag(self, tag):
        if tag == 'script':
            self.in_data = False

    def handle_data(self, data):
        if self.in_data:
            self.data += data


class SemanticViewTests(unittest.TestCase):
    def render(self, value=None, **kwargs):
        return render_semantic_review(value or candidate(), PNG, {'layer-000': PNG}, **kwargs)

    def test_embedded_images_unset_annotations_and_no_network(self):
        value = candidate()
        before = deepcopy(value)
        page = self.render(value)
        parser = Parser(page)
        data = json.loads(parser.data)
        self.assertEqual(data['draft'], build_semantic_draft(value))
        row = data['draft']['records'][0]
        self.assertIsNone(row['semantic'])
        self.assertEqual(row['side'], 'unknown')
        self.assertEqual(row['disposition'], 'undecided')
        self.assertEqual(value, before)
        images = [attrs for tag, attrs in parser.tags if tag == 'img']
        self.assertEqual(len(images), 2)
        self.assertTrue(all(image['src'].startswith('data:image/png;base64,') for image in images))
        self.assertFalse(any('src' in attrs for tag, attrs in parser.tags if tag == 'script'))
        self.assertIn("connect-src 'none'", page)
        for forbidden in ('fetch(', 'XMLHttpRequest', 'localStorage', 'approved'):
            self.assertNotIn(forbidden, page)

    def test_untrusted_layer_names_and_reasons_are_escaped(self):
        value = candidate()
        value['layers'][0]['name'] = '</script><img src=x onerror="alert(1)">\u2028'
        value['layers'][0]['reason_codes'] = ['</p><script>alert(1)</script>', '__DATA__']
        parser = Parser(self.render(value))
        self.assertEqual(sum(tag == 'script' for tag, _ in parser.tags), 2)
        self.assertEqual(sum(tag == 'img' for tag, _ in parser.tags), 2)
        self.assertFalse(any('onerror' in attrs for _, attrs in parser.tags))
        self.assertIn('__DATA__', self.render(value))

    def test_changed_image_or_authority_rejected(self):
        with self.assertRaisesRegex(ValueError, 'image_changed'):
            render_semantic_review(candidate(), PNG + b'x', {'layer-000': PNG})
        with self.assertRaisesRegex(ValueError, 'image_changed'):
            render_semantic_review(candidate(), PNG, {'layer-000': PNG + b'x'})
        with self.assertRaisesRegex(ValueError, 'images_invalid'):
            render_semantic_review(candidate(), PNG, {})
        value = candidate()
        value['authority'] = 'human'
        with self.assertRaisesRegex(ValueError, 'authority_invalid'):
            self.render(value)

    def test_server_restore_requires_exact_candidate(self):
        value = candidate()
        draft = build_semantic_draft(value)
        draft['records'][0].update(semantic='body.arm.lower', side='left', disposition='include', notes='需要复核')
        self.assertEqual(json.loads(Parser(self.render(value, draft=draft)).data)['draft'], draft)
        draft['candidate_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            self.render(value, draft=draft)

    @unittest.skipUnless(shutil.which('node'), 'Node is unavailable')
    def test_browser_edits_download_restoration_and_rejection_are_atomic(self):
        page = self.render()
        data = json.loads(Parser(page).data)
        script = re.findall(r'<script>(.*?)</script>', page, flags=re.S)[0]
        harness = r'''
const assert = require('node:assert/strict'), vm = require('node:vm');
const nodes = {}; let downloaded;
for (const id of ['status','download','restore','semantic-0','side-0','disposition-0','notes-0']) {
  nodes[id] = {value:'',listeners:{},files:[],addEventListener(name,fn){this.listeners[name]=fn;}};
}
nodes['semantic-data'] = {textContent:JSON.stringify(INPUT)};
const sandbox = {document:{getElementById:id=>nodes[id],body:{appendChild(){}},
  createElement:()=>({click(){},remove(){}})},URL:{createObjectURL:blob=>{downloaded=blob;return 'blob:local'},revokeObjectURL(){}},
  Blob:class{constructor(parts){this.text=parts.join('')}},setTimeout:fn=>fn()};
vm.runInNewContext(SCRIPT,sandbox);
assert.equal(nodes['semantic-0'].value,'');assert.equal(nodes['side-0'].value,'unknown');
assert.equal(nodes['disposition-0'].value,'undecided');
nodes['semantic-0'].value='body.arm.lower';nodes['side-0'].value='left';
nodes['disposition-0'].value='include';nodes['notes-0'].value='review later';
nodes['notes-0'].listeners.input();nodes.download.listeners.click();
const draft=JSON.parse(downloaded.text);
assert.equal(draft.authority,'none');assert.equal(draft.records[0].side,'left');
assert.equal(draft.records[0].semantic,'body.arm.lower');assert.equal(draft.records[0].disposition,'include');
async function restore(value) {
  const raw=JSON.stringify(value);nodes.restore.files=[{size:raw.length,text:async()=>raw}];
  await nodes.restore.listeners.change();
}
(async()=>{
  draft.records[0].side='right';await restore(draft);assert.equal(nodes['side-0'].value,'right');
  const invalids = [
    value=>{value.authority='human'}, value=>{value.candidate_sha256='0'.repeat(64)},
    value=>{value.records.push({...value.records[0]})}, value=>{value.records[0].semantic='fake'},
    value=>{value.records[0].notes='\u200b'}, value=>{value.records[0].notes='x'.repeat(1001)},
    value=>{value.records[0].layer_id='missing'}, value=>{value.extra='authority'},
    value=>{value.records[0].decision_source='human'}, value=>{value.records[0].side='screen_left'},
    value=>{value.records[0].disposition='accepted'}];
  for(const change of invalids){const value=JSON.parse(JSON.stringify(draft));change(value);await restore(value);
    assert.equal(nodes['side-0'].value,'right');assert.match(nodes.status.textContent,/恢复失败/);}
  nodes['notes-0'].value='\u0001';nodes['notes-0'].listeners.input();assert.equal(nodes.download.disabled,true);
  nodes['notes-0'].value='safe';nodes['notes-0'].listeners.input();assert.equal(nodes.download.disabled,false);
  nodes.download.listeners.click();assert.equal(JSON.parse(downloaded.text).authority,'none');
})().catch(error=>{console.error(error);process.exitCode=1});
'''
        result = subprocess.run([shutil.which('node'), '-e',
                                 'const INPUT=' + json.dumps(data) + ';const SCRIPT=' + json.dumps(script) + ';' + harness],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
