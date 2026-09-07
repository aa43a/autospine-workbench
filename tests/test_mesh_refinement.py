"""Separate refinement identity and unchanged baseline topology."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from tests.test_mesh_candidate import fixture
from autospine_workbench.asset.joints.mesh_candidate import build_mesh_candidate
from autospine_workbench.asset.joints.mesh_refinement import refine_mesh_weights,validate_mesh_refinement
from autospine_workbench.resolved_project import canonical_sha256


class MeshRefinementTests(unittest.TestCase):
    def test_preserve_baseline_and_grid_exactly(self):
        args=fixture();base=build_mesh_candidate(*args);before=deepcopy(base)
        _,_,sk,bindings,draft,_=args
        doc=refine_mesh_weights(base,sk,bindings,draft)
        self.assertEqual(base,before)
        self.assertEqual(doc['source_mesh_sha256'],canonical_sha256(base))
        for old,new in zip(base['layers'],doc['layers']):
            for field in ('vertices_xy','triangles','uvs'):self.assertEqual(old[field],new[field])
        self.assertNotEqual(doc['layers'][1]['weights'],base['layers'][1]['weights'])
        self.assertEqual(validate_mesh_refinement(base,sk,bindings,draft,doc),doc)
        from jsonschema import Draft202012Validator
        schema=json.loads((Path(__file__).resolve().parents[1]/'schemas/weighted-mesh-refinement-v1.schema.json').read_text('utf-8'))
        Draft202012Validator(schema).validate(doc)
        doc['layers'][1]['weights'][0][0]['weight']=.99
        with self.assertRaises(ValueError):validate_mesh_refinement(base,sk,bindings,draft,doc)

    def test_unknown_source_rejected_and_pending_stays_pending(self):
        args=fixture();base=build_mesh_candidate(*args);_,_,sk,bindings,draft,_=args
        doc=refine_mesh_weights(base,sk,bindings,draft)
        self.assertEqual(doc['layers'][0],base['layers'][0])
        base['source_draft_sha256']='0'*64
        with self.assertRaises(ValueError):refine_mesh_weights(base,sk,bindings,draft)
