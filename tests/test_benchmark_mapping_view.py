"""Review pages embed evidence and export drafts without assuming human approval."""
from copy import deepcopy
import hashlib
from html.parser import HTMLParser
import json
import re
import shutil
import subprocess
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from autospine_workbench.benchmark.mapping_view import render_mapping_review


PNG = bytes.fromhex("89504e470d0a1a0a") + b"synthetic-page-unit-test"


def candidate():
    return {
        "schema": "autospine.benchmark-mapping-candidate/v1",
        "authority": "none", "review_required": True,
        "png_source": {"path": "png/example.png", "sha256": hashlib.sha256(PNG).hexdigest(), "canvas": [10, 20]},
        "psd_source": {"path": "example.psd", "canvas": [20, 40]},
        "source_to_psd_transform": {"scale": [2, 2], "translation": [0, 0],
                                    "coordinate_system": "pixel_top_left_y_down"},
        "basis": "canvas_fit_hypothesis", "evidence": None,
    }


class PageParser(HTMLParser):
    def __init__(self, page):
        super().__init__()
        self.tags = []
        self.script_count = 0
        self.in_data = False
        self.data = ""
        self.feed(page)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags.append((tag, attrs))
        if tag == "script":
            self.script_count += 1
            self.in_data = attrs.get("id") == "candidate-data"

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_data = False

    def handle_data(self, data):
        if self.in_data:
            self.data += data


class MappingViewTests(unittest.TestCase):
    def test_self_contained_evidence_and_exact_candidate(self):
        original = candidate()
        before = deepcopy(original)
        page = render_mapping_review(original, PNG, PNG)
        parser = PageParser(page)
        self.assertEqual(json.loads(parser.data), original)
        self.assertEqual(original, before)
        images = [attrs for tag, attrs in parser.tags if tag == "img"]
        self.assertEqual(len(images), 2)
        self.assertTrue(all(image["src"].startswith("data:image/png;base64,") for image in images))
        self.assertFalse(any("src" in attrs for tag, attrs in parser.tags if tag == "script"))
        self.assertNotIn("fetch(", page)
        self.assertNotIn("XMLHttpRequest", page)
        self.assertIn("connect-src 'none'", page)
        self.assertIn("pixel_top_left_y_down", page)

    def test_untrusted_names_cannot_close_script_or_inject_elements(self):
        value = candidate()
        value["png_source"]["path"] = '</script><script>alert(1)</script><img src=x onerror="x">\u2028'
        value["psd_source"]["path"] = "__CANDIDATE_JSON__&<b>"
        parser = PageParser(render_mapping_review(value, PNG, PNG))
        self.assertEqual(parser.script_count, 2)
        self.assertEqual(sum(tag == "img" for tag, _ in parser.tags), 2)
        self.assertEqual(json.loads(parser.data), value)
        self.assertFalse(any("onerror" in attrs for _, attrs in parser.tags))

    def test_download_remains_a_non_authoritative_candidate(self):
        page = render_mapping_review(candidate(), PNG, PNG)
        self.assertIn("draft.basis = 'explicit_transform_draft'", page)
        self.assertIn("draft.authority = 'none'", page)
        self.assertIn("draft.review_required = true", page)
        self.assertIn("mapping-transform-draft.json", page)
        self.assertIn("URL.revokeObjectURL", page)
        self.assertIn("result.every(Number.isFinite)", page)
        self.assertNotIn("approved", page)
        self.assertNotIn("localStorage", page)

    def test_reject_authority_and_mismatched_evidence(self):
        value = candidate()
        value["authority"] = "human"
        with self.assertRaisesRegex(ValueError, "authority_invalid"):
            render_mapping_review(value, PNG, PNG)
        value = candidate()
        with self.assertRaisesRegex(ValueError, "source_changed"):
            render_mapping_review(value, PNG + b"changed", PNG)
        value["evidence"] = {"composite_sha256": "0" * 64}
        with self.assertRaisesRegex(ValueError, "composite_changed"):
            render_mapping_review(value, PNG, PNG)
        with self.assertRaisesRegex(ValueError, "png_required"):
            render_mapping_review(candidate(), PNG, b"not png")

    @unittest.skipUnless(shutil.which("node"), "Node is unavailable")
    def test_controls_download_and_reset_execute_without_network(self):
        page = render_mapping_review(candidate(), PNG, PNG)
        script = re.findall(r"<script>(.*?)</script>", page, flags=re.S)[0]
        harness = r'''
const assert = require('node:assert/strict'), vm = require('node:vm');
const nodes = {}, transforms = []; let downloaded;
const context = {setTransform:(...args)=>transforms.push(args),clearRect(){},drawImage(){}};
for (const id of ['source','composite','overlay','sx','sy','tx','ty','opacity','status','download','reset']) {
  nodes[id] = {value:'',complete:true,naturalWidth:10,listeners:{},
    addEventListener(event,callback){this.listeners[event]=callback},getContext(){return context}};
  Object.defineProperty(nodes[id],'value',{get(){return this._value || ''},set(value){this._value=String(value)}});
}
nodes['candidate-data'] = {textContent:JSON.stringify(INPUT)};
const sandbox = {document:{getElementById:id=>nodes[id],body:{appendChild(){}},
  createElement:()=>({click(){},remove(){}})},URL:{createObjectURL:blob=>{downloaded=blob;return 'blob:local'},revokeObjectURL(){}},
  Blob:class{constructor(parts){this.text=parts.join('')}},setTimeout:callback=>callback()};
vm.runInNewContext(SCRIPT,sandbox);
assert.equal(nodes.sx.value,'2');
nodes.sx.value='1.25';nodes.sy.value='1.5';nodes.tx.value='12';nodes.ty.value='-3';
nodes.sx.listeners.input();
assert.deepEqual(transforms.at(-2),[1.25,0,0,1.5,12,-3]);
nodes.download.listeners.click();
const draft=JSON.parse(downloaded.text);
assert.deepEqual(draft.source_to_psd_transform.scale,[1.25,1.5]);
assert.deepEqual(draft.source_to_psd_transform.translation,[12,-3]);
assert.equal(draft.authority,'none');assert.equal(draft.review_required,true);
assert.equal(draft.basis,'explicit_transform_draft');
nodes.sx.value='Infinity';nodes.sx.listeners.input();assert.equal(nodes.download.disabled,true);
nodes.sx.value='0';nodes.sx.listeners.input();assert.equal(nodes.download.disabled,true);
nodes.sx.value='1e308';nodes.sx.listeners.input();assert.equal(nodes.download.disabled,true);
nodes.sx.value='5e-324';nodes.sx.listeners.input();assert.equal(nodes.download.disabled,true);
nodes.sx.value='-1.25';nodes.sx.listeners.input();assert.equal(nodes.download.disabled,false);
nodes.download.listeners.click();assert.equal(JSON.parse(downloaded.text).source_to_psd_transform.scale[0],-1.25);
nodes.reset.listeners.click();assert.equal(nodes.sx.value,'2');assert.equal(nodes.tx.value,'0');
assert.equal(nodes.download.disabled,false);
'''
        harness = "const INPUT=" + json.dumps(candidate()) + ";const SCRIPT=" + json.dumps(script) + ";\n" + harness
        result = subprocess.run([shutil.which("node"), "-e", harness], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
