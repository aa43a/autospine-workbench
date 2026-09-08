"""Correction stays bounded and preserves fixed vertices and setup identity."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from tests.test_partition_mesh import fixture
from autospine_workbench.asset.joints.partition_mesh import build_region
from autospine_workbench.asset.joints.distal_corrective import prepare,sample,ANGLES


class DistalCorrectiveTests(unittest.TestCase):
    def context(self):
        args=fixture();row=build_region(*args)
        return prepare(row,args[-1]['bones'])

    def test_setup_exact_and_offsets_reconstruct_all_angles(self):
        context=self.context();before=deepcopy(context)
        for angle in ANGLES:
            result=sample(context,angle);qa=result['qa']
            self.assertLessEqual(qa['projection_displacement_px'],context['budget']+1e-7)
            self.assertLess(qa['fixed_vertex_error'],1e-7)
            self.assertLess(qa['offset_reconstruction_error'],1e-7)
            self.assertEqual(len(result['offsets']),len(context['row']['weights']))
        self.assertEqual(sample(context,0)['positions'],context['row']['vertices_xy'])
        self.assertEqual(context,before)

    def test_determinism_zero_budget_and_invalid_angles(self):
        context=self.context()
        self.assertEqual(sample(context,60),sample(context,60))
        context['budget']=0
        self.assertLess(sample(context,90)['qa']['projection_displacement_px'],1e-7)
        for bad in (91,float('nan'),True):
            with self.assertRaises(ValueError):sample(context,bad)

    def test_report_schema_and_angle_control(self):
        from autospine_workbench.benchmark.distal_corrective_cli import analyze
        from autospine_workbench.benchmark.distal_corrective_view import render_corrective
        from autospine_workbench.resolved_project import canonical_sha256
        args=fixture();row=build_region(*args)
        mesh={'profile':'partition-full-alpha-supported-v2','source_skeleton_sha256':canonical_sha256(args[-1]),'layers':[row]}
        report=analyze(mesh,args[-1])
        try:
            from jsonschema import Draft202012Validator
        except ImportError:self.skipTest('jsonschema unavailable')
        root=Path(__file__).resolve().parents[1]
        Draft202012Validator(json.loads((root/'schemas/distal-corrective-v1.schema.json').read_text('utf-8'))).validate(report)
        html=render_corrective({'canvas':[24,80],'composite_sha256':hashlib.sha256(args[0]).hexdigest()},args[0],report)
        script=html.rsplit('<script>',1)[1].split('</script>')[0]
        node=shutil.which('node')
        if not node:self.skipTest('node unavailable')
        program='''const frames=Array.from({length:9},(_,i)=>({dataset:{frame:String(i)},style:{}}));
const input={value:'8'},out={};const card={querySelector:s=>s==='input'?input:out,querySelectorAll:()=>frames};
const document={querySelectorAll:()=>[card]};
'''+script+'''
input.oninput({target:input});require('node:assert/strict').equal(out.textContent,'90°');
require('node:assert/strict').equal(frames.filter(f=>f.style.display==='inline').length,1);
require('node:assert/strict').equal(frames[8].style.display,'inline');
'''
        result=subprocess.run([node,'-'],input=program,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
