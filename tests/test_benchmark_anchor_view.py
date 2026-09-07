"""Anchor input maps browser image geometry to immutable source coordinates."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from autospine_workbench.benchmark.mapping_anchor_view import ANCHOR_SCRIPT, render_anchor_controls
from autospine_workbench.resolved_project import canonical_sha256


class AnchorViewTests(unittest.TestCase):
    def test_binding_is_canonical_and_markup_cannot_embed_candidate_names(self):
        candidate = {"name": "</script><img src=x>", "authority": "none"}
        markup = render_anchor_controls(candidate)
        self.assertIn(canonical_sha256(candidate), markup)
        self.assertNotIn(candidate["name"], markup)
        self.assertNotIn("fetch(", ANCHOR_SCRIPT)

    @unittest.skipUnless(shutil.which("node"), "Node is unavailable")
    def test_letterbox_pairing_undo_clear_and_bound_download(self):
        harness = r'''
const assert = require('node:assert/strict'), vm = require('node:vm');
let download;
function node() {
  return {listeners:{},children:[],textContent:'',dataset:{},style:{},disabled:false,
    addEventListener(name,callback){this.listeners[name]=callback},
    appendChild(value){this.children.push(value)},replaceChildren(){this.children=[]},click(){},remove(){}};
}
const nodes = {};
for(const name of ['anchor-binding','source','composite','anchor-list','anchor-status','anchor-download','anchor-undo','anchor-clear','anchor-load','anchor-markers']) nodes[name]=node();
nodes['anchor-binding'].dataset.candidateSha='a'.repeat(64);
// 200x100 source letterboxed vertically in a 200x200 content box with 1px borders.
Object.assign(nodes.source,{complete:true,naturalWidth:200,naturalHeight:100,
  clientWidth:200,clientHeight:200,offsetWidth:202,offsetHeight:202,clientLeft:1,clientTop:1,
  getBoundingClientRect(){return {left:10,top:20,width:202,height:202}}});
// 100x200 PSD letterboxed horizontally in a 200x200 content box.
Object.assign(nodes.composite,{complete:true,naturalWidth:100,naturalHeight:200,
  clientWidth:200,clientHeight:200,offsetWidth:202,offsetHeight:202,clientLeft:1,clientTop:1,
  getBoundingClientRect(){return {left:300,top:20,width:202,height:202}}});
const events={};
const sandbox = {window:{addEventListener:(name,callback)=>events[name]=callback},
 document:{getElementById:id=>nodes[id],createElement:node,body:node()},
 URL:{createObjectURL:blob=>{download=JSON.parse(blob.text);return 'blob:local'},revokeObjectURL(){}},
 Blob:class{constructor(parts){this.text=parts.join('')}},setTimeout:callback=>callback()};
vm.runInNewContext(SCRIPT,sandbox);
const click=(id,x,y)=>nodes[id].listeners.click({clientX:x,clientY:y});
const count=()=>nodes['anchor-list'].children.length;
const save=()=>nodes['anchor-download'].listeners.click();
assert.equal(nodes['anchor-download'].disabled,true);
click('composite',371,61);assert.equal(count(),0); // cannot pair before PNG
click('source',21,31);click('composite',371,61);assert.equal(count(),0); // vertical blank ignored
click('source',21,81);click('composite',311,61);assert.equal(count(),0); // horizontal blank ignored
click('composite',371,61);assert.equal(count(),1);
assert.equal(nodes['anchor-markers'].children.length,2);
assert.equal(nodes['anchor-markers'].children[0].style.left,'21px');
assert.equal(nodes['anchor-markers'].children[0].style.top,'81px');
assert.equal(typeof events.scroll,'function');assert.equal(typeof events.resize,'function');
click('source',21,81);click('composite',391,101);assert.equal(count(),1); // duplicate PNG ignored
click('source',51,101);click('composite',371,61);assert.equal(count(),1); // duplicate PSD retains pending
click('composite',391,101);assert.equal(count(),2);
save();assert.equal(download.candidate_sha256,'a'.repeat(64));assert.equal(download.authority,'none');
assert.equal(download.schema,'autospine.benchmark-mapping-anchors/v1');
assert.deepEqual(download.anchors,[{id:'anchor-1',png:[10,10],psd:[20,40]},
 {id:'anchor-2',png:[40,30],psd:[40,80]}]);
click('source',61,111);assert.equal(nodes['anchor-download'].disabled,true);
nodes['anchor-undo'].listeners.click();assert.equal(count(),2); // removes pending only
nodes['anchor-undo'].listeners.click();assert.equal(count(),1);
nodes['anchor-clear'].listeners.click();assert.equal(count(),0);
assert.equal(nodes['anchor-download'].disabled,true);
// CSS-scaled rect must still use natural pixels, including its scaled border.
nodes.source.getBoundingClientRect=()=>({left:10,top:20,width:404,height:404});
click('source',32,142);click('composite',371,61);
assert.match(nodes['anchor-list'].children[0].textContent,/PNG \(10.00, 10.00\)/);
nodes['anchor-clear'].listeners.click();
// More than 32 pairs cannot be added.
nodes.source.getBoundingClientRect=()=>({left:10,top:20,width:202,height:202});
for(let i=0;i<33;i++){click('source',11+i,71+i);click('composite',351+i,21+i);}
assert.equal(count(),32);save();assert.equal(download.anchors.length,32);
(async()=>{
 const before=JSON.stringify(download);
 const imported=JSON.parse(before);imported.candidate_sha256='b'.repeat(64);
 async function load(value){nodes['anchor-load'].files=[{size:2000,text:async()=>JSON.stringify(value)}];await nodes['anchor-load'].listeners.change();}
 await load(imported);assert.equal(count(),32);save();assert.equal(JSON.stringify(download),before);
 imported.candidate_sha256='a'.repeat(64);imported.anchors=imported.anchors.slice(0,2);
 imported.anchors[0].png=[999,999];await load(imported);assert.equal(count(),32);
 imported.anchors[0].png=[0,0];await load(imported);assert.equal(count(),2);
 save();assert.equal(download.anchors.length,2);assert.equal(download.authority,'none');
 imported.anchors[0].id='left-shoulder';imported.anchors[1].id='anchor-3';
 await load(imported);save();assert.deepEqual(download.anchors,imported.anchors);
 assert.match(nodes['anchor-list'].children[0].textContent,/left-shoulder/);
 for(let i=10;i<13;i++){click('source',11+i,71+i);click('composite',351+i,21+i);}
 save();assert.deepEqual(download.anchors.map(anchor=>anchor.id),
   ['left-shoulder','anchor-3','anchor-1','anchor-2','anchor-4']);
 assert.equal(new Set(download.anchors.map(anchor=>anchor.id)).size,5);
})().catch(error=>{console.error(error);process.exitCode=1});
'''
        result = subprocess.run([shutil.which("node"), "-e",
                                 "const SCRIPT=" + json.dumps(ANCHOR_SCRIPT) + ";\n" + harness],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
