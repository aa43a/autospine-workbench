"""Bounded corrections preserve anchors, setup and local-offset replay."""
import math
import unittest
from copy import deepcopy
from tests.test_mesh_weights import chain
from autospine_workbench.asset.joints.joint_plane_weights import weights_for_vertices
from autospine_workbench.asset.joints.elbow_constraints import prepare,solve
from autospine_workbench.asset.joints.elbow_alternatives import deform
from autospine_workbench.asset.joints.elbow_constraint_report import measure,local_offsets,build_report,validate_report
from autospine_workbench.asset.joints.mesh_weights import _deform,_frames


class ElbowConstraintsTests(unittest.TestCase):
    def setUp(self):
        self.bones=chain()
        vertices=[[0,0],[8,1],[9,1],[9,2],[20,0],[20,2]]
        self.row={'layer_id':'arm','vertices_xy':vertices,'triangles':[[1,2,3]],
                  'weights':weights_for_vertices(vertices,self.bones)}
        self.ctx=prepare(self.row,self.bones)

    def test_setup_and_locked_endpoints(self):
        self.assertEqual(solve(self.ctx,0),self.row['vertices_xy'])
        for angle in (-90,90):
            base=deform(self.row['vertices_xy'],self.row['weights'],self.bones,angle,'half_angle_auxiliary')
            result=solve(self.ctx,angle)
            for i,free in enumerate(self.ctx['free']):
                if not free:self.assertEqual(result[i],base[i])
            self.assertLessEqual(max(math.dist(p,q) for p,q in zip(result,base)),self.ctx['max_offset']+1e-9)

    def test_deterministic_and_source_unchanged(self):
        before=deepcopy(self.ctx)
        self.assertEqual(solve(self.ctx,90),solve(self.ctx,90))
        self.assertEqual(self.ctx,before)

    def test_corrective_replay(self):
        for angle in (-90,0,90):
            weights=deepcopy(self.row['weights'])
            for row,deltas in zip(weights,local_offsets(self.ctx,angle)):
                for influence,delta in zip(row,deltas):
                    influence['local_xy']=[a+b for a,b in zip(influence['local_xy'],delta)]
            for p,q in zip(_deform(weights,_frames(self.bones,angle)),solve(self.ctx,angle)):
                self.assertLess(math.dist(p,q),1e-12)

    def test_unsatisfied_constraints_do_not_claim_pass(self):
        self.ctx['free']=[False]*len(self.row['vertices_xy'])
        # Use an intentionally compressed local triangle; locked constraints cannot fix it.
        self.row['vertices_xy'][1:4]=[[9,4],[10,4],[10,5]]
        self.row['weights']=weights_for_vertices(self.row['vertices_xy'],self.bones)
        self.ctx=prepare(self.row,self.bones)
        self.ctx['free']=[False]*len(self.row['vertices_xy'])
        result=measure(self.ctx)
        self.assertEqual(result['status'],'blocked')
        self.assertIn('mesh_area_compression',result['reason_codes'])

    def test_schema_and_tamper(self):
        import json
        from pathlib import Path
        from jsonschema import Draft202012Validator
        mesh={'profile':'joint-plane-three-bone-v2','layers':[self.row]}
        skeleton={'bones':self.bones}
        doc=build_report(mesh,skeleton)
        schema=json.loads((Path(__file__).resolve().parents[1]/'schemas/elbow-constraint-report-v1.schema.json').read_text('utf-8'))
        Draft202012Validator(schema).validate(doc)
        validate_report(mesh,skeleton,doc)
        doc['layers'][0]['min_area_ratio']=9
        with self.assertRaisesRegex(ValueError,'elbow_constraint_report_mismatch'):validate_report(mesh,skeleton,doc)
