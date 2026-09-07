"""Run actual page JavaScript to verify multi-point dragging and batch export."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

from tests.test_benchmark_joint_draft import candidate
from autospine_workbench.benchmark.joint_draft import build_joint_draft, JOINTS
from autospine_workbench.benchmark.joint_view import _SCRIPT


class JointDragTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node unavailable')
    def test_drag_undo_cancel_batch_confirm_and_assisted_export(self):
        draft = build_joint_draft(candidate())
        for i, row in enumerate(draft['records']):
            row.update(position=[20+i*5, 30], status='observed')
        assisted = {'schema': 'autospine.benchmark-assisted-joint-draft/v1', 'authority': 'none',
                    'annotation_mode': 'model_assisted', 'independent_annotation': False,
                    'candidate_sha256': draft['candidate_sha256'], 'source_pose_sha256': 'a'*64,
                    'source_baseline_sha256': 'b'*64, 'reviewed_joint_ids': [], 'draft': draft}
        data = {'draft': draft, 'canvas': [200, 100], 'joints': JOINTS, 'assistance': assisted}
        harness = r'''
const assert=require('node:assert/strict'), elements={};
const context=new Proxy({}, {get:()=>()=>{}});
function element(id){return elements[id]??={value:'',textContent:'',files:[],complete:true,naturalWidth:200,naturalHeight:100,
 append(o){if(!this.value)this.value=o.value;},getContext(){return context;},getBoundingClientRect(){return {left:10,top:20,width:400,height:200};}};}
global.document={getElementById:element,createElement:()=>({})};
element('joint-data').textContent=JSON.stringify(INPUT);
'''.replace('INPUT', json.dumps(data))
        assertions = r'''
assert.equal(exportDraft().reviewed_joint_ids.length,0);
canvas.onpointerdown({clientX:50,clientY:80,pointerId:1,button:0});
canvas.onpointermove({clientX:110,clientY:120,pointerId:1});
canvas.onpointerup({clientX:110,clientY:120,pointerId:1});
canvas.onclick({clientX:110,clientY:120});
assert.deepEqual(draft.records[0].position,[50,50]);
assert.equal(history.length,1);assert.equal(reviewed.size,1);
assert.equal(exportDraft().independent_annotation,false);
el('undo').onclick();assert.deepEqual(draft.records[0].position,[20,30]);assert.equal(reviewed.size,0);
canvas.onpointerdown({clientX:210,clientY:80,pointerId:2,button:0});
assert.equal(el('joint').value,data.joints[16]);
canvas.onpointermove({clientX:600,clientY:-10,pointerId:2});
assert.deepEqual(current().position,[200,0]);canvas.onpointercancel();
assert.deepEqual(draft.records[16].position,[100,30]);assert.equal(reviewed.size,0);
el('confirm-all').onclick();assert.equal(reviewed.size,17);
assert.equal(exportDraft().reviewed_joint_ids.length,17);
assert.equal(exportDraft().draft.records.length,17);
el('undo').onclick();assert.equal(reviewed.size,0);
'''
        result = subprocess.run(['node', '-e', harness+_SCRIPT+assertions], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
