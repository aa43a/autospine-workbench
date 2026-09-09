from copy import deepcopy
import json
from pathlib import Path
import unittest
from autospine_workbench.asset.planning.component_ownership import template, validate
from autospine_workbench.asset.planning.component_partition_review import render
from tests.test_component_partitions import fixture
from autospine_workbench.asset.planning.component_partitions import build


class ComponentOwnershipTests(unittest.TestCase):
    def setUp(self):
        layer, raw = fixture(); layer['name'] = 'sleeve <test>'
        self.entries = [(layer, raw, build(layer, raw), 'a' * 64)]
        self.expected = template('test', self.entries, {'input_identity_sha256': 'b'*64}, 'c'*64, ['arm', 'hand'])

    def test_roundtrip_and_partial_assignment_no_authority(self):
        value = deepcopy(self.expected)
        value['records'][0].update(status='assigned', semantic='wear.sleeve', side='left', bone_ids=['arm','hand'])
        self.assertEqual(validate(value, self.expected), value)
        self.assertEqual(self.expected['records'][0]['status'], 'pending')
        self.assertFalse(value['production_authorized'])
        self.assertEqual(value['records'][-1]['status'], 'pending')
        import jsonschema
        jsonschema.validate(value, json.loads(Path('schemas/component-ownership-draft-v1.schema.json').read_text()))

    def test_wrong_source_incomplete_inventory_and_residual_assignment_rejected(self):
        for mutate in [lambda v: v.update(project_id='other'), lambda v: v['records'].pop(),
                       lambda v: v['sources'].update(plan_sha256='d'*64),
                       lambda v: v['records'][-1].update(status='assigned', semantic='wear.sleeve', side='left', bone_ids=['arm']),
                       lambda v: v['records'][0].update(status='assigned', semantic='wear.sleeve', side='left', bone_ids=['absent'])]:
            value = deepcopy(self.expected); mutate(value)
            with self.assertRaises(ValueError): validate(value, self.expected)

    def test_report_embeds_safe_standalone_draft_controls(self):
        html = render('test', self.entries, self.expected)
        self.assertIn('sleeve &lt;test&gt;', html)
        self.assertIn('mountComponentOwnership(document,', html)
        self.assertIn('data-component="component-0000"', html)
        self.assertNotIn('export function', html)

    def test_full_canvas_bones_preserve_local_pixel_coordinates(self):
        scene = dict(canvas=[100,200],composite=self.entries[0][1],bones=[
            dict(id='arm_l',head_xy=[15,25],tail_xy=[18,35])])
        html = render('test',self.entries,self.expected,scene=scene)
        self.assertIn('viewBox="0 0 100 200"',html)
        self.assertIn('transform="translate(10 20)"',html)
        self.assertIn('data-bone="arm_l"',html)
        self.assertIn('x1="15" y1="25" x2="18" y2="35"',html)
        self.assertNotIn('import { mountComponentBones',html)
