"""Area loss is distinct from inversion; winding and replay stay deterministic."""
from copy import deepcopy
import unittest
import json
from pathlib import Path
from tests.test_mesh_weights import chain
from autospine_workbench.asset.joints.mesh_area import analyze_area, build_area_report, validate_area_report


class MeshAreaTests(unittest.TestCase):
    def fixture(self, blend=.5):
        vertices = [[9,0],[11,0],[10,2]]
        weights = [[{'bone_id':'upperarm','weight':1-blend,'local_xy':p[:]},
                    {'bone_id':'forearm','weight':blend,'local_xy':[p[0]-10,p[1]]}]
                   for p in vertices]
        return vertices, [[0,1,2]], weights, chain()

    def test_rigid_preserves_area(self):
        report = analyze_area(*self.fixture(0))
        self.assertEqual(report['status'], 'passed')
        self.assertAlmostEqual(report['min_area_ratio'], 1)

    def test_half_rotation_mix_loses_half_area_without_inversion(self):
        report = analyze_area(*self.fixture())
        self.assertAlmostEqual(report['min_area_ratio'], .5)
        self.assertEqual(report['inverted_triangle_samples'], 0)

    def test_winding_and_immutability(self):
        args = self.fixture()
        before = deepcopy(args)
        first = analyze_area(*args)
        self.assertEqual(args, before)
        args[1][0].reverse()
        self.assertAlmostEqual(first['min_area_ratio'], analyze_area(*args)['min_area_ratio'])

    def test_degenerate_setup_rejected(self):
        args = self.fixture()
        args[0][2] = [10,0]
        with self.assertRaisesRegex(ValueError, 'mesh_area_degenerate_setup'):
            analyze_area(*args)

    def test_empty_is_not_pass_and_tampering_fails(self):
        mesh = {'layers':[{'layer_id':'missing','weights':[]}]}
        skeleton = {'bones':chain()}
        doc = build_area_report(mesh,skeleton)
        from jsonschema import Draft202012Validator
        schema = json.loads((Path(__file__).resolve().parents[1]/'schemas/mesh-area-report-v1.schema.json').read_text('utf-8'))
        Draft202012Validator(schema).validate(doc)
        self.assertEqual(doc['layers'][0]['status'],'not_evaluated')
        validate_area_report(mesh,skeleton,doc)
        doc['production_authorized'] = True
        with self.assertRaisesRegex(ValueError,'mesh_area_report_mismatch'):
            validate_area_report(mesh,skeleton,doc)

    def test_joint_gradient_blocks_compression_even_without_inversion(self):
        from autospine_workbench.asset.joints.joint_plane_weights import weights_for_vertices
        vertices = [[8,1],[9,1],[9,2]]
        weights = weights_for_vertices(vertices,chain())
        result = analyze_area(vertices,[[0,1,2]],weights,chain())
        self.assertEqual(result['status'],'blocked')
        self.assertIn('mesh_area_compression',result['reason_codes'])
        self.assertEqual(result['inverted_triangle_samples'],0)

    def test_populated_schema_and_view(self):
        from autospine_workbench.asset.joints.joint_plane_weights import weights_for_vertices
        from autospine_workbench.benchmark.mesh_area_view import render_area
        from jsonschema import Draft202012Validator
        vertices = [[8,1],[9,1],[9,2]]
        mesh = {'layers':[{'layer_id':'<unsafe>', 'vertices_xy':vertices,
                          'triangles':[[0,1,2]], 'weights':weights_for_vertices(vertices,chain())}]}
        skeleton = {'bones':chain()}
        doc = build_area_report(mesh,skeleton)
        schema = json.loads((Path(__file__).resolve().parents[1]/'schemas/mesh-area-report-v1.schema.json').read_text('utf-8'))
        Draft202012Validator(schema).validate(doc)
        html = render_area(mesh,skeleton,doc)
        self.assertIn('&lt;unsafe&gt;',html)
        self.assertNotIn('<unsafe>',html)
        self.assertIn('#ff5555',html)
        doc['layers'][0]['status'] = 'passed'
        with self.assertRaisesRegex(ValueError,'mesh_area_report_mismatch'):
            render_area(mesh,skeleton,doc)
