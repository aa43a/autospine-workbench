"""Baked keys, local interpolation, loop closure and exact report replay."""
import json
import math
from pathlib import Path
from copy import deepcopy
import unittest
from autospine_workbench.asset.joints.elbow_bake import angle_at,build_bake,validate_bake,replay
from autospine_workbench.asset.joints.elbow_constraints import solve


class ElbowBakeTests(unittest.TestCase):
    def setUp(self):
        from tests import test_elbow_constraints
        fixture=test_elbow_constraints.ElbowConstraintsTests()
        fixture.setUp()
        self.row,self.bones,self.ctx=fixture.row,fixture.bones,fixture.ctx
        self.mesh={'profile':'joint-plane-three-bone-v2','layers':[self.row]}
        self.skeleton={'bones':self.bones}

    def test_loop_schedule(self):
        self.assertEqual([angle_at(i) for i in (0,15,30,45,60)],[0,90,0,-90,0])

    def test_keys_reconstruct_and_interpolation_is_measured(self):
        doc=build_bake(self.mesh,self.skeleton);layer=doc['layers'][0]
        self.assertEqual(len(layer['frames']),61)
        for index in (0,15,30,45,60):
            key=layer['frames'][index]
            for p,q in zip(replay(self.row,self.bones,key,key,0),solve(self.ctx,angle_at(index))):
                self.assertLess(math.dist(p,q),1e-12)
        self.assertLess(layer['qa']['loop_max_error'],1e-12)
        self.assertGreater(layer['qa']['max_interpolation_error_px'],0)
        from jsonschema import Draft202012Validator
        schema=json.loads((Path(__file__).resolve().parents[1]/'schemas/elbow-bake-v1.schema.json').read_text('utf-8'))
        Draft202012Validator(schema).validate(doc)

    def test_determinism_and_tampering(self):
        before=deepcopy(self.mesh);doc=build_bake(self.mesh,self.skeleton)
        validate_bake(self.mesh,self.skeleton,doc)
        self.assertEqual(self.mesh,before)
        doc['layers'][0]['frames'][15]['offsets'][0][0][0]+=1
        with self.assertRaisesRegex(ValueError,'elbow_bake_mismatch'):validate_bake(self.mesh,self.skeleton,doc)

    def test_absent_mesh_does_not_pass(self):
        self.row['weights']=[]
        self.assertEqual(build_bake(self.mesh,self.skeleton)['layers'][0]['status'],'not_evaluated')

    def test_view_rejects_wrong_texture_candidate(self):
        from autospine_workbench.benchmark.elbow_bake_view import render
        self.skeleton['candidate_sha256']='0'*64
        doc=build_bake(self.mesh,self.skeleton)
        with self.assertRaisesRegex(ValueError,'elbow_bake_texture_source_mismatch'):
            render(self.mesh,self.skeleton,doc,{}, {})
