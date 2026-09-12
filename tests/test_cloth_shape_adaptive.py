import json
import unittest
from unittest.mock import patch
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.cloth_shape_adaptive import build


class AdaptiveTests(unittest.TestCase):
    def trial(self, passed):
        setup = [[0, 0], [1, 0], [0, 1]]
        points = setup if passed else [[0, 0], [1, 0], [0, -1]]
        return {'deformation.json': canonical_bytes({'passed': passed}),
                'cloth-shape.json': canonical_bytes({'sample_count': 3}),
                'numeric-reference.json': canonical_bytes({'animations': {'wave': [
                    {'time': 0, 'vertices': {'fabric': setup}},
                    {'time': .25, 'vertices': {'fabric': points}}]}})}

    def test_failed_time_is_resolved_before_pass_without_selection(self):
        document = {'skins': [{'attachments': {'fabric': {'fabric': {'triangles': [0, 1, 2]}}}}]}
        with patch('autospine_workbench.targets.character43.cloth_shape_adaptive.bake',
                   side_effect=[self.trial(False), self.trial(True)]) as bake:
            files = build(document, 'wave', 'cloth-fabric')
        self.assertEqual(bake.call_args_list[1].kwargs['extra_times'], [.25])
        report = json.loads(files['cloth-adaptive.json'])
        self.assertTrue(report['geometry_passed'])
        self.assertFalse(report['selected'])
        self.assertEqual(len(report['rounds']), 2)

    def test_unchanged_failure_stops_and_remains_failed(self):
        document = {'skins': [{'attachments': {'fabric': {'fabric': {'triangles': [0, 1, 2]}}}}]}
        with patch('autospine_workbench.targets.character43.cloth_shape_adaptive.bake',
                   return_value=self.trial(False)) as bake:
            files = build(document, 'wave', 'cloth-fabric')
        self.assertEqual(bake.call_count, 2)
        self.assertFalse(json.loads(files['cloth-adaptive.json'])['geometry_passed'])
