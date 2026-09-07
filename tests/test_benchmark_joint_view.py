"""Offline viewer uses real JavaScript for scaling, edits, undo and validation."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from autospine_workbench.benchmark.joint_draft import build_joint_draft, JOINTS
from autospine_workbench.benchmark.joint_view import render_joint_review, _SCRIPT
from tests.test_benchmark_joint_draft import candidate

PNG = b'\x89PNG\r\n\x1a\npage-fixture-only'


class JointViewTests(unittest.TestCase):
    def source(self):
        return dict(candidate(), composite_sha256=hashlib.sha256(PNG).hexdigest())

    def test_bound_image_offline_and_escaped_notes(self):
        source = self.source()
        draft = build_joint_draft(source)
        draft['records'][0]['notes'] = '</script><img src=x>'
        page = render_joint_review(source, PNG, draft=draft)
        self.assertNotIn('</script><img src=x>', page)
        self.assertIn("connect-src 'none'", page)
        self.assertIn('data:image/png;base64,', page)
        with self.assertRaises(ValueError):
            render_joint_review(source, PNG+b'changed')

    @unittest.skipUnless(shutil.which('node'), 'Node unavailable')
    def test_browser_scaled_click_unobservable_undo_and_restore_validation(self):
        data = {'draft': build_joint_draft(self.source()), 'canvas': [200, 100], 'joints': JOINTS}
        harness = r'''
const assert=require('node:assert/strict'), elements={};
const context=new Proxy({}, {get:()=>()=>{}});
function element(id){return elements[id]??=( {value:'',textContent:'',files:[],complete:true,naturalWidth:200,naturalHeight:100,
 append(o){if(!this.value)this.value=o.value;},getContext(){return context;},getBoundingClientRect(){return {left:10,top:20,width:400,height:200};}});}
global.document={getElementById:element,createElement:()=>({})};
element('joint-data').textContent=JSON.stringify(INPUT);
'''.replace('INPUT', json.dumps(data))
        assertions = r'''
canvas.onclick({clientX:210,clientY:120});
assert.deepEqual(draft.records[0].position,[100,50]);
assert.equal(draft.records[0].status,'observed');
el('unobservable').onclick();assert.equal(draft.records[0].status,'observed');
el('notes').value='遮挡';el('unobservable').onclick();
assert.equal(draft.records[0].status,'unobservable');assert.equal(draft.records[0].position,null);
el('undo').onclick();assert.deepEqual(draft.records[0].position,[100,50]);
el('clear').onclick();assert.equal(draft.records[0].status,'unmarked');
img.naturalWidth=199;canvas.onclick({clientX:210,clientY:120});
assert.equal(draft.records[0].status,'unmarked');img.naturalWidth=200;
let bad=clone(draft);bad.candidate_sha256='0'.repeat(64);assert.throws(()=>valid(bad));
bad=clone(draft);bad.records[0].position=[1,2];assert.throws(()=>valid(bad));
bad=clone(draft);bad.records.reverse();assert.throws(()=>valid(bad));
el('restore').files=[{size:10,text:async()=>JSON.stringify(data.draft)}];
(async()=>{await el('restore').onchange();assert.deepEqual(draft,data.draft);})();
'''
        result = subprocess.run([shutil.which('node'), '-e', harness + _SCRIPT + assertions],
                                capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
