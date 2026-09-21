from copy import deepcopy
import json
import unittest
from unittest.mock import patch
from test_depth_region_partition import source
from autospine_workbench.targets.character43.depth_region_partition import build
from autospine_workbench.targets.character43.regional_depth_profile import apply, partition_slots, remap_setup


class RegionalProfileTests(unittest.TestCase):
    def fixture(self):
        doc, files = source()
        files['skirt-trial.json'] = json.dumps(dict(profile='fixed-waist-three-chain-sway-v1', rows=[dict(layer_id='a')])).encode()
        candidate, partition = build(doc, ['a'])
        report = dict(depth=dict(pairs=[]), refinement=dict(rows=[]), partition=partition,
            order=dict(status='no_visible_order_change', failures=[], reason_codes=[], frames=[]),
            cloth_constraints=dict(unmeasured_samples=0), limb_constraints=dict(unmeasured_samples=0))
        return doc, files, candidate, report

    def test_exact_skirt_provenance_not_layer_name(self):
        doc, files, _, _ = self.fixture()
        self.assertEqual(partition_slots(files, doc), ['a'])
        self.assertEqual(partition_slots({}, doc), [])
        files['skirt-trial.json'] = json.dumps(dict(profile='fixed-waist-three-chain-sway-v1', rows=[dict(layer_id='missing')])).encode()
        with self.assertRaisesRegex(ValueError, 'inventory'): partition_slots(files, doc)

    def test_setup_vertices_follow_source_partition_without_aliasing(self):
        _, _, _, report = self.fixture(); vertices = dict(a=[[1, 2]], b=[[3, 4]])
        result = remap_setup(vertices, report['partition'])
        self.assertNotIn('a', result)
        self.assertEqual(result['a-depth-001'], vertices['a'])
        result['a-depth-001'][0][0] = 10
        self.assertEqual(vertices['a'], [[1, 2]])
        self.assertEqual(result['a-depth-002'], [[1, 2]])

    def test_missing_checks_preserve_original_candidate(self):
        doc, files, candidate, report = self.fixture()
        for key in ('refinement', 'cloth_constraints', 'limb_constraints'):
            evidence = deepcopy(report)
            if key == 'refinement': evidence[key]['rows'] = [dict(checks=[dict(status='unmeasured')])]
            else: evidence[key]['unmeasured_samples'] = 1
            with patch('autospine_workbench.targets.character43.regional_depth_profile.build', return_value=(candidate, evidence)):
                result, depth, transform = apply(doc, files, 'test', {}, object(), {})
            self.assertIs(result, doc)
            self.assertFalse(depth['selected'])
            self.assertIsNone(transform)

    def test_success_records_exact_transform(self):
        doc, files, candidate, report = self.fixture()
        with patch('autospine_workbench.targets.character43.regional_depth_profile.build', return_value=(candidate, report)):
            result, depth, transform = apply(doc, files, 'test', {}, object(), {})
        self.assertEqual(result, candidate)
        self.assertTrue(depth['selected'])
        self.assertEqual(transform['partition_slots'], ['a'])
