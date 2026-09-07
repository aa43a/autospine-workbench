"""Synthetic editing, immutable draft intake, restore and source tamper checks."""
import json
import shutil
import subprocess
import unittest

from tests import test_region_binding_cli as fixtures
from tests.test_region_binding import fixture
from autospine_workbench.asset.joints.region_binding import build_region_bindings
from autospine_workbench.benchmark.region_binding_draft import build_binding_draft
from autospine_workbench.benchmark.region_binding_controls import SCRIPT
from autospine_workbench.benchmark.region_binding_cli import read_binding_draft
from autospine_workbench.benchmark.__main__ import parser, _execute
from autospine_workbench.resolved_project import canonical_sha256


class BindingDraftCliTests(unittest.TestCase):
    def test_record_resume_and_source_revalidation(self):
        f = fixtures.RegionBindingCliTests(); f.setUp(); self.addCleanup(f.doCleanups)
        bindings = f.build()[0]
        draft = build_binding_draft(bindings)
        draft['records'][0].update(action='semantic_review', notes='Synthetic only\nNeeds semantic review')
        path = f.f.root/'draft.json'; path.write_text(json.dumps(draft), encoding='utf-8')
        out = f.f.root/'draft-out.json'
        args = ['--state-root', f.f.state, 'build-region-bindings', '--manifest', f.f.root/'manifest.json',
                '--workspace', f.f.root, '--skeleton', f.f.root/'skeleton.json', '--html', f.f.root/'resumed.html',
                '--draft', path, '--draft-output', out]
        parsed = parser().parse_args(list(map(str,args)))
        self.assertEqual(_execute(parsed)[0], bindings)
        self.assertEqual(json.loads(out.read_text('utf-8')), draft)
        self.assertEqual(read_binding_draft(f.f.state, f.f.manifest, canonical_sha256(draft), workspace=f.f.root), draft)
        self.assertEqual(_execute(parsed)[0], bindings)
        (f.f.root/'layer-0.png').write_bytes(b'changed')
        with self.assertRaises(ValueError):
            read_binding_draft(f.f.state, f.f.manifest, canonical_sha256(draft), workspace=f.f.root)

    def test_browser_validation_matches_contract(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('node unavailable')
        bindings = build_region_bindings(*fixture()); draft = build_binding_draft(bindings)
        test = '''
const assert = require('node:assert/strict');
assert.deepEqual(validateDraft(bindings,base,base),base);
let edited=structuredClone(base); edited.records[0].action='bind'; edited.records[0].bone_id='head';
assert.equal(validateDraft(bindings,base,edited).records[0].bone_id,'head');
edited.records[1].action='requires_split'; edited.records[1].notes='two parts\\nseparate';
validateDraft(bindings,base,edited);
const before=JSON.stringify(base);
for (const mutate of [d=>d.source_bindings_sha256='0'.repeat(64),d=>d.records.reverse(),
d=>d.records[0].bone_id='unknown',d=>d.records[1].notes='',d=>d.production_authorized=true]) {
 const bad=structuredClone(edited); mutate(bad); assert.throws(()=>validateDraft(bindings,base,bad));
}
assert.equal(JSON.stringify(base),before);
'''
        program = SCRIPT+'\nconst bindings='+json.dumps(bindings)+';const base='+json.dumps(draft)+';\n'+test
        result = subprocess.run([node, '-'], input=program, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
